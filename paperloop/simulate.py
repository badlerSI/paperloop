"""Simulate: fake a filled-in, scanned class set so the pipeline runs without a printer.

Each worksheet's fake students live in examples/<assignment_id>.students.json:
what they write, circle, label, and draw. This writes their answers in
handwriting-style system fonts, fills the ID bubbles, then adds scan damage:
skew, shift, blur, noise, one sheet fed upside down, a blank page, and
shuffled order. It also writes truth.json, so tests can measure routing,
misreads, and silent autocorrect.

This is a stand-in for hand-filled copies, not a replacement for them.
"""

from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import template as T
from .make import load_assignment
from .raster import render_pages
from .schemas import Box, WorksheetDef, load

FONT_DIRS = [Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts"), Path("/Library/Fonts")]
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
HAND_PT = 15  # handwriting size


def students_path(assignment_id: str) -> Path:
    return EXAMPLES_DIR / f"{assignment_id}.students.json"


def load_students(assignment_id: str, path: Path | None = None) -> dict:
    path = Path(path) if path else students_path(assignment_id)
    if not path.exists():
        raise FileNotFoundError(f"No simulated students for {assignment_id}: expected {path}")
    return json.loads(path.read_text())


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size)


def _write_box(draw: ImageDraw.ImageDraw, rect, text: str, font, rng: random.Random, ink: int, dpi: int) -> None:
    """Write words left to right on the box's ruled lines, wrapping, with a little wobble."""
    left, top, right, bottom = T.rect_to_px(rect, dpi)
    line_h = round(22 * T.scale(dpi))
    x, baseline = left + 14, top + line_h - 10
    for token in re.findall(r"~~[^~]+~~|\S+", text):
        crossed = token.startswith("~~")
        word = token.strip("~")
        width = draw.textlength(word + " ", font=font)
        if x + width > right - 10:
            x, baseline = left + 14 + rng.randint(-4, 4), baseline + line_h
            if baseline > bottom - 4:
                return
        y = baseline + rng.randint(-3, 3)
        draw.text((x, y), word, font=font, fill=ink, anchor="ls")
        if crossed:
            w = draw.textlength(word, font=font)
            mid = y - font.size * 0.3
            draw.line([(x - 3, mid + 2), (x + w + 3, mid - 2)], fill=ink, width=3)
        x += width


def _write_label(draw: ImageDraw.ImageDraw, rect, text: str, font_name: str, rng: random.Random,
                 ink: int, dpi: int) -> None:
    """Write one label inside its box, shrinking the writing to fit like a kid would."""
    left, top, right, bottom = T.rect_to_px(rect, dpi)
    size = round(13 * T.scale(dpi))
    font = _font(font_name, size)
    while draw.textlength(text, font=font) > (right - left) - 34 and size > 18:
        size -= 2
        font = _font(font_name, size)
    draw.text((left + 26 + rng.randint(-3, 3), bottom - 14 + rng.randint(-2, 2)), text,
              font=font, fill=ink, anchor="ls")


def _circle_option(draw: ImageDraw.ImageDraw, box: Box, letter: str, crossed: bool, rng: random.Random,
                   ink: int, dpi: int) -> None:
    spot = next(o for o in box.options if o.letter == letter)
    cx, cy = T.pt_to_px(*spot.letter_at, dpi)
    s = T.scale(dpi)
    cx, cy = cx + rng.uniform(-1.5, 1.5) * s, cy + rng.uniform(-1.5, 1.5) * s
    rx, ry = rng.uniform(10, 12) * s, rng.uniform(8, 9.5) * s
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=ink, width=4)
    if crossed:
        draw.line([(cx - rx, cy - ry), (cx + rx, cy + ry)], fill=ink, width=4)
        draw.line([(cx - rx, cy + ry), (cx + rx, cy - ry)], fill=ink, width=4)


def _draw_particles(draw: ImageDraw.ImageDraw, region, count: int, style: str, rng: random.Random,
                    ink: int, dpi: int) -> None:
    """Same-size particles on a jittered grid, so more particles means closer packing."""
    x, y, w, h = region
    x, y, w, h = x + 6, y + 6, w - 12, h - 12
    cols = max(1, round(math.sqrt(count * w / h)))
    rows = math.ceil(count / cols)
    cells = [(c, r) for r in range(rows) for c in range(cols)]
    rng.shuffle(cells)
    cw, ch = w / cols, h / rows
    radius = 4.5 if style == "circle" else 3.2
    for c, r in cells[:count]:
        px = x + (c + 0.5 + rng.uniform(-0.2, 0.2)) * cw
        py = y + (r + 0.5 + rng.uniform(-0.2, 0.2)) * ch
        (cx, cy), rp = T.pt_to_px(px, py, dpi), radius * T.scale(dpi)
        if style == "dot":
            draw.ellipse([cx - rp, cy - rp, cx + rp, cy + rp], fill=ink)
        else:
            draw.ellipse([cx - rp, cy - rp, cx + rp, cy + rp], outline=ink, width=3)


def _fill_id(draw: ImageDraw.ImageDraw, grid, student_id: str, font, rng: random.Random, ink: int, dpi: int) -> None:
    s = T.scale(dpi)
    for d, digit in enumerate(student_id):
        x0, y0, x1, y1 = T.rect_to_px(grid.writein_rects[d], dpi)
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), digit, font=font, fill=ink, anchor="mm")
        cx, cy = T.pt_to_px(*grid.centers[d][int(digit)], dpi)
        r = grid.bubble_r * s * rng.uniform(0.8, 0.95)
        jx, jy = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        draw.ellipse([cx - r + jx, cy - r * 0.9 + jy, cx + r + jx, cy + r * 0.9 + jy], fill=ink)


def _answer(draw: ImageDraw.ImageDraw, box: Box, answer: dict, defn: WorksheetDef, student: dict,
            hand, rng: random.Random, ink: int, dpi: int) -> None:
    if "text" in answer:
        _write_box(draw, box.rect, answer["text"], hand, rng, ink, dpi)
    if "circle" in answer:
        for mark in answer["circle"]:
            _circle_option(draw, box, mark.strip("~"), mark.startswith("~~"), rng, ink, dpi)
    if "labels" in answer:
        spots = {s.n: s.rect for s in box.labels}
        for n, text in answer["labels"].items():
            _write_label(draw, spots[int(n)], text, student["font"], rng, ink, dpi)
    if "particles" in answer:
        question = next(q for q in defn.questions if q.q == box.q)
        shapes = {s.id: s for s in question.diagram.shapes if s.id}
        ox, oy = box.rect[0], box.rect[1]
        for region_id, spec in answer["particles"].items():
            s = shapes[region_id]
            _draw_particles(draw, (ox + s.x, oy + s.y, s.w, s.h), spec["count"], spec.get("style", "circle"),
                            rng, ink, dpi)


def _scan_damage(img: np.ndarray, rng: random.Random, angle: float, flip: bool) -> np.ndarray:
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle + (180 if flip else 0), rng.uniform(0.985, 1.01))
    m[:, 2] += (rng.uniform(-18, 18), rng.uniform(-18, 18))
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=250)
    out = cv2.GaussianBlur(out, (0, 0), 0.7)
    noise = np.random.default_rng(rng.randint(0, 2**31)).normal(0, 6, out.shape)
    return np.clip(out.astype(np.float32) * 0.97 + noise + 4, 0, 255).astype(np.uint8)


def simulate(assignment_dir: Path, out_pdf: Path, seed: int = 7, students: Path | None = None,
             dpi: int = T.DPI) -> Path:
    """Write a fake scanned class set and truth.json beside it. Returns the PDF path."""
    assignment_dir, out_pdf = Path(assignment_dir), Path(out_pdf)
    layout, _ = load_assignment(assignment_dir)
    defn = load(WorksheetDef, assignment_dir / "worksheet.json")
    roster = load_students(layout.assignment_id, students)
    rng = random.Random(seed)
    blanks = render_pages(assignment_dir / "worksheet.pdf", dpi)

    sheets = []  # (image, truth)
    for student in roster["students"]:
        hand = _font(student["font"], round(HAND_PT * T.scale(dpi)))
        ink = 70 if student["style"] == "messy" else 45
        flip = student["style"] == "messy"  # one sheet goes through the feeder upside down
        for page_layout, blank in zip(layout.pages, blanks):
            pil = Image.fromarray(blank.copy())
            draw = ImageDraw.Draw(pil)
            _fill_id(draw, page_layout.id_grid, student["id"], hand, rng, ink, dpi)
            for box in page_layout.boxes:
                answer = student["answers"].get(str(box.q))
                if answer:
                    _answer(draw, box, answer, defn, student, hand, rng, ink, dpi)
            damaged = _scan_damage(np.array(pil), rng, rng.uniform(-1.8, 1.8), flip)
            sheets.append((damaged, {"student_id": student["id"], "page": page_layout.page, "upside_down": flip}))

    noise = np.random.default_rng(seed).normal(0, 4, blanks[0].shape)
    sheets.append((np.clip(248 + noise, 0, 255).astype(np.uint8), {"blank": True}))
    rng.shuffle(sheets)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.fromarray(img) for img, _ in sheets]
    images[0].save(out_pdf, save_all=True, append_images=images[1:], resolution=dpi)

    truth = {
        "assignment_id": layout.assignment_id,
        "scan_pages": [{"scan_index": i, **t} for i, (_, t) in enumerate(sheets, start=1)],
        "students": roster["students"],
    }
    out_pdf.with_suffix(".truth.json").write_text(json.dumps(truth, indent=2) + "\n")
    return out_pdf
