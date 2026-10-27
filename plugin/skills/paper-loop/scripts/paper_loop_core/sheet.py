"""The printed page: fixed geometry, the page code, and laying out a worksheet.

Everything is in PDF points (1/72 inch) with the origin at the bottom-left, as in reportlab.
Rects are [x0, y0, x1, y1]. The geometry matches the Paper Loop CLI exactly, so sheets printed
from either one can be read by either one.
"""

from __future__ import annotations

import json
import math
import zlib
from pathlib import Path

from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter
DPI = 200  # canonical raster for deskewed pages, crops, and rendering

# Corner markers: ArUco DICT_4X4_50 ids 0-3, drawn and read here without OpenCV. Inner 4x4 bits,
# row by row from the marker's own top-left, 1 = white. The 1-cell border around them is black.
MARKER_SIZE, MARKER_INSET = 32.0, 22.0
_lo, _hi_x, _hi_y = MARKER_INSET, PAGE_W - MARKER_INSET - MARKER_SIZE, PAGE_H - MARKER_INSET - MARKER_SIZE
MARKER_RECTS = {
    0: (_lo, _hi_y, _lo + MARKER_SIZE, _hi_y + MARKER_SIZE),  # top-left
    1: (_hi_x, _hi_y, _hi_x + MARKER_SIZE, _hi_y + MARKER_SIZE),  # top-right
    2: (_hi_x, _lo, _hi_x + MARKER_SIZE, _lo + MARKER_SIZE),  # bottom-right
    3: (_lo, _lo, _lo + MARKER_SIZE, _lo + MARKER_SIZE),  # bottom-left
}
MARKER_BITS = {
    0: ("1011", "0101", "0011", "0010"),
    1: ("0000", "1111", "1001", "1010"),
    2: ("0011", "0011", "0010", "1101"),
    3: ("1001", "1001", "0100", "0110"),
}

# Page code: 32 squares in the top-left corner (where older sheets have a QR code) that say which
# assignment and page this is. 18 bits of assignment hash, 6 bits of page number, 8 bits of CRC.
CODE_RECT = (66.0, 722.0, 126.0, 752.0)
CODE_ROWS, CODE_COLS = 4, 8
CODE_AREA = (66.0, 698.0, 128.0, 760.0)  # the code's spot, or an older sheet's QR code

ID_DIGITS = 4
ID_WRITE_X, ID_WRITE_Y, ID_WRITE_W, ID_WRITE_H = 446.0, 722.0, 26.0, 30.0
CONTENT_TOP = 680.0
LEFT, BOX_RIGHT, GUTTER_LEFT, GUTTER_RIGHT = 48.0, 392.0, 404.0, 572.0
SUMMARY_RECT = (48.0, 64.0, 572.0, 136.0)
SUMMARY_RECT_COMPACT = (48.0, 56.0, 572.0, 106.0)

PROMPT_FONT = "Helvetica"
OPTION_REACH = 16.0  # a circle drawn around a letter pokes left of its text; count that ink too
INK, OUTLINE, FAINT = 0.0, 0.35, 0.8  # FAINT is light enough that the ink threshold ignores it


def scale(dpi: int = DPI) -> float:
    return dpi / 72.0


def pt_to_px(x: float, y: float, dpi: int = DPI) -> tuple[float, float]:
    """PDF point (origin bottom-left) to pixel (origin top-left)."""
    s = scale(dpi)
    return x * s, (PAGE_H - y) * s


def rect_to_px(rect, dpi: int = DPI, inset_pt: float = 0.0) -> tuple[int, int, int, int]:
    """PDF rect to integer pixel box (left, top, right, bottom), optionally shrunk on every side."""
    x0, y0, x1, y1 = rect
    s = scale(dpi)
    return (round((x0 + inset_pt) * s), round((PAGE_H - y1 + inset_pt) * s),
            round((x1 - inset_pt) * s), round((PAGE_H - y0 - inset_pt) * s))


def canonical_size(dpi: int = DPI) -> tuple[int, int]:
    return round(PAGE_W * scale(dpi)), round(PAGE_H * scale(dpi))


# --- Page code ------------------------------------------------------------------

def assignment_hash(assignment_id: str) -> int:
    return zlib.crc32(assignment_id.encode()) & 0x3FFFF


def _crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def page_code(assignment_id: str, page: int) -> int:
    if not 1 <= page <= 63:
        raise ValueError("a worksheet can have at most 63 pages")
    body = (assignment_hash(assignment_id) << 6) | page
    return (body << 8) | _crc8(body.to_bytes(3, "big"))


def code_bits(code: int) -> list[int]:
    return [(code >> (31 - i)) & 1 for i in range(CODE_ROWS * CODE_COLS)]


def parse_code(bits: list[int]) -> tuple[int, int] | None:
    """(assignment hash, page), or None if the squares don't add up to a valid code."""
    code = 0
    for b in bits:
        code = (code << 1) | b
    body, crc = code >> 8, code & 0xFF
    if _crc8(body.to_bytes(3, "big")) != crc or not body & 0x3F:
        return None
    return body >> 6, body & 0x3F


def code_cells() -> list[tuple[float, float, float, float]]:
    """Each square's rect, in bit order: rows top to bottom, columns left to right."""
    x0, y0, x1, y1 = CODE_RECT
    w, h = (x1 - x0) / CODE_COLS, (y1 - y0) / CODE_ROWS
    return [(x0 + c * w, y1 - (r + 1) * h, x0 + (c + 1) * w, y1 - r * h)
            for r in range(CODE_ROWS) for c in range(CODE_COLS)]


# --- Worksheet definition ---------------------------------------------------------

class WorksheetError(ValueError):
    pass


SHAPE_DEFAULTS = dict(id=None, x=0.0, y=0.0, w=0.0, h=0.0, r=0.0, points=[], text="", size=9.0, bold=False,
                      align="left", fill=None, stroke=0.0, width=1.0)
SHAPES = {"rect", "circle", "line", "arrow", "polyline", "polygon", "text"}


def _need(obj: dict, field: str, where: str):
    if field not in obj:
        raise WorksheetError(f"{where}: missing \"{field}\"")
    return obj[field]


def _diagram(d: dict, where: str) -> dict:
    d = {"shapes": [], "description": "", **d}
    _need(d, "width", where), _need(d, "height", where)
    shapes = []
    for n, s in enumerate(d["shapes"], start=1):
        s = {**SHAPE_DEFAULTS, **s}
        if s.get("shape") not in SHAPES:
            raise WorksheetError(f"{where}, shape {n}: \"shape\" must be one of {', '.join(sorted(SHAPES))}")
        shapes.append(s)
    d["shapes"] = shapes
    return d


def normalize(defn: dict) -> dict:
    """Fill in defaults and check the worksheet, with errors that say exactly what to fix."""
    defn = {"subject": "science", "grade_band": "middle school",
            "instructions": "Answer each question in its box. Write your ID number, not your name.",
            "compact": False, **defn}
    for field in ("assignment_id", "title", "questions"):
        _need(defn, field, "worksheet")
    defn["id_style"] = "write"  # handwritten ID boxes: Claude reads them, so no bubble grid
    questions = []
    for raw in defn["questions"]:
        q = {"type": "short", **raw}
        where = f"question {q.get('q', '?')}"
        _need(q, "q", where), _need(q, "prompt", where)
        kind = q["type"]
        if kind == "short":
            q = {"points": 2, "lines": 4, **q}
            _need(q, "key", where)
        elif kind == "choice":
            q = {"points": 1, "columns": 1, **q}
            options = [{"why": "", **o} for o in _need(q, "options", where)]
            q["options"] = options
            if _need(q, "answer", where) not in {o["letter"] for o in options}:
                raise WorksheetError(f"{where}: answer {q['answer']!r} isn't one of the option letters")
        elif kind == "label":
            q = {"word_bank": [], **q}
            q["diagram"] = _diagram(_need(q, "diagram", where), where)
            q["labels"] = [{"points_to": None, "accept": [], "points": 1, **s} for s in _need(q, "labels", where)]
            q["points"] = sum(s["points"] for s in q["labels"])
        elif kind == "draw":
            q["diagram"] = _diagram(_need(q, "diagram", where), where)
            q["checklist"] = [{"short": "", "points": 1, **c} for c in _need(q, "checklist", where)]
            q["points"] = sum(c["points"] for c in q["checklist"])
        else:
            raise WorksheetError(f"{where}: \"type\" must be short, choice, label, or draw")
        if kind in ("label", "draw") and q["diagram"]["width"] > BOX_RIGHT - LEFT:
            raise WorksheetError(f"{where}: diagram is wider than {BOX_RIGHT - LEFT:g}pt")
        questions.append(q)
    defn["questions"] = questions
    return defn


# --- Layout -------------------------------------------------------------------------

STYLES = {
    False: dict(prompt_size=11.0, prompt_leading=14.0, prompt_gap=6.0, line_spacing=22.0, block_gap=18.0,
                option_size=10.5, option_leading=13.0, option_gap=9.0, word_bank_h=20.0),
    True: dict(prompt_size=10.5, prompt_leading=12.5, prompt_gap=4.0, line_spacing=21.0, block_gap=11.0,
               option_size=10.0, option_leading=12.0, option_gap=6.0, word_bank_h=17.0),
}


def id_boxes() -> list[tuple[float, float, float, float]]:
    return [(ID_WRITE_X + d * ID_WRITE_W, ID_WRITE_Y, ID_WRITE_X + (d + 1) * ID_WRITE_W, ID_WRITE_Y + ID_WRITE_H)
            for d in range(ID_DIGITS)]


def _prompt_lines(q: dict, st: dict) -> list[str]:
    return simpleSplit(f"{q['q']}. {q['prompt']}", PROMPT_FONT, st["prompt_size"], BOX_RIGHT - LEFT)


def _option_geometry(q: dict, st: dict):
    columns = max(1, q["columns"])
    col_w = (BOX_RIGHT - LEFT) / columns
    indent = 30.0 if columns == 1 else 20.0
    width = col_w - indent - (0 if columns == 1 else 4)
    lines = [simpleSplit(o["text"], "Helvetica", st["option_size"], width) for o in q["options"]]
    return columns, col_w, indent, lines


def _option_rows(q: dict, st: dict) -> list[float]:
    columns, _, _, lines = _option_geometry(q, st)
    rows = [lines[i:i + columns] for i in range(0, len(lines), columns)]
    return [max(len(l) for l in row) * st["option_leading"] for row in rows]


def _body_height(q: dict, st: dict) -> float:
    if q["type"] == "short":
        return q["lines"] * st["line_spacing"]
    if q["type"] == "choice":
        rows = _option_rows(q, st)
        return sum(rows) + st["option_gap"] * (len(rows) - 1)
    if q["type"] == "label":
        return q["diagram"]["height"] + (st["word_bank_h"] if q["word_bank"] else 0)
    return q["diagram"]["height"]


def block_height(q: dict, st: dict) -> float:
    return len(_prompt_lines(q, st)) * st["prompt_leading"] + st["prompt_gap"] + _body_height(q, st)


def paginate(defn: dict) -> list[list[int]]:
    """Question indexes on each page."""
    st = STYLES[defn["compact"]]
    bottom = (SUMMARY_RECT_COMPACT if defn["compact"] else SUMMARY_RECT)[3] + 12
    pages: list[list[int]] = [[]]
    y = CONTENT_TOP
    for i, q in enumerate(defn["questions"]):
        height = block_height(q, st)
        if y - height < bottom and pages[-1]:
            pages.append([])
            y = CONTENT_TOP
        pages[-1].append(i)
        y -= height + st["block_gap"]
    return pages


def space_left(defn: dict) -> float:
    """Points of free space at the bottom of the last page (negative means it doesn't fit)."""
    st = STYLES[defn["compact"]]
    bottom = (SUMMARY_RECT_COMPACT if defn["compact"] else SUMMARY_RECT)[3] + 12
    y = CONTENT_TOP
    for i in paginate(defn)[-1]:
        y -= block_height(defn["questions"][i], st) + st["block_gap"]
    return y + st["block_gap"] - bottom


# --- Drawing ------------------------------------------------------------------------

def _cells(c: canvas.Canvas, rect, rows: list[list[bool]]) -> None:
    """Fill the dark cells of a grid drawn into rect."""
    x0, _, x1, y1 = rect
    cell = (x1 - x0) / len(rows[0])
    c.setFillGray(INK)
    for r, row in enumerate(rows):
        for col, dark in enumerate(row):
            if dark:  # a hair of overlap so adjacent cells don't render with seams
                c.rect(x0 + col * cell, y1 - (r + 1) * cell, cell + 0.05, cell + 0.05, stroke=0, fill=1)


def _draw_marker(c: canvas.Canvas, marker_id: int) -> None:
    inner = MARKER_BITS[marker_id]
    rows = [[True] * 6] + [[True, *(b == "0" for b in row), True] for row in inner] + [[True] * 6]
    _cells(c, MARKER_RECTS[marker_id], rows)


def _draw_code(c: canvas.Canvas, code: int) -> None:
    c.setFillGray(INK)
    for (x0, y0, x1, y1), bit in zip(code_cells(), code_bits(code)):
        if bit:
            c.rect(x0, y0, x1 - x0 + 0.05, y1 - y0 + 0.05, stroke=0, fill=1)
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(0.6)
    x0, y0, x1, y1 = CODE_RECT
    c.rect(x0 - 2, y0 - 2, x1 - x0 + 4, y1 - y0 + 4, stroke=1, fill=0)


def _draw_header(c: canvas.Canvas, defn: dict, page_no: int, n_pages: int) -> None:
    c.setFillGray(INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(138, 744, defn["title"])
    c.setFont("Helvetica", 9)
    c.drawString(138, 730, f"Page {page_no} of {n_pages}")
    c.setFont("Helvetica", 8.5)
    y = 716.0
    for line in simpleSplit(defn["instructions"], "Helvetica", 8.5, 290):
        c.drawString(138, y, line)
        y -= 10.5
    boxes = id_boxes()
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(boxes[0][0] - 6, boxes[0][1] + 11, "ID #")
    c.setFont("Helvetica", 6.5)
    c.setFillGray(0.45)
    c.drawString(boxes[0][0], boxes[0][1] - 9, "one digit per box, not your name")
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(0.8)
    for x0, y0, x1, y1 in boxes:
        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
    c.setFillGray(INK)
    c.line(LEFT, CONTENT_TOP + 8, GUTTER_RIGHT, CONTENT_TOP + 8)


def _draw_footer(c: canvas.Canvas, defn: dict, page_no: int, n_pages: int, summary) -> None:
    x0, y0, x1, y1 = summary
    c.setStrokeGray(FAINT)
    c.setLineWidth(0.8)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
    c.setFillGray(0.6)
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 5, y1 - 10, "Feedback summary (your teacher fills this in)")
    c.drawCentredString(PAGE_W / 2, 32, f"{defn['assignment_id']} | page {page_no} of {n_pages} | "
                                        "please don't write in the corner squares")


def _arrowhead(c: canvas.Canvas, x0: float, y0: float, x1: float, y1: float, size: float) -> None:
    angle = math.atan2(y1 - y0, x1 - x0)
    p = c.beginPath()
    p.moveTo(x1, y1)
    for side in (-1, 1):
        a = angle + math.pi - side * math.radians(25)
        p.lineTo(x1 + size * math.cos(a), y1 + size * math.sin(a))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def draw_diagram(c: canvas.Canvas, diagram: dict, x0: float, y0: float) -> None:
    for s in diagram["shapes"]:
        stroke, fill = s["stroke"] is not None, s["fill"] is not None
        c.setLineWidth(s["width"])
        c.setStrokeGray(s["stroke"] if stroke else 0)
        c.setFillGray(s["fill"] if fill else 0)
        if s["shape"] == "rect":
            c.rect(x0 + s["x"], y0 + s["y"], s["w"], s["h"], stroke=int(stroke), fill=int(fill))
        elif s["shape"] == "circle":
            c.circle(x0 + s["x"], y0 + s["y"], s["r"], stroke=int(stroke), fill=int(fill))
        elif s["shape"] in ("line", "arrow", "polyline", "polygon") and len(s["points"]) >= 2:
            p = c.beginPath()
            p.moveTo(x0 + s["points"][0][0], y0 + s["points"][0][1])
            for px, py in s["points"][1:]:
                p.lineTo(x0 + px, y0 + py)
            if s["shape"] == "polygon":
                p.close()
            c.drawPath(p, stroke=int(stroke), fill=int(fill and s["shape"] == "polygon"))
            if s["shape"] == "arrow":
                (ax, ay), (bx, by) = s["points"][-2], s["points"][-1]
                c.setFillGray(s["stroke"] if stroke else 0)
                _arrowhead(c, x0 + ax, y0 + ay, x0 + bx, y0 + by, 4 + 2 * s["width"])
        elif s["shape"] == "text":
            c.setFillGray(s["fill"] if fill else 0)
            c.setFont("Helvetica-Bold" if s["bold"] else "Helvetica", s["size"])
            draw = {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[s["align"]]
            draw(x0 + s["x"], y0 + s["y"], s["text"])


def _leader(c: canvas.Canvas, box, point) -> None:
    """A line from a label box to the spot it names, from the side facing the spot."""
    bx, by, bw, bh = box
    px, py = point
    if bx <= px <= bx + bw:
        start = (bx + bw / 2, by + bh if py > by + bh else by)
    else:
        start = (bx if px < bx else bx + bw, by + bh / 2)
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(0.8)
    c.line(*start, px, py)
    c.setFillGray(OUTLINE)
    c.circle(px, py, 1.6, stroke=0, fill=1)


def _draw_question(c: canvas.Canvas, q: dict, y: float, st: dict) -> dict:
    top = y
    lines = _prompt_lines(q, st)
    c.setFillGray(INK)
    c.setFont(PROMPT_FONT, st["prompt_size"])
    for n, line in enumerate(lines):
        c.drawString(LEFT, y - st["prompt_size"] - n * st["prompt_leading"], line)
    body_top = y - len(lines) * st["prompt_leading"] - st["prompt_gap"]
    bottom = y - block_height(q, st)
    box = {"q": q["q"], "type": q["type"], "rect": (LEFT, bottom, BOX_RIGHT, body_top),
           "feedback_rect": (GUTTER_LEFT, bottom, GUTTER_RIGHT, top), "prompt": q["prompt"],
           "points": q["points"], "lines": 0, "options": [], "labels": []}

    if q["type"] == "short":
        box["lines"] = q["lines"]
        c.setStrokeGray(FAINT)
        c.setLineWidth(0.6)
        for k in range(1, q["lines"]):
            ly = bottom + k * st["line_spacing"]
            c.line(LEFT + 6, ly, BOX_RIGHT - 6, ly)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(LEFT, bottom, BOX_RIGHT - LEFT, body_top - bottom, stroke=1, fill=0)

    elif q["type"] == "choice":
        columns, col_w, indent, option_lines = _option_geometry(q, st)
        row_heights = _option_rows(q, st)
        row_top = body_top
        for i, option in enumerate(q["options"]):
            row, col = divmod(i, columns)
            if col == 0 and row > 0:
                row_top -= row_heights[row - 1] + st["option_gap"]
            x = LEFT + col * col_w
            baseline = row_top - st["option_size"]
            c.setFillGray(INK)
            c.setFont("Helvetica-Bold", st["option_size"] + 0.5)
            c.drawString(x + 10, baseline, option["letter"])
            c.setFont("Helvetica", st["option_size"])
            for n, line in enumerate(option_lines[i]):
                c.drawString(x + indent, baseline - n * st["option_leading"], line)
            left = x - OPTION_REACH if col == 0 else x - 4
            right = x + col_w if columns == 1 else x + col_w - 4
            box["options"].append({
                "letter": option["letter"],
                "rect": (left, row_top - row_heights[row] - st["option_gap"] / 2, right,
                         row_top + st["option_gap"] / 2),
                "letter_at": (x + 10 + c.stringWidth(option["letter"], "Helvetica-Bold",
                                                     st["option_size"] + 0.5) / 2, baseline + 3.8),
            })
        box["rect"] = (LEFT - OPTION_REACH, bottom - st["option_gap"] / 2, BOX_RIGHT,
                       body_top + st["option_gap"] / 2)

    elif q["type"] == "label":
        diagram_top = body_top
        if q["word_bank"]:
            c.setFillGray(INK)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(LEFT, body_top - 12, "Word bank:")
            c.setFont("Helvetica", 9.5)
            c.drawString(LEFT + 58, body_top - 12, "     •     ".join(q["word_bank"]))
            diagram_top -= st["word_bank_h"]
        x0, y0 = LEFT, diagram_top - q["diagram"]["height"]
        draw_diagram(c, q["diagram"], x0, y0)
        for spot in q["labels"]:
            bx, by, bw, bh = spot["box"]
            c.setStrokeGray(OUTLINE)
            c.setLineWidth(1)
            c.rect(x0 + bx, y0 + by, bw, bh, stroke=1, fill=0)
            c.setFillGray(0.45)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(x0 + bx + 2.5, y0 + by + bh - 8, str(spot["n"]))
            if spot["points_to"]:
                _leader(c, (x0 + bx, y0 + by, bw, bh), (x0 + spot["points_to"][0], y0 + spot["points_to"][1]))
            box["labels"].append({"n": spot["n"], "rect": (x0 + bx, y0 + by, x0 + bx + bw, y0 + by + bh)})
        box["rect"] = (x0, y0, x0 + q["diagram"]["width"], diagram_top)

    else:  # draw
        x0, y0 = LEFT, body_top - q["diagram"]["height"]
        draw_diagram(c, q["diagram"], x0, y0)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(x0, y0, q["diagram"]["width"], q["diagram"]["height"], stroke=1, fill=0)
        box["rect"] = (x0, y0, x0 + q["diagram"]["width"], body_top)

    return box


def _key_item(q: dict) -> dict:
    item = {"q": q["q"], "type": q["type"], "prompt": q["prompt"], "points": q["points"], "key": "",
            "options": [], "answer": "", "labels": [], "word_bank": [], "checklist": [], "diagram": ""}
    if q["type"] == "short":
        item["key"] = q["key"]
    elif q["type"] == "choice":
        item.update(options=q["options"], answer=q["answer"],
                    key=f"{q['answer']}: " + next(o["text"] for o in q["options"] if o["letter"] == q["answer"]))
    elif q["type"] == "label":
        item.update(labels=q["labels"], word_bank=q["word_bank"], diagram=q["diagram"]["description"],
                    key="; ".join(f"{s['n']}: {s['answer']}" for s in q["labels"]))
    else:
        item.update(checklist=q["checklist"], diagram=q["diagram"]["description"],
                    key="; ".join(c["item"] for c in q["checklist"]))
    return item


def make_worksheet(defn: dict, out_dir: Path) -> dict:
    """Writes worksheet.pdf, layout.json, key.json, and worksheet.json. Returns the layout."""
    defn = normalize(defn)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    st = STYLES[defn["compact"]]
    summary = SUMMARY_RECT_COMPACT if defn["compact"] else SUMMARY_RECT
    pages = paginate(defn)

    c = canvas.Canvas(str(out_dir / "worksheet.pdf"), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(defn["title"])
    c.setAuthor("Paper Loop")
    page_layouts = []
    for page_no, indexes in enumerate(pages, start=1):
        code = page_code(defn["assignment_id"], page_no)
        for marker_id in MARKER_RECTS:
            _draw_marker(c, marker_id)
        _draw_code(c, code)
        _draw_header(c, defn, page_no, len(pages))
        _draw_footer(c, defn, page_no, len(pages), summary)
        boxes, y = [], CONTENT_TOP
        for i in indexes:
            q = defn["questions"][i]
            boxes.append(_draw_question(c, q, y, st))
            y -= block_height(q, st) + st["block_gap"]
        # "qr" and "qr_rect" keep the layout readable by the Paper Loop CLI.
        page_layouts.append({"page": page_no, "code": code, "qr": f"{defn['assignment_id']}|p{page_no}",
                             "qr_rect": CODE_AREA, "id_grid": None, "id_boxes": id_boxes(),
                             "summary_rect": summary, "boxes": boxes})
        c.showPage()
    c.save()

    layout = {"assignment_id": defn["assignment_id"], "title": defn["title"], "page_size": (PAGE_W, PAGE_H),
              "markers": MARKER_RECTS, "pages": page_layouts}
    key = {"assignment_id": defn["assignment_id"], "subject": defn["subject"], "grade_band": defn["grade_band"],
           "items": [_key_item(q) for q in defn["questions"]]}
    write_json(out_dir / "layout.json", layout)
    write_json(out_dir / "key.json", key)
    write_json(out_dir / "worksheet.json", defn)
    return layout


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def read_json(path: Path):
    return json.loads(Path(path).read_text())
