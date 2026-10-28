"""Writing systems: which ones a PDF can print here, Arabic-script shaping, and right-to-left lines.

reportlab draws one glyph per character, left to right. That's right for Latin, Cyrillic, Greek, and
Chinese, Japanese, and Korean. Arabic-script languages (Arabic, Urdu, Dari, Farsi, Pashto) need each
letter in the form that joins its neighbors, and their lines run right to left: `shape` picks the joined
forms from Unicode's presentation forms, and `visual` puts a line in display order. Scripts whose letters
combine in ways only a shaping engine handles (Bengali, Devanagari, Gurmukhi, Gujarati, Telugu, Burmese,
Khmer, and others) can't print correctly here: those languages go on the Word companion page, which Word
and Google Docs shape properly.
"""

from __future__ import annotations

import unicodedata
from functools import cache

# Scripts that need a shaping engine this sandbox doesn't have: (name, first, last code point).
COMPLEX = [
    ("Devanagari", 0x0900, 0x097F), ("Bengali", 0x0980, 0x09FF), ("Gurmukhi", 0x0A00, 0x0A7F),
    ("Gujarati", 0x0A80, 0x0AFF), ("Oriya", 0x0B00, 0x0B7F), ("Tamil", 0x0B80, 0x0BFF),
    ("Telugu", 0x0C00, 0x0C7F), ("Kannada", 0x0C80, 0x0CFF), ("Malayalam", 0x0D00, 0x0D7F),
    ("Sinhala", 0x0D80, 0x0DFF), ("Thai", 0x0E00, 0x0E7F), ("Lao", 0x0E80, 0x0EFF), ("Tibetan", 0x0F00, 0x0FFF),
    ("Myanmar", 0x1000, 0x109F), ("Khmer", 0x1780, 0x17FF), ("Myanmar", 0xAA60, 0xAA7F),
    ("Myanmar", 0xA9E0, 0xA9FF), ("Syriac", 0x0700, 0x074F), ("Thaana", 0x0780, 0x07BF),
    ("Hebrew", 0x0590, 0x05FF),  # no shaping, but right to left with points: not handled here
]
ARABIC = [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]
CJK = [(0x1100, 0x11FF), (0x2E80, 0x2FDF), (0x3000, 0x30FF), (0x3100, 0x31FF), (0x3200, 0x9FFF),
       (0xA960, 0xA97F), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF), (0x20000, 0x2FFFF)]


def _in(ch: str, ranges) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in ranges)


def is_arabic(ch: str) -> bool:
    return _in(ch, ARABIC)


def is_cjk(ch: str) -> bool:
    return _in(ch, CJK)


def complex_scripts(text: str) -> list[str]:
    """Names of scripts in text that need a shaping engine to print (Bengali, Burmese, ...)."""
    found = []
    for ch in text:
        o = ord(ch)
        for name, a, b in COMPLEX:
            if a <= o <= b and name not in found:
                found.append(name)
    return found


def has_rtl(text: str) -> bool:
    return any(is_arabic(ch) for ch in text)


def has_cjk(text: str) -> bool:
    return any(is_cjk(ch) for ch in text)


# --- Arabic shaping ---------------------------------------------------------------------------

LAM, TATWEEL = chr(0x0644), chr(0x0640)
ALEFS = {chr(0x0622), chr(0x0623), chr(0x0625), chr(0x0627)}


@cache
def _forms() -> tuple[dict, dict]:
    """From Unicode's presentation forms: letter -> {isolated, final, initial, medial}, and the lam-alef
    ligatures: (lam, alef) -> {isolated, final}. Read from unicodedata, so no table to keep up to date."""
    forms: dict[str, dict[str, str]] = {}
    ligatures: dict[tuple[str, str], dict[str, str]] = {}
    for cp in list(range(0xFB50, 0xFE00)) + list(range(0xFE70, 0xFF00)):
        decomposition = unicodedata.decomposition(chr(cp))
        if not decomposition.startswith("<"):
            continue
        tag, *parts = decomposition.split()
        tag = tag.strip("<>")
        if tag not in ("isolated", "final", "initial", "medial"):
            continue
        letters = "".join(chr(int(p, 16)) for p in parts)
        if len(letters) == 1:
            forms.setdefault(letters, {}).setdefault(tag, chr(cp))
        elif len(letters) == 2 and letters[0] == LAM and letters[1] in ALEFS:
            ligatures.setdefault((letters[0], letters[1]), {}).setdefault(tag, chr(cp))
    return forms, ligatures


def _joins_left(ch: str) -> bool:
    """Can connect to the letter after it (dual-joining), judged by having an initial or medial form."""
    if ch == TATWEEL:
        return True
    f = _forms()[0].get(ch, {})
    return "initial" in f or "medial" in f


def _joins(ch: str) -> bool:
    """Connects to the letter before it."""
    return ch == TATWEEL or bool(_forms()[0].get(ch))


def _transparent(ch: str) -> bool:
    return unicodedata.category(ch) == "Mn"  # vowel marks sit on a letter and don't break joining


# Letter + mark pairs written as one letter in Persian and Urdu (heh + hamza above is Dari's ezafe).
_COMPOSE = {(chr(0x0647), chr(0x0654)): chr(0x06C0), (chr(0x06C1), chr(0x0654)): chr(0x06C2),
            (chr(0x06D2), chr(0x0654)): chr(0x06D3), (chr(0x064A), chr(0x0654)): chr(0x0626),
            (chr(0x0648), chr(0x0654)): chr(0x0624), (chr(0x0627), chr(0x0654)): chr(0x0623)}


def compose(text: str) -> str:
    """Letter + combining hamza as the one letter fonts have a glyph for."""
    if chr(0x0654) not in text:
        return text
    out = []
    for ch in text:
        if out and (out[-1], ch) in _COMPOSE:
            out[-1] = _COMPOSE[(out[-1], ch)]
        else:
            out.append(ch)
    return "".join(out)


def shape(text: str, has_glyph=lambda ch: True) -> str:
    """Arabic-script letters replaced by the presentation form that joins their neighbors, in logical
    order. A letter without a presentation form, or whose form the font lacks (has_glyph), is left as
    written: it prints unjoined, which reads, rather than as a missing-glyph box. A vowel mark the font
    lacks is left out: the word still reads, as it does in most print."""
    if not has_rtl(text):
        return text
    text = compose(text)
    forms, ligatures = _forms()
    chars = [ch for ch in text if not (_transparent(ch) and is_arabic(ch) and not has_glyph(ch))]
    out = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if not _joins(ch) or ch == TATWEEL:
            out.append(ch)
            i += 1
            continue
        prev = next((c for c in reversed(chars[:i]) if not _transparent(c)), None)
        j = i + 1
        while j < len(chars) and _transparent(chars[j]):
            j += 1
        nxt = chars[j] if j < len(chars) else None
        joined_before = prev is not None and _joins_left(prev) and _joins(prev)
        if ch == LAM and nxt and (ch, nxt) in ligatures:
            lig = ligatures[(ch, nxt)].get("final" if joined_before else "isolated")
            if lig and has_glyph(lig):
                out.append(lig)
                out.extend(chars[i + 1:j])  # marks on the lam
                i = j + 1
                continue
        joined_after = nxt is not None and _joins_left(ch) and _joins(nxt)
        f = forms.get(ch, {})
        tag = ("medial" if joined_before and joined_after else "final" if joined_before
               else "initial" if joined_after else "isolated")
        form = f.get(tag) or f.get("isolated")
        out.append(form if form and has_glyph(form) else ch)
        i += 1
    return "".join(out)


# --- Right-to-left lines ------------------------------------------------------------------------

_MIRROR = dict(zip("()[]{}<>«»", ")(][}{><»«"))
_JOINS_NUMBERS = set("+-−.,:/×÷")  # between two digits, part of the number ("12+5", "3.5", "1/2")
_TERMINATORS = set("$%¢£€¥°#٪")


def _kind(ch: str) -> str:
    """'R' right-to-left letter, 'L' left-to-right letter, 'EN' digit, 'N' anything else."""
    if ch.isdigit():
        return "EN"
    cat = unicodedata.category(ch)
    if is_arabic(ch) and cat[0] in "LM":
        return "R"
    if cat[0] == "L" or (cat[0] == "M" and not is_arabic(ch)):
        return "L"
    return "N"


def rtl_line(line: str) -> bool:
    """The line's direction, from its first letter (Unicode's rule): "ratio = نسبة" reads left to right."""
    first = next((k for k in map(_kind, line) if k in ("L", "R")), "L")
    return first == "R"


def visual(line: str, rtl: bool | None = None) -> str:
    """One line of mixed-direction text (already shaped) in the order to draw it left to right. The line's
    direction is rtl, or else comes from its first letter; Latin words and numbers keep their own order
    inside right-to-left text, brackets pair up, and punctuation between runs follows the Unicode
    bidirectional algorithm. A simplified version of that algorithm (one level of embedding), enough for
    worksheet text."""
    if not has_rtl(line):
        return line
    base = 1 if (rtl_line(line) if rtl is None else rtl) else 0
    kinds = [_kind(ch) for ch in line]
    for k in range(1, len(line) - 1):  # "12+5", "3.5": a separator between digits is part of the number
        if kinds[k] == "N" and line[k] in _JOINS_NUMBERS and kinds[k - 1] == kinds[k + 1] == "EN":
            kinds[k] = "EN"
    changed = True
    while changed:  # "$15", "50%", "3°": a currency or percent sign next to a number goes with it (rule W5)
        changed = False
        for k, ch in enumerate(line):
            if kinds[k] == "N" and ch in _TERMINATORS and (
                    (k > 0 and kinds[k - 1] == "EN") or (k + 1 < len(line) and kinds[k + 1] == "EN")):
                kinds[k] = "EN"
                changed = True
    # A number takes the direction of the letters before it: inside Arabic it sits in the right-to-left run.
    strong, last = [], "R" if base else "L"
    for kd in kinds:
        if kd in ("L", "R"):
            last = kd
        strong.append("R" if kd == "EN" and last == "R" else "L" if kd == "EN" else kd)
    pair_dir: dict[int, str] = {}  # brackets: both of a pair take the direction of what they hold (rule N0)
    stack = []
    for k, ch in enumerate(line):
        if ch in "([{«":
            stack.append(k)
        elif ch in ")]}»" and stack:
            k0 = stack.pop()
            inside = {strong[j] for j in range(k0 + 1, k) if strong[j] != "N"}
            embed = "R" if base else "L"
            d = embed if embed in inside else (inside - {embed}).pop() if inside else None
            if d:
                pair_dir[k0] = pair_dir[k] = d
    levels = []
    for k, kd in enumerate(kinds):
        if k in pair_dir:
            kd = pair_dir[k]
        if kd == "EN":
            levels.append(2 if strong[k] == "R" else base + (base % 2))  # numbers are left to right inside
            continue
        if kd == "N":
            before = next((strong[j] for j in range(k - 1, -1, -1) if strong[j] != "N"), "R" if base else "L")
            after = next((strong[j] for j in range(k + 1, len(line)) if strong[j] != "N"), "R" if base else "L")
            kd = before if before == after else ("R" if base else "L")
        levels.append((1 if kd == "R" else 2) if base else (1 if kd == "R" else 0))
    chars = [_MIRROR.get(ch, ch) if lv % 2 else ch for ch, lv in zip(line, levels)]
    for level in range(max(levels), 0, -1):  # reverse every run at or above each level, highest first
        k = 0
        while k < len(chars):
            if levels[k] >= level:
                j = k
                while j < len(chars) and levels[j] >= level:
                    j += 1
                chars[k:j], levels[k:j] = chars[k:j][::-1], levels[k:j][::-1]
                k = j
            else:
                k += 1
    return "".join(chars)
