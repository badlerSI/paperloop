"""Pixels: render PDFs to grayscale images, and separate student ink from printed ink."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium

from . import template as T

DARK = 160  # grayscale below this counts as ink; printed faint guides sit above it
PRINTED = 200  # anything darker than this on the blank template is printed, including light fills
PRINT_SLACK_PX = 4  # registration error to forgive around printed ink


def render_pages(pdf_path: Path, dpi: int) -> list[np.ndarray]:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return [np.array(doc[i].render(scale=dpi / 72).to_pil().convert("L")) for i in range(len(doc))]
    finally:
        doc.close()


def template_path(assignment_dir: Path, page: int) -> Path:
    return Path(assignment_dir) / f"template-p{page}.png"


def write_templates(assignment_dir: Path, dpi: int = T.DPI) -> None:
    """Blank renders of each worksheet page, for telling student ink from printed ink."""
    for n, img in enumerate(render_pages(Path(assignment_dir) / "worksheet.pdf", dpi), start=1):
        cv2.imwrite(str(template_path(assignment_dir, n)), img)


@cache
def load_template(assignment_dir: str, page: int) -> np.ndarray:
    path = template_path(Path(assignment_dir), page)
    if not path.exists():
        write_templates(Path(assignment_dir))  # assignments made before templates existed
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)


def student_ink(canonical: np.ndarray, blank: np.ndarray) -> np.ndarray:
    """Boolean mask of ink on the scan that isn't on the printed page, specks removed."""
    printed = (blank < PRINTED).astype(np.uint8)
    size = 2 * PRINT_SLACK_PX + 1
    printed = cv2.dilate(printed, np.ones((size, size), np.uint8)).astype(bool)
    ink = ((canonical < DARK) & ~printed).astype(np.uint8)
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)


def crop(img: np.ndarray, rect, dpi: int = T.DPI, inset_pt: float = 0.0) -> np.ndarray:
    x0, y0, x1, y1 = rect
    left, top, right, bottom = T.rect_to_px((x0 + inset_pt, y0 + inset_pt, x1 - inset_pt, y1 - inset_pt), dpi)
    h, w = img.shape[:2]
    return img[max(top, 0):min(bottom, h), max(left, 0):min(right, w)]
