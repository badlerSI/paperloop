"""Make: lay out a printable worksheet and write layout.json + key.json.

The template decides where everything goes, so later steps never guess
coordinates: ingest reads the markers, QR code, and ID bubbles from fixed
positions, and mark crops each answer box from its rect in layout.json.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import qrcode
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from . import template as T
from .schemas import AnswerKey, Box, IdGrid, KeyItem, Layout, PageLayout, WorksheetDef, load, save

PROMPT_FONT, PROMPT_SIZE, PROMPT_LEADING = "Helvetica", 11.0, 14.0
PROMPT_GAP = 6.0  # between prompt text and its answer box
LINE_SPACING = 22.0  # ruled writing lines inside answer boxes
BLOCK_GAP = 18.0  # between questions

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


def _paginate(defn: WorksheetDef) -> list[list[tuple[int, list[str], float]]]:
    """Group questions into pages: (question index, wrapped prompt lines, block height)."""
    pages: list[list[tuple[int, list[str], float]]] = [[]]
    y = T.CONTENT_TOP
    for i, question in enumerate(defn.questions):
        lines = simpleSplit(f"{question.q}. {question.prompt}", PROMPT_FONT, PROMPT_SIZE, T.BOX_RIGHT - T.LEFT)
        height = len(lines) * PROMPT_LEADING + PROMPT_GAP + question.lines * LINE_SPACING
        if y - height < T.CONTENT_BOTTOM and pages[-1]:
            pages.append([])
            y = T.CONTENT_TOP
        pages[-1].append((i, lines, height))
        y -= height + BLOCK_GAP
    return pages


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


def make_worksheet(defn: WorksheetDef, out_dir: Path) -> tuple[Path, Layout, AnswerKey]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "worksheet.pdf"
    grid = id_grid()
    pages = _paginate(defn)

    c = canvas.Canvas(str(pdf_path), pagesize=(T.PAGE_W, T.PAGE_H))
    c.setTitle(defn.title)
    c.setAuthor("Paper Loop")
    page_layouts: list[PageLayout] = []
    for page_no, blocks in enumerate(pages, start=1):
        payload = T.qr_payload(defn.assignment_id, page_no)
        for marker_id, rect in T.MARKER_RECTS.items():
            _draw_marker(c, marker_id, rect)
        _draw_qr(c, payload, T.QR_RECT)
        _draw_header(c, defn, page_no, len(pages), grid)
        _draw_footer(c, defn, page_no, len(pages))

        boxes: list[Box] = []
        y = T.CONTENT_TOP
        for i, lines, height in blocks:
            question = defn.questions[i]
            c.setFillGray(INK)
            c.setFont(PROMPT_FONT, PROMPT_SIZE)
            for n, line in enumerate(lines):
                c.drawString(T.LEFT, y - PROMPT_SIZE - n * PROMPT_LEADING, line)
            box_top = y - len(lines) * PROMPT_LEADING - PROMPT_GAP
            box_bottom = y - height
            c.setStrokeGray(FAINT)
            c.setLineWidth(0.6)
            for k in range(1, question.lines):
                ly = box_bottom + k * LINE_SPACING
                c.line(T.LEFT + 6, ly, T.BOX_RIGHT - 6, ly)
            c.setStrokeGray(OUTLINE)
            c.setLineWidth(1)
            c.rect(T.LEFT, box_bottom, T.BOX_RIGHT - T.LEFT, box_top - box_bottom, stroke=1, fill=0)
            boxes.append(Box(
                q=question.q,
                rect=(T.LEFT, box_bottom, T.BOX_RIGHT, box_top),
                feedback_rect=(T.GUTTER_LEFT, box_bottom, T.GUTTER_RIGHT, y),
                prompt=question.prompt,
                points=question.points,
            ))
            y -= height + BLOCK_GAP

        page_layouts.append(PageLayout(
            page=page_no, qr=payload, qr_rect=T.QR_RECT, id_grid=grid,
            summary_rect=T.SUMMARY_RECT, boxes=boxes,
        ))
        c.showPage()
    c.save()

    layout = Layout(
        assignment_id=defn.assignment_id, title=defn.title,
        page_size=(T.PAGE_W, T.PAGE_H), markers=T.MARKER_RECTS, pages=page_layouts,
    )
    key = AnswerKey(
        assignment_id=defn.assignment_id, subject=defn.subject, grade_band=defn.grade_band,
        items=[KeyItem(q=q.q, prompt=q.prompt, key=q.key, points=q.points) for q in defn.questions],
    )
    save(layout, out_dir / "layout.json")
    save(key, out_dir / "key.json")
    save(defn, out_dir / "worksheet.json")
    return pdf_path, layout, key


def load_assignment(assignment_dir: Path) -> tuple[Layout, AnswerKey]:
    assignment_dir = Path(assignment_dir)
    return load(Layout, assignment_dir / "layout.json"), load(AnswerKey, assignment_dir / "key.json")
