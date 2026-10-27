"""A made worksheet, seen from the front of the room: each question as printed, and the key's answers
written onto it.

Slides show a question by cropping it from worksheet.pdf, so students see exactly what's on their sheet.
The answers go on top as their own text and circles, placed by the boxes in layout.json, so they stay sharp
and editable. The same marks make answer-key.pdf, the worksheet filled in for the teacher.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from . import diagrams as D
from . import fonts as F
from . import sheet as S

DPI = 300  # sharp enough to fill a projector
ANSWER_SHAPES = ("circle", "line", "arrow", "polyline", "polygon", "rect", "text", "plot", "mark")


@dataclass
class Mark:
    """An answer drawn on the page, in page points (origin bottom left)."""
    kind: str  # "text" in a box, or "circle" around a letter
    rect: tuple  # x0, y0, x1, y1
    text: str = ""


class Worksheet:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        for name in ("layout.json", "key.json", "worksheet.pdf"):
            if not (self.folder / name).exists():
                raise FileNotFoundError(f"{self.folder} has no {name}: point at the folder `make` wrote "
                                        "(the one with worksheet.pdf, layout.json, and key.json)")
        self.layout = S.read_json(self.folder / "layout.json")
        self.key = S.read_json(self.folder / "key.json")
        self.defn = S.read_json(self.folder / "worksheet.json") if (self.folder / "worksheet.json").exists() else {}
        self.items = {item["q"]: item for item in self.key["items"]}
        self.boxes, self.page_of = {}, {}
        for page in self.layout["pages"]:
            for b in page["boxes"]:
                if b.get("part", 1) == 1:
                    self.boxes[b["q"]] = b
                    self.page_of[b["q"]] = page["page"]
        self.passages: dict[str, list[tuple[int, tuple]]] = {}  # id: (page, rect) for each piece
        for page in self.layout["pages"]:
            for piece in page.get("passages", []):
                self.passages.setdefault(piece["id"], []).append((page["page"], tuple(piece.get("body_rect")
                                                                                       or piece["rect"])))
        self.style = S.STYLES[self.layout.get("style", "standard")]
        self._pages = None

    @property
    def title(self) -> str:
        return self.layout["title"]

    @property
    def questions(self) -> list[int]:
        return sorted(self.items)

    def pages(self):
        if self._pages is None:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(self.folder / "worksheet.pdf"))
            self._pages = [pdf[i].render(scale=DPI / 72).to_pil().convert("L") for i in range(len(pdf))]
        return self._pages

    def region(self, q: int) -> tuple:
        """The question as students see it, in page points. A written answer's empty lines and a math work
        area are left out: they'd only shrink the prompt."""
        b = self.boxes[q]
        top = b["feedback_rect"][3] + 3
        x0 = S.LEFT - S.OPTION_REACH - 2
        x1 = max(S.BOX_RIGHT, b["rect"][2]) + 4
        if b["type"] in ("short", "math"):
            bottom = b["rect"][3] + 2  # just above the writing box's top edge
        else:
            bottom = min(b["rect"][1], b["feedback_rect"][1]) - 3
        return (x0, bottom, x1, top)

    def crop(self, q: int, path: Path, drawing: list[dict] | None = None, color: str = "C62828") -> tuple[float, float]:
        """Saves the question's picture, with the answer drawn on it in color if there's a drawing; returns
        its size in page points."""
        x0, y0, x1, y1 = self.region(q)
        k = DPI / 72
        box = (int(x0 * k), int((S.PAGE_H - y1) * k), int(x1 * k), int((S.PAGE_H - y0) * k))
        img = self.pages()[self.page_of[q] - 1]
        if drawing:
            img = tint(img.crop(box), self.drawing_layer(q, drawing).crop(box), color)
        else:
            img = img.crop(box)
        img.save(path)
        return x1 - x0, y1 - y0

    def question_def(self, q: int) -> dict:
        return next((b for b in self.defn.get("questions", []) if b.get("q") == q and b.get("type") != "passage"), {})

    def answer_drawing(self, q: int, shapes: list) -> list[dict]:
        """A drawn answer, in the question's diagram coordinates, as diagram shapes. "plot" puts points (in
        graph units) on the diagram's axes, "mark" puts points on its number line. Raises ValueError."""
        d = self.question_def(q).get("diagram")
        if not d:
            raise ValueError(f"question {q} has no diagram to draw the answer on")
        parts = [D.normalize_shape(s) for s in d["shapes"]]
        out = []
        for n, s in enumerate(shapes, start=1):
            where = f"walkthrough for question {q}, draw {n}"
            if not isinstance(s, dict) or s.get("shape") not in ANSWER_SHAPES:
                raise ValueError(f"{where}: \"shape\" must be one of {', '.join(ANSWER_SHAPES)}")
            if s["shape"] == "plot":
                axes = next((p for p in parts if p["shape"] == "axes"), None)
                if not axes:
                    raise ValueError(f"{where}: \"plot\" needs axes in the question's diagram")
                sx = axes["w"] / (axes["xmax"] - axes["xmin"])
                sy = axes["h"] / (axes["ymax"] - axes["ymin"])
                graph = [(float(gx), float(gy)) for gx, gy in s.get("points", [])]
                to_page = lambda gx, gy: (axes["x"] + (gx - axes["xmin"]) * sx, axes["y"] + (gy - axes["ymin"]) * sy)  # noqa: E731
                pts = [to_page(gx, gy) for gx, gy in graph]
                if s.get("extend") and len(graph) > 1:  # the line through the first and last points, edge to edge
                    line = _clip_line(graph[0], graph[-1], axes)
                    if line:
                        out.append(D.normalize_shape({"shape": "line", "points": [to_page(*p) for p in line],
                                                      "width": s.get("width", 2.0)}))
                elif s.get("line") and len(pts) > 1:
                    out.append(D.normalize_shape({"shape": "polyline", "points": pts, "width": s.get("width", 2.0)}))
                out += [D.normalize_shape({"shape": "circle", "x": x, "y": y, "r": s.get("r", 3.2), "fill": 0})
                        for x, y in pts]
            elif s["shape"] == "mark":
                line = next((p for p in parts if p["shape"] == "number_line"), None)
                if not line:
                    raise ValueError(f"{where}: \"mark\" needs a number line in the question's diagram")
                pad = 10 if line["arrows"] else 0
                for v in s.get("at", []):
                    x = line["x"] + pad + (float(v) - line["min"]) / (line["max"] - line["min"]) * (line["w"] - 2 * pad)
                    out.append(D.normalize_shape({"shape": "circle", "x": x, "y": line["y"], "r": s.get("r", 4.0),
                                                  "fill": 0}))
            else:
                out.append(D.normalize_shape({"width": 2.0, **s}))
        return out

    def drawing_layer(self, q: int, shapes: list[dict]):
        """The drawn answer alone, black on white, at the page's size."""
        import io

        import pypdfium2 as pdfium
        d = self.question_def(q)["diagram"]
        rect = self.boxes[q]["rect"]
        fonts, _ = F.choose([s.get("text", "") for s in shapes])
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(S.PAGE_W, S.PAGE_H))
        D.draw_diagram(c, {"shapes": shapes}, rect[0], rect[3] - d["height"], fonts, self.folder)
        c.save()
        return pdfium.PdfDocument(buf.getvalue())[0].render(scale=DPI / 72).to_pil().convert("L")

    def passage_title(self, pid: str) -> str:
        return next((p["title"] for p in self.key.get("passages", []) if p["id"] == pid and p.get("title")), "")

    def crop_rect(self, page: int, rect: tuple, path: Path) -> tuple[float, float]:
        """A piece of a page, trimmed to its ink with a small margin; returns its size in page points."""
        import numpy as np
        x0, y0, x1, y1 = rect
        k = DPI / 72
        img = self.pages()[page - 1].crop((int(x0 * k), int((S.PAGE_H - y1) * k), int(x1 * k),
                                           int((S.PAGE_H - y0) * k)))
        ys, xs = np.nonzero(np.asarray(img) < 160)  # the text, not the light frame around it
        if len(xs):
            m = int(8 * k)
            img = img.crop((max(xs.min() - m, 0), max(ys.min() - m, 0), min(xs.max() + m, img.width),
                            min(ys.max() + m, img.height)))
        img.point(lambda v: 255 if v > 185 else v).save(path)  # the frame's light gray goes; the text stays
        return img.width / k, img.height / k

    def passage(self, pid: str) -> dict:
        """The passage as key.json has it (its printed lines and numbers), and whether it's code."""
        p = next((p for p in self.key.get("passages", []) if p["id"] == pid), None)
        mono = any(b.get("mono") for b in self.defn.get("questions", []) if b.get("type") == "passage"
                   and b.get("id") == pid)
        text = next((b.get("text", "") for b in self.defn.get("questions", []) if b.get("type") == "passage"
                     and b.get("id") == pid), "")
        return {**p, "mono": mono, "text": text} if p else {}

    def thumbnail(self, page: int, path: Path, width_px: int = 900) -> tuple[int, int]:
        img = self.pages()[page - 1]
        small = img.resize((width_px, round(img.height * width_px / img.width)))
        small.save(path)
        return small.size

    def marks(self, q: int) -> list[Mark]:
        """The key's answers, where they'd be written."""
        b, item = self.boxes[q], self.items[q]
        kind = b["type"]
        if kind == "choice":
            option = next((o for o in b["options"] if o["letter"] == item["answer"]), None)
            if not option:
                return []
            cx, cy = option["letter_at"]
            rx, ry = self.style["option_size"] * 0.56, self.style["option_size"] * 0.82  # clear of the option's text
            return [Mark("circle", (cx - rx, cy - ry, cx + rx, cy + ry))]
        out = []
        if kind in ("label", "blanks", "match", "table"):
            answers = {spot["n"]: spot["answer"] for spot in item["labels"]}
            for spot in b["labels"]:
                if spot["n"] in answers:
                    out.append(Mark("text", tuple(spot["rect"]), answers[spot["n"]]))
        if b.get("answer_rect") and item.get("answer"):
            out.append(Mark("text", tuple(b["answer_rect"]), item["answer"]))
        return out

    def answer_text(self, q: int) -> str:
        """The key in a sentence, for slides and the plan."""
        item = self.items[q]
        if item["type"] == "choice":
            return item["key"]
        if item["type"] == "math":
            return f"{item['answer']}" + (f" {item['units']}" if item.get("units") else "")
        if item["type"] == "draw":
            return "; ".join(c["item"].rstrip(". ") for c in item["checklist"]) + "."
        if item["type"] == "short":
            return item["key"]
        return item["key"]


def _clip_line(a: tuple, b: tuple, axes: dict) -> list[tuple] | None:
    """The line through a and b (graph units), cut to the axes' window."""
    (x0, y0), (x1, y1) = a, b
    lo, hi = axes["xmin"], axes["xmax"]
    if x0 == x1:
        return [(x0, axes["ymin"]), (x0, axes["ymax"])] if lo <= x0 <= hi else None
    m = (y1 - y0) / (x1 - x0)
    pts = []
    for x in (lo, hi):  # where it crosses the left and right edges
        y = y0 + m * (x - x0)
        if axes["ymin"] - 1e-9 <= y <= axes["ymax"] + 1e-9:
            pts.append((x, y))
    if m:
        for y in (axes["ymin"], axes["ymax"]):  # and the bottom and top
            x = x0 + (y - y0) / m
            if lo - 1e-9 <= x <= hi + 1e-9:
                pts.append((x, y))
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))
    return [pts[0], pts[-1]] if len(pts) >= 2 else None


def _pts(n: float) -> str:
    return f"{n:g} point{'s' if n != 1 else ''}"


def key_lines(item: dict) -> list[str]:
    """The key with its scoring, for the plan and the answer key: what earns each point."""
    kind = item["type"]
    if kind == "math":
        return [f"Answer ({_pts(item['answer_points'])}): {item['answer']}" + (f" {item['units']}" if item.get("units") else ""),
                f"Work ({_pts(item['work_points'])}): {item['key']}"]
    if kind == "draw":
        out = []
        if item.get("answer"):
            out.append(f"Answer ({_pts(item['answer_points'])}): {item['answer']}")
        out.append("Drawing: " + "; ".join(f"{c['item'].rstrip('. ')} ({_pts(c['points'])})" for c in item["checklist"]))
        return out
    if kind == "short" and item.get("rubric"):
        return [f"Rubric ({_pts(item['points'])}): " + "; ".join(
            f"{c.get('short') or c['criterion'].rstrip('. ')} 0-{c['max']}" for c in item["rubric"]),
            *([f"Full credit: {item['key']}"] if item.get("key") and item["key"] != "Scored on the rubric." else [])]
    if kind == "short":
        return [f"Full credit ({_pts(item['points'])}): {item['key']}"]
    if kind == "choice":
        return [f"Answer ({_pts(item['points'])}): {item['key']}"]
    return [f"Answers ({_pts(item['points'])}): {item['key']}"]


def tint(base, layer, color: str):
    """base (gray) with layer's ink laid on in color."""
    import numpy as np
    from PIL import Image
    b = np.asarray(base.convert("RGB"), dtype=float)
    ink = (255 - np.asarray(layer, dtype=float))[..., None] / 255
    rgb = np.array([int(color[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)
    return Image.fromarray((b * (1 - ink) + rgb * ink).astype("uint8"))


def mark_size(m: Mark, text_w, base: float, share: float = 1.0) -> float:
    """Type size for an answer in its box, in page points: most of the box's height, less if it's long.
    share: how much of the box's width a line may use (a slide's text boxes wrap a little short)."""
    x0, y0, x1, y1 = m.rect
    size = min(base, (y1 - y0) * 0.62)
    while size > 5 and text_w(m.text, size) > (x1 - x0) * share - 4:
        size -= 0.5
    return size


def answer_key(ws: Worksheet, path: Path, drawings: dict | None = None, color: str = "C62828",
               models: dict | None = None) -> None:
    """The worksheet with every answer written in, and the key beside each question. drawings: question
    number to its drawn answer (diagram shapes, from answer_drawing); models: question number to a model
    written answer, for its lines (else the key goes there)."""
    texts = [ws.title, *S.all_texts(ws.defn), *(models or {}).values()]
    for item in ws.items.values():
        texts += [item["key"], item.get("answer", ""), item.get("notes", ""), *key_lines(item)]
        texts += [lvl for c in item.get("rubric", []) for lvl in c["levels"]]
    fonts, _ = F.choose(texts)
    c = canvas.Canvas(str(path), pagesize=(S.PAGE_W, S.PAGE_H))
    c.setTitle(fonts.text(f"{ws.title}: answer key"))
    c.setAuthor("Paper Loop")
    ink = HexColor("#" + color)
    for n, img in enumerate(ws.pages(), start=1):
        for q, shapes in (drawings or {}).items():
            if ws.page_of.get(q) == n and shapes:
                img = tint(img, ws.drawing_layer(q, shapes), color)
        c.drawImage(ImageReader(img), 0, 0, S.PAGE_W, S.PAGE_H)
        c.setFillColor(ink)
        c.setFont(fonts.bold, 16)
        sx0, sy0, sx1, sy1 = ws.layout["pages"][n - 1]["summary_rect"]  # where the feedback summary prints
        c.drawCentredString((sx0 + sx1) / 2, (sy0 + sy1) / 2 - 6, "ANSWER KEY")
        for q, page in ws.page_of.items():
            if page != n:
                continue
            for m in ws.marks(q):
                x0, y0, x1, y1 = m.rect
                c.setStrokeColor(ink)
                c.setFillColor(ink)
                if m.kind == "circle":
                    c.setLineWidth(1.8)
                    c.ellipse(x0, y0, x1, y1, stroke=1, fill=0)
                    continue
                size = mark_size(m, lambda t, s: stringWidth(fonts.text(t), fonts.bold, s), 13)
                c.setFont(fonts.bold, size)
                c.drawCentredString((x0 + x1) / 2, (y0 + y1) / 2 - size * 0.35, fonts.text(m.text))
            _write_in(c, ws, q, (models or {}).get(q), fonts)
            gx0, gy0, gx1, gy1 = ws.boxes[q]["feedback_rect"]
            for size in (8.0, 7.0, 6.5):
                lines = [part for text in key_lines(ws.items[q])
                         for part in simpleSplit(fonts.text(text), fonts.regular, size, gx1 - gx0 - 8)]
                room = int((gy1 - gy0 - 6) // (size * 1.25))
                if len(lines) <= room:
                    break
            if len(lines) > room:  # the whole key is on the scoring page
                lines = lines[:max(room - 1, 1)] + ["(all of it: the scoring page at the end)"]
            c.setFont(fonts.regular, size)
            for k, line in enumerate(lines):
                c.drawString(gx0 + 4, gy1 - size - 2 - size * 1.25 * k, line)
        c.showPage()
    _scoring_pages(c, ws, fonts)
    c.save()


def _write_in(c, ws: Worksheet, q: int, model: str | None, fonts) -> None:
    """A written answer on its lines (the model answer, or the key), and a math key's work in its work area."""
    b, item = ws.boxes[q], ws.items[q]
    x0, y0, x1, y1 = b["rect"]
    if b["type"] == "short":
        text = model or item["key"]
        if not text or text == "Scored on the rubric.":
            return
        spacing = ws.style["line_spacing"]
        n = max(1, int(round((y1 - y0) / spacing)))
        for size in (ws.style["prompt_size"], 10.0, 9.0, 8.0, 7.0):
            lines = simpleSplit(fonts.text(text), fonts.oblique, size, x1 - x0 - 16)
            if len(lines) <= n:
                break
        c.setFont(fonts.oblique, size)
        if len(lines) <= n:  # on the ruled lines
            for k, line in enumerate(lines):
                c.drawString(x0 + 8, y1 - spacing * (k + 1) + 4, line)
        else:  # more than the lines hold: small, evenly spaced, inside the box
            for size in (size, 6.5, 6.0):
                lines = simpleSplit(fonts.text(text), fonts.oblique, size, x1 - x0 - 16)
                if len(lines) * size * 1.2 <= y1 - y0 - 6:
                    break
            c.setFont(fonts.oblique, size)
            for k, line in enumerate(lines):
                y = y1 - size - 3 - size * 1.2 * k
                if y < y0 + 2:
                    break
                c.drawString(x0 + 8, y, line)
    elif b["type"] == "math" and b.get("answer_rect") and item.get("key"):
        top, bottom = y1 - 14, b["answer_rect"][3] + 6  # under "Show your work", above the answer box
        for size in (9.5, 8.5, 7.5, 6.5):
            lines = simpleSplit(fonts.text(item["key"]), fonts.oblique, size, x1 - x0 - 16)
            if len(lines) * size * 1.25 <= top - bottom:
                break
        c.setFont(fonts.oblique, size)
        for k, line in enumerate(lines):
            if top - size * 1.25 * (k + 1) < bottom - size:
                break
            c.drawString(x0 + 8, top - size * 1.25 * (k + 1) + 2, line)


def _scoring_pages(c, ws: Worksheet, fonts) -> None:
    """Every question's key in full, with each rubric's levels: what the margins can't hold."""
    left, width, top, bottom = 54.0, S.PAGE_W - 108, S.PAGE_H - 60, 54.0
    y = top

    def line(text: str, font: str, size: float, indent: float = 0.0, gap: float = 2.0) -> None:
        nonlocal y
        for part in simpleSplit(fonts.text(text), font, size, width - indent) or [""]:
            if y - size < bottom:
                c.showPage()
                y = top
            c.setFont(font, size)
            c.drawString(left + indent, y - size, part)
            y -= size * 1.3
        y -= gap

    line(f"Scoring: {ws.title}", fonts.bold, 16, gap=10)
    for q in ws.questions:
        item = ws.items[q]
        line(f"Question {q} ({_pts(item['points'])})", fonts.bold, 11)
        line(" ".join(item["prompt"].split()), fonts.oblique, 9.5, gap=3)
        for text in key_lines(item):
            line(text, fonts.regular, 10, 10)
        for crit in item.get("rubric", []):
            levels = "; ".join(f"{n}: {lvl}" for n, lvl in enumerate(crit["levels"]))
            line(f"{crit.get('short') or crit['criterion']}: {levels}", fonts.regular, 9.5, 22)
        if item.get("notes"):
            line(f"Notes: {item['notes']}", fonts.regular, 9.5, 10)
        y -= 8
    c.showPage()
