"""Ingest: split a scanned class set, deskew each page, read its QR code and student ID.

Pages come in any order and orientation. The four corner markers give a
homography to the template, so every later step works in template coordinates.
Anything that can't be read for certain goes to the review pile; never guess.
"""

from __future__ import annotations

from collections import defaultdict
from functools import cache
from pathlib import Path

import cv2
import numpy as np

from . import template as T
from .make import load_assignment
from .raster import DARK, render_pages
from .schemas import IdGrid, IngestResult, PageScan, Rect, save

BLANK_INK_FRACTION = 0.002
BUBBLE_FILLED = 0.35  # share of a bubble's center that must be dark to count as filled
BUBBLE_AMBIGUOUS = 0.6  # a runner-up this close to the darkest bubble makes the digit ambiguous
MAX_REPROJECTION_PX = 6.0


@cache
def _aruco_detector() -> cv2.aruco.ArucoDetector:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, T.MARKER_DICT))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(dictionary, params)


def find_markers(gray: np.ndarray) -> dict[int, np.ndarray]:
    """Marker id -> its 4 corners in image pixels (marker's own TL, TR, BR, BL)."""
    corners, ids, _ = _aruco_detector().detectMarkers(gray)
    found: dict[int, np.ndarray] = {}
    if ids is not None:
        for pts, marker_id in zip(corners, ids.flatten()):
            marker_id = int(marker_id)
            if marker_id in T.MARKER_RECTS and marker_id not in found:
                found[marker_id] = pts.reshape(4, 2)
    return found


def register(gray: np.ndarray, markers: dict[int, np.ndarray], dpi: int) -> tuple[np.ndarray, float]:
    """Warp a scanned page onto the template. Returns (canonical image, mean reprojection error px)."""
    src, dst = [], []
    for marker_id, pts in markers.items():
        x0, y0, x1, y1 = T.MARKER_RECTS[marker_id]
        for p, (x, y) in zip(pts, [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]):
            src.append(p)
            dst.append(T.pt_to_px(x, y, dpi))
    src_a, dst_a = np.float32(src), np.float32(dst)
    H, _ = cv2.findHomography(src_a, dst_a, cv2.RANSAC, 5.0)
    if H is None:
        return gray, float("inf")
    projected = cv2.perspectiveTransform(src_a.reshape(-1, 1, 2), H).reshape(-1, 2)
    error = float(np.mean(np.linalg.norm(projected - dst_a, axis=1)))
    canonical = cv2.warpPerspective(gray, H, T.canonical_size(dpi), flags=cv2.INTER_LINEAR, borderValue=255)
    return canonical, error


def _crop(img: np.ndarray, rect: Rect, dpi: int, pad_pt: float = 0.0) -> np.ndarray:
    x0, y0, x1, y1 = rect
    left, top, right, bottom = T.rect_to_px((x0 - pad_pt, y0 - pad_pt, x1 + pad_pt, y1 + pad_pt), dpi)
    h, w = img.shape[:2]
    return img[max(top, 0):min(bottom, h), max(left, 0):min(right, w)]


def read_qr(canonical: np.ndarray, dpi: int) -> str | None:
    crop = _crop(canonical, T.QR_RECT, dpi, pad_pt=12)
    _, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    attempts = [crop, binary, cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)]
    for detector in (cv2.QRCodeDetector(), cv2.QRCodeDetectorAruco()):
        for img in attempts:
            text, _, _ = detector.detectAndDecode(img)
            if text:
                return text
    return None


@cache
def _disk(radius_px: int) -> np.ndarray:
    yy, xx = np.mgrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    return (xx * xx + yy * yy) <= radius_px * radius_px


def bubble_fill(canonical: np.ndarray, cx: float, cy: float, radius_px: int) -> float:
    x, y = round(cx), round(cy)
    patch = canonical[y - radius_px:y + radius_px + 1, x - radius_px:x + radius_px + 1]
    disk = _disk(radius_px)
    if patch.shape != disk.shape:
        return 0.0
    return float(np.mean(patch[disk] < DARK))


def read_student_id(canonical: np.ndarray, grid: IdGrid, dpi: int) -> tuple[str | None, str | None]:
    """Returns (student_id, None) or (None, why it couldn't be read)."""
    # Sample only the center of each bubble so the printed outline doesn't count.
    radius_px = max(2, round(grid.bubble_r * T.scale(dpi) * 0.6))
    digits = []
    for d, row in enumerate(grid.centers, start=1):
        fills = [bubble_fill(canonical, *T.pt_to_px(cx, cy, dpi), radius_px) for cx, cy in row]
        ranked = sorted(range(10), key=lambda v: fills[v], reverse=True)
        best, runner_up = fills[ranked[0]], fills[ranked[1]]
        if best < BUBBLE_FILLED:
            return None, f"ID digit {d} has no bubble filled"
        if runner_up >= BUBBLE_FILLED or runner_up >= BUBBLE_AMBIGUOUS * best:
            return None, f"ID digit {d} has two bubbles marked ({ranked[0]} and {ranked[1]})"
        digits.append(str(ranked[0]))
    return "".join(digits), None


def ingest(scan_pdfs: Path | list[Path], assignment_dir: Path, workdir: Path, dpi: int = T.DPI) -> IngestResult:
    """Scans can be one PDF or several (fronts and backs scanned separately); order doesn't matter."""
    scan_pdfs = [scan_pdfs] if isinstance(scan_pdfs, (str, Path)) else list(scan_pdfs)
    layout, _ = load_assignment(assignment_dir)
    workdir = Path(workdir)
    (workdir / "pages").mkdir(parents=True, exist_ok=True)
    (workdir / "raw").mkdir(parents=True, exist_ok=True)

    grays = [gray for pdf in scan_pdfs for gray in render_pages(pdf, dpi)]
    results: list[PageScan] = []
    for index, gray in enumerate(grays, start=1):
        scan = _ingest_page(index, gray, layout, workdir, dpi)
        if scan.status == "review":
            raw = workdir / "raw" / f"scan-{index:03}.png"
            cv2.imwrite(str(raw), gray)
            scan.raw_image = str(raw.relative_to(workdir))
        results.append(scan)

    _flag_duplicates(results)
    result = IngestResult(
        source_pdfs=[str(Path(p).resolve()) for p in scan_pdfs],
        assignment_dir=str(Path(assignment_dir).resolve()), dpi=dpi, pages=results,
    )
    save(result, workdir / "ingest.json")
    return result


def _ingest_page(index: int, gray: np.ndarray, layout, workdir: Path, dpi: int) -> PageScan:
    markers = find_markers(gray)
    if len(markers) < 3:
        if np.mean(gray < DARK) < BLANK_INK_FRACTION:
            return PageScan(scan_index=index, status="blank")
        return PageScan(scan_index=index, status="review",
                        reason=f"found {len(markers)} of 4 corner squares; can't line the page up")

    canonical, error = register(gray, markers, dpi)
    if error > MAX_REPROJECTION_PX:
        return PageScan(scan_index=index, status="review",
                        reason=f"page didn't line up cleanly (error {error:.1f}px); torn or folded?")

    image = workdir / "pages" / f"scan-{index:03}.png"
    cv2.imwrite(str(image), canonical)
    scan = PageScan(scan_index=index, status="review", image=str(image.relative_to(workdir)))

    payload = read_qr(canonical, dpi)
    parsed = T.parse_qr_payload(payload) if payload else None
    if parsed is None:
        scan.reason = "QR code unreadable" if payload is None else f"QR code not from Paper Loop: {payload!r}"
        return scan
    assignment_id, page_no = parsed
    scan.assignment_id, scan.page = assignment_id, page_no
    if assignment_id != layout.assignment_id:
        scan.reason = f"page belongs to a different assignment ({assignment_id})"
        return scan
    try:
        page_layout = layout.page(page_no)
    except KeyError:
        scan.reason = f"{assignment_id} has no page {page_no}"
        return scan

    student_id, problem = read_student_id(canonical, page_layout.id_grid, dpi)
    if student_id is None:
        scan.reason = problem
        return scan
    scan.student_id = student_id
    scan.status = "ok"
    return scan


def _flag_duplicates(pages: list[PageScan]) -> None:
    seen: dict[tuple[str, int], list[PageScan]] = defaultdict(list)
    for p in pages:
        if p.status == "ok":
            seen[(p.student_id, p.page)].append(p)
    for (student_id, page_no), dupes in seen.items():
        if len(dupes) > 1:
            where = ", ".join(str(p.scan_index) for p in dupes)
            for p in dupes:
                p.status = "review"
                p.reason = f"student {student_id} page {page_no} appears more than once (scans {where})"


def page_map(result: IngestResult, n_pages: int) -> str:
    """Human-readable table of what ingest found, plus missing pages per student."""
    lines = [f"{'scan':>4}  {'status':<7} {'student':<8} {'page':<4} note"]
    for p in result.pages:
        lines.append(
            f"{p.scan_index:>4}  {p.status:<7} {p.student_id or '-':<8} {p.page or '-'!s:<4} {p.reason or ''}".rstrip()
        )
    found: dict[str, set[int]] = defaultdict(set)
    for p in result.pages:
        if p.status == "ok":
            found[p.student_id].add(p.page)
    counts = {s: len(v) for s, v in found.items()}
    missing = [f"{s} missing page {sorted(set(range(1, n_pages + 1)) - v)}" for s, v in sorted(found.items())
               if len(v) < n_pages]
    status = defaultdict(int)
    for p in result.pages:
        status[p.status] += 1
    lines.append("")
    lines.append(f"{len(counts)} students, {status['ok']} pages ok, {status['blank']} blank, "
                 f"{status['review']} for review")
    lines.extend(missing)
    return "\n".join(lines)
