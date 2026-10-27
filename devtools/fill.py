"""Fill any Paper Loop plugin worksheet with simulated handwriting, for testing the skill's marking.

    .venv/bin/python devtools/fill.py ASSIGNMENT_DIR STUDENTS.json OUT.pdf

STUDENTS.json: {"students": [{"id": "0417", "style": "clean", "answers": {"1": {...}}}]}. Answer specs:
- short: {"text": "..."} (and "more": ["page 2 text", ...] for an essay across pages); plus "expected" (verdict) or "expected_levels" ({"1": 2}) for rubrics,
  and "misspellings" (words that must survive transcription)
- choice: {"circle": ["A"]}, or ["~~C~~", "A"] for circled then crossed out; "expected"
- label, blanks, match, table: {"boxes": {"1": "melting"}, "expected": {"1": "correct"}}
- math: {"work": ["line", ...], "answer": "59", "expected_answer": "correct", "expected_work": "correct"}
- draw: {"sketch": [shapes in diagram coordinates], "expected_items": {"1": "yes"}}
A question left out is left blank. Writes OUT.pdf (shuffled, one sheet upside down, a blank page) and
OUT.truth.json. Uses the CLI's scan damage; dev only, never shipped.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "skills" / "paper-loop" / "scripts"))
from paper_loop_core import scan as L  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402

from paperloop.simulate import _scan_damage  # noqa: E402

FONT_DIRS = [Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts"), Path("/Library/Fonts")]
STYLE_FONTS = {"clean": "Noteworthy.ttc", "messy": "Bradley Hand Bold.ttf", "kid": "Chalkboard.ttc",
               "neat": "MarkerFelt.ttc", "crossed": "Noteworthy.ttc"}
DPI = S.DPI


def font(name: str, px: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), px)
    return ImageFont.load_default(px)


def px(x: float, y: float) -> tuple[float, float]:
    return S.pt_to_px(x, y, DPI)


def wobble(rng: random.Random, n: float = 1.2) -> float:
    return rng.uniform(-n, n)


def write_text(draw, x_pt: float, y_top_pt: float, width_pt: float, height_pt: float, text: str, fname: str,
               rng: random.Random, ink: int, size_pt: float, line_pt: float | None = None) -> None:
    """Handwriting that wraps inside a region, starting at its top-left."""
    f = font(fname, round(size_pt * S.scale(DPI)))
    line_pt = line_pt or size_pt * 1.45
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) > (width_pt - 10) * S.scale(DPI) and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    for k, line in enumerate(lines):
        y = y_top_pt - k * line_pt
        if y_top_pt - y > height_pt - size_pt * 0.6:
            break
        x, yy = px(x_pt + 4 + wobble(rng), y - size_pt * 1.05 + wobble(rng, 0.8))
        draw.text((x, yy), line, fill=ink, font=f)


def in_box(draw, rect, text: str, fname: str, rng: random.Random, ink: int) -> None:
    x0, y0, x1, y1 = rect
    h = y1 - y0
    size = min(h * 0.62, 18)
    f = font(fname, round(size * S.scale(DPI)))
    while f.getlength(text) > (x1 - x0 - 12) * S.scale(DPI) and size > 7:
        size -= 1
        f = font(fname, round(size * S.scale(DPI)))
    x, y = px(x0 + 8 + wobble(rng), y0 + h / 2 + size * 0.62 + wobble(rng, 0.6))
    draw.text((x, y), text, fill=ink, font=f)


def circle(draw, at, crossed: bool, rng: random.Random, ink: int) -> None:
    cx, cy = px(*at)
    r = 9 * S.scale(DPI) + wobble(rng, 3)
    draw.ellipse((cx - r * 1.15, cy - r, cx + r * 1.15, cy + r), outline=ink, width=4)
    if crossed:
        draw.line((cx - r, cy - r, cx + r, cy + r), fill=ink, width=5)
        draw.line((cx - r, cy + r, cx + r, cy - r), fill=ink, width=5)


def sketch(draw, origin, shapes: list[dict], fname: str, rng: random.Random, ink: int) -> None:
    ox, oy = origin
    pt = lambda x, y: px(ox + x + wobble(rng, 0.8), oy + y + wobble(rng, 0.8))  # noqa: E731
    for s in shapes:
        kind = s["shape"]
        if kind in ("line", "arrow", "polyline"):
            pts = [pt(*p) for p in s["points"]]
            draw.line(pts, fill=ink, width=4, joint="curve")
            if kind == "arrow":
                (ax, ay), (bx, by) = pts[-2], pts[-1]
                ang = np.arctan2(by - ay, bx - ax)
                for side in (-1, 1):
                    a = ang + np.pi - side * 0.45
                    draw.line((bx, by, bx + 22 * np.cos(a), by + 22 * np.sin(a)), fill=ink, width=4)
        elif kind == "dot":
            cx, cy = pt(s["x"], s["y"])
            draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=ink)
        elif kind == "circle":
            cx, cy = pt(s["x"], s["y"])
            r = s["r"] * S.scale(DPI)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=ink, width=4)
        elif kind == "text":
            f = font(fname, round(s.get("size", 11) * S.scale(DPI)))
            x, y = pt(s["x"], s["y"] + s.get("size", 11))
            draw.text((x, y), s["text"], fill=ink, font=f)


def fill_page(blank: np.ndarray, page: dict, key: dict, layout_style: str, student: dict,
              rng: random.Random) -> np.ndarray:
    img = Image.fromarray(blank.copy())
    draw = ImageDraw.Draw(img)
    fname = STYLE_FONTS.get(student.get("style", "clean"), "Noteworthy.ttc")
    ink = 70 if student.get("style") == "messy" else 45
    for digit, rect in zip(student["id"], page["id_boxes"]):
        in_box(draw, rect, digit, fname, rng, ink)
    items = {i["q"]: i for i in key["items"]}
    line_spacing = S.STYLES[layout_style]["line_spacing"]
    for box in page["boxes"]:
        a = student["answers"].get(str(box["q"]))
        if not a:
            continue
        kind = box["type"]
        x0, y0, x1, y1 = box["rect"]
        if kind == "short":
            part = box.get("part", 1)  # an essay across pages: "more" holds the text for each later page
            text = a.get("text", "") if part == 1 else (a.get("more", []) + [""] * part)[part - 2]
            if text:
                write_text(draw, x0, y1, x1 - x0, y1 - y0, text, fname, rng, ink,
                           size_pt=min(15, line_spacing * 0.68), line_pt=line_spacing)
        elif kind == "choice":
            for mark in a["circle"]:
                letter = mark.strip("~")
                spot = next(o for o in box["options"] if o["letter"] == letter)
                circle(draw, spot["letter_at"], mark.startswith("~~"), rng, ink)
        elif kind in ("label", "blanks", "match", "table"):
            rects = {s["n"]: s["rect"] for s in box["labels"]}
            for n, text in a["boxes"].items():
                if text:
                    in_box(draw, rects[int(n)], text, fname, rng, ink)
        elif kind == "math":
            yy = y1 - 14
            for line in a.get("work", []):
                write_text(draw, x0 + 6, yy, x1 - x0 - 12, 20, line, fname, rng, ink, 13)
                yy -= 19
            if a.get("answer"):
                in_box(draw, box["answer_rect"], a["answer"], fname, rng, ink)
        elif kind == "draw":
            sketch(draw, (x0, y0), a["sketch"], fname, rng, ink)
    return np.array(img)


def main(assignment: Path, students_path: Path, out_pdf: Path, seed: int = 11) -> None:
    layout = S.read_json(assignment / "layout.json")
    key = S.read_json(assignment / "key.json")
    roster = json.loads(students_path.read_text())
    rng = random.Random(seed)
    sheets = []
    for student in roster["students"]:
        flip = student.get("style") == "messy"
        for page in layout["pages"]:
            blank = L.render_pdf(assignment / "worksheet.pdf")[page["page"] - 1]
            filled = fill_page(blank, page, key, layout.get("style", "standard"), student, rng)
            damaged = _scan_damage(filled, rng, rng.uniform(-1.5, 1.5), flip)
            sheets.append((damaged, {"student_id": student["id"], "page": page["page"], "upside_down": flip}))
    noise = np.random.default_rng(seed).normal(0, 4, sheets[0][0].shape)
    sheets.append((np.clip(248 + noise, 0, 255).astype(np.uint8), {"blank": True}))
    rng.shuffle(sheets)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.fromarray(img) for img, _ in sheets]
    images[0].save(out_pdf, save_all=True, append_images=images[1:], resolution=DPI)
    truth = {"assignment_id": layout["assignment_id"],
             "scan_pages": [{"scan_index": i, **t} for i, (_, t) in enumerate(sheets, start=1)],
             "students": roster["students"]}
    out_pdf.with_suffix(".truth.json").write_text(json.dumps(truth, indent=1, ensure_ascii=False))
    print(f"wrote {out_pdf} ({len(sheets)} pages) and its truth file")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
