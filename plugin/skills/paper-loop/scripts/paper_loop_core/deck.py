"""The kinds of slide a lesson uses, laid out for a classroom projector.

A Builder turns slide specs (dicts from a lesson file) into slides.Slide objects: it picks type sizes for the
grade, shrinks text to fit down to a floor, and records a warning for anything that still doesn't fit or
has more words than the back row will read. Worksheet questions come from walk.Worksheet as pictures, with
the key's answers drawn over them as text and circles.
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.pdfgen import canvas

from . import diagrams as D
from . import fonts as F
from . import sheet as S
from . import slides as K
from . import walk as WK
from .slides import MUTED, WHITE, Box, Para, Picture, Run, Slide, Text

X0, X1 = K.MARGIN, K.W - K.MARGIN
BOTTOM = K.H - 46  # content stops here; the slide number sits below
TITLE_Y = 32.0
PAD = 22.0  # inside a card
GAP = 20.0  # between blocks


class LessonError(ValueError):
    pass


def _strings(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


class Builder:
    def __init__(self, theme: K.Theme, grade: int, measure: K.Measure, image_dir: Path, base: Path):
        self.t, self.grade, self.m = theme, grade, measure
        self.sz = K.sizes_for(grade)
        self.images, self.base = Path(image_dir), Path(base)
        self.images.mkdir(parents=True, exist_ok=True)
        self.slides: list[Slide] = []
        self.warnings: list[str] = []
        self.smallest: dict[str, float] = {}  # a diagram picture's smallest text, in diagram points
        self._n = 0

    # --- Primitives ----------------------------------------------------------------------

    def where(self) -> str:
        s = self.slides[-1]
        return f"slide {len(self.slides)} ({K.plain(s.title)})"

    def warn(self, text: str) -> None:
        self.warnings.append(f"{self.where()}: {text}")

    def new(self, title: str, notes: str = "", dark: bool = False) -> Slide:
        s = Slide(K.plain(title), [], notes.strip(), self.t.dark if dark else WHITE)
        self.slides.append(s)
        return s

    def finish(self, s: Slide, number: bool = True, words: int | None = None) -> None:
        if number:
            s.elements.append(Text(K.W - X0 - 80, K.H - 34, 80, 16, [Para([Run("")])], 13, MUTED, align="right",
                                   field="slidenum"))
        limit = words or self.sz["words"]
        count = K.words_on(s)
        if count > limit:
            self.warn(f"{count} words; the back row reads about {limit} on a slide like this: cut words, or "
                      "put the rest in \"say\" (the speaker notes)")
        for problem in K.out_of_bounds(s):
            self.warn(problem)

    def heading(self, s: Slide, title: str, chip: str | None = None, chip_fill: str | None = None) -> float:
        """The slide's title, top left. Returns where the content starts."""
        size, floor = self.sz["title"], self.sz["title"] - 8
        chip_w = self.chip_width(chip) + 18 if chip else 0
        width = X1 - X0 - chip_w
        paras = [Para(K.runs(title, bold=True))]
        lines = 1
        while size > floor and self.m.height(paras, width, size, 1.15) > size * 1.15 + 0.5:
            size -= 1
        if self.m.height(paras, width, size, 1.15) > size * 1.15 + 0.5:
            lines = 2
            if self.m.height(paras, width, size, 1.15) > 2 * size * 1.15 + 0.5:
                self.warn("the title is too long for two lines; shorten it")
        h = lines * size * 1.15
        s.elements.append(Text(X0, TITLE_Y, width, h, paras, size, self.t.dark, leading=1.15, role="title"))
        if chip:
            line_w = self.m.line_width(self.m.wrap(paras[0], width, size)[0], size)
            self.chip(s, X0 + min(line_w, width) + 18, TITLE_Y + (size * 1.15 - self.chip_h()) / 2, chip,
                      fill=chip_fill or self.t.accent, color=WHITE)
        return TITLE_Y + h + 24

    def chip_h(self, size: float | None = None) -> float:
        return (size or self.sz["small"] - 4) * 1.75

    def chip_width(self, text: str, size: float | None = None) -> float:
        size = size or self.sz["small"] - 4
        return self.m.width(text, Run(text, bold=True), size) / K.SLACK + size * 1.6

    def chip(self, s: Slide, x: float, y: float, text: str, fill: str, color: str, size: float | None = None) -> float:
        """A rounded label. Returns its width."""
        size = size or self.sz["small"] - 4
        w, h = self.chip_width(text, size), self.chip_h(size)
        s.elements.append(Box(x, y, w, h, fill, radius=h / 2))
        s.elements.append(Text(x, y, w, h, [Para([Run(text, bold=True)])], size, color, align="center",
                               valign="middle"))
        return w

    def text(self, s: Slide, x: float, y: float, w: float, h: float, paras: list[Para], size: float,
             floor: float | None = None, color: str = K.INK, **kw) -> Text:
        """Text shrunk to fit its box, from `size` down to `floor`; a warning if it still doesn't."""
        mono = kw.get("mono", False)
        leading = kw.get("leading", 1.2)
        fitted, ok = self.m.fit(paras, w, h, size, floor or size, leading, mono)
        if not ok:
            self.warn("text doesn't fit at the smallest readable size; cut words or split the slide")
        paras = [Para(p.runs, p.bullet, p.bullet_color, p.space_after * fitted / size) for p in paras]
        needed = self.m.height(paras, w, fitted, leading, mono)
        t = Text(x, y, w, h if kw.get("valign") == "middle" else min(max(needed, fitted * leading), h + 400),
                 paras, fitted, color, **kw)
        s.elements.append(t)
        return t

    def bullets(self, points: list[str], size: float, color: str | None = None) -> list[Para]:
        return [Para(K.runs(p, color), bullet="•", bullet_color=self.t.accent, space_after=size * 0.45)
                for p in points]

    def text_width(self, paras: list[Para], size: float, most: float) -> float:
        """How wide some lines need to be at this size, up to `most`."""
        need = max((self.m.line_width([(t, r) for r in p.runs for t in [r.text]], size) / K.SLACK + self.m.indent(p, size)
                    for p in paras), default=0.0)
        return min(most, need + 8)

    def card(self, s: Slide, x: float, y: float, w: float, h: float, fill: str | None = None) -> None:
        s.elements.append(Box(x, y, w, h, fill or self.t.tint, radius=14))

    def place(self, s: Slide, path: Path, size: tuple[float, float], x: float, y: float, w: float, h: float,
              alt: str, max_scale: float = 99.0, border: str | None = None, align: str = "center") -> tuple:
        """A picture fitted inside a box, keeping its shape. Returns where it went: (x, y, w, h)."""
        iw, ih = size
        k = min(w / iw, h / ih, max_scale)
        pw, ph = iw * k, ih * k
        px = x + (w - pw) / 2 if align == "center" else x
        py = y + (h - ph) / 2
        s.elements.append(Picture(px, py, pw, ph, str(path), alt, border))
        small = self.smallest.get(str(path))
        least = 18 if self.grade <= 3 else 14
        if small and small * k < least:
            self.warn(f"the picture's smallest text prints at {small * k:.0f}pt, too small for the back row "
                      f"(aim for {least}pt): make the diagram's text bigger, or give the picture a slide of its own")
        return px, py, pw, ph

    def image_file(self, name: str) -> Path:
        self._n += 1
        return self.images / f"{self._n:02d}-{name}.png"

    def visual(self, spec: dict, where: str) -> tuple[Path, tuple[float, float], str] | None:
        """A slide's picture: a file the teacher supplied, or a diagram drawn as worksheets draw them."""
        if spec.get("image"):
            from PIL import Image
            src = Path(spec["image"])
            src = src if src.is_absolute() else self.base / src
            if not src.exists():
                raise LessonError(f"{where}: image {spec['image']} not found")
            from PIL import ImageOps
            img = ImageOps.exif_transpose(Image.open(src))  # a phone photo stands the way it was taken
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                paper = Image.new("RGBA", img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(paper, img)
            img = img.convert("RGB")
            path = self.image_file("image")
            img.save(path)
            return path, img.size, spec.get("alt") or spec.get("caption") or src.stem
        if spec.get("diagram"):
            d = spec["diagram"]
            if not isinstance(d, dict) or "width" not in d or "height" not in d:
                raise LessonError(f"{where}: \"diagram\" needs \"width\", \"height\", and \"shapes\", as on a "
                                  "worksheet")
            try:
                d = S._diagram(d, where, faint_images=False)
            except S.WorksheetError as e:
                raise LessonError(str(e)) from None
            path = self.image_file("diagram")
            _diagram_png(d, path, self.base)
            self.smallest[str(path)] = _smallest_text(d)
            return path, (d["width"] + 12, d["height"] + 12), d.get("description") or "diagram"
        return None

    # --- Opening slides --------------------------------------------------------------------

    def title_slide(self, title: str, subtitle: str, chip: str, notes: str = "") -> None:
        s = self.new(title, notes, dark=True)
        x, w = X0 + 24, X1 - X0 - 48
        self.chip(s, x, 140, chip, fill=self.t.accent, color=WHITE, size=17)
        paras = [Para(K.runs(title, bold=True))]
        size, ok = self.m.fit(paras, w, 190, 56, 40, 1.1)
        h = self.m.height(paras, w, size, 1.1)
        s.elements.append(Text(x, 190, w, h, paras, size, WHITE, leading=1.1, role="title"))
        if subtitle:
            self.text(s, x, 190 + h + 18, w, 90, [Para(K.runs(subtitle))], 26, 20, color=self.t.on_dark)
        self.finish(s, number=False)

    def section(self, title: str, subtitle: str = "", chip: str = "", notes: str = "") -> None:
        s = self.new(title, notes, dark=True)
        x, w = X0 + 24, X1 - X0 - 48
        if chip:
            self.chip(s, x, 170, chip, fill=self.t.accent, color=WHITE, size=17)
        paras = [Para(K.runs(title, bold=True))]
        size, _ = self.m.fit(paras, w, 150, 48, 36, 1.1)
        h = self.m.height(paras, w, size, 1.1)
        s.elements.append(Text(x, 218, w, h, paras, size, WHITE, leading=1.1, role="title"))
        if subtitle:
            self.text(s, x, 218 + h + 16, w, 100, [Para(K.runs(subtitle))], 24, 18, color=self.t.on_dark)
        self.finish(s)

    def targets(self, targets: list[str], notes: str = "") -> None:
        s = self.new("Learning target" + ("s" if len(targets) > 1 else ""), notes)
        top = self.heading(s, s.title)
        size = self.sz["body"] + 2
        paras = self.bullets(targets, size)
        fitted, _ = self.m.fit(paras, X1 - X0 - 2 * PAD - 8, BOTTOM - top - 2 * PAD, size, self.sz["floor"])
        h = self.m.height([Para(p.runs, p.bullet, p.bullet_color, p.space_after * fitted / size) for p in paras],
                          X1 - X0 - 2 * PAD - 8, fitted)
        self.card(s, X0, top, X1 - X0, h + 2 * PAD)
        self.text(s, X0 + PAD + 4, top + PAD, X1 - X0 - 2 * PAD - 8, h + 4, paras, fitted, self.sz["floor"])
        self.finish(s)

    def agenda(self, rows: list[tuple[str, int]], notes: str = "") -> None:
        s = self.new("Today", notes)
        top = self.heading(s, "Today")
        size = self.sz["body"]
        room = BOTTOM - top
        row_h = min(size * 2.1, room / max(1, len(rows)))
        size = min(size, row_h / 2.1)
        d = size * 1.45
        for k, (name, minutes) in enumerate(rows):
            y = top + k * row_h
            s.elements.append(Box(X0, y + (row_h - d) / 2, d, d, self.t.accent, shape="oval"))
            s.elements.append(Text(X0, y + (row_h - d) / 2, d, d, [Para([Run(str(k + 1), bold=True)])], size * 0.8,
                                   WHITE, align="center", valign="middle"))
            s.elements.append(Text(X0 + d + 18, y, 620, row_h, [Para(K.runs(name))], size, K.INK, valign="middle"))
            if minutes:
                s.elements.append(Text(X1 - 180, y, 180, row_h, [Para([Run(f"{minutes} min")])], size - 2, MUTED,
                                       align="right", valign="middle"))
        self.finish(s)

    # --- Teaching slides -------------------------------------------------------------------

    def points(self, spec: dict, where: str) -> None:
        s = self.new(spec["title"], spec.get("say", ""))
        top = self.heading(s, spec["title"], spec.get("chip"))
        bottom = BOTTOM - self.callout_height(spec.get("callout"), X1 - X0) if spec.get("callout") else BOTTOM
        vis = self.visual(spec, where)
        size = self.sz["body"]
        if vis and spec.get("points"):
            paras = self.bullets(spec["points"], size)
            iw, ih = vis[1]
            text_w = max(300.0, self.text_width(paras, size, 470.0))  # short points leave the picture more room
            side = min((X1 - X0 - text_w - 40) / iw, (bottom - top) / ih)
            stacked_h = self.m.height(paras, X1 - X0, size)
            below = min((X1 - X0) / iw, (bottom - top - stacked_h - GAP) / ih)
            if below > side * 1.15:  # a wide picture: the points above it, the picture across the slide
                t = self.text(s, X0, top, X1 - X0, stacked_h, paras, size, self.sz["floor"])
                y = top + t.h + GAP
                self.place(s, vis[0], vis[1], X0, y, X1 - X0, bottom - y, vis[2])
            else:
                self.text(s, X0, top, text_w, bottom - top, paras, size, self.sz["floor"])
                self.place(s, vis[0], vis[1], X0 + text_w + 40, top, X1 - X0 - text_w - 40, bottom - top, vis[2])
        elif vis:
            self.place(s, vis[0], vis[1], X0, top, X1 - X0, bottom - top, vis[2])
        else:
            self.text(s, X0, top, X1 - X0, bottom - top, self.bullets(spec.get("points", []), size), size,
                      self.sz["floor"])
        if spec.get("callout"):
            self.callout(s, spec["callout"], X0, bottom + GAP / 2, X1 - X0)
        self.finish(s)

    def callout_height(self, text: str, w: float) -> float:
        size = self.sz["body"]
        return self.m.height([Para(K.runs(text))], w - 2 * PAD, size) + 2 * PAD - 4 + GAP / 2

    def callout(self, s: Slide, text: str, x: float, y: float, w: float, size: float | None = None,
                fill: str | None = None) -> float:
        """A tinted card with a line or two in it. Returns its bottom."""
        size = size or self.sz["body"]
        h = self.m.height([Para(K.runs(text))], w - 2 * PAD, size) + 2 * PAD - 4
        self.card(s, x, y, w, h, fill or self.t.soft)
        self.text(s, x + PAD, y + PAD - 2, w - 2 * PAD, h - 2 * PAD + 4, [Para(K.runs(text))], size, size)
        return y + h

    def example(self, spec: dict, where: str) -> None:
        """A worked example: the problem in a card, then numbered steps, then the answer. With "reveal",
        one slide per step, laid out the same so nothing jumps."""
        steps = spec.get("steps", [])
        vis = self.visual(spec, where)
        sizes = range(int(self.sz["body"]), int(self.sz["dense"]) - 1, -1)
        for size in sizes:
            plan = self._example_plan(spec, steps, vis, size)
            if plan["bottom"] <= BOTTOM:
                break
        else:
            plan["overflow"] = True
        reveal = bool(spec.get("reveal")) and steps
        shown = range(0, len(steps) + 1) if reveal else [len(steps)]
        for count in shown:
            s = self.new(spec["title"], spec.get("say", ""))
            self.heading(s, spec["title"], spec.get("chip"))
            self._draw_example(s, spec, steps[:count], plan, vis, final=count == len(steps))
            if plan.get("overflow"):
                self.warn("the example doesn't fit; use fewer or shorter steps")
            self.finish(s)

    @staticmethod
    def _problem(spec: dict) -> list[Para]:
        """The example's problem: words, or with "code", lines of code kept as written."""
        if spec.get("code"):
            return [Para([Run(line.expandtabs(4) if line.strip() else "\u00a0")])
                    for line in spec.get("problem", "").split("\n")]
        return [Para(K.runs(spec.get("problem", "")))]

    def _example_plan(self, spec: dict, steps: list[str], vis, size: float) -> dict:
        """Where everything goes. A wide picture (a number line, a staff) goes across the slide under the
        problem; any other picture gets the right side, beside the problem and the steps."""
        top = TITLE_Y + self.sz["title"] * 1.15 + 24
        wide = bool(vis) and vis[1][0] / vis[1][1] > 2.2
        col_w = 540.0 if vis and not wide else X1 - X0
        problem = self._problem(spec)
        card_h = self.m.height(problem, col_w - 2 * PAD, size, mono=bool(spec.get("code"))) + 2 * PAD - 4
        vis_h = min(vis[1][1] * min((X1 - X0) / vis[1][0], 2.5), 100.0) if wide else 0.0
        d = size * 1.4
        text_w = col_w - d - 16
        y = top + card_h + GAP + 4 + (vis_h + GAP if wide else 0)
        rows = []
        for step in steps:
            h = max(d, self.m.height([Para(K.runs(step))], text_w, size))
            rows.append((y, h))
            y += h + size * 0.55
        answer_h = 0.0
        if spec.get("answer"):
            answer_h = self.m.height([Para(K.runs(f"**Answer:** {spec['answer']}"))], col_w - 2 * PAD, size) + 24
            y += 4
        return dict(size=size, top=top, col_w=col_w, card_h=card_h, d=d, text_w=text_w, rows=rows,
                    answer_y=y, bottom=y + answer_h, wide=wide, vis_h=vis_h)

    def _draw_example(self, s: Slide, spec: dict, steps: list[str], plan: dict, vis, final: bool) -> None:
        size, top, col_w = plan["size"], plan["top"], plan["col_w"]
        self.card(s, X0, top, col_w, plan["card_h"])
        self.text(s, X0 + PAD, top + PAD - 2, col_w - 2 * PAD, plan["card_h"] - 2 * PAD + 4,
                  self._problem(spec), size, self.sz["dense"], mono=bool(spec.get("code")))
        if vis and plan["wide"]:
            self.place(s, vis[0], vis[1], X0, top + plan["card_h"] + GAP, X1 - X0, plan["vis_h"], vis[2])
        elif vis:
            self.place(s, vis[0], vis[1], X0 + col_w + 28, top, X1 - X0 - col_w - 28, BOTTOM - top, vis[2])
        d = plan["d"]
        for k, (step, (y, h)) in enumerate(zip(steps, plan["rows"])):
            s.elements.append(Box(X0, y, d, d, self.t.accent, shape="oval"))
            s.elements.append(Text(X0, y, d, d, [Para([Run(str(k + 1), bold=True)])], size * 0.75, WHITE,
                                   align="center", valign="middle"))
            self.text(s, X0 + d + 16, y + (d - size * 1.2) / 2 if h <= d else y, plan["text_w"], h + 2,
                      [Para(K.runs(step))], size, self.sz["dense"])
        if final and spec.get("answer"):
            y = plan["answer_y"]
            text = [Para(K.runs(f"**Answer:** {spec['answer']}", ))]
            h = plan["bottom"] - y
            self.card(s, X0, y, col_w, h, self.t.soft)
            self.text(s, X0 + PAD, y + 12, col_w - 2 * PAD, h - 20, text, size, self.sz["dense"])

    def vocab(self, spec: dict, where: str) -> None:
        words = spec.get("words", [])
        if not words or not all(isinstance(w, dict) and w.get("term") and w.get("meaning") for w in words):
            raise LessonError(f"{where}: a vocab slide needs \"words\": [{{\"term\": ..., \"meaning\": ...}}]")
        if len(words) > 6:
            raise LessonError(f"{where}: at most 6 words on a vocab slide; use two slides")
        title = spec.get("title") or "Vocabulary"
        s = self.new(title, spec.get("say", ""))
        top = self.heading(s, title, spec.get("chip"))
        n = len(words)
        cols = n if n <= 3 else 2 if n == 4 else 3
        rows = -(-n // cols)
        gap = 20.0
        cw = (X1 - X0 - gap * (cols - 1)) / cols
        ch = (BOTTOM - top - gap * (rows - 1)) / rows
        for size in range(int(self.sz["body"]), int(self.sz["dense"]) - 1, -1):
            if all(self._vocab_h(w, cw - 2 * PAD, size) <= ch - 2 * PAD for w in words):
                break
        else:
            self.warn("the definitions don't fit; shorten them or use two slides")
        for k, w in enumerate(words):
            r, c = divmod(k, cols)
            x, y = X0 + c * (cw + gap), top + r * (ch + gap)
            self.card(s, x, y, cw, ch)
            self.text(s, x + PAD, y + PAD, cw - 2 * PAD, ch - 2 * PAD, self._vocab_paras(w, size), size, size)
        self.finish(s)

    def _vocab_paras(self, w: dict, size: float) -> list[Para]:
        paras = [Para(K.runs(w.get("term", ""), self.t.accent, bold=True), space_after=size * 0.35),
                 Para(K.runs(w.get("meaning", "")), space_after=size * 0.35)]
        if w.get("example"):
            paras.append(Para(K.runs(w["example"], MUTED, italic=True)))
        return paras

    def _vocab_h(self, w: dict, width: float, size: float) -> float:
        return self.m.height(self._vocab_paras(w, size), width, size)

    def question(self, spec: dict, where: str) -> None:
        """A question for the whole class, then (with "answer") the same slide with the answer shown."""
        self._question(spec, where, reveal=False)
        if spec.get("answer"):
            self._question(spec, where, reveal=True)

    def _question(self, spec: dict, where: str, reveal: bool) -> None:
        title = spec.get("title") or "Quick check"
        if reveal:
            notes = spec.get("answer_say") or K.plain(f"Answer: {spec.get('answer', '')}. {spec.get('why', '')}")
        else:
            notes = spec.get("say", "")
        s = self.new(title, notes)
        tag = " · ".join(x for x in (spec.get("mode", ""), f"{spec['minutes']} min" if spec.get("minutes") else "") if x)
        top = self.heading(s, title, "Answer" if reveal else (spec.get("chip") or tag or None),
                           chip_fill=self.t.accent if reveal else self.t.dark)
        choices = spec.get("choices", [])
        letters = "12345678" if spec.get("choice_labels") == "numbers" else "ABCDEFGH"  # music: A-G are notes
        answer = str(spec.get("answer", "")).strip()
        vis = self.visual(spec, where)
        width = 500.0 if vis else X1 - X0
        why = spec.get("why", "") if reveal else ""
        room_why = self.callout_height(spec["why"], width) if spec.get("why") and spec.get("answer") else 0.0
        below = 0.0  # what has to fit under the prompt
        if choices:
            below += min(len(choices), 4) * self.sz["body"] * 1.9
        if answer and not choices:  # reserved on the question slide too, so the prompt doesn't change size
            below += self.callout_height(f"**Answer:** {answer}", width)
        below += room_why
        size = self.sz["body"] + (2 if choices else 6)  # a question on its own is big
        prompt = [Para(K.runs(spec.get("prompt", "")))]
        t = self.text(s, X0, top, width, max(BOTTOM - top - below - GAP, size * 1.2), prompt, size, self.sz["floor"])
        y = top + t.h + GAP
        if vis:
            self.place(s, vis[0], vis[1], X0 + width + 30, top, X1 - X0 - width - 30, BOTTOM - top, vis[2])
        if choices:
            grid = len(choices) <= 4 and all(len(c) <= (14 if vis else 30) for c in choices)
            cols = 2 if grid else 1
            rows = -(-len(choices) // cols)
            gap = 16.0
            cw = (width - gap * (cols - 1)) / cols
            room = BOTTOM - y - room_why  # the same on the question and the answer, so nothing moves
            ch = min((room - gap * (rows - 1)) / rows, self.sz["body"] * 2.6)
            size = self.sz["body"]
            if ch < size * 1.6:
                ch = size * 1.6
                self.warn("the prompt, choices, and why don't all fit: shorten the prompt, the choices, or the why")
            for k, choice in enumerate(choices):
                r, c = divmod(k, cols)
                x, cy = X0 + c * (cw + gap), y + r * (ch + gap)
                right = reveal and letters[k] == answer.upper()[:1]
                self.card(s, x, cy, cw, ch, self.t.accent if right else self.t.tint)
                d = min(ch - 16, size * 1.5)
                s.elements.append(Box(x + 14, cy + (ch - d) / 2, d, d, WHITE if right else self.t.accent, shape="oval"))
                s.elements.append(Text(x + 14, cy + (ch - d) / 2, d, d, [Para([Run(letters[k], bold=True)])],
                                       size * 0.75, self.t.accent if right else WHITE, align="center",
                                       valign="middle"))
                self.text(s, x + 14 + d + 14, cy, cw - d - 42, ch, [Para(K.runs(choice))], size, self.sz["dense"],
                          color=WHITE if right else (MUTED if reveal else K.INK), valign="middle")
            y += rows * ch + (rows - 1) * gap + GAP
        elif reveal and answer:
            y = self.callout(s, f"**Answer:** {answer}", X0, y, width, self.sz["body"], self.t.soft) + 14
        if why:
            self.callout(s, why, X0, y, width, fill=self.t.tint)
        self.finish(s)

    def compare(self, spec: dict, where: str) -> None:
        for side in ("left", "right"):
            if isinstance((spec.get(side) or {}).get("points"), str):
                raise LessonError(f"{where}: \"{side}\" \"points\" is a list of short lines, not one string")
        s = self.new(spec["title"], spec.get("say", ""))
        top = self.heading(s, spec["title"], spec.get("chip"))
        sides = [spec.get("left") or {}, spec.get("right") or {}]
        if not all(side.get("heading") for side in sides):
            raise LessonError(f"{where}: a compare slide needs \"left\" and \"right\", each with \"heading\" and "
                              "\"points\"")
        bottom = BOTTOM - (self.callout_height(spec["callout"], X1 - X0) if spec.get("callout") else 0)
        gap = 24.0
        cw = (X1 - X0 - gap) / 2
        size = self.sz["body"]
        for size in range(int(self.sz["body"]), int(self.sz["dense"]) - 1, -1):
            if all(self.m.height(self._side(side, size), cw - 2 * PAD, size) <= bottom - top - 2 * PAD for side in sides):
                break
        tallest = max(self.m.height(self._side(side, size), cw - 2 * PAD, size) for side in sides)
        card_h = min(max(tallest + 2 * PAD, (bottom - top) * 0.45), bottom - top)  # as tall as the longer side
        for k, side in enumerate(sides):
            x = X0 + k * (cw + gap)
            self.card(s, x, top, cw, card_h)
            self.text(s, x + PAD, top + PAD, cw - 2 * PAD, card_h - 2 * PAD, self._side(side, size), size,
                      self.sz["dense"])
        if spec.get("callout"):
            self.callout(s, spec["callout"], X0, top + card_h + GAP / 2, X1 - X0)
        self.finish(s)

    def _side(self, side: dict, size: float) -> list[Para]:
        return [Para(K.runs(side["heading"], self.t.accent, bold=True), space_after=size * 0.5),
                *self.bullets(side.get("points", []), size)]

    def passage(self, spec: dict, where: str, mono: bool = False) -> None:
        """A text to read together, or code: in a card, with line numbers if asked."""
        text = spec.get("text", "")
        if not text.strip():
            raise LessonError(f"{where}: needs \"text\"")
        s = self.new(spec["title"], spec.get("say", ""))
        top = self.heading(s, spec["title"], spec.get("chip"), chip_fill=self.t.dark)
        focus = spec.get("focus", "")
        source = [Para([Run(spec["source"], italic=True)])] if spec.get("source") else []
        source_h = self.m.height(source, X1 - X0, 14) + 8 if source else 0.0
        bottom = BOTTOM - (self.callout_height(f"**{spec.get('focus_label', 'Focus')}:** {focus}", X1 - X0)
                           if focus else 0) - source_h
        numbers = spec.get("line_numbers", mono)
        num_w = 44.0 if numbers else 0.0
        given = spec.get("numbers")  # the worksheet's own numbering: None on a wrapped line
        raw = text.expandtabs(4).split("\n") if mono else [p for p in text.split("\n")]
        paras = [Para([Run(line if line.strip() else "\u00a0")]) for line in raw]
        width = X1 - X0 - 2 * PAD - num_w
        size, ok = self.m.fit(paras, width, bottom - top - 2 * PAD, self.sz["body"] + 2, self.sz["dense"], 1.25,
                              mono)
        if not ok:
            self.warn("the passage doesn't fit; show fewer lines (quote the part you'll discuss)")
        h = min(self.m.height(paras, width, size, 1.25, mono), bottom - top - 2 * PAD)
        self.card(s, X0, top, X1 - X0, h + 2 * PAD, "F4F5F7" if mono else self.t.tint)
        s.elements.append(Text(X0 + PAD + num_w, top + PAD, width, h + 2, paras, size, K.INK, mono=mono,
                               leading=1.25))
        if numbers:
            nums = []
            start = int(spec.get("first_line", 1))
            for k, p in enumerate(paras):
                wrapped = len(self.m.wrap(p, width, size, mono))
                label = (str(given[k]) if given[k] else "\u00a0") if given else str(start + k)
                nums.append(Para([Run(label)]))
                nums += [Para([Run("\u00a0")]) for _ in range(wrapped - 1)]
            s.elements.append(Text(X0 + PAD - 6, top + PAD, num_w - 10, h + 2, nums, size, MUTED, align="right",
                                   mono=mono, leading=1.25))
        y = top + h + 2 * PAD
        if source:
            s.elements.append(Text(X0, y + 6, X1 - X0, source_h - 8, source, 14, MUTED))
            y += source_h
        if focus:
            self.callout(s, f"**{spec.get('focus_label', 'Focus')}:** {focus}", X0, y + GAP / 2, X1 - X0)
        self.finish(s)

    # --- The worksheet ---------------------------------------------------------------------

    def worksheet_time(self, ws: WK.Worksheet, minutes: int, then: str = "", notes: str = "") -> None:
        s = self.new("Worksheet time", notes)
        top = self.heading(s, "Worksheet time", f"{minutes} min" if minutes else None, chip_fill=self.t.dark)
        thumb = self.image_file("worksheet")
        size_px = ws.thumbnail(1, thumb)
        placed = self.place(s, thumb, size_px, X0, top, 330, BOTTOM - top, f"Page 1 of {ws.title}",
                            border="9AA0A6", align="left")
        x = placed[0] + placed[2] + 44
        n = len(ws.questions)
        pages = len(S.form_pages(ws.layout))
        points = ["Write your **class ID number** in the boxes at the top, not your name.",
                  f"{n} question{'s' if n != 1 else ''}" + (f" on {pages} pages" if pages > 1 else "")
                  + ". Answer each one in its box."]
        if then:
            points.append(then)
        size = self.sz["body"]
        self.text(s, x, top + 10, X1 - x, BOTTOM - top - 10, self.bullets(points, size), size, self.sz["floor"])
        self.finish(s)

    def walk_passage(self, ws: WK.Worksheet, pid: str, questions: list[int]) -> None:
        """A reading or a program the next questions are about: as text when its printed lines are short
        enough to show big (code, a poem), else as printed."""
        title = ws.passage_title(pid) or "The reading"
        qs = ", ".join(map(str, questions))
        notes = (f"Question{'s' if len(questions) > 1 else ''} {qs} {'are' if len(questions) > 1 else 'is'} about "
                 "this. Have students find it on their sheet.")
        p = ws.passage(pid)
        if p and p.get("lines"):
            lines = [t for _, t in p["lines"]]
            numbered = p.get("line_numbers")
            width = (X1 - X0 - 2 * PAD - (44 if numbered else 0)) * K.SLACK
            longest = max(self.m.width(t or " ", Run(t or " "), 1, p["mono"]) for t in lines)
            top = TITLE_Y + self.sz["title"] * 1.15 + 24
            room = BOTTOM - top - 2 * PAD - (26 if p.get("source") else 0)
            size = min(self.sz["body"] + 2, width / longest, room / (len(lines) * 1.25))
            if size >= self.sz["dense"]:
                self.passage({"title": title, "text": "\n".join(lines), "line_numbers": numbered,
                              "numbers": [n for n, _ in p["lines"]], "source": p.get("source", ""),
                              "chip": "On your sheet", "say": notes, "keep_lines": True}, "walkthrough", mono=p["mono"])
                return
            if not numbered and not p["mono"] and p.get("text"):  # prose: as paragraphs, as big as it fits
                paras = [Para([Run(t)], space_after=8) for t in p["text"].split("\n") if t.strip()]
                if self.m.fit(paras, X1 - X0 - 2 * PAD, room, self.sz["body"], self.sz["dense"], 1.25)[1]:
                    self.passage({"title": title, "text": "\n".join(t for t in p["text"].split("\n") if t.strip()),
                                  "line_numbers": False, "source": p.get("source", ""), "chip": "On your sheet",
                                  "say": notes}, "walkthrough")
                    return
        pieces = ws.passages.get(pid, [])
        if not pieces and p and p.get("lines"):  # a worksheet made before passages were placed: as text, smaller
            self.passage({"title": title, "text": "\n".join(t for _, t in p["lines"]), "line_numbers": p.get("line_numbers"),
                          "numbers": [n for n, _ in p["lines"]], "source": p.get("source", ""), "chip": "On your sheet",
                          "say": notes}, "walkthrough", mono=p["mono"])
            return
        for n, (page, rect) in enumerate(pieces, start=1):
            s = self.new(title, notes)
            top = self.heading(s, title, f"{n} of {len(pieces)}" if len(pieces) > 1 else "On your sheet",
                               chip_fill=self.t.dark)
            path = self.image_file(f"{pid}-{n}")
            size = ws.crop_rect(page, rect, path)
            text = " ".join((p.get("text") or "").split()) if p else ""
            self.place(s, path, size, X0, top, X1 - X0, BOTTOM - top, f"{title}: {text}"[:1500] if text else title,
                       2.4)
            self.finish(s)

    def walk_question(self, ws: WK.Worksheet, q: int, spec: dict, chip: str | None = None,
                      chip_fill: str | None = None, notes: str = "", side: list[Para] | None = None,
                      side_extra=None, words: int | None = None) -> None:
        """A worksheet question as printed, with something to think about before the answer."""
        s = self.new(f"Question {q}", notes)
        top = self.heading(s, f"Question {q}", chip, chip_fill=chip_fill or self.t.dark)
        think = spec.get("think", "")
        bottom = BOTTOM - (self.callout_height(f"**Think:** {think}", X1 - X0) if think else 0)
        path = self.image_file(f"q{q}")
        size = ws.crop(q, path)
        alt = f"Question {q} as printed: {' '.join(ws.items[q]['prompt'].split())}"
        if (side or side_extra) and size[0] / size[1] >= 3:  # a strip (a prompt alone): across the top
            k = min((X1 - X0) / size[0], 2.4)
            placed = self.place(s, path, size, X0, top, X1 - X0, size[1] * k, alt, k)
            x, y0, w = X0, placed[1] + placed[3] + GAP, X1 - X0
        elif side or side_extra:
            k = min(500 / size[0], (bottom - top) / size[1], 2.2)
            placed = self.place(s, path, size, X0, top, 500, size[1] * k, alt, 2.2,
                                align="left")
            x, y0 = placed[0] + placed[2] + 32, top
            w = X1 - x
        if side or side_extra:
            y = side_extra(s, x, y0, w, bottom - y0) if side_extra else y0
            if side:
                self.text(s, x, y, w, bottom - y, side, self.sz["small"], self.sz["dense"])
        else:
            k = min((X1 - X0) / size[0], (bottom - top) / size[1], 2.6)
            placed = self.place(s, path, size, X0, top, X1 - X0, size[1] * k, alt, 2.6)
            if think and size[0] / size[1] >= 3:  # a prompt alone: the question to think about right under it
                self.callout(s, f"**Think:** {think}", X0, placed[1] + placed[3] + GAP, X1 - X0)
                think = ""
        if think:
            self.callout(s, f"**Think:** {think}", X0, bottom + GAP / 2, X1 - X0)
        self.finish(s, words=words)

    def walk_answer(self, ws: WK.Worksheet, q: int, spec: dict, notes: str = "", extra: str = "") -> None:
        """The question with the key's answers written in, and how to get there."""
        s = self.new(f"Question {q}", notes)
        top = self.heading(s, f"Question {q}", "Answer")
        path = self.image_file(f"q{q}-answer")
        cw, ch = ws.crop(q, path, spec.get("drawing"), self.t.accent)
        versions = [self.answer_paras(ws, q, spec, extra), self.answer_paras(ws, q, spec, extra, mistakes=False)]
        mode, k, panel, size, paras = self.answer_layout(cw, ch, top, versions, ws.style["prompt_size"])
        paras = [Para(p.runs, p.bullet, p.bullet_color, p.space_after * size / self.sz["body"]) for p in paras]
        if mode == "side":
            placed = self.place(s, path, (cw, ch), X0, top, cw * k, ch * k, f"Question {q} with the answer: {ws.answer_text(q)}", k,
                                align="left")
        else:
            placed = self.place(s, path, (cw, ch), X0, top, X1 - X0, ch * k, f"Question {q} with the answer: {ws.answer_text(q)}", k)
        self.overlay(s, ws, q, ws.region(q), placed)
        if paras:
            self.text(s, *panel, paras, size, self.sz["dense"])
        self.finish(s, words=int(self.sz["words"] * 1.3))  # a model answer is read, not glanced at

    def answer_layout(self, cw: float, ch: float, top: float, paras: list[Para], printed: float) -> tuple:
        """Where the question's picture and the explanation go: side by side, or the picture above. Picks
        the arrangement whose smaller text, the picture's printed words or the explanation, is biggest."""
        room = BOTTOM - top
        candidates = []
        for w in (640, 600, 560, 520, 480, 440, 400, 360):
            k = min(w / cw, room / ch, 2.4)
            candidates.append(("side", k, (X0 + cw * k + 32, top, X1 - X0 - cw * k - 32, room)))
        for share in (0.7, 0.62, 0.55, 0.48, 0.4, 0.33):
            k = min((X1 - X0) / cw, room * share / ch, 2.4)
            candidates.append(("top", k, (X0, top + ch * k + GAP, X1 - X0, room - ch * k - GAP)))
        if not paras or not paras[0]:
            k = min((X1 - X0) / cw, room / ch, 2.6)
            return "top", k, (X0, top, X1 - X0, room), self.sz["small"], []
        # Readable first: at the grade's floor, with the mistakes if they fit, else without them (they're in the
        # notes); only then smaller.
        for floor in (self.sz["floor"], self.sz["dense"]):
            for version in paras:
                best = None
                for mode, k, panel in candidates:
                    if panel[2] < 250 or panel[3] < 60:
                        continue
                    size, ok = self.m.fit(version, panel[2], panel[3], self.sz["body"], floor)
                    if not ok:
                        continue
                    score = (min(printed * k, size), k)
                    if best is None or score > best[0]:
                        best = (score, mode, k, panel, size)
                if best:
                    return (*best[1:], version)
        self.warn("the explanation doesn't fit beside the question; use fewer or shorter steps")
        mode, k, panel = candidates[len(candidates) // 2 - 1]
        return mode, k, panel, self.sz["dense"], paras[-1]

    def answer_paras(self, ws: WK.Worksheet, q: int, spec: dict, extra: str = "", mistakes: bool = True) -> list[Para]:
        item = ws.items[q]
        size = self.sz["body"]  # spacing for the largest size the panel tries; answer_layout scales it
        out = []
        if spec.get("idea"):
            out.append(Para(K.runs(spec["idea"], self.t.accent, bold=True), space_after=size * 0.6))
        kind = item["type"]

        def labeled(label: str, text: str, markup: bool = False) -> Para:  # worksheet text: ** is Python, not bold
            return Para([Run(f"{label}: ", bold=True), *K.runs(text, markup=markup)], space_after=size * 0.5)

        if kind == "math" or (kind == "draw" and item.get("answer")):
            out.append(labeled("Answer", ws.answer_text(q) if kind == "math" else item["answer"]))
        if kind == "short":
            if spec.get("model"):
                out.append(labeled("A strong answer", spec["model"], markup=True))
            elif item.get("rubric") and item["key"] == "Scored on the rubric.":
                out.append(labeled("Scored on", "; ".join(f"{c.get('short') or c['criterion']} (0-{c['max']})"
                                                         for c in item["rubric"])))
            else:
                out.append(labeled("Full credit", item["key"]))
        out += self.bullets(spec.get("steps", []), size)  # bullets: numbers would read as the sheet's box numbers
        if kind == "draw" and not spec.get("drawing"):  # no drawn answer to look at: say what one shows
            out.append(Para([Run("A complete drawing shows:", bold=True)], space_after=size * 0.3))
            out += [Para(K.runs(c.get("short") or c["item"], markup=False), bullet="•", bullet_color=self.t.accent,
                         space_after=size * 0.45) for c in item["checklist"]]
        if spec.get("mistakes") and mistakes:
            if out:
                out[-1].space_after = size * 0.7
            label = Run("Watch out: ", bold=True, color=self.t.accent)
            if len(spec["mistakes"]) == 1:
                out.append(Para([label, *K.runs(spec["mistakes"][0])]))
            else:
                out.append(Para([label], space_after=size * 0.2))
                out += self.bullets(spec["mistakes"], size)
        if extra:
            out.append(Para(K.runs(extra, MUTED)))
        return out

    def overlay(self, s: Slide, ws: WK.Worksheet, q: int, region: tuple, placed: tuple) -> None:
        """The key's answers on the question's picture."""
        cx0, cy0, cx1, cy1 = region
        px, py, pw, ph = placed
        k = pw / (cx1 - cx0)
        for mark in ws.marks(q):
            x0, y0, x1, y1 = mark.rect
            if x0 < cx0 - 1 or x1 > cx1 + 1 or y0 < cy0 - 1 or y1 > cy1 + 1:
                continue  # outside the picture: a math answer box below the prompt
            rx, ry, rw, rh = px + (x0 - cx0) * k, py + (cy1 - y1) * k, (x1 - x0) * k, (y1 - y0) * k
            if mark.kind == "circle":
                s.elements.append(Box(rx, ry, rw, rh, None, line=self.t.accent, line_w=1.6 * k, shape="oval"))
                continue
            size = WK.mark_size(mark, lambda t, sz: self.m.width(t, Run(t, bold=True), sz), 13, K.SLACK) * k
            s.elements.append(Text(rx, ry, rw, rh, [Para([Run(mark.text, bold=True)])], size, self.t.accent,
                                   align="center", valign="middle", leading=1.0, role="answer"))


_HELPER_TEXT = {"clock": 8.0}  # labels with a fixed size; the other helpers take "size"


def _smallest_text(d: dict) -> float | None:
    sizes = []
    for s in d["shapes"]:
        if s["shape"] == "text" and s.get("text"):
            sizes.append(float(s["size"]))
        elif s["shape"] in ("timeline", "axes", "number_line"):
            sizes.append(float(s["size"]))
        elif s["shape"] == "bar_chart":
            sizes.append(float(s["size"]) - 1)
        elif s["shape"] in _HELPER_TEXT:
            sizes.append(_HELPER_TEXT[s["shape"]])
    return min(sizes) if sizes else None


def _diagram_png(d: dict, path: Path, base: Path) -> None:
    import pypdfium2 as pdfium
    fonts, _ = F.choose(_strings(d["shapes"]))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(d["width"] + 12, d["height"] + 12))
    D.draw_diagram(c, d, 6, 6, fonts, base)
    c.save()
    pdf = pdfium.PdfDocument(buf.getvalue())
    pdf[0].render(scale=4).to_pil().convert("RGB").save(path)
