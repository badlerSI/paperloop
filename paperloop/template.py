"""Page geometry shared by every worksheet.

Everything is in PDF points (1/72 inch) with the origin at the bottom-left, as
in reportlab. Ingest finds the registration markers and reads the QR code
before it knows which assignment a page belongs to, so these never vary
between assignments. Rects are [x0, y0, x1, y1].
"""

from __future__ import annotations

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter

# ArUco markers in the four corners give orientation and a homography for deskew.
# Inset keeps them clear of the ~12pt unprintable margin on most printers.
MARKER_DICT = "DICT_4X4_50"
MARKER_SIZE = 32.0
MARKER_INSET = 22.0
_lo = MARKER_INSET
_hi_x = PAGE_W - MARKER_INSET - MARKER_SIZE
_hi_y = PAGE_H - MARKER_INSET - MARKER_SIZE
MARKER_RECTS: dict[int, tuple[float, float, float, float]] = {
    0: (_lo, _hi_y, _lo + MARKER_SIZE, _hi_y + MARKER_SIZE),  # top-left
    1: (_hi_x, _hi_y, _hi_x + MARKER_SIZE, _hi_y + MARKER_SIZE),  # top-right
    2: (_hi_x, _lo, _hi_x + MARKER_SIZE, _lo + MARKER_SIZE),  # bottom-right
    3: (_lo, _lo, _lo + MARKER_SIZE, _lo + MARKER_SIZE),  # bottom-left
}

QR_RECT = (66.0, 698.0, 128.0, 760.0)

# Student ID: one row of ten bubbles (0-9) per digit, plus a write-in box.
ID_DIGITS = 4
ID_BUBBLE_R = 5.0
ID_BUBBLE_PITCH = 15.0
ID_ROW_PITCH = 17.0
ID_FIRST_ROW_Y = 734.0
ID_WRITEIN_X = 358.0
ID_FIRST_BUBBLE_X = 390.0

# Content area for questions, and the summary box above the bottom markers.
CONTENT_TOP = 652.0
CONTENT_BOTTOM = 150.0
LEFT = 48.0
BOX_RIGHT = 392.0
GUTTER_LEFT = 404.0
GUTTER_RIGHT = 572.0
SUMMARY_RECT = (48.0, 64.0, 572.0, 136.0)

# Canonical raster for deskewed pages, crops, and rendering.
DPI = 200


def scale(dpi: int = DPI) -> float:
    return dpi / 72.0


def pt_to_px(x: float, y: float, dpi: int = DPI) -> tuple[float, float]:
    """PDF point (origin bottom-left) to pixel (origin top-left)."""
    s = scale(dpi)
    return x * s, (PAGE_H - y) * s


def rect_to_px(rect: tuple[float, float, float, float], dpi: int = DPI) -> tuple[int, int, int, int]:
    """PDF rect to integer pixel box (left, top, right, bottom)."""
    x0, y0, x1, y1 = rect
    s = scale(dpi)
    return round(x0 * s), round((PAGE_H - y1) * s), round(x1 * s), round((PAGE_H - y0) * s)


def canonical_size(dpi: int = DPI) -> tuple[int, int]:
    s = scale(dpi)
    return round(PAGE_W * s), round(PAGE_H * s)


def qr_payload(assignment_id: str, page: int) -> str:
    return f"{assignment_id}|p{page}"


def parse_qr_payload(text: str) -> tuple[str, int] | None:
    assignment_id, sep, page = text.rpartition("|p")
    if not sep or not assignment_id or not page.isdigit():
        return None
    return assignment_id, int(page)
