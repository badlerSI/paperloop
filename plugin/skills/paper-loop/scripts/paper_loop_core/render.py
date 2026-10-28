"""Stamp feedback on the scanned pages; one PDF sorted by student ID.

Each returned page is the lined-up scan with a comment beside each answer, in the gutter the template left
empty, and a check or cross on the student's own work: beside each box they wrote in, on a math answer box,
and on each drawing checklist line. Each student gets one summary, on their last page. Pages that couldn't
be read go to a review pile.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from . import fonts as F
from . import sheet as S

COMMENT_SIZE, COMMENT_LEADING = 10.0, 12.0
SUMMARY_SIZE, SUMMARY_LEADING = 9.5, 11.5
CHECK_SIZE, CHECK_LEADING = 8.5, 10.5
BOXES = {"label", "blanks", "match", "table"}
PEN = (0.1, 0.1, 0.45)  # dark blue; prints as near-black on a mono copier
WASH_ALPHA = 0.85  # students doodle in the margin: fade it behind each line of feedback, don't hide it
_MARK_KIND = {"yes": "check", "correct": "check", "no": "cross", "incorrect": "cross",
              "unclear": "query", "unreadable": "query"}


class Pen:
    """Fonts and sizes for one rendering. Grades 2-3 get upright print as big as the questions (slanted
    letters are harder for early readers); older grades get italic, which sets comments apart from print."""

    def __init__(self, fonts: F.Fonts, primary: bool, grade: int, scale: float = 1.0):
        self.f, self.primary, self.grade = fonts, primary, grade
        self.label_scale = min(scale, S.HEADER_GROWTH)  # the page's printed labels grew this much (sheet.py)
        self.comment = fonts.regular if primary else fonts.oblique
        self.size = min(16.0, (13.0 if primary else COMMENT_SIZE) * scale)  # large print: comments grow too
        self.leading = self.size * COMMENT_LEADING / COMMENT_SIZE


def _draw_mark(c: canvas.Canvas, state: str, x: float, y: float, size: float) -> bool:
    """A check, a cross, or a ? (for "a teacher should look"), drawn as strokes so it prints the same in
    every viewer. Partial and blank get no mark: a half or a dash on a child's page reads as a mistake."""
    kind = _MARK_KIND.get(state)
    if kind is None:
        return False
    c.setStrokeColorRGB(*PEN)
    c.setLineWidth(max(1.2, size / 6))
    c.setLineCap(1)
    c.setLineJoin(1)
    if kind == "check":
        p = c.beginPath()
        p.moveTo(x, y + 0.45 * size)
        p.lineTo(x + 0.35 * size, y + 0.05 * size)
        p.lineTo(x + size, y + 0.9 * size)
        c.drawPath(p, stroke=1, fill=0)
    elif kind == "cross":
        c.line(x + 0.1 * size, y + 0.05 * size, x + 0.8 * size, y + 0.75 * size)
        c.line(x + 0.1 * size, y + 0.75 * size, x + 0.8 * size, y + 0.05 * size)
    else:
        c.setFillColorRGB(*PEN)
        c.setFont("Helvetica-Bold", size + 1)
        c.drawString(x + 0.1 * size, y, "?")
    return True


def _wash(c: canvas.Canvas, left: float, right: float, baseline: float, size: float, leading: float) -> None:
    """A white band behind one line of text. Bands of adjacent lines meet without overlapping."""
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.setFillAlpha(WASH_ALPHA)
    c.rect(left, baseline + 0.255 * size - leading / 2, right - left, leading, stroke=0, fill=1)
    c.restoreState()


def _mark_on(c: canvas.Canvas, rect, state: str, size: float = 8.0) -> None:
    """A mark in the top-right corner of a box the student wrote in, on a small white patch."""
    x0, y0, x1, y1 = rect
    if _MARK_KIND.get(state) is None:
        return
    x, y = x1 - size - 2, y1 - size - 1.5
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.setFillAlpha(WASH_ALPHA)
    c.rect(x - 1.5, y - 1.5, size + 3, size + 3, stroke=0, fill=1)
    c.restoreState()
    _draw_mark(c, state, x, y, size)


def _split(text: str, font: str, size: float, width: float, f: F.Fonts) -> tuple[list[str], str, bool]:
    """(lines, font, right to left) for text in any language: the pen's own font when it can print it,
    else Arabic script shaped, or a font for the text's script."""
    from . import script as SC
    from . import sheet as S
    if not SC.has_rtl(text) and (F.covers(font, text) or not f.unicode and not F.needs_unicode([text])):
        return simpleSplit(f.text(text), font, size, width), font, False
    shaped = SC.shape(text, lambda ch: F.covers(f.regular, ch))
    use, _ = F.font_for(shaped, f)
    return S.wrap_text(text, use, size, width), use, SC.has_rtl(text)


def _directions(lines: list[str], rtl: bool) -> list[bool]:
    """Which lines read right to left. The text's first letter sets its direction (Unicode's rule): text that
    starts in Arabic reads right to left throughout. A comment in English and then Arabic keeps its English and
    mixed lines flush left, in their own order, and sets only its lines wholly in Arabic flush right."""
    from . import script as SC
    if not rtl:
        return [False] * len(lines)
    if SC.rtl_line(" ".join(lines)):
        return [True] * len(lines)
    return [SC.has_rtl(line) and not any(ch.isalpha() and not SC.is_arabic(ch) for ch in line) for line in lines]


def _put(c: canvas.Canvas, line: str, x: float, right: float, y: float, font: str, size: float, rtl: bool) -> float:
    """Draw one line, flush right in display order when it reads right to left. Returns where its ink starts."""
    from . import script as SC
    c.setFont(font, size)
    if SC.has_rtl(line):
        line = SC.visual(line, rtl)
    if rtl:
        x = right - c.stringWidth(line, font, size)
    c.drawString(x, y, line)
    return x


def _draw_comment(c: canvas.Canvas, pen: Pen, rect, verdict: str, comment: str,
                  checks: list[tuple[str | None, str]]) -> None:
    """Comment at the top of the gutter, then one line per drawing checklist item or rubric criterion, with
    a thin bar down the left so feedback stands out from the printing on a black-and-white copy."""
    x0, y0, x1, y1 = rect
    f = pen.f
    font = pen.comment
    x = x0 + 6 + (16 if verdict == "correct" else 0)
    # On a packed page the space beside a question can be short: shrink the comment to fit it
    # (with the checklist lines below it), and trim only as a last resort.
    width = x1 - x0 - 22
    wrapped = [simpleSplit(f.text(text), f.regular, CHECK_SIZE, width) or [""] for _, text in checks]
    if sum(map(len, wrapped)) * CHECK_LEADING > (y1 - y0) * 0.6:  # short of room: one line per mark, trimmed
        wrapped = [[w[0] if len(w) == 1 else w[0].rstrip(" .,;") + "…"] for w in wrapped]
    room = (y1 - y0) + 6 - sum(map(len, wrapped)) * CHECK_LEADING - (4 if checks else 0)
    for size in (pen.size, pen.size - 1, 9.0, 8.0):
        leading = size * COMMENT_LEADING / COMMENT_SIZE
        lines, use, rtl = _split(comment, font, size, x1 - x - 2, f)
        if len(lines) * leading <= room:
            break
    else:
        keep = max(1, int(room // leading))
        if len(lines) > keep:
            lines = lines[:keep]
            lines[-1] = lines[-1].rstrip(" .,;") + "…"
    top = y1
    y = y1 - size - 2
    for n, line in enumerate(lines):
        _wash(c, x0 + 3 if n == 0 else x - 2, x1 - 2 if rtl else x + c.stringWidth(line, use, size) + 2,
              y - n * leading, size, leading)
    if verdict == "correct":
        _draw_mark(c, "correct", x0 + 6, y - 1, 10)
    c.setFillColorRGB(*PEN)
    for line, right_to_left in zip(lines, _directions(lines, rtl)):
        _put(c, line, x, x1 - 4, y, use, size, right_to_left)
        y -= leading
    if checks:
        y -= 4
    for (state, _), lines_ in zip(checks, wrapped):
        for n, line in enumerate(lines_):
            _wash(c, x0 + 3 if n == 0 else x0 + 16, x0 + 20 + c.stringWidth(line, f.regular, CHECK_SIZE),
                  y - n * CHECK_LEADING, CHECK_SIZE, CHECK_LEADING)
        if state:
            _draw_mark(c, state, x0 + 6, y - 1, CHECK_SIZE)
        c.setFillColorRGB(*PEN)
        c.setFont(f.regular, CHECK_SIZE)
        for line in lines_:
            c.drawString(x0 + 18, y, line)
            y -= CHECK_LEADING
    bottom = y + (CHECK_LEADING if checks else leading) - 3
    c.setStrokeColorRGB(*PEN)
    c.setLineWidth(1.4)
    c.line(x0 + 1, top - 1, x0 + 1, max(bottom, y0))


def _draw_above(c: canvas.Canvas, pen: Pen, box: dict, verdict: str, comment: str,
                checks: list[tuple[str | None, str]]) -> None:
    """A comment for an essay whose first page isn't in the scan, on its later page: the writing fills that
    page's width, so the comment goes in the strip above it, beside "continued", on two lines at most, with any
    rubric scores at its end."""
    f = pen.f
    _, _, x1, body_top = box["rect"]
    top = box["feedback_rect"][3]
    label = f.text(f"{box['q']}. continued (part {box.get('part')} of {box.get('parts')})")
    x0 = S.LEFT + c.stringWidth(label, f.oblique, 9) + 12  # where sheet.py's "continued" line ends
    x = x0 + 6 + (16 if verdict == "correct" else 0)
    text = " ".join(filter(None, [comment, "; ".join(t for _, t in checks)]))
    room = top + 6 - body_top  # up to the rule under the header, down to the box
    for size in (pen.size, pen.size - 1, 9.0, 8.0, 7.0):
        leading = size * COMMENT_LEADING / COMMENT_SIZE
        lines, use, rtl = _split(text, pen.comment, size, x1 - x - 2, f)
        if size + 0.25 * size + (len(lines) - 1) * leading <= room - 2 and len(lines) <= 2:
            break
    else:
        lines = lines[:max(1, int((room - 2 - 1.25 * size) // leading) + 1)]
        lines[-1] = lines[-1].rstrip(" .,;") + "…"
    y = top + 6 - size
    for n, line in enumerate(lines):
        _wash(c, x0 + 3 if n == 0 else x - 2, x1 - 2 if rtl else x + c.stringWidth(line, use, size) + 2,
              y - n * leading, size, leading)
    if verdict == "correct":
        _draw_mark(c, "correct", x0 + 6, y - 1, 10)
    c.setFillColorRGB(*PEN)
    for n, (line, right_to_left) in enumerate(zip(lines, _directions(lines, rtl))):
        _put(c, line, x, x1 - 4, y - n * leading, use, size, right_to_left)
    c.setStrokeColorRGB(*PEN)
    c.setLineWidth(1.4)
    c.line(x0 + 1, top + 6, x0 + 1, body_top + 2)


def _gutter_lines(result: dict, pen: Pen) -> list[tuple[str | None, str]]:
    """The lines under a comment: drawing checklist items with their marks, and rubric scores (from grade
    6; younger students get the comment alone). Boxes and math answers are marked on the work instead."""
    kind, details = result["type"], result["details"]
    if kind == "draw":
        return [(d["met"], d["item"]) for d in details if "met" in d]
    if kind == "short" and details and "criterion" in details[0] and pen.grade >= 6:
        return [(None, f"{d['criterion']}: {d['level']}/{d['max']}") for d in details]
    return []


def _marks_on_work(c: canvas.Canvas, box: dict, result: dict) -> None:
    kind, details = result["type"], result["details"]
    if kind in BOXES:
        verdicts = {d["n"]: d["verdict"] for d in details}
        for spot in box["labels"]:
            _mark_on(c, spot["rect"], verdicts.get(spot["n"], "blank"))
    elif box.get("answer_rect"):
        answer = next((d for d in details if d.get("part") == "answer"), None)
        if answer:
            _mark_on(c, box["answer_rect"], answer["verdict"], 10)


def _draw_summary(c: canvas.Canvas, pen: Pen, rect, summary: dict | None, score: str | None,
                  last_page: int | None) -> None:
    x0, y0, x1, y1 = rect
    f = pen.f
    hk = pen.label_scale  # large print: the placeholder label is bigger, and so is the student's summary
    # Cover the printed placeholder label, then write the heading and the summary.
    c.setFillGray(1)
    c.rect(x0 + 1, y1 - 12.5 * hk, 200 * hk, 12.5 * hk - 1, stroke=0, fill=1)
    c.setFillColorRGB(*PEN)
    if summary is None:  # not this student's last page: say where the summary is
        c.setFont(f.oblique, 8 * hk)
        c.drawString(x0 + 5, y1 - 10 * hk, f"Your feedback summary is on page {last_page}.")
        return
    if score:
        c.setFont("Helvetica-Bold", 12 * hk)
        c.drawRightString(x1 - 6, y1 - 15 * hk, f.text(score))
    fixes = summary.get("fixes", [])
    entries = [("Strength:", summary["strength"])] if summary.get("strength") else []
    entries += [("Next step:" if len(fixes) == 1 else f"Next step {n}:", fix) for n, fix in enumerate(fixes, 1)]
    left, right = x0 + 5, x1 - 6 - (90 * hk if score else 0)
    # As big as the student's print, smaller only if that's what fits the box (and trimmed as a last resort).
    biggest = (SUMMARY_SIZE + (2.5 if pen.primary else 0)) * hk
    for size in sorted({biggest, *(s for s in (SUMMARY_SIZE + 2.5, SUMMARY_SIZE, 8.5, 7.5) if s < biggest)},
                       reverse=True):
        leading = size * SUMMARY_LEADING / SUMMARY_SIZE
        top = y1 - 3.5 - size  # under the "Feedback" heading
        laid = []
        for label, text in entries:
            indent = c.stringWidth(label + " ", f.bold, size)
            laid.append((label, indent, *_split(text, f.regular, size, right - left - indent, f)))
        if top - size - (sum(len(lines) for *_, lines, _, _ in laid) - 1) * leading >= y0 + 3:
            break
    c.setFont(f.bold, size + 0.5)
    c.drawString(x0 + 5, y1 - 1.5 - size, "Feedback")
    y = top - size
    for label, indent, lines, use, rtl in laid:
        for n, (line, right_to_left) in enumerate(zip(lines, _directions(lines, rtl))):
            if y < y0 + 3:
                return
            _wash(c, left - 2 if n == 0 else left + indent - 2,
                  right + 2 if rtl else left + indent + c.stringWidth(line, use, size) + 2, y, size, leading)
            c.setFillColorRGB(*PEN)
            if n == 0:
                c.setFont(f.bold, size)
                c.drawString(left, y, label)
            _put(c, line, left + indent, right, y, use, size, right_to_left)
            y -= leading


def _jpeg(png: Path, out_dir: Path) -> str:
    """The page as a grayscale JPEG: about a tenth the size of the PNG, and plenty for a copier."""
    from PIL import Image
    jpg = out_dir / "pages" / (png.stem + ".jpg")
    jpg.parent.mkdir(exist_ok=True)
    Image.open(png).convert("L").save(jpg, quality=80, optimize=True)
    return str(jpg)


def render(work: Path, pages: list[dict], summary_by_student: dict, grade: str = "off") -> dict:
    """returned.pdf (and review_pile.pdf, grades.csv) in work/out. `grade` is off, back, or csv."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    layout = S.read_json(Path(manifest["assignment_dir"]) / "layout.json")
    key = S.read_json(Path(manifest["assignment_dir"]) / "key.json")
    layout_pages = {p["page"]: p for p in layout["pages"]}
    images = {p["scan_index"]: work / p["image"] for p in manifest["pages"] if p["image"]}
    out_dir = work / "out"
    out_dir.mkdir(exist_ok=True)
    by_student: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        by_student[page["student_id"]].append(page)

    texts = [b["comment"] for p in pages for b in p["boxes"]] + [
        t for s in summary_by_student.values() for t in [s.get("strength", ""), *s.get("fixes", [])]]
    fonts, _ = F.choose(texts + [d.get("item", "") for p in pages for b in p["boxes"] for d in b["details"]])
    pens: dict[float, Pen] = {}
    returned = out_dir / "returned.pdf"
    c = canvas.Canvas(str(returned), pagesize=(S.PAGE_W, S.PAGE_H))
    c.setTitle(f"{manifest['assignment_id']}: marked")
    sheets, totals = 0, {}
    missing = {}
    forms_of = {sid: layout_pages[min(p["page"] for p in got)].get("form", "") for sid, got in by_student.items()}
    # Double-sided when any student's copy has two pages or more: then every student starts on a new sheet, so
    # no one's page prints on the back of a classmate's (a large-print version, practice sheets of any length).
    double_sided = any(len(S.form_pages(layout, form)) > 1 for form in forms_of.values())
    for student_id in sorted(by_student):
        student_pages = sorted(by_student[student_id], key=lambda p: p["page"])
        form_pages = S.form_pages(layout, forms_of[student_id])
        earned = sum(b["points_awarded"] for p in student_pages for b in p["boxes"])
        possible = sum(b["points"] for p in form_pages for b in p["boxes"])  # even if a page is missing
        absent = sorted({p.get("form_page", p["page"]) for p in form_pages}
                        - {layout_pages[p["page"]].get("form_page", p["page"]) for p in student_pages})
        if absent:
            missing[student_id] = absent
        totals[student_id] = (earned, possible)
        last_page = layout_pages[student_pages[-1]["page"]].get("form_page", student_pages[-1]["page"])
        for page in student_pages:
            page_layout = layout_pages[page["page"]]
            k = page_layout.get("print_scale", 1.0)
            pen = pens.setdefault(k, Pen(fonts, layout.get("style") == "primary", int(key.get("grade", 7)), k))
            c.drawImage(_jpeg(images[page["scan_index"]], out_dir), 0, 0, S.PAGE_W, S.PAGE_H)
            results = {b["q"]: b for b in page["boxes"]}
            for box in page_layout["boxes"]:
                result = results.get(box["q"])
                if result is None:
                    continue  # an essay's later page: its comment is beside the first page of it
                if result["verdict"] != "blank":
                    _marks_on_work(c, box, result)
                lines = [] if result["verdict"] == "blank" else _gutter_lines(result, pen)
                if not (result["comment"] or result["verdict"] == "correct" or lines):
                    continue
                if box.get("part", 1) > 1:  # an essay whose first page is missing: its writing fills this page's width
                    _draw_above(c, pen, box, result["verdict"], result["comment"], lines)
                else:
                    _draw_comment(c, pen, box["feedback_rect"], result["verdict"], result["comment"], lines)
            last = page is student_pages[-1]
            score = f"Score: {earned:g} / {possible}" if grade == "back" and last else None
            _draw_summary(c, pen, page_layout["summary_rect"], summary_by_student.get(student_id, {}) if last else None,
                          score, last_page)
            c.showPage()
            sheets += 1
        if double_sided and len(student_pages) % 2:
            c.showPage()  # blank back, so each student starts on a new sheet when printed double-sided
            sheets += 1
    c.save()
    out = {"returned": returned, "sheets": sheets, "students": len(by_student), "double_sided": double_sided,
           "missing": missing}

    if grade == "csv":
        # A column for each question a student here had: the worksheet's in order, then any only some copies have
        # (the stretch questions on practice sheets).
        had = {b["q"] for form in set(forms_of.values()) for p in S.form_pages(layout, form) for b in p["boxes"]}
        base = [b["q"] for p in S.form_pages(layout) for b in p["boxes"] if b.get("part", 1) == 1]
        questions = [q for q in base if q in had] + sorted(had - set(base))
        out["grades"] = out_dir / "grades.csv"
        with out["grades"].open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["student_id", *[f"q{q}" for q in questions], "total", "possible"])
            for student_id in sorted(by_student):
                points = {b["q"]: b["points_awarded"] for p in by_student[student_id] for b in p["boxes"]}
                earned, possible = totals[student_id]
                writer.writerow([student_id, *[f"{points[q]:g}" if q in points else "" for q in questions],
                                 f"{earned:g}", possible])

    pile = [p for p in manifest["pages"] if p["status"] == "review"]
    if pile:
        out["review_pile"] = out_dir / "review_pile.pdf"
        c = canvas.Canvas(str(out["review_pile"]), pagesize=(S.PAGE_W, S.PAGE_H))
        for p in pile:
            image = next((work / f for f in (p["raw_image"], p["image"]) if f and (work / f).exists()), None)
            if image:
                c.drawImage(str(image), 36, 36, S.PAGE_W - 72, S.PAGE_H - 96, preserveAspectRatio=True)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(36, S.PAGE_H - 40, F.HELVETICA.text(f"Review pile, scan page {p['scan_index']}: {p['reason']}"))
            c.showPage()
        c.save()
    return out
