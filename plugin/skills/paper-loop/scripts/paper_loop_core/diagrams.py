"""Printed diagrams: basic shapes, plus helpers for the scaffolds worksheets use most.

Coordinates are points inside the diagram, origin bottom-left. Helpers: `axes` (a coordinate grid),
`number_line`, `fraction` (a bar or circle in equal parts), `clock`, `timeline`, and `image` (a teacher's
picture, such as a map).
"""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from .fonts import Fonts

GRID = 0.78  # light enough that pencil on it still reads as the student's
SHADE = 0.72

BASE = dict(id=None, x=0.0, y=0.0, w=0.0, h=0.0, r=0.0, points=[], text="", size=9.0, bold=False, align="left",
            fill=None, stroke=0.0, width=1.0, wrap=0.0)
HELPERS = {
    "axes": dict(xmin=-5.0, xmax=5.0, ymin=-5.0, ymax=5.0, xstep=1.0, ystep=1.0, grid=True, label_every=1,
                 xlabel="", ylabel="", size=7.0),
    "number_line": dict(min=0.0, max=10.0, step=1.0, label_every=1, labels="decimal", arrows=True, minor=0, size=8.0),
    "fraction": dict(kind="bar", parts=4, shaded=0),
    "clock": dict(hour=None, minute=None, numbers=True),
    "timeline": dict(start=0, end=10, step=1, label_every=1, events=[], size=7.5, levels=2),
    "image": dict(path="", faint=False),
    "bar_chart": dict(categories=[], values=[], ymax=10.0, ystep=1.0, label_every=1, ylabel="", bar_fill=0.7, size=8.0),
    "staff": dict(clef="treble", notes=[], lines=5, time="", bars=[], final_bar=False),
}
SHAPES = {"rect", "circle", "line", "arrow", "polyline", "polygon", "text", *HELPERS}


def normalize_shape(s: dict) -> dict:
    return {**BASE, **HELPERS.get(s.get("shape"), {}), **s}


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _frac(v: float) -> str:
    f = Fraction(v).limit_denominator(64)
    if f.denominator == 1:
        return str(f.numerator)
    whole, rest = divmod(abs(f.numerator), f.denominator)
    sign = "-" if f < 0 else ""
    return f"{sign}{whole} {rest}/{f.denominator}" if whole else f"{sign}{rest}/{f.denominator}"


def _steps(lo: float, hi: float, step: float) -> list[float]:
    n = int(math.floor((hi - lo) / step + 1e-9))
    return [round(lo + i * step, 9) for i in range(n + 1)]


def _arrowhead(c: canvas.Canvas, x0: float, y0: float, x1: float, y1: float, size: float) -> None:
    angle = math.atan2(y1 - y0, x1 - x0)
    p = c.beginPath()
    p.moveTo(x1, y1)
    for side in (-1, 1):
        a = angle + math.pi - side * math.radians(25)
        p.lineTo(x1 + size * math.cos(a), y1 + size * math.sin(a))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def _axes(c: canvas.Canvas, s: dict, ox: float, oy: float, f: Fonts) -> None:
    x0, y0, w, h = ox + s["x"], oy + s["y"], s["w"], s["h"]
    sx, sy = w / (s["xmax"] - s["xmin"]), h / (s["ymax"] - s["ymin"])
    px = lambda v: x0 + (v - s["xmin"]) * sx  # noqa: E731
    py = lambda v: y0 + (v - s["ymin"]) * sy  # noqa: E731
    xs, ys = _steps(s["xmin"], s["xmax"], s["xstep"]), _steps(s["ymin"], s["ymax"], s["ystep"])
    if s["grid"]:
        c.setStrokeGray(GRID)
        c.setLineWidth(0.5)
        for v in xs:
            c.line(px(v), y0, px(v), y0 + h)
        for v in ys:
            c.line(x0, py(v), x0 + w, py(v))
    ax = 0.0 if s["ymin"] <= 0 <= s["ymax"] else s["ymin"]
    ay = 0.0 if s["xmin"] <= 0 <= s["xmax"] else s["xmin"]
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.setLineWidth(1.2)
    c.line(x0, py(ax), x0 + w, py(ax))
    c.line(px(ay), y0, px(ay), y0 + h)
    _arrowhead(c, x0 + w - 6, py(ax), x0 + w + 2, py(ax), 5)
    _arrowhead(c, px(ay), y0 + h - 6, px(ay), y0 + h + 2, 5)
    size = float(s["size"])  # the labels; 7 on a worksheet, bigger on a slide
    c.setFont(f.regular, size)
    every = max(1, int(s["label_every"]))
    origin = ax == 0 and ay == 0  # only a true origin goes unlabeled; 1960 or 99.2% at the corner is labeled
    for i, v in enumerate(xs):
        if i % every == 0 and (v != ay or not origin):
            if v == ay and ax != s["ymin"]:  # at the crossing, beside the y-axis rather than struck through by it
                c.drawString(px(v) + 3, py(ax) - 2 - size, f.text(_fmt(v)))
            else:
                c.drawCentredString(px(v), py(ax) - 2 - size, f.text(_fmt(v)))
    for i, v in enumerate(ys):
        if i % every == 0 and (v != ax or not origin):
            c.drawRightString(px(ay) - 3, py(v) - size * 0.36, f.text(_fmt(v)))
    if s["xlabel"]:
        c.drawRightString(x0 + w, py(ax) + 4, f.text(s["xlabel"]))
    if s["ylabel"]:
        c.drawString(px(ay) + 5, y0 + h - size, f.text(s["ylabel"]))


def _number_line(c: canvas.Canvas, s: dict, ox: float, oy: float, f: Fonts) -> None:
    x0, y, w = ox + s["x"], oy + s["y"], s["w"]
    pad = 10 if s["arrows"] else 0
    span = s["max"] - s["min"]
    px = lambda v: x0 + pad + (v - s["min"]) / span * (w - 2 * pad)  # noqa: E731
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.setLineWidth(1.2)
    c.line(x0, y, x0 + w, y)
    if s["arrows"]:
        _arrowhead(c, x0 + 6, y, x0 - 1, y, 5)
        _arrowhead(c, x0 + w - 6, y, x0 + w + 1, y, 5)
    minor = int(s["minor"])
    if minor:
        c.setLineWidth(0.6)
        for v in _steps(s["min"], s["max"], s["step"] / (minor + 1)):
            c.line(px(v), y - 3, px(v), y + 3)
    c.setLineWidth(1)
    size = float(s["size"])
    c.setFont(f.regular, size)
    every = max(1, int(s["label_every"]))
    for i, v in enumerate(_steps(s["min"], s["max"], s["step"])):
        c.line(px(v), y - 6, px(v), y + 6)
        if s["labels"] != "none" and i % every == 0:
            c.drawCentredString(px(v), y - 8 - size, f.text(_frac(v) if s["labels"] == "fraction" else _fmt(v)))


def _fraction(c: canvas.Canvas, s: dict, ox: float, oy: float) -> None:
    parts, shaded = max(1, int(s["parts"])), int(s["shaded"])
    c.setStrokeGray(0)
    c.setLineWidth(1)
    if s["kind"] == "circle":
        cx, cy, r = ox + s["x"], oy + s["y"], s["r"]
        for i in range(parts):
            start, extent = 90 - (i + 1) * 360 / parts, 360 / parts
            c.setFillGray(SHADE if i < shaded else 1)
            c.wedge(cx - r, cy - r, cx + r, cy + r, start, extent, stroke=1, fill=1)
        return
    x0, y0, w, h = ox + s["x"], oy + s["y"], s["w"], s["h"]
    for i in range(parts):
        c.setFillGray(SHADE if i < shaded else 1)
        c.rect(x0 + i * w / parts, y0, w / parts, h, stroke=1, fill=1)


def _clock(c: canvas.Canvas, s: dict, ox: float, oy: float, f: Fonts) -> None:
    cx, cy, r = ox + s["x"], oy + s["y"], s["r"]
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.setLineWidth(1.6)
    c.circle(cx, cy, r, stroke=1, fill=0)
    for m in range(60):
        a = math.radians(90 - m * 6)
        inner = r * (0.86 if m % 5 == 0 else 0.93)
        c.setLineWidth(1.2 if m % 5 == 0 else 0.5)
        c.line(cx + inner * math.cos(a), cy + inner * math.sin(a), cx + r * math.cos(a), cy + r * math.sin(a))
    if s["numbers"]:
        size = max(6.0, r * 0.18)
        c.setFont(f.bold, size)
        for n in range(1, 13):
            a = math.radians(90 - n * 30)
            c.drawCentredString(cx + 0.72 * r * math.cos(a), cy + 0.72 * r * math.sin(a) - size * 0.35, str(n))
    if s["hour"] is not None and s["minute"] is not None:
        hour = (float(s["hour"]) % 12) + float(s["minute"]) / 60
        for angle, length, width in ((90 - hour * 30, 0.48, 2.6), (90 - float(s["minute"]) * 6, 0.78, 1.6)):
            a = math.radians(angle)
            c.setLineWidth(width)
            c.line(cx, cy, cx + length * r * math.cos(a), cy + length * r * math.sin(a))
    c.circle(cx, cy, 2.2, stroke=0, fill=1)


def _timeline(c: canvas.Canvas, s: dict, ox: float, oy: float, f: Fonts) -> None:
    x0, y, w = ox + s["x"], oy + s["y"], s["w"]
    span = float(s["end"]) - float(s["start"])
    px = lambda v: x0 + (float(v) - float(s["start"])) / span * w  # noqa: E731
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.setLineWidth(1.6)
    c.line(x0, y, x0 + w, y)
    c.setLineWidth(1)
    size = float(s["size"])  # the events' labels; the years are a little bigger
    c.setFont(f.regular, size + 0.5)
    every = max(1, int(s["label_every"]))
    for i, v in enumerate(_steps(float(s["start"]), float(s["end"]), float(s["step"]))):
        c.line(px(v), y - 5, px(v), y + 5)
        if i % every == 0:
            c.drawCentredString(px(v), y - 8 - size, _fmt(v))
    for k, event in enumerate(s["events"]):
        x = px(event["at"])
        lift = 12 + (size + 5.5) * (k % max(1, int(s["levels"])))  # staggered so neighbors don't collide
        c.circle(x, y, 2.4, stroke=0, fill=1)
        c.setLineWidth(0.6)
        c.line(x, y, x, y + lift - 3)
        c.setFont(f.regular, size)
        c.drawCentredString(x, y + lift, f.text(event.get("text", "")))


def _bar_chart(c: canvas.Canvas, s: dict, ox: float, oy: float, f: Fonts) -> None:
    """Axes with a category under each slot. Bars are drawn for the values given (None or a missing value
    leaves the slot empty, for students to draw)."""
    x0, y0, w, h = ox + s["x"], oy + s["y"], s["w"], s["h"]
    cats = s["categories"]
    sy = h / s["ymax"]
    c.setStrokeGray(GRID)
    c.setLineWidth(0.5)
    for k, v in enumerate(_steps(0, s["ymax"], s["ystep"])):
        c.line(x0, y0 + v * sy, x0 + w, y0 + v * sy)
    slot = w / max(1, len(cats))
    for k, cat in enumerate(cats):
        value = s["values"][k] if k < len(s["values"]) else None
        if value is not None:
            c.setFillGray(s["bar_fill"])
            c.setStrokeGray(0)
            c.setLineWidth(0.8)
            c.rect(x0 + k * slot + slot * 0.2, y0, slot * 0.6, value * sy, stroke=1, fill=1)
        c.setFillGray(0)
        c.setFont(f.regular, float(s["size"]))
        c.drawCentredString(x0 + (k + 0.5) * slot, y0 - 3 - float(s["size"]), f.text(str(cat)))
    c.setStrokeGray(0)
    c.setLineWidth(1.2)
    c.line(x0, y0, x0 + w, y0)
    c.line(x0, y0, x0, y0 + h)
    c.setFont(f.regular, float(s["size"]) - 1)
    every = max(1, int(s["label_every"]))
    for i, v in enumerate(_steps(0, s["ymax"], s["ystep"])):
        if i % every == 0:
            c.drawRightString(x0 - 3, y0 + v * sy - (float(s["size"]) - 1) * 0.36, _fmt(v))
    if s["ylabel"]:  # above the top gridline, clear of it and of the top value's label
        c.drawString(x0 + 4, y0 + h + 6, f.text(s["ylabel"]))


_STEPS = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_BOTTOM_LINE = {"treble": ("E", 4), "bass": ("G", 2)}


def _staff_step(pitch: str, clef: str) -> int:
    """Half-spaces above the bottom line: E4 on a treble staff is 0, F4 (or F#4) is 1, G4 is 2."""
    letter, octave = pitch[0].upper(), int(pitch[-1])
    base_letter, base_octave = _BOTTOM_LINE[clef]
    return (octave * 7 + _STEPS[letter]) - (base_octave * 7 + _STEPS[base_letter])


# Clef outlines in staff spaces, from the bottom line: one stroke of curves, then dots
_TREBLE = [(0.15, 1.35), (0.5, 1.45, 0.68, 1.1, 0.62, 0.7), (0.56, 0.25, 0.3, 0.0, 0.0, 0.0),
           (-0.45, 0.0, -0.78, 0.45, -0.75, 1.05), (-0.72, 1.75, -0.2, 2.25, 0.2, 2.75),
           (0.62, 3.25, 0.82, 4.4, 0.55, 5.1), (0.38, 5.55, -0.05, 5.5, -0.15, 4.9),
           (-0.25, 4.3, -0.05, 2.0, 0.2, 0.2), (0.28, -0.45, 0.32, -1.0, 0.2, -1.35),
           (0.05, -1.75, -0.45, -1.7, -0.5, -1.35)]
_BASS = [(-0.45, 3.0), (-0.4, 3.75, 0.45, 4.15, 0.85, 3.5), (1.2, 2.95, 0.9, 1.6, -0.55, 0.85)]


def _clef(c: canvas.Canvas, clef: str, x: float, y: float, gap: float) -> None:
    """A treble or bass clef drawn as curves (no font has the glyph), x at its middle, y the bottom line."""
    points, dots = (_TREBLE, [(-0.4, -1.3, 0.24)]) if clef == "treble" else \
        (_BASS, [(-0.45, 3.0, 0.3), (1.35, 3.5, 0.16), (1.35, 2.5, 0.16)])
    path = c.beginPath()
    path.moveTo(x + points[0][0] * gap, y + points[0][1] * gap)
    for seg in points[1:]:
        path.curveTo(*[x + v * gap if i % 2 == 0 else y + v * gap for i, v in enumerate(seg)])
    c.saveState()
    c.setLineWidth(max(1.2, gap * 0.16))
    c.setLineCap(1)
    c.setLineJoin(1)
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.drawPath(path, stroke=1, fill=0)
    for dx, dy, r in dots:
        c.circle(x + dx * gap, y + dy * gap, r * gap, stroke=0, fill=1)
    c.restoreState()


def _accidental(c: canvas.Canvas, kind: str, x: float, y: float, gap: float) -> None:
    """A sharp (#) or flat (b) centered at x, on the note's line or space at y."""
    c.saveState()
    c.setStrokeGray(0)
    c.setLineCap(1)
    if kind == "#":
        c.setLineWidth(0.8)
        for dx in (-0.22, 0.22):
            c.line(x + dx * gap, y - 1.1 * gap, x + dx * gap, y + 1.2 * gap)
        c.setLineWidth(max(1.4, gap * 0.2))
        for dy in (-0.32, 0.32):
            c.line(x - 0.5 * gap, y + (dy - 0.1) * gap, x + 0.5 * gap, y + (dy + 0.1) * gap)
    else:
        c.setLineWidth(0.9)
        c.line(x - 0.3 * gap, y - 0.45 * gap, x - 0.3 * gap, y + 1.6 * gap)
        path = c.beginPath()
        path.moveTo(x - 0.3 * gap, y + 0.15 * gap)
        path.curveTo(x + 0.1 * gap, y + 0.55 * gap, x + 0.65 * gap, y + 0.3 * gap, x + 0.35 * gap, y - 0.05 * gap)
        path.curveTo(x + 0.15 * gap, y - 0.25 * gap, x - 0.1 * gap, y - 0.4 * gap, x - 0.3 * gap, y - 0.45 * gap)
        c.setLineWidth(1.2)
        c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


DURATIONS = ("whole", "half", "quarter", "eighth")
RESTS = DURATIONS


def _duration(note: dict) -> str:
    if note.get("duration"):
        return note["duration"]
    if not note.get("filled", True):  # the older form: "filled": false, "stem": false
        return "half" if note.get("stem", True) else "whole"
    return "quarter"


def _rest(c: canvas.Canvas, kind: str, x: float, mid: float, gap: float, one_line: bool) -> None:
    """A rest centered at x; mid is the middle line (or the single line of a rhythm staff)."""
    c.saveState()
    c.setFillGray(0)
    c.setStrokeGray(0)
    c.setLineCap(1)
    c.setLineJoin(1)
    if kind in ("whole", "half"):  # a block hanging from the line above the middle, or sitting on the middle
        top = mid + (0 if one_line else gap)
        bottom = top - gap * 0.5 if kind == "whole" else mid
        c.rect(x - gap * 0.55, bottom, gap * 1.1, gap * 0.5, stroke=0, fill=1)
    elif kind == "quarter":
        c.setLineWidth(gap * 0.3)
        path = c.beginPath()
        path.moveTo(x - gap * 0.3, mid + gap * 1.5)
        for dx, dy in ((0.3, 0.8), (-0.2, 0.15), (0.3, -0.5)):
            path.lineTo(x + dx * gap, mid + dy * gap)
        path.curveTo(x - gap * 0.5, mid - gap * 0.6, x - gap * 0.45, mid - gap * 1.25, x + gap * 0.1, mid - gap * 1.5)
        c.drawPath(path, stroke=1, fill=0)
    else:  # eighth
        c.circle(x - gap * 0.3, mid + gap * 0.6, gap * 0.22, stroke=0, fill=1)
        c.setLineWidth(gap * 0.14)
        path = c.beginPath()
        path.moveTo(x - gap * 0.3, mid + gap * 0.45)
        path.curveTo(x - gap * 0.05, mid + gap * 0.3, x + gap * 0.25, mid + gap * 0.45, x + gap * 0.4, mid + gap * 0.75)
        path.lineTo(x - gap * 0.1, mid - gap * 1.0)
        c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


def _staff(c: canvas.Canvas, s: dict, ox: float, oy: float, f: Fonts) -> None:
    """Five lines (or one, for rhythm), a clef, a time signature, bar lines, and notes and rests. Every x is
    in the diagram's coordinates. A note: {"pitch": "G4", "x": 60, "duration": "half", "dot": true};
    "F#4" and "Bb3" get a sharp or flat, and ledger lines are added. A rest: {"rest": "quarter", "x": 90}."""
    x0, y0, w = ox + s["x"], oy + s["y"], s["w"]
    gap = s["h"] / 4 if s["h"] else 8.0
    one_line = s["lines"] == 1
    mid = y0 if one_line else y0 + 2 * gap
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.setLineWidth(0.8)
    if one_line:
        c.line(x0, y0, x0 + w, y0)
    else:
        for k in range(5):
            c.line(x0, y0 + k * gap, x0 + w, y0 + k * gap)
        c.line(x0, y0, x0, y0 + 4 * gap)
    if s["clef"] in ("treble", "bass") and not one_line:
        _clef(c, s["clef"], x0 + gap * 1.3, y0, gap)
    if s["time"]:
        top, bottom = str(s["time"]).split("/")
        tx = x0 + gap * (4.2 if s["clef"] in ("treble", "bass") and not one_line else 1.2)
        size = gap * 2.1
        c.setFont(f.bold, size)
        for text, centre in ((top, mid + gap), (bottom, mid - gap)):
            c.drawCentredString(tx, centre - size * 0.36, text)
    c.setLineWidth(1)
    low, high = (y0 - gap, y0 + gap) if one_line else (y0, y0 + 4 * gap)
    for bx in s["bars"]:
        c.line(ox + bx, low, ox + bx, high)
    if s["final_bar"]:
        c.line(x0 + w - gap * 0.6, low, x0 + w - gap * 0.6, high)
        c.setLineWidth(gap * 0.35)
        c.line(x0 + w - gap * 0.18, low, x0 + w - gap * 0.18, high)
    for note in s["notes"]:
        nx = ox + note["x"]
        if note.get("rest"):
            _rest(c, note["rest"], nx, mid, gap, one_line)
            if note.get("dot"):
                c.circle(nx + gap * 0.95, mid + gap * 0.5, gap * 0.16, stroke=0, fill=1)
            continue
        kind = _duration(note)
        step = 0 if one_line else _staff_step(note["pitch"], s["clef"])
        ny = y0 + step * gap / 2
        c.setLineWidth(0.8)
        for ledger in range(-2, step - 1, -2) if step < 0 else range(10, step + 1, 2):
            c.line(nx - gap * 0.9, y0 + ledger * gap / 2, nx + gap * 0.9, y0 + ledger * gap / 2)
        if not one_line and len(note["pitch"]) == 3:
            _accidental(c, note["pitch"][1], nx - gap * 1.6, ny, gap)
        c.saveState()
        c.translate(nx, ny)
        if kind == "whole":
            c.setLineWidth(gap * 0.16)
            c.ellipse(-gap * 0.72, -gap * 0.45, gap * 0.72, gap * 0.45, stroke=1, fill=0)
        else:
            c.rotate(20)
            c.setLineWidth(1.1)
            c.ellipse(-gap * 0.62, -gap * 0.42, gap * 0.62, gap * 0.42, stroke=1, fill=int(kind != "half"))
        c.restoreState()
        if note.get("dot"):  # in the space above when the note sits on a line
            on_line = one_line or step % 2 == 0
            c.circle(nx + gap * 1.05, ny + (gap * 0.5 if on_line else 0), gap * 0.16, stroke=0, fill=1)
        if kind == "whole":
            continue
        up = one_line or step < 4
        sx = nx + gap * 0.58 if up else nx - gap * 0.58
        tip = ny + gap * 3.3 if up else ny - gap * 3.3
        c.setLineWidth(1)
        c.line(sx, ny, sx, tip)
        if kind == "eighth":
            sign = -1 if up else 1
            path = c.beginPath()
            path.moveTo(sx, tip)
            path.curveTo(sx + gap * 0.2, tip + sign * gap * 0.7, sx + gap * 1.1, tip + sign * gap * 1.0,
                         sx + gap * 0.7, tip + sign * gap * 2.2)
            c.setLineWidth(gap * 0.18)
            c.drawPath(path, stroke=1, fill=0)


def _image(c: canvas.Canvas, s: dict, ox: float, oy: float, base: Path) -> None:
    path = Path(s["path"])
    path = path if path.is_absolute() else base / path
    c.drawImage(ImageReader(str(path)), ox + s["x"], oy + s["y"], s["w"], s["h"],
                preserveAspectRatio=True, anchor="c")


def draw_diagram(c: canvas.Canvas, diagram: dict, x0: float, y0: float, f: Fonts, base: Path = Path(".")) -> None:
    for s in diagram["shapes"]:
        kind = s["shape"]
        if kind == "axes":
            _axes(c, s, x0, y0, f)
            continue
        if kind == "number_line":
            _number_line(c, s, x0, y0, f)
            continue
        if kind == "fraction":
            _fraction(c, s, x0, y0)
            continue
        if kind == "clock":
            _clock(c, s, x0, y0, f)
            continue
        if kind == "timeline":
            _timeline(c, s, x0, y0, f)
            continue
        if kind == "image":
            _image(c, s, x0, y0, base)
            continue
        if kind == "bar_chart":
            _bar_chart(c, s, x0, y0, f)
            continue
        if kind == "staff":
            _staff(c, s, x0, y0, f)
            continue
        stroke, fill = s["stroke"] is not None, s["fill"] is not None
        c.setLineWidth(s["width"])
        c.setStrokeGray(s["stroke"] if stroke else 0)
        c.setFillGray(s["fill"] if fill else 0)
        if kind == "rect":
            c.rect(x0 + s["x"], y0 + s["y"], s["w"], s["h"], stroke=int(stroke), fill=int(fill))
        elif kind == "circle":
            c.circle(x0 + s["x"], y0 + s["y"], s["r"], stroke=int(stroke), fill=int(fill))
        elif kind in ("line", "arrow", "polyline", "polygon") and len(s["points"]) >= 2:
            p = c.beginPath()
            p.moveTo(x0 + s["points"][0][0], y0 + s["points"][0][1])
            for px, py in s["points"][1:]:
                p.lineTo(x0 + px, y0 + py)
            if kind == "polygon":
                p.close()
            c.drawPath(p, stroke=int(stroke), fill=int(fill and kind == "polygon"))
            if kind == "arrow":
                (ax, ay), (bx, by) = s["points"][-2], s["points"][-1]
                c.setFillGray(s["stroke"] if stroke else 0)
                _arrowhead(c, x0 + ax, y0 + ay, x0 + bx, y0 + by, 4 + 2 * s["width"])
        elif kind == "text":
            c.setFillGray(s["fill"] if fill else 0)
            font = f.bold if s["bold"] else f.regular
            c.setFont(font, s["size"])
            draw = {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[s["align"]]
            lines = simpleSplit(f.text(s["text"]), font, s["size"], s["wrap"]) if s["wrap"] else [f.text(s["text"])]
            for n, line in enumerate(lines):
                draw(x0 + s["x"], y0 + s["y"] - n * s["size"] * 1.2, line)


def diagram_texts(diagram: dict) -> list[str]:
    """Every string a diagram prints, for choosing a font."""
    out = []
    for s in diagram["shapes"]:
        out += [s.get("text", ""), s.get("xlabel", ""), s.get("ylabel", "")] + [str(x) for x in s.get("categories", [])]
        out += [e.get("text", "") for e in s.get("events", [])]
    return out
