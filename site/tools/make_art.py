"""Draw the site's poster art: the sun setting on ed tech, behind a palm jungle.

An original homage to a 1970s war-movie poster, drawn from scratch so nothing is copied. Real lines
of Paper Loop's code drift across the sun like stratus clouds, thickening toward the horizon until
they blot it out, and a squadron of paper airplanes flies off ahead of the dark.

Writes public/img/poster.svg (the hero), public/img/jungle.svg (a silhouette strip for section
edges), and public/img/grit.png (the mask that roughens the big title).

    python3 tools/make_art.py
"""

import math
import random
import struct
import zlib
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
OUT = SITE / "public" / "img"
REPO = SITE.parent
W, H = 1600, 1000
BLACK = "#080201"

# The clouds are made of these, and each one must still be in Paper Loop's source.
CODE = [
    'comment = "No answer circled." if box.type == "choice" else "No answer yet."',
    'answered = [b for b in boxes if b.verdict != "blank"]',
    'confidence = min(max(confidence, 0.0), 1.0)',
    'boxes_id = id_boxes(defn["id_digits"], defn["style"], L.k)',
    'crop_path = workdir / "crops" / f"{page.student_id}-p{page.page}-q{box.q}.png"',
    'checks = [] if result.verdict == "blank" else _checks(result)',
    'base_skill = {i["q"]: i.get("skill") for i in key["items"]}',
    'blanks = render_pages(assignment_dir / "worksheet.pdf", dpi)',
    'def _comment_limit(key_file: dict, form: str = "") -> int:',
    'boxes = sum(len(p.boxes) for p in feedback.pages)',
]


def check_code():
    sources = "\n".join(
        f.read_text(errors="ignore")
        for root in (REPO / "plugin", REPO / "paperloop")
        for f in root.rglob("*.py")
    )
    missing = [line for line in CODE if line not in sources]
    if missing:
        raise SystemExit("These lines are no longer in Paper Loop's code:\n" + "\n".join(missing))


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def code_clouds(cx, rng):
    """Bands of code across the sun: thin and faint up high, thick and dark at the horizon."""
    # (baseline, font size, opacity, width, offset from the sun's center)
    bands = [(548, 11, 0.38, 520, -60), (574, 12, 0.44, 760, 90), (602, 14, 0.5, 600, -120),
             (634, 16, 0.58, 880, 40), (670, 18, 0.64, 700, 150), (708, 21, 0.72, 980, -30),
             (750, 24, 0.8, 820, 110), (792, 27, 0.88, 1100, 0)]
    out = []
    order = CODE[:]
    rng.shuffle(order)
    k = 0
    for y, size, opacity, width, shift in bands:
        need = int(width / (size * 0.6)) + 2
        text = ""
        while len(text) < need:
            text += order[k % len(order)] + "    "
            k += 1
        text = text[:need].rstrip()
        x = cx - width / 2 + shift
        out.append(
            f'<text x="{x:.0f}" y="{y}" font-size="{size}" textLength="{width}" lengthAdjust="spacingAndGlyphs" '
            f'fill="#5e1203" opacity="{opacity}" mask="url(#streak)">{esc(text)}</text>'
        )
    return (
        '<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, \'DejaVu Sans Mono\', monospace" '
        f'font-weight="700"><g filter="url(#haze)">{"".join(out)}</g>{"".join(out)}</g>'
    )


# A paper dart flying left, lit by the sunset: the near wing, the far wing, and the keel in shadow.
PLANE = (
    '<path d="M0 18L130 0L96 22Z" fill="#f7ead2"/>'
    '<path d="M0 18L118 9L96 22Z" fill="#e2c49a"/>'
    '<path d="M0 18L96 22L84 37Z" fill="#a8703f"/>'
    '<path d="M0 18L96 22" stroke="#8a5428" stroke-width="1" fill="none" opacity=".6"/>'
)


def plane(x, y, scale, tilt, opacity):
    contrail = (
        f'<path d="M{x + 128 * scale:.0f} {y + 10 * scale:.0f} l{200 * scale:.0f} {16 * scale:.0f}" '
        f'stroke="#ffe2b8" stroke-width="{max(1, 1.8 * scale):.1f}" stroke-linecap="round" '
        f'stroke-dasharray="1 10" opacity="{0.45 * opacity:.2f}"/>'
    )
    return (
        f'{contrail}<g class="plane" opacity="{opacity}">'
        f'<g transform="translate({x:.0f} {y:.0f}) rotate({tilt} 60 20) scale({scale})">{PLANE}</g></g>'
    )


def palm(x, ground, height, lean, rng, color=BLACK):
    """A trunk that curves up to a crown of drooping fronds."""
    cx, cy = x + lean, ground - height
    trunk = (
        f'<path d="M{x - 7:.1f} {ground} Q{x + lean * 0.2 - 5:.1f} {ground - height * 0.5:.1f} {cx - 3:.1f} {cy:.1f} '
        f'L{cx + 3:.1f} {cy:.1f} Q{x + lean * 0.2 + 5:.1f} {ground - height * 0.5:.1f} {x + 7:.1f} {ground}Z"/>'
    )
    parts = [trunk]
    n = rng.randint(8, 11)
    for i in range(n):
        a = math.radians(-175 + i * (170 / (n - 1)) + rng.uniform(-8, 8))
        length = height * rng.uniform(0.32, 0.46)
        droop = length * rng.uniform(0.35, 0.75) * (1 - abs(math.sin(a)) * 0.6)
        tx, ty = cx + math.cos(a) * length, cy + math.sin(a) * length + droop
        mx, my = (cx + tx) / 2, (cy + ty) / 2 - length * 0.18
        nx, ny = -(ty - cy), tx - cx
        norm = math.hypot(nx, ny) or 1
        w = length * 0.11
        nx, ny = nx / norm * w, ny / norm * w
        parts.append(
            f'<path d="M{cx:.1f} {cy:.1f} Q{mx + nx:.1f} {my + ny:.1f} {tx:.1f} {ty:.1f} '
            f'Q{mx - nx:.1f} {my - ny:.1f} {cx:.1f} {cy:.1f}Z"/>'
        )
    return f'<g fill="{color}">{"".join(parts)}</g>'


def canopy(ground, rng, color, rmin, rmax, step):
    """A tree line: overlapping round crowns along the ground, filled to the bottom."""
    blobs = [f'<rect x="0" y="{ground}" width="{W}" height="{H - ground + 2}"/>']
    x = -40
    while x < W + 40:
        r = rng.uniform(rmin, rmax)
        blobs.append(f'<circle cx="{x:.0f}" cy="{ground + r * 0.35:.0f}" r="{r:.0f}"/>')
        x += step * rng.uniform(0.6, 1.2)
    return f'<g fill="{color}">{"".join(blobs)}</g>'


def ridge(base, amp, color, rng, opacity=1.0):
    pts = []
    phase = [rng.uniform(0, 6) for _ in range(3)]
    for i in range(0, W + 41, 40):
        y = base - amp * (
            0.6 * math.sin(i / 230 + phase[0]) + 0.3 * math.sin(i / 97 + phase[1]) + 0.15 * math.sin(i / 41 + phase[2])
        )
        pts.append(f"{i},{y:.0f}")
    return f'<polygon fill="{color}" opacity="{opacity}" points="0,{H} {" ".join(pts)} {W},{H}"/>'


def poster():
    rng = random.Random(1979)
    sun_x, sun_y = 1060, 700
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMax slice">',
        "<defs>",
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#0c0302"/><stop offset=".22" stop-color="#2e0704"/>'
        '<stop offset=".45" stop-color="#7d1806"/><stop offset=".62" stop-color="#c63a0c"/>'
        '<stop offset=".76" stop-color="#ef7422"/><stop offset=".86" stop-color="#ffb347"/>'
        "</linearGradient>",
        '<radialGradient id="glow"><stop offset="0" stop-color="#ffd27a" stop-opacity=".75"/>'
        '<stop offset=".45" stop-color="#ff8a2a" stop-opacity=".35"/><stop offset="1" stop-color="#ff5a14" stop-opacity="0"/>'
        "</radialGradient>",
        '<radialGradient id="sun" cx=".45" cy=".4"><stop offset="0" stop-color="#fff4c4"/>'
        '<stop offset=".55" stop-color="#ffd166"/><stop offset="1" stop-color="#ff9f30"/></radialGradient>',
        '<linearGradient id="fadeh"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".22" stop-color="#fff"/><stop offset=".78" stop-color="#fff"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
        '<mask id="streak" maskUnits="objectBoundingBox" maskContentUnits="objectBoundingBox" '
        'x="0" y="-1" width="1" height="3"><rect y="-1" width="1" height="3" fill="url(#fadeh)"/></mask>',
        '<filter id="haze" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="3.5"/></filter>',
        "<style>.plane{animation:bob 7s ease-in-out infinite}.plane:nth-of-type(2n){animation-duration:9s}"
        "@keyframes bob{50%{translate:0 -6px}}"
        "@media (prefers-reduced-motion:reduce){.plane{animation:none}}</style>",
        "</defs>",
        f'<rect width="{W}" height="{H}" fill="url(#sky)"/>',
        f'<circle cx="{sun_x}" cy="{sun_y}" r="560" fill="url(#glow)"/>',
        f'<circle cx="{sun_x}" cy="{sun_y}" r="250" fill="url(#sun)"/>',
    ]
    out.append(code_clouds(sun_x, rng))
    # Paper airplanes in formation, flying off ahead of the dark: far ones small and hazy.
    squad = [
        (1250, 300, 0.34, -8, 0.55),
        (1390, 345, 0.28, -7, 0.5),
        (1120, 390, 0.42, -9, 0.65),
        (470, 290, 0.48, -10, 0.75),
        (660, 215, 0.34, -8, 0.6),
        (800, 440, 0.82, -11, 0.95),
        (170, 380, 1.0, -12, 1),
        (1430, 450, 0.56, -9, 0.85),
    ]
    for x, y, sc, t, o in squad:
        out.append(plane(x, y, sc, t, o))
    out.append(ridge(820, 26, "#3a0904", rng, 0.9))
    out.append(ridge(865, 22, "#1c0402", rng))
    for x, height, lean in [(70, 360, 30), (210, 300, -24), (1390, 380, -36), (1530, 290, 20), (1250, 230, 14), (640, 210, -10)]:
        out.append(palm(x, 940, height, lean, rng))
    out.append(canopy(930, rng, BLACK, 34, 78, 70))
    out.append("</svg>")
    return "\n".join(out)


def jungle():
    """A transparent silhouette strip, for the bottom edge of dark sections."""
    rng = random.Random(1969)
    h = 220
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" preserveAspectRatio="xMidYMax slice">']
    for x, height, lean in [(90, 200, 18), (260, 160, -14), (1300, 210, -20), (1480, 170, 16), (760, 120, 8)]:
        out.append(palm(x, h - 20, height, lean, rng, "#000"))
    blobs = [f'<rect x="0" y="{h - 26}" width="{W}" height="30"/>']
    x = -30
    while x < W + 30:
        r = rng.uniform(16, 38)
        blobs.append(f'<circle cx="{x:.0f}" cy="{h - 20:.0f}" r="{r:.0f}"/>')
        x += 46 * rng.uniform(0.6, 1.2)
    out.append(f'<g fill="#000">{"".join(blobs)}</g>')
    out.append("</svg>")
    return "\n".join(out)


def grit(size=512):
    """An alpha mask: mostly solid, with specks and scratches knocked out, like worn poster ink."""
    rng = random.Random(7)
    alpha = bytearray([255] * (size * size))
    for _ in range(size * size // 26):
        x, y = rng.randrange(size), rng.randrange(size)
        r = rng.choice([0, 0, 0, 1, 1, 2])
        level = rng.choice([0, 40, 90, 140])
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    alpha[((y + dy) % size) * size + (x + dx) % size] = level
    for _ in range(70):
        x, y = rng.randrange(size), rng.randrange(size)
        length, angle = rng.randint(20, 90), rng.uniform(-0.5, 0.5)
        for t in range(length):
            px, py = int(x + t * math.cos(angle)) % size, int(y + t * math.sin(angle)) % size
            alpha[py * size + px] = 30
    raw = b"".join(b"\x00" + bytes(v for a in alpha[r * size:(r + 1) * size] for v in (0, 0, 0, a)) for r in range(size))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    check_code()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "poster.svg").write_text(poster())
    (OUT / "jungle.svg").write_text(jungle())
    (OUT / "grit.png").write_bytes(grit())
    for name in ["poster.svg", "jungle.svg", "grit.png"]:
        print(name, (OUT / name).stat().st_size, "bytes")
