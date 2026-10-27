"""Turn a clean scanned page into what a phone camera would produce, for testing scan robustness.

    .venv/bin/python devtools/photo.py IN.pdf PAGE OUT.jpg [--tilt 12] [--shadow 0.5] [--seed 3]

Perspective tilt, a shadow falling across the page, a warm color cast, blur, a dark table around the page,
lower resolution, and JPEG compression. Dev only, never shipped.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "skills" / "paper-loop" / "scripts"))
from paper_loop_core import scan as L  # noqa: E402


def _coeffs(src, dst):
    """PIL perspective coefficients mapping output (dst) points back to input (src) points."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs += [u, v]
    return np.linalg.solve(np.array(rows, float), np.array(rhs, float))


def photo(page: np.ndarray, tilt: float = 12.0, shadow: float = 0.5, seed: int = 3, out_w: int = 1500,
          out_h: int = 2000) -> Image.Image:
    rng = random.Random(seed)
    h, w = page.shape
    img = Image.fromarray(page).convert("RGB")
    # Where the page's corners land in the photo: inset from the frame, pulled in at the top (camera tilt).
    k = tilt / 100
    m = 0.07
    dst = [(out_w * (m + k), out_h * m), (out_w * (1 - m - k * 0.8), out_h * (m + 0.01)),
           (out_w * (1 - m + 0.01), out_h * (1 - m)), (out_w * m, out_h * (1 - m - 0.015))]
    dst = [(x + rng.uniform(-12, 12), y + rng.uniform(-12, 12)) for x, y in dst]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    table = Image.new("RGB", (out_w, out_h), (58, 52, 47))
    warped = img.transform((out_w, out_h), Image.PERSPECTIVE, tuple(_coeffs(src, dst)), Image.BICUBIC,
                           fillcolor=(58, 52, 47))
    mask = Image.new("L", (w, h), 255).transform((out_w, out_h), Image.PERSPECTIVE, tuple(_coeffs(src, dst)),
                                                  Image.BICUBIC, fillcolor=0)
    table.paste(warped, (0, 0), mask)
    arr = np.asarray(table).astype(np.float32)
    yy, xx = np.mgrid[0:out_h, 0:out_w]
    light = 1 - shadow * np.clip((xx / out_w + yy / out_h - 0.8), 0, 1)  # a shadow over the lower right
    arr *= light[..., None]
    arr *= np.array([1.0, 0.96, 0.86])  # warm indoor light
    arr += np.random.default_rng(seed).normal(0, 5, arr.shape)
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("page", type=int)
    ap.add_argument("out", type=Path)
    ap.add_argument("--tilt", type=float, default=12.0)
    ap.add_argument("--shadow", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    page = L.render_pdf(a.pdf, 200)[a.page - 1]
    photo(page, a.tilt, a.shadow, a.seed).save(a.out, quality=82)
    print(f"wrote {a.out}")
