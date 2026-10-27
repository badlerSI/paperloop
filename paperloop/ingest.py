"""Ingest: split a scanned class set, deskew each page, read its QR code and student ID.

Pages come in any order and orientation. The four corner markers give a
homography to the template, and the printed content then corrects the bow that
paper curl and the feeder leave in the middle of the page, so every later step
works in template coordinates.
Anything that can't be read for certain goes to the review pile; never guess.
"""

from __future__ import annotations

from collections import defaultdict
from functools import cache
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import raster
from . import template as T
from .make import load_assignment
from .raster import DARK, PRINTED, load_template, render_pages, student_ink
from .schemas import IdGrid, IngestResult, PageScan, Rect, Usage, save

BLANK_INK_FRACTION = 0.002
ID_MIN_INK_PX = 80  # student ink in the ID boxes below this means nothing was written
ID_CONFIDENCE = 0.9  # stricter than marking: a misread ID hands one student's work to another
# On real handwriting the model's confidence sits at 0.6-0.9 even for reads that are right (an open 0
# looks like a 6 to it), so with a roster a lower bar is enough when no one-digit slip could reach this ID.
ID_CONFIDENCE_ON_ROSTER = 0.5
BUBBLE_FILLED = 0.35  # share of a bubble's center that must be dark to count as filled
BUBBLE_AMBIGUOUS = 0.6  # a runner-up this close to the darkest bubble makes the digit ambiguous
MAX_REPROJECTION_PX = 6.0
FLATTEN_TILE_PX = 160  # patches of printing, about 0.8in at 200 dpi, each measured for drift
FLATTEN_MIN_TILES = 8


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


def _quadratic(c: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return c[0] + c[1] * u + c[2] * v + c[3] * u * u + c[4] * u * v + c[5] * v * v


def flatten(canonical: np.ndarray, blank: np.ndarray) -> np.ndarray:
    """Undo what four corner markers can't: paper curl and the feeder bow the middle of a page several
    pixels off the template while the corners line up. Measures how far printed-only patches drifted,
    fits a smooth (quadratic) warp to those shifts, and resamples the scan through it."""
    h, w = blank.shape
    t = FLATTEN_TILE_PX
    printed = blank < PRINTED
    # Judge handwriting generously, so drifted printing isn't mistaken for it; patches with any are skipped.
    near_print = cv2.dilate(printed.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool)
    handwriting = (canonical < DARK) & ~near_print
    window = cv2.createHanningWindow((t, t), cv2.CV_32F)
    # Ink as bright on black: a white background would match itself (and the window) at zero shift.
    template_f, scan_f = 255 - blank.astype(np.float32), 255 - canonical.astype(np.float32)
    centers, shifts = [], []
    for y in range(0, h - t + 1, t // 2):
        for x in range(0, w - t + 1, t // 2):
            if printed[y:y + t, x:x + t].mean() < 0.02 or handwriting[y:y + t, x:x + t].mean() > 0.001:
                continue
            (dx, dy), response = cv2.phaseCorrelate(template_f[y:y + t, x:x + t], scan_f[y:y + t, x:x + t], window)
            if response > 0.2 and abs(dx) < 15 and abs(dy) < 15:
                centers.append(((x + t / 2) / w - 0.5, (y + t / 2) / h - 0.5))
                shifts.append((dx, dy))
    if len(centers) < FLATTEN_MIN_TILES:
        return canonical
    centers, shifts = np.array(centers), np.array(shifts)
    terms = np.stack([np.ones(len(centers)), centers[:, 0], centers[:, 1],
                      centers[:, 0] ** 2, centers[:, 0] * centers[:, 1], centers[:, 1] ** 2], axis=1)
    keep = np.ones(len(terms), bool)
    for _ in range(2):  # refit without patches the smooth warp doesn't explain (a repeating pattern, a stray mark)
        coef, *_ = np.linalg.lstsq(terms[keep], shifts[keep], rcond=None)
        keep = np.linalg.norm(terms @ coef - shifts, axis=1) < 1.5
        if keep.sum() < FLATTEN_MIN_TILES:
            return canonical
    coef, *_ = np.linalg.lstsq(terms[keep], shifts[keep], rcond=None)
    u = (np.arange(w, dtype=np.float32) / w - 0.5)[None, :]
    v = (np.arange(h, dtype=np.float32) / h - 0.5)[:, None]
    dx, dy = _quadratic(coef[:, 0], u, v), _quadratic(coef[:, 1], u, v)
    if max(np.abs(dx).max(), np.abs(dy).max()) < 0.5:
        return canonical  # already flat: don't blur it with another resample
    map_x = (np.arange(w, dtype=np.float32)[None, :] + dx).astype(np.float32)
    map_y = (np.arange(h, dtype=np.float32)[:, None] + dy).astype(np.float32)
    return cv2.remap(canonical, map_x, map_y, cv2.INTER_LINEAR, borderValue=255)


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


def ingest(scan_pdfs: Path | list[Path], assignment_dir: Path, workdir: Path, dpi: int = T.DPI,
           id_reader: Callable | None = None, roster: set[str] | None = None) -> IngestResult:
    """Scans can be one PDF or several (fronts and backs scanned separately); order doesn't matter.

    Handwritten IDs need `id_reader` (a marker's `read_id`); without one those pages go to review.
    `roster` is the set of valid IDs, if known: anything else goes to review rather than to a stranger.
    """
    scan_pdfs = [scan_pdfs] if isinstance(scan_pdfs, (str, Path)) else list(scan_pdfs)
    layout, _ = load_assignment(assignment_dir)
    workdir = Path(workdir)
    (workdir / "pages").mkdir(parents=True, exist_ok=True)
    (workdir / "raw").mkdir(parents=True, exist_ok=True)

    grays = [gray for pdf in scan_pdfs for gray in render_pages(pdf, dpi)]
    results: list[PageScan] = []
    id_usage = Usage()
    for index, gray in enumerate(grays, start=1):
        scan = _ingest_page(index, gray, layout, Path(assignment_dir), workdir, dpi, id_reader, roster, id_usage)
        if scan.status == "review":
            raw = workdir / "raw" / f"scan-{index:03}.png"
            cv2.imwrite(str(raw), gray)
            scan.raw_image = str(raw.relative_to(workdir))
        results.append(scan)

    _flag_duplicates(results)
    result = IngestResult(
        source_pdfs=[str(Path(p).resolve()) for p in scan_pdfs],
        assignment_dir=str(Path(assignment_dir).resolve()), dpi=dpi, pages=results, id_usage=id_usage,
    )
    save(result, workdir / "ingest.json")
    return result


def _one_digit_apart(a: str, b: str) -> bool:
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def read_written_id(canonical: np.ndarray, boxes: list[Rect], assignment_dir: Path, page: int, dpi: int,
                    id_reader: Callable | None, usage: Usage,
                    roster: set[str] | None = None) -> tuple[str | None, str | None]:
    """Handwritten ID: crop only the ID boxes and have the model read them in a request of their own.

    Below ID_CONFIDENCE, a read is still accepted if it's on the roster and no other roster ID is one
    digit away: a misread usually changes one digit, so it can't have come from a classmate's ID.
    """
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    region = (x0 - 3, y0 - 3, x1 + 3, y1 + 3)
    ink = student_ink(canonical, load_template(str(assignment_dir), page))
    if int(raster.crop(ink, region, dpi).sum()) < ID_MIN_INK_PX:
        return None, "no ID written"
    if id_reader is None:
        return None, "handwritten ID needs the model to read it (no API key, or --mock)"
    png = cv2.imencode(".png", raster.crop(canonical, region, dpi))[1].tobytes()
    try:
        read, u = id_reader(png, len(boxes))
    except Exception as e:  # never route on a failed read
        return None, f"ID couldn't be read ({type(e).__name__})"
    usage.add(u)
    digits = "".join(read.digits)
    if len(read.digits) != len(boxes) or not digits.isdigit():
        return None, f"ID read as {digits or 'nothing'!r}: not {len(boxes)} clear digits"
    if read.confidence >= ID_CONFIDENCE:
        return digits, None
    if roster is not None and digits in roster and read.confidence >= ID_CONFIDENCE_ON_ROSTER:
        neighbor = next((other for other in sorted(roster) if _one_digit_apart(other, digits)), None)
        if neighbor is None:
            return digits, None
        return None, f"ID read as {digits} ({read.confidence:.2f} sure), but {neighbor} on the roster is one digit away"
    return None, f"ID read as {digits}, but only {read.confidence:.2f} sure"


def _ingest_page(index: int, gray: np.ndarray, layout, assignment_dir: Path, workdir: Path, dpi: int,
                 id_reader: Callable | None, roster: set[str] | None, id_usage: Usage) -> PageScan:
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
    canonical = flatten(canonical, load_template(str(assignment_dir), page_no))
    cv2.imwrite(str(image), canonical)

    if page_layout.id_grid:
        student_id, problem = read_student_id(canonical, page_layout.id_grid, dpi)
    else:
        student_id, problem = read_written_id(canonical, page_layout.id_boxes, assignment_dir, page_no, dpi,
                                              id_reader, id_usage, roster)
    if student_id is None:
        scan.reason = problem
        return scan
    if roster is not None and student_id not in roster:
        scan.reason = f"ID {student_id} isn't on the class roster"
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
