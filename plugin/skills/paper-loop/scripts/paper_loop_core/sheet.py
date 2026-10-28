"""The printed page: fixed geometry, the page code, and laying out a worksheet.

Everything is in PDF points (1/72 inch) with the origin at the bottom-left, as in reportlab.
Rects are [x0, y0, x1, y1]. The page geometry matches the Paper Loop CLI exactly, so sheets printed
from either one line up the same way.

Blocks on a worksheet:
- passage: printed text (a reading, a primary source), never marked; can run across pages
- short: a ruled box to write in, judged against a key or scored on a rubric
- choice: circle one letter
- label: write in numbered boxes on a printed diagram
- draw: draw in a frame, judged against a checklist
- blanks: fill in the blanks inside a sentence or paragraph
- match: write a letter (or number, or T/F) in the box beside each item
- table: fill in the empty cells of a printed table
- math: show work in an open area, then write the final answer in its own box
"""

from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from . import diagrams as D
from . import fonts as F

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

ID_RIGHT, ID_WRITE_Y = 550.0, 722.0  # the ID boxes end here; their bottom edge
CONTENT_TOP = 680.0
LEFT, BOX_RIGHT, GUTTER_LEFT, GUTTER_RIGHT = 48.0, 392.0, 404.0, 572.0
SUMMARY_RECT = (48.0, 64.0, 572.0, 136.0)
SUMMARY_RECT_COMPACT = (48.0, 56.0, 572.0, 106.0)

OPTION_REACH = 16.0  # a circle drawn around a letter pokes left of its text; count that ink too
CONTINUED_H = 16.0  # the "continued" line above the rest of an essay on a later page
QR_SIZE = 62.0  # a QR code in a note: big enough for a phone camera at arm's length
INK, OUTLINE, FAINT = 0.0, 0.35, 0.8  # FAINT is light enough that the ink threshold ignores it

# standard is the original look; compact fits about six questions on a page; primary is for grades 2-3:
# bigger print, primary-ruled writing lines (dashed midline), bigger boxes, two-digit IDs.
STYLES = {
    "standard": dict(prompt_size=11.0, prompt_leading=14.0, prompt_gap=6.0, line_spacing=22.0, block_gap=18.0,
                     option_size=10.5, option_leading=13.0, option_gap=9.0, word_bank_h=20.0, box_h=22.0,
                     blank_w=80.0, work_h=100.0, passage_size=10.5, passage_leading=14.0, id_box=(26.0, 30.0),
                     primary=False),
    "compact": dict(prompt_size=10.5, prompt_leading=12.5, prompt_gap=4.0, line_spacing=21.0, block_gap=11.0,
                    option_size=10.0, option_leading=12.0, option_gap=6.0, word_bank_h=17.0, box_h=20.0,
                    blank_w=72.0, work_h=86.0, passage_size=10.0, passage_leading=13.0, id_box=(26.0, 30.0),
                    primary=False),
    "primary": dict(prompt_size=14.0, prompt_leading=18.0, prompt_gap=8.0, line_spacing=36.0, block_gap=20.0,
                    option_size=13.5, option_leading=17.0, option_gap=12.0, word_bank_h=26.0, box_h=32.0,
                    blank_w=100.0, work_h=130.0, passage_size=14.0, passage_leading=20.0, id_box=(34.0, 38.0),
                    primary=True),
}


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


QUESTION_TYPES = {"short", "choice", "label", "draw", "blanks", "match", "table", "math"}
# Printed help under a question's prompt, added by a version's scaffolds or home language (forms.py).
ASIDES = ("example", "hint", "steps", "words", "bank", "translation", "last", "last_other")
_BAND_GRADES = ((r"kinder", 0), (r"elementary", 4), (r"middle", 7),
                (r"high school|\bap\b|\bib\b|honors|college", 10))


def grade_of(defn: dict) -> int:
    """The worksheet's grade, 0-12: "grade" if given, else read from grade_band ("6th grade", "middle school")."""
    if defn.get("grade") is not None:
        return int(defn["grade"])
    band = str(defn.get("grade_band", "")).lower()  # "4th grade", "grade 9", "grades 6-8"; not "Spanish 2"
    numbers = [int(m.group(1) or m.group(2)) for m in
               re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s-]*grade|\bgrades?\s*(\d{1,2})\b", band)]
    numbers = [n for n in numbers if 0 <= n <= 12]
    if numbers:
        return numbers[0]
    return next((g for pattern, g in _BAND_GRADES if re.search(pattern, band)), 7)


def _need(obj: dict, field: str, where: str):
    if field not in obj:
        raise WorksheetError(f"{where}: missing \"{field}\"")
    return obj[field]


def _check_staff(s: dict, where: str) -> None:
    if s["clef"] not in ("treble", "bass", "none"):
        raise WorksheetError(f'{where}: a staff\'s "clef" is "treble", "bass", or "none"')
    if s["lines"] not in (1, 5):
        raise WorksheetError(f'{where}: a staff has 5 "lines", or 1 for a rhythm line')
    if s["lines"] == 5 and s["clef"] == "none" and any(not n.get("rest") for n in s["notes"]):
        raise WorksheetError(f'{where}: notes on a 5-line staff need a clef to set their pitch; use "lines": 1 for '
                             f'rhythm without pitch')
    if s["time"] and not re.fullmatch(r"\d{1,2}/\d{1,2}", str(s["time"])):
        raise WorksheetError(f'{where}: "time" is a time signature like "4/4" or "3/4"')
    for k, note in enumerate(s["notes"], start=1):
        if "x" not in note:
            raise WorksheetError(f'{where}, note {k}: needs "x"')
        if note.get("rest"):
            if note["rest"] not in D.RESTS:
                raise WorksheetError(f'{where}, note {k}: "rest" is one of {", ".join(D.RESTS)}')
            continue
        if note.get("duration") and note["duration"] not in D.DURATIONS:
            raise WorksheetError(f'{where}, note {k}: "duration" is one of {", ".join(D.DURATIONS)}')
        if s["lines"] == 5 and not re.fullmatch(r"[A-Ga-g][#b]?[0-8]", str(note.get("pitch", ""))):
            raise WorksheetError(f'{where}, note {k}: pitch {note.get("pitch")!r} should be a letter, then # or b if '
                                 f'needed, then the octave, like "G4", "F#4", or "Bb3" (middle C is C4)')


def _diagram(d: dict, where: str, faint_images: bool) -> dict:
    d = {"shapes": [], "description": "", **d}
    _need(d, "width", where), _need(d, "height", where)
    shapes = []
    for n, raw in enumerate(d["shapes"], start=1):
        if raw.get("shape") not in D.SHAPES:
            raise WorksheetError(f"{where}, shape {n}: \"shape\" must be one of {', '.join(sorted(D.SHAPES))}")
        s = D.normalize_shape(raw)
        if s["shape"] == "staff":
            _check_staff(s, f"{where}, shape {n}")
        if s["shape"] == "image":
            if not s["path"]:
                raise WorksheetError(f"{where}, shape {n}: an image needs \"path\"")
            if "faint" not in raw:
                s["faint"] = faint_images  # pencil over a dark picture is hard to tell from the picture
        shapes.append(s)
    d["shapes"] = shapes
    return d


def _boxes_spec(entries: list, where: str, kind: str) -> list[dict]:
    out = []
    for n, e in enumerate(entries, start=1):
        e = {"n": n, "accept": [], "points": 1, **e}
        _need(e, "answer", f"{where}, {kind} {n}")
        e["answer"], e["accept"] = str(e["answer"]), [str(a) for a in e["accept"]]
        out.append(e)
    return out


def normalize(defn: dict) -> dict:
    """Fill in defaults and check the worksheet, with errors that say exactly what to fix."""
    defn = {"subject": "", "instructions": "Answer each question in its box. Write your ID number, not your name.",
            "compact": False, **defn}
    for field in ("assignment_id", "title", "questions"):
        _need(defn, field, "worksheet")
    defn["grade"] = grade_of(defn)
    defn.setdefault("grade_band", f"grade {defn['grade']}")
    style = defn.get("style") or ("primary" if defn["grade"] <= 3 else "compact" if defn["compact"] else "standard")
    if style not in STYLES:
        raise WorksheetError(f"worksheet: \"style\" must be one of {', '.join(STYLES)}")
    defn["style"] = style
    defn["id_style"] = "write"  # handwritten ID boxes: Claude reads them, so no bubble grid
    defn["id_digits"] = int(defn.get("id_digits") or (2 if defn["grade"] <= 3 else 4))
    defn["feedback"] = defn.get("feedback", "hint")
    if defn["feedback"] not in ("hint", "answer"):
        raise WorksheetError("worksheet: \"feedback\" must be \"hint\" (point toward the fix) or \"answer\" "
                             "(comments may give the right answer)")
    defn["teacher_notes"] = defn.get("teacher_notes", "")
    defn["comment_language"] = defn.get("comment_language", "English")
    if not 2 <= defn["id_digits"] <= 4:
        raise WorksheetError("worksheet: \"id_digits\" must be 2, 3, or 4")
    defn["print"] = {"scale": 1.0, "space": 1.0, "per_page": None, **(defn.get("print") or {})}
    blocks, seen_q, passages = [], set(), 0
    for raw in defn["questions"]:
        kind = raw.get("type", "short")
        if kind == "note":  # printed text that isn't a reading: "Done early?", directions, a key-word box
            raw, kind = {**raw, "type": "passage", "note": True}, "passage"
        if kind == "passage":
            passages += 1
            p = {"title": "", "source": "", "line_numbers": False, "id": f"passage-{passages}", "mono": False,
                 "note": False, "lang": "", "license": "", **raw}
            p.setdefault("number_every", 1 if p["mono"] else 5)
            _need(p, "text", f"passage {passages}")
            if p.get("cite"):
                from . import sources as SR
                p["source"], p["license"] = SR.check_cite(p["cite"], f"passage {p['title'] or passages}")
            blocks.append(p)
            continue
        q = {"type": "short", "spelling": False, "passage": None, "notes": "", "asides": [], "frame": [], **raw}
        where = f"question {q.get('q', '?')}"
        if isinstance(q["passage"], list):  # a question about two sources: the first leads, marking sees both
            q["passages"] = [str(p) for p in q["passage"]]
            q["passage"] = q["passages"][0] if q["passages"] else None
        elif q["passage"] is not None and not isinstance(q["passage"], str):
            raise WorksheetError(f"{where}: \"passage\" is a passage's id, or a list of them")
        for aside in q["asides"]:
            if aside.get("kind") not in ASIDES or "text" not in aside:
                raise WorksheetError(f"{where}: each aside needs \"kind\" ({', '.join(ASIDES)}) and \"text\"")
        _need(q, "q", where)
        try:
            q["q"] = int(q["q"])
        except (TypeError, ValueError):
            raise WorksheetError(f"{where}: \"q\" must be a whole number (number parts 3a and 3b as 3 and 4)")
        if q["q"] in seen_q:
            raise WorksheetError(f"{where}: two questions have the same number")
        seen_q.add(q["q"])
        if kind not in QUESTION_TYPES:
            raise WorksheetError(f"{where}: \"type\" must be passage, {', '.join(sorted(QUESTION_TYPES))}")
        if kind == "short":
            q = {"points": 2, "lines": 4, "rubric": [], **q}
            _need(q, "prompt", where)
            if q["rubric"]:
                rubric = []
                for n, c in enumerate(q["rubric"], start=1):
                    c = {"n": n, "short": "", **c}
                    _need(c, "criterion", f"{where}, rubric {n}")
                    if len(_need(c, "levels", f"{where}, rubric {n}")) < 2:
                        raise WorksheetError(f"{where}, rubric {n}: give at least two levels, lowest first")
                    c["max"] = len(c["levels"]) - 1
                    rubric.append(c)
                q["rubric"] = rubric
                q["points"] = sum(c["max"] for c in rubric)
                q.setdefault("key", "Scored on the rubric.")
            _need(q, "key", where)
        elif kind == "choice":
            q = {"points": 1, "columns": 1, **q}
            _need(q, "prompt", where)
            options = [{"why": "", **o} for o in _need(q, "options", where)]
            for n, o in enumerate(options, start=1):
                _need(o, "letter", f"{where}, option {n}"), _need(o, "text", f"{where}, option {n}")
            q["options"] = options
            if _need(q, "answer", where) not in {o["letter"] for o in options}:
                raise WorksheetError(f"{where}: answer {q['answer']!r} isn't one of the option letters")
        elif kind == "label":
            q = {"word_bank": [], **q}
            _need(q, "prompt", where)
            q["diagram"] = _diagram(_need(q, "diagram", where), where, faint_images=False)
            q["labels"] = [{"points_to": None, "accept": [], "points": 1, **s} for s in _need(q, "labels", where)]
            for s in q["labels"]:
                spot = f"{where}, label {s.get('n', '?')}"
                _need(s, "n", spot), _need(s, "box", spot), _need(s, "answer", spot)
                if len(s["box"]) != 4:
                    raise WorksheetError(f"{spot}: \"box\" is [x, y, width, height]")
                s["answer"], s["accept"] = str(s["answer"]), [str(a) for a in s["accept"]]
            q["points"] = sum(s["points"] for s in q["labels"])
        elif kind == "draw":
            q = {"answer": None, "accept": [], "units": "", "answer_points": 1, "answer_width": 120.0, **q}
            _need(q, "prompt", where)
            q["diagram"] = _diagram(_need(q, "diagram", where), where, faint_images=True)
            q["checklist"] = [{"short": "", "points": 1, **c} for c in _need(q, "checklist", where)]
            if not q["checklist"]:
                raise WorksheetError(f"{where}: a drawing needs at least one checklist item")
            for n, c in enumerate(q["checklist"], start=1):
                _need(c, "item", f"{where}, checklist item {n}")
            if q["answer"] is not None:  # draw, then write a result in its own box ("shade it, then write the sum")
                q["answer"], q["accept"] = str(q["answer"]), [str(a) for a in q["accept"]]
            q["points"] = sum(c["points"] for c in q["checklist"]) + (q["answer_points"] if q["answer"] else 0)
        elif kind == "blanks":
            q = {"prompt": "Fill in the blanks.", "word_bank": [], **q}
            text = _need(q, "text", where)
            answers = q.get("answers")
            if isinstance(answers, dict):
                answers = [{"n": int(k), **(v if isinstance(v, dict) else {"answer": v})}
                           for k, v in sorted(answers.items(), key=lambda kv: int(kv[0]))]
            q["answers"] = _boxes_spec(_need({"answers": answers} if answers else {}, "answers", where), where, "blank")
            numbers = [int(n) for n in re.findall(r"\{(\d+)\}", text)]
            if sorted(numbers) != sorted(a["n"] for a in q["answers"]):
                raise WorksheetError(f"{where}: the text's blanks {{1}}, {{2}}, ... must match the answers' numbers")
            q["points"] = sum(a["points"] for a in q["answers"])
        elif kind == "match":
            q = {"prompt": "Write the letter of the match in each box.", "choices": [], **q}
            q["items"] = _boxes_spec(_need(q, "items", where), where, "item")
            for item in q["items"]:
                _need(item, "text", f"{where}, item {item['n']}")
            q["choices"] = [{"letter": c.get("letter", chr(65 + i)), "text": c.get("text", "")} if isinstance(c, dict)
                            else {"letter": chr(65 + i), "text": str(c)} for i, c in enumerate(q["choices"])]
            # Ordering and true/false (no choices): items are lettered, so their names can't be mistaken for answers.
            for item in q["items"]:
                item["name"] = str(item["n"]) if q["choices"] else chr(64 + item["n"])
            q["points"] = sum(i["points"] for i in q["items"])
        elif kind == "table":
            q = {"col_widths": None, "row_height": None, **q}
            _need(q, "prompt", where)
            columns = _need(q, "columns", where)
            if q["col_widths"] and len(q["col_widths"]) != len(columns):
                raise WorksheetError(f"{where}: \"col_widths\" needs one width per column ({len(columns)})")
            rows = []
            n = 0
            for r, row in enumerate(_need(q, "rows", where), start=1):
                if len(row) != len(columns):
                    raise WorksheetError(f"{where}, row {r}: has {len(row)} cells but there are {len(columns)} columns")
                cells = []
                for cell in row:
                    if isinstance(cell, dict):
                        n += 1
                        cell = {"n": n, "accept": [], "points": 1, **cell}
                        _need(cell, "answer", f"{where}, row {r}")
                        cell["answer"], cell["accept"] = str(cell["answer"]), [str(a) for a in cell["accept"]]
                    else:
                        cell = "" if cell is None else str(cell)
                    cells.append(cell)
                rows.append(cells)
            if not n:
                raise WorksheetError(f"{where}: no cells to fill; write those as {{\"answer\": \"...\"}}")
            q["rows"] = rows
            q["points"] = sum(c["points"] for row in rows for c in row if isinstance(c, dict))
        elif kind == "math":
            q = {"accept": [], "units": "", "key": "", "answer_points": 1, "work_points": 1, "work_height": None,
                 "grid": False, "answer_width": 120.0, **q}
            _need(q, "prompt", where)
            q["answer"] = str(_need(q, "answer", where))
            q["accept"] = [a for a in dict.fromkeys(str(a) for a in q["accept"]) if a != q["answer"]]
            q["points"] = q["answer_points"] + q["work_points"]
        if kind in ("label", "draw") and q["diagram"]["width"] > BOX_RIGHT - LEFT:
            raise WorksheetError(f"{where}: diagram is wider than {BOX_RIGHT - LEFT:g}pt")
        blocks.append(q)
    ids = {b["id"] for b in blocks if b["type"] == "passage" and not b["note"]}
    for b in blocks:
        for pid in b.get("passages") or ([b["passage"]] if b["type"] != "passage" and b.get("passage") else []):
            if pid not in ids:
                raise WorksheetError(f"question {b['q']}: no passage with id {pid!r}")
    defn["questions"] = blocks
    return defn


def all_texts(defn: dict) -> list[str]:
    """Every string the worksheet prints in its own font, for choosing it. Home-language text (a
    translation, a note in another language) gets its own font, so it isn't listed."""
    out = [defn["title"], defn["instructions"]]
    for b in defn["questions"]:
        if b.get("lang"):
            continue
        out += [b.get("prompt", ""), b.get("title", ""), b.get("source", ""), b.get("units", "")]
        out += [b.get("text", "")] if isinstance(b.get("text"), str) else []
        out += list(b.get("frame", []))
        for aside in b.get("asides", []):
            if aside["kind"] != "translation":
                out += aside["text"] if isinstance(aside["text"], list) else [aside["text"]]
        out += [o.get("text", "") for o in b.get("options", [])] + list(b.get("word_bank", []))
        out += [i["text"] for i in b.get("items", [])] + [c["text"] for c in b.get("choices", [])]
        if b["type"] == "table":
            out += list(b["columns"]) + [c for row in b["rows"] for c in row if isinstance(c, str)]
        if "diagram" in b:
            out += D.diagram_texts(b["diagram"])
    return out


# --- Measuring ----------------------------------------------------------------------

class Layout:
    """Measures and draws blocks for one worksheet's style and fonts."""

    def __init__(self, defn: dict, fonts: F.Fonts, base: Path, label: str = "", student_id: str = ""):
        self.defn, self.f, self.base, self.label, self.student_id = defn, fonts, base, label, student_id
        pr = defn.get("print") or {}
        # Large print scales type and answer areas; "space" gives more room to write; both are versions.
        self.k, self.space, self.per_page = float(pr.get("scale") or 1), float(pr.get("space") or 1), pr.get("per_page")
        st = dict(STYLES[defn["style"]])
        for key in ("prompt_size", "prompt_leading", "prompt_gap", "line_spacing", "option_size", "option_leading",
                    "option_gap", "word_bank_h", "box_h", "blank_w", "work_h", "passage_size", "passage_leading"):
            st[key] *= self.k
        st["line_spacing"] *= self.space
        st["work_h"] *= self.space
        st["box_h"] *= min(self.space, 1.25)
        self.st = st
        self.summary = SUMMARY_RECT_COMPACT if defn["style"] == "compact" else SUMMARY_RECT
        self.bottom = self.summary[3] + 12
        self.lang_fonts: dict[tuple[str, str], tuple[str, str]] = {}
        # The header grows with large print too (up to 1.6x): directions, labels, and the ID boxes.
        self.hk = min(self.k, 1.6)
        self.header_size, self.header_leading = (10.5, 13.0) if st["primary"] else (8.5, 10.5)
        self.header_size, self.header_leading = self.header_size * self.hk, self.header_leading * self.hk
        self.header_lines = self.split(defn["instructions"], fonts.regular, self.header_size, 290)
        # Large print: the directions start below the bigger "Page 1 of N" line, not on it.
        self.header_top = min(716.0, 727 - 2 * (self.hk - 1) - 0.75 * self.header_size)
        self.content_top = min(CONTENT_TOP, self.header_top - (len(self.header_lines) - 1) * self.header_leading - 12
                               - (6 if len(self.header_lines) > 3 else 0))  # a fourth line keeps clear of the rule

    def sized(self, value: float, room: bool = False) -> float:
        """A size the worksheet set (a box height, a work area), at this version's print size."""
        return float(value) * self.k * (min(self.space, 1.25) if room == "box" else self.space if room else 1)

    def diagram_scale(self, q: dict) -> float:
        return min(self.k, (BOX_RIGHT - LEFT) / q["diagram"]["width"])

    # Text helpers
    def split(self, text: str, font: str, size: float, width: float) -> list[str]:
        out = []
        for para in self.f.text(text).split("\n"):
            out += simpleSplit(para, font, size, width) or [""]
        return out

    def lang_font(self, text: str, lang: str = "") -> tuple[str, str]:
        """(font, how) for home-language text: see fonts.font_for."""
        from . import script as SC
        key = (text, lang)
        if key not in self.lang_fonts:
            shaped = SC.shape(text, lambda ch: F.covers(self.f.regular, ch))
            self.lang_fonts[key] = F.font_for(shaped, self.f, lang)
        return self.lang_fonts[key]

    def wrap(self, text: str, font: str, size: float, width: float) -> list[str]:
        return wrap_text(text, font, size, width)

    def draw_line(self, c, text: str, x0: float, x1: float, baseline: float, font: str, size: float,
                  rtl: bool | None = None) -> None:
        """A line of any language: right-to-left lines are put in display order and set flush right. rtl is the
        direction of the text the line belongs to (a whole translation reads right to left, even a line that
        starts with "A."); None takes it from the line's first letter."""
        from . import script as SC
        c.setFont(font, size)
        if SC.has_rtl(text):
            right = SC.rtl_line(text) if rtl is None else rtl
            line = SC.visual(text, right)
            c.drawString(x1 - c.stringWidth(line, font, size) if right else x0, baseline, line)
        else:
            c.drawString(x0, baseline, text)

    # Asides: help printed between a prompt and its answer area (a version's scaffolds, a translation)
    ASIDE_LABELS = {"example": "Example", "hint": "Hint:", "steps": "Steps:", "words": "Key words:",
                    "bank": "Word bank:", "last": "Last time:", "last_other": "Last time (other numbers):"}

    def aside_lines(self, q: dict) -> list[dict]:
        """Each aside laid out: its font, size, lines, and height."""
        out = []
        from . import script as SC
        width = BOX_RIGHT - LEFT - 12
        size = self.st["prompt_size"] * 0.92
        leading = self.st["prompt_leading"] * 0.92
        for aside in q.get("asides", []):
            kind, text = aside["kind"], aside["text"]
            if kind == "translation":  # the same size as the English: a home language isn't secondary
                tsize, tlead = self.st["prompt_size"], self.st["prompt_leading"] * 1.05
                font, how = self.lang_font(text, aside.get("lang", ""))
                lines = self.wrap(text, font, tsize, width)
                out.append({"kind": kind, "font": font, "how": how, "size": tsize, "leading": tlead,
                            "lines": lines, "height": len(lines) * tlead + 6, "rtl": SC.has_rtl(text)})
                continue
            if kind == "steps":
                text = "\n".join(f"{n}. {step}" for n, step in enumerate(text, start=1))
            elif kind == "words":
                text = "\n".join(text)
            elif kind == "bank":
                text = "     •     ".join(text)
            label = self.ASIDE_LABELS[kind]
            font = self.f.oblique if kind in ("hint", "last", "last_other") else self.f.regular
            if kind in ("steps", "words", "example"):
                lines = [label] + self.split(text, font, size, width - 8)
            else:
                lines = self.split(f"{label} {text}", font, size, width)
            pad = 8 if kind == "example" else 4
            out.append({"kind": kind, "font": font, "how": "base", "size": size, "leading": leading, "lines": lines,
                        "label": label, "height": len(lines) * leading + pad})
        return out

    def asides_height(self, q: dict) -> float:
        return sum(a["height"] + 3 for a in self.aside_lines(q))

    def prompt_lines(self, q: dict) -> list[str]:
        return self.split(f"{q['q']}. {q['prompt']}", self.f.regular, self.st["prompt_size"], BOX_RIGHT - LEFT)

    # Passages: full width, no feedback gutter, split across pages by line
    def passage_font(self, p: dict) -> str:
        if p.get("lang"):
            return self.lang_font(p["text"], p["lang"])[0]
        return self.f.mono if p.get("mono") else self.f.regular

    def code_lines(self, p: dict) -> list[tuple[str, bool]]:
        """Code (mono): every line with its indentation, hard-wrapping only what's too long. Each printed
        line comes with whether it continues the line before."""
        char = self._width("M", self.f.mono, self.st["passage_size"])
        per_line = max(20, int((GUTTER_RIGHT - LEFT - 16) / char))
        out = []
        for line in self.f.text(p["text"].rstrip("\n")).split("\n"):
            line, more = line.expandtabs(4), False
            while len(line) > per_line:
                out.append((line[:per_line], more))
                line, more = "    " + line[per_line:], True
            out.append((line, more))
        return out

    def psize(self, p: dict) -> float:
        """A passage's type size: the style's, or its own "size" (a note for the adult, in small print)."""
        return float(p.get("size") or self.st["passage_size"])

    def plead(self, p: dict) -> float:
        return self.psize(p) * 1.3 if p.get("size") else self.st["passage_leading"]

    def passage_width(self, p: dict) -> float:
        return GUTTER_RIGHT - LEFT - 16 - (QR_SIZE + 12 if p.get("qr") else 0)

    def passage_lines(self, p: dict) -> list[str]:
        width = self.passage_width(p)
        if p.get("mono"):
            return [line for line, _ in self.code_lines(p)]
        out = []
        for n, para in enumerate(p["text"].strip().split("\n\n")):
            if n:
                out.append("")
            for line in para.split("\n"):  # a single line break is kept: poems, addresses, lists
                if p.get("lang"):
                    out += self.wrap(" ".join(line.split()), self.passage_font(p), self.psize(p), width)
                    continue
                out += simpleSplit(self.f.text(" ".join(line.split())), self.f.regular, self.psize(p),
                                   width) or [""]
        return out

    def passage_numbers(self, p: dict) -> list[int | None]:
        """Each printed line's number: text lines count, the gaps between paragraphs don't. In code (mono),
        every source line counts, blank or not, as in an editor; a wrapped part gets no number."""
        if p.get("mono"):
            out, n = [], 0
            for _, more in self.code_lines(p):
                n += not more
                out.append(None if more else n)
            return out
        out, n = [], 0
        for line in self.passage_lines(p):
            if line:
                n += 1
            out.append(n if line else None)
        return out

    def passage_height(self, p: dict, start: int, end: int, n_lines: int) -> float:
        h = (end - start) * self.plead(p) + 12
        if start == 0 and p["title"]:
            h += self.psize(p) + 10
        if end == n_lines and p["source"]:
            h += 12 * len(self.source_lines(p)) + 2
        return max(h, QR_SIZE + 12) if p.get("qr") else h

    def source_lines(self, p: dict) -> list[str]:
        return simpleSplit(self.f.text(p["source"]), self.f.oblique, 8, GUTTER_RIGHT - LEFT - 16)

    def body_font(self, q: dict) -> str:
        """Options, cells, and blanks text: code ("mono": true) or regular."""
        return self.f.mono if q.get("mono") else self.f.regular

    # Choice options
    def option_geometry(self, q: dict):
        columns = max(1, q["columns"])
        col_w = (BOX_RIGHT - LEFT) / columns
        indent = ((36.0 if self.st["primary"] else 30.0) if columns == 1 else  # room for the letter
                  (30.0 if self.st["primary"] else 20.0)) * self.k
        width = col_w - indent - (0 if columns == 1 else 4)
        lines = [self.split(o["text"], self.body_font(q), self.st["option_size"], width) for o in q["options"]]
        return columns, col_w, indent, lines

    def option_rows(self, q: dict) -> list[float]:
        columns, _, _, lines = self.option_geometry(q)
        rows = [lines[i:i + columns] for i in range(0, len(lines), columns)]
        return [max(len(l) for l in row) * self.st["option_leading"] for row in rows]

    # Blanks: words and boxes flowed into lines
    def blank_flow(self, q: dict) -> list[list[tuple]]:
        size, width = self.st["prompt_size"], BOX_RIGHT - LEFT
        font = self.f.mono if q.get("mono") else self.f.regular
        widths = {a["n"]: self.sized(a["width"]) if "width" in a else self.st["blank_w"] for a in q["answers"]}
        space = self.f.text(" ")
        text = "\n".join(line.expandtabs(4) for line in q["text"].split("\n")) if q.get("mono") else q["text"]
        tokens = []  # (kind, value, space before); "\n" in the text starts a new line
        for piece in re.split(r"(\{\d+\}|\n)", text):
            m = re.fullmatch(r"\{(\d+)\}", piece)
            if m:
                tokens.append(("blank", int(m.group(1)), bool(tokens) and tokens[-1][0] == "space"))
                continue
            if piece == "\n":
                tokens.append(("break", None, False))
                continue
            if q.get("mono") and (not tokens or tokens[-1][0] == "break"):
                indent = len(piece) - len(piece.lstrip(" "))
                if indent:  # code keeps its indentation
                    tokens.append(("indent", indent, False))
            for part in re.split(r"(\t|[^\S\t]+)", piece):
                if not part:
                    continue
                if part == "\t":  # the next item starts at the middle of the line
                    tokens.append(("tab", None, False))
                elif part.isspace():
                    tokens.append(("space", part, False))
                else:
                    tokens.append(("word", self.f.text(part), bool(tokens) and tokens[-1][0] == "space"))
        lines, x = [[]], 0.0
        gap = self._width(space, font, size)
        for kind, value, spaced in tokens:
            if kind == "space":
                continue
            if kind == "break":
                lines.append([])
                x = 0.0
                continue
            if kind == "indent":
                x = value * gap
                continue
            if kind == "tab":
                stop = width / 2
                if x + gap > stop and lines[-1]:
                    lines.append([])
                    x = 0.0
                else:
                    x = stop if lines[-1] else 0.0
                continue
            w = widths[value] if kind == "blank" else self._width(value, font, size)
            after_tab = bool(lines[-1]) and x == width / 2 and lines[-1][-1][2] + lines[-1][-1][3] < x
            g = 0.0 if after_tab else gap if spaced and lines[-1] else (2.0 if kind == "blank" and lines[-1] else 0.0)
            if x + g + w > width and lines[-1]:
                lines.append([])
                x, g = 0.0, 0.0
            lines[-1].append((kind, value, x + g, w))
            x += g + w
        return lines

    def _width(self, text: str, font: str, size: float) -> float:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        return stringWidth(text, font, size)

    def box_h(self, q: dict) -> float:
        """Height of write-in boxes: the style's, or the question's box_height (bigger for big writers)."""
        return self.sized(q["box_height"], "box") if q.get("box_height") else self.st["box_h"]

    def blank_line_h(self, q: dict) -> float:
        return self.box_h(q) + 8

    def blank_heights(self, q: dict) -> list[float]:
        """Each line of a blanks question: room for a box, or just text height where there's no blank
        (most lines of a code listing)."""
        text_h = self.st["prompt_size"] * 1.7
        return [self.blank_line_h(q) if any(kind == "blank" for kind, *_ in line) else text_h
                for line in self.blank_flow(q)]

    # Match: items on the left with boxes, choices on the right
    def match_geometry(self, q: dict):
        box_w = (38.0 if self.st["primary"] else 30.0) * self.k
        full = BOX_RIGHT - LEFT
        size, leading = self.st["option_size"], self.st["option_leading"]
        if q["choices"]:  # split the width by how much each side has to say, from 40% to 70% for the items
            longest = lambda texts: max(self._width(w, self.f.regular, size) for t in texts for w in t.split() or [t])  # noqa: E731
            need_items = box_w + 12 + max(self._width(i["text"], self.f.regular, size) for i in q["items"]) * 0.6
            need_choices = 8 + max(self._width(f"{c['letter']}. {c['text']}", self.f.regular, size)
                                   for c in q["choices"]) * 0.6
            left_w = full * min(0.7, max(0.4, need_items / (need_items + need_choices)))
            # never narrower than the longest single word on either side (large print: "photosynthesis")
            left_w = max(left_w, box_w + 16 + longest([i["text"] for i in q["items"]]))
            left_w = min(left_w, full - 12 - longest([f"{c['letter']}. {c['text']}" for c in q["choices"]]))
        else:
            left_w = full
        # With choices, items carry no numbers of their own: under "4." they read as question numbers.
        item_lines = [self.split(f"{i['name']}. {i['text']}" if not q["choices"] else i["text"], self.f.regular,
                                 size, left_w - box_w - 12) for i in q["items"]]
        item_h = [max(self.box_h(q) + 6, len(l) * leading + 6) for l in item_lines]
        choice_lines = [self.split(f"{c['letter']}. {c['text']}", self.f.regular, size, full - left_w - 8)
                        for c in q["choices"]]
        choice_h = [len(l) * leading + 4 for l in choice_lines]
        return box_w, left_w, item_lines, item_h, choice_lines, choice_h

    # Table
    def table_geometry(self, q: dict):
        full = BOX_RIGHT - LEFT
        n = len(q["columns"])
        widths = q["col_widths"] or [full / n] * n
        if abs(sum(widths) - full) > 0.5:
            widths = [w * full / sum(widths) for w in widths]
        size = self.st["option_size"]
        header = [self.split(h, self.f.bold, size, w - 6) for h, w in zip(q["columns"], widths)]
        header_h = max(len(l) for l in header) * (size + 2) + 8
        row_h = self.sized(q["row_height"], "box") if q["row_height"] else self.st["box_h"] + 10 * self.k
        cell_lines = [[self.split(c, self.body_font(q), size, w - 6) if isinstance(c, str) else []
                       for c, w in zip(row, widths)] for row in q["rows"]]
        heights = [max(row_h, max((len(l) for l in row), default=1) * (size + 2) + 8) for row in cell_lines]
        return widths, header, header_h, cell_lines, heights

    def math_heights(self, q: dict) -> tuple[float, float]:
        work = self.sized(q["work_height"], True) if q.get("work_height") else self.st["work_h"]
        return work, self.st["box_h"] + 12

    def body_height(self, q: dict) -> float:
        st = self.st
        kind = q["type"]
        if kind == "short":
            return q["lines"] * st["line_spacing"]
        if kind == "choice":
            rows = self.option_rows(q)
            return sum(rows) + st["option_gap"] * (len(rows) - 1)
        if kind == "label":
            return q["diagram"]["height"] * self.diagram_scale(q) + self.word_bank_height(q)
        if kind == "draw":
            return q["diagram"]["height"] * self.diagram_scale(q) + (self.math_heights(q)[1] if q.get("answer") else 0)
        if kind == "blanks":
            return sum(self.blank_heights(q)) + self.word_bank_height(q)
        if kind == "match":
            *_, item_h, _, choice_h = self.match_geometry(q)
            return max(sum(item_h), sum(choice_h))
        if kind == "table":
            _, _, header_h, _, heights = self.table_geometry(q)
            return header_h + sum(heights)
        work, answer = self.math_heights(q)
        return work + answer

    def word_bank_lines(self, q: dict) -> list[str]:
        if not q.get("word_bank"):
            return []
        size = (13.0 if self.st["primary"] else 9.5) * self.k
        indent = self._width("Word bank: ", self.f.bold, size) + 4
        return simpleSplit(self.f.text("     •     ".join(q["word_bank"])), self.f.regular, size,
                           BOX_RIGHT - LEFT - indent)

    def word_bank_height(self, q: dict) -> float:
        n = len(self.word_bank_lines(q))
        return self.st["word_bank_h"] + (n - 1) * (self.st["word_bank_h"] - 4) if n else 0.0

    def block_height(self, q: dict) -> float:
        return (len(self.prompt_lines(q)) * self.st["prompt_leading"] + self.asides_height(q) + self.st["prompt_gap"]
                + self.body_height(q))

    # Pagination
    def paginate(self) -> list[list[tuple]]:
        """Each page's pieces: (block index, None) for a question, (block index, (start, end)) for passage lines
        or for the writing lines of an essay that runs onto more pages."""
        st = self.st
        pages: list[list[tuple]] = [[]]
        y = self.content_top
        for i, b in enumerate(self.defn["questions"]):
            if b["type"] == "passage":
                lines = self.passage_lines(b)
                start = 0
                while start < len(lines):
                    room = y - self.bottom
                    end = len(lines)
                    while end > start and self.passage_height(b, start, end, len(lines)) > room:
                        end -= 1
                    if end - start < min(4, len(lines) - start) or (b.get("qr") and end < len(lines)):
                        if not pages[-1]:
                            raise WorksheetError(f"{b['id']}: a single line doesn't fit on a page")
                        pages.append([])
                        y = self.content_top
                        continue
                    pages[-1].append((i, (start, end)))
                    y -= self.passage_height(b, start, end, len(lines)) + st["block_gap"]
                    start = end
                continue
            height = self.block_height(b)
            if b["type"] == "short" and height > self.content_top - self.bottom:  # an essay: continues on the next page
                start = 0
                while start < b["lines"]:
                    head = self.question_height(b, (start, start))
                    fit = int((y - self.bottom - head) // st["line_spacing"])
                    if fit < min(6, b["lines"] - start):  # too little room: start a new page
                        if not pages[-1]:
                            raise WorksheetError(f"question {b['q']}: its prompt doesn't fit on a page")
                        pages.append([])
                        y = self.content_top
                        continue
                    end = min(b["lines"], start + fit)
                    short = b["lines"] - end
                    if 0 < short < 4 and end - start - (4 - short) >= 6:
                        end -= 4 - short  # don't leave a line or two alone on the next page
                    pages[-1].append((i, (start, end)))
                    y -= self.piece_height(i, (start, end)) + st["block_gap"]
                    start = end
                continue
            if height > self.content_top - self.bottom:
                raise WorksheetError(f"question {b['q']}: too tall for one page ({height:.0f}pt of "
                                     f"{self.content_top - self.bottom:.0f}pt); use fewer lines or a smaller diagram"
                                     + (" (at this version's print size)" if self.k > 1 or self.space > 1 else ""))
            on_page = sum(1 for j, _ in pages[-1] if self.defn["questions"][j]["type"] != "passage")
            if (y - height < self.bottom or self.per_page and on_page >= self.per_page) and pages[-1]:
                pages.append([])
                y = self.content_top
            pages[-1].append((i, None))
            y -= height + st["block_gap"]
        return pages

    def grow(self) -> None:
        """Fewer questions to a page leave room: give it to writing lines and work areas, page by page, so a
        version printed a question or two to a page has more room to write, not blank paper."""
        st = self.st
        for pieces, free in zip(self.paginate(), self.free_by_page()):
            room = free - 12
            growing = [i for i, part in pieces if part is None and self.defn["questions"][i]["type"] in ("short", "math")]
            if not growing or room < st["line_spacing"]:
                continue
            share = room / len(growing)
            for i in growing:
                q = self.defn["questions"][i]
                if q["type"] == "short":  # at most double: more room to write, not a page of lines to fill
                    q["lines"] += min(q["lines"], int(share // st["line_spacing"]))
                else:
                    factor = self.sized(100, True) / 100
                    work = self.math_heights(q)[0]
                    q["work_height"] = (work + min(work, share)) / factor

    def space_left(self) -> float:
        """Points of free space at the bottom of the last page (negative means it doesn't fit)."""
        y = self.content_top
        for i, part in self.paginate()[-1]:
            y -= self.piece_height(i, part) + self.st["block_gap"]
        return y + self.st["block_gap"] - self.bottom

    def shortfall(self) -> float:
        """Points to cut to lose the last page (0 if there's only one page)."""
        pages = self.paginate()
        if len(pages) < 2:
            return 0.0
        y = self.content_top
        for i, part in pages[-2]:
            y -= self.piece_height(i, part) + self.st["block_gap"]
        room = y - self.bottom
        need = sum(self.piece_height(i, part) + self.st["block_gap"] for i, part in pages[-1]) - self.st["block_gap"]
        return max(0.0, need - room)

    def free_by_page(self) -> list[float]:
        out = []
        for pieces in self.paginate():
            y = self.content_top
            for i, part in pieces:
                y -= self.piece_height(i, part) + self.st["block_gap"]
            out.append(y + self.st["block_gap"] - self.bottom)
        return out

    def piece_height(self, i: int, part) -> float:
        b = self.defn["questions"][i]
        if b["type"] == "passage":
            return self.passage_height(b, part[0], part[1], len(self.passage_lines(b)))
        return self.question_height(b, part)

    def question_height(self, q: dict, part: tuple | None = None) -> float:
        """A question's height, or one part of an essay's: the prompt (or a "continued" line) and its lines."""
        if part is None:
            return self.block_height(q)
        head = self.block_height(q) - self.body_height(q) if part[0] == 0 else CONTINUED_H
        return head + (part[1] - part[0]) * self.st["line_spacing"]


def wrap_text(text: str, font: str, size: float, width: float) -> list[str]:
    """Lines of any language's text, in logical order: Arabic script shaped first, Chinese, Japanese, and
    Korean broken between characters where there are no spaces."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from . import script as SC
    if SC.has_rtl(text):
        text = SC.shape(text, lambda ch: F.covers(font, ch))
    out = []
    for para in text.split("\n"):
        if not SC.has_cjk(para):
            out += simpleSplit(para, font, size, width) or [""]
            continue
        line = ""
        for ch in para:
            if stringWidth(line + ch, font, size) > width and line:
                cut = line.rfind(" ")
                if cut > len(line) // 2:
                    out.append(line[:cut])
                    line = line[cut + 1:]
                else:
                    out.append(line)
                    line = ""
                if ch == " ":
                    continue
            line += ch
        out.append(line)
    return out


# --- Drawing ------------------------------------------------------------------------

def id_boxes(digits: int = 4, style: str = "standard", scale: float = 1.0) -> list[tuple[float, float, float, float]]:
    w, h = (v * min(scale, 1.4) for v in STYLES[style]["id_box"])
    x0 = ID_RIGHT - digits * w
    return [(x0 + d * w, ID_WRITE_Y, x0 + (d + 1) * w, ID_WRITE_Y + h) for d in range(digits)]


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


def _draw_header(c: canvas.Canvas, L: Layout, page_no: int, n_pages: int, boxes) -> None:
    f, defn = L.f, L.defn
    c.setFillGray(INK)
    room = boxes[0][0] - 40 - 138  # up to the "ID #" label
    size = 15.0
    while size > 10 and c.stringWidth(f.text(defn["title"]), f.bold, size) > room:
        size -= 0.5
    c.setFont(f.bold, size)
    c.drawString(138, 744, f.text(defn["title"]))
    c.setFont(f.regular, 9 * L.hk)
    c.drawString(138, 730 - 2 * (L.hk - 1), f"Page {page_no} of {n_pages}")
    c.setFont(f.regular, L.header_size)
    y = L.header_top
    for line in L.header_lines:  # the header rule sits below the last line
        c.drawString(138, y, line)
        y -= L.header_leading
    c.setFont(f.bold, 10 * L.hk)
    c.drawRightString(boxes[0][0] - 6, boxes[0][1] + 11, "ID #")
    c.setFont(f.regular, 6.5 * L.hk)
    c.setFillGray(0.45)
    c.drawString(boxes[0][0], boxes[0][1] - 9 * L.hk, "one digit per box, not your name" if len(boxes) > 2
                 else "your number")
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(0.8)
    for x0, y0, x1, y1 in boxes:
        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
    if L.student_id:  # a sheet made for one student (practice): their class ID, printed for them
        c.setFillGray(0.3)
        c.setFont(f.regular, 16)
        for (x0, y0, x1, y1), digit in zip(boxes, L.student_id):
            c.drawCentredString((x0 + x1) / 2, y0 + (y1 - y0) / 2 - 5.5, digit)
    c.setFillGray(INK)
    c.line(LEFT, L.content_top + 8, GUTTER_RIGHT, L.content_top + 8)


def _draw_footer(c: canvas.Canvas, L: Layout, page_no: int, n_pages: int) -> None:
    x0, y0, x1, y1 = L.summary
    c.setStrokeGray(FAINT)
    c.setLineWidth(0.8)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
    c.setFillGray(0.6)
    c.setFont(L.f.regular, 7 * L.hk)
    c.drawString(x0 + 5, y1 - 10 * L.hk, "Feedback summary")
    form = f" | form {L.label}" if L.label else ""
    c.drawCentredString(PAGE_W / 2, 32, L.f.text(f"{L.defn['assignment_id']}{form} | page {page_no} of {n_pages} | "
                                                 "please don't write in the corner squares"))


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


def _write_box(c: canvas.Canvas, f: F.Fonts, x0: float, y0: float, w: float, h: float, number=None) -> tuple:
    """An outlined box to write in, with a small number in its corner. Returns its rect."""
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(1)
    c.rect(x0, y0, w, h, stroke=1, fill=0)
    if number is not None:
        c.setFillGray(0.45)
        c.setFont(f.bold, 6.5)
        c.drawString(x0 + 2, y0 + h - 7, str(number))
    return (x0, y0, x0 + w, y0 + h)


def _primary_lines(c: canvas.Canvas, x0: float, x1: float, bottom: float, n: int, spacing: float) -> None:
    """Primary-ruled writing lines: solid top and base lines, dashed midline, room below for descenders."""
    c.setStrokeGray(FAINT)
    for k in range(n):
        base = bottom + k * spacing + spacing * 0.24
        top = base + spacing * 0.62
        c.setLineWidth(0.7)
        c.setDash()
        c.line(x0 + 6, base, x1 - 6, base)
        c.line(x0 + 6, top, x1 - 6, top)
        c.setLineWidth(0.6)
        c.setDash(3, 3)
        c.line(x0 + 6, (base + top) / 2, x1 - 6, (base + top) / 2)
    c.setDash()


def _draw_passage(c: canvas.Canvas, L: Layout, p: dict, start: int, end: int, y: float) -> None:
    st, f = L.st, L.f
    lines = L.passage_lines(p)
    top = y
    height = L.passage_height(p, start, end, len(lines))
    c.setStrokeGray(0.85 if p.get("note") else 0.75)
    c.setLineWidth(0.8)
    if p.get("note"):  # a version's note (key words, directions in a home language): set off, not a reading
        c.setDash(3, 2)
    c.rect(LEFT - 4, top - height, GUTTER_RIGHT - LEFT + 8, height, stroke=1, fill=0)
    c.setDash()
    y = top - 6
    size, leading = L.psize(p), L.plead(p)
    if p.get("qr"):  # a link for a phone camera, at the box's right
        _draw_qr(c, p["qr"], GUTTER_RIGHT - QR_SIZE - 2, top - QR_SIZE - 6)
    if start == 0 and p["title"]:
        c.setFillGray(INK)
        if not _rtl(p["title"]) and F.covers(f.bold, p["title"]):
            c.setFont(f.bold, size + 1)
            c.drawString(LEFT + 8, y - size, p["title"])
        else:  # a title in a script the page's font lacks
            title_font = L.lang_font(p["title"], p.get("lang", ""))[0]
            L.draw_line(c, L.wrap(p["title"], title_font, size + 1, 400)[0], LEFT + 8, GUTTER_RIGHT - 8,
                        y - size, title_font, size + 1)
        y -= size + 10
    elif start > 0:
        c.setFillGray(0.45)
        c.setFont(f.oblique, 7)
        c.drawRightString(GUTTER_RIGHT - 4, top + 3, f.text(f"{p['title'] or 'Passage'}, continued"))
    c.setFillGray(INK)
    font = L.passage_font(p)
    c.setFont(font, size)
    numbers = L.passage_numbers(p)
    every = max(1, int(p["number_every"]))
    for n in range(start, end):
        baseline = y - size
        if p.get("lang"):
            L.draw_line(c, lines[n], LEFT + 8, LEFT + 8 + L.passage_width(p), baseline, font, size,
                        _rtl(p["text"]))
        else:
            c.drawString(LEFT + 8, baseline, lines[n])
        if p["line_numbers"] and numbers[n] and numbers[n] % every == 0:
            c.setFont(f.regular, 7)
            c.setFillGray(0.4)
            c.drawRightString(LEFT - 8 if every > 1 else LEFT + 4, baseline + 1, str(numbers[n]))
            c.setFont(font, size)
            c.setFillGray(INK)
        y -= leading
    if end == len(lines) and p["source"]:
        c.setFillGray(0.35)
        c.setFont(f.oblique, 8)
        for k, line in enumerate(L.source_lines(p)):
            c.drawString(LEFT + 8, y - 10 - 12 * k, line)


def _draw_qr(c: canvas.Canvas, url: str, x: float, y: float) -> None:
    """A QR code (reportlab's own encoder, so nothing to install) with its bottom-left at (x, y)."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    widget = QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(QR_SIZE, QR_SIZE, transform=[QR_SIZE / (x1 - x0), 0, 0, QR_SIZE / (y1 - y0), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _draw_question(c: canvas.Canvas, L: Layout, q: dict, y: float, part: tuple | None = None,
                   part_no: int = 1, parts: int = 1) -> dict:
    """One question. An essay that runs onto more pages is drawn a part at a time: part is its (start, end)
    writing lines, and parts after the first get a "continued" line instead of the prompt."""
    st, f = L.st, L.f
    top = y
    lines = L.prompt_lines(q) if part_no == 1 else []
    c.setFillGray(INK)
    c.setFont(f.regular, st["prompt_size"])
    for n, line in enumerate(lines):
        c.drawString(LEFT, y - st["prompt_size"] - n * st["prompt_leading"], line)
    body_top = y - len(lines) * st["prompt_leading"] - st["prompt_gap"]
    if part_no == 1 and q.get("asides"):
        body_top = _draw_asides(c, L, q, y - len(lines) * st["prompt_leading"]) - st["prompt_gap"]
    if part_no > 1:
        c.setFillGray(0.35)
        c.setFont(f.oblique, 9)
        c.drawString(LEFT, y - 10, f.text(f"{q['q']}. continued (part {part_no} of {parts})"))
        body_top = y - CONTINUED_H
    bottom = y - L.question_height(q, part)
    right = BOX_RIGHT if part_no == 1 else GUTTER_RIGHT  # later parts of an essay get the full width
    box = {"q": q["q"], "type": q["type"], "rect": (LEFT, bottom, right, body_top),
           "feedback_rect": (GUTTER_LEFT, bottom, GUTTER_RIGHT, top), "prompt": q["prompt"],
           "points": q["points"] if part_no == 1 else 0, "lines": 0, "options": [], "labels": []}
    if parts > 1:
        box.update(part=part_no, parts=parts)

    if q["type"] == "short":
        n_lines = part[1] - part[0] if part else q["lines"]
        box["lines"] = n_lines
        box["line_spacing"] = st["line_spacing"]
        if st["primary"]:
            _primary_lines(c, LEFT, right, bottom, n_lines, st["line_spacing"])
        else:
            c.setStrokeGray(FAINT if L.k == 1 else 0.55)  # large print: lines a low-vision reader can see
            c.setLineWidth(0.6 if L.k == 1 else 1.0)
            for k in range(1, n_lines):
                ly = bottom + k * st["line_spacing"]
                c.line(LEFT + 6, ly, right - 6, ly)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(LEFT, bottom, right - LEFT, body_top - bottom, stroke=1, fill=0)
        if part_no == 1 and q.get("frame"):  # sentence starters, printed on the first writing lines
            c.setFillGray(0.3)  # upright and dark enough to read; still lighter than the student's pencil
            size = st["prompt_size"] * 0.95
            for k, frame in enumerate(q["frame"][:n_lines]):
                base_y = body_top - (k + 1) * st["line_spacing"] + (st["line_spacing"] * 0.24 if st["primary"] else 5)
                text = f.text(re.sub(r"_{3,}", "_" * 14, frame))
                fit = size  # a long starter shrinks to stay inside the box
                while fit > 7 and c.stringWidth(text, f.regular, fit) > right - LEFT - 16:
                    fit -= 0.5
                c.setFont(f.regular, fit)
                c.drawString(LEFT + 8, base_y, text)
            c.setFillGray(INK)

    elif q["type"] == "choice":
        columns, col_w, indent, option_lines = L.option_geometry(q)
        row_heights = L.option_rows(q)
        row_top = body_top
        for i, option in enumerate(q["options"]):
            row, col = divmod(i, columns)
            if col == 0 and row > 0:
                row_top -= row_heights[row - 1] + st["option_gap"]
            x = LEFT + col * col_w
            baseline = row_top - st["option_size"]
            c.setFillGray(INK)
            c.setFont(f.bold, st["option_size"] + 0.5)
            c.drawString(x + 10, baseline, f.text(option["letter"]))
            c.setFont(L.body_font(q), st["option_size"])
            for n, line in enumerate(option_lines[i]):
                c.drawString(x + indent, baseline - n * st["option_leading"], line)
            left = x - OPTION_REACH if col == 0 else x - 4
            right = x + col_w if columns == 1 else x + col_w - 4
            box["options"].append({
                "letter": option["letter"],
                "rect": (left, row_top - row_heights[row] - st["option_gap"] / 2, right,
                         row_top + st["option_gap"] / 2),
                "letter_at": (x + 10 + c.stringWidth(f.text(option["letter"]), f.bold, st["option_size"] + 0.5) / 2,
                              baseline + (5.0 if st["primary"] else 3.8) * L.k),
            })
        box["rect"] = (LEFT - OPTION_REACH, bottom - st["option_gap"] / 2, BOX_RIGHT, body_top + st["option_gap"] / 2)

    elif q["type"] == "label":
        diagram_top = _word_bank(c, L, q, body_top)
        ds = L.diagram_scale(q)
        x0, y0 = LEFT, diagram_top - q["diagram"]["height"] * ds
        _diagram_at(c, L, q, x0, y0, ds)
        for spot in q["labels"]:
            bx, by, bw, bh = (v * ds for v in spot["box"])
            _write_box(c, f, x0 + bx, y0 + by, bw, bh, spot["n"])
            if spot["points_to"]:
                _leader(c, (x0 + bx, y0 + by, bw, bh), (x0 + spot["points_to"][0] * ds, y0 + spot["points_to"][1] * ds))
            box["labels"].append({"n": spot["n"], "rect": (x0 + bx, y0 + by, x0 + bx + bw, y0 + by + bh)})
        box["rect"] = (x0, y0, x0 + q["diagram"]["width"] * ds, diagram_top)
        if ds != 1:
            box["scale"] = ds

    elif q["type"] == "draw":
        ds = L.diagram_scale(q)
        w, h = q["diagram"]["width"] * ds, q["diagram"]["height"] * ds
        x0, y0 = LEFT, body_top - h
        _diagram_at(c, L, q, x0, y0, ds)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(x0, y0, w, h, stroke=1, fill=0)
        box["rect"] = (x0, y0, x0 + w, body_top)
        if ds != 1:
            box["scale"] = ds
        if q.get("answer"):
            box["answer_rect"] = _answer_row(c, L, q, bottom)
            box["rect"] = (x0, bottom, max(x0 + w, box["answer_rect"][2]), body_top)

    elif q["type"] == "blanks":
        text_top = _word_bank(c, L, q, body_top)
        size, box_h = st["prompt_size"], L.box_h(q)
        y = text_top
        for line, line_h in zip(L.blank_flow(q), L.blank_heights(q)):
            y -= line_h
            row_bottom = y + 4
            baseline = row_bottom + (min(box_h, line_h - 8) - size * 0.72) / 2
            for kind, value, x, w in line:
                if kind == "word":
                    c.setFillGray(INK)
                    c.setFont(f.mono if q.get("mono") else f.regular, size)
                    c.drawString(LEFT + x, baseline, value)
                else:
                    rect = _write_box(c, f, LEFT + x, row_bottom, w, box_h, value)
                    box["labels"].append({"n": value, "rect": rect})
        box["labels"].sort(key=lambda s: s["n"])

    elif q["type"] == "match":
        box_w, left_w, item_lines, item_h, choice_lines, _ = L.match_geometry(q)
        size, leading = st["option_size"], st["option_leading"]
        y_item = body_top
        box_h = L.box_h(q)
        for item, text_lines, h in zip(q["items"], item_lines, item_h):
            rect = _write_box(c, f, LEFT, y_item - box_h - 3, box_w, box_h)
            box["labels"].append({"n": item["n"], "rect": rect, "name": item["name"]})
            c.setFillGray(INK)
            c.setFont(f.regular, size)
            for k, line in enumerate(text_lines):
                c.drawString(LEFT + box_w + 8, y_item - 3 - (box_h + size * 0.72) / 2 - k * leading, line)
            y_item -= h
        y_choice = body_top
        for text_lines in choice_lines:
            for k, line in enumerate(text_lines):
                c.setFont(f.bold if k == 0 else f.regular, size)
                letter, _, rest = line.partition(". ") if k == 0 else ("", "", line)
                x = LEFT + left_w + 8
                if k == 0:
                    c.drawString(x, y_choice - size - k * leading, letter + ".")
                    c.setFont(f.regular, size)
                    c.drawString(x + c.stringWidth(letter + ". ", f.bold, size), y_choice - size, rest)
                else:
                    c.drawString(x + 12, y_choice - size - k * leading, line)
            y_choice -= len(text_lines) * leading + 4

    elif q["type"] == "table":
        widths, header, header_h, cell_lines, heights = L.table_geometry(q)
        size = st["option_size"]
        x_edges = [LEFT]
        for w in widths:
            x_edges.append(x_edges[-1] + w)
        c.setFillGray(0.92)
        c.rect(LEFT, body_top - header_h, BOX_RIGHT - LEFT, header_h, stroke=0, fill=1)
        c.setFillGray(INK)
        for col, lines_ in enumerate(header):
            cx = (x_edges[col] + x_edges[col + 1]) / 2
            for k, line in enumerate(lines_):
                c.setFont(f.bold, size)
                c.drawCentredString(cx, body_top - 4 - size - k * (size + 2), line)
        y_row = body_top - header_h
        for row, lines_row, h in zip(q["rows"], cell_lines, heights):
            for col, cell in enumerate(row):
                x0, x1 = x_edges[col], x_edges[col + 1]
                if isinstance(cell, dict):
                    rect = (x0 + 3, y_row - h + 3, x1 - 3, y_row - 3)
                    c.setFillGray(0.45)
                    c.setFont(f.bold, 6.5)
                    c.drawString(x0 + 3, y_row - 9, str(cell["n"]))
                    box["labels"].append({"n": cell["n"], "rect": rect})
                else:
                    c.setFillGray(INK)
                    c.setFont(L.body_font(q), size)
                    block = len(lines_row[col]) * (size + 2)
                    for k, line in enumerate(lines_row[col]):
                        c.drawCentredString((x0 + x1) / 2, y_row - (h - block) / 2 - size - k * (size + 2) + 2, line)
            y_row -= h
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(LEFT, bottom, BOX_RIGHT - LEFT, body_top - bottom, stroke=1, fill=0)
        c.setLineWidth(0.6)
        for x in x_edges[1:-1]:
            c.line(x, bottom, x, body_top)
        y_line = body_top - header_h
        c.line(LEFT, y_line, BOX_RIGHT, y_line)
        for h in heights[:-1]:
            y_line -= h
            c.line(LEFT, y_line, BOX_RIGHT, y_line)
        box["labels"].sort(key=lambda s: s["n"])

    elif q["type"] == "math":
        work_h, answer_h = L.math_heights(q)
        work_bottom = body_top - work_h
        if q["grid"]:
            c.setStrokeGray(0.86)
            c.setLineWidth(0.4)
            step = 14.0
            gx = LEFT + step
            while gx < BOX_RIGHT - 1:
                c.line(gx, work_bottom, gx, body_top)
                gx += step
            gy = work_bottom + step
            while gy < body_top - 1:
                c.line(LEFT, gy, BOX_RIGHT, gy)
                gy += step
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(LEFT, work_bottom, BOX_RIGHT - LEFT, work_h, stroke=1, fill=0)
        c.setFillGray(FAINT)
        c.setFont(f.oblique, 7.5)
        c.drawString(LEFT + 4, body_top - 10, "Show your work")
        box["answer_rect"] = _answer_row(c, L, q, bottom)

    return box


def _diagram_at(c: canvas.Canvas, L: Layout, q: dict, x0: float, y0: float, ds: float) -> None:
    """A question's diagram with its bottom-left at (x0, y0), scaled for large print."""
    if ds == 1:
        D.draw_diagram(c, q["diagram"], x0, y0, L.f, L.base)
        return
    c.saveState()
    c.translate(x0, y0)
    c.scale(ds, ds)
    D.draw_diagram(c, q["diagram"], 0, 0, L.f, L.base)
    c.restoreState()


def _draw_asides(c: canvas.Canvas, L: Layout, q: dict, top: float) -> float:
    """A version's help under the prompt (a worked example, a hint, steps, key words, a word bank) and a
    home-language translation. Returns where the answer area can start."""
    y = top - 3
    for a in L.aside_lines(q):
        h = a["height"]
        if a["kind"] == "example":
            c.setFillGray(0.95)
            c.setStrokeGray(0.8)
            c.setLineWidth(0.6)
            c.rect(LEFT, y - h, BOX_RIGHT - LEFT, h, stroke=1, fill=1)
        elif a["kind"] == "translation":
            c.setStrokeGray(0.75)
            c.setLineWidth(1.5)
            x = BOX_RIGHT - 2 if any(_rtl(line) for line in a["lines"]) else LEFT + 2
            c.line(x, y - h + 3, x, y - 2)
        c.setFillGray(0.15 if a["kind"] != "translation" else INK)
        baseline = y - a["size"] - (4 if a["kind"] == "example" else 2)
        for k, line in enumerate(a["lines"]):
            bold = k == 0 and a["kind"] in ("steps", "words", "example")
            font = L.f.bold if bold else a["font"]
            if a["kind"] == "translation":
                L.draw_line(c, line, LEFT + 8, BOX_RIGHT - 8, baseline, font, a["size"], a["rtl"])
            else:
                c.setFont(font, a["size"])
                c.drawString(LEFT + (6 if a["kind"] == "example" else 0) + (8 if k and bold is False and
                                                                              a["kind"] in ("steps", "words", "example") else 0),
                             baseline, line)
            baseline -= a["leading"]
        y -= h + 3
    c.setFillGray(INK)
    return y


def _rtl(text: str) -> bool:
    from . import script as SC
    return SC.has_rtl(text)


def _answer_row(c: canvas.Canvas, L: Layout, q: dict, bottom: float) -> tuple:
    """"Answer:" and a box at the bottom right of a question, with units after it. Returns the box's rect."""
    st, f = L.st, L.f
    units_w = c.stringWidth(f.text(q["units"]), f.regular, st["prompt_size"]) + 6 if q["units"] else 0
    ax1 = BOX_RIGHT - units_w
    ax0 = ax1 - min(L.sized(q["answer_width"]), BOX_RIGHT - LEFT - units_w - 80)
    ay0 = bottom + 4
    rect = _write_box(c, f, ax0, ay0, ax1 - ax0, st["box_h"] + 4)
    baseline = ay0 + (st["box_h"] + 4 - st["prompt_size"] * 0.72) / 2
    c.setFillGray(INK)
    c.setFont(f.bold, st["prompt_size"])
    c.drawRightString(ax0 - 6, baseline, f.text(q.get("answer_label") or "Answer:"))
    if q["units"]:
        c.setFont(f.regular, st["prompt_size"])
        c.drawString(ax1 + 4, baseline, f.text(q["units"]))
    return rect


def _word_bank(c: canvas.Canvas, L: Layout, q: dict, top: float) -> float:
    """Draws the word bank if there is one; returns where the body continues."""
    if not q.get("word_bank"):
        return top
    st, f = L.st, L.f
    size = (9.5 if not st["primary"] else 13.0) * L.k
    c.setFillGray(INK)
    c.setFont(f.bold, size)
    c.drawString(LEFT, top - 12 * L.k, "Word bank:")
    c.setFont(f.regular, size)
    for k, line in enumerate(L.word_bank_lines(q)):
        c.drawString(LEFT + c.stringWidth("Word bank: ", f.bold, size) + 4, top - 12 * L.k - k * (st["word_bank_h"] - 4),
                     line)
    return top - L.word_bank_height(q)


# --- Key ------------------------------------------------------------------------------

def _key_item(q: dict, L: Layout) -> dict:
    item = {"q": q["q"], "type": q["type"], "prompt": q["prompt"], "points": q["points"], "key": "",
            "options": [], "answer": "", "labels": [], "word_bank": q.get("word_bank", []), "checklist": [],
            "diagram": "", "spelling": q.get("spelling", False), "passage": q.get("passage"),
            "passages": q.get("passages") or ([q["passage"]] if q.get("passage") else []),
            "notes": q.get("notes", ""), "skill": q.get("skill", "")}
    if q.get("asides") or q.get("frame"):  # what a version printed to help, for marking to know
        item.update(asides=q.get("asides", []), frame=q.get("frame", []))
    if q.get("scaffolded"):  # help printed here that changes what the question measures (forms.py)
        item["scaffolded"] = q["scaffolded"]
    if q.get("retry"):  # practice of the very same question: progress reports don't count it as new evidence
        item["retry"] = True
    kind = q["type"]
    if kind == "short":
        item.update(key=q["key"], rubric=q["rubric"])
    elif kind == "choice":
        item.update(options=q["options"], answer=q["answer"],
                    key=f"{q['answer']}: " + next(o["text"] for o in q["options"] if o["letter"] == q["answer"]))
    elif kind == "label":
        item.update(labels=q["labels"], diagram=q["diagram"]["description"],
                    key="; ".join(f"{s['n']}: {s['answer']}" for s in q["labels"]))
    elif kind == "draw":
        item.update(checklist=q["checklist"], diagram=q["diagram"]["description"],
                    key="; ".join(c["item"] for c in q["checklist"]))
        if q.get("answer"):
            item.update(answer=q["answer"], accept=q["accept"], units=q["units"], answer_points=q["answer_points"])
    elif kind == "blanks":
        item.update(labels=q["answers"], text=q["text"], key="; ".join(f"{a['n']}: {a['answer']}" for a in q["answers"]))
    elif kind == "match":
        item.update(labels=q["items"], choices=q["choices"],  # each item keeps its printed "name"
                    key="; ".join(f"{i['n']}: {i['answer']}" for i in q["items"]))
    elif kind == "table":
        labels = []
        for r, row in enumerate(q["rows"], start=1):
            row_name = next((c for c in row if isinstance(c, str) and c), "")
            for col, cell in zip(q["columns"], row):
                if isinstance(cell, dict):
                    where = f"row {r}" + (f" (\"{row_name}\")" if row_name else "") + f", column \"{col}\""
                    labels.append({**cell, "where": where})
        item.update(labels=labels, columns=q["columns"],
                    rows=[[c if isinstance(c, str) else f"[{c['n']}]" for c in row] for row in q["rows"]],
                    key="; ".join(f"{l['n']}: {l['answer']}" for l in labels))
    elif kind == "math":
        item.update(answer=q["answer"], accept=q["accept"], units=q["units"], key=q["key"],
                    answer_points=q["answer_points"], work_points=q["work_points"])
    return item


def design_problems(defn: dict) -> list[str]:
    """Things that print fine but will mark badly, and readings far above the grade."""
    from . import sources as SR
    problems = SR.level_problems(defn)
    words = comment_words(defn["grade"])
    for b in defn["questions"]:
        if b["type"] == "choice":
            for o in b["options"]:
                if len(o["why"].split()) > words:
                    problems.append(f"question {b['q']} option {o['letter']}: its \"why\" is {len(o['why'].split())} "
                                    f"words, but comments beside answers are {words} words at most")
        if b["type"] in ("draw", "label"):
            for s in b["diagram"]["shapes"]:
                if s.get("fill") is not None and s["fill"] < 0.7 and s["shape"] in ("rect", "circle", "polygon") \
                        and s.get("w", 0) * s.get("h", 0) + 3.14 * s.get("r", 0) ** 2 > 400:
                    problems.append(f"question {b['q']}: a {s['shape']} filled {s['fill']} is too dark for pencil to "
                                    "show on it; use 0.75 or lighter where students write or draw")
    return problems


def comment_words(grade: int) -> int:
    """Word limit for a comment beside an answer: two short sentences for grades 2-3, one for 4-8, and room
    to be specific for 9-12."""
    return 16 if grade <= 3 else 15 if grade <= 8 else 25


def strength_words(grade: int) -> int:
    return 14 if grade <= 3 else 20 if grade <= 8 else 30


_CITE = re.compile(r"\blines?\s+(\d+)(?:\s*(?:-|–|to|and)\s*(\d+))?", re.I)


def citation_problems(defn: dict, passages: list[dict]) -> list[str]:
    """Line numbers cited in questions, keys, and rubrics that the passage doesn't have."""
    if not passages:
        return []
    lengths = {p["id"]: max((n for n, _ in p["lines"] if n), default=0) for p in passages}
    problems = []
    for b in defn["questions"]:
        if b["type"] == "passage":
            continue
        most = lengths.get(b.get("passage")) or (next(iter(lengths.values())) if len(lengths) == 1 else max(lengths.values()))
        texts = [b.get("prompt", ""), b.get("key", ""), b.get("text", ""), b.get("notes", "")]
        texts += [c["criterion"] for c in b.get("rubric", [])] + [i["text"] for i in b.get("items", [])]
        for t in texts:
            for m in _CITE.finditer(t or ""):
                cited = [int(x) for x in m.groups() if x]
                if max(cited) > most:
                    problems.append(f"question {b['q']} cites {m.group(0)!r}, but the passage has {most} lines")
    return problems


# --- Making the worksheet ---------------------------------------------------------------

def _prepare_images(defn: dict, base: Path, out_dir: Path) -> None:
    """Copy each image beside the worksheet, in gray, lightened if pencil will go on top of it."""
    from PIL import Image
    n = 0
    for b in defn["questions"]:
        for s in b.get("diagram", {}).get("shapes", []):
            if s["shape"] != "image":
                continue
            src = Path(s["path"])
            src = src if src.is_absolute() else base / src
            if not src.exists():
                raise WorksheetError(f"question {b.get('q', '?')}: image {s['path']} not found")
            img = Image.open(src)
            if img.mode in ("RGBA", "LA", "P"):  # transparent parts become paper, not black
                img = img.convert("RGBA")
                paper = Image.new("RGBA", img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(paper, img)
            img = img.convert("L")
            if s["faint"]:
                img = img.point(lambda v: 205 + v * 50 // 255)
            n += 1
            (out_dir / "images").mkdir(exist_ok=True)
            name = f"images/q{b.get('q', 0)}-{n}.png"
            img.save(out_dir / name)
            s["path"] = name


def _draw_form(c: canvas.Canvas, L: Layout, code_id: str, form: dict, first_page: int, pdf: str) -> list[dict]:
    """Every page of one form onto the canvas. Returns their layouts, numbered from first_page."""
    defn = L.defn
    pages = L.paginate()
    parts = {}  # block index: how many pages an essay runs across
    for pieces in pages:
        for i, part in pieces:
            parts[i] = parts.get(i, 0) + 1
    seen = {}
    boxes_id = id_boxes(defn["id_digits"], defn["style"], L.k)
    page_layouts = []
    for page_no, pieces in enumerate(pages, start=1):
        code = page_code(code_id, page_no)
        for marker_id in MARKER_RECTS:
            _draw_marker(c, marker_id)
        _draw_code(c, code)
        _draw_header(c, L, page_no, len(pages), boxes_id)
        _draw_footer(c, L, page_no, len(pages))
        boxes, passages, y = [], [], L.content_top
        for i, part in pieces:
            b = defn["questions"][i]
            if b["type"] == "passage":
                _draw_passage(c, L, b, part[0], part[1], y)
                title_h = L.psize(b) + 10 if part[0] == 0 and b["title"] else 0.0
                if not b["note"]:
                    passages.append({"id": b["id"], "title": b["title"],  # where it printed, for slides
                                     "rect": (LEFT - 20, y - L.piece_height(i, part) - 2, GUTTER_RIGHT + 6, y + 6),
                                     "body_rect": (LEFT - 20, y - L.piece_height(i, part) - 2, GUTTER_RIGHT + 6,
                                                   y - 4 - title_h)})
            else:
                seen[i] = seen.get(i, 0) + 1
                boxes.append(_draw_question(c, L, b, y, part, seen[i], parts[i]))
            y -= L.piece_height(i, part) + L.st["block_gap"]
        # "qr" and "qr_rect" keep the layout readable by the Paper Loop CLI.
        page_layouts.append({"page": first_page + page_no - 1, "code": code, "qr": f"{code_id}|p{page_no}",
                             "qr_rect": CODE_AREA, "id_grid": None, "id_boxes": boxes_id,
                             "summary_rect": L.summary, "boxes": boxes, "passages": passages,
                             "form": form["id"], "form_page": page_no, "form_pages": len(pages), "pdf": pdf,
                             "pdf_page": c.getPageNumber(), **({"student_id": form["student_id"]}
                                                               if form.get("student_id") else {}),
                             **({"print_scale": L.k} if L.k != 1 else {})})
        c.showPage()
    return page_layouts


def _code_ids(assignment_id: str, forms: list[dict]) -> list[str]:
    """A page-code name for each form, all with different hashes, so a scan says which form it is."""
    taken, out = set(), []
    for form in forms:
        name = assignment_id if not form["id"] else f"{assignment_id}/{form['id']}"
        while assignment_hash(name) in taken:
            name += "~"
        taken.add(assignment_hash(name))
        out.append(name)
    return out


def _lang_problems(L: Layout, form: dict) -> list[str]:
    """Home-language text this machine can't print in a PDF: say what to do instead."""
    from . import script as SC
    texts = [a["text"] for q in L.defn["questions"] for a in q.get("asides", []) if a["kind"] == "translation"]
    texts += [b["text"] for b in L.defn["questions"] if b.get("lang")]
    problems = []
    for text in texts:
        scripts = SC.complex_scripts(text)
        how = L.lang_font(text, form.get("language") or "")[1]
        if scripts or how == "none":
            what = ", ".join(scripts) if scripts else "its script"
            problems.append(f"version {form['id']!r}: {form.get('language_name') or form.get('language')} text "
                            f"({what}) can't be printed correctly in a PDF here. Set \"language_mode\": "
                            "\"companion\": the worksheet stays in English and the translation goes on a Word page, "
                            "which Word and Google Docs print correctly")
            break
    return problems


def unlabeled(key: str) -> str:
    """A key without its own "Full credit:" label, for places that print the label already."""
    return re.sub(r"^\s*full credit(\s*\([^)]*\))?\s*:\s*", "", key, flags=re.I)  # not "Full credit for any two of:"


def make_worksheet(defn: dict, out_dir: Path, base: Path | None = None) -> dict:
    """Writes worksheet.pdf, layout.json, key.json, and worksheet.json, and each other form: versions in
    versions/, a different copy per student in copies.pdf. Returns the layout, with "unprintable" listing
    any characters that will print as "?"."""
    from . import forms as FM
    base = Path(base or ".")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("template-p*.png"):
        old.unlink()  # rendered again from the new PDFs when they're needed
    forms = []
    expanded = FM.expand(defn, base)
    for form, raw in expanded:
        try:
            forms.append((form, normalize(raw)))
        except WorksheetError as e:
            raise WorksheetError(f"{form['name']}: {e}" if form["id"] else str(e))
    _save_source(defn, expanded, base, out_dir)  # only once every form is good, so practice matches the key
    defn = forms[0][1]
    code_ids = _code_ids(defn["assignment_id"], [f for f, _ in forms])
    for _, d in forms:
        _prepare_images(d, base, out_dir)

    page_layouts, layouts, form_list, items_by_form, notes = [], {}, [], {}, []
    canvases: dict[str, canvas.Canvas] = {}
    for (form, d), code_id in zip(forms, code_ids):
        pdf = ("worksheet.pdf" if form["kind"] == "base" else "copies.pdf" if form["kind"] == "variant"
               else f"versions/{form['id']}.pdf")
        if pdf not in canvases:
            (out_dir / pdf).parent.mkdir(exist_ok=True)
            fonts_for_title = F.choose([d["title"]])[0]
            canvases[pdf] = canvas.Canvas(str(out_dir / pdf), pagesize=(PAGE_W, PAGE_H))
            canvases[pdf].setTitle(fonts_for_title.text(d["title"]))
            canvases[pdf].setAuthor("Paper Loop")
        fonts, ok = F.choose(all_texts(d))
        L = Layout(d, fonts, out_dir, form["label"], form.get("student_id", ""))
        problems = _lang_problems(L, form) if form.get("language") and form.get("language_mode") != "companion" else []
        if problems:
            raise WorksheetError(problems[0])
        if L.per_page:
            L.grow()
        first = len(page_layouts) + 1
        pages = _draw_form(canvases[pdf], L, code_id, form, first, pdf)
        page_layouts += pages
        layouts[form["id"]] = (L, ok)
        items = [_key_item(q, L) for q in d["questions"] if q["type"] != "passage"]
        items_by_form[form["id"]] = items
        entry = {k: v for k, v in form.items() if k != "translation"}
        fit = {}
        if form["kind"] == "version":  # what to cut when a version runs longer than everyone else's
            fit = {"shortfall": L.shortfall(), "free_by_page": L.free_by_page(),
                   "blocks_by_page": [[(_piece_name(d["questions"][i], part), L.piece_height(i, part))
                                       for i, part in piece] for piece in L.paginate()]}
        form_list.append({**entry, "code_id": code_id, "pdf": pdf, "pages": [p["page"] for p in pages],
                          "comment_language": d["comment_language"], **fit})
    for c in canvases.values():
        c.save()

    L, ok = layouts[""]
    base_items = items_by_form[""]
    for item in base_items:  # questions that differ from copy to copy: no literal answers to compare
        item["varies"] = any(_differs(item, next((i for i in other if i["q"] == item["q"]), item))
                             for fid, other in items_by_form.items() if fid and _kind(form_list, fid) == "variant")
    passages = [{"id": b["id"], "title": b["title"], "source": b["source"], "line_numbers": b["line_numbers"],
                 "lines": [[n, line] for n, line in zip(L.passage_numbers(b), L.passage_lines(b))]}
                for b in defn["questions"] if b["type"] == "passage" and not b["note"]]
    layout = {"assignment_id": defn["assignment_id"], "title": defn["title"], "page_size": (PAGE_W, PAGE_H),
              "markers": MARKER_RECTS, "style": defn["style"], "pages": page_layouts}
    if len(form_list) > 1:
        layout["forms"] = form_list
    key = {"assignment_id": defn["assignment_id"], "subject": defn["subject"], "grade_band": defn["grade_band"],
           "grade": defn["grade"], "id_digits": defn["id_digits"], "comment_words": comment_words(defn["grade"]),
           "strength_words": strength_words(defn["grade"]),
           "feedback": defn["feedback"], "comment_language": defn["comment_language"],
           "instructions": defn["instructions"], "passages": passages, "items": base_items}
    if len(form_list) > 1:
        key["forms"] = {f["id"]: {"name": f["name"], "label": f["label"], "kind": f["kind"],
                                  "comment_language": f["comment_language"],
                                  **{k: f[k] for k in ("language", "language_name", "language_english", "language_mode", "scaffolds",
                                                       "modifies")
                                     if f.get(k)},
                                  "items": items_by_form[f["id"]]} for f in form_list if f["id"]}
    write_json(out_dir / "layout.json", layout)
    write_json(out_dir / "key.json", key)
    write_json(out_dir / "worksheet.json", defn)
    for (form, d) in forms[1:]:
        if form["kind"] == "version":
            notes += _version_extras(form, d, out_dir, layouts[form["id"]][0])
    variants = [f for f in form_list if f["kind"] == "variant" and not f.get("student_id")]
    variant_notes = []
    if variants:
        variant_notes = _copies_key(defn, variants, items_by_form, out_dir)

    layout["defn"] = defn
    layout["forms_made"] = form_list
    layout["version_notes"] = notes
    layout["variant_notes"] = variant_notes
    layout["unprintable"] = "" if ok else F.unprintable(all_texts(defn))
    layout["passages"] = passages
    base_pages = [p for p in page_layouts if not p["form"]]
    layout["space_left"] = L.space_left()
    layout["shortfall"] = L.shortfall()
    layout["free_by_page"] = L.free_by_page()
    layout["blocks_by_page"] = [[(_piece_name(defn["questions"][i], part), L.piece_height(i, part)) for i, part in pieces]
                                for pieces in L.paginate()]
    layout["citation_problems"] = (citation_problems(defn, passages) + design_problems(defn)
                                   + _separated_passages(defn, L.paginate()))
    layout["teacher_notes"] = defn["teacher_notes"]
    layout["base_pages"] = len(base_pages)
    layout["licenses"] = sorted({b["license"] for b in defn["questions"] if b["type"] == "passage" and b["license"]})
    return layout


def _save_source(defn: dict, expanded: list, base: Path, out_dir: Path) -> None:
    """The worksheet as written, with its translations and pictures inside the folder, so practice sheets
    can be made from it later (practice.py) wherever the folder goes."""
    import copy
    import shutil
    source = copy.deepcopy(defn)
    translations = dict(source.get("translations") or {})
    for form, _ in expanded:
        if form.get("translation"):
            translations[form["language"]] = form["translation"]
    if translations:
        source["translations"] = translations
    pictures = out_dir / "source-images"
    shutil.rmtree(pictures, ignore_errors=True)

    def walk(node):
        if isinstance(node, dict):
            if node.get("shape") == "image" and node.get("path"):
                src = Path(node["path"]) if Path(node["path"]).is_absolute() else base / node["path"]
                if src.exists():
                    pictures.mkdir(exist_ok=True)
                    shutil.copy(src, pictures / src.name)
                    node["path"] = f"source-images/{src.name}"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(source)
    write_json(out_dir / "source.json", source)


def _answers(item: dict) -> list[tuple[str, str]]:
    """(where, answer) for each thing a question is marked on, in words, for a printed key."""
    kind = item["type"]
    if kind == "choice":
        text = next((o["text"] for o in item["options"] if o["letter"] == item["answer"]), "")
        return [("", f"{item['answer']} ({text})")]
    if kind in ("label", "blanks", "match", "table"):
        return [(f"{s['n']}", s["answer"]) for s in item["labels"]]
    if kind == "math" or (kind == "draw" and item.get("answer")):
        return [("", item["answer"] + (f" {item['units']}" if item.get("units") else ""))]
    if kind == "draw":
        return [("", "see the checklist")]
    return [("", item["key"])]


def _copies_key(defn: dict, variants: list[dict], items_by_form: dict, out_dir: Path) -> list[str]:
    """copies-key.pdf: every copy's answers, for checking a copy by hand. Returns problems worth a look:
    an answer that's the same on most copies doesn't stop copying."""
    fonts, _ = F.choose([str(a) for f in variants for item in items_by_form[f["id"]] for _, a in _answers(item)])
    c = canvas.Canvas(str(out_dir / "copies-key.pdf"), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(fonts.text(f"{defn['title']}: every copy's answers"))
    y = PAGE_H - 54

    def line(text: str, font: str, size: float, x: float = 54) -> None:
        nonlocal y
        for part in simpleSplit(fonts.text(text), font, size, PAGE_W - x - 54) or [""]:
            if y < 54:
                c.showPage()
                y = PAGE_H - 54
            c.setFont(font, size)
            c.drawString(x, y, part)
            y -= size + 3

    line(f"{defn['title']}: every copy's answers", fonts.bold, 14)
    line("The copy number is in each sheet's footer (\"form 7\").", fonts.oblique, 9)
    y -= 6
    seen: dict[tuple[int, str], list[str]] = {}
    for f in variants:
        line(f"Copy {f['label']}", fonts.bold, 11)
        for item in items_by_form[f["id"]]:
            answers = _answers(item)
            for where, answer in answers:
                seen.setdefault((item["q"], where), []).append(answer)
            shown = "; ".join(f"{w}: {a}" if w else a for w, a in answers)
            line(f"Q{item['q']}: {shown}", fonts.regular, 9.5, 66)
        y -= 4
    c.save()
    problems = []
    for (q, where), answers in seen.items():
        if not answers or answers[0] == "see the checklist":
            continue
        most = max(set(answers), key=answers.count)
        if answers.count(most) > len(answers) / 2 and len(answers) > 2:
            spot = f"Q{q}" + (f" box {where}" if where else "")
            problems.append(f"{spot} has the same answer ({most}) on {answers.count(most)} of {len(answers)} copies, "
                            "so neighbors can still share it: let more of the question vary")
    return problems


def _kind(form_list: list[dict], fid: str) -> str:
    return next(f["kind"] for f in form_list if f["id"] == fid)


def _differs(a: dict, b: dict) -> bool:
    fields = ("prompt", "answer", "accept", "key", "labels", "options", "text", "rows", "checklist")
    return any(json.dumps(a.get(k), sort_keys=True) != json.dumps(b.get(k), sort_keys=True) for k in fields)


def _version_extras(form: dict, defn: dict, out_dir: Path, L: Layout) -> list[str]:
    """A version's companion page (its home language, for Word) and reference page; notes for the teacher."""
    from . import forms as FM
    notes = []
    if form.get("language") and form.get("translation"):
        path = FM.companion(form, defn, out_dir)
        notes.append(f"{form['name']}: {form['language_name']} page {path.relative_to(out_dir)} (print from Word or "
                     f"Google Docs{'; it goes with the English sheet' if form['language_mode'] == 'companion' else ''})")
    if form.get("reference"):
        path = FM.reference_pages(form, defn, out_dir, L)
        notes.append(f"{form['name']}: reference page {path.relative_to(out_dir)} (students keep it; it isn't "
                     "handed in or scanned)")
    if form.get("notes"):
        notes.append(f"{form['name']}: {form['notes']}")
    return notes


def _piece_name(b: dict, part) -> str:
    if b["type"] == "passage":
        return b["title"] or b["id"]
    return f"Q{b['q']}" + (" continued" if part and part[0] > 0 else "")


def _separated_passages(defn: dict, pages: list[list[tuple]]) -> list[str]:
    """A passage that ends on one page while its first question starts on a later one."""
    page_of = {}
    for n, pieces in enumerate(pages, start=1):
        for i, _ in pieces:
            page_of.setdefault(i, []).append(n)
    out = []
    for i, b in enumerate(defn["questions"]):
        if b["type"] != "passage":
            continue
        users = [j for j, q in enumerate(defn["questions"]) if q["type"] != "passage" and q.get("passage") == b["id"]]
        if users and page_of[users[0]][0] > page_of[i][-1]:
            first = defn["questions"][users[0]]
            out.append(f"{b['title'] or b['id']} ends on page {page_of[i][-1]}, but its first question (Q{first['q']}) "
                       f"starts on page {page_of[users[0]][0]}; shorten something so they share a page")
    return out


def form_pages(layout: dict, form: str = "") -> list[dict]:
    """One form's pages (the worksheet as written, by default). Older layouts have only that form."""
    return [p for p in layout["pages"] if p.get("form", "") == form]


def form_items(key: dict, form: str = "") -> dict[int, dict]:
    """One form's answer key, by question number. A version or a student's copy may print a question
    differently (other numbers, fewer choices, a translation), so marking reads the key for its form."""
    items = key["forms"][form]["items"] if form and form in key.get("forms", {}) else key["items"]
    return {item["q"]: item for item in items}


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path):
    return json.loads(Path(path).read_text())
