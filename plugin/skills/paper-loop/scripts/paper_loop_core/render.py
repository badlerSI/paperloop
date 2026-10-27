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

    def __init__(self, fonts: F.Fonts, primary: bool, grade: int):
        self.f, self.primary, self.grade = fonts, primary, grade
        self.comment = fonts.regular if primary else fonts.oblique
        self.size = 13.0 if primary else COMMENT_SIZE
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
        lines = simpleSplit(f.text(comment), font, size, x1 - x - 2)
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
        _wash(c, x0 + 3 if n == 0 else x - 2, x + c.stringWidth(line, font, size) + 2,
              y - n * leading, size, leading)
    if verdict == "correct":
        _draw_mark(c, "correct", x0 + 6, y - 1, 10)
    c.setFillColorRGB(*PEN)
    c.setFont(font, size)
    for line in lines:
        c.drawString(x, y, line)
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
    # Cover the printed placeholder label, then write the heading and the summary.
    c.setFillGray(1)
    c.rect(x0 + 1, y1 - 12, 200, 11, stroke=0, fill=1)
    c.setFillColorRGB(*PEN)
    if summary is None:  # not this student's last page: say where the summary is
        c.setFont(f.oblique, 8)
        c.drawString(x0 + 5, y1 - 10, f"Your feedback summary is on page {last_page}.")
        return
    c.setFont(f.bold, SUMMARY_SIZE + 0.5)
    c.drawString(x0 + 5, y1 - 11, "Feedback")
    if score:
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(x1 - 6, y1 - 15, f.text(score))
    fixes = summary.get("fixes", [])
    entries = [("Strength:", summary["strength"])] if summary.get("strength") else []
    entries += [("Next step:" if len(fixes) == 1 else f"Next step {n}:", fix) for n, fix in enumerate(fixes, 1)]
    size = SUMMARY_SIZE + (2.5 if pen.primary else 0)
    leading = size * SUMMARY_LEADING / SUMMARY_SIZE
    left, right = x0 + 5, x1 - 6 - (90 if score else 0)
    y = y1 - 13 - size
    for label, text in entries:
        indent = c.stringWidth(label + " ", f.bold, size)
        for n, line in enumerate(simpleSplit(f.text(text), f.regular, size, right - left - indent)):
            if y < y0 + 3:
                return
            _wash(c, left - 2 if n == 0 else left + indent - 2,
                  left + indent + c.stringWidth(line, f.regular, size) + 2, y, size, leading)
            c.setFillColorRGB(*PEN)
            if n == 0:
                c.setFont(f.bold, size)
                c.drawString(left, y, label)
            c.setFont(f.regular, size)
            c.drawString(left + indent, y, line)
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
    pen = Pen(fonts, layout.get("style") == "primary", int(key.get("grade", 7)))
    returned = out_dir / "returned.pdf"
    c = canvas.Canvas(str(returned), pagesize=(S.PAGE_W, S.PAGE_H))
    c.setTitle(f"{manifest['assignment_id']}: marked")
    sheets, totals = 0, {}
    whole = sum(b["points"] for p in layout["pages"] for b in p["boxes"])
    missing = {}
    for student_id in sorted(by_student):
        student_pages = sorted(by_student[student_id], key=lambda p: p["page"])
        earned = sum(b["points_awarded"] for p in student_pages for b in p["boxes"])
        possible = whole  # out of the whole worksheet, even if a page is missing from the scan
        absent = sorted(set(layout_pages) - {p["page"] for p in student_pages})
        if absent:
            missing[student_id] = absent
        totals[student_id] = (earned, possible)
        last_page = student_pages[-1]["page"]
        for page in student_pages:
            page_layout = layout_pages[page["page"]]
            c.drawImage(_jpeg(images[page["scan_index"]], out_dir), 0, 0, S.PAGE_W, S.PAGE_H)
            results = {b["q"]: b for b in page["boxes"]}
            for box in page_layout["boxes"]:
                result = results.get(box["q"])
                if result is None:
                    continue  # an essay's later page: its comment is beside the first page of it
                if result["verdict"] != "blank":
                    _marks_on_work(c, box, result)
                lines = [] if result["verdict"] == "blank" else _gutter_lines(result, pen)
                if result["comment"] or result["verdict"] == "correct" or lines:
                    _draw_comment(c, pen, box["feedback_rect"], result["verdict"], result["comment"], lines)
            last = page is student_pages[-1]
            score = f"Score: {earned:g} / {possible}" if grade == "back" and last else None
            _draw_summary(c, pen, page_layout["summary_rect"], summary_by_student.get(student_id, {}) if last else None,
                          score, last_page)
            c.showPage()
            sheets += 1
        if len(layout["pages"]) > 1 and len(student_pages) % 2:
            c.showPage()  # blank back, so each student starts on a new sheet when printed double-sided
            sheets += 1
    c.save()
    out = {"returned": returned, "sheets": sheets, "students": len(by_student),
           "double_sided": len(layout["pages"]) > 1, "missing": missing}

    if grade == "csv":
        questions = [b["q"] for p in layout["pages"] for b in p["boxes"] if b.get("part", 1) == 1]
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
