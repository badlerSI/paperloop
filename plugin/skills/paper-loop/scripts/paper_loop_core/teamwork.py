"""Group work where students teach each other: role cards, the group's task, and what each student hands in.

Cooperative learning helps when two things are both true: the group shares a goal, and each student is
accountable on their own (Slavin). So every activity here gives each student a job (on a card that rotates
each round, so no one is stuck as the helper or the helped), a group task that needs several kinds of
ability, and an individual worksheet at the end that Paper Loop marks like any other.

Structures:
- lab: a hands-on investigation (dice, tokens, measurements) with a data table, in groups of 3-5;
- jigsaw: each student becomes the expert on one part and teaches it to their home group;
- reciprocal: reading in groups of four: predict, question, clarify, summarize;
- pairs: peer tutoring in the PALS pattern: a coach and a player, who switch halfway;
- heads: Numbered Heads Together: the group makes sure everyone can answer; one is called at random.

`groups` forms mixed-skill groups from a class's marked work, by class ID only.
"""

from __future__ import annotations

import io
import json
import random
import re
import string
from pathlib import Path

from reportlab.pdfgen import canvas

from . import diagrams as D
from . import fonts as F
from . import sheet as S
from . import sources as SRC
from .pieces import (INK, MARGIN, PAGE_H, PAGE_W, Pen, PiecesError, cut_line, fold_line, scissors,
                     step_number)

# Each role: (name, what to do, sentence starters). Everyone also does the work itself.
ROLES = {
    "lab": [
        ("Facilitator", ["Read each step out loud.", "Make sure everyone talks before the group decides.",
                         "Watch the time."],
         ["Who hasn't shared yet?", "What should we try next?", "We have __ minutes left."]),
        ("Recorder", ["Write the group's data and answers.", "Read them back before the group moves on."],
         ["Let me read that back: __", "Is this what we agree on?"]),
        ("Skeptic", ["Ask “How do we know?”", "Before moving on, check that everyone can explain the answer, "
                     "not just say it."],
         ["How do you know?", "What's our evidence?", "Can you explain it another way?"]),
        ("Reporter", ["Share the group's thinking with the class.", "Ask the teacher a question only after the "
                      "whole group has tried."],
         ["Our group found __ because __.", "We disagreed about __."]),
        ("Materials", ["Get and return the materials.", "Roll the dice and move the pieces."],
         ["Everyone ready? I'm rolling.", "Count with me: __."]),
    ],
    "reciprocal": [  # in the order they speak after each part
        ("Summarizer", ["After each part, tell the big idea in a sentence or two."],
         ["This part is mostly about __.", "First __, then __."]),
        ("Questioner", ["Ask the group a question about the part.", "Ask a “why” question too."],
         ["Why did __?", "Where does it say __?"]),
        ("Clarifier", ["Find a word or idea that's confusing. Figure it out together."],
         ["I'm not sure what __ means.", "Let's reread that sentence."]),
        ("Predictor", ["Guess what the next part will be about, and why."],
         ["I think the next part will tell __, because __."]),
    ],
    "jigsaw": [
        ("Expert", ["Learn your part well enough to teach it.", "Teach it to your home group in about 3 minutes.",
                    "Ask your group your check question.", "When the others teach, take notes and ask until "
                    "you could explain it yourself."],
         ["The big idea of my part: __.", "My question for you: __", "Can you say that another way?"]),
    ],
    "pairs": [
        ("Coach", ["Read the question. Keep the answer hidden.", "Right? Say what was right.",
                   "Not yet? Say “Check it,” and let them try again.",
                   "Still stuck? Give a hint, then show it. They say it back to you."],
         ["Check it.", "What do you know that helps?", "Yes! You __."]),
        ("Player", ["Say your answer out loud.", "Not sure? Say what you're thinking.",
                    "Halfway, switch: you become the coach."],
         ["I think __ because __.", "Can I try again?"]),
    ],
    "heads": [
        ("Number", ["Heads together: make sure everyone in your group can answer.",
                    "When the teacher calls your number, you answer for the group, alone."],
         ["Let's check: can everyone say it?", "Explain it to me as if I'll be called."]),
    ],
}
STRUCTURES = {  # (name, why it works: what the evidence says, plainly)
    "lab": ("Lab group", "A shared goal plus each student accountable alone is what makes group work pay off: "
            "methods with both averaged about +0.32 SD in Slavin's review, against about +0.07 with one or neither. "
            "Jobs rotate, so no one is always the helper."),
    "jigsaw": ("Jigsaw", "Every student has something the group needs. On learning, jigsaw's results are mixed "
               "(five recent classroom trials found no gain), so this version adds the safeguards of Slavin's "
               "Jigsaw II: you check each expert's teach box, everyone writes notes on every part, and each "
               "student does the worksheet on all parts alone."),
    "reciprocal": ("Reciprocal teaching", "Summarizing, questioning, clarifying, and predicting, practiced aloud in "
                   "turns (Palincsar and Brown): gains in reading comprehension across studies (Rosenshine and "
                   "Meister 1994)."),
    "pairs": ("Coach and player", "Peer tutoring in the PALS pattern: a set way to correct, and partners who "
              "switch so each one coaches. PALS has strong evidence in elementary reading; in math the evidence is "
              "weaker, so keep sessions short and regular."),
    "heads": ("Numbered Heads Together", "Quick review: each group makes sure everyone can answer, because a die "
              "picks who answers. There's little rigorous research on it alone; its value is that every student "
              "has to be ready."),
}
SIZES = {"lab": (3, 5), "jigsaw": (3, 5), "reciprocal": (4, 4), "pairs": (2, 2), "heads": (3, 5)}
FIELDS = ("title", "grade", "grade_band", "subject", "structure", "group_size", "minutes", "goal", "abilities",
          "materials", "launch", "steps", "rounds", "rotate_every", "dice", "table", "data", "board", "tokens", "roles", "parts",
          "cards",
          "worksheet", "class_size", "versions", "listen_for", "debrief", "sources")
PATTERNS = ("solid", "dots", "stripes", "plain", "checks", "rings")


class TeamworkError(PiecesError):
    pass


def _list(data: dict, name: str, where: str, need: bool = False) -> list:
    value = data.get(name, [])
    if not isinstance(value, list) or (need and not value):
        raise TeamworkError(f"{where}: \"{name}\" is a list" + (" with at least one entry" if need else ""))
    return value


PART_FIELDS = ("title", "text", "teach", "check", "source", "cite", "words", "quote", "quote_source")
NO_ADAPT_NAMES = {"commonlit": "commonlit.org", "readworks": "readworks.org", "ck-12": "ck12.org", "ck12": "ck12.org",
                  "openstax": "openstax.org", "newsela": "newsela.com", "khan academy": "khanacademy.org"}


def _part(part: dict, k: int, need_title: bool) -> dict:
    """A jigsaw or reading part, its credit line checked the way a worksheet's passage is."""
    where = f"part {k}"
    if not isinstance(part, dict):
        raise TeamworkError(f"{where}: one object, {{\"title\": ..., \"text\": ...}}")
    unknown = sorted(set(part) - set(PART_FIELDS))
    if unknown:
        raise TeamworkError(f"{where}: unknown field {', '.join(unknown)}; a part has {', '.join(PART_FIELDS)}")
    part = dict(part)
    for name in ("title", "text", "check", "source", "quote", "quote_source"):
        part[name] = _text(part, name, where)
    if not part["text"] or (need_title and not part["title"]):
        raise TeamworkError(f"{where}: needs " + ("\"title\" and " if need_title else "") + "\"text\"" +
                            (" (and \"teach\": the 2-3 things to teach, and \"check\": a question to ask the home "
                             "group)" if need_title else ""))
    part["teach"] = _texts(part, "teach", where)
    if part.get("cite"):
        try:
            part["source"], _ = SRC.check_cite(part["cite"], where)
        except S.WorksheetError as e:
            raise TeamworkError(str(e)) from None
    said = " ".join((part["source"], part["quote_source"])).lower()
    for brand, site in NO_ADAPT_NAMES.items():
        if re.search(rf"\b{re.escape(brand)}\b", said):
            raise TeamworkError(f"{where}: {SRC.NO_ADAPT[site]}, so a part can't be adapted from it. {SRC.INSTEAD}.")
    words = part.get("words", [])
    if not isinstance(words, list) or not all(isinstance(w, dict) and isinstance(w.get("word"), str) and w["word"]
                                              and isinstance(w.get("means"), str) and w["means"] for w in words):
        raise TeamworkError(f"{where}: \"words\" is [{{\"word\": \"alliance\", \"means\": \"an agreement to help "
                            "each other\"}}]")
    part["words"] = words
    return part


def _text(data: dict, name: str, where: str) -> str:
    """A text field: absent is empty; a number is fine; anything else says what's wrong."""
    value = data.get(name)
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TeamworkError(f"{where}: \"{name}\" is text")
    return str(value)


def _texts(data: dict, name: str, where: str) -> list[str]:
    """A list of texts (a single text is a mistake: it would print one letter per line)."""
    value = data.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(isinstance(v, bool) or not isinstance(v, (str, int, float)) for v in value):
        raise TeamworkError(f"{where}: \"{name}\" is a list of texts, [\"...\", \"...\"]")
    return [str(v) for v in value]


def _whole(data: dict, name: str, default: int, low: int, high: int, where: str = "teamwork file") -> int:
    value = data.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) \
            or not low <= value <= high:
        raise TeamworkError(f"{where}: \"{name}\" is a whole number from {low} to {high}")
    return int(value)


BOARDS = {"grid": ("cols", "rows"), "number_line": ("min", "max", "parts"), "rows": ("rows",), "ring": ("stations",),
          "graph": ("xmin", "xmax", "xstep", "ymin", "ymax", "ystep"), "diagram": ("width", "height", "shapes")}


def _board(board):
    """A printed board, checked: a grid, a number line, labeled layers, a ring of stations, or graph axes."""
    if board is None:
        return None
    if not isinstance(board, dict) or board.get("kind") not in BOARDS:
        raise TeamworkError(f"teamwork file: \"board\" is {{\"kind\": one of {', '.join(BOARDS)}, ...}}")
    kind = board["kind"]
    missing = [f for f in BOARDS[kind] if f not in board]
    if missing:
        raise TeamworkError(f"board: a {kind} board needs {', '.join(missing)}")
    if kind == "diagram":  # a picture drawn from the worksheet's diagram shapes: a track, a map, a food web
        try:
            d = S._diagram({k: v for k, v in board.items() if k in ("width", "height", "shapes", "description")},
                           "board", faint_images=False)
        except (S.WorksheetError, KeyError, TypeError, ValueError) as e:
            raise TeamworkError(f"board: {e}" if not isinstance(e, S.WorksheetError) else str(e)) from None
        return {**board, **d}
    if kind in ("rows", "ring"):
        names = board[BOARDS[kind][0]]
        if not isinstance(names, list) or not 2 <= len(names) <= 12 or not all(isinstance(n, str) and n for n in names):
            raise TeamworkError(f"board: \"{BOARDS[kind][0]}\" is a list of 2-12 names")
        return board
    try:
        nums = {f: float(board[f]) for f in BOARDS[kind]}
    except (TypeError, ValueError):
        raise TeamworkError(f"board: {', '.join(BOARDS[kind])} are numbers") from None
    if kind == "grid" and not (2 <= nums["cols"] <= 40 and 2 <= nums["rows"] <= 50):
        raise TeamworkError("board: a grid is 2-40 columns and 2-50 rows")
    if kind == "number_line" and not (nums["max"] > nums["min"] and nums["max"] - nums["min"] <= 6
                                      and 1 <= nums["parts"] <= 48 and nums["min"] == int(nums["min"])):
        raise TeamworkError("board: a number line runs from a whole number \"min\" to \"max\" (at most 6 wholes), with "
                            "1-48 \"parts\" in each whole")
    if kind == "graph" and not (nums["xmax"] > nums["xmin"] and nums["ymax"] > nums["ymin"] and nums["xstep"] > 0
                                and nums["ystep"] > 0 and (nums["xmax"] - nums["xmin"]) / nums["xstep"] <= 40
                                and (nums["ymax"] - nums["ymin"]) / nums["ystep"] <= 40):
        raise TeamworkError("board: graph axes need max above min, and steps that make 40 or fewer gridlines")
    return {**board, **nums}


LAB_ONLY = ("rounds", "rotate_every", "dice", "table", "data", "board", "tokens")


def normalize(data: dict) -> dict:
    """Defaults filled in and every field checked, with errors that say what to fix."""
    if not isinstance(data, dict):
        raise TeamworkError("teamwork file: one JSON object with \"title\", \"grade\", and \"structure\"")
    unknown = sorted(set(data) - set(FIELDS))
    if unknown:
        raise TeamworkError(f"teamwork file: unknown field {', '.join(unknown)}; the fields are {', '.join(FIELDS)}")
    W = "teamwork file"
    kind = data.get("structure")
    if not isinstance(kind, str) or kind not in STRUCTURES:
        raise TeamworkError(f"{W}: \"structure\" is one of {', '.join(STRUCTURES)}")
    title = _text(data, "title", W)
    if not title:
        raise TeamworkError(f"{W}: missing \"title\"")
    try:
        grade = S.grade_of(data)
    except (TypeError, ValueError):
        raise TeamworkError(f"{W}: \"grade\" is a whole number from 2 to 12") from None
    if not 2 <= grade <= 12:
        raise TeamworkError(f"{W}: \"grade\" is a whole number from 2 to 12")
    if kind != "lab":
        stray = [f for f in LAB_ONLY if f in data]
        if stray:
            raise TeamworkError(f"{W}: {', '.join(stray)} print only in a lab, not in a {STRUCTURES[kind][0].lower()}")
    low, high = SIZES[kind]
    parts = _list(data, "parts", W)
    if kind == "jigsaw":
        size = len(parts)
        if not low <= size <= high:
            raise TeamworkError(f"{W}: a jigsaw needs {low}-{high} \"parts\", one per expert")
        if "group_size" in data and data["group_size"] != size:
            raise TeamworkError(f"{W}: a jigsaw's group size is its number of parts ({size}); leave out \"group_size\"")
    else:
        size = _whole(data, "group_size", 2 if kind == "pairs" else 4, 1, 99)
    if not low <= size <= high:
        raise TeamworkError(f"{W}: a {STRUCTURES[kind][0].lower()} works with {low}"
                            + (f" to {high}" if high != low else "") + f" students, not {size}"
                            + (" (one part per expert)" if kind == "jigsaw" else ""))
    rounds = _whole(data, "rounds", 1, 1, 30)
    out = {**data, "kind": kind, "title": title, "grade": grade, "group_size": size,
           "minutes": _whole(data, "minutes", 30, 5, 180), "subject": _text(data, "subject", W),
           "goal": _text(data, "goal", W), "rounds": rounds,
           "rotate_every": _whole(data, "rotate_every", 1, 1, rounds), "class_size": _whole(data, "class_size", 0, 0, 200),
           "worksheet": _text(data, "worksheet", W)}
    for name in ("materials", "launch", "abilities", "steps", "debrief", "listen_for", "sources"):
        out[name] = _texts(data, name, W)
    out["tokens"], out["cards"] = _list(data, "tokens", W), _list(data, "cards", W)
    if kind == "lab" and not out["steps"]:
        raise TeamworkError(f"{W}: a lab needs \"steps\": what the group does each round")
    if kind == "jigsaw" and not low <= len(parts) <= high:
        raise TeamworkError(f"{W}: a jigsaw needs {low}-{high} \"parts\", one per expert")
    if kind == "reciprocal" and not 2 <= len(parts) <= 8:
        raise TeamworkError(f"{W}: reciprocal teaching needs 2-8 \"parts\": the reading in chunks, with a stop to talk "
                            "after each")
    out["parts"] = [_part(part, k, kind == "jigsaw") for k, part in enumerate(parts, start=1)]
    if kind in ("pairs", "heads") and not out["cards"]:
        raise TeamworkError(f"{W}: {STRUCTURES[kind][0]} needs \"cards\": questions with answers, "
                            "[{\"q\": \"...\", \"a\": \"...\"}]")
    cards = []
    for k, card in enumerate(out["cards"], start=1):
        if not isinstance(card, dict) or card.get("q") in (None, "") or card.get("a") in (None, ""):
            raise TeamworkError(f"card {k}: needs \"q\" and \"a\"")
        cards.append({"q": _text(card, "q", f"card {k}"), "a": _text(card, "a", f"card {k}")})
    out["cards"] = cards
    tokens = []
    for k, token in enumerate(out["tokens"], start=1):
        if not isinstance(token, dict) or not _text(token, "label", f"token {k}"):
            raise TeamworkError(f"token {k}: needs \"label\" and a whole-number \"count\" (per group)")
        count = _whole(token, "count", 0, 1, 300, f"token {k}")
        if not count:
            raise TeamworkError(f"token {k}: needs \"label\" and a whole-number \"count\" (per group)")
        size_in = token.get("size", 0.75)
        if isinstance(size_in, bool) or not isinstance(size_in, (int, float)) or not 0.5 <= size_in <= 4:
            raise TeamworkError(f"token {k}: \"size\" is the side in inches, 0.5 to 4 (default 0.75)")
        if token.get("pattern", "plain") not in PATTERNS:
            raise TeamworkError(f"token {k}: \"pattern\" is one of {', '.join(PATTERNS)} (so copies stay black "
                                "and white)")
        tokens.append({**token, "label": str(token["label"]), "count": count, "size": size_in})
    out["tokens"] = tokens
    dice = data.get("dice")
    if dice is not None:
        rows = dice.get("rows") if isinstance(dice, dict) else None
        if not isinstance(rows, list) or not rows or any(not isinstance(r, list) or len(r) != 2 for r in rows):
            raise TeamworkError(f"{W}: \"dice\" is {{\"title\": ..., \"rows\": [[\"1-2\", \"what happens\"], ...]}}")
        dice = {"title": _text(dice, "title", "dice"), "rows": [[str(a), str(b)] for a, b in rows]}
    out["dice"] = dice
    out["data"] = []
    for k, d in enumerate(_list(data, "data", W), start=1):
        if not isinstance(d, dict) or not isinstance(d.get("columns"), list) or not isinstance(d.get("rows"), list) \
                or not d["rows"] or any(not isinstance(r, list) or len(r) != len(d["columns"]) for r in d["rows"]):
            raise TeamworkError(f"data table {k}: {{\"title\": ..., \"columns\": [...], \"rows\": [[...], ...]}}, each "
                                "row as long as the columns")
        out["data"].append({"title": _text(d, "title", f"data table {k}"), "columns": [str(c) for c in d["columns"]],
                            "rows": [["" if c is None else str(c) for c in r] for r in d["rows"]]})
    boards = data.get("board")
    out["boards"] = [_board(b) for b in (boards if isinstance(boards, list) else [boards] if boards else [])]
    out["board"] = out["boards"][0] if out["boards"] else None
    table = data.get("table")
    if table is not None:
        if not isinstance(table, dict) or not isinstance(table.get("columns"), list) or not 1 <= len(table["columns"]) <= 6:
            raise TeamworkError(f"{W}: \"table\" is {{\"title\": ..., \"columns\": [up to 6 headings], \"rows\": how "
                                "many}")
        table = {"title": _text(table, "title", "table"), "columns": [str(c) for c in table["columns"]],
                 "rows": _whole(table, "rows", 6, 1, 40, "table")}
    out["table"] = table
    roles = ROLES[kind]
    out["roles"] = roles[:size] if kind in ("lab",) else roles
    if kind == "jigsaw":  # a tent for each expert letter: the A's find each other, and home groups see who's who
        _, jobs, stems = ROLES["jigsaw"][0]
        out["roles"] = [(f"Expert {chr(65 + k)}", [f"Your part: {part['title']}."] + jobs, stems)
                        for k, part in enumerate(out["parts"])]
    if kind == "heads":  # the number is the role: it faces the group, and the job faces the student
        _, jobs, stems = ROLES["heads"][0]
        out["roles"] = [(f"Number {k + 1}", jobs, stems) for k in range(size)]
    if "roles" in data:  # the author's wording, one entry per card
        own = data["roles"]
        if not isinstance(own, list) or len(own) != len(out["roles"]):
            raise TeamworkError(f"{W}: \"roles\" replaces the {len(out['roles'])} cards "
                                f"({', '.join(r[0] for r in out['roles'])}): one entry for each, in that order")
        roles = []
        for k, r in enumerate(own, start=1):
            where = f"role {k}"
            if not isinstance(r, dict) or not _text(r, "name", where) or not _texts(r, "jobs", where):
                raise TeamworkError(f"{where}: needs \"name\" and \"jobs\" (a list), and \"say\" (a list of "
                                    "sentence starters)")
            roles.append((_text(r, "name", where), _texts(r, "jobs", where), _texts(r, "say", where)))
        out["roles"] = roles
    out["_checker"] = _checker_index(out["roles"])
    out["versions"] = _versions(data.get("versions"), out)
    return out


VERSION_FIELDS = ("id", "name", "language", "parts", "roles", "steps", "goal", "labels", "reviewed_by")

# The words the pages themselves print for students, so a version's pages can say them in its language.
LABELS = {
    "en": {"intro": "1. Read your part with the other experts on it. 2. Agree on what matters most. 3. Fill the "
                    "teach box: you'll teach your home group in about 3 minutes.",
           "make_sure": "Make sure you teach: ", "teach_box": "Teach box", "teacher_checked": "Teacher checked",
           "ideas": "The most important ideas, in my words:", "example": "An example:",
           "check": "My check question for the group: ", "answer": "Its answer:",
           "picture": "A picture I'll draw to show it:", "your_job": "{name}: your job", "say_it": "Say it like this",
           "read_together": "Read together",
           "read_intro": "First, the {last} looks at the title and guesses what the reading is about. Take turns "
                         "reading each part aloud, going left. After each part, stop and talk.",
           "stop": "Stop and talk, in this order: {order}. Pass the cards left.",
           "last_stop": "Last stop: {order}. Then sum up the whole reading together.",
           "footer": "Everyone also does the work, and helps each other.",
           "footer_lab": "Next round, pass this card to your left.",
           "footer_lab_every": "Every {every} rounds, pass this card to your left.",
           "footer_reciprocal": "After each stop, pass this card to your left.", "footer_pairs": "Halfway, switch cards.",
           "task": "Group task", "needs": "This task needs {abilities}. Everyone in your group is good at some of these.",
           "rounds": "Rounds:", "check_off": "Check off each round. Pass the role cards left after each one.",
           "check_off_every": "Check off each round. Pass the role cards left after every {every} rounds.",
           "roll": "Roll a die", "our_data": "Our data",
           "close": "Before you move on, {checker} checks: can everyone explain it? Then you each do the worksheet on "
                    "your own.",
           "the_role": "the {name}", "someone": "someone in the group", "key_words": "Key words: ",
           "expert": "Expert {letter}"},
    "es": {"intro": "1. Lee tu parte con los otros expertos. 2. Pónganse de acuerdo en lo más importante. 3. Llena "
                    "el cuadro para enseñar: le vas a enseñar a tu grupo en unos 3 minutos.",
           "make_sure": "Asegúrate de enseñar: ", "teach_box": "Para enseñar", "teacher_checked": "Revisado",
           "ideas": "Las ideas más importantes, en mis palabras:", "example": "Un ejemplo:",
           "check": "Mi pregunta para el grupo: ", "answer": "Su respuesta:",
           "picture": "Un dibujo para mostrarlo:", "your_job": "{name}: tu trabajo", "say_it": "Dilo así",
           "read_together": "Leer juntos",
           "read_intro": "Primero, el {last} mira el título y adivina de qué trata la lectura. Túrnense para leer "
                         "cada parte en voz alta, hacia la izquierda. Después de cada parte, paren y hablen.",
           "stop": "Paren y hablen, en este orden: {order}. Pasen las tarjetas a la izquierda.",
           "last_stop": "Última parada: {order}. Luego resuman juntos toda la lectura.",
           "footer": "Todos también hacen el trabajo y se ayudan.",
           "footer_lab": "En la próxima ronda, pasa esta tarjeta a tu izquierda.",
           "footer_lab_every": "Cada {every} rondas, pasa esta tarjeta a tu izquierda.",
           "footer_reciprocal": "Después de cada parada, pasa esta tarjeta a tu izquierda.",
           "footer_pairs": "A la mitad, cambien de tarjeta.",
           "task": "Tarea del grupo",
           "needs": "Esta tarea necesita {abilities}. Cada persona del grupo es buena en algo de esto.",
           "rounds": "Rondas:", "check_off": "Marca cada ronda. Pasen las tarjetas a la izquierda después de cada una.",
           "check_off_every": "Marca cada ronda. Pasen las tarjetas a la izquierda cada {every} rondas.",
           "roll": "Tira un dado", "our_data": "Nuestros datos",
           "close": "Antes de seguir, {checker} revisa: ¿todos pueden explicarlo? Luego cada uno hace la hoja solo.",
           "the_role": "{name}", "someone": "alguien del grupo", "key_words": "Palabras clave: ",
           "expert": "Experto {letter}"},
}


def _label(A: dict, key: str, **fill) -> str:
    text = (A.get("ui") or LABELS["en"]).get(key) or LABELS["en"][key]
    return text.format(**fill) if fill else text


def _versions(raw, A: dict) -> list[dict]:
    """Versions of the group materials for the students who need them: plain English, or a home language.
    Each replaces the activity's own words (parts, role cards, steps, goal); the work stays the same."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TeamworkError("teamwork file: \"versions\" is a list, [{\"id\": \"plain\", \"parts\": [...]}]")
    from .forms import LANGUAGES
    out, seen = [], set()
    for k, v in enumerate(raw, start=1):
        where = f"version {k}"
        if not isinstance(v, dict):
            raise TeamworkError(f"{where}: one object, {{\"id\": ..., \"parts\": [...]}}")
        unknown = sorted(set(v) - set(VERSION_FIELDS))
        if unknown:
            raise TeamworkError(f"{where}: unknown field {', '.join(unknown)}; a version has {', '.join(VERSION_FIELDS)}")
        vid = _text(v, "id", where)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", vid) or vid in seen:
            raise TeamworkError(f"{where}: \"id\" is a short, different name for each, in small letters (\"plain\", "
                                "\"es\")")
        seen.add(vid)
        lang = _text(v, "language", where)
        known = LANGUAGES.get(lang)
        name = _text(v, "name", where) or (known[1] if known else lang) or "Plain English"
        labels = v.get("labels") or {}
        if not isinstance(labels, dict) or any(k not in LABELS["en"] or not isinstance(t, str) for k, t in labels.items()):
            raise TeamworkError(f"{where}: \"labels\" gives the page's own words in the version's language, by key: "
                                + ", ".join(LABELS["en"]))
        for key, text in labels.items():  # the same {placeholders} as the English, and nothing else
            try:
                fields = {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
                wanted = {f for _, f, _, _ in string.Formatter().parse(LABELS["en"][key]) if f is not None}
            except ValueError:
                fields, wanted = {"?"}, set()
            if fields - wanted:
                raise TeamworkError(f"{where}: label {key!r} may use only "
                                    + (", ".join("{" + f + "}" for f in sorted(wanted)) or "no {placeholders}")
                                    + " (write a literal brace as {{ or }})")
        V = {"id": vid, "name": name, "language": lang, "reviewed_by": _text(v, "reviewed_by", where),
             "ui": {**LABELS["en"], **LABELS.get(lang, {}), **labels},
             "quality": (known[2] if known else "unknown") if lang else "", "english_name": known[0] if known else lang,
             "goal": _text(v, "goal", where) or A["goal"], "steps": _texts(v, "steps", where) or A["steps"]}
        parts = v.get("parts")
        if parts is not None:
            if not isinstance(parts, list) or len(parts) != len(A["parts"]):
                raise TeamworkError(f"{where}: \"parts\" has one entry for each of the activity's {len(A['parts'])} "
                                    "parts, in order (each with the fields it changes: title, text, teach, check, words)")
            merged = []
            for n, (base, change) in enumerate(zip(A["parts"], parts), start=1):
                if not isinstance(change, dict):
                    raise TeamworkError(f"{where}, part {n}: one object with the fields it changes")
                keep = {f: base[f] for f in ("title", "text", "teach", "check", "words", "quote", "quote_source",
                                             "source") if base.get(f)}
                merged.append(_part({**keep, **change}, n, A["kind"] == "jigsaw"))
            V["parts"] = merged
        else:
            V["parts"] = A["parts"]
        roles = v.get("roles")
        if roles is not None:
            if not isinstance(roles, list) or len(roles) != len(A["roles"]):
                raise TeamworkError(f"{where}: \"roles\" has one entry for each of the {len(A['roles'])} cards, in order")
            V["roles"] = []
            for n, r in enumerate(roles, start=1):
                rw = f"{where}, role {n}"
                if not isinstance(r, dict) or not _text(r, "name", rw) or not _texts(r, "jobs", rw):
                    raise TeamworkError(f"{rw}: needs \"name\" and \"jobs\" (and \"say\")")
                V["roles"].append((_text(r, "name", rw), _texts(r, "jobs", rw), _texts(r, "say", rw)))
        else:
            V["roles"] = None
        if parts is None and roles is None and "steps" not in v and "goal" not in v:
            raise TeamworkError(f"{where}: changes nothing; give the \"parts\", \"roles\", \"steps\", or \"goal\" in "
                                "its words")
        out.append(V)
    return out


def _version_activity(A: dict, V: dict) -> dict:
    """The activity as this version prints it."""
    return {**A, "parts": V["parts"], "roles": V["roles"] or A["roles"], "steps": V["steps"], "goal": V["goal"],
            "tag": V["name"], "ui": V["ui"]}


def _version_word(A: dict, V: dict, path: Path) -> Path:
    """A version in a script these pages can't shape, as a Word file: Word and Google Docs shape every script."""
    from . import script as SC
    from . import wordfile as W
    lang = V["language"]
    rtl = SC.has_rtl(json.dumps([V["parts"], V["roles"], V["steps"], V["goal"]], ensure_ascii=False))
    doc = W.Doc()
    doc.para(A["title"], bold=True, size=18, markup=False)
    doc.para(f"{V['name']}: give this to students who read it more easily than English. They still teach, "
             "listen, and talk with their group.", italic=True, color="666666", markup=False)
    say = lambda text, **kw: doc.para(text, markup=False, lang=lang, rtl=rtl, **kw)  # noqa: E731
    if V["goal"] != A["goal"]:
        say(V["goal"], bold=True)
    if V["steps"] is not A["steps"]:
        doc.heading("Steps", 2)
        for n, step in enumerate(V["steps"], start=1):
            say(f"{n}. {step}", after=40)
    for n, part in enumerate(V["parts"] if V["parts"] is not A["parts"] else [], start=1):
        doc.heading(f"{chr(64 + n) if A['kind'] == 'jigsaw' else n}. {part.get('title') or ''}".rstrip(". "), 2)
        for para in str(part["text"]).split("\n\n"):
            say(para)
        if part.get("quote"):
            say(f"“{part['quote']}” {('— ' + part['quote_source']) if part.get('quote_source') else ''}", italic=True)
        if part.get("words"):
            say("; ".join(f"{w['word']}: {w['means']}" for w in part["words"]))
        if part.get("teach"):
            say("; ".join(part["teach"]), bold=True)
        if part.get("check"):
            say(part["check"])
    if V["roles"]:
        doc.heading("Jobs", 2)
        for name, jobs, stems in V["roles"]:
            say(name, bold=True, after=20)
            for line in jobs + [f"“{t}”" for t in stems]:
                say(line, after=20)
    doc.save(path, f"{A['title']} ({V['name']})")
    return path


# --- Drawing ----------------------------------------------------------------------------------------

def _size(A: dict, size: float) -> float:
    """Type a student reads: bigger in grades 2-5."""
    return size * (1.25 if A["grade"] <= 3 else 1.12 if A["grade"] <= 5 else 1)


def _header(pen: Pen, A: dict, what: str) -> float:
    c = pen.c
    if A.get("tag"):
        what = f"{what} · {A['tag']}"
    c.setFillGray(INK)
    size = 16.0
    while size > 9 and pen.width(what, pen.f.bold, size) > PAGE_W - 2 * MARGIN:
        size -= 0.5
    if pen.width(what, pen.f.bold, size) > PAGE_W - 2 * MARGIN:
        pen.warnings.append(f"the heading \"{what[:40]}...\" is too long for the page: shorten it")
    c.setFont(pen.f.bold, size)
    c.drawString(MARGIN, PAGE_H - MARGIN - 14, pen.f.text(what))
    c.setFont(pen.f.regular, 9)
    c.setFillGray(0.4)
    if what != A["title"] and pen.width(what, pen.f.bold, size) + pen.width(A["title"], pen.f.regular, 9) + 20 \
            < PAGE_W - 2 * MARGIN:  # the activity's name, when there's room beside the heading
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN - 12, pen.f.text(A["title"]))
    c.setFillGray(INK)
    return PAGE_H - MARGIN - 30


def teacher_page(pen: Pen, A: dict, worksheet_note: str, pages: dict[str, str]) -> None:
    name, why = STRUCTURES[A["kind"]]
    y = _header(pen, A, A["title"])
    exit_minutes = 10 if A.get("worksheet") else 0
    info = "  |  ".join(x for x in (name, f"grade {A['grade']}", A["subject"], f"groups of {A['group_size']}",
                                    f"about {A['minutes']} minutes" + (f", plus about {exit_minutes} for the exit "
                                                                       "sheet" if exit_minutes else "")) if x)
    y = pen.para(info, MARGIN, y, PAGE_W - 2 * MARGIN, 11, gray=0.35) - 6
    if A["goal"]:
        y = pen.para(f"Goal: {A['goal']}", MARGIN, y, PAGE_W - 2 * MARGIN, 11.5, pen.f.bold) - 6
    y = pen.para(f"Why it works: {why}", MARGIN, y, PAGE_W - 2 * MARGIN, 10) - 10
    rotation = _rotation(A)
    sections = [("Before class", [
        _grouping(A) + _counts(A),
        "This page is for you: print it once. " + _printing(A, pages),
        ("Each group needs: " + "; ".join(A["materials"]) + ".") if A["materials"] else "",
        _versions_note(A, pages),
        worksheet_note]),
        ("Launch, with the whole class", A["launch"]),
        ("During", _during(A) + (A["steps"] if A["kind"] != "lab" else [])),
        (rotation[0], rotation[1] + [
                         "Say out loud when a student does something the task needs, specifically (“your table "
                         "made the pattern easy to see”): it raises how the group sees them."
                         if not A["abilities"] else
                         "This task needs " + ", ".join(A["abilities"]) + ": no one is good at all of them, and "
                         "everyone is good at some. When a student shows one, say so to the group, specifically."]),
    ]
    if A["listen_for"]:
        sections.append(("Listen for", A["listen_for"]))
    if A["debrief"]:
        sections.append(("Wrap up with the class", A["debrief"]))
    if A["sources"]:
        sections.append(("Sources", A["sources"]))
    full = False
    for head, items in sections:
        items = [item for item in items if item]
        first = pen.para_height(f"• {items[0]}", PAGE_W - 2 * MARGIN - 6, 10) if items else 0
        if y - 17 - first < 50:
            full = True
        for n, item in enumerate(items):
            if full or y - (17 if n == 0 else 0) - pen.para_height(f"• {item}", PAGE_W - 2 * MARGIN - 6, 10) < 50:
                full = True
                break
            if n == 0:
                pen.c.setFont(pen.f.bold, 11.5)
                pen.c.drawString(MARGIN, y - 11, pen.f.text(head))
                y -= 17
            y = pen.para(f"• {item}", MARGIN + 6, y, PAGE_W - 2 * MARGIN - 6, 10) - 3
        if full:
            pen.warnings.append(f"the teacher's page ran out of room at \"{head}\": shorten the goal, "
                                "listen_for, or debrief")
            break
        y -= 7


def _checker_index(roles: list) -> int | None:
    """Which card asks "can everyone explain it?": one named for it, else one whose job is checking."""
    for k, (name, _, _) in enumerate(roles):
        if re.search(r"skeptic|check", name, re.I):
            return k
    for k, (_, jobs, _) in enumerate(roles):
        if any(re.search(r"\bcheck(s|ing)?\b(?! out)", j, re.I) for j in jobs):
            return k
    return None


def _checker(A: dict) -> str:
    """The checker's card by its position in the activity's own roles, so a translated card is found too."""
    k = A.get("_checker")
    if k is None or k >= len(A["roles"]):
        return _label(A, "someone")
    return _label(A, "the_role", name=A["roles"][k][0])


def _rotation(A: dict) -> tuple[str, list[str]]:
    kind = A["kind"]
    if kind == "jigsaw":
        return ("Every expert counts", ["Each home group needs every letter. If a student is absent, the home group "
                                        "reads that expert sheet together; if a group has five, two share a letter."])
    if kind == "heads":
        return ("Anyone can be called", ["Roll a die for the number, so every student gets ready, not only the one "
                                         "who usually answers."])
    sizes = group_sizes(A["class_size"], A["group_size"], *group_range(kind, A["group_size"])) if A["class_size"] else []
    extra = (f" In a group of {max(sizes)}, two students share a job card." if sizes and max(sizes) > len(A["roles"])
             and kind in ("lab", "reciprocal") else "")
    turns = len(A["parts"]) if kind == "reciprocal" else -(-A["rounds"] // max(1, A["rotate_every"]))
    every = turns >= len(A["roles"])
    turns -= 1  # hand-offs: the cards change hands between turns
    return ("Jobs rotate", [("Halfway, partners switch, so each is the coach once." if kind == "pairs" else
                             "Pass the role cards one seat to the left " + (
                                 "after each stop" if kind == "reciprocal" else "each round" if A["rotate_every"] == 1
                                 else f"every {A['rotate_every']} rounds")
                             + (", so every student does every job." if every else
                                (f", so jobs change hands {turns} time{'s' if turns != 1 else ''}" if turns else
                                 ": with one round, jobs don't change hands") + "; next time, start the cards with "
                                "different students."))
                            + " No one is always the helper or the helped."
                            + extra])


def _versions_note(A: dict, pages: dict[str, str]) -> str:
    where = []
    for name in A.get("_pdf_versions", []):
        found = [p for key, p in pages.items() if key.startswith(f"{name}:")]
        where.append(f"{name}" + (f" ({', '.join(found)})" if found else ""))
    where += [f"{name} (the Word file {path}: print it from Word or Google Docs)" for name, path in A.get("_word_files", [])]
    if not where:
        return ""
    return ("Versions for the students who need them: " + "; ".join(where) + ". Same parts and jobs, so groups "
            "stay mixed: a student with a version still teaches, listens, and talks with everyone.")


def _counts(A: dict) -> str:
    n = A.get("class_size")
    if not n:
        return ""
    sizes = group_sizes(n, A["group_size"], *group_range(A["kind"], A["group_size"]))
    what = "pairs" if A["kind"] == "pairs" else "groups"
    by = {k: sizes.count(k) for k in sorted(set(sizes), reverse=True)}
    parts = [f"{count} of {k}" for k, count in by.items()]
    out = (f" For {n} students: {len(sizes)} {what[:-1] if len(sizes) == 1 else what}"
           + (f" ({', '.join(parts)})" if len(by) > 1 else f" of {sizes[0]}") + ".")
    if A["kind"] == "jigsaw":
        letters = len(A["parts"])
        if max(sizes) > letters:
            out += f" In a group of {max(sizes)}, two students share a letter."
        if min(sizes) < letters:
            out += (f" A group of {min(sizes)} has no Expert {chr(64 + letters)}: it reads that expert sheet "
                    "together.")
    return out


def _grouping(A: dict) -> str:
    if A["kind"] == "pairs":
        return ("Pair students: ask Claude to pair the class from marked work (by class ID: the stronger half "
                "paired with the other half in order, so partners are close enough to help), or at random.")
    return ("Form groups: ask Claude to group the class from marked work (by class ID, a range of skill in each "
            "group), or at random from your class numbers. Don't say why a group is mixed.")


def _printing(A: dict, pages: dict[str, str]) -> str:
    """What to print, with page numbers (known after a first pass)."""
    at = lambda name: f" ({pages[name]})" if pages.get(name) else ""  # noqa: E731
    kind = A["kind"]
    if kind == "lab":
        each = [f"the role cards{at('Role cards')}", f"the task card{at('Group task')}",
                f"the data{at('Data')}" if A["data"] else "",
                f"the board{'s' if len(A['boards']) > 1 else ''}{at('Board')}" if A["boards"] else ""]
        each = [e for e in each if e]
        sets = A.get("_token_sets", 1)
        tokens = (f" The tokens{at('Tokens')}: one page holds {sets} groups' sets." if A["tokens"] and sets > 1 else
                  f" And per group, the tokens{at('Tokens')}." if A["tokens"] else "")
        return "Per group, print " + ", ".join(each[:-1]) + (" and " if len(each) > 1 else "") + each[-1] + "." + tokens
    if kind == "jigsaw":
        return (f"Print one set of expert cards{at('Role cards')} per home group, and for each student the expert "
                f"sheet for their letter{at('Expert sheets')} and the home-group notes{at('Home group notes')}.")
    if kind == "reciprocal":
        return (f"Print one set of role cards{at('Role cards')} per group, and the reading{at('Reading')} for each "
                "student.")
    if kind == "pairs":
        return (f"Print one set of role cards{at('Role cards')} and one coach-and-player sheet"
                f"{at('Coach and player sheet')} per pair.")
    return (f"Print one set of number cards{at('Number cards')} per group; keep the questions{at('Questions')} "
            "for yourself.")


def _during(A: dict) -> list[str]:
    kind = A["kind"]
    if kind == "lab":
        rounds = f" Do {A['rounds']} rounds." if A["rounds"] > 1 else ""
        asker = "the Reporter" if A["group_size"] >= 4 else "the Facilitator"
        return [f"Groups follow the task card.{rounds} Circulate; answer group questions, from {asker}, only "
                "after the group has tried.", f"Before a group moves on, ask {_checker({**A, 'ui': None})}: “Can everyone explain "
                "it?” Then pick someone else to explain."]
    if kind == "jigsaw":
        home = 4 * len(A["parts"])
        expert = A["minutes"] - home - 5
        if expert < 10:
            A.setdefault("_timing", f"a jigsaw with {len(A['parts'])} parts needs about {home + 15} minutes "
                                    f"(10 in expert groups, {home} in home groups, 5 to wrap up), not {A['minutes']}")
            expert = 10
        return [f"Expert groups of 3-4 (the A's together, splitting a letter into two groups if there are more): "
                f"about {expert} minutes to learn the part and fill the teach box. Check each expert's box before "
                "they leave; fix gaps now, so no home group misses a part.",
                f"Home groups, about {home} minutes: each expert teaches for about 3 minutes and asks their check "
                "question; everyone writes notes on every part.", "Wrap up, then everyone does the worksheet, on "
                "all the parts, alone."]
    if kind == "reciprocal":
        return ["Read in parts. After each part, the jobs speak in order (the reading sheet says who), and the "
                "cards pass left.", "Model one part first with the whole class, doing every job yourself." +
                (" New to the jobs? Teach one a day for a week before groups use all four." if A["grade"] <= 5
                 else "")]
    if kind == "pairs":
        return ["Model the coach's steps with a student first: “Check it,” a hint, then showing how.",
                "Halfway (when you say so), partners switch: the player becomes the coach.",
                "Walk around and listen for coaches saying exactly what was right."]
    return ["Ask a question. Groups put their heads together until everyone can answer.",
            "Roll a die or spin for a number; that student in each group answers. Ask the others to add on."]


def role_cards(pen: Pen, A: dict) -> None:
    """Tent cards, two to a page: fold on the dashed line so the role faces the group and the job faces the
    student holding it."""
    c = pen.c
    roles = A["roles"]
    for start in range(0, len(roles), 2):
        y_top = PAGE_H - MARGIN
        for k, (name, jobs, stems) in enumerate(roles[start:start + 2]):
            top = y_top - k * (PAGE_H - 2 * MARGIN) / 2
            h = (PAGE_H - 2 * MARGIN) / 2 - 10
            x0, x1 = MARGIN, PAGE_W - MARGIN
            mid = top - h / 2
            cut_line(c, x0, top, x1, top)
            cut_line(c, x0, top - h, x1, top - h)
            cut_line(c, x0, top - h, x0, top)
            cut_line(c, x1, top - h, x1, top)
            fold_line(c, x0, mid, x1, mid)
            scissors(c, x0 + 8, top, 10)
            # the outside face, upside down so it reads from across the table once folded
            c.saveState()
            c.translate((x0 + x1) / 2, mid + h / 4)
            c.rotate(180)
            c.setFillGray(INK)
            size = 40.0
            while size > 14 and pen.width(name, pen.f.bold, size) > x1 - x0 - 40:
                size -= 1
            topic = A["parts"][start + k]["title"] if A["kind"] == "jigsaw" and start + k < len(A["parts"]) else ""
            c.setFont(pen.f.bold, size)
            c.drawCentredString(0, -size * 0.35 + (12 if topic else 0), pen.f.text(name))
            if topic:  # so the home group sees who teaches what
                tsize = 16.0
                while tsize > 9 and pen.width(topic, pen.f.regular, tsize) > x1 - x0 - 40:
                    tsize -= 0.5
                c.setFont(pen.f.regular, tsize)
                c.drawCentredString(0, -size * 0.35 - 14, pen.f.text(topic))
            if pen.width(name, pen.f.bold, size) > x1 - x0 - 40 or \
                    (topic and pen.width(topic, pen.f.regular, 9) > x1 - x0 - 40):
                pen.warnings.append(f"the card \"{name[:30]}\" has a name or topic too long for it: shorten it")
            c.restoreState()
            # the inside face: the job and the words to use
            yy = mid - 16
            jw, sx = (x1 - x0) * 0.55 - 24, x0 + (x1 - x0) * 0.58
            room = h / 2 - 50  # below the heading, above the footer line
            size = _size(A, 12.5)
            while size > 9 and max(sum(pen.para_height(f"• {j}", jw, size) + 2 for j in jobs),
                                   sum(pen.para_height(f"“{t}”", x1 - sx - 14, size, pen.f.oblique) + 3
                                       for t in stems)) > room:
                size -= 0.5
            if max(sum(pen.para_height(f"• {j}", jw, size) + 2 for j in jobs),
                   sum(pen.para_height(f"“{t}”", x1 - sx - 14, size, pen.f.oblique) + 3 for t in stems)) > room:
                pen.warnings.append(f"the {name} card's jobs or sentence starters don't fit even at 9pt: shorten them")
            hsize = _size(A, 14)
            heading = _label(A, "your_job", name=name)
            while hsize > 9 and pen.width(heading, pen.f.bold, hsize) > jw + 4:
                hsize -= 0.5
            c.setFont(pen.f.bold, hsize)
            c.drawString(x0 + 14, yy, pen.f.text(heading))
            yy -= 6
            for job in jobs:
                yy = pen.para(f"• {job}", x0 + 18, yy, jw, size) - 2
            yy2 = mid - 16
            c.setFont(pen.f.bold, _size(A, 11))
            c.drawString(sx, yy2, pen.f.text(_label(A, "say_it")))
            yy2 -= 6
            for stem in stems:
                yy2 = pen.para(f"“{stem}”", sx, yy2, x1 - sx - 14, size, pen.f.oblique) - 3
            c.setFillGray(0.25)
            c.setFont(pen.f.regular, _size(A, 9.5))
            more = {"lab": (_label(A, "footer_lab") if A["rotate_every"] == 1 else
                            _label(A, "footer_lab_every", every=A["rotate_every"])),
                    "reciprocal": _label(A, "footer_reciprocal"), "pairs": _label(A, "footer_pairs")}.get(A["kind"], "")
            c.drawString(x0 + 14, top - h + 8, pen.f.text(_label(A, "footer") + (" " + more if more else "")))
            c.setFillGray(INK)
        yield


def task_card(pen: Pen, A: dict) -> None:
    c = pen.c
    y = _header(pen, A, _label(A, "task"))
    if A["goal"]:
        y = pen.para(A["goal"], MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 13), pen.f.bold) - 8
    if A["abilities"]:
        y = pen.para(_label(A, "needs", abilities=", ".join(A["abilities"])), MARGIN, y, PAGE_W - 2 * MARGIN,
                     _size(A, 10.5), pen.f.oblique) - 10
    for n, step in enumerate(A["steps"], start=1):
        step_number(pen, MARGIN + 9, y - 8, n, 8)
        y = pen.para(step, MARGIN + 24, y, PAGE_W - 2 * MARGIN - 24, _size(A, 12)) - 6
    if A["rounds"] > 1:
        c.setFont(pen.f.bold, 11)
        c.drawString(MARGIN, y - 12, pen.f.text(_label(A, "rounds")))
        x = MARGIN + 52
        for r in range(1, A["rounds"] + 1):  # a box to check off for each, wrapping as needed
            if x + 34 > PAGE_W - MARGIN:
                x, y = MARGIN + 52, y - 20
            c.setStrokeGray(0.3)
            c.rect(x, y - 15, 13, 13, stroke=1, fill=0)
            c.setFont(pen.f.regular, 10)
            c.drawString(x + 16, y - 12, str(r))
            x += 34
        y -= 20
        every = A["rotate_every"]
        y = pen.para(_label(A, "check_off") if every == 1 else _label(A, "check_off_every", every=every), MARGIN,
                     y - 2, PAGE_W - 2 * MARGIN, _size(A, 10.5), pen.f.oblique) - 6
    dice = A["dice"]
    if dice:
        c.setFont(pen.f.bold, 12)
        c.drawString(MARGIN, y - 12, pen.f.text(dice.get("title") or _label(A, "roll")))
        y -= 20
        col = min(160.0, max([70.0] + [pen.width(str(r[0]), pen.f.bold, 12) + 16 for r in dice["rows"]]))
        for roll, what in dice["rows"]:
            c.setStrokeGray(0.6)
            c.setLineWidth(0.6)
            h = max(20.0, pen.para_height(str(what), PAGE_W - 2 * MARGIN - col - 16, _size(A, 11)) + 8)
            c.rect(MARGIN, y - h, PAGE_W - 2 * MARGIN, h, stroke=1, fill=0)
            c.line(MARGIN + col, y - h, MARGIN + col, y)
            c.setFont(pen.f.bold, 12)
            c.drawCentredString(MARGIN + col / 2, y - h / 2 - 4, pen.f.text(str(roll)))
            pen.para(str(what), MARGIN + col + 8, y - 4, PAGE_W - 2 * MARGIN - col - 16, _size(A, 11))
            y -= h
        y -= 10
    table = A.get("table")
    if table:  # the Recorder's data table, blank
        c.setFont(pen.f.bold, 12)
        c.drawString(MARGIN, y - 12, pen.f.text(table.get("title") or _label(A, "our_data")))
        y -= 18
        cols = table["columns"]
        weights = [max(len(str(col)), 8) for col in cols]
        widths = [(PAGE_W - 2 * MARGIN) * wt / sum(weights) for wt in weights]
        edges = [MARGIN + sum(widths[:k]) for k in range(len(cols) + 1)]
        head = max(pen.para_height(col, w - 8, 10, pen.f.bold) for col, w in zip(cols, widths)) + 8
        row_h = 22.0
        rows = max(1, min(int(table["rows"]), int((y - head - 72) // row_h)))  # room left for the closing line
        if rows < int(table["rows"]):
            pen.warnings.append(f"the Recorder's table has room for {rows} rows, not {table['rows']}: cut steps or "
                                "dice rows, ask for fewer rows, or use a \"data\" table with blank cells (it runs onto "
                                "more pages)")
        c.setStrokeGray(0.4)
        c.setLineWidth(0.7)
        c.setFillGray(0.9)
        c.rect(MARGIN, y - head, PAGE_W - 2 * MARGIN, head, stroke=1, fill=1)
        c.setFillGray(INK)
        for k, col in enumerate(cols):
            pen.box(col, edges[k] + 4, y - head + 2, edges[k + 1] - 4, y - 2, font=pen.f.bold, start=10)
        for r in range(rows):
            c.rect(MARGIN, y - head - (r + 1) * row_h, PAGE_W - 2 * MARGIN, row_h, stroke=1, fill=0)
        for k in range(1, len(cols)):
            c.line(edges[k], y, edges[k], y - head - rows * row_h)
        y -= head + rows * row_h + 10
    if y < 56:
        pen.warnings.append("the group task card runs off the page: shorten the steps or the dice rows, or use fewer "
                            "table rows")
    c.setFillGray(0.35)
    pen.para(_label(A, "close", checker=_checker(A)), MARGIN, max(y, 56), PAGE_W - 2 * MARGIN, 10, pen.f.oblique,
             gray=0.35)
    c.setFillGray(INK)


def data_pages(pen: Pen, A: dict):
    """Printed data for the group to use: tables, filled in."""
    c = pen.c
    y = _header(pen, A, "Data")
    width = PAGE_W - 2 * MARGIN
    for d in A["data"]:
        cols = d["columns"]
        weights = [min(30, max([len(str(col)), 6] + [len(str(r[k])) for r in d["rows"]])) for k, col in enumerate(cols)]
        widths = [width * w / sum(weights) for w in weights]
        edges = [MARGIN + sum(widths[:k]) for k in range(len(cols) + 1)]
        size = _size(A, 11)
        head = max(pen.para_height(str(col), w - 8, size, pen.f.bold) for col, w in zip(cols, widths)) + 8
        title_h = pen.para_height(d.get("title", ""), width, 11, pen.f.bold) + 6 if d.get("title") else 0
        if y - title_h - head - 3 * 20 < MARGIN + 10:
            yield
            y = _header(pen, A, "Data")
        if d.get("title"):
            y = pen.para(d["title"], MARGIN, y, width, 11, pen.f.bold) - 6
        c.setStrokeGray(0.4)
        c.setLineWidth(0.7)
        c.setFillGray(0.9)
        c.rect(MARGIN, y - head, width, head, stroke=1, fill=1)
        c.setFillGray(INK)
        for k, col in enumerate(cols):
            pen.box(str(col), edges[k] + 4, y - head + 2, edges[k + 1] - 4, y - 2, font=pen.f.bold, start=size)
        y -= head
        blank_rows = any(cell == "" for r in d["rows"] for cell in r)
        for row in d["rows"]:
            h = max(pen.para_height(str(cell), w - 8, size) for cell, w in zip(row, widths)) + 8
            if blank_rows:
                h = max(h, 26.0)  # room for handwriting in the blank cells
            if y - h < MARGIN + 10:  # the rest of the table on the next page, under its headings again
                yield
                y = _header(pen, A, "Data (continued)")
                c.setFillGray(0.9)
                c.rect(MARGIN, y - head, width, head, stroke=1, fill=1)
                c.setFillGray(INK)
                for k, col in enumerate(cols):
                    pen.box(str(col), edges[k] + 4, y - head + 2, edges[k + 1] - 4, y - 2, font=pen.f.bold, start=size)
                y -= head
            c.setStrokeGray(0.4)
            c.rect(MARGIN, y - h, width, h, stroke=1, fill=0)
            for k, cell in enumerate(row):
                if k:
                    c.line(edges[k], y, edges[k], y - h)
                pen.para(str(cell), edges[k] + 4, y - 4, widths[k] - 8, size)
            y -= h
        y -= 16
    yield


def board_pages(pen: Pen, A: dict):
    for b in A["boards"]:
        yield from board_page(pen, A, b)


def board_page(pen: Pen, A: dict, b: dict):
    """One printed board: a grid, a number line, labeled layers, a ring of stations, graph axes, or a diagram."""
    c = pen.c
    y = _header(pen, A, b.get("title") or "Board")
    left, right, bottom = MARGIN, PAGE_W - MARGIN, MARGIN + 10
    width, height = right - left, y - 8 - bottom
    c.setStrokeGray(0.3)
    c.setFillGray(INK)
    kind = b["kind"]
    if kind == "grid":
        cols, rows = int(b["cols"]), int(b["rows"])
        side = min(width / cols, height / rows)
        x0, top = left + (width - side * cols) / 2, y - 8
        c.setLineWidth(0.6)
        for k in range(cols + 1):
            c.line(x0 + k * side, top, x0 + k * side, top - rows * side)
        for k in range(rows + 1):
            c.line(x0, top - k * side, x0 + cols * side, top - k * side)
    elif kind == "number_line":
        from fractions import Fraction
        low, high, parts = int(b["min"]), int(b["max"]), int(b["parts"])
        units = high - low
        gap = min(260.0, height / units)
        for u in range(units):
            ly = y - 8 - gap * (u + 0.6)
            x0, x1 = left + 14, right - 14
            c.setLineWidth(1.4)
            c.line(x0, ly, x1, ly)
            for t in range(parts + 1):
                denominator = Fraction(t, parts).denominator  # simpler fractions get taller marks
                tick = 16 if denominator == 1 else 11 if denominator == 2 else 8 if denominator <= 4 else 5
                x = x0 + (x1 - x0) * t / parts
                c.setLineWidth(1.2 if denominator == 1 else 0.7)
                c.line(x, ly - tick / 2, x, ly + tick / 2)
            c.setFont(pen.f.bold, _size(A, 14))
            c.drawCentredString(x0, ly - 26, str(low + u))
            c.drawCentredString(x1, ly - 26, str(low + u + 1))
    elif kind == "rows":
        names = b["rows"]
        band = height / len(names)
        for k, name in enumerate(names):
            top = y - 8 - k * band
            c.setFillGray(0.95 if k % 2 else 1)
            c.rect(left, top - band, width, band, stroke=1, fill=1)
            c.setFillGray(INK)
            c.setFont(pen.f.bold, _size(A, 14))
            c.drawString(left + 10, top - 22, pen.f.text(name))
    elif kind == "ring":
        import math
        names = b["stations"]
        cx, cy = PAGE_W / 2, y - 8 - height / 2
        radius = min(width, height) / 2 - 60
        bw, bh = 130.0, 60.0
        c.setLineWidth(0.8)
        c.setDash(4, 3)
        c.circle(cx, cy, radius, stroke=1, fill=0)
        c.setDash()
        for k, name in enumerate(names):
            angle = math.pi / 2 - 2 * math.pi * k / len(names)
            bx, by = cx + radius * math.cos(angle) - bw / 2, cy + radius * math.sin(angle) - bh / 2
            c.setFillGray(1)
            c.rect(bx, by, bw, bh, stroke=1, fill=1)
            c.setFillGray(INK)
            pen.box(name, bx + 6, by + 4, bx + bw - 6, by + bh - 4, font=pen.f.bold, start=_size(A, 14))
    elif kind == "diagram":
        scale = min(width / b["width"], height / b["height"])
        c.saveState()
        c.translate(left + (width - b["width"] * scale) / 2, y - 8 - b["height"] * scale)
        c.scale(scale, scale)
        D.draw_diagram(c, b, 0, 0, pen.f, A.get("_base") or Path("."))
        c.restoreState()
    else:  # graph axes, with gridlines; "y_down" counts down from the top (depth)
        x0, x1 = left + 50, right - 10
        top, base = y - (40 if b.get("y_down") else 14), bottom + (10 if b.get("y_down") else 36)
        xs = [b["xmin"] + k * b["xstep"] for k in range(int(round((b["xmax"] - b["xmin"]) / b["xstep"])) + 1)]
        ys = [b["ymin"] + k * b["ystep"] for k in range(int(round((b["ymax"] - b["ymin"]) / b["ystep"])) + 1)]
        fmt = lambda v: f"{v:g}"  # noqa: E731
        c.setFont(pen.f.regular, 9)
        for v in xs:
            x = x0 + (x1 - x0) * (v - b["xmin"]) / (b["xmax"] - b["xmin"])
            c.setStrokeGray(0.75)
            c.setLineWidth(0.5)
            c.line(x, base, x, top)
            c.drawCentredString(x, base - 12, fmt(v)) if not b.get("y_down") else c.drawCentredString(x, top + 4, fmt(v))
        for v in ys:
            frac = (v - b["ymin"]) / (b["ymax"] - b["ymin"])
            yy = top - frac * (top - base) if b.get("y_down") else base + frac * (top - base)
            c.setStrokeGray(0.75)
            c.line(x0, yy, x1, yy)
            c.drawRightString(x0 - 4, yy - 3, fmt(v))
        c.setStrokeGray(INK)
        c.setLineWidth(1.2)
        c.line(x0, base, x0, top)
        c.line(x0, top if b.get("y_down") else base, x1, top if b.get("y_down") else base)
        c.setFont(pen.f.bold, 10)
        if b.get("xlabel"):
            c.drawCentredString((x0 + x1) / 2, (top + 16) if b.get("y_down") else base - 26, pen.f.text(b["xlabel"]))
        if b.get("ylabel"):
            c.saveState()
            c.translate(left + 10, (top + base) / 2)
            c.rotate(90)
            c.drawCentredString(0, 0, pen.f.text(b["ylabel"]))
            c.restoreState()
    yield


def _token_set_height(A: dict) -> float:
    width = PAGE_W - 2 * MARGIN
    h = 0.0
    for token in A["tokens"]:
        side = float(token.get("size", 0.75)) * 72
        cols = max(1, int(width // side))
        h += -(-token["count"] // cols) * side + 6
    return h


def tokens_page(pen: Pen, A: dict):
    """Cut-out tokens, in patterns that stay distinct on a black-and-white copy. Each kind starts a new row, at
    its own size. When a group's set is small, several sets share a page, split by a cut line."""
    c = pen.c
    set_h = _token_set_height(A) + 14
    sets = max(1, int((PAGE_H - 2 * MARGIN - 40) // set_h))
    A["_token_sets"] = sets
    if sets > 1:
        y = _header(pen, A, f"Tokens: {sets} groups' sets on this page")
        for k in range(sets):
            if k:
                cut_line(c, MARGIN, y - 4, PAGE_W - MARGIN, y - 4)
                y -= 12
            y = _token_set(pen, A, y)
        yield
        return
    yield from _token_pages(pen, A)


def _token_set(pen: Pen, A: dict, y: float) -> float:
    """One group's tokens from y down (they fit on the page); returns the y below."""
    c = pen.c
    width = PAGE_W - 2 * MARGIN
    for token in A["tokens"]:
        side = float(token.get("size", 0.75)) * 72
        cols = max(1, int(width // side))
        for k in range(token["count"]):
            col = k % cols
            if col == 0:
                y -= side if k else 6
            _token(pen, token, MARGIN + col * side, y, side, k)
        y -= side
    return y


def _token(pen: Pen, token: dict, x0: float, y: float, side: float, k: int) -> None:
    c = pen.c
    c.setStrokeGray(0.3)
    c.setLineWidth(0.6)
    c.rect(x0, y - side, side, side, stroke=1, fill=0)
    _pattern(c, token.get("pattern", "plain"), x0 + 6, y - side + 6, side - 12)
    label = token["label"]
    size = min(9 + (side - 54) / 8, 18)
    if pen.width(label, pen.f.bold, size) > side - 8:
        size = max(6.0, size * (side - 8) / pen.width(label, pen.f.bold, size))
        if pen.width(label, pen.f.bold, size) > side - 4 and k == 0:
            pen.warnings.append(f"the token label \"{label}\" is too long for its size: shorten it or make the token "
                                "bigger")
    c.setFillGray(1)
    c.rect(x0 + 3, y - side / 2 - size * 0.7, side - 6, size * 1.35, stroke=0, fill=1)
    c.setFillGray(INK)
    c.setFont(pen.f.bold, size)
    c.drawCentredString(x0 + side / 2, y - side / 2 - size * 0.33, pen.f.text(label))


def _token_pages(pen: Pen, A: dict):
    """One group's tokens across as many pages as they need."""
    c = pen.c
    y = _header(pen, A, "Tokens for one group")
    width = PAGE_W - 2 * MARGIN
    for token in A["tokens"]:
        side = float(token.get("size", 0.75)) * 72
        cols = max(1, int(width // side))
        for k in range(token["count"]):
            col = k % cols
            if col == 0:
                if k or y < PAGE_H - MARGIN - 30:
                    y -= side if k else 6  # the next row, or a gap before a new kind
                if y - side < MARGIN:
                    yield
                    y = _header(pen, A, "Tokens for one group")
            _token(pen, token, MARGIN + col * side, y, side, k)
        y -= side
    yield


def _pattern(c, pattern: str, x: float, y: float, s: float) -> None:
    c.saveState()
    p = c.beginPath()
    p.rect(x, y, s, s)
    c.clipPath(p, stroke=0, fill=0)
    c.setStrokeGray(0.35)
    c.setFillGray(0.35)
    c.setLineWidth(0.8)
    if pattern == "solid":
        c.setFillGray(0.55)
        c.rect(x, y, s, s, stroke=0, fill=1)
    elif pattern == "stripes":
        for k in range(-int(s), int(s), 6):
            c.line(x + k, y, x + k + s, y + s)
    elif pattern == "dots":
        for i in range(4):
            for j in range(4):
                c.circle(x + 5 + i * (s - 10) / 3, y + 5 + j * (s - 10) / 3, 2, stroke=0, fill=1)
    elif pattern == "checks":
        step = s / 4
        for i in range(4):
            for j in range(4):
                if (i + j) % 2 == 0:
                    c.rect(x + i * step, y + j * step, step, step, stroke=0, fill=1)
    elif pattern == "rings":
        for r in (s * 0.15, s * 0.3, s * 0.45):
            c.circle(x + s / 2, y + s / 2, r, stroke=1, fill=0)
    c.restoreState()


def _part_extras(pen: Pen, A: dict, part: dict, y: float, width: float) -> float:
    """Under a part's text: a primary source set apart, the key words, and the credit line."""
    c = pen.c
    if part.get("quote"):
        top = y
        y = pen.para(f"“{part['quote']}”", MARGIN + 18, y - 2, width - 30, _size(A, 11), pen.f.oblique) - 2
        if part.get("quote_source"):
            y = pen.para(f"— {part['quote_source']}", MARGIN + 18, y, width - 30, 9, gray=0.3) - 2
        c.setStrokeGray(0.4)
        c.setLineWidth(2)
        c.line(MARGIN + 6, top - 2, MARGIN + 6, y + 2)
        c.setLineWidth(1)
        y -= 6
    if part.get("words"):
        y = pen.para(_label(A, "key_words") + "; ".join(f"{w['word']}: {w['means']}" for w in part["words"]), MARGIN, y,
                     width, _size(A, 10)) - 6
    if part.get("source"):
        y = pen.para(part["source"], MARGIN, y, width, 8, pen.f.oblique, gray=0.35) - 6
    return y


def _extras_height(pen: Pen, A: dict, part: dict, width: float) -> float:
    h = 0.0
    if part.get("quote"):
        h += pen.para_height(f"“{part['quote']}”", width - 30, _size(A, 11), pen.f.oblique) + 10
        if part.get("quote_source"):
            h += pen.para_height(part["quote_source"], width - 30, 9) + 2
    if part.get("words"):
        h += pen.para_height(_label(A, "key_words") + "; ".join(f"{w['word']}: {w['means']}" for w in part["words"]),
                             width,
                             _size(A, 10)) + 6
    if part.get("source"):
        h += pen.para_height(part["source"], width, 8, pen.f.oblique) + 6
    return h


def expert_sheets(pen: Pen, A: dict):
    """Jigsaw: one sheet per part, then the home group's note sheet."""
    c = pen.c
    for k, part in enumerate(A["parts"]):
        letter = chr(65 + k)
        y = _header(pen, A, f"{_label(A, 'expert', letter=letter)}: {part['title']}")
        y = pen.para(_label(A, "intro"), MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 10.5), pen.f.oblique) - 10
        words = len(str(part["text"]).split()) + len(str(part.get("quote", "")).split())
        if words > 220:
            pen.warnings.append(f"part {letter} has {words} words: about 150-200 fit beside the teach box; shorten it")
        y = pen.para(part["text"], MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 11.5)) - 6
        y = _part_extras(pen, A, part, y, PAGE_W - 2 * MARGIN)
        if part.get("teach"):
            y = pen.para(_label(A, "make_sure") + "; ".join(part["teach"]), MARGIN, y, PAGE_W - 2 * MARGIN,
                         _size(A, 10.5), pen.f.bold) - 8
        if y < 250:
            pen.warnings.append(f"expert sheet {letter} leaves too little room for the teach box: shorten part "
                                f"{letter}'s text (about 150 words fits)")
        c.setFillGray(INK)
        c.setFont(pen.f.bold, 12)
        c.drawString(MARGIN, y - 12, pen.f.text(_label(A, "teach_box")))
        c.setFont(pen.f.regular, 9.5)
        c.drawRightString(PAGE_W - MARGIN - 20, y - 11, pen.f.text(_label(A, "teacher_checked")))
        c.setStrokeGray(0.3)
        c.rect(PAGE_W - MARGIN - 14, y - 14, 12, 12, stroke=1, fill=0)
        y -= 20
        prompts = [_label(A, "ideas"), "1.", "2.", "3.", _label(A, "example")]
        for item in prompts:
            if y < 70:
                break
            c.setStrokeGray(0.75)
            c.line(MARGIN, y - 22, PAGE_W - MARGIN, y - 22)
            c.setFillGray(INK)
            c.setFont(pen.f.regular, 10.5)
            c.drawString(MARGIN, y - 16, pen.f.text(item))
            y -= 26
        if part.get("check") and y > 90:
            y = pen.para(_label(A, "check") + part["check"], MARGIN, y - 6, PAGE_W - 2 * MARGIN,
                         10.5) - 4
            c.setStrokeGray(0.75)
            c.line(MARGIN, y - 20, PAGE_W - MARGIN, y - 20)
            c.setFillGray(INK)
            c.setFont(pen.f.regular, 10.5)
            c.drawString(MARGIN, y - 14, pen.f.text(_label(A, "answer")))
            y -= 26
        if y <= 170:
            pen.warnings.append(f"expert sheet {letter} has no room for the sketch box: shorten part {letter}")
        if y > 170:  # a sketch is a second way in, for the teacher and for the group
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 10.5)
            c.drawString(MARGIN, y - 14, pen.f.text(_label(A, "picture")))
            c.setStrokeGray(0.6)
            c.rect(MARGIN, 64, PAGE_W - 2 * MARGIN, y - 24 - 64)
        yield


def home_notes(pen: Pen, A: dict):
    """Jigsaw: one sheet per student, with room for every part (Jigsaw II: everyone learns every part)."""
    c = pen.c
    y = _header(pen, A, "Home group notes")
    y = pen.para("As each expert teaches, write the big idea in your own words (not copied from their sheet), and "
                 "answer their check question.", MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 10.5), pen.f.oblique) - 8
    boxes = [f"{chr(65 + k)}: {part['title']}" for k, part in enumerate(A["parts"])] + ["How the parts connect"]
    h = (y - 60) / (len(boxes) - 0.4)  # the last box is a little smaller
    for k, head in enumerate(boxes):
        top = y - k * h
        bh = h * (0.6 if k == len(boxes) - 1 else 1) - 6
        c.setStrokeGray(0.5)
        c.setLineWidth(0.8)
        c.rect(MARGIN, top - bh, PAGE_W - 2 * MARGIN, bh, stroke=1, fill=0)
        c.setFillGray(INK)
        c.setFont(pen.f.bold, 11)
        c.drawString(MARGIN + 8, top - 16, pen.f.text(head))
        c.setStrokeGray(0.82)
        ln = top - 22 - 22
        while ln > top - bh + 8:  # ruled lines, none on the border
            c.line(MARGIN + 8, ln, PAGE_W - MARGIN - 8, ln)
            ln -= 22
    yield


def pair_sheet(pen: Pen, A: dict):
    """Coach and player: questions on the left, answers on the right; fold on the line so the player sees
    only the questions."""
    c = pen.c
    cards = A["cards"]
    per = 12
    for start in range(0, len(cards), per):
        y = _header(pen, A, "Coach and player")
        pen.para("Fold on the dashed line so the player sees the questions and the coach sees the answers. Switch "
                 "jobs halfway.", MARGIN, y, PAGE_W - 2 * MARGIN, 10, pen.f.oblique, gray=0.35)
        y -= 26
        mid = PAGE_W / 2
        bottom = MARGIN + 10  # clear of the page label
        fold_line(c, mid, bottom, mid, y + 4)
        h = (y - bottom) / per
        for k, card in enumerate(cards[start:start + per]):
            top = y - k * h
            if start + k == len(cards) // 2 and start + k:  # PALS: the player becomes the coach
                c.setStrokeGray(INK)
                c.setLineWidth(1.6)
                c.line(MARGIN, top, PAGE_W - MARGIN, top)
                c.setLineWidth(1)
                c.setFillGray(1)
                c.rect(PAGE_W / 2 - 130, top + 1, 260, 13, stroke=0, fill=1)
                c.setFillGray(INK)
                c.setFont(pen.f.bold, 10)
                c.drawCentredString(PAGE_W / 2, top + 4, "Switch jobs here: turn the folded sheet around")
            c.setStrokeGray(0.82)
            c.line(MARGIN, top - h, PAGE_W - MARGIN, top - h)
            c.setFont(pen.f.bold, 10)
            c.drawString(MARGIN, top - 13, f"{start + k + 1}.")
            pen.box(card["q"], MARGIN + 18, top - h + 3, mid - 10, top - 3, start=_size(A, 16), align="left",
                    valign="top", where=f"card {start + k + 1}")
            pen.box(card["a"], mid + 10, top - h + 3, PAGE_W - MARGIN, top - 3, start=_size(A, 13), align="left",
                    valign="top", gray=0.25, where=f"card {start + k + 1}'s answer")
        yield


def questions_page(pen: Pen, A: dict):
    y = _header(pen, A, "Questions to ask (teacher)")
    for k, card in enumerate(A["cards"], start=1):
        need = pen.para_height(f"{k}. {card['q']}", PAGE_W - 2 * MARGIN, 11) \
            + pen.para_height(f"Answer: {card['a']}", PAGE_W - 2 * MARGIN - 16, 10) + 8
        if y - need < 60:
            yield
            y = _header(pen, A, "Questions to ask (teacher)")
        y = pen.para(f"{k}. {card['q']}", MARGIN, y, PAGE_W - 2 * MARGIN, 11) - 1
        y = pen.para(f"Answer: {card['a']}", MARGIN + 16, y, PAGE_W - 2 * MARGIN - 16, 10, gray=0.35) - 6
    yield


def reading_sheets(pen: Pen, A: dict):
    """Reciprocal teaching: the reading in chunks, with a stop after each where every role speaks."""
    c = pen.c
    names = [r[0] for r in A["roles"]]
    size = _size(A, 11.5)
    width = min(PAGE_W - 2 * MARGIN, size * 36)  # about 70 letters a line, easier to track
    y = _header(pen, A, _label(A, "read_together"))
    y = pen.para(_label(A, "read_intro", last=names[-1]), MARGIN, y, width, _size(A, 10.5)) - 10
    for k, part in enumerate(A["parts"], start=1):
        need = pen.para_height(part["text"], width, size) + _extras_height(pen, A, part, width) \
            + (24 if part.get("title") else 6) + 40
        if need > PAGE_H - 2 * MARGIN - 70:
            pen.warnings.append(f"part {k} is longer than a page: split it into two parts")
        if y - need < 60 and y < PAGE_H - MARGIN - 40:
            yield
            y = _header(pen, A, _label(A, "read_together"))
        if part.get("title"):
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 12)
            c.drawString(MARGIN, y - 12, pen.f.text(f"Part {k}: {part['title']}"))
            y -= 18
        y = pen.para(part["text"], MARGIN, y, width, size) - 4
        y = _part_extras(pen, A, part, y, width) + 2
        last = k == len(A["parts"])
        if not last:
            stop = _label(A, "stop", order=", ".join(names))
        else:  # nothing left to predict: the last job sits out
            stop = _label(A, "last_stop", order=", ".join(names[:-1] or names))
        stop_size = _size(A, 10.5)
        h = pen.para_height(stop, width - 16, stop_size, pen.f.bold) + 8
        c.setFillGray(0.92)
        c.rect(MARGIN, y - h - 2, width, h, stroke=0, fill=1)
        c.setFillGray(INK)
        pen.para(stop, MARGIN + 8, y - 5, width - 16, stop_size, pen.f.bold)
        y -= h + 12
    yield


def _shaped(text: str) -> bool:
    """Right-to-left, Indic, Myanmar, or Ethiopic: scripts these pages can't shape."""
    return any("\u0590" <= ch <= "\u08ff" or "\ufb1d" <= ch <= "\ufeff" or "\u0900" <= ch <= "\u0dff"
               or "\u1000" <= ch <= "\u109f" or "\u1200" <= ch <= "\u139f" for ch in text)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def build(json_path: Path, out_dir: Path) -> dict:
    """Writes out_dir/teamwork.pdf: the teacher's page, role cards, the task, and anything to cut out."""
    json_path, out_dir = Path(json_path), Path(out_dir)
    try:
        data = S.read_json(json_path)
    except ValueError as e:
        raise TeamworkError(f"{json_path.name} isn't valid JSON: {e}") from None
    A = normalize(data)
    A["_base"] = json_path.parent
    texts = list(_strings({k: v for k, v in data.items() if k != "versions"}))
    on_pdf, on_word = [], []
    for V in A["versions"]:
        vtexts = list(_strings([V["parts"], V["roles"], V["steps"], V["goal"]]))
        needs_word = any(_shaped(t) for t in vtexts) or not F.choose(vtexts)[1] or \
            any("\u2e80" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for t in vtexts for ch in t)
        (on_word if needs_word else on_pdf).append(V)
    fonts, prints = F.choose(texts + [t for V in on_pdf for t in _strings([V["parts"], V["roles"], V["steps"],
                                                                          V["goal"]])])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "teamwork.pdf"
    worksheet = A.get("worksheet")
    sheet_json = json_path.parent / f"{worksheet}.json" if worksheet else None
    has_versions = bool(sheet_json and sheet_json.exists() and S.read_json(sheet_json).get("versions"))
    note = (f"Print the worksheet each student does alone at the end ({worksheet}), one per student"
            + (", with its versions for the students who need them: all forms are scanned together and marked like any "
               "worksheet." if has_versions else ": it's scanned and marked like any worksheet.")
            if worksheet else
            "Add a short worksheet each student does alone at the end: group work pays off only when each student "
            "is accountable on their own.")
    checks: list[str] = []
    if not worksheet:
        checks.append("no \"worksheet\": add the individual worksheet each student hands in (an exit sheet "
                      "Paper Loop marks), so the group's work is also each student's")
    elif not any((json_path.parent / name).exists() for name in (f"{worksheet}.json", f"{worksheet}/key.json")):
        checks.append(f"no worksheet {worksheet!r} beside {json_path.name}: make it with `make` (or fix the id)")
    if not prints:
        checks.append(f"these characters will print as boxes: {F.unprintable(texts)}. Put home-language words on the "
                      "exit sheet's version instead (worksheets print every supported language)")
    if any(_shaped(t) for t in texts):
        checks.append("group pages can't shape right-to-left or Indic scripts (they'd print reversed or broken): put "
                      "those words in a \"versions\" entry (it goes in a Word file, which shapes every script)")
    reading = " ".join(str(part.get("text", "")) for part in A["parts"] if isinstance(part, dict))
    level = SRC.reading_grade(reading) if reading else None
    if level is not None and A["grade"] >= 3 and level > A["grade"] + 2:
        checks.append(f"the reading scores about grade {level:g} (Flesch-Kincaid) for grade {A['grade']}: "
                      "simplify it, unless that's intended")
    for V in A["versions"]:
        if V["language"] and V["quality"] in ("medium", "low", "unknown") and not V["reviewed_by"]:
            checks.append(f"Claude's {V['english_name']} isn't reliable enough to print unchecked: have a bilingual adult "
                          f"read version {V['id']!r}, then add \"reviewed_by\" (a role, not a name)")
        if not V["language"] and V["parts"] is not A["parts"]:
            plain = SRC.reading_grade(" ".join(p["text"] for p in V["parts"]))
            if plain is not None and level is not None and plain >= level:
                checks.append(f"version {V['id']!r} reads at about grade {plain:g}, no easier than the original "
                              f"({level:g}): use shorter sentences and everyday words")
    word_files = []
    for V in on_word:
        (out_dir / "versions").mkdir(parents=True, exist_ok=True)
        word_files.append((V, _version_word(A, V, out_dir / "versions" / f"{V['id']}.docx")))
    A["_word_files"] = [(V["name"], f"versions/{V['id']}.docx") for V, _ in word_files]
    A["_pdf_versions"] = [V["name"] for V in on_pdf]

    def render(target, page_of: dict[str, str]) -> tuple[list, list[str]]:
        c = canvas.Canvas(target, pagesize=(PAGE_W, PAGE_H))
        c.setTitle(fonts.text(f"{A['title']}: group work"))
        c.setAuthor("Paper Loop")
        warnings: list[str] = list(checks)
        pen = Pen(c, fonts, A["grade"], warnings)
        sections = [("Teacher's page", lambda: iter([teacher_page(pen, A, note, page_of)]))]
        sections.append(("Number cards" if A["kind"] == "heads" else "Role cards", lambda: role_cards(pen, A)))
        if A["kind"] == "lab":
            sections.append(("Group task", lambda: iter([task_card(pen, A)])))
            if A["data"]:
                sections.append(("Data", lambda: data_pages(pen, A)))
            if A["boards"]:
                sections.append(("Board", lambda: board_pages(pen, A)))
            if A["tokens"]:
                sections.append(("Tokens", lambda: tokens_page(pen, A)))
        elif A["kind"] == "jigsaw":
            sections.append(("Expert sheets", lambda: expert_sheets(pen, A)))
            sections.append(("Home group notes", lambda: home_notes(pen, A)))
        elif A["kind"] == "pairs":
            sections.append(("Coach and player sheet", lambda: pair_sheet(pen, A)))
        elif A["kind"] == "heads":
            sections.append(("Questions", lambda: questions_page(pen, A)))
        elif A["kind"] == "reciprocal":
            sections.append(("Reading", lambda: reading_sheets(pen, A)))
        for V in on_pdf:  # each version's own pages, after everyone's
            AV = _version_activity(A, V)
            if V["roles"]:
                sections.append((f"{V['name']}: role cards", lambda AV=AV: role_cards(pen, AV)))
            if A["kind"] == "lab" and (V["steps"] is not A["steps"] or V["goal"] != A["goal"]):
                sections.append((f"{V['name']}: group task", lambda AV=AV: iter([task_card(pen, AV)])))
            if A["kind"] == "jigsaw" and V["parts"] is not A["parts"]:
                sections.append((f"{V['name']}: expert sheets", lambda AV=AV: expert_sheets(pen, AV)))
            if A["kind"] == "reciprocal" and V["parts"] is not A["parts"]:
                sections.append((f"{V['name']}: reading", lambda AV=AV: reading_sheets(pen, AV)))
        pages = []
        for name, make in sections:
            first = pen.page + 1
            for _ in make():
                pen.page += 1
                pen.footer(A["title"])
                c.showPage()
            pages.append((name, first, pen.page))
        c.save()
        return pages, list(dict.fromkeys(warnings))

    pages, _ = render(io.BytesIO(), {})
    if A.get("_timing"):
        checks.append(A["_timing"])
    page_of = {name: f"page {a}" if a == b else f"pages {a}-{b}" for name, a, b in pages}
    pages, warnings = render(str(path), page_of)
    return {"pdf": path, "pages": pages, "warnings": warnings, "structure": STRUCTURES[A["kind"]][0],
            "group_size": A["group_size"], "word_files": [str(p) for _, p in word_files]}


# --- Mixed-skill groups from a class's marked work ------------------------------------------------------

def group_range(structure: str, size: int) -> tuple[int, int]:
    """The smallest and largest group that still works: a pair may be a trio, a jigsaw group has every letter
    (and at most one shared), and four reading jobs stretch over 3-5 students."""
    if structure == "pairs":
        return 2, 3
    if structure == "jigsaw":
        return size, size + 1
    if structure == "reciprocal":
        return 3, 5
    if structure == "game":  # never more players than the game takes; an odd one out joins a pair
        return (2, 3) if size == 2 else (max(2, size - 1), size)
    return SIZES[structure]


def group_sizes(n: int, size: int, low: int, high: int) -> list[int]:
    """n students in groups as close to `size` as the range allows, the sizes differing by one at most."""
    if n <= high:
        return [n]
    groups = max(1, round(n / size))
    while -(-n // groups) > high:
        groups += 1
    while groups > 1 and n // groups < low and -(-n // (groups - 1)) <= high:
        groups -= 1
    base, extra = divmod(n, groups)
    return [base + 1] * extra + [base] * (groups - extra)


def role_names(structure: str, n: int, size: int) -> list[str]:
    """The first-round job for each of n students in a group meant for size: extras double up on a printed job."""
    if structure == "jigsaw":
        return [f"Expert {chr(65 + k % size)}" for k in range(n)]  # a fifth student shares a letter
    if structure == "heads":
        return [f"Number {k % size + 1}" for k in range(n)]
    if structure == "game":
        return [""] * n
    names = [r[0] for r in ROLES.get(structure, ROLES["lab"])]
    if structure == "pairs":
        return [names[0]] + [names[1]] * (n - 1)  # a trio: the players take turns
    names = names[:size] if structure == "lab" else names
    return [names[k % len(names)] for k in range(n)]


def form_groups(folder: Path, size: int | None = None, skill: str | None = None, roster_path: Path | None = None,
                structure: str = "lab", seed: int = 1, out: Path | None = None, similar: bool = False) -> dict:
    """Groups of `size`, from students sorted by their latest score (on one skill, or across all):
    - mixed (the default, for labs and other group work): dealt out back and forth, so every group gets some
      from each part of the range. Students who are behind learn more in mixed groups (Lou et al. 1996).
    - pairs: the PALS way. The ranked class is split in half and the two halves pair up in order (1st with the
      first of the lower half), so partners are apart but close enough to help.
    - similar (for practicing one skill): neighbors in the ranking together, so the teacher can give each
      group what it needs next.
    The first round's jobs are dealt at random, not by score, and the cards rotate after that."""
    from . import prepare as P
    from . import progress as PG
    if structure not in STRUCTURES and structure != "game":
        raise TeamworkError(f"\"structure\" is one of {', '.join(STRUCTURES)}, or game (groups with no jobs)")
    size = (2 if structure == "pairs" else 4) if size is None else size
    low, high = SIZES.get(structure, (2, 6))
    if not low <= size <= high:
        raise TeamworkError(f"a {STRUCTURES.get(structure, ('game',))[0].lower()} works with groups of {low}"
                            + (f" to {high}" if high != low else "") + f", not {size}")
    folder = Path(folder)
    if not folder.is_dir():
        raise TeamworkError(f"no folder {folder}: give the class's folder (where its worksheets are)")
    roster = P.load_roster(roster_path) if roster_path else None
    if roster_path and not roster:
        raise TeamworkError(f"{roster_path} has no class ID numbers: one ID a line, or an \"id\" column")
    runs = PG.collect(folder, roster)
    rng = random.Random(seed)
    unplaced: list[str] = []
    if runs:
        data = PG.analyze(runs)
        if skill and skill not in data["skills"]:
            raise TeamworkError(f"no skill called {skill!r}; the skills are: {'; '.join(data['skills'])}")

        totals: dict[str, list[float]] = {}
        for run in runs:  # every point counts the same, whatever skill it's tagged with
            for sid, st in run["students"].items():
                for a in st["answers"].values():
                    if not a.get("retry"):
                        t = totals.setdefault(sid, [0.0, 0.0])
                        t[0] += a["earned"]
                        t[1] += a["possible"]

        def score(sid: str) -> float:
            if skill:
                return data["students"][sid][skill]["pct"]
            earned, possible = totals.get(sid, (0.0, 0.0))
            return earned / possible if possible else 0.5

        unplaced = sorted(sid for sid in data["students"] if skill and skill not in data["students"][sid])
        ties = {sid: rng.random() for sid in data["students"]}  # equal scores in a chance order, not by ID
        ids = sorted((sid for sid in data["students"] if sid not in unplaced), key=lambda sid: (-score(sid), ties[sid]))
        if roster:
            unplaced += sorted(set(roster) - set(data["students"]))
        middle = len(ids) // 2  # no evidence yet: in the middle, not at the bottom
        ids = ids[:middle] + unplaced + ids[middle:]
    elif roster:
        ids = sorted(roster)
        rng.shuffle(ids)  # nothing marked yet: at random
        skill = None
    else:
        raise TeamworkError(f"no marked classes under {folder}: groups come from marked work (or pass the IDs "
                            "with --roster to group them at random)")
    g_low, g_high = group_range(structure, size)
    sizes = group_sizes(len(ids), size, g_low, g_high)
    groups: list[list[str]] = [[] for _ in sizes]
    if not runs or (not similar and structure != "pairs"):
        order = list(range(len(sizes))) + list(reversed(range(len(sizes))))  # snake: 1..n, then n..1
        k = 0
        for sid in ids:
            while len(groups[order[k % len(order)]]) >= sizes[order[k % len(order)]]:
                k += 1
            groups[order[k % len(order)]].append(sid)
            k += 1
    elif similar:  # runs of neighbors in the ranking
        start = 0
        for g, n in enumerate(sizes):
            groups[g] = ids[start:start + n]
            start += n
    else:  # PALS: the top half paired in order with the lower half; an odd one out makes a trio
        pairs = len(ids) // 2
        for k in range(pairs):
            groups[k] = [ids[k], ids[pairs + k + (len(ids) % 2)]]
        if len(ids) % 2:
            groups[pairs - 1 if pairs else 0].append(ids[pairs])  # the middle student joins the last pair
        groups = [g for g in groups if g]
    plan = []
    for g in groups:
        members = list(g)
        rng.shuffle(members)  # who starts with which job: chance, not rank
        plan.append(list(zip(members, role_names(structure, len(members), size))))
    out = Path(out or folder / "progress")
    out.mkdir(parents=True, exist_ok=True)
    how = (("Similar" if similar else "Paired" if structure == "pairs" else "Mixed")
           + f" by {'“' + skill + '”' if skill else 'all marked work so far (every point counts the same)'}"
           + (": neighbors in skill, for targeted practice. Listed from the highest recent scores (Group 1) to "
              f"the lowest (Group {len(plan)}). " if similar else
              ": the top half paired in order with the lower half. " if structure == "pairs" else
              ": each group has a range. ") if runs else "At random: nothing is marked yet. ")
    jobs = ("" if structure == "game" else "First-round jobs were dealt at random; pass the role cards left each "
            "round. ")
    lines = ["# Groups (for the teacher; don't post)", "",
             how + jobs + f"(Made with seed {seed}; another seed reshuffles"
             + (" ties and first jobs.)" if runs else " the groups.)"), ""]
    for k, g in enumerate(plan, start=1):
        missing = ""
        if structure == "jigsaw" and len(g) < size:  # a part with no expert: the group reads it together
            missing = " (no " + ", ".join(f"Expert {chr(65 + n)}" for n in range(len(g), size)) + \
                ": read that expert sheet together)"
        lines.append(f"- Group {k}: " + ", ".join(f"{sid} ({role})" if role else sid for sid, role in g) + missing)
    if unplaced and runs:
        lines += ["", "No marked work " + (f"on “{skill}” " if skill else "") + "yet, so placed in the middle: "
                  + ", ".join(unplaced) + "."]
    if runs and skill:
        distinct = {round(score(sid), 3) for sid in data["students"] if sid not in unplaced}
        if len(distinct) <= 3:
            lines += ["", f"Only {len(distinct)} different scores on “{skill}”: few questions measured it, so these "
                      "groups are rough. Leave out --skill to use all marked work."]
    path = out / f"groups-{structure}{'-similar' if similar else ''}.md"
    path.write_text("\n".join(lines) + "\n")
    S.write_json(path.with_suffix(".json"), {"structure": structure, "similar": similar, "seed": seed,
                                              "groups": [[{"id": sid, "job": job} for sid, job in g] for g in plan]})
    return {"groups": plan, "path": path, "skill": skill, "mixed": bool(runs), "similar": similar}


# --- Team points: each team scored by how much its members improved ------------------------------------

def improvement_points(base: float | None, score: float) -> int:
    """STAD's improvement points (Slavin), percentages: a perfect paper or 10 or more above your own usual is 30;
    your usual to 10 above, 20; up to 10 below, 10; further below, 5. No earlier work counts as at your usual."""
    if score >= 100 or (base is not None and score > base + 10):
        return 30
    if base is None or score >= base:
        return 20
    return 10 if score >= base - 10 else 5


def team_points(folder: Path, worksheet: str, groups_path: Path | None = None, out: Path | None = None) -> dict:
    """After the exit sheet is marked: each student's improvement points and each team's average, so every
    student, at every level, can add as much to the team as anyone. Writes the teacher's details
    (team-points.md, by class ID) and a page to post (team-points.pdf: teams and their points, nothing else)."""
    from . import progress as PG
    folder = Path(folder)
    if not folder.is_dir():
        raise TeamworkError(f"no folder {folder}: give the class's folder")
    progress_dir = folder / "progress"
    if groups_path is None:
        made = sorted(progress_dir.glob("groups-*.json"), key=lambda p: p.stat().st_mtime)
        if not made:
            raise TeamworkError("no groups yet: make them with `groups` first (team points need the teams)")
        groups_path = made[-1]
    try:
        teams = S.read_json(Path(groups_path))["groups"]
        teams = [[{"id": str(m["id"])} if isinstance(m, dict) else {"id": str(m)} for m in team] for team in teams]
    except (KeyError, TypeError, ValueError):
        raise TeamworkError(f"{groups_path} isn't a groups file: make one with `groups`") from None
    runs = PG.collect(folder)
    exits = [r for r in runs if r["assignment_id"] == worksheet]
    if not exits:
        found = sorted({r["assignment_id"] for r in runs})
        raise TeamworkError(f"no marked class of {worksheet!r} under {folder}"
                            + (f"; marked worksheets: {', '.join(found)}" if found else ""))
    # Every marking of the exit sheet counts (two periods, a make-up); the latest page for each student.
    exit_run = {**exits[0], "students": {sid: st for r in exits for sid, st in r["students"].items()},
                "date": exits[-1]["date"]}

    def pct(run: dict, sid: str) -> float | None:
        answers = run["students"].get(sid, {}).get("answers", {})
        new = [a for a in answers.values() if not a.get("retry")]
        possible = sum(a["possible"] for a in new)
        if not possible or all(a.get("verdict") == "blank" for a in new):
            return None  # nothing on the page: absent, not zero
        return 100 * sum(a["earned"] for a in new) / possible

    earlier = [r for r in runs if (r["date"], r["title"]) < (exits[0]["date"], exits[0]["title"])
               and r["assignment_id"] != worksheet]
    rows, posted = [], []
    for k, team in enumerate(teams, start=1):
        members = []
        for member in team:
            sid = member["id"]
            score = pct(exit_run, sid)
            past = [v for v in (pct(r, sid) for r in earlier) if v is not None]
            base = sum(past) / len(past) if past else None
            points = improvement_points(base, score) if score is not None else None
            members.append((sid, base, score, points))
        scored = [m[3] for m in members if m[3] is not None]
        average = sum(scored) / len(scored) if scored else None
        rows.append((k, members, average))
        posted.append((k, average if len(scored) >= 2 else None))  # one student's score alone isn't posted
    out = Path(out or progress_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Team points (for the teacher; post team-points.pdf, not this)", "",
             f"Exit sheet: {exit_run['title']} ({exit_run['date']}). Each student's usual is their average on "
             f"{len(earlier)} earlier marked worksheet{'s' if len(earlier) != 1 else ''}. Points: 30 for a perfect paper "
             "or more than 10 above their usual; 20 for their usual to 10 above (or no earlier work); 10 for up to 10 "
             "below; 5 for further below. Absent students don't count against the team. A team with only one exit sheet "
             "posts \"-\" (a single score would show that student's).", ""]
    for k, members, average in rows:
        lines.append(f"- Team {k}: " + (f"{average:.0f} points" if average is not None else "no exit sheets") + " ("
                     + "; ".join(f"{sid}: " + ("absent" if score is None else
                                               f"{score:.0f}% vs usual {'none yet' if base is None else f'{base:.0f}%'}"
                                               f", {points}") for sid, base, score, points in members) + ")")
    (out / "team-points.md").write_text("\n".join(lines) + "\n")
    _team_points_page(out / "team-points.pdf", exit_run["title"], posted)
    return {"teams": rows, "md": out / "team-points.md", "pdf": out / "team-points.pdf", "earlier": len(earlier),
            "groups": Path(groups_path)}


def _team_points_page(path: Path, title: str, posted: list[tuple[int, float | None]]) -> None:
    fonts, _ = F.choose([title])
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(fonts.text(f"Team points: {title}"))
    c.setAuthor("Paper Loop")
    c.setFillGray(INK)
    c.setFont(fonts.bold, 26)
    c.drawString(MARGIN, PAGE_H - MARGIN - 26, "Team points")
    c.setFont(fonts.regular, 13)
    c.drawString(MARGIN, PAGE_H - MARGIN - 50, fonts.text(title))
    c.setFont(fonts.oblique, 11.5)
    c.setFillGray(0.3)
    c.drawString(MARGIN, PAGE_H - MARGIN - 72, "Everyone earns points by beating their own past work, so every "
                                                "teammate counts the same.")
    c.setFillGray(INK)
    y = PAGE_H - MARGIN - 110
    for k, average in posted:
        c.setFont(fonts.bold, 20)
        c.drawString(MARGIN + 10, y, f"Team {k}")
        c.drawRightString(PAGE_W - MARGIN - 10, y, f"{average:.0f}" if average is not None else "-")
        c.setStrokeGray(0.8)
        c.line(MARGIN, y - 10, PAGE_W - MARGIN, y - 10)
        y -= 40
        if y < MARGIN + 30:
            c.showPage()
            y = PAGE_H - MARGIN - 40
    c.showPage()
    c.save()

