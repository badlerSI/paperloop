"""Make: lay out a printable worksheet and write layout.json + key.json.

The template decides where everything goes, so later steps never guess
coordinates: ingest reads the markers, QR code, and ID from fixed positions,
and mark crops each question from its rect in layout.json.

Question types: short answer (a ruled box), choice (circle a letter), label
(write in numbered boxes on a printed diagram), and draw (draw into a framed
area over a printed scaffold, judged against a checklist).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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

PROMPT_FONT = "Helvetica"
OPTION_REACH = 16.0  # a circle drawn around a letter pokes left of its text; count that ink too

INK = 0.0
OUTLINE = 0.35
FAINT = 0.8  # light enough that ingest's darkness threshold ignores it


@dataclass(frozen=True)
class Style:
    prompt_size: float = 11.0
    prompt_leading: float = 14.0
    prompt_gap: float = 6.0  # between prompt text and what follows
    line_spacing: float = 22.0  # ruled writing lines inside answer boxes
    block_gap: float = 18.0  # between questions
    option_size: float = 10.5
    option_leading: float = 13.0
    option_gap: float = 9.0
    word_bank_h: float = 20.0


ROOMY = Style()
COMPACT = Style(prompt_size=10.5, prompt_leading=12.5, prompt_gap=4.0, line_spacing=21.0, block_gap=11.0,
                option_size=10.0, option_leading=12.0, option_gap=6.0, word_bank_h=17.0)


def id_grid() -> IdGrid:
    centers, writeins = [], []
    for d in range(T.ID_DIGITS):
        y = T.ID_FIRST_ROW_Y - d * T.ID_ROW_PITCH
        writeins.append((T.ID_WRITEIN_X, y - 7.0, T.ID_WRITEIN_X + 20.0, y + 7.0))
        centers.append([(T.ID_FIRST_BUBBLE_X + v * T.ID_BUBBLE_PITCH, y) for v in range(10)])
    return IdGrid(digits=T.ID_DIGITS, bubble_r=T.ID_BUBBLE_R, writein_rects=writeins, centers=centers)


def id_boxes() -> list[tuple[float, float, float, float]]:
    return [(T.ID_WRITE_X + d * T.ID_WRITE_W, T.ID_WRITE_Y, T.ID_WRITE_X + (d + 1) * T.ID_WRITE_W,
             T.ID_WRITE_Y + T.ID_WRITE_H) for d in range(T.ID_DIGITS)]


# --- Measuring --------------------------------------------------------------

def _prompt_lines(question, st: Style) -> list[str]:
    return simpleSplit(f"{question.q}. {question.prompt}", PROMPT_FONT, st.prompt_size, T.BOX_RIGHT - T.LEFT)


def _option_geometry(question: ChoiceQ, st: Style):
    """Column width, text indent, and each option's wrapped lines."""
    columns = max(1, question.columns)
    col_w = (T.BOX_RIGHT - T.LEFT) / columns
    indent = 30.0 if columns == 1 else 20.0
    width = col_w - indent - (0 if columns == 1 else 4)
    lines = [simpleSplit(o.text, "Helvetica", st.option_size, width) for o in question.options]
    return columns, col_w, indent, lines


def _option_rows(question: ChoiceQ, st: Style) -> list[float]:
    columns, _, _, lines = _option_geometry(question, st)
    rows = [lines[i:i + columns] for i in range(0, len(lines), columns)]
    return [max(len(l) for l in row) * st.option_leading for row in rows]


def _body_height(question, st: Style) -> float:
    if isinstance(question, ShortQ):
        return question.lines * st.line_spacing
    if isinstance(question, ChoiceQ):
        rows = _option_rows(question, st)
        return sum(rows) + st.option_gap * (len(rows) - 1)
    if isinstance(question, LabelQ):
        return question.diagram.height + (st.word_bank_h if question.word_bank else 0)
    return question.diagram.height


def _block_height(question, st: Style) -> float:
    return len(_prompt_lines(question, st)) * st.prompt_leading + st.prompt_gap + _body_height(question, st)


def _paginate(defn: WorksheetDef, st: Style, top: float, bottom: float) -> list[list[int]]:
    """Group question indexes into pages."""
    pages: list[list[int]] = [[]]
    y = top
    for i, question in enumerate(defn.questions):
        if isinstance(question, (LabelQ, DrawQ)) and question.diagram.width > T.BOX_RIGHT - T.LEFT:
            raise ValueError(f"question {question.q}: diagram is wider than {T.BOX_RIGHT - T.LEFT:g}pt")
        height = _block_height(question, st)
        if y - height < bottom and pages[-1]:
            pages.append([])
            y = top
        pages[-1].append(i)
        y -= height + st.block_gap
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


def _draw_header(c: canvas.Canvas, defn: WorksheetDef, page_no: int, n_pages: int, grid: IdGrid | None,
                 boxes: list) -> float:
    """Title, instructions, and the ID area. Returns the y of the rule under the header."""
    c.setFillGray(INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(138, 744, defn.title)
    c.setFont("Helvetica", 9)
    c.drawString(138, 730, f"Page {page_no} of {n_pages}")
    c.setFont("Helvetica", 8.5)
    y = 716.0
    width = 205 if grid else 290
    for line in simpleSplit(defn.instructions, "Helvetica", 8.5, width):
        c.drawString(138, y, line)
        y -= 10.5

    c.setLineWidth(0.8)
    if grid:
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(T.ID_WRITEIN_X, 746, "STUDENT ID: write each digit, then fill its bubble")
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
        rule = 666.0
    else:
        c.setFillGray(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(boxes[0][0] - 6, boxes[0][1] + 11, "ID #")
        c.setFont("Helvetica", 6.5)
        c.setFillGray(0.45)
        c.drawString(boxes[0][0], boxes[0][1] - 9, "one digit per box, not your name")
        c.setStrokeGray(OUTLINE)
        for x0, y0, x1, y1 in boxes:
            c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
        rule = T.CONTENT_TOP_WRITTEN_ID + 8
    c.setFillGray(INK)
    c.setStrokeGray(OUTLINE)
    c.line(T.LEFT, rule, T.GUTTER_RIGHT, rule)
    return rule


def _draw_footer(c: canvas.Canvas, defn: WorksheetDef, page_no: int, n_pages: int, summary) -> None:
    x0, y0, x1, y1 = summary
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


def _draw_prompt(c: canvas.Canvas, question, y: float, st: Style) -> float:
    """Draws the numbered prompt; returns the y where the body starts."""
    lines = _prompt_lines(question, st)
    c.setFillGray(INK)
    c.setFont(PROMPT_FONT, st.prompt_size)
    for n, line in enumerate(lines):
        c.drawString(T.LEFT, y - st.prompt_size - n * st.prompt_leading, line)
    return y - len(lines) * st.prompt_leading - st.prompt_gap


def _leader(c: canvas.Canvas, box, point) -> None:
    """A line from a label box to the spot it names: from the side facing the spot."""
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


def _draw_question(c: canvas.Canvas, question, y: float, st: Style) -> Box:
    top = y
    body_top = _draw_prompt(c, question, y, st)
    bottom = y - _block_height(question, st)
    feedback = (T.GUTTER_LEFT, bottom, T.GUTTER_RIGHT, top)
    box = Box(q=question.q, type=question.type, rect=(T.LEFT, bottom, T.BOX_RIGHT, body_top),
              feedback_rect=feedback, prompt=question.prompt, points=question.points)

    if isinstance(question, ShortQ):
        box.lines = question.lines
        c.setStrokeGray(FAINT)
        c.setLineWidth(0.6)
        for k in range(1, question.lines):
            ly = bottom + k * st.line_spacing
            c.line(T.LEFT + 6, ly, T.BOX_RIGHT - 6, ly)
        c.setStrokeGray(OUTLINE)
        c.setLineWidth(1)
        c.rect(T.LEFT, bottom, T.BOX_RIGHT - T.LEFT, body_top - bottom, stroke=1, fill=0)

    elif isinstance(question, ChoiceQ):
        columns, col_w, indent, lines = _option_geometry(question, st)
        row_heights = _option_rows(question, st)
        row_top = body_top
        for i, option in enumerate(question.options):
            row, col = divmod(i, columns)
            if col == 0 and row > 0:
                row_top -= row_heights[row - 1] + st.option_gap
            x = T.LEFT + col * col_w
            baseline = row_top - st.option_size
            c.setFillGray(INK)
            c.setFont("Helvetica-Bold", st.option_size + 0.5)
            c.drawString(x + 10, baseline, option.letter)
            c.setFont("Helvetica", st.option_size)
            for n, line in enumerate(lines[i]):
                c.drawString(x + indent, baseline - n * st.option_leading, line)
            row_h = row_heights[row]
            left = x - OPTION_REACH if col == 0 else x - 4
            right = x + col_w if columns == 1 else x + col_w - 4
            box.options.append(OptionSpot(
                letter=option.letter,
                rect=(left, row_top - row_h - st.option_gap / 2, right, row_top + st.option_gap / 2),
                letter_at=(x + 10 + c.stringWidth(option.letter, "Helvetica-Bold", st.option_size + 0.5) / 2,
                           baseline + 3.8),
            ))
        box.rect = (T.LEFT - OPTION_REACH, bottom - st.option_gap / 2, T.BOX_RIGHT, body_top + st.option_gap / 2)

    elif isinstance(question, LabelQ):
        diagram_top = body_top
        if question.word_bank:
            c.setFillGray(INK)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(T.LEFT, body_top - 12, "Word bank:")
            c.setFont("Helvetica", 9.5)
            c.drawString(T.LEFT + 58, body_top - 12, "     •     ".join(question.word_bank))
            diagram_top -= st.word_bank_h
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
                _leader(c, (x0 + bx, y0 + by, bw, bh), (x0 + spot.points_to[0], y0 + spot.points_to[1]))
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
    st = COMPACT if defn.compact else ROOMY
    summary = T.SUMMARY_RECT_COMPACT if defn.compact else T.SUMMARY_RECT
    written = defn.id_style == "write"
    grid, boxes = (None, id_boxes()) if written else (id_grid(), [])
    top = T.CONTENT_TOP_WRITTEN_ID if written else T.CONTENT_TOP
    bottom = summary[3] + 12
    pdf_path = out_dir / "worksheet.pdf"
    pages = _paginate(defn, st, top, bottom)

    c = canvas.Canvas(str(pdf_path), pagesize=(T.PAGE_W, T.PAGE_H))
    c.setTitle(defn.title)
    c.setAuthor("Paper Loop")
    page_layouts: list[PageLayout] = []
    for page_no, indexes in enumerate(pages, start=1):
        payload = T.qr_payload(defn.assignment_id, page_no)
        for marker_id, rect in T.MARKER_RECTS.items():
            _draw_marker(c, marker_id, rect)
        _draw_qr(c, payload, T.QR_RECT)
        _draw_header(c, defn, page_no, len(pages), grid, boxes)
        _draw_footer(c, defn, page_no, len(pages), summary)

        page_boxes: list[Box] = []
        y = top
        for i in indexes:
            question = defn.questions[i]
            page_boxes.append(_draw_question(c, question, y, st))
            y -= _block_height(question, st) + st.block_gap

        page_layouts.append(PageLayout(
            page=page_no, qr=payload, qr_rect=T.QR_RECT, id_grid=grid, id_boxes=boxes,
            summary_rect=summary, boxes=page_boxes,
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
