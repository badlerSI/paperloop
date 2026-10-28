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


# --- Other writing systems -----------------------------------------------------------------------
# A home-language translation may need a script DejaVu doesn't have. These are font files known to cover
# one, by the names Linux distributions, LibreOffice, and macOS install them under. reportlab reads only
# TrueType outlines, so OpenType/CFF files (most Noto CJK) are skipped when they don't load.
_SEARCH_DIRS = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
                Path("/usr/lib/libreoffice/share/fonts"), Path("/opt"), Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts")]
_WANTED = ("DroidSansFallback", "wqy-zenhei", "wqy-microhei", "uming", "ukai", "NanumGothic", "UnDotum",
           "ipag", "ipaexg", "TakaoGothic", "Arial Unicode", "NotoSansEthiopic", "NotoSerifEthiopic",
           "Abyssinica", "Kefa", "NotoSansArmenian", "NotoSansGeorgian", "FreeSans", "unifont")
# Chinese, Japanese, and Korean fonts every PDF viewer can supply (Adobe's standard CJK fonts). reportlab
# knows their widths; the glyphs come from the viewer, so these print from Chrome, Preview, Acrobat, or
# Word, but may not from a copier's own print-from-USB menu.
_CID = {"zh-hans": "STSong-Light", "zh-hant": "MSung-Light", "ja": "HeiseiKakuGo-W5", "ko": "HYGothic-Medium"}


@cache
def _font_files() -> tuple[Path, ...]:
    found = []
    for d in _SEARCH_DIRS:
        if not d.exists():
            continue
        depth = "**/" if d != Path("/opt") else "*/share/fonts/**/"
        for path in d.glob(f"{depth}*"):
            if path.suffix.lower() in (".ttf", ".ttc") and any(w.lower() in path.name.lower() for w in _WANTED):
                found.append(path)
    return tuple(sorted(found))


@cache
def _load(path: Path, index: int = 0) -> tuple[str, frozenset] | None:
    """Register a font file with reportlab: (font name, the code points it covers), or None."""
    name = f"PL-{path.stem}-{index}".replace(" ", "")
    try:
        font = TTFont(name, str(path), subfontIndex=index) if path.suffix.lower() == ".ttc" else TTFont(name, str(path))
        pdfmetrics.registerFont(font)
    except Exception:  # CFF outlines, a broken file: not one reportlab can use
        return None
    return name, frozenset(font.face.charToGlyph)


def covers(font_name: str, text: str) -> bool:
    try:
        cmap = pdfmetrics.getFont(font_name).face.charToGlyph
    except AttributeError:  # a built-in font: Windows-1252 only
        return not needs_unicode([text])
    return all(ord(ch) in cmap for ch in text if not ch.isspace())


def _cjk_language(text: str) -> str:
    if any(0xAC00 <= ord(ch) <= 0xD7AF or 0x1100 <= ord(ch) <= 0x11FF for ch in text):
        return "ko"
    if any(0x3040 <= ord(ch) <= 0x30FF for ch in text):
        return "ja"
    return "zh-hans"


def font_for(text: str, base: Fonts, language: str = "") -> tuple[str, str]:
    """(font name, how) for a block of home-language text, already shaped. how is "base" (the page's own
    font), "found" (a font on this machine covers it), "viewer" (a standard CJK font the PDF viewer
    supplies), or "none" (no font here can print it: use the Word companion page)."""
    if base.unicode and covers(base.regular, text) or not base.unicode and not needs_unicode([text]):
        return base.regular, "base"
    for path in _font_files():
        for index in range(4 if path.suffix.lower() == ".ttc" else 1):
            loaded = _load(path, index)
            if loaded and all(ord(ch) in loaded[1] for ch in text if not ch.isspace()):
                return loaded[0], "found"
    from . import script as SC
    if SC.has_cjk(text) and not SC.has_rtl(text) and not SC.complex_scripts(text):
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        lang = language.lower()
        key = ("zh-hant" if lang in ("zh-hant", "zh-tw", "zh-hk", "yue") else
               lang if lang in _CID else _cjk_language(text))
        pdfmetrics.registerFont(UnicodeCIDFont(_CID[key]))
        return _CID[key], "viewer"
    return base.regular, "none"


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
