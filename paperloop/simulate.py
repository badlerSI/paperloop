"""Simulate: fake a filled-in, scanned class set so the pipeline runs without a printer.

Writes answers in handwriting-style system fonts, fills ID bubbles, then adds
scan damage: skew, shift, blur, noise, one sheet fed upside down, a blank page,
and shuffled order. Also writes truth.json with what each page really says, so
tests can measure routing, misreads, and silent autocorrect.

This is a stand-in for Day 1's hand-filled copies, not a replacement for them.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import template as T
from .ingest import render_pages
from .make import load_assignment

FONT_DIRS = [Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts"), Path("/Library/Fonts")]

# Four copies, matching Day 1: clean, messy, crossed out with misspellings, blank.
# ~~word~~ is written and then struck through. Misspellings are listed so tests
# can check the transcription kept them (silent autocorrect).
STUDENTS = [
    {
        "id": "0417", "style": "clean", "font": "Noteworthy.ttc",
        "answers": {
            1: ("Ice is less dense than liquid water, so it floats.", [], "correct"),
            2: ("D = m / V = 40 g / 20 cm3 = 2 g/cm3", [], "correct"),
            3: ("It stays the same. Both the mass and the volume are cut in half.", [], "correct"),
            4: ("Oil is less dense than water.", [], "correct"),
            5: ("The log has more volume, so it is less dense than water and floats. "
                "The rock has less volume, so it is denser than water and sinks.", [], "correct"),
        },
    },
    {
        "id": "2093", "style": "messy", "font": "Bradley Hand Bold.ttf",
        "answers": {
            1: ("ice is lighter then water", ["then"], "partial"),
            2: ("2", [], "partial"),
            3: ("each half is half as dense", [], "incorrect"),
            4: ("oil is thicker than water", [], "incorrect"),
            5: ("the log is bigger", [], "partial"),
        },
    },
    {
        "id": "3158", "style": "crossed", "font": "ChalkboardSE.ttc",
        "answers": {
            1: ("Ice is less ~~heavy~~ dense then water", ["then"], "correct"),
            2: ("denisty = 40/20 = 2 g/cm3", ["denisty"], "correct"),
            3: ("the densty stays the same becuase its the same wood", ["densty", "becuase"], "correct"),
            4: ("oil is less dence than water", ["dence"], "correct"),
            5: ("the rock has ~~more~~ less volume so it is more dense", [], "partial"),
        },
    },
    {"id": "0006", "style": "blank", "font": "MarkerFelt.ttc", "answers": {}},
]


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


def _fill_id(draw: ImageDraw.ImageDraw, grid, student_id: str, font, rng: random.Random, ink: int, dpi: int) -> None:
    s = T.scale(dpi)
    for d, digit in enumerate(student_id):
        x0, y0, x1, y1 = T.rect_to_px(grid.writein_rects[d], dpi)
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), digit, font=font, fill=ink, anchor="mm")
        cx, cy = T.pt_to_px(*grid.centers[d][int(digit)], dpi)
        r = grid.bubble_r * s * rng.uniform(0.8, 0.95)
        jx, jy = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        draw.ellipse([cx - r + jx, cy - r * 0.9 + jy, cx + r + jx, cy + r * 0.9 + jy], fill=ink)


def _scan_damage(img: np.ndarray, rng: random.Random, angle: float, flip: bool) -> np.ndarray:
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle + (180 if flip else 0), rng.uniform(0.985, 1.01))
    m[:, 2] += (rng.uniform(-18, 18), rng.uniform(-18, 18))
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=250)
    out = cv2.GaussianBlur(out, (0, 0), 0.7)
    noise = np.random.default_rng(rng.randint(0, 2**31)).normal(0, 6, out.shape)
    return np.clip(out.astype(np.float32) * 0.97 + noise + 4, 0, 255).astype(np.uint8)


def simulate(assignment_dir: Path, out_pdf: Path, seed: int = 7, dpi: int = T.DPI) -> Path:
    """Write a fake scanned class set and truth.json beside it. Returns the PDF path."""
    assignment_dir, out_pdf = Path(assignment_dir), Path(out_pdf)
    layout, _ = load_assignment(assignment_dir)
    rng = random.Random(seed)
    blanks = render_pages(assignment_dir / "worksheet.pdf", dpi)

    sheets = []  # (image, truth)
    for student in STUDENTS:
        hand = _font(student["font"], round(15 * T.scale(dpi)))
        ink = 70 if student["style"] == "messy" else 45
        flip = student["style"] == "messy"  # one sheet goes through the feeder upside down
        for page_layout, blank in zip(layout.pages, blanks):
            pil = Image.fromarray(blank.copy())
            draw = ImageDraw.Draw(pil)
            _fill_id(draw, page_layout.id_grid, student["id"], hand, rng, ink, dpi)
            for box in page_layout.boxes:
                if box.q in student["answers"]:
                    _write_box(draw, box.rect, student["answers"][box.q][0], hand, rng, ink, dpi)
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
        "students": [
            {
                "id": s["id"], "style": s["style"],
                "answers": {
                    str(q): {"text": text, "misspellings": miss, "expected": expected}
                    for q, (text, miss, expected) in s["answers"].items()
                },
            }
            for s in STUDENTS
        ],
    }
    (out_pdf.with_suffix(".truth.json")).write_text(json.dumps(truth, indent=2) + "\n")
    return out_pdf
