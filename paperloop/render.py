"""Render: stamp comments beside each box, add the summary, sort by student ID.

Each returned page is the deskewed scan with feedback drawn in the gutter the
template left empty, so comments always land beside the right box. Output is
one PDF ready to print and hand back, plus a separate review pile.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Literal

from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from . import template as T
from .make import load_assignment
from .review import pending
from .schemas import Feedback, IngestResult, PageFeedback, load

Grade = Literal["off", "back", "csv"]

COMMENT_FONT, COMMENT_SIZE, COMMENT_LEADING = "Helvetica-Oblique", 10.0, 12.0
SUMMARY_SIZE, SUMMARY_LEADING = 9.5, 11.5
PEN = (0.1, 0.1, 0.45)  # dark blue; prints as near-black on a mono copier

_ASCII = {"→": "->", "←": "<-", "≥": ">=", "≤": "<=", "×": "x", "÷": "/",
          "−": "-", "≈": "~"}


class RenderBlocked(Exception):
    pass


def printable(text: str) -> str:
    """Keep only what the built-in PDF fonts can draw (Windows-1252)."""
    out = []
    for ch in text:
        ch = _ASCII.get(ch, ch)
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def _draw_comment(c: canvas.Canvas, rect, verdict: str, comment: str) -> None:
    x0, _, x1, y1 = rect
    x, y = x0 + 4, y1 - COMMENT_SIZE - 2
    c.setFillColorRGB(*PEN)
    if verdict == "correct":
        c.setFont("ZapfDingbats", 12)
        c.drawString(x, y - 1, "4")  # check mark
        x += 16
    c.setFont(COMMENT_FONT, COMMENT_SIZE)
    for line in simpleSplit(printable(comment), COMMENT_FONT, COMMENT_SIZE, x1 - x - 2):
        c.drawString(x, y, line)
        y -= COMMENT_LEADING


def _draw_summary(c: canvas.Canvas, rect, page: PageFeedback, score: str | None) -> None:
    x0, y0, x1, y1 = rect
    # Cover the printed placeholder label, then write the summary.
    c.setFillGray(1)
    c.rect(x0 + 1, y1 - 12, 200, 11, stroke=0, fill=1)
    c.setFillColorRGB(*PEN)
    if score:
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(x1 - 6, y1 - 15, printable(score))

    fixes = page.summary.fixes
    entries = [("Strength:", page.summary.strength)] if page.summary.strength else []
    entries += [("Next step:" if len(fixes) == 1 else f"Next step {n}:", fix) for n, fix in enumerate(fixes, 1)]
    left, right = x0 + 5, x1 - 6 - (90 if score else 0)
    y = y1 - SUMMARY_SIZE - 3
    for label, text in entries:
        indent = c.stringWidth(label + " ", "Helvetica-Bold", SUMMARY_SIZE)
        if y < y0 + 3:
            return
        c.setFont("Helvetica-Bold", SUMMARY_SIZE)
        c.drawString(left, y, label)
        c.setFont("Helvetica", SUMMARY_SIZE)
        for line in simpleSplit(printable(text), "Helvetica", SUMMARY_SIZE, right - left - indent):
            if y < y0 + 3:
                return
            c.drawString(left + indent, y, line)
            y -= SUMMARY_LEADING


def render(workdir: Path, grade: Grade = "off", force: bool = False, duplex: bool = True) -> dict[str, Path | int]:
    workdir = Path(workdir)
    feedback = load(Feedback, workdir / "feedback.json")
    ingested = load(IngestResult, workdir / "ingest.json")
    layout, _ = load_assignment(Path(ingested.assignment_dir))
    unreviewed = pending(feedback)
    if unreviewed and not force:
        raise RenderBlocked(f"{len(unreviewed)} flagged answers still need review; run `paperloop review` first")

    out_dir = workdir / "out"
    out_dir.mkdir(exist_ok=True)
    images = {p.scan_index: workdir / p.image for p in ingested.pages if p.status == "ok"}
    by_student: dict[str, list[PageFeedback]] = defaultdict(list)
    for page in feedback.pages:
        by_student[page.student_id].append(page)

    returned = out_dir / "returned.pdf"
    c = canvas.Canvas(str(returned), pagesize=(T.PAGE_W, T.PAGE_H))
    c.setTitle(f"{feedback.assignment_id}: marked")
    sheets = 0
    totals: dict[str, tuple[float, int]] = {}
    for student_id in sorted(by_student):
        pages = sorted(by_student[student_id], key=lambda p: p.page)
        earned = sum(b.points_awarded for p in pages for b in p.boxes)
        possible = sum(b.points_possible for p in pages for b in p.boxes)
        totals[student_id] = (earned, possible)
        for page in pages:
            page_layout = layout.page(page.page)
            c.drawImage(str(images[page.scan_index]), 0, 0, T.PAGE_W, T.PAGE_H)
            boxes = {b.q: b for b in page.boxes}
            for box in page_layout.boxes:
                result = boxes[box.q]
                if result.comment or result.verdict == "correct":
                    _draw_comment(c, box.feedback_rect, result.verdict, result.comment)
            last = page is pages[-1]
            score = f"Score: {earned:g} / {possible}" if grade == "back" and last else None
            _draw_summary(c, page_layout.summary_rect, page, score)
            c.showPage()
            sheets += 1
        if duplex and len(pages) % 2:
            c.showPage()  # blank back so the next student starts on a new sheet
            sheets += 1
    c.save()

    result: dict[str, Path | int] = {"returned": returned, "pages": sheets, "students": len(by_student)}
    if grade == "csv":
        questions = [b.q for p in layout.pages for b in p.boxes]
        grades = out_dir / "grades.csv"
        with grades.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["student_id", *[f"q{q}" for q in questions], "total", "possible"])
            for student_id in sorted(by_student):
                points = {b.q: b.points_awarded for p in by_student[student_id] for b in p.boxes}
                earned, possible = totals[student_id]
                writer.writerow([student_id, *[f"{points[q]:g}" if q in points else "" for q in questions],
                                 f"{earned:g}", possible])
        result["grades"] = grades

    pile = [p for p in ingested.pages if p.status == "review"]
    if pile:
        review_pdf = out_dir / "review_pile.pdf"
        c = canvas.Canvas(str(review_pdf), pagesize=(T.PAGE_W, T.PAGE_H))
        for p in pile:
            c.drawImage(str(workdir / p.raw_image), 36, 36, T.PAGE_W - 72, T.PAGE_H - 96, preserveAspectRatio=True)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(36, T.PAGE_H - 40, printable(f"Review pile, scan page {p.scan_index}: {p.reason}"))
            c.showPage()
        c.save()
        result["review_pile"] = review_pdf
    return result
