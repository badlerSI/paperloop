"""Classroom pieces on paper: fold-over cards, board games, and foldables, from one deck of cards.

Claude writes one pieces file (JSON, described in references/pieces-format.md): a deck of cards and the
pieces to make from it. `build` writes pieces.pdf: a page for the teacher (what's in the file, what to
print it on, prep, materials), then each piece, starting on a new page. Everything prints one-sided in
black and white on US Letter, and needs only scissors to make (a glue stick helps, but is optional).

- cards: fold-over question cards, with the answer upside down on the bottom half, so no duplex is needed
- blank_cards: the same cards, empty, for students to write their own
- snake_race, question_checkers, four_in_a_row, chess_quiz: rules for games on any checker or chess
  board, played with the cards and a die; board: a board to print, for a class without one
- die, spinner, pawns: a paper die, a paper-clip spinner, and stand-up tent pawns
- fortune_teller: a cootie catcher with 8 questions under its flaps and the answers beneath them
- minibook: an 8-page book from one sheet (a zine fold), filled in from the deck or blank
- abcd: A, B, C, D cards, so the whole class holds up an answer at once
- bingo: unique boards from the deck's answers, and a caller sheet

The three foldables whose layout depends on folding (cards, fortune teller, mini-book) are laid out from
a model of their folds (card_fold, FortuneTeller, zine_book), which tests/test_pieces.py checks.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import zlib
from pathlib import Path

import numpy as np
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from . import fonts as F
from . import sheet as S

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter, portrait
MARGIN = 36.0  # every mark stays 0.4in or more from the edge, where any printer reaches
FOOT_Y = 30.5  # the page label's baseline, in the margin but still inside 0.4in
INK, LABEL, RULE, LINES, FILL = 0.0, 0.45, 0.3, 0.72, 0.87  # FILL is light enough to write on
DASH = (4, 3)

TYPES = {
    "cards": "Fold-over cards", "blank_cards": "Blank cards", "snake_race": "Snake Race",
    "question_checkers": "Question Checkers", "four_in_a_row": "Four in a Row", "chess_quiz": "Chess Quiz",
    "board": "Game board", "die": "Paper die", "spinner": "Spinner", "pawns": "Tent pawns",
    "fortune_teller": "Fortune teller", "minibook": "Mini-book", "abcd": "ABCD answer cards", "bingo": "Bingo",
}
GAMES = ("snake_race", "question_checkers", "four_in_a_row", "chess_quiz")
OPTIONS = {"blank_cards": ("pages",), "die": ("faces",), "spinner": ("sectors",), "pawns": ("labels",),
           "fortune_teller": ("outer", "cards"), "minibook": ("title", "pages", "back", "cards", "blank", "also_blank"),
           "abcd": ("letters",), "bingo": ("boards", "size")}
TOP_FIELDS = ("title", "short_title", "subject", "grade", "grade_band", "seed", "cards", "pieces")
CARD_FIELDS = ("q", "a", "level", "kind")
VOCAB_MOVES = ["Define it", "Draw it", "Use it in a sentence", "Opposite", "Example", "Act it out"]


class PiecesError(ValueError):
    pass


# --- Reading the pieces file ----------------------------------------------------------

def _text(obj: dict, name: str, where: str, required: bool = True) -> str:
    value = obj.get(name)
    if isinstance(value, bool) or not isinstance(value, (str, int, float, type(None))):
        raise PiecesError(f'{where}: "{name}" must be text, not {type(value).__name__}')
    value = "" if value is None else str(value).strip()
    if required and not value:
        raise PiecesError(f'{where}: missing "{name}"')
    return value


def _unknown(obj: dict, known, where: str, hint: str = "") -> None:
    extra = [k for k in obj if k not in known]
    if extra:
        raise PiecesError(f'{where}: unknown field "{extra[0]}"; {hint or "use " + ", ".join(known)}')


def _strings(value, where: str, name: str, low: int, high: int) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, (str, int, float)) and not isinstance(v, bool)
                                              for v in value):
        raise PiecesError(f'{where}: "{name}" must be a list of short texts')
    out = [str(v).strip() for v in value]
    if any(not v for v in out):
        raise PiecesError(f'{where}: "{name}" has an empty entry')
    if not low <= len(out) <= high:
        raise PiecesError(f'{where}: "{name}" needs {low if low == high else f"{low} to {high}"} entries; it has '
                          f'{len(out)}')
    return out


def _card_numbers(value, where: str, n_cards: int, count: int) -> list[int]:
    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise PiecesError(f'{where}: "cards" is a list of card numbers (1 is the first card in the deck)')
    if len(value) != count:
        raise PiecesError(f'{where}: "cards" needs exactly {count} card numbers; it has {len(value)}')
    bad = [v for v in value if not 1 <= v <= n_cards]
    if bad:
        raise PiecesError(f'{where}: card {bad[0]} isn\'t in the deck, which has cards 1-{n_cards}')
    if len(set(value)) != len(value):
        raise PiecesError(f'{where}: "cards" lists a card twice')
    return value


def normalize(data: dict) -> dict:
    """Defaults filled in and every field checked, with errors that say what to fix."""
    if not isinstance(data, dict):
        raise PiecesError('pieces file: it\'s one JSON object with "title", "grade", "cards", and "pieces"')
    _unknown(data, TOP_FIELDS, "pieces file")
    title = _text(data, "title", "pieces file")
    if data.get("grade") is None and not data.get("grade_band"):
        raise PiecesError('pieces file: missing "grade" (2-12); it sets the type sizes')
    try:
        grade = S.grade_of(data)
    except (TypeError, ValueError):
        raise PiecesError('pieces file: "grade" must be a whole number from 2 to 12') from None
    if not 2 <= grade <= 12:
        raise PiecesError(f'pieces file: "grade" must be 2 to 12, not {grade}')
    seed = data.get("seed", 1)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise PiecesError('pieces file: "seed" must be a whole number (change it for different bingo boards)')
    short = _text(data, "short_title", "pieces file", required=False) or _shorten(title)
    if len(short) > 24:
        raise PiecesError(f'pieces file: "short_title" is printed on every card; keep it to 24 characters (it has '
                          f'{len(short)})')

    raw_cards = data.get("cards")
    if not isinstance(raw_cards, list) or not raw_cards:
        raise PiecesError('pieces file: "cards" must be a list of cards, like [{"q": "...", "a": "..."}]')
    cards = []
    for k, raw in enumerate(raw_cards, start=1):
        where = f"card {k}"
        if not isinstance(raw, dict):
            raise PiecesError(f'{where}: a card is an object like {{"q": "What do roots do?", "a": "Take in water"}}')
        for wrong, right in (("question", "q"), ("answer", "a"), ("term", "q"), ("meaning", "a"), ("front", "q"),
                             ("back", "a")):
            if wrong in raw and right not in raw:
                raise PiecesError(f'{where}: write "{wrong}" as "{right}"' + (' and add "kind": "term"'
                                                                              if wrong in ("term", "meaning") else ""))
        _unknown(raw, CARD_FIELDS, where, 'a card has "q", "a", "level" (1-3), and "kind" ("question" or "term")')
        level = raw.get("level")
        if level is not None and (isinstance(level, bool) or level not in (1, 2, 3)):
            raise PiecesError(f'{where}: "level" is 1, 2, or 3 (how hard the card is), not {level!r}')
        kind = raw.get("kind", "question")
        if kind not in ("question", "term"):
            raise PiecesError(f'{where}: "kind" is "question" or "term" (a vocabulary word, with its meaning in "a")')
        cards.append({"n": k, "q": _text(raw, "q", where), "a": _text(raw, "a", where), "level": level, "kind": kind})

    raw_pieces = data.get("pieces")
    if not isinstance(raw_pieces, list) or not raw_pieces:
        raise PiecesError(f'pieces file: "pieces" must be a list, such as ["cards", "snake_race", "bingo"]; '
                          f'the types are {", ".join(TYPES)}')
    pieces = []
    for k, raw in enumerate(raw_pieces, start=1):
        p = {"type": raw} if isinstance(raw, str) else raw
        if not isinstance(p, dict) or "type" not in p:
            raise PiecesError(f'pieces {k}: give a type ("cards") or an object with "type" ({{"type": "die", ...}})')
        kind = p["type"]
        if kind not in TYPES:
            close = [t for t in TYPES if t.split("_")[0] in str(kind) or str(kind).split("_")[0] in t]
            raise PiecesError(f'pieces {k}: unknown type "{kind}"' + (f' (did you mean "{close[0]}"?)' if close else "")
                              + f'; the types are {", ".join(TYPES)}')
        where = f"pieces {k} ({kind})"
        _unknown(p, ("type",) + OPTIONS.get(kind, ()), where,
                 f'{kind} takes ' + (", ".join(f'"{o}"' for o in OPTIONS[kind]) if kind in OPTIONS else "no options"))
        pieces.append(_piece_options(dict(p), where, cards))
    return {"title": title, "short": short, "subject": _text(data, "subject", "pieces file", required=False),
            "grade": grade, "seed": seed, "cards": cards, "pieces": pieces}


def _shorten(title: str, most: int = 20) -> str:
    if len(title) <= most:
        return title
    words, out = title.split(), ""
    for w in words:
        if len(out) + len(w) + (1 if out else 0) > most:
            break
        out = f"{out} {w}".strip()
    return out or title[:most]


def _piece_options(p: dict, where: str, cards: list[dict]) -> dict:
    kind, n = p["type"], len(cards)
    if kind == "blank_cards":
        pages = p.setdefault("pages", 1)
        if not isinstance(pages, int) or isinstance(pages, bool) or not 1 <= pages <= 10:
            raise PiecesError(f'{where}: "pages" is how many pages of blank cards, 1 to 10')
    elif kind == "die":
        faces = p.get("faces", "pips")
        if faces == "vocab":
            faces = list(VOCAB_MOVES)
        p["faces"] = faces if faces == "pips" else _strings(faces, where, "faces", 6, 6)
    elif kind == "spinner":
        p["sectors"] = _strings(p.get("sectors", ["1 dot", "2 dots", "3 dots", "1 dot", "2 dots", "3 dots"]),
                                where, "sectors", 2, 8)
    elif kind == "pawns":
        p["labels"] = _strings(p.get("labels", ["1", "2", "3", "4", "5", "6"]), where, "labels", 2, 6)
    elif kind == "fortune_teller":
        p["outer"] = _strings(p.get("outer", ["Red", "Blue", "Green", "Gold"]), where, "outer", 4, 4)
        if "cards" in p:
            p["cards"] = _card_numbers(p["cards"], where, n, 8)
        elif n < 8:
            raise PiecesError(f'{where}: needs 8 cards for its 8 flaps; the deck has {n}. Add cards, or leave the '
                              'fortune teller out')
        else:  # the 8 shortest: the flaps are small
            length = lambda k: len(cards[k - 1]["q"]) + len(cards[k - 1]["a"])  # noqa: E731
            p["cards"] = sorted(sorted(range(1, n + 1), key=length)[:8])
    elif kind == "minibook":
        for flag in ("blank", "also_blank"):
            if not isinstance(p.setdefault(flag, False), bool):
                raise PiecesError(f'{where}: "{flag}" is true or false')
        p["title"] = _text(p, "title", where, required=False)
        p["back"] = _text(p, "back", where, required=False)
        if "pages" in p:
            if not isinstance(p["pages"], list) or len(p["pages"]) != 6:
                raise PiecesError(f'{where}: "pages" is a list of the 6 inside pages, each {{"heading": "...", '
                                  f'"text": "..."}}')
            for k, page in enumerate(p["pages"], start=1):
                if not isinstance(page, dict):
                    raise PiecesError(f'{where}, page {k}: a page is {{"heading": "...", "text": "..."}}')
                _unknown(page, ("heading", "text"), f"{where}, page {k}")
                page["heading"] = _text(page, "heading", f"{where}, page {k}", required=False)
                page["text"] = _text(page, "text", f"{where}, page {k}")
            if "cards" in p:
                raise PiecesError(f'{where}: give "pages" or "cards", not both')
        elif not p["blank"]:
            if "cards" in p:
                numbers = _card_numbers(p["cards"], where, n, 6)
            elif n < 6:
                raise PiecesError(f'{where}: a mini-book from the deck needs 6 cards; the deck has {n}. Write its '
                                  '"pages", or use "blank": true')
            else:
                numbers = list(range(1, 7))
            p["pages"] = [{"heading": cards[k - 1]["q"], "text": cards[k - 1]["a"]} for k in numbers]
    elif kind == "abcd":
        p["letters"] = _strings(p.get("letters", ["A", "B", "C", "D"]), where, "letters", 2, 4)
    elif kind == "bingo":
        boards, size = p.setdefault("boards", 30), p.setdefault("size", 5)
        if not isinstance(boards, int) or isinstance(boards, bool) or not 1 <= boards <= 60:
            raise PiecesError(f'{where}: "boards" is how many boards to print (one per student), 1 to 60')
        if size not in (3, 4, 5):
            raise PiecesError(f'{where}: "size" is 5 (5x5 with a free middle), 4, or 3')
        need = size * size - (size % 2)  # odd sizes have a free middle square
        items = {(c["a"] if c["kind"] == "question" else c["q"]).lower() for c in cards}
        if len(items) < need:
            raise PiecesError(f'{where}: a {size}x{size} board needs {need} different answers, and the deck has '
                              f'{len(items)}. Add cards, or use "size": ' + ("4 (16 answers) or 3 (8 answers)"
                                                                            if size == 5 else "3 (8 answers)"))
    p["name"] = TYPES[kind]
    return p


def level_problems(P: dict) -> list[str]:
    """Pieces that use card levels when the deck doesn't have them."""
    have = {c["level"] for c in P["cards"]}
    out, kinds = [], {p["type"] for p in P["pieces"]}
    needs = {"snake_race": ({3}, "a 3-dot card for landing on a corner square"),
             "question_checkers": ({3}, "a 3-dot card to become a king"),
             "chess_quiz": ({1, 2, 3}, "cards of each level, to match the piece captured")}
    for kind, (levels, why) in needs.items():
        missing = sorted(levels - have)
        if kind in kinds and missing:
            out.append(f'{TYPES[kind]} uses {why}, but no card has "level": {" or ".join(map(str, missing))}. Give '
                       'the harder cards a level')
    if kinds & set(GAMES) and 3 not in have and not out:
        out.append('the games\' "explain it" rule is for 3-dot cards, and no card has "level": 3')
    return out


def all_texts(P: dict) -> list[str]:
    out = [P["title"], P["short"]] + [c[k] for c in P["cards"] for k in ("q", "a")]
    for p in P["pieces"]:
        for key in ("faces", "sectors", "labels", "outer", "letters"):
            if isinstance(p.get(key), list):
                out += p[key]
        out += [p.get("title", ""), p.get("back", "")]
        if isinstance(p.get("pages"), list):
            out += [x[k] for x in p["pages"] for k in ("heading", "text")]
    return [t for t in out if t]


# --- Drawing: text that fits, lines, and icons ---------------------------------------------

def sizes(grade: int) -> dict:
    """Type sizes by grade: the card text starts at `card` and may shrink to `min` before it warns."""
    if grade <= 3:
        return {"card": 18.0, "min": 12.0, "body": 13.0, "small": 10.5, "head": 22.0}
    if grade <= 5:
        return {"card": 16.0, "min": 9.0, "body": 12.0, "small": 10.0, "head": 20.0}
    return {"card": 14.0, "min": 9.0, "body": 11.5, "small": 9.5, "head": 20.0}


class Pen:
    """The canvas and fonts, and text that always fits its box: it shrinks to fit, warns when it shrinks
    below the grade's minimum, and as a last resort cuts the text (and says so)."""

    def __init__(self, c: canvas.Canvas, fonts: F.Fonts, grade: int, warnings: list[str]):
        self.c, self.f, self.grade, self.warnings = c, fonts, grade, warnings
        self.sz = sizes(grade)
        self.page = 0

    def width(self, text: str, font: str, size: float) -> float:
        return pdfmetrics.stringWidth(self.f.text(text), font, size)

    def wrap(self, text: str, font: str, size: float, width: float) -> list[str]:
        out = []
        for para in self.f.text(text).split("\n"):
            out += simpleSplit(para, font, size, width) or [""]
        return out

    def _warn(self, where: str, size: float, minimum: float, cut: bool) -> None:
        if not where:
            return
        if cut:
            self.warnings.append(f"{where} doesn't fit even at 6pt and was cut short: shorten it")
        else:
            self.warnings.append(f"{where} was shrunk to {size:g}pt to fit, below the {minimum:g}pt minimum for "
                                 f"grade {self.grade}: shorten it")

    def fit(self, text: str, font: str, w: float, h: float, start: float, where: str = "",
            minimum: float | None = None, leading: float = 1.2) -> tuple[float, list[str]]:
        """The biggest size, from start down, at which text wraps into w by h."""
        minimum = self.sz["min"] if minimum is None else minimum
        size = start
        while True:
            lines = self.wrap(text, font, size, w)
            if len(lines) * size * leading <= h + 0.01 and all(self.width(s, font, size) <= w + 0.01 for s in lines):
                if size < minimum - 1e-6:
                    self._warn(where, size, minimum, False)
                return size, self.balance(text, font, size, w, lines)
            if size <= 6:
                break
            size = max(6.0, size - 0.5)
        keep = max(1, int(h // (size * leading)))  # cut: what fits, ending in "..."
        lines = lines[:keep]
        while lines and self.width(lines[-1] + "...", font, size) > w:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
        self._warn(where, size, minimum, True)
        return size, lines

    def balance(self, text: str, font: str, size: float, w: float, lines: list[str]) -> list[str]:
        """The same number of lines, as even as they'll go: no lone word on the last line."""
        if len(lines) < 2 or "\n" in text:
            return lines
        lo = max(self.width(word, font, size) for word in self.f.text(text).split())
        hi = w
        for _ in range(12):
            mid = (lo + hi) / 2
            if len(self.wrap(text, font, size, mid)) == len(lines):
                hi = mid
            else:
                lo = mid
        return self.wrap(text, font, size, hi)

    def lines(self, lines: list[str], font: str, size: float, x0: float, x1: float, y0: float, y1: float,
              align: str = "center", valign: str = "middle", leading: float = 1.2, gray: float = INK) -> None:
        """Draws wrapped lines inside the box x0..x1, y0..y1 (cap height centered in each line's slot)."""
        c, lead = self.c, size * leading
        total = len(lines) * lead
        top = {"top": y1, "bottom": y0 + total}.get(valign, (y0 + y1) / 2 + total / 2)
        c.setFillGray(gray)
        c.setFont(font, size)
        for i, s in enumerate(lines):
            base = top - i * lead - (lead + 0.72 * size) / 2
            if align == "left":
                c.drawString(x0, base, s)
            elif align == "right":
                c.drawRightString(x1, base, s)
            else:
                c.drawCentredString((x0 + x1) / 2, base, s)

    def box(self, text: str, x0: float, y0: float, x1: float, y1: float, font: str | None = None,
            start: float | None = None, where: str = "", minimum: float | None = None, align: str = "center",
            valign: str = "middle", leading: float = 1.2, gray: float = INK) -> float:
        """Fits text into the box and draws it. Returns the size used."""
        font = font or self.f.regular
        size, lines = self.fit(text, font, x1 - x0, y1 - y0, start or self.sz["card"], where, minimum, leading)
        self.lines(lines, font, size, x0, x1, y0, y1, align, valign, leading, gray)
        return size

    def para(self, text: str, x: float, y_top: float, w: float, size: float, font: str | None = None,
             leading: float = 1.25, gray: float = INK) -> float:
        """Left-aligned wrapped text from y_top down (it's laid out to fit). Returns the y below it."""
        font = font or self.f.regular
        lines = self.wrap(text, font, size, w)
        self.lines(lines, font, size, x, x + w, y_top - len(lines) * size * leading, y_top, "left", "top", leading,
                   gray)
        return y_top - len(lines) * size * leading

    def para_height(self, text: str, w: float, size: float, font: str | None = None, leading: float = 1.25) -> float:
        return len(self.wrap(text, font or self.f.regular, size, w)) * size * leading

    # Text in a convex polygon (fortune teller triangles, spinner sectors), in the text's own frame
    def fit_poly(self, text: str, font: str, poly: list[tuple[float, float]], start: float, where: str = "",
                 minimum: float | None = None, pad: float = 4.0, leading: float = 1.15):
        """Lines and baselines that put text inside poly (x to the right, y up, in the text's frame). Each line
        is as wide as the polygon allows at its height; the block sits as near the middle as it can."""
        minimum = self.sz["min"] if minimum is None else minimum
        found = self._fit_poly(self.f.text(text).split(), font, poly, start, 6.0, pad, leading)
        if found:
            if found[0] < minimum - 1e-6:
                self._warn(where, found[0], minimum, False)
            return found
        words = self.f.text(text).split()  # too long even at 6pt: as many words as fit, then "..."
        for k in range(len(words) - 1, 0, -1):
            found = self._fit_poly(words[:k] + ["..."], font, poly, 6.0, 6.0, pad, leading)
            if found:
                break
        self._warn(where, 6, minimum, True)
        return found or (6.0, [])

    def _fit_poly(self, words, font, poly, start, smallest, pad, leading):
        ys = [p[1] for p in poly]
        anchor = sum(ys) / len(ys)
        size = start
        while size >= smallest:
            lead, cap, desc = size * leading, 0.72 * size, 0.22 * size
            for n in range(1, int((max(ys) - min(ys)) / lead) + 1):
                tops = np.arange(max(ys) - pad, min(ys) + pad + n * lead - 0.01, -1.5)
                for top in sorted(tops, key=lambda t: abs(t - n * lead / 2 - anchor)):
                    slots = []
                    for i in range(n):
                        base = top - i * lead - (lead + cap) / 2
                        span = _band(poly, base - desc - pad, base + cap + pad)
                        if not span or span[1] - span[0] < 2 * pad + size:
                            break
                        slots.append((base, span[0] + pad, span[1] - pad))
                    if len(slots) < n:
                        continue
                    placed = _fill(words, slots, lambda s: self.width(s, font, size))
                    if placed:
                        return size, placed
            size -= 0.5
        return None

    def poly_text(self, text: str, poly_page: list, up: tuple[float, float], font: str, start: float,
                  where: str = "", minimum: float | None = None, pad: float = 4.0, gray: float = INK) -> float:
        """Text inside a convex polygon on the page, reading with its top toward `up` (a unit vector)."""
        ox = sum(p[0] for p in poly_page) / len(poly_page)
        oy = sum(p[1] for p in poly_page) / len(poly_page)
        ux, uy = up
        rx, ry = uy, -ux  # reading direction: up turned a quarter clockwise
        local = [((x - ox) * rx + (y - oy) * ry, (x - ox) * ux + (y - oy) * uy) for x, y in poly_page]
        size, placed = self.fit_poly(text, font, local, start, where, minimum, pad)
        c = self.c
        c.saveState()
        c.translate(ox, oy)
        c.rotate(math.degrees(math.atan2(ry, rx)))
        c.setFillGray(gray)
        c.setFont(font, size)
        for line, base, x0, x1 in placed:
            c.drawCentredString((x0 + x1) / 2, base, line)
        c.restoreState()
        return size

    def footer(self, title: str) -> None:
        """The page number, small, in the bottom margin (the teacher's page lists pieces by page)."""
        self.c.setFillGray(0.55)
        self.c.setFont(self.f.regular, 7)
        self.c.drawCentredString(PAGE_W / 2, FOOT_Y, self.f.text(f"{title}  |  page {self.page}"))

    def header(self, title: str, piece: str, note: str = "") -> float:
        """A piece's page heading. Returns the y just below it."""
        c = self.c
        top = PAGE_H - MARGIN
        size = 15.0
        while size > 10 and self.width(piece, self.f.bold, size) + self.width(title, self.f.regular, 10) + 30 > \
                PAGE_W - 2 * MARGIN:
            size -= 0.5
        c.setFillGray(INK)
        c.setFont(self.f.bold, size)
        c.drawString(MARGIN, top - size, self.f.text(piece))
        c.setFillGray(LABEL)
        c.setFont(self.f.regular, 10)
        c.drawRightString(PAGE_W - MARGIN, top - size, self.f.text(title))
        y = top - size - 6
        if note:
            y = self.para(note, MARGIN, y - 2, PAGE_W - 2 * MARGIN, 10, gray=0.25) - 2
        return y - 6


def _band(poly, a: float, b: float):
    """The x interval a convex polygon covers at every height from a to b, or None."""
    spans = [_span_at(poly, y) for y in (a, b)]
    if not all(spans):
        return None
    lo, hi = max(s[0] for s in spans), min(s[1] for s in spans)
    return (lo, hi) if hi > lo else None


def _span_at(poly, y: float):
    xs = []
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 - y) * (y1 - y) <= 0 and y0 != y1:
            xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        elif y0 == y1 == y:
            xs += [x0, x1]
    return (min(xs), max(xs)) if len(xs) >= 2 else None


def _fill(words: list[str], slots, measure):
    """Greedy word wrap into lines of different widths. [(line, baseline, x0, x1)], or None if it won't fit."""
    out, i = [], 0
    for base, x0, x1 in slots:
        line = ""
        while i < len(words) and measure((line + " " + words[i]).strip()) <= x1 - x0:
            line = (line + " " + words[i]).strip()
            i += 1
        if not line:
            return None
        out.append((line, base, x0, x1))
        if i == len(words):
            return out
    return None


def cut_line(c: canvas.Canvas, x0: float, y0: float, x1: float, y1: float) -> None:
    c.setDash()
    c.setStrokeGray(INK)
    c.setLineWidth(0.9)
    c.line(x0, y0, x1, y1)


def fold_line(c: canvas.Canvas, x0: float, y0: float, x1: float, y1: float, gray: float = RULE) -> None:
    c.setStrokeGray(gray)
    c.setLineWidth(0.8)
    c.setDash(*DASH)
    c.line(x0, y0, x1, y1)
    c.setDash()


def poly(c: canvas.Canvas, pts, stroke: bool = True, fill: float | None = None, close: bool = True,
         width: float = 0.9, gray: float = INK, dash: bool = False) -> None:
    p = c.beginPath()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    if close:
        p.close()
    if fill is not None:
        c.setFillGray(fill)
    c.setStrokeGray(gray)
    c.setLineWidth(width)
    if dash:
        c.setDash(*DASH)
    c.drawPath(p, stroke=1 if stroke else 0, fill=1 if fill is not None else 0)
    c.setDash()


def arrow(c: canvas.Canvas, pts, head: float = 5.0, width: float = 1.0, gray: float = INK) -> None:
    """A polyline with a filled head at its last point."""
    poly(c, pts, close=False, width=width, gray=gray)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    left = (x1 - head * math.cos(a - 0.45), y1 - head * math.sin(a - 0.45))
    right = (x1 - head * math.cos(a + 0.45), y1 - head * math.sin(a + 0.45))
    poly(c, [(x1, y1), left, right], fill=gray, width=0.5, gray=gray)


def arc_points(cx: float, cy: float, r: float, a0: float, a1: float, n: int = 24) -> list[tuple[float, float]]:
    """Points along a circle from angle a0 to a1 (degrees, counterclockwise from 3 o'clock)."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def dots(c: canvas.Canvas, x: float, y: float, n: int, r: float = 2.3, gap: float = 6.5, filled: bool = True,
         align: str = "left") -> None:
    """Level dots: n filled circles (or empty ones, for a student to fill in)."""
    if align == "right":
        x -= (n - 1) * gap
    c.setFillGray(INK)
    c.setStrokeGray(INK)
    c.setLineWidth(0.7)
    for i in range(n):
        c.circle(x + i * gap, y, r, stroke=0 if filled else 1, fill=1 if filled else 0)


def scissors(c: canvas.Canvas, x: float, y: float, size: float = 12.0, angle: float = 0.0) -> None:
    """A small scissors icon, blades pointing along `angle` (degrees), the pivot at (x, y)."""
    c.saveState()
    c.translate(x, y)
    c.rotate(angle)
    s = size
    c.setStrokeGray(INK)
    c.setLineWidth(0.3)
    for sign in (1, -1):  # each blade runs from one handle, across the pivot, to a tip on the other side
        poly(c, [(-0.24 * s, sign * 0.12 * s), (-0.17 * s, sign * 0.22 * s), (0.85 * s, -sign * 0.13 * s)],
             fill=INK, width=0.3)
    c.setFillGray(1)
    c.setStrokeGray(INK)
    c.setLineWidth(max(0.7, s * 0.07))
    c.ellipse(-0.66 * s, 0.06 * s, -0.22 * s, 0.36 * s, stroke=1, fill=1)
    c.ellipse(-0.66 * s, -0.36 * s, -0.22 * s, -0.06 * s, stroke=1, fill=1)
    c.circle(0.0, 0.0, 0.05 * s, stroke=0, fill=1)
    c.restoreState()


def star(c: canvas.Canvas, x: float, y: float, r: float, fill: float = INK) -> None:
    pts = [(x + (r if i % 2 == 0 else r * 0.45) * math.cos(math.radians(90 + 36 * i)),
            y + (r if i % 2 == 0 else r * 0.45) * math.sin(math.radians(90 + 36 * i))) for i in range(10)]
    poly(c, pts, fill=fill, width=0.4)


def step_number(pen: Pen, x: float, y: float, n: int, r: float = 8.0) -> None:
    """A numbered black disc for a direction step."""
    c = pen.c
    c.setFillGray(INK)
    c.circle(x, y, r, stroke=0, fill=1)
    c.setFillGray(1)
    c.setFont(pen.f.bold, r * 1.2)
    c.drawCentredString(x, y - r * 0.42, str(n))


def checkbox(c: canvas.Canvas, x: float, y: float, s: float = 9.0) -> None:
    c.setStrokeGray(INK)
    c.setLineWidth(0.8)
    c.rect(x, y, s, s, stroke=1, fill=0)


def turn_arrow(c: canvas.Canvas, cx: float, cy: float, w: float, h: float, gray: float = INK) -> None:
    """A curved arrow: turn it over, side to side."""
    pts = [(cx + w / 2 * math.cos(math.radians(a)), cy + h / 2 * math.sin(math.radians(a)))
           for a in range(160, 15, -10)]
    arrow(c, pts, head=4.5, gray=gray)


def steps_row(pen: Pen, x0: float, x1: float, top: float, steps, draw_h: float, caption: float = 10.0) -> float:
    """Numbered direction steps in a row: each a small diagram (draw(x, y, w, h)) above a short caption.
    Returns the y below the captions."""
    n, gap = len(steps), 10.0
    w = (x1 - x0 - gap * (n - 1)) / n
    low = top
    for i, (draw, text) in enumerate(steps):
        x = x0 + i * (w + gap)
        step_number(pen, x + 8, top - 8, i + 1)
        draw(x + 4, top - draw_h, w - 8, draw_h - 4)
        size, lines = pen.fit(text, pen.f.regular, w, 4 * caption * 1.2, caption, f"step {i + 1} of the directions",
                              minimum=9)
        pen.lines(lines, pen.f.regular, size, x, x + w, top - draw_h - 4 - len(lines) * size * 1.2,
                  top - draw_h - 4, "center", "top")
        low = min(low, top - draw_h - 4 - len(lines) * size * 1.2)
    return low


# --- Fold models -------------------------------------------------------------------------------
# Each foldable is laid out from a model of its folds, so a label printed flat ends up where kids look,
# reading upright. tests/test_pieces.py runs the models forward and checks every label.

_FOLD_BACK = np.diag([1.0, -1.0, -1.0])  # half a turn about the fold line (the x axis)
_TURNS = {"side": np.diag([-1.0, 1.0, -1.0]), "top": np.diag([1.0, -1.0, -1.0]), "none": np.eye(3)}


def card_fold(point, up, turn: str = "side"):
    """Where ink printed on a fold-over card ends up, and which way it reads.

    The strip lies printing up (+z), its fold line on y = 0: the question above it, the answer below.
    Folding the answer half behind the question half, printing out, turns that half 180 degrees about the
    fold line: (x, y, z) -> (x, -y, -z). Turning the card over side to side, as you turn a page, is half a
    turn about a vertical line: (x, y, z) -> (-x, y, -z); top to bottom is about a horizontal line:
    (x, y, z) -> (x, -y, -z). Ink faces the reader when its normal ends up at +z.

    An answer printed upside down (up = (0, -1)) on the bottom half: the fold takes its up to (0, 1) and its
    normal to -z (facing away); a side-to-side turn keeps up at (0, 1) and brings the normal back to +z. So
    the answer reads upright after a side-to-side turn, and upside down after a top-to-bottom turn (up goes
    back to (0, -1)). Hence the direction "turn it over side to side". Either half can be the one folded
    back: both give the same two-sided card.

    Returns ((x, y), up, right, faces the reader)."""
    x, y = point
    m = _TURNS[turn] @ (_FOLD_BACK if y < 0 else np.eye(3))
    p, u = m @ [x, y, 0.0], m @ [up[0], up[1], 0.0]
    r, n = m @ [up[1], -up[0], 0.0], m @ [0.0, 0.0, 1.0]
    return (p[0], p[1]), (u[0], u[1]), (r[0], r[1]), bool(n[2] > 0)


def _reflect(a, b):
    """A reflection as (A, b): x -> A x + b."""
    return np.array(a, dtype=float), np.array(b, dtype=float)


# The printed square is [-1, 1] x [-1, 1], printing up. Each step either turns the whole paper over (side
# to side: a reflection in the vertical axis) or folds some regions over onto the top of the stack (a
# reflection in the fold line). A fold step's regions are tested in the paper's position at that step.
FT_STEPS = [
    ("turn", None),
    ("fold", [(lambda x, y: x + y > 1, _reflect([[0, -1], [-1, 0]], [1, 1])),  # each corner to the middle
              (lambda x, y: -x + y > 1, _reflect([[0, 1], [1, 0]], [-1, 1])),
              (lambda x, y: -x - y > 1, _reflect([[0, -1], [-1, 0]], [-1, -1])),
              (lambda x, y: x - y > 1, _reflect([[0, 1], [1, 0]], [1, -1]))]),
    ("turn", None),
    ("fold", [(lambda x, y: x > 0.5, _reflect([[-1, 0], [0, 1]], [1, 0])),  # the new corners to the middle
              (lambda x, y: x < -0.5, _reflect([[-1, 0], [0, 1]], [-1, 0])),
              (lambda x, y: y > 0.5, _reflect([[1, 0], [0, -1]], [0, 1])),
              (lambda x, y: y < -0.5, _reflect([[1, 0], [0, -1]], [0, -1]))]),
]
_TURN_OVER = _reflect([[-1, 0], [0, 1]], [0, 0])
LIFTED = 3  # the state before the last fold: what you see with a flap lifted


class FortuneTeller:
    """A fortune teller (cootie catcher) folded from the printed square, region by region.

    The square's fold lines (its diagonals and midlines, the diamond joining the edge midpoints, and the
    lines at a quarter of the way in) cut it into 32 small triangles that no fold ever splits, so each
    triangle moves as one piece. Folding them all records, for every triangle and every step, its corners,
    the map from the printed square (x -> A x + b), whether its printing faces up (parity), its height in
    the stack (z), and the fold steps that moved it.

    After the last fold the square is [-1/2, 1/2]^2, and its 8 triangles (cut by the diagonals and midlines)
    are numbered 1-8 clockwise from 12 o'clock, seen from the top. From the top down, each holds:
    - the number on the flap (moved by both folds, printing up);
    - the question on the flap's underside (moved by the last fold only, printing down onto the base);
    - the answer, on the base under the flap (never moved, printing up);
    - an outer label's corner square, on the bottom (moved by the first fold only, printing down).
    """

    def __init__(self):
        self.regions = []
        for i in range(4):
            for j in range(4):
                x0, y0 = -1 + 0.5 * i, -1 + 0.5 * j
                sq = [(x0, y0), (x0 + 0.5, y0), (x0 + 0.5, y0 + 0.5), (x0, y0 + 0.5)]
                # split on the diagonal that's a fold line: x = y or x + y = 0 near the big diagonals,
                # |x| + |y| = 1 in the edge squares
                cx, cy = x0 + 0.25, y0 + 0.25
                edge = abs(abs(cx) - abs(cy)) > 0.4
                along = (cx * cy > 0) != edge  # the diagonal running bottom-left to top-right
                halves = ([sq[0], sq[1], sq[2]], [sq[0], sq[2], sq[3]]) if along else \
                    ([sq[0], sq[1], sq[3]], [sq[1], sq[2], sq[3]])
                for tri in halves:
                    self.regions.append({"printed": tri, "states": [(tri, np.eye(2), np.zeros(2), 1, 0.0, ())]})
        self._fold()

    def _fold(self) -> None:
        for step, (kind, rules) in enumerate(FT_STEPS, start=1):
            current = [r["states"][-1] for r in self.regions]
            moves = []
            for verts, A, b, parity, z, moved in current:
                cx, cy = np.mean(verts, axis=0)
                rule = _TURN_OVER if kind == "turn" else next(
                    (m for test, m in rules if test(cx, cy)), None)
                moves.append(rule)
            top = max(s[4] for s in current)
            top_moved = max((s[4] for s, m in zip(current, moves) if m is not None), default=0)
            for r, s, m in zip(self.regions, current, moves):
                verts, A, b, parity, z, moved = s
                if m is None:
                    r["states"].append(s)
                    continue
                M, t = m
                new = [tuple(M @ np.array(v) + t) for v in verts]
                if kind == "turn":  # the stack turns over: top becomes bottom
                    r["states"].append((new, M @ A, M @ b + t, -parity, -z, moved))
                else:  # the moved layers land on top, in reverse order
                    r["states"].append((new, M @ A, M @ b + t, -parity, top + 1 + (top_moved - z), moved + (step,)))

    def role(self, r: dict) -> str:
        moved = r["states"][-1][5]
        return {(2, 4): "number", (4,): "question", (): "answer", (2,): "outer"}[moved]

    @staticmethod
    def sector(point) -> int:
        """1-8, clockwise from 12 o'clock, of a point on the folded square seen from the top."""
        angle = math.degrees(math.atan2(point[1], point[0]))
        return 1 + int(((90 - angle) % 360) // 45)

    @staticmethod
    def outward(point) -> tuple[float, float]:
        """The axis direction nearest a point's direction from the middle: outward along its flap."""
        x, y = point
        return (math.copysign(1.0, x), 0.0) if abs(x) > abs(y) else (0.0, math.copysign(1.0, y))

    def layout(self) -> dict:
        """Where each label prints, and which way is up for it on the printed square.

        number k, question k, answer k: the triangles that end up in sector k. Each reads with its top
        outward along its flap (toward the flap's hinge), in the view where kids read it: the number on the
        folded top, the question and answer with the flap lifted (the state before the last fold).
        outer i: the corner squares, clockwise from the printed top-left; each reads with its top toward
        its point of the finished fortune teller (the folded square's corner), seen from below.
        Printed up = A^T (up where it's read), since A is a rotation or reflection."""
        out = {"number": {}, "question": {}, "answer": {}, "outer": {}}
        for r in self.regions:
            role = self.role(r)
            final = r["states"][-1]
            centroid = np.mean(final[0], axis=0)
            if role == "outer":
                continue
            k = self.sector(centroid)
            view = final if role == "number" else r["states"][LIFTED]
            up = self.outward(np.mean(view[0], axis=0))
            out[role][k] = (r["printed"], tuple(view[1].T @ np.array(up)))
        corners = [(-1, 1), (1, 1), (1, -1), (-1, -1)]  # clockwise from the printed top-left
        for i, (sx, sy) in enumerate(corners, start=1):
            parts = [r for r in self.regions if self.role(r) == "outer"
                     and all(sx * x >= 0.5 - 1e-9 and sy * y >= 0.5 - 1e-9 for x, y in r["printed"])]
            final = parts[0]["states"][-1]
            cx, cy = np.mean(final[0], axis=0)
            tip = np.array([math.copysign(1, cx), math.copysign(1, cy)]) / math.sqrt(2)
            square = [(sx * 0.5, sy * 0.5), (sx * 1.0, sy * 0.5), (sx * 1.0, sy * 1.0), (sx * 0.5, sy * 1.0)]
            out["outer"][i] = (square, tuple(final[1].T @ tip))
        return out

    def forward(self, point, up, state: int | None = None):
        """A printed point and up vector carried through the folds (to `state`, default the end):
        (point, up, parity, z, moved)."""
        p = np.array(point, dtype=float)
        for r in self.regions:
            if _inside(p, r["printed"]):
                verts, A, b, parity, z, moved = r["states"][len(FT_STEPS) if state is None else state]
                return tuple(A @ p + b), tuple(A @ np.array(up, dtype=float)), parity, z, moved
        raise ValueError(f"{point} isn't on the printed square")


def _inside(p, tri, eps: float = 1e-9) -> bool:
    (x1, y1), (x2, y2), (x3, y3) = tri
    d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    a = ((y2 - y3) * (p[0] - x3) + (x3 - x2) * (p[1] - y3)) / d
    b = ((y3 - y1) * (p[0] - x3) + (x1 - x3) * (p[1] - y3)) / d
    return a >= -eps and b >= -eps and 1 - a - b >= -eps


def zine_book() -> list[tuple[int, int]]:
    """The 8-page zine fold's page order, derived from how the folded sheet hangs together.

    The sheet is held landscape, printing up, cut into 2 rows and 4 columns of panels, (row, column): row 0
    is the bottom row, column 0 the left. Folding the long way, top row behind, puts each top panel back
    to back with the bottom panel below it; the slit along that fold, through the middle two columns,
    frees those panels from each other. Pushing the ends together makes 4 leaves around a spine:
    - each end column is a leaf: its bottom panel and, back to back, its top panel (joined by the long fold);
    - the middle columns make two leaves: the bottom row's panels 1 and 2 back to back (joined by the
      crease between them), and the same for the top row;
    - facing pages across the spine are joined by the creases at columns 1 and 3, in the same row.
    Starting from the cover, pages alternate: the back of the leaf, then the facing page across the
    spine. The cover is the bottom row's right end, so the order runs B3, T3, T2, T1, T0, B0, B1, B2: the
    top row upside down (pages 5 4 3 2, left to right), the bottom row upright (6 7 back cover)."""
    leaf, spine = {}, {}
    for col in (0, 3):
        leaf[(0, col)], leaf[(1, col)] = (1, col), (0, col)
    for row in (0, 1):
        leaf[(row, 1)], leaf[(row, 2)] = (row, 2), (row, 1)
        for a, b in ((0, 1), (2, 3)):
            spine[(row, a)], spine[(row, b)] = (row, b), (row, a)
    order = [(0, 3)]
    while len(order) < 8:
        order.append(leaf[order[-1]] if len(order) % 2 == 1 else spine[order[-1]])
    return order


def zine_spine_side(panel: tuple[int, int]) -> str:
    """Which side of a page, as it's read, the spine is on. The spine is the crease at column 1 (for
    columns 0-1) or 3 (columns 2-3); the top row prints upside down, so its sides swap."""
    row, col = panel
    on_left_of_sheet = (1 if col <= 1 else 3) == col
    return ("left" if on_left_of_sheet else "right") if row == 0 else ("right" if on_left_of_sheet else "left")


# --- Fold-over cards, blank cards, ABCD cards ---------------------------------------------------

def strip_rows(grade: int) -> int:
    """Strips (cards) per column: 4 tall ones for young hands and big type, 5 from grade 6."""
    return 4 if grade <= 5 else 5


def _icon_cut(c, x, y):
    cut_line(c, x, y + 4, x + 16, y + 4)
    scissors(c, x + 2, y + 4, 9)


def _icon_fold(c, x, y):
    fold_line(c, x, y + 4, x + 16, y + 4, gray=INK)


def _icon_turn(c, x, y):
    turn_arrow(c, x + 8, y + 3, 18, 12)


def card_header(pen: Pen, name: str, title: str, tips) -> float:
    """A card page's heading and one line of how-to, each tip with a little icon. Returns the y below."""
    c = pen.c
    top = PAGE_H - MARGIN
    c.setFillGray(INK)
    c.setFont(pen.f.bold, 15)
    c.drawString(MARGIN, top - 15, pen.f.text(name))
    c.setFillGray(LABEL)
    c.setFont(pen.f.regular, 10)
    c.drawRightString(PAGE_W - MARGIN, top - 15, pen.f.text(title))
    y = top - 36
    size = 10.0
    while size > 8 and sum(pen.width(t, pen.f.regular, size) + 32 for _, t in tips) > PAGE_W - 2 * MARGIN:
        size -= 0.25
    x = MARGIN
    for icon, text in tips:
        icon(c, x, y)
        x += 22
        c.setFillGray(INK)
        c.setFont(pen.f.regular, size)
        c.drawString(x, y + 1, pen.f.text(text))
        x += pen.width(text, pen.f.regular, size) + 12
    return y - 10


def strip_grid(c, x0: float, top: float, cols: int, rows: int, w: float, h: float) -> None:
    """Cut lines around and between the strips (shared, so each cut does two edges), and a fold line
    across the middle of each strip."""
    for j in range(rows):
        y = top - j * h - h / 2
        fold_line(c, x0, y, x0 + cols * w, y)
    for i in range(cols + 1):
        cut_line(c, x0 + i * w, top, x0 + i * w, top - rows * h)
    for j in range(rows + 1):
        cut_line(c, x0, top - j * h, x0 + cols * w, top - j * h)
    scissors(c, x0 + 22, top, 12)


def card_half(pen: Pen, x0: float, y0: float, w: float, h: float, text: str, label: str, level, font: str,
              where: str, start: float | None = None) -> None:
    """One face of a fold-over card, with the fold along its bottom edge (y0)."""
    c, pad = pen.c, 8.0
    c.setFillGray(LABEL)
    c.setFont(pen.f.regular, 7)
    c.drawString(x0 + pad, y0 + h - pad - 6, pen.f.text(label))
    if level:
        dots(c, x0 + w - pad - 2.5, y0 + h - pad - 3.5, level, align="right")
    pen.box(text, x0 + pad + 6, y0 + pad, x0 + w - pad - 6, y0 + h - pad - 11, font, start, where)


def upside_down(c, x0: float, y_fold: float, w: float):
    """A transform in which (0, 0)-(w, h) is the strip's lower half, turned 180 degrees: its bottom edge
    is the fold. Use inside saveState/restoreState."""
    c.translate(x0 + w, y_fold)
    c.rotate(180)


def piece_cards(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    rows = strip_rows(P["grade"])
    per = rows * 2
    pages = [P["cards"][i:i + per] for i in range(0, len(P["cards"]), per)]

    def page(chunk, k):
        def draw():
            c = pen.c
            top = card_header(pen, f"Fold-over cards ({k} of {len(pages)})", P["title"],
                              [(_icon_cut, "Cut on the solid lines."),
                               (_icon_fold, "Fold on the dashed line, printing out."),
                               (_icon_turn, "Turn it over side to side for the answer.")])
            w, h = (PAGE_W - 2 * MARGIN) / 2, (top - MARGIN - 6) / rows  # clear of the page label below
            for i, card in enumerate(chunk):
                x0, y_top = MARGIN + (i % 2) * w, top - (i // 2) * h
                y_fold = y_top - h / 2
                term = card["kind"] == "term"
                card_half(pen, x0, y_fold, w, h / 2, card["q"], f"{P['short']}  {card['n']}", card["level"],
                          pen.f.bold if term else pen.f.regular,
                          f"card {card['n']}'s " + ("term" if term else "question"),
                          pen.sz["card"] + (4 if term else 0))
                c.saveState()
                upside_down(c, x0, y_fold, w)
                card_half(pen, 0, 0, w, h / 2, card["a"], f"Answer  {P['short']}  {card['n']}", card["level"],
                          pen.f.regular, f"card {card['n']}'s " + ("meaning" if term else "answer"))
                c.restoreState()
            for i in range(len(chunk), per):  # the rest of the last page: blank cards to write
                x0, y_top = MARGIN + (i % 2) * w, top - (i // 2) * h
                blank_half(pen, x0, y_top - h / 2, w, h / 2, "Question")
                c.saveState()
                upside_down(c, x0, y_top - h / 2, w)
                blank_half(pen, 0, 0, w, h / 2, "Answer")
                c.restoreState()
            strip_grid(c, MARGIN, top, 2, rows, w, h)
        return draw
    return [page(chunk, k) for k, chunk in enumerate(pages, start=1)]


def writing_lines(c, x0: float, x1: float, y0: float, y1: float, primary: bool, spacing: float | None = None) -> None:
    """Ruled lines to write on, centered in y0..y1: primary ruling (dashed midline) for grades 2-3."""
    spacing = spacing or (28.0 if primary else 20.0)
    n = max(1, int((y1 - y0 - 8) // spacing))
    first = y0 + (y1 - y0 - n * spacing) / 2 + 4
    for k in range(n):
        base = first + k * spacing
        c.setStrokeGray(LINES)
        c.setLineWidth(0.7)
        c.line(x0, base, x1, base)
        if primary:
            c.line(x0, base + spacing * 0.68, x1, base + spacing * 0.68)
            c.setDash(2, 2.5)
            c.line(x0, base + spacing * 0.34, x1, base + spacing * 0.34)
            c.setDash()


def blank_half(pen: Pen, x0: float, y0: float, w: float, h: float, label: str) -> None:
    c, pad = pen.c, 8.0
    c.setFillGray(INK)
    c.setFont(pen.f.bold, 9)
    c.drawString(x0 + pad, y0 + h - pad - 7, pen.f.text(label))
    c.setFillGray(LABEL)
    c.setFont(pen.f.regular, 7)
    c.drawRightString(x0 + w - pad - 26, y0 + h - pad - 6, "hard?")
    dots(c, x0 + w - pad - 2.5, y0 + h - pad - 3.5, 3, filled=False, align="right")
    writing_lines(c, x0 + pad + 2, x0 + w - pad - 2, y0 + 2, y0 + h - pad - 14, False,
                  22.0 if pen.grade <= 3 else 18.0)  # plain lines: primary ruling leaves room for only one


GOOD_CARD = ["I can answer my own question.", "My partner can check my answer.", "One idea on each card.",
             "Turn the page around to write the answer.", "A hard card? Fill in all 3 dots."]


def piece_blank_cards(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    rows = strip_rows(P["grade"]) - 1  # the checklist takes a row

    def draw_page(k):
        def draw():
            c = pen.c
            top = card_header(pen, "Make your own cards" + (f" ({k} of {p['pages']})" if p["pages"] > 1 else ""),
                              P["title"], [(_icon_cut, "Cut on the solid lines."),
                                           (_icon_fold, "Fold on the dashed line, printing out.")])
            # the checklist, on its own panel
            size = 11.0 if P["grade"] <= 5 else 10.5
            panel_h = 18 + 3 * size * 1.55 + 10
            y1 = top - 2
            c.setStrokeGray(0.6)
            c.setLineWidth(0.8)
            c.roundRect(MARGIN, y1 - panel_h, PAGE_W - 2 * MARGIN, panel_h, 6, stroke=1, fill=0)
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 12)
            c.drawString(MARGIN + 12, y1 - 17, "Make a good card")
            col_w = (PAGE_W - 2 * MARGIN - 24) / 2
            for i, item in enumerate(GOOD_CARD):
                x = MARGIN + 12 + (i // 3) * col_w
                y = y1 - 22 - (i % 3 + 1) * size * 1.55
                checkbox(c, x, y - 1, 9)
                c.setFillGray(INK)
                c.setFont(pen.f.regular, size)
                c.drawString(x + 15, y, pen.f.text(item))
            top = y1 - panel_h - 12
            w, h = (PAGE_W - 2 * MARGIN) / 2, min((top - MARGIN) / rows, 172.0)
            for i in range(rows * 2):
                x0, y_top = MARGIN + (i % 2) * w, top - (i // 2) * h
                y_fold = y_top - h / 2
                blank_half(pen, x0, y_fold, w, h / 2, "Question")
                c.saveState()
                upside_down(c, x0, y_fold, w)
                blank_half(pen, 0, 0, w, h / 2, "Answer")
                c.restoreState()
            strip_grid(c, MARGIN, top, 2, rows, w, h)
        return draw
    return [draw_page(k) for k in range(1, p["pages"] + 1)]


def piece_abcd(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    letters = p["letters"]

    def draw():
        c = pen.c
        top = card_header(pen, "Answer cards", P["title"],
                          [(_icon_cut, "Cut on the solid lines."), (_icon_fold, "Fold on the dashed line."),
                           (lambda c, x, y: None, "Hold up your answer: the letter faces the teacher.")])
        cols = 2
        rows = (len(letters) + 1) // 2
        w, h = (PAGE_W - 2 * MARGIN) / cols, (top - MARGIN) / 2
        for i, letter in enumerate(letters):
            x0, y_top = MARGIN + (i % 2) * w, top - (i // 2) * h
            y_fold = y_top - h / 2
            for flip in (False, True):
                c.saveState()
                if flip:
                    upside_down(c, x0, y_fold, w)
                    bx, by = 0, 0
                else:
                    bx, by = x0, y_fold
                pen.box(letter, bx + 16, by + 12, bx + w - 16, by + h / 2 - 12, pen.f.bold, 150,
                        f"answer card \"{letter}\"", minimum=40, leading=1.0)
                c.restoreState()
        for r in range(rows):  # a row at a time, so an odd count leaves no empty card to cut out
            strip_grid(c, MARGIN, top - r * h, min(cols, len(letters) - r * cols), 1, w, h)
    return [draw]


# --- Board games ----------------------------------------------------------------------------------

def snake_square(n: int) -> tuple[int, int]:
    """(column, row) of square n (1-64) on the Snake Race path: along the bottom row left to right, up one,
    back right to left, and so on (row 0 is nearest the players, column 0 on their left)."""
    row, k = divmod(n - 1, 8)
    return (k if row % 2 == 0 else 7 - k), row


def snake_corners() -> list[int]:
    """The corner squares, where the snake turns: each row's ends, but not the start or the finish."""
    return [n for n in range(2, 64) if n % 8 in (0, 1)]


def mini_board(c, x: float, y: float, sq: float, dark: float = 0.82) -> None:
    """An 8x8 board with its bottom-left corner at (x, y). Dark squares are where checkers go: the bottom
    left square is dark, as on a real board."""
    for col in range(8):
        for row in range(8):
            if (col + row) % 2 == 0:
                c.setFillGray(dark)
                c.rect(x + col * sq, y + row * sq, sq, sq, stroke=0, fill=1)
    c.setStrokeGray(INK)
    c.setLineWidth(0.9)
    c.rect(x, y, 8 * sq, 8 * sq, stroke=1, fill=0)


def _centre(x, y, sq, col, row):
    return x + (col + 0.5) * sq, y + (row + 0.5) * sq


def checker(c, cx: float, cy: float, r: float, black: bool) -> None:
    c.setStrokeGray(INK)
    c.setLineWidth(1)
    c.setFillGray(0.15 if black else 1)
    c.circle(cx, cy, r, stroke=1, fill=1)
    c.setStrokeGray(0.6 if black else 0.55)
    c.setLineWidth(0.6)
    c.circle(cx, cy, r * 0.62, stroke=1, fill=0)


def card_icon(pen: Pen, cx: float, cy: float, text: str = "?", w: float = 18, h: float = 13) -> None:
    c = pen.c
    c.setFillGray(1)
    c.setStrokeGray(INK)
    c.setLineWidth(0.8)
    c.roundRect(cx - w / 2, cy - h / 2, w, h, 2, stroke=1, fill=1)
    c.setFillGray(INK)
    c.setFont(pen.f.bold, 9)
    c.drawCentredString(cx, cy - 3.2, text)


def snake_path(c, x: float, y: float, sq: float, width: float, gray: float, head: float) -> None:
    """The Snake Race path through the squares' centres, with an arrow in each row and at each turn."""
    pts = [_centre(x, y, sq, *snake_square(n)) for n in range(1, 65)]
    poly(c, pts, close=False, width=width, gray=gray)
    for row in range(8):  # which way each row runs
        a, b = _centre(x, y, sq, 3, row), _centre(x, y, sq, 4, row)
        if row % 2:
            a, b = b, a
        arrow(c, [a, ((a[0] + b[0]) / 2, a[1])], head=head, width=width, gray=gray)
    for n in range(8, 64, 8):  # up to the next row
        a, b = _centre(x, y, sq, *snake_square(n)), _centre(x, y, sq, *snake_square(n + 1))
        arrow(c, [a, (a[0], (a[1] + b[1]) / 2)], head=head, width=width, gray=gray)


def diagram_snake(pen: Pen, x: float, y: float, size: float) -> None:
    c, sq = pen.c, size / 8
    mini_board(c, x, y, sq)
    snake_path(c, x, y, sq, 1.1, 0.35, 6)
    for n in snake_corners():
        star(c, *_centre(x, y, sq, *snake_square(n)), sq * 0.26)
    c.setFillGray(INK)
    c.setFont(pen.f.bold, 7.5)
    for n in (1, 64):
        cx, cy = _centre(x, y, sq, *snake_square(n))
        c.setFillGray(1)
        c.circle(cx, cy, sq * 0.32, stroke=1, fill=1)
        c.setFillGray(INK)
        c.drawCentredString(cx, cy - 2.6, str(n))
    c.setFont(pen.f.regular, 8.5)
    c.drawString(x, y - 11, "Start: square 1")
    c.drawRightString(x + size, y + size + 4, "Finish: square 64")


def diagram_checkers(pen: Pen, x: float, y: float, size: float) -> None:
    c, sq = pen.c, size / 8
    mini_board(c, x, y, sq)
    r = sq * 0.36
    for col, row, black in ((0, 0, False), (2, 0, False), (4, 0, False), (1, 1, False), (5, 1, False),
                            (2, 2, False), (6, 2, False), (3, 3, True), (5, 5, True), (1, 7, True), (3, 7, True),
                            (7, 7, True), (6, 6, True), (0, 6, True), (4, 6, True)):
        checker(c, *_centre(x, y, sq, col, row), r, black)
    a, b = _centre(x, y, sq, 2, 2), _centre(x, y, sq, 4, 4)
    arrow(c, [(a[0] + r * 0.7, a[1] + r * 0.7), ((a[0] + b[0]) / 2 - 6, (a[1] + b[1]) / 2 + 9),
              (b[0] - r * 0.4, b[1] - r * 0.1)], head=6, width=1.6)
    card_icon(pen, x + 1.1 * sq, y + 4.1 * sq)
    c.setFont(pen.f.regular, 8.5)
    c.setFillGray(INK)
    c.drawString(x, y - 11, "Answer a card first, then jump.")


def diagram_four(pen: Pen, x: float, y: float, size: float) -> None:
    c, sq = pen.c, size / 8
    mini_board(c, x, y, sq)
    r = sq * 0.36
    stacks = {1: "wb", 2: "bw", 3: "wbw", 4: "bbbw", 5: "b", 6: "bw"}
    for col, s in stacks.items():
        for row, who in enumerate(s):
            checker(c, *_centre(x, y, sq, col, row), r, who == "b")
    win = [(1, 0), (2, 1), (3, 2), (4, 3)]
    poly(c, [_centre(x, y, sq, *win[0]), _centre(x, y, sq, *win[-1])], close=False, width=2.2)
    cx, _ = _centre(x, y, sq, 5, 1)
    arrow(c, [(cx, y + size + 10), (cx, y + 1.9 * sq)], head=6, width=1.4)
    c.setStrokeGray(INK)
    c.setLineWidth(3)
    c.line(x, y, x + size, y)
    c.setFillGray(INK)
    c.setFont(pen.f.regular, 8.5)
    c.drawString(x, y - 11, "This side is the bottom. Checkers fall down.")


def diagram_chess(pen: Pen, x: float, y: float, size: float) -> None:
    c, sq = pen.c, size / 8
    mini_board(c, x, y, sq)
    back = "RNBQKBNR"
    for col in range(8):
        for row, letter, black in ((0, back[col], False), (1, "P", False), (6, "P", True), (7, back[col], True)):
            cx, cy = _centre(x, y, sq, col, row)
            c.setStrokeGray(INK)
            c.setLineWidth(0.8)
            c.setFillGray(0.15 if black else 1)
            c.circle(cx, cy, sq * 0.38, stroke=1, fill=1)
            c.setFillGray(1 if black else INK)
            c.setFont(pen.f.bold, sq * 0.45)
            c.drawCentredString(cx, cy - sq * 0.16, letter)
    c.setFillGray(INK)
    c.setFont(pen.f.regular, 8)
    c.drawString(x, y - 11, "P pawn, N knight, B bishop, R rook, Q queen, K king")


EXPLAIN = 'On a 3-dot card, also say why: "I know because..." No reason, no {move}.'
CHECK = "The reader looks at the back of the card: the answer is there. Not sure? Ask your teacher."
WRONG = "The reader tells you the answer. Put the card at the bottom of the pile, so it comes back."

GAME_RULES = {
    "snake_race": {
        "meta": "2 to 4 players  |  30-40 minutes (set a timer: farthest along wins)", "move": "move",
        "need": "The printed board (or a checker or chess board), 1 die, the cards in two piles (3-dot cards, and "
                "the rest), and a marker for each player: a coin, a checker, or a tent pawn.",
        "rules": ["Follow the arrows from Start (1) to Finish (64). On a plain board, go along the bottom row, "
                  "up one, and back.",
                  "Put your marker beside square 1.",
                  "Roll the die. The player on your left reads you a card. They keep the back hidden.",
                  "Right? Move that many squares. Wrong? Stay.",
                  "Land on a star? Answer a card from the 3-dot pile. Right? Move 3 more.",
                  "First to Finish wins. You don't need an exact roll."],
        "draw": diagram_snake},
    "question_checkers": {
        "meta": "2 players  |  about 25 minutes", "move": "jump",
        "need": "A checker board, 12 checkers for each player, and the fold-over cards in a pile.",
        "rules": ["Set up and play checkers as usual, on the dark squares.",
                  "Before you jump, the other player reads you a card.",
                  "Right answer: make the jump. Wrong answer: no jump, and your turn is over.",
                  "Jumping two pieces in one turn? Answer a card for each jump.",
                  "Reach the far side? Answer a 3-dot card to be crowned king. Wrong: your piece waits there, "
                  "and you can try again on a later turn.",
                  "Jumps are never forced in this game. Take all the other player's pieces, or leave them no "
                  "move, to win."],
        "draw": diagram_checkers},
    "four_in_a_row": {
        "meta": "2 players  |  about 15 minutes", "move": "checker",
        "need": "A checker board, 16 checkers for each player, and the fold-over cards in a pile.",
        "rules": ["Choose one side of the board to be the bottom. Start with an empty board.",
                  "On your turn, the other player reads you a card.",
                  "Right answer: put one of your checkers in any column, on the lowest empty square, as if it "
                  "fell down.",
                  "Wrong answer: no checker this turn.",
                  "Four of yours in a row wins: across, up and down, or slanting.",
                  "Board full and no winner? It's a tie. Play again!"],
        "draw": diagram_four},
    "chess_quiz": {
        "meta": "2 players  |  about 30 minutes", "move": "capture",
        "need": "A chess set and board, and the fold-over cards sorted into three piles by their dots.",
        "rules": ["Set up and play chess as usual.",
                  "Before you capture a piece, the other player reads you a card. Its dots match the piece you "
                  "capture (see the table).",
                  "Right answer: make the capture. Wrong answer: put your piece back and make a different move, "
                  "with no capture.",
                  "Getting out of check never needs a card. Checkmate wins."],
        "draw": diagram_chess, "table": [("Pawn", 1), ("Knight or bishop", 2), ("Rook or queen", 3)]},
}


def piece_game(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    g = GAME_RULES[p["type"]]

    def draw():
        c = pen.c
        y = pen.header(P["title"], p["name"])
        body = pen.sz["body"]
        c.setFillGray(LABEL)
        c.setFont(pen.f.regular, 11)
        c.drawString(MARGIN, y - 11, g["meta"])
        y -= 24
        c.setFillGray(INK)
        c.setFont(pen.f.bold, body)
        c.drawString(MARGIN, y - body, "You need")
        y = pen.para(g["need"], MARGIN + pen.width("You need", pen.f.bold, body) + 8, y, PAGE_W - 2 * MARGIN
                     - pen.width("You need", pen.f.bold, body) - 8, body) - 16
        # rules on the left, the picture on the right
        right_w = 220.0
        left_w = PAGE_W - 2 * MARGIN - right_w - 24
        size = body + 1
        while size > 9.5 and sum(pen.para_height(r, left_w - 24, size) + 8 for r in g["rules"]) > 360:
            size -= 0.25
        top = y
        for k, rule in enumerate(g["rules"], start=1):
            step_number(pen, MARGIN + 9, y - size * 0.55, k, 9)
            y = pen.para(rule, MARGIN + 26, y, left_w - 26, size) - 8
        bx = PAGE_W - MARGIN - right_w
        board = 216.0
        g["draw"](pen, bx + (right_w - board) / 2, top - board - 18, board)
        low = top - board - 32
        if g.get("table"):
            ty = low - 6
            c.setFont(pen.f.bold, 10.5)
            c.drawString(bx + 10, ty - 10, "You capture")
            c.drawRightString(bx + right_w - 10, ty - 10, "Card")
            for name, level in g["table"]:
                ty -= 20
                c.setStrokeGray(0.75)
                c.line(bx + 10, ty + 6, bx + right_w - 10, ty + 6)
                c.setFillGray(INK)
                c.setFont(pen.f.regular, 11)
                c.drawString(bx + 10, ty - 8, name)
                dots(c, bx + right_w - 12, ty - 4.5, level, r=3, gap=8, align="right")
            low = ty - 18
        y = min(y, low) - 10
        # the three rules every game shares
        boxes = [("Check it", CHECK), ("Wrong answer?", WRONG), ("Explain it", EXPLAIN.format(move=g["move"]))]
        gap = 12.0
        bw = (PAGE_W - 2 * MARGIN - 2 * gap) / 3
        size = max(10.0, body - 1)
        bh = max(pen.para_height(t, bw - 20, size) for _, t in boxes) + 38
        for i, (head, text) in enumerate(boxes):
            x0 = MARGIN + i * (bw + gap)
            c.setStrokeGray(0.6)
            c.setLineWidth(0.8)
            c.roundRect(x0, y - bh, bw, bh, 6, stroke=1, fill=0)
            c.setFillGray(INK)
            c.setFont(pen.f.bold, size + 1)
            c.drawString(x0 + 10, y - 18, head)
            if head == "Explain it":
                dots(c, x0 + bw - 12, y - 13.5, 3, align="right")
            pen.para(text, x0 + 10, y - 26, bw - 20, size)
        if y - bh < MARGIN:
            pen.warnings.append(f"{p['name']}'s rules run off the page")
    return [draw]


def piece_board(m: "Maker", p: dict):
    pen, P = m.pen, m.P

    def draw():
        c = pen.c
        y = pen.header(P["title"], "Game board",
                       "Snake Race: follow the arrows from Start to Finish. A star means a 3-dot card. (For "
                       "checkers or chess, ignore the arrows and numbers.)")
        sq = (PAGE_W - 2 * MARGIN) / 8
        x0, y0 = MARGIN, y - 8 * sq - 6
        mini_board(c, x0, y0, sq, dark=0.85)
        snake_path(c, x0, y0, sq, 1.8, 0.5, 10)
        c.setFont(pen.f.bold, 9.5)
        for n in range(1, 65):  # dark enough to survive a copier
            col, row = snake_square(n)
            c.setFillGray(0.2)
            c.drawString(x0 + col * sq + 4, y0 + (row + 1) * sq - 12, str(n))
        for n, word in ((1, "Start"), (64, "Finish")):
            col, row = snake_square(n)
            c.setFillGray(1)
            c.rect(x0 + col * sq + 4, y0 + row * sq + 5, sq - 8, 14, stroke=0, fill=1)
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 11)
            c.drawCentredString(x0 + (col + 0.5) * sq, y0 + row * sq + 8, word)
            c.setFont(pen.f.bold, 9.5)
        for n in snake_corners():
            col, row = snake_square(n)
            star(c, x0 + (col + 1) * sq - 9, y0 + (row + 1) * sq - 8, 4.5, fill=0.5)
        c.setStrokeGray(INK)
        c.setLineWidth(1.5)
        c.rect(x0, y0, 8 * sq, 8 * sq, stroke=1, fill=0)
    return [draw]


# --- Paper die, spinner, tent pawns --------------------------------------------------------------

# The die's net, a cross: (column, row) with row 0 at the top. A, B, C, D run down the middle and wrap
# around the cube; L and R are B's sides. Opposite faces: A-C, B-D, L-R.
DIE_NET = {"A": (1, 0), "L": (0, 1), "B": (1, 1), "R": (2, 1), "C": (1, 2), "D": (1, 3)}
# Every cube edge that isn't a fold in the net joins two free edges; one of each pair gets a glue tab:
# A top-D bottom, A left-L top, A right-R top, L bottom-C left, R bottom-C right, L left-D left, R right-D right.
DIE_TABS = {("L", "top"), ("R", "top"), ("L", "bottom"), ("R", "bottom"), ("D", "left"), ("D", "right"),
            ("D", "bottom")}
DIE_ORDER = ["B", "A", "L", "R", "C", "D"]  # faces[0..5]; with pips, opposite faces add up to 7
PIPS = {1: [(0.5, 0.5)], 2: [(0.27, 0.73), (0.73, 0.27)], 3: [(0.27, 0.73), (0.5, 0.5), (0.73, 0.27)],
        4: [(0.27, 0.27), (0.27, 0.73), (0.73, 0.27), (0.73, 0.73)],
        5: [(0.27, 0.27), (0.27, 0.73), (0.5, 0.5), (0.73, 0.27), (0.73, 0.73)],
        6: [(0.27, 0.25), (0.27, 0.5), (0.27, 0.75), (0.73, 0.25), (0.73, 0.5), (0.73, 0.75)]}
PIP_FACES = {"B": 1, "A": 2, "L": 3, "R": 4, "C": 5, "D": 6}


def _edges(col, row):
    """A net cell's edges as (name, (x0, y0), (x1, y1)) in cell units, y up, row 0 at the top."""
    x0, y1 = col, -row
    x1, y0 = col + 1, -row - 1
    return [("top", (x0, y1), (x1, y1)), ("bottom", (x0, y0), (x1, y0)), ("left", (x0, y0), (x0, y1)),
            ("right", (x1, y0), (x1, y1))]


def net_lines(face_size: float, tab: float, ox: float, oy: float):
    """The die net's fold lines, cut lines, and tab outlines, in page points from the net's top-left."""
    cells = set(DIE_NET.values())
    folds, cuts, tabs = [], [], []
    to_page = lambda p: (ox + p[0] * face_size, oy + p[1] * face_size)  # noqa: E731
    for face, (col, row) in DIE_NET.items():
        for name, a, b in _edges(col, row):
            dx, dy = {"top": (0, -1), "bottom": (0, 1), "left": (1, 0), "right": (-1, 0)}[name]
            neighbour = (col - dx, row + dy) if name in ("left", "right") else (col, row + dy)
            pa, pb = to_page(a), to_page(b)
            if neighbour in cells:
                if name in ("bottom", "right"):  # each shared edge once (a dashed line drawn twice looks solid)
                    folds.append((pa, pb))
            elif (face, name) in DIE_TABS:
                folds.append((pa, pb))
                out = {"top": (0, 1), "bottom": (0, -1), "left": (-1, 0), "right": (1, 0)}[name]
                ux, uy = (pb[0] - pa[0]) / face_size, (pb[1] - pa[1]) / face_size
                tabs.append([pa, (pa[0] + tab * (ux + out[0]), pa[1] + tab * (uy + out[1])),
                             (pb[0] + tab * (out[0] - ux), pb[1] + tab * (out[1] - uy)), pb])
            else:
                cuts.append((pa, pb))
    return folds, cuts, tabs


def _mini_net(c, x, y, w, h, dashed: bool):
    s = min(w / 3, h / 4)
    ox, oy = x + (w - 3 * s) / 2, y + h - (h - 4 * s) / 2
    folds, cuts, tabs = net_lines(s, s * 0.22, ox, oy)
    for a, b in cuts:
        cut_line(c, *a, *b)
    for t in tabs:
        poly(c, t, close=False, width=0.7)
    for a, b in folds:
        if dashed:
            c.setDash(2, 1.5)
            c.setStrokeGray(INK)
            c.setLineWidth(0.6)
            c.line(*a, *b)
            c.setDash()
    return ox, oy, s


def _iso_cube(c, cx, cy, s):
    a = math.radians(30)
    dx, dy = s * math.cos(a), s * math.sin(a)
    top = [(cx, cy), (cx + dx, cy + dy), (cx, cy + 2 * dy), (cx - dx, cy + dy)]
    left = [(cx - dx, cy + dy), (cx, cy), (cx, cy - s), (cx - dx, cy + dy - s)]
    right = [(cx, cy), (cx + dx, cy + dy), (cx + dx, cy + dy - s), (cx, cy - s)]
    poly(c, left, fill=1)
    poly(c, right, fill=0.85)
    poly(c, top, fill=1)
    tab = [(cx + dx, cy + dy), (cx + dx + 0.18 * s, cy + dy + 0.45 * s), (cx + 0.35 * s, cy + 2 * dy + 0.35 * s),
           (cx, cy + 2 * dy)]
    poly(c, tab, fill=0.93, close=False, width=0.7)


def piece_die(m: "Maker", p: dict):
    pen, P = m.pen, m.P

    def draw():
        c = pen.c
        y = pen.header(P["title"], "Paper die")
        s, tab = 124.0, 26.0
        ox, oy = MARGIN + 6, y - 6
        folds, cuts, tabs = net_lines(s, tab, ox, oy)
        for t in tabs:
            poly(c, t, fill=0.93, close=False, width=0.9)
            mx, my = sum(q[0] for q in t) / 4, sum(q[1] for q in t) / 4
            c.setFillGray(0.5)
            c.setFont(pen.f.regular, 7)
            c.drawCentredString(mx, my - 2.5, "glue")
        for a, b in cuts:
            cut_line(c, *a, *b)
        for a, b in folds:
            fold_line(c, *a, *b)
        scissors(c, ox + s + 30, oy, 12)
        for k, face in enumerate(DIE_ORDER):
            col, row = DIE_NET[face]
            fx, fy = ox + col * s, oy - (row + 1) * s
            if p["faces"] == "pips":
                c.setFillGray(INK)
                for px, py in PIPS[PIP_FACES[face]]:
                    c.circle(fx + px * s, fy + py * s, s * 0.075, stroke=0, fill=1)
            else:
                pen.box(p["faces"][k], fx + 12, fy + 12, fx + s - 12, fy + s - 12, pen.f.bold, pen.sz["card"] + 4,
                        f"die face \"{p['faces'][k]}\"")
        # directions, down the right side
        x0 = ox + 3 * s + 24
        x1 = PAGE_W - MARGIN
        w = x1 - x0
        steps = [(lambda x, y_, w_, h_: (_mini_net(c, x, y_, w_, h_, False),
                                         scissors(c, x + w_ * 0.2, y_ + h_ * 0.9, 11)),
                  "Cut on the solid lines, around the tabs."),
                 (lambda x, y_, w_, h_: _mini_net(c, x, y_, w_, h_, True), "Fold on every dashed line."),
                 (lambda x, y_, w_, h_: _iso_cube(c, x + w_ / 2, y_ + h_ * 0.4, h_ * 0.42),
                  "Fold it into a cube. Glue or tape each tab inside.")]
        ty = y - 4
        for k, (fn, text) in enumerate(steps, start=1):
            step_number(pen, x0 + 8, ty - 8, k)
            fn(x0 + 20, ty - 110, w - 20, 100)
            ty = pen.para(text, x0, ty - 118, w, 10.5) - 22
    return [draw]


def spinner_up(pen: Pen, text: str, font: str, poly_page, mid_angle: float, start: float):
    """The reading direction that gives a sector's label the biggest type: level, or across the sector
    with its top toward the rim (toward the middle on the lower half, so it isn't upside down)."""
    radial = (math.cos(math.radians(mid_angle)), math.sin(math.radians(mid_angle)))
    across = radial if radial[1] >= -0.01 else (-radial[0], -radial[1])
    best = None
    for up in ((0.0, 1.0), across):
        ox = sum(q[0] for q in poly_page) / len(poly_page)
        oy = sum(q[1] for q in poly_page) / len(poly_page)
        rx, ry = up[1], -up[0]
        local = [((x - ox) * rx + (y - oy) * ry, (x - ox) * up[0] + (y - oy) * up[1]) for x, y in poly_page]
        size, placed = pen.fit_poly(text, font, local, start, "", pad=6)
        if placed and (best is None or size > best[0] + 0.25):
            best = (size, up)
    return best[1] if best else (0.0, 1.0)


def paper_clip(c, x, y, length, angle=0.0):
    c.saveState()
    c.translate(x, y)
    c.rotate(angle)
    c.setStrokeGray(INK)
    c.setLineWidth(1.1)
    c.roundRect(-0.12 * length, -0.14 * length, length, 0.28 * length, 0.14 * length, stroke=1, fill=0)
    c.roundRect(-0.04 * length, -0.08 * length, 0.72 * length, 0.16 * length, 0.08 * length, stroke=1, fill=0)
    c.restoreState()


def pencil(c, tip_x, tip_y, length, angle=90.0):
    """A pencil standing on its point at (tip_x, tip_y), pointing back along `angle`."""
    c.saveState()
    c.translate(tip_x, tip_y)
    c.rotate(angle)
    w = length * 0.11
    poly(c, [(0, 0), (length * 0.18, w / 2), (length * 0.18, -w / 2)], fill=0.85)
    poly(c, [(0, 0), (length * 0.06, w * 0.17), (length * 0.06, -w * 0.17)], fill=INK)
    poly(c, [(length * 0.18, w / 2), (length * 0.9, w / 2), (length * 0.9, -w / 2), (length * 0.18, -w / 2)], fill=1)
    poly(c, [(length * 0.9, w / 2), (length, w / 2), (length, -w / 2), (length * 0.9, -w / 2)], fill=0.6)
    c.restoreState()


def piece_spinner(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    labels = p["sectors"]

    def draw():
        c = pen.c
        y = pen.header(P["title"], "Spinner")
        R = 190.0
        cx, cy = PAGE_W / 2, y - R - 12
        n = len(labels)
        step = 360.0 / n
        for i, label in enumerate(labels):
            a0, a1 = 90 - i * step, 90 - (i + 1) * step
            wedge = [(cx, cy)] + arc_points(cx, cy, R, a0, a1, 32)
            poly(c, wedge, fill=0.92 if i % 2 else 1, width=1.0)
            inner = 0.16 * R
            outline = arc_points(cx, cy, R - 4, a0, a1, 24) + [
                (cx + inner * math.cos(math.radians(a1)), cy + inner * math.sin(math.radians(a1))),
                (cx + inner * math.cos(math.radians(a0)), cy + inner * math.sin(math.radians(a0)))]
            outline = outline[::-1]  # counterclockwise, like the other polygons
            mid = (a0 + a1) / 2
            start = pen.sz["card"] + 10
            up = spinner_up(pen, label, pen.f.bold, outline, mid, start)
            pen.poly_text(label, outline, up, pen.f.bold, start, f"spinner sector \"{label}\"", pad=6)
        c.setStrokeGray(INK)
        c.setLineWidth(1.6)
        c.circle(cx, cy, R, stroke=1, fill=0)
        c.setFillGray(1)
        c.circle(cx, cy, 9, stroke=1, fill=1)
        c.setFillGray(INK)
        c.circle(cx, cy, 2.2, stroke=0, fill=1)
        top = cy - R - 22

        def clip_step(x, y_, w, h):
            ccx, ccy = x + w / 2, y_ + h / 2
            c.setStrokeGray(INK)
            c.setLineWidth(0.8)
            c.circle(ccx, ccy, h / 2, stroke=1, fill=0)
            paper_clip(c, ccx - 3, ccy, h * 0.42)
            c.circle(ccx, ccy, 1.8, stroke=0, fill=1)

        def pencil_step(x, y_, w, h):
            clip_step(x, y_, w, h)
            pencil(c, x + w / 2, y_ + h / 2, h * 0.75, 75)

        def flick_step(x, y_, w, h):
            clip_step(x, y_, w, h)
            pencil(c, x + w / 2, y_ + h / 2, h * 0.75, 75)
            arrow(c, arc_points(x + w / 2, y_ + h / 2, h * 0.36, -40, 40, 10), head=5)

        steps_row(pen, MARGIN, PAGE_W - MARGIN, top,
                  [(clip_step, "Lay a paper clip on the middle dot."),
                   (pencil_step, "Hold it there: a pencil point in the clip's loop, on the dot."),
                   (flick_step, "Flick the clip. Read where its end stops.")], 92, caption=11)
    return [draw]


PATTERNS = ["plain", "solid", "stripes", "dots", "checks", "rings"]


def pattern_fill(c, x0, y0, w, h, kind: str) -> None:
    """A light pattern, so pawns stay different on black-and-white copies."""
    c.saveState()
    p = c.beginPath()
    p.rect(x0, y0, w, h)
    c.clipPath(p, stroke=0, fill=0)
    c.setStrokeGray(0.55)
    c.setFillGray(0.62)
    c.setLineWidth(1.4)
    if kind == "solid":
        c.setFillGray(0.8)
        c.rect(x0, y0, w, h, stroke=0, fill=1)
    elif kind == "stripes":
        for k in range(-int(h), int(w) + int(h), 8):
            c.line(x0 + k, y0, x0 + k + h, y0 + h)
    elif kind == "dots":
        for i in range(int(w // 8) + 1):
            for j in range(int(h // 8) + 1):
                c.circle(x0 + 4 + i * 8 + (4 if j % 2 else 0), y0 + 4 + j * 8, 1.5, stroke=0, fill=1)
    elif kind == "checks":
        c.setFillGray(0.8)
        for i in range(int(w // 8) + 1):
            for j in range(int(h // 8) + 1):
                if (i + j) % 2 == 0:
                    c.rect(x0 + i * 8, y0 + j * 8, 8, 8, stroke=0, fill=1)
    elif kind == "rings":
        c.setLineWidth(1)
        for r in range(6, int(max(w, h)), 6):
            c.circle(x0 + w / 2, y0 + h / 2, r, stroke=1, fill=0)
    c.restoreState()


PAWN_SIDE, PAWN_DEPTH = 54.0, 42.0  # a tent about 3/4 inch across: it sits on one board square


def pawn_strip(pen: Pen, x0: float, y0: float, label: str, pattern: str) -> None:
    """One pawn: half a base, two sides, and the other half of the base. Folded printing out, the sides
    meet at the peak (the middle fold), and each label reads with its top toward the peak."""
    c, a, d = pen.c, PAWN_SIDE, PAWN_DEPTH
    for side, (sx, angle) in enumerate(((x0 + a / 2, -90), (x0 + 1.5 * a, 90))):
        pattern_fill(c, sx, y0, a, d, pattern)
        cx, cy = sx + a / 2, y0 + d / 2
        c.setFillGray(1)
        c.setStrokeGray(0.4)
        c.setLineWidth(0.7)
        c.circle(cx, cy, 17.5, stroke=1, fill=1)
        c.saveState()
        c.translate(cx, cy)
        c.rotate(angle)  # -90: top toward +x (the peak, for the left side); 90: top toward -x
        pen.box(label, -15, -12, 15, 12, pen.f.bold, 20, f"pawn \"{label}\"", minimum=8, leading=1.0)
        c.restoreState()
    for fx in (x0 + a / 2, x0 + 1.5 * a, x0 + 2.5 * a):
        fold_line(c, fx, y0, fx, y0 + d)


def piece_pawns(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    labels = p["labels"]

    def draw():
        c = pen.c
        y = pen.header(P["title"], "Tent pawns", "Every player in a group takes a different pattern, so pawns "
                       "stay easy to tell apart on a black-and-white copy.")
        L, d = 3 * PAWN_SIDE, PAWN_DEPTH
        gap = (PAGE_W - 2 * MARGIN - 3 * L) / 2
        band = len(labels) * d
        bands = 2 if 2 * band + 16 <= y - MARGIN - 130 else 1
        top = y - 4
        for b in range(bands):
            for col in range(3):
                x0 = MARGIN + col * (L + gap)
                yt = top - b * (band + 16)
                for i, label in enumerate(labels):
                    pawn_strip(pen, x0, yt - (i + 1) * d, label, PATTERNS[i % len(PATTERNS)])
                for i in range(len(labels) + 1):
                    cut_line(c, x0, yt - i * d, x0 + L, yt - i * d)
                cut_line(c, x0, yt, x0, yt - band)
                cut_line(c, x0 + L, yt, x0 + L, yt - band)
            scissors(c, MARGIN + 20, top - b * (band + 16), 11)
        low = top - bands * band - (bands - 1) * 16 - 18

        def strip_icon(x, y_, w, h, dashed):
            sw, sh = min(w, 3 * h), min(h, w / 3)
            sx, sy = x + (w - sw) / 2, y_ + (h - sh) / 2
            c.setStrokeGray(INK)
            c.setLineWidth(0.9)
            c.rect(sx, sy, sw, sh * 0.5, stroke=1, fill=0)
            if dashed:
                for f in (1 / 6, 1 / 2, 5 / 6):
                    fold_line(c, sx + f * sw, sy, sx + f * sw, sy + sh * 0.5, gray=INK)
            else:
                scissors(c, sx - 2, sy + sh * 0.5, 10)

        def tent(x, y_, w, h):
            base = min(w * 0.6, h * 0.9)
            bx, by = x + (w - base) / 2, y_ + 6
            poly(c, [(bx, by), (bx + base, by), (bx + base / 2, by + base * 0.87)], fill=0.9, width=1.1)
            c.setStrokeGray(INK)
            c.setLineWidth(2)
            c.line(bx - 4, by, bx + base + 4, by)

        steps_row(pen, MARGIN, PAGE_W - MARGIN, low,
                  [(lambda x, y_, w, h: strip_icon(x, y_, w, h, False), "Cut out one strip."),
                   (lambda x, y_, w, h: strip_icon(x, y_, w, h, True), "Fold on the 3 dashed lines, printing out."),
                   (tent, "Stand it up as a tent: the two ends meet underneath. A dab of glue holds it.")],
                  62, caption=10.5)
    return [draw]


# --- Fortune teller ---------------------------------------------------------------------------------

def _ft_icon(c, x, y, w, h, stage: int) -> None:
    """The fortune teller's folding steps, as small pictures."""
    s = min(w, h) * 0.86
    cx, cy = x + w / 2, y + h / 2
    sq = [(cx - s / 2, cy - s / 2), (cx + s / 2, cy - s / 2), (cx + s / 2, cy + s / 2), (cx - s / 2, cy + s / 2)]
    diamond = [(cx, cy - s / 2), (cx + s / 2, cy), (cx, cy + s / 2), (cx - s / 2, cy)]
    if stage == 1:
        poly(c, sq, fill=1)
        for a, b in ((sq[0], sq[2]), (sq[1], sq[3])):
            fold_line(c, *a, *b, gray=0.6)
        scissors(c, sq[3][0] + 6, sq[3][1], 10)
    elif stage == 2:
        poly(c, sq, fill=0.93)
        c.setFillGray(LABEL)
        c.setFont("Helvetica", 7)
        c.drawCentredString(cx, cy - 2.5, "blank side")
        turn_arrow(c, cx, cy + s / 2 + 2, s * 0.8, 12)
    elif stage == 3:
        poly(c, sq, fill=None, dash=True, gray=0.6)
        poly(c, diamond, fill=1)
        for corner, mid in zip(sq, ((cx - s * 0.15, cy - s * 0.15), (cx + s * 0.15, cy - s * 0.15),
                                    (cx + s * 0.15, cy + s * 0.15), (cx - s * 0.15, cy + s * 0.15))):
            arrow(c, [corner, mid], head=4, width=0.8)
    elif stage == 4:
        q = s * 0.36
        small = [(cx - q, cy - q), (cx + q, cy - q), (cx + q, cy + q), (cx - q, cy + q)]
        poly(c, [(cx, cy - q * 1.41), (cx + q * 1.41, cy), (cx, cy + q * 1.41), (cx - q * 1.41, cy)],
             fill=None, dash=True, gray=0.6)
        poly(c, small, fill=1)
        for a, b in ((small[0], small[2]), (small[1], small[3])):
            c.setStrokeGray(INK)
            c.setLineWidth(0.7)
            c.line(*a, *b)
        c.setFillGray(INK)
        c.setFont("Helvetica-Bold", 7)
        for k, (dx, dy) in enumerate(((0.35, 0.75), (0.75, 0.35), (0.75, -0.35), (0.35, -0.75)), start=1):
            c.drawCentredString(cx + dx * q, cy + dy * q - 2.5, str(k))
    elif stage == 5:
        q = s * 0.36
        poly(c, [(cx - q, cy - q), (cx + q, cy - q), (cx + q, cy + q), (cx - q, cy + q)], fill=1)
        fold_line(c, cx - q, cy, cx + q, cy, gray=INK)
        fold_line(c, cx, cy - q, cx, cy + q, gray=INK)
    else:  # the finished fortune teller, from above: four points
        q = s * 0.42
        for k in range(4):
            a = math.radians(45 + 90 * k)
            tip = (cx + q * math.cos(a), cy + q * math.sin(a))
            left = (cx + q * 0.55 * math.cos(a - 0.8), cy + q * 0.55 * math.sin(a - 0.8))
            right = (cx + q * 0.55 * math.cos(a + 0.8), cy + q * 0.55 * math.sin(a + 0.8))
            poly(c, [(cx, cy), left, tip], fill=1, width=0.8)
            poly(c, [(cx, cy), tip, right], fill=0.85, width=0.8)


def piece_fortune_teller(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    cards = [P["cards"][k - 1] for k in p["cards"]]
    plan = FortuneTeller().layout()

    def draw():
        c = pen.c
        y = pen.header(P["title"], "Fortune teller")
        S_ = 504.0  # the square: 7 inches
        cx, cy = PAGE_W / 2, y - S_ / 2 - 2
        to_page = lambda pts: [(cx + x * S_ / 2, cy + yy * S_ / 2) for x, yy in pts]  # noqa: E731
        # fold lines first, light, so the text sits on top
        h = S_ / 2
        for a, b in (((-1, -1), (1, 1)), ((-1, 1), (1, -1)), ((-1, 0), (1, 0)), ((0, -1), (0, 1)),
                     ((-1, 0), (0, 1)), ((0, 1), (1, 0)), ((1, 0), (0, -1)), ((0, -1), (-1, 0)),
                     ((-0.5, -0.5), (-0.5, 0.5)), ((0.5, -0.5), (0.5, 0.5)), ((-0.5, 0.5), (0.5, 0.5)),
                     ((-0.5, -0.5), (0.5, -0.5))):
            fold_line(c, cx + a[0] * h, cy + a[1] * h, cx + b[0] * h, cy + b[1] * h, gray=0.62)
        minimum = pen.sz["min"]
        for k in range(1, 9):
            card = cards[k - 1]
            tri, up = plan["number"][k]
            pen.poly_text(str(k), to_page(tri), up, pen.f.bold, 34, f"fortune teller number {k}", minimum=20, pad=12)
            tri, up = plan["question"][k]
            pen.poly_text(card["q"], to_page(tri), up, pen.f.regular, pen.sz["card"],
                          f"card {card['n']}'s question on the fortune teller", minimum, pad=5)
            tri, up = plan["answer"][k]
            pen.poly_text(card["a"], to_page(tri), up, pen.f.oblique, pen.sz["card"],
                          f"card {card['n']}'s answer on the fortune teller", minimum, pad=5)
        for i, label in enumerate(p["outer"], start=1):
            square, up = plan["outer"][i]
            pts = to_page(square)
            pen.poly_text(label, pts, up, pen.f.bold, 24, f"fortune teller corner \"{label}\"", minimum, pad=8)
        c.setStrokeGray(INK)
        c.setLineWidth(1.2)
        c.rect(cx - h, cy - h, S_, S_, stroke=1, fill=0)
        scissors(c, cx - h + 26, cy + h, 12)
        top = cy - h - 14
        captions = ["Cut out the square.", "Turn it over: printing down.", "Fold each corner to the middle.",
                    "Turn it over. Fold each corner in again.", "Fold in half both ways. Open.",
                    "Fingers under the 4 corner squares. Push the points up."]
        low = steps_row(pen, MARGIN, PAGE_W - MARGIN, top,
                        [(lambda x, y_, w, hh, k=k: _ft_icon(c, x, y_, w, hh, k), text)
                         for k, text in enumerate(captions, start=1)], 58, caption=9.5)
        play = ("Play: your partner picks a corner word; spell it, opening and closing once for each letter. They "
                "pick a number they can see; count it out. They pick again: lift that flap, read the question "
                "under it, and check the answer below.")
        size, lines = pen.fit(play, pen.f.regular, PAGE_W - 2 * MARGIN, low - MARGIN - 2, 10.5,
                              "the fortune teller's how-to-play line", minimum=9)
        pen.lines(lines, pen.f.regular, size, MARGIN, PAGE_W - MARGIN, MARGIN, low - 4, "left", "top")
    return [draw]


# --- Mini-book ---------------------------------------------------------------------------------------

ZINE_W, ZINE_H = PAGE_H, PAGE_W  # the sheet, held landscape


def zine_panels() -> dict:
    """Book page (1 = cover, 8 = back cover) -> (row, column) on the sheet."""
    return {k: panel for k, panel in enumerate(zine_book(), start=1)}


def _panel_box(row: int, col: int, inset_edge: float = MARGIN, inset_fold: float = 12.0):
    """A panel's content box on the landscape sheet: clear of the sheet's margins and of the folds."""
    pw, ph = ZINE_W / 4, ZINE_H / 2
    x0, y0 = col * pw, row * ph
    return (x0 + (inset_edge if col == 0 else inset_fold), y0 + (inset_edge if row == 0 else inset_fold),
            x0 + pw - (inset_edge if col == 3 else inset_fold), y0 + ph - (inset_edge if row == 1 else inset_fold))


def picture_box(c, x0, y0, x1, y1) -> None:
    c.setStrokeGray(0.6)
    c.setLineWidth(0.8)
    c.roundRect(x0, y0, x1 - x0, y1 - y0, 4, stroke=1, fill=0)


def zine_page(pen: Pen, box, k: int, book: dict, blank: bool, P: dict) -> None:
    """One page of the mini-book, drawn upright in its box (the caller turns the top row around)."""
    c = pen.c
    x0, y0, x1, y1 = box
    w = x1 - x0
    title = book.get("title") or P["title"]
    where = f"mini-book page {k}"
    if k == 1:  # the cover
        if blank:
            c.setFillGray(LABEL)
            c.setFont(pen.f.regular, 9)
            c.drawString(x0, y1 - 10, "Title")
            writing_lines(c, x0, x1, y1 - 74, y1 - 16, pen.grade <= 3)
        else:
            pen.box(title, x0, y1 - 74, x1, y1, pen.f.bold, pen.sz["head"] + 4, f"{where} (the cover title)",
                    leading=1.15)
        picture_box(c, x0 + 6, y0 + 46, x1 - 6, y1 - 86)
        c.setFillGray(INK)
        c.setFont(pen.f.regular, 11)
        c.drawString(x0, y0 + 16, "by")
        c.setStrokeGray(LINES)
        c.line(x0 + 18, y0 + 14, x1, y0 + 14)
        return
    if k == 8:  # the back cover
        text = "" if blank else (book.get("back") or "")
        if text:
            pen.box(text, x0, y0 + 40, x1, y1, pen.f.regular, pen.sz["body"] + 1, f"{where} (the back cover)",
                    valign="middle")
        else:
            c.setFillGray(LABEL)
            c.setFont(pen.f.regular, 9)
            c.drawString(x0, y1 - 10, "About the author")
            writing_lines(c, x0, x1, y0 + 40, y1 - 18, pen.grade <= 3)
        if not blank:
            c.setFillGray(LABEL)
            c.setFont(pen.f.regular, 8)
            c.drawCentredString((x0 + x1) / 2, y0 + 4, pen.f.text(title))
        return
    c.setFillGray(LABEL)
    c.setFont(pen.f.regular, 9)
    c.drawCentredString((x0 + x1) / 2, y0 + 6, str(k))
    if blank:
        picture_box(c, x0, y1 - 120, x1, y1)
        writing_lines(c, x0, x1, y0 + 20, y1 - 130, pen.grade <= 3)
        return
    page = book["pages"][k - 2]
    top = y1
    if page.get("heading"):
        size, lines = pen.fit(page["heading"], pen.f.bold, w, 50, pen.sz["body"] + 3, f"{where}'s heading")
        pen.lines(lines, pen.f.bold, size, x0, x1, top - len(lines) * size * 1.2, top, "left", "top")
        top -= len(lines) * size * 1.2 + 6
    pic = min(110.0, (top - y0) * 0.45)
    picture_box(c, x0, top - pic, x1, top)
    pen.box(page["text"], x0, y0 + 20, x1, top - pic - 8, pen.f.regular, pen.sz["card"], f"{where}'s text",
            align="left", valign="top")


def piece_minibook(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    versions = [True] if p["blank"] else ([False, True] if p["also_blank"] else [False])
    panels = zine_panels()

    def sheet(blank: bool):
        def draw():
            c = pen.c
            c.saveState()
            c.translate(PAGE_W, 0)
            c.rotate(90)  # landscape: (X, Y) on the sheet prints at (612 - Y, X)
            pw, ph = ZINE_W / 4, ZINE_H / 2
            for x in (pw, 2 * pw, 3 * pw):
                fold_line(c, x, MARGIN, x, ZINE_H - MARGIN)
            fold_line(c, MARGIN, ph, pw, ph)
            fold_line(c, 3 * pw, ph, ZINE_W - MARGIN, ph)
            cut_line(c, pw, ph, 3 * pw, ph)  # the slit
            scissors(c, pw + 14, ph, 12)
            for k, (row, col) in panels.items():
                x0, y0, x1, y1 = _panel_box(row, col)
                c.saveState()
                if row == 1:  # the top row prints upside down: its tops meet the bottom row's at the long fold
                    c.translate(x0 + x1, y0 + y1)
                    c.rotate(180)
                zine_page(pen, (x0, y0, x1, y1), k, p, blank, P)
                c.restoreState()
            c.setFillGray(LABEL)
            c.setFont(pen.f.regular, 7.5)
            c.drawString(MARGIN, ZINE_H - MARGIN + 1.5, pen.f.text(
                f"{P['title']}  |  page {pen.page}  |  " + ("Blank mini-book" if blank else "Mini-book")
                + ": print it one-sided, then fold it"))
            c.restoreState()
            return True  # its own page label: the usual footer would run into a page
        return draw

    def directions():
        c = pen.c
        y = pen.header(P["title"], "Mini-book: how to fold it")
        sw, sh = 150.0, 110.0  # a sheet, small: 11 x 8.5
        cols = 3
        cell_w = (PAGE_W - 2 * MARGIN) / cols

        def sheet_icon(x, yb, folds=(), slit=False, half=False):
            w, h = (sw / 2, sh) if half else (sw, sh)
            poly(c, [(x, yb), (x + w, yb), (x + w, yb + h), (x, yb + h)], fill=1)
            for (ax, ay), (bx, by) in folds:
                fold_line(c, x + ax * w, yb + ay * h, x + bx * w, yb + by * h, gray=INK)
            if slit:  # the folded edge is on the left: cut from it to the middle crease
                c.setStrokeGray(INK)
                c.setLineWidth(2.2)
                c.line(x, yb, x, yb + h)
                c.setFont(pen.f.regular, 9)
                c.setFillGray(LABEL)
                c.drawRightString(x - 5, yb + h - 12, "fold")
                cut_line(c, x, yb + h / 2, x + w / 2, yb + h / 2)
                scissors(c, x + w / 2 + 12, yb + h / 2, 12, 180)
            return w, h

        def strip_icon(x, yb):
            w, h = sw, sh / 2
            poly(c, [(x, yb), (x + w, yb), (x + w, yb + h), (x, yb + h)], fill=1)
            for f in (0.25, 0.5, 0.75):
                fold_line(c, x + f * w, yb, x + f * w, yb + h, gray=INK)
            c.setStrokeGray(INK)
            c.setLineWidth(1.6)
            c.line(x + 0.25 * w, yb + h, x + 0.75 * w, yb + h)
            arrow(c, [(x - 12, yb + h / 2), (x + 8, yb + h / 2)], head=5)
            arrow(c, [(x + w + 12, yb + h / 2), (x + w - 8, yb + h / 2)], head=5)

        def plus_icon(x, yb):
            cx, cy, r = x + sw / 2, yb + sh / 2, sh * 0.42
            for a in (0, 90, 180, 270):
                ax, ay = math.cos(math.radians(a)), math.sin(math.radians(a))
                px, py = -ay, ax
                poly(c, [(cx, cy), (cx + r * ax + 7 * px, cy + r * ay + 7 * py), (cx + r * ax - 7 * px,
                                                                                     cy + r * ay - 7 * py)],
                     fill=1 if a % 180 else 0.88)

        def book_icon(x, yb):
            bw, bh = sw * 0.42, sh * 0.85
            bx, by = x + (sw - bw) / 2, yb + (sh - bh) / 2
            for k in range(3, 0, -1):
                poly(c, [(bx + 2 * k, by - 2 * k), (bx + bw + 2 * k, by - 2 * k), (bx + bw + 2 * k, by + bh - 2 * k),
                         (bx + 2 * k, by + bh - 2 * k)], fill=1, width=0.6)
            poly(c, [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)], fill=1, width=1.1)
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 10)
            c.drawCentredString(bx + bw / 2, by + bh * 0.6, "Cover")

        steps = [(lambda x, yb: sheet_icon(x, yb, [((0, 0.5), (1, 0.5))]), "Fold in half the long way. Open it."),
                 (lambda x, yb: sheet_icon(x, yb, [((f, 0), (f, 1)) for f in (0.25, 0.5, 0.75)]),
                  "Fold in half the short way, then each end to the middle. Open it."),
                 (lambda x, yb: sheet_icon(x + sw / 4, yb, [((0.5, 0), (0.5, 1))], slit=True, half=True),
                  "Fold in half the short way. Cut from the fold along the middle line, to the next fold."),
                 (strip_icon, "Open it. Fold it the long way, printing out. Push the ends together."),
                 (plus_icon, "The middle opens. Keep pushing until it's a plus shape."),
                 (book_icon, "Fold the pages around into a book, the cover on the front.")]
        row_h = sh + 90
        for i, (fn, text) in enumerate(steps):
            col, row = i % cols, i // cols
            x = MARGIN + col * cell_w
            yt = y - 10 - row * row_h
            step_number(pen, x + 10, yt - 10, i + 1, 10)
            fn(x + (cell_w - sw) / 2, yt - sh - 14)
            pen.para(text, x + 8, yt - sh - 26, cell_w - 16, 11.5)
        tip = ("Page 1 is the cover and page 8 the back. The top row prints upside down on purpose: after folding, "
               "every page is the right way up.")
        pen.para(tip, MARGIN, y - 10 - 2 * row_h - 6, PAGE_W - 2 * MARGIN, 11, gray=0.25)

    return [sheet(b) for b in versions] + [directions]


# --- Bingo -------------------------------------------------------------------------------------------

def bingo_items(P: dict) -> list[dict]:
    """What goes on the boards (answers, or terms for vocabulary cards) with the clue read aloud for each.
    Two cards with the same answer make one square."""
    items, seen = [], set()
    for card in P["cards"]:
        square, clue = (card["a"], card["q"]) if card["kind"] == "question" else (card["q"], card["a"])
        if square.lower() not in seen:
            seen.add(square.lower())
            items.append({"square": square, "clue": clue, "card": card["n"]})
    return items


def bingo_boards(P: dict, p: dict) -> tuple[list[dict], list[list[int | None]], list[int]]:
    """(items, boards, calling order). A board lists item indexes row by row, None for the free middle.
    Seeded from the title and "seed", so building twice prints the same boards; no two boards match."""
    items = bingo_items(P)
    size = p["size"]
    free = size % 2 == 1
    need = size * size - (1 if free else 0)
    rng = random.Random(zlib.crc32(f"{P['title']}|{P['seed']}|bingo".encode()))
    boards, seen = [], set()
    tries = 0
    while len(boards) < p["boards"]:
        tries += 1
        if tries > 5000:
            raise PiecesError(f'bingo: can\'t make {p["boards"]} different boards from {len(items)} answers; add cards')
        cells = rng.sample(range(len(items)), need)
        if tuple(cells) in seen:
            continue
        seen.add(tuple(cells))
        if free:
            cells.insert(need // 2, None)
        boards.append(cells)
    order = list(range(len(items)))
    rng.shuffle(order)
    return items, boards, order


def piece_bingo(m: "Maker", p: dict):
    pen, P = m.pen, m.P
    items, boards, order = bingo_boards(P, p)
    size = p["size"]
    # the caller's list: on one page if a little less space between rows does it, else as many as it takes
    num_w, ans_w = 26.0, 150.0
    clue_w = PAGE_W - 2 * MARGIN - num_w - ans_w - 22 - 12
    note = ("Read each clue aloud in this order, and check it off. When someone calls bingo, check their squares "
            "against the answers you've read.")
    room = PAGE_H - 2 * MARGIN - 15 - 14 - pen.para_height(note, PAGE_W - 2 * MARGIN, 10) - 22
    for body, pad in ((10.5, 8.0), (10.0, 6.0), (9.5, 5.0), (10.5, 8.0)):
        rows = []
        for k, i in enumerate(order, start=1):
            clue = items[i]["clue"][:1].upper() + items[i]["clue"][1:]
            h = max(pen.para_height(clue, clue_w, body), pen.para_height(items[i]["square"], ans_w, body,
                                                                         pen.f.bold)) + pad
            rows.append((k, items[i], clue, h))
        if sum(r[3] for r in rows) <= room:
            break
    caller_pages, page = [], []
    for row in rows:
        if page and sum(r[3] for r in page) + row[3] > room:
            caller_pages.append(page)
            page = []
        page.append(row)
    caller_pages.append(page)

    def caller(chunk, n):
        def draw():
            c = pen.c
            y = pen.header(P["title"], "Bingo: the caller's list" + (f" ({n} of {len(caller_pages)})"
                                                                     if len(caller_pages) > 1 else ""),
                           note)
            c.setFont(pen.f.bold, 9.5)
            c.setFillGray(LABEL)
            x_clue, x_ans = MARGIN + num_w, MARGIN + num_w + clue_w + 12
            c.drawString(x_clue, y - 10, "Read this")
            c.drawString(x_ans, y - 10, "Answer")
            y -= 16
            for k, item, clue, h in chunk:
                c.setStrokeGray(0.8)
                c.setLineWidth(0.6)
                c.line(MARGIN, y, PAGE_W - MARGIN, y)
                c.setFillGray(LABEL)
                c.setFont(pen.f.regular, body)
                c.drawString(MARGIN, y - body - 3, str(k))
                pen.para(clue, x_clue, y - 4, clue_w, body)
                pen.para(item["square"], x_ans, y - 4, ans_w, body, font=pen.f.bold)
                checkbox(c, PAGE_W - MARGIN - 12, y - body - 5, 11)
                y -= h
        return draw

    def board_page(pair, first):
        def draw():
            c = pen.c
            half = (PAGE_H - 2 * MARGIN) / 2
            for j, cells in enumerate(pair):
                top = PAGE_H - MARGIN - j * half - (12 if j else 0)
                c.setFillGray(INK)
                c.setFont(pen.f.bold, 15)
                c.drawString(MARGIN, top - 15, pen.f.text(f"{P['short']} Bingo"))
                c.setFont(pen.f.regular, 10)
                c.setFillGray(LABEL)
                c.drawRightString(PAGE_W - MARGIN, top - 15, f"Board {first + j}")
                gw = PAGE_W - 2 * MARGIN
                gh = half - 60
                cw, ch = gw / size, gh / size
                gy = top - 24
                for r in range(size):
                    for col in range(size):
                        x0, y1 = MARGIN + col * cw, gy - r * ch
                        idx = cells[r * size + col]
                        if idx is None:
                            c.setFillGray(FILL)
                            c.rect(x0, y1 - ch, cw, ch, stroke=0, fill=1)
                            pen.box("FREE", x0 + 6, y1 - ch + 6, x0 + cw - 6, y1 - 6, pen.f.bold, 18, minimum=10)
                        else:
                            pen.box(items[idx]["square"], x0 + 6, y1 - ch + 5, x0 + cw - 6, y1 - 5, pen.f.regular,
                                    pen.sz["card"] - 2, f"bingo square \"{items[idx]['square']}\"")
                c.setStrokeGray(INK)
                c.setLineWidth(1)
                for k in range(size + 1):
                    c.line(MARGIN + k * cw, gy, MARGIN + k * cw, gy - gh)
                    c.line(MARGIN, gy - k * ch, MARGIN + gw, gy - k * ch)
                c.setFillGray(0.25)
                c.setFont(pen.f.regular, 10)
                c.drawString(MARGIN, gy - gh - 14, f"Cover a square when you hear its clue. "
                             f"{('Three', 'Four', 'Five')[size - 3]} in a row wins: across, down, or corner to corner.")
        return draw

    pages = [caller(chunk, n) for n, chunk in enumerate(caller_pages, start=1)]
    pages += [board_page(boards[i:i + 2], i + 1) for i in range(0, len(boards), 2)]
    return pages, len(caller_pages)


# --- The teacher's page, and building the file --------------------------------------------------------

PRINT = {  # (print on, prep): short enough for one line each on the teacher's page
    "cards": ("Cardstock if you have it", "5 min a page to cut"),
    "blank_cards": ("Plain, one per student", "None"),
    "snake_race": ("Plain, one per group", "None"), "question_checkers": ("Plain, one per group", "None"),
    "four_in_a_row": ("Plain, one per group", "None"), "chess_quiz": ("Plain, one per group", "None"),
    "board": ("Cardstock, one per group", "None"),
    "die": ("Cardstock, one per group", "Students: 10 min"),
    "spinner": ("Cardstock, one per group", "None"),
    "pawns": ("Cardstock: 6 sets a sheet", "Students: 5 min"),
    "fortune_teller": ("Plain, one per student", "10 min, after a demo"),
    "minibook": ("Plain, one per student", "10 min, after a demo"),
    "abcd": ("Cardstock, one per student", "5 min to cut and fold"),
    "bingo": ("Plain, a board each", "None"),
}
WHAT = {
    "cards": "Question on the front, answer on the back.",
    "blank_cards": "Students write their own, with a checklist.",
    "snake_race": "A race along all 64 squares, with a die.",
    "question_checkers": "Every jump needs a right answer.",
    "four_in_a_row": "A checker for each right answer.",
    "chess_quiz": "Every capture needs a right answer.",
    "board": "8x8, with the Snake Race path.",
    "die": "A cube to cut and fold.", "spinner": "Spins with a paper clip and a pencil.",
    "pawns": "Stand-up pieces in different patterns.",
    "fortune_teller": "8 questions under the flaps.",
    "minibook": "An 8-page book from one sheet.",
    "abcd": "The whole class answers at once.", "bingo": "Unique boards and a caller's list.",
}


def materials(P: dict) -> list[str]:
    kinds = {p["type"] for p in P["pieces"]}
    out = ["Scissors for each student or pair"]
    if kinds & {"die", "pawns", "fortune_teller", "minibook"}:
        out.append("Glue sticks or tape (optional: a dab helps the die and pawns hold together)")
    if "snake_race" in kinds:
        out.append("A six-sided die per group" + (" (or the paper die)" if "die" in kinds else ""))
    if kinds & {"snake_race", "question_checkers", "four_in_a_row", "chess_quiz"}:
        out.append("A checker or chess board per group" + (" (or the printed board)" if "board" in kinds else ""))
    if kinds & {"question_checkers", "four_in_a_row"}:
        out.append("Checkers: 12 each for checkers, 16 each for Four in a Row (coins or paper squares work)")
    if "chess_quiz" in kinds:
        out.append("A chess set per pair")
    if "snake_race" in kinds and "pawns" not in kinds:
        out.append("A marker per player: a coin, an eraser, or a checker")
    if "spinner" in kinds:
        out.append("A paper clip and a pencil per spinner")
    if kinds & {"cards", "snake_race", "question_checkers", "four_in_a_row", "chess_quiz"}:
        out.append("The fold-over cards, one set per group")
    return out


def teacher_page(m: "Maker", plan: list, ranges: list) -> None:
    pen, P, c = m.pen, m.P, m.pen.c
    y = PAGE_H - MARGIN
    size, lines = pen.fit(P["title"], pen.f.bold, PAGE_W - 2 * MARGIN, 60, 22, "", minimum=14)
    pen.lines(lines, pen.f.bold, size, MARGIN, PAGE_W - MARGIN, y - len(lines) * size * 1.2, y, "left", "top")
    y -= len(lines) * size * 1.2 + 4
    levels = [sum(1 for card in P["cards"] if card["level"] == k) for k in (1, 2, 3)]
    n = len(P["cards"])
    counts = [f"{v} with {k} dot" + ("s" if k > 1 else "") for k, v in zip((1, 2, 3), levels) if v]
    deck = f"{n} card{'s' if n != 1 else ''}" + (f" ({', '.join(counts)})" if counts else "")
    info = "  |  ".join(x for x in ("Paper pieces", f"grade {P['grade']}", P["subject"], deck) if x)
    y = pen.para(info, MARGIN, y, PAGE_W - 2 * MARGIN, 11, gray=0.35) - 8
    if any(card["level"] == 3 for card in P["cards"]) and any(card["level"] < 3 for card in P["cards"]):
        y = pen.para("Levels: each card has 1 to 3 dots. For a group still practicing, take out the 3-dot cards "
                     "(a star then means a 2-dot card). For a group that's ahead, use only the 2- and 3-dot cards.",
                     MARGIN, y, PAGE_W - 2 * MARGIN, 11) - 8
    y = pen.para("Everything prints one-sided, in black and white. Students need scissors (a glue stick helps for "
                 "the die and pawns). Each piece starts "
                 "on a new page; print just the pages you want.", MARGIN, y, PAGE_W - 2 * MARGIN, 11) - 14
    cols = [("Pages", 44.0), ("Piece", 206.0), ("Print on", 150.0), ("Prep", 140.0)]
    xs = [MARGIN]
    for _, w in cols[:-1]:
        xs.append(xs[-1] + w)
    c.setFillGray(INK)
    c.setFont(pen.f.bold, 10)
    for (name, _), x in zip(cols, xs):
        c.drawString(x, y - 10, name)
    y -= 15
    size, lead, small = 9.5, 11.5, 8.5
    for (piece, pages), (a, b) in zip(plan, ranges):
        what = WHAT[piece["type"]]
        if piece["type"] == "cards":
            what = f"{n} cards: question front, answer back."
        if piece["type"] == "bingo":
            what = f"{piece['boards']} boards, {piece['size']}x{piece['size']}, and a caller's list."
        if piece["type"] == "minibook":
            what = "A blank 8-page book to write." if piece["blank"] else what + (" And a blank one." if
                                                                                    piece["also_blank"] else "")
        texts = [(f"{a}" if a == b else f"{a}-{b}", pen.f.regular), (piece["name"], pen.f.bold),
                 (PRINT[piece["type"]][0], pen.f.regular), (PRINT[piece["type"]][1], pen.f.regular)]
        wrapped = [pen.wrap(t, f, size, w - 10) for (t, f), (_, w) in zip(texts, cols)]
        sub = pen.wrap(what, pen.f.regular, small, cols[1][1] - 10)
        h = max(max(len(wr) for wr in wrapped) * lead, lead + len(sub) * (small + 1.5)) + 7
        c.setStrokeGray(0.8)
        c.setLineWidth(0.6)
        c.line(MARGIN, y, PAGE_W - MARGIN, y)
        for k, (wr, x) in enumerate(zip(wrapped, xs)):
            pen.lines(wr, texts[k][1], size, x, x + 200, y - 3.5 - len(wr) * lead, y - 3.5, "left", "top",
                      leading=lead / size)
        pen.lines(sub, pen.f.regular, small, xs[1], xs[1] + 200, y - 3.5 - lead - len(sub) * (small + 1.5),
                  y - 3.5 - lead, "left", "top", leading=(small + 1.5) / small, gray=0.35)
        y -= h
    c.setStrokeGray(0.8)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 26
    # materials on the left, tips on the right
    half = (PAGE_W - 2 * MARGIN - 24) / 2
    notes = []
    if any(pc["type"] in ("cards",) + GAMES for pc in P["pieces"]):
        notes.append("Fold-over cards: fold on the dashed line, printing outside, then turn the card over side to "
                     "side, like a page, to read the answer. Students can cut and fold their own; a little glue "
                     "between the halves makes them sturdier.")
    if any(levels):
        notes.append("Dots show how hard a card is: 1 dot is a warm-up, 3 dots a stretch. The games save 3-dot cards "
                     "for their big moments, and students explain those answers.")
    if any(pc["type"] == "blank_cards" for pc in P["pieces"]):
        notes.append("Look over students' own cards before they join a game: one clear answer for each question.")
    for x, head, items in ((MARGIN, "Materials", materials(P)), (MARGIN + half + 24, "Tips", notes)):
        if not items:
            continue
        need = 14 + sum(pen.para_height(t, half - 14, 10) + 3 for t in items)
        if head == "Tips" and y - need < MARGIN:
            continue  # nice to have; the materials matter more
        c.setFillGray(INK)
        c.setFont(pen.f.bold, 12)
        c.drawString(x, y, head)
        yy = y - 8
        for item in items:
            c.setFillGray(INK)
            c.circle(x + 4, yy - 7.2, 1.8, stroke=0, fill=1)
            yy = pen.para(item, x + 14, yy, half - 14, 10) - 3
        if yy < MARGIN:
            pen.warnings.append("the teacher's page runs off the bottom: list fewer pieces")


BUILDERS = {"cards": piece_cards, "blank_cards": piece_blank_cards, "board": piece_board, "die": piece_die,
            "spinner": piece_spinner, "pawns": piece_pawns, "fortune_teller": piece_fortune_teller,
            "minibook": piece_minibook, "abcd": piece_abcd, **{g: piece_game for g in GAMES}}


class Maker:
    """What every piece draws with: the pieces file and the pen."""

    def __init__(self, P: dict, pen: Pen):
        self.P, self.pen = P, pen


def build(json_path: Path, out_dir: Path) -> dict:
    """Writes out_dir/pieces.pdf. Returns a report: files, pages, each piece's pages, and warnings."""
    json_path, out_dir = Path(json_path), Path(out_dir)
    try:
        data = S.read_json(json_path)
    except ValueError as e:
        raise PiecesError(f"{json_path.name} isn't valid JSON: {e}") from None
    P = normalize(data)
    warnings = level_problems(P)
    fonts, ok = F.choose(all_texts(P))
    if not ok:
        warnings.append(f"these characters will print as \"?\": {F.unprintable(all_texts(P))}. No Unicode font was "
                        "found; write them in words")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "pieces.pdf"
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(fonts.text(f"{P['title']}: paper pieces"))
    c.setAuthor("Paper Loop")
    pen = Pen(c, fonts, P["grade"], warnings)
    m = Maker(P, pen)
    plan, extra = [], {}
    for piece in P["pieces"]:
        pages = BUILDERS[piece["type"]](m, piece) if piece["type"] != "bingo" else None
        if piece["type"] == "bingo":
            pages, extra["caller_pages"] = piece_bingo(m, piece)
        plan.append((piece, pages))
    ranges, n = [], 2
    for _, pages in plan:
        ranges.append((n, n + len(pages) - 1))
        n += len(pages)
    pen.page = 1
    teacher_page(m, plan, ranges)
    pen.footer(P["title"])
    c.showPage()
    for _, pages in plan:
        for draw in pages:
            pen.page += 1
            if not draw():
                pen.footer(P["title"])
            c.showPage()
    c.save()
    seen, unique = set(), []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return {"files": ["pieces.pdf"], "pdf": str(path), "pages": pen.page, "cards": len(P["cards"]),
            "pieces": [{"type": piece["type"], "name": piece["name"], "pages": [a, b]}
                       for (piece, _), (a, b) in zip(plan, ranges)],
            "warnings": unique}


def main(argv: list[str] | None = None) -> int:
    """`pieces FILE.json --out DIR`: prints what it wrote, then anything to check."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["pieces"]:
        argv = argv[1:]
    parser = argparse.ArgumentParser(prog="paper_loop.py pieces",
                                     description="Fold-over cards, games, and foldables from one pieces file.")
    parser.add_argument("pieces", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = build(args.pieces, args.out)
    except (PiecesError, OSError) as e:
        print(f"Can't make the pieces: {e}")
        return 1
    except (KeyError, TypeError, IndexError, AttributeError, ValueError) as e:
        print(f"Can't make the pieces: a field is missing or the wrong type ({type(e).__name__}: {e}). Check it "
              "against references/pieces-format.md.")
        return 1
    print(f"Wrote {args.out / 'pieces.pdf'}: {report['pages']} pages, {report['cards']} cards. Page 1 is for the "
          "teacher.")
    for piece in report["pieces"]:
        a, b = piece["pages"]
        print(f"  page{'s' if b > a else ''} {a if a == b else f'{a}-{b}'}: {piece['name']}")
    for warning in report["warnings"]:
        print(f"  Check: {warning}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
