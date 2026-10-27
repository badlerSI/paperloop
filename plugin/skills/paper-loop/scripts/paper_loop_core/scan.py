"""From a scanned page to a page lined up with its template, using numpy and scipy only.

The four corner markers give a homography; then the printing itself is lined up patch by patch to
take out the bow that paper curl and the copier's feeder leave in the middle of a page. After
that, every rect in layout.json lands on the same pixels of the scan as on the blank template.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from scipy import ndimage

from . import sheet as S

DARK = 160  # grayscale below this counts as ink; printed faint guides sit above it
PRINTED = 200  # anything darker than this on the blank template is printed, including light fills
PRINT_SLACK_PX = 4  # misalignment to forgive around printed ink
MAX_REPROJECTION_PX = 6.0
FLATTEN_TILE_PX = 160  # patches of printing, about 0.8in at 200 dpi, each measured for drift
FLATTEN_MIN_TILES = 8


# --- Pixels in and out ------------------------------------------------------------

def render_pdf(path: Path, dpi: int = S.DPI) -> list[np.ndarray]:
    doc = pdfium.PdfDocument(str(path))
    try:
        return [np.array(doc[i].render(scale=dpi / 72).to_pil().convert("L")) for i in range(len(doc))]
    finally:
        doc.close()


def save_png(img: np.ndarray, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(path)


def load_png(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("L"))


def template(assignment_dir: Path, page: int) -> np.ndarray:
    """The blank page as printed, rendered once and kept beside the worksheet."""
    path = Path(assignment_dir) / f"template-p{page}.png"
    if not path.exists():
        for n, img in enumerate(render_pdf(Path(assignment_dir) / "worksheet.pdf"), start=1):
            save_png(img, Path(assignment_dir) / f"template-p{n}.png")
    return load_png(path)


def crop(img: np.ndarray, rect, inset_pt: float = 0.0, dpi: int = S.DPI) -> np.ndarray:
    left, top, right, bottom = S.rect_to_px(rect, dpi, inset_pt)
    h, w = img.shape[:2]
    return img[max(top, 0):min(bottom, h), max(left, 0):min(right, w)]


def student_ink(canonical: np.ndarray, blank: np.ndarray) -> np.ndarray:
    """Boolean mask of ink on the scan that isn't on the printed page, specks removed."""
    size = 2 * PRINT_SLACK_PX + 1
    printed = ndimage.binary_dilation(blank < PRINTED, structure=np.ones((size, size), bool))
    ink = (canonical < DARK) & ~printed
    return ndimage.binary_opening(ink, structure=np.ones((2, 2), bool))


# --- Corner markers --------------------------------------------------------------

def _otsu(gray: np.ndarray) -> float:
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    weight = np.cumsum(hist)
    mean = np.cumsum(hist * np.arange(256))
    total, total_mean = weight[-1], mean[-1]
    between = (total_mean * weight - mean * total) ** 2 / np.maximum(weight * (total - weight), 1)
    return float(np.argmax(between))


def _square_corners(mask: np.ndarray, offset: tuple[int, int]) -> np.ndarray:
    """Corners of a filled, roughly upright square: top-left, top-right, bottom-right, bottom-left (x, y)."""
    ys, xs = np.nonzero(mask)
    xs, ys = xs + offset[1], ys + offset[0]
    s, d = xs + ys, xs - ys
    picks = [np.argmin(s), np.argmax(d), np.argmax(s), np.argmin(d)]
    return np.array([[xs[i], ys[i]] for i in picks], dtype=float)


def _sample_grid(gray: np.ndarray, corners: np.ndarray, n: int = 6) -> np.ndarray:
    """Mean gray of each cell center in an n x n grid spanning the quad (rows top to bottom)."""
    tl, tr, br, bl = corners
    out = np.zeros((n, n))
    for r in range(n):
        for c in range(n):
            u, v = (c + 0.5) / n, (r + 0.5) / n
            x, y = (1 - u) * (1 - v) * tl + u * (1 - v) * tr + u * v * br + (1 - u) * v * bl
            xi, yi = int(round(x)), int(round(y))
            patch = gray[max(yi - 2, 0):yi + 3, max(xi - 2, 0):xi + 3]
            out[r, c] = patch.mean() if patch.size else 255
    return out


def find_markers(gray: np.ndarray, dpi: int = S.DPI) -> dict[int, np.ndarray]:
    """Marker id -> its 4 corners in image pixels, in the marker's own TL, TR, BR, BL order."""
    threshold = _otsu(gray)
    dark = gray < threshold
    labels, _ = ndimage.label(dark, structure=np.ones((3, 3), bool))
    side = S.MARKER_SIZE * S.scale(dpi)
    patterns = {mid: np.array([[c == "1" for c in row] for row in bits]) for mid, bits in S.MARKER_BITS.items()}
    found: dict[int, tuple[float, np.ndarray]] = {}
    for n, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (0.6 * side < h < 1.5 * side and 0.6 * side < w < 1.5 * side) or abs(h - w) > 0.25 * max(h, w):
            continue
        filled = ndimage.binary_fill_holes(labels[sl] == n)
        if filled.mean() < 0.8:
            continue
        corners = _square_corners(filled, (sl[0].start, sl[1].start))
        cells = _sample_grid(gray, corners) < threshold  # True = dark
        border = np.concatenate([cells[0], cells[-1], cells[1:-1, 0], cells[1:-1, -1]])
        if border.mean() < 0.85:
            continue
        inner_white = ~cells[1:5, 1:5]
        for mid, pattern in patterns.items():
            for k in range(4):
                errors = int((np.rot90(inner_white, k) != pattern).sum())
                if errors <= 1 and (mid not in found or errors < found[mid][0]):
                    # Rotating the sampled grid k quarter-turns counterclockwise matches the pattern,
                    # so the marker's own corner j sits at image corner j + k.
                    found[mid] = (errors, np.array([corners[(j + k) % 4] for j in range(4)]))
    return {mid: c for mid, (_, c) in found.items()}


# --- Homography and warping ---------------------------------------------------------

def _normalizer(pts: np.ndarray) -> np.ndarray:
    center = pts.mean(axis=0)
    spread = np.sqrt(((pts - center) ** 2).sum(axis=1)).mean() / np.sqrt(2)
    return np.array([[1 / spread, 0, -center[0] / spread], [0, 1 / spread, -center[1] / spread], [0, 0, 1]])


def homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares 3x3 homography mapping src points to dst points (normalized DLT)."""
    ts, td = _normalizer(src), _normalizer(dst)
    s = (ts @ np.c_[src, np.ones(len(src))].T).T
    d = (td @ np.c_[dst, np.ones(len(dst))].T).T
    rows = []
    for (x, y, _), (u, v, _) in zip(s, d):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.array(rows))
    h = np.linalg.inv(td) @ vt[-1].reshape(3, 3) @ ts
    return h / h[2, 2]


def project(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    p = np.c_[pts, np.ones(len(pts))] @ h.T
    return p[:, :2] / p[:, 2:3]


def register(gray: np.ndarray, markers: dict[int, np.ndarray], dpi: int = S.DPI) -> tuple[np.ndarray, float]:
    """Warp a scanned page onto the template. Returns (canonical image, mean reprojection error in px).

    If one marker was misread (a smudge, a fold), the fit leaving it out wins."""
    corr = {}
    for mid, pts in markers.items():
        x0, y0, x1, y1 = S.MARKER_RECTS[mid]
        corr[mid] = (pts, np.array([S.pt_to_px(x, y, dpi) for x, y in [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]]))
    candidates = [list(corr)]
    if len(corr) == 4:
        candidates += [[m for m in corr if m != out] for out in corr]
    best = None
    for ids in candidates:
        src = np.concatenate([corr[m][0] for m in ids])
        dst = np.concatenate([corr[m][1] for m in ids])
        h = homography(src, dst)
        error = float(np.linalg.norm(project(h, src) - dst, axis=1).mean())
        if best is None or error < best[1] - 0.5:  # prefer all four markers unless dropping one clearly helps
            best = (h, error)
    h, error = best
    w, hgt = S.canonical_size(dpi)
    ys, xs = np.mgrid[0:hgt, 0:w].astype(np.float64)
    inv = np.linalg.inv(h)
    den = inv[2, 0] * xs + inv[2, 1] * ys + inv[2, 2]
    sx = (inv[0, 0] * xs + inv[0, 1] * ys + inv[0, 2]) / den
    sy = (inv[1, 0] * xs + inv[1, 1] * ys + inv[1, 2]) / den
    canonical = ndimage.map_coordinates(gray, [sy, sx], order=1, cval=255).astype(np.uint8)
    return canonical, error


# --- Flattening ------------------------------------------------------------------------

def phase_shift(a: np.ndarray, b: np.ndarray, window: np.ndarray) -> tuple[float, float, float]:
    """How far b's content sits from a's: (dx, dy, response). Response near 1 means a clean match."""
    fa, fb = np.fft.fft2(a * window), np.fft.fft2(b * window)
    cross = np.conj(fa) * fb
    surface = np.fft.ifft2(cross / (np.abs(cross) + 1e-9)).real
    h, w = surface.shape
    py, px = np.unravel_index(np.argmax(surface), surface.shape)
    ys, xs = np.mgrid[-2:3, -2:3]
    patch = surface[(py + ys) % h, (px + xs) % w]
    weights = np.clip(patch, 0, None)
    total = weights.sum()
    dy = py + (weights * ys).sum() / total if total > 0 else py
    dx = px + (weights * xs).sum() / total if total > 0 else px
    dy = dy - h if dy > h / 2 else dy
    dx = dx - w if dx > w / 2 else dx
    return float(dx), float(dy), float(patch.sum())


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
    near_print = ndimage.binary_dilation(printed, structure=np.ones((17, 17), bool))
    handwriting = (canonical < DARK) & ~near_print
    window = np.outer(np.hanning(t), np.hanning(t))
    # Ink as bright on black: a white background would match itself (and the window) at zero shift.
    template_f, scan_f = 255 - blank.astype(np.float64), 255 - canonical.astype(np.float64)
    centers, shifts = [], []
    for y in range(0, h - t + 1, t // 2):
        for x in range(0, w - t + 1, t // 2):
            if printed[y:y + t, x:x + t].mean() < 0.02 or handwriting[y:y + t, x:x + t].mean() > 0.001:
                continue
            dx, dy, response = phase_shift(template_f[y:y + t, x:x + t], scan_f[y:y + t, x:x + t], window)
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
    u = (np.arange(w) / w - 0.5)[None, :]
    v = (np.arange(h) / h - 0.5)[:, None]
    dx, dy = _quadratic(coef[:, 0], u, v), _quadratic(coef[:, 1], u, v)
    if max(np.abs(dx).max(), np.abs(dy).max()) < 0.5:
        return canonical  # already flat: don't blur it with another resample
    xs = np.arange(w)[None, :] + dx
    ys = np.arange(h)[:, None] + dy
    return ndimage.map_coordinates(canonical, [ys, xs], order=1, cval=255).astype(np.uint8)


# --- Reading the page -----------------------------------------------------------------

def read_code(canonical: np.ndarray, dpi: int = S.DPI) -> tuple[int, int] | None:
    """(assignment hash, page) from the page code, or None if there isn't a readable one."""
    means = []
    for rect in S.code_cells():
        cell = crop(canonical, rect, inset_pt=(rect[2] - rect[0]) * 0.25, dpi=dpi)
        means.append(float(cell.mean()) if cell.size else 255.0)
    lo, hi = min(means), max(means)
    if hi - lo < 60:
        return None  # all one shade: no code here (an older sheet with a QR code, or a blank corner)
    cut = (lo + hi) / 2
    return S.parse_code([int(m < cut) for m in means])


def page_match(canonical: np.ndarray, blank: np.ndarray, dpi: int = S.DPI) -> float:
    """Share of the template's solid printing in the question area that's also dark on the scan.
    On the day-2 scans: 0.98 or more for the right page, 0.30 or less for other worksheets, whose
    markers, header, and footer are the same, so those are left out."""
    solid = ndimage.binary_erosion(blank < 100, structure=np.ones((3, 3), bool))
    _, top, _, bottom = S.rect_to_px((0, S.SUMMARY_RECT[1], S.PAGE_W, S.CONTENT_TOP), dpi)
    solid[:top], solid[bottom:] = False, False
    if not solid.any():
        return 0.0
    dark_near = ndimage.minimum_filter(canonical, size=3) < DARK
    return float(dark_near[solid].mean())
