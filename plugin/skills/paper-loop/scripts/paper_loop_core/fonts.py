"""Fonts: Helvetica when the text allows it, a Unicode font when it needs math symbols or other scripts.

reportlab's built-in fonts only draw Windows-1252 (Latin letters, common accents, ½, °, ², ³). Math
(π, √, ≤, θ), Greek, Cyrillic, and the like need a TrueType font. DejaVu Sans ships inside matplotlib,
which Claude's sandboxes include, and most Linux images also have it. Without one, those characters
print as "?" and `make` says so.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_ASCII = {"→": "->", "←": "<-", "−": "-"}  # dashes and curly quotes are in Windows-1252 and print as is


@dataclass(frozen=True)
class Fonts:
    regular: str
    bold: str
    oblique: str
    unicode: bool
    mono: str = "Courier"  # code, and anything that must keep its spacing

    def text(self, s: str) -> str:
        """What this font family can draw of s: everything for a Unicode font, else Windows-1252."""
        if self.unicode:
            return s
        out = []
        for ch in s:
            ch = _ASCII.get(ch, ch)
            try:
                ch.encode("cp1252")
                out.append(ch)
            except UnicodeEncodeError:
                out.append("?")
        return "".join(out)


HELVETICA = Fonts("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", False)


def needs_unicode(texts) -> bool:
    for s in texts:
        try:
            "".join(_ASCII.get(ch, ch) for ch in s).encode("cp1252")
        except UnicodeEncodeError:
            return True
    return False


def _candidates() -> list[Path]:
    dirs = []
    spec = importlib.util.find_spec("matplotlib")
    if spec and spec.origin:
        dirs.append(Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf")
    dirs += [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"),
             Path("/usr/share/fonts/TTF"), Path("/usr/local/share/fonts")]
    return dirs


@cache
def unicode_fonts() -> Fonts | None:
    """DejaVu Sans, registered with reportlab, or None if this machine doesn't have it."""
    for d in _candidates():
        files = {style: d / f"DejaVuSans{suffix}.ttf"
                 for style, suffix in (("regular", ""), ("bold", "-Bold"), ("oblique", "-Oblique"), ("mono", "Mono"))}
        if all(f.exists() for f in files.values()):
            for style, f in files.items():
                pdfmetrics.registerFont(TTFont(f"PL-Sans-{style}", str(f)))
            return Fonts("PL-Sans-regular", "PL-Sans-bold", "PL-Sans-oblique", True, "PL-Sans-mono")
    return None


def choose(texts) -> tuple[Fonts, bool]:
    """(fonts, every character will print). Helvetica unless the text needs more."""
    if not needs_unicode(texts):
        return HELVETICA, True
    fonts = unicode_fonts()
    return (fonts, True) if fonts else (HELVETICA, False)


def unprintable(texts) -> str:
    """The characters Helvetica can't draw, for telling the teacher what will print as "?"."""
    bad = set()
    for s in texts:
        for ch in s:
            try:
                _ASCII.get(ch, ch).encode("cp1252")
            except UnicodeEncodeError:
                bad.add(ch)
    return " ".join(sorted(bad))
