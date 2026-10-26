"""Make: lay out a printable worksheet and write layout.json + key.json.

The template decides where everything goes, so later steps never guess
coordinates: ingest reads the markers, QR code, and ID bubbles from fixed
positions, and mark crops each question from its rect in layout.json.

Question types: short answer (a ruled box), choice (circle a letter), label
(write in numbered boxes on a printed diagram), and draw (draw into a framed
area over a printed scaffold, judged against a checklist).
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import qrcode
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from . import raster
from . import template as T
from .schemas import (
    AnswerKey, Box, ChoiceQ, Diagram, DrawQ, IdGrid, KeyItem, LabelBoxSpot, LabelQ, Layout, OptionSpot,
    PageLayout, ShortQ, WorksheetDef, load, save,
)

PROMPT_FONT, PROMPT_SIZE, PROMPT_LEADING = "Helvetica", 11.0, 14.0
PROMPT_GAP = 6.0  # between prompt text and what follows
LINE_SPACING = 22.0  # ruled writing lines inside answer boxes
BLOCK_GAP = 18.0  # between questions
OPTION_SIZE, OPTION_LEADING, OPTION_GAP = 10.5, 13.0, 9.0
OPTION_TEXT_X = T.LEFT + 30
OPTION_REACH = 16.0  # a circle drawn around a letter pokes left of the margin; count that ink too
WORD_BANK_H = 20.0

INK = 0.0
OUTLINE = 0.35
FAINT = 0.8  # light enough that ingest's darkness threshold ignores it


def id_grid() -> IdGrid:
    centers, writeins = [], []
    for d in range(T.ID_DIGITS):
        y = T.ID_FIRST_ROW_Y - d * T.ID_ROW_PITCH
        writeins.append((T.ID_WRITEIN_X, y - 7.0, T.ID_WRITEIN_X + 20.0, y + 7.0))
        centers.append([(T.ID_FIRST_BUBBLE_X + v * T.ID_BUBBLE_PITCH, y) for v in range(10)])
    return IdGrid(digits=T.ID_DIGITS, bubble_r=T.ID_BUBBLE_R, writein_rects=writeins, centers=centers)


# --- Measuring --------------------------------------------------------------

def _prompt_lines(question) -> list[str]:
    return simpleSplit(f"{question.q}. {question.prompt}", PROMPT_FONT, PROMPT_SIZE, T.BOX_RIGHT - T.LEFT)


def _option_lines(text: str) -> list[str]:
    return simpleSplit(text, "Helvetica", OPTION_SIZE, T.BOX_RIGHT - OPTION_TEXT_X)


def _body_height(question) -> float:
    if isinstance(question, ShortQ):
        return question.lines * LINE_SPACING
    if isinstance(question, ChoiceQ):
        rows = [len(_option_lines(o.text)) * OPTION_LEADING for o in question.options]
        return sum(rows) + OPTION_GAP * (len(rows) - 1)
    if isinstance(question, LabelQ):
        return question.diagram.height + (WORD_BANK_H if question.word_bank else 0)
    return question.diagram.height


def _block_height(question) -> float:
    return len(_prompt_lines(question)) * PROMPT_LEADING + PROMPT_GAP + _body_height(question)


def _paginate(defn: WorksheetDef) -> list[list[int]]:
    """Group question indexes into pages."""
    pages: list[list[int]] = [[]]
    y = T.CONTENT_TOP
    for i, question in enumerate(defn.questions):
        if isinstance(question, (LabelQ, DrawQ)) and question.diagram.width > T.BOX_RIGHT - T.LEFT:
            raise ValueError(f"question {question.q}: diagram is wider than {T.BOX_RIGHT - T.LEFT:g}pt")
        height = _block_height(question)
        if y - height < T.CONTENT_BOTTOM and pages[-1]:
            pages.append([])
            y = T.CONTENT_TOP
        pages[-1].append(i)
        y -= height + BLOCK_GAP
    return pages


# --- Drawing ------------------------------------------------------------------

def _draw_marker(c: canvas.Canvas, marker_id: int, rect) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, T.MARKER_DICT))
    bits = cv2.aruco.generateImageMarker(dictionary, marker_id, 6)  # 4x4 bits + 1-bit border
    x0, _, x1, y1 = rect
    cell = (x1 - x0) / bits.shape[0]
    c.setFillGray(INK)
    for r in range(bits.shape[0]):
        for col in range(bits.shape[1]):
            if bits[r, col] == 0:
                # A hair of overlap so adjacent cells don't render with seams.
                c.rect(x0 + col * cell, y1 - (r + 1) * cell, cell + 0.05, cell + 0.05, stroke=0, fill=1)


def _draw_qr(c: canvas.Canvas, payload: str, rect) -> None:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=2, box_size=1)
    qr.add_data(payload)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    x0, _, x1, y1 = rect
    cell = (x1 - x0) / len(matrix)
    c.setFillGray(INK)
    for r, row in enumerate(matrix):
        for col, dark in enumerate(row):
            if dark:
                c.rect(x0 + col * cell, y1 - (r + 1) * cell, cell + 0.05, cell + 0.05, stroke=0, fill=1)


def _draw_header(c: canvas.Canvas, defn: WorksheetDef, page_no: int, n_pages: int, grid: IdGrid) -> None:
    c.setFillGray(INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(138, 744, defn.title)
    c.setFont("Helvetica", 9)
    c.drawString(138, 730, f"Page {page_no} of {n_pages}")
    c.setFont("Helvetica", 8.5)
    y = 716.0
    for line in simpleSplit(defn.instructions, "Helvetica", 8.5, 205):
        c.drawString(138, y, line)
        y -= 10.5

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(T.ID_WRITEIN_X, 746, "STUDENT ID: write each digit, then fill its bubble")
    c.setLineWidth(0.8)
    for writein, row in zip(grid.writein_rects, grid.centers):
        x0, y0, x1, y1 = writein
        c.setStrokeGray(OUTLINE)
        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
        for value, (cx, cy) in enumerate(row):
            c.setStrokeGray(OUTLINE)
            c.circle(cx, cy, grid.bubble_r, stroke=1, fill=0)
            c.setFillGray(FAINT)
            c.setFont("Helvetica", 6)
            c.drawCentredString(cx, cy - 2.1, str(value))
    c.setFillGray(INK)
    c.setStrokeGray(OUTLINE)
    c.line(T.LEFT, 666, T.GUTTER_RIGHT, 666)


def _draw_footer(c: canvas.Canvas, defn: WorksheetDef, page_no: int, n_pages: int) -> None:
    x0, y0, x1, y1 = T.SUMMARY_RECT
    c.setStrokeGray(FAINT)
    c.setLineWidth(0.8)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
    c.setFillGray(0.6)
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 5, y1 - 10, "Feedback summary (your teacher fills this in)")
    c.drawCentredString(
        T.PAGE_W / 2, 32,
        f"{defn.assignment_id} | page {page_no} of {n_pages} | please don't write in the corner squares",
    )


def _arrowhead(c: canvas.Canvas, x0: float, y0: float, x1: float, y1: float, size: float) -> None:
    angle = math.atan2(y1 - y0, x1 - x0)
    p = c.beginPath()
    p.moveTo(x1, y1)
    for side in (-1, 1):
        a = angle + math.pi - side * math.radians(25)
        p.lineTo(x1 + size * math.cos(a), y1 + size * math.sin(a))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def draw_diagram(c: canvas.Canvas, diagram: Diagram, x0: float, y0: float) -> None:
    for s in diagram.shapes:
        stroke, fill = s.stroke is not None, s.fill is not None
        c.setLineWidth(s.width)
        c.setStrokeGray(s.stroke if stroke else 0)
        c.setFillGray(s.fill if fill else 0)
        if s.shape == "rect":
            c.rect(x0 + s.x, y0 + s.y, s.w, s.h, stroke=int(stroke), fill=int(fill))
        elif s.shape == "circle":
            c.circle(x0 + s.x, y0 + s.y, s.r, stroke=int(stroke), fill=int(fill))
        elif s.shape in ("line", "arrow", "polyline", "polygon") and len(s.points) >= 2:
            p = c.beginPath()
            p.moveTo(x0 + s.points[0][0], y0 + s.points[0][1])
            for px, py in s.points[1:]:
                p.lineTo(x0 + px, y0 + py)
            if s.shape == "polygon":
                p.close()
            c.drawPath(p, stroke=int(stroke), fill=int(fill and s.shape == "polygon"))
            if s.shape == "arrow":
                (ax, ay), (bx, by) = s.points[-2], s.points[-1]
                c.setFillGray(s.stroke if stroke else 0)
                _arrowhead(c, x0 + ax, y0 + ay, x0 + bx, y0 + by, 4 + 2 * s.width)
        elif s.shape == "text":
            c.setFillGray(s.fill if fill else 0)
            c.setFont("Helvetica-Bold" if s.bold else "Helvetica", s.size)
            draw = {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[s.align]
            draw(x0 + s.x, y0 + s.y, s.text)


def _draw_prompt(c: canvas.Canvas, question, y: float) -> float:
    """Draws the numbered prompt; returns the y where the body starts."""
    lines = _prompt_lines(question)
    c.setFillGray(INK)
    c.setFont(PROMPT_FONT, PROMPT_SIZE)
    for n, line in enumerate(lines):
        c.drawString(T.LEFT, y - PROMPT_SIZE - n * PROMPT_LEADING, line)
    return y - len(lines) * PROMPT_LEADING - PROMPT_GAP


def _draw_question(c: canvas.Canvas, question, y: float) -> Box:
    top = y
    body_top = _draw_prompt(c, question, y)
    bottom = y - _block_height(question)
    feedback = (T.GUTTER_LEFT, bottom, T.GUTTER_RIGHT, top)
    box = Box(q=question.q, type=question.type, rect=(T.LEFT, bottom, T.BOX_RIGHT, body_top),
              feedback_rect=feedback, prompt=question.prompt, points=question.points)

    if isinstance(question, ShortQ):
        c.setStrokeGray(FAINT)
        c.setLineWidth(0.6)
        for k in range(1, question.lines):
            ly = bottom + k * LINE_SPACING
            c.line(T.LEFT + 6, ly, T.BOX_RIGHT - 6, ly)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(T.LEFT, bottom, T.BOX_RIGHT - T.LEFT, body_top - bottom, stroke=1, fill=0)

    elif isinstance(question, ChoiceQ):
        row_top = body_top
        for option in question.options:
            lines = _option_lines(option.text)
            baseline = row_top - OPTION_SIZE
            c.setFillGray(INK)
            c.setFont("Helvetica-Bold", OPTION_SIZE + 0.5)
            c.drawString(T.LEFT + 10, baseline, option.letter)
            c.setFont("Helvetica", OPTION_SIZE)
            for n, line in enumerate(lines):
                c.drawString(OPTION_TEXT_X, baseline - n * OPTION_LEADING, line)
            row_h = len(lines) * OPTION_LEADING
            box.options.append(OptionSpot(
                letter=option.letter,
                rect=(T.LEFT - OPTION_REACH, row_top - row_h - OPTION_GAP / 2, T.BOX_RIGHT,
                      row_top + OPTION_GAP / 2),
                letter_at=(T.LEFT + 10 + c.stringWidth(option.letter, "Helvetica-Bold", OPTION_SIZE + 0.5) / 2,
                           baseline + 3.8),
            ))
            row_top -= row_h + OPTION_GAP
        box.rect = (T.LEFT - OPTION_REACH, bottom - OPTION_GAP / 2, T.BOX_RIGHT, body_top + OPTION_GAP / 2)

    elif isinstance(question, LabelQ):
        diagram_top = body_top
        if question.word_bank:
            c.setFillGray(INK)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(T.LEFT, body_top - 12, "Word bank:")
            c.setFont("Helvetica", 9.5)
            c.drawString(T.LEFT + 58, body_top - 12, "     •     ".join(question.word_bank))
            diagram_top -= WORD_BANK_H
        x0, y0 = T.LEFT, diagram_top - question.diagram.height
        draw_diagram(c, question.diagram, x0, y0)
        for spot in question.labels:
            bx, by, bw, bh = spot.box
            c.setStrokeGray(OUTLINE)
            c.setLineWidth(1)
            c.rect(x0 + bx, y0 + by, bw, bh, stroke=1, fill=0)
            c.setFillGray(0.45)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(x0 + bx + 2.5, y0 + by + bh - 8, str(spot.n))
            if spot.points_to:
                px, py = spot.points_to
                ex = bx if px < bx else bx + bw
                c.setStrokeGray(OUTLINE)
                c.setLineWidth(0.8)
                c.line(x0 + ex, y0 + by + bh / 2, x0 + px, y0 + py)
                c.setFillGray(OUTLINE)
                c.circle(x0 + px, y0 + py, 1.6, stroke=0, fill=1)
            box.labels.append(LabelBoxSpot(n=spot.n, rect=(x0 + bx, y0 + by, x0 + bx + bw, y0 + by + bh)))
        box.rect = (x0, y0, x0 + question.diagram.width, diagram_top)

    elif isinstance(question, DrawQ):
        x0, y0 = T.LEFT, body_top - question.diagram.height
        draw_diagram(c, question.diagram, x0, y0)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(x0, y0, question.diagram.width, question.diagram.height, stroke=1, fill=0)
        box.rect = (x0, y0, x0 + question.diagram.width, body_top)

    return box


def _key_item(question) -> KeyItem:
    common = dict(q=question.q, type=question.type, prompt=question.prompt, points=question.points)
    if isinstance(question, ShortQ):
        return KeyItem(**common, key=question.key)
    if isinstance(question, ChoiceQ):
        return KeyItem(**common, options=question.options, answer=question.answer,
                       key=f"{question.answer}: " + next(o.text for o in question.options
                                                          if o.letter == question.answer))
    if isinstance(question, LabelQ):
        key = "; ".join(f"{s.n}: {s.answer}" for s in question.labels)
        return KeyItem(**common, labels=question.labels, word_bank=question.word_bank, key=key,
                       diagram=question.diagram.description)
    return KeyItem(**common, checklist=question.checklist, diagram=question.diagram.description,
                   key="; ".join(c.item for c in question.checklist))


def make_worksheet(defn: WorksheetDef, out_dir: Path) -> tuple[Path, Layout, AnswerKey]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for question in defn.questions:
        if isinstance(question, ChoiceQ) and question.answer not in {o.letter for o in question.options}:
            raise ValueError(f"question {question.q}: answer {question.answer!r} isn't one of the options")
    pdf_path = out_dir / "worksheet.pdf"
    grid = id_grid()
    pages = _paginate(defn)

    c = canvas.Canvas(str(pdf_path), pagesize=(T.PAGE_W, T.PAGE_H))
    c.setTitle(defn.title)
    c.setAuthor("Paper Loop")
    page_layouts: list[PageLayout] = []
    for page_no, indexes in enumerate(pages, start=1):
        payload = T.qr_payload(defn.assignment_id, page_no)
        for marker_id, rect in T.MARKER_RECTS.items():
            _draw_marker(c, marker_id, rect)
        _draw_qr(c, payload, T.QR_RECT)
        _draw_header(c, defn, page_no, len(pages), grid)
        _draw_footer(c, defn, page_no, len(pages))

        boxes: list[Box] = []
        y = T.CONTENT_TOP
        for i in indexes:
            question = defn.questions[i]
            boxes.append(_draw_question(c, question, y))
            y -= _block_height(question) + BLOCK_GAP

        page_layouts.append(PageLayout(
            page=page_no, qr=payload, qr_rect=T.QR_RECT, id_grid=grid,
            summary_rect=T.SUMMARY_RECT, boxes=boxes,
        ))
        c.showPage()
    c.save()
    raster.write_templates(out_dir)

    layout = Layout(
        assignment_id=defn.assignment_id, title=defn.title,
        page_size=(T.PAGE_W, T.PAGE_H), markers=T.MARKER_RECTS, pages=page_layouts,
    )
    key = AnswerKey(assignment_id=defn.assignment_id, subject=defn.subject, grade_band=defn.grade_band,
                    items=[_key_item(q) for q in defn.questions])
    save(layout, out_dir / "layout.json")
    save(key, out_dir / "key.json")
    save(defn, out_dir / "worksheet.json")
    return pdf_path, layout, key


def load_assignment(assignment_dir: Path) -> tuple[Layout, AnswerKey]:
    assignment_dir = Path(assignment_dir)
    return load(Layout, assignment_dir / "layout.json"), load(AnswerKey, assignment_dir / "key.json")
