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
import random
from pathlib import Path

from reportlab.pdfgen import canvas

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
          "materials", "steps", "rounds", "rotate_every", "dice", "table", "tokens", "roles", "parts", "cards",
          "worksheet", "class_size", "listen_for", "debrief", "sources")
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


def _part(part: dict, k: int) -> dict:
    """A jigsaw or reading part, its credit line checked the way a worksheet's passage is."""
    unknown = sorted(set(part) - set(PART_FIELDS))
    if unknown:
        raise TeamworkError(f"part {k}: unknown field {', '.join(unknown)}; a part has {', '.join(PART_FIELDS)}")
    part = dict(part)
    if part.get("cite"):
        try:
            part["source"], _ = SRC.check_cite(part["cite"], f"part {k}")
        except S.WorksheetError as e:
            raise TeamworkError(str(e)) from None
    said = " ".join(str(part.get(f, "")) for f in ("source", "quote_source")).lower()
    for brand, site in NO_ADAPT_NAMES.items():
        if brand in said:
            raise TeamworkError(f"part {k}: {SRC.NO_ADAPT[site]}, so a part can't be adapted from it. {SRC.INSTEAD}.")
    words = part.get("words", [])
    if not isinstance(words, list) or not all(isinstance(w, dict) and w.get("word") and w.get("means") for w in words):
        raise TeamworkError(f"part {k}: \"words\" is [{{\"word\": \"alliance\", \"means\": \"an agreement to help "
                            "each other\"}}]")
    return part


def normalize(data: dict) -> dict:
    """Defaults filled in and every field checked, with errors that say what to fix."""
    if not isinstance(data, dict):
        raise TeamworkError("teamwork file: one JSON object with \"title\", \"grade\", and \"structure\"")
    unknown = sorted(set(data) - set(FIELDS))
    if unknown:
        raise TeamworkError(f"teamwork file: unknown field {', '.join(unknown)}; the fields are {', '.join(FIELDS)}")
    for name in ("title", "structure"):
        if not data.get(name):
            raise TeamworkError(f"teamwork file: missing \"{name}\"")
    kind = data["structure"]
    if kind not in STRUCTURES:
        raise TeamworkError(f"teamwork file: \"structure\" is one of {', '.join(STRUCTURES)}")
    grade = S.grade_of(data)
    low, high = SIZES[kind]
    size = int(data.get("group_size") or (2 if kind == "pairs" else 4))
    if not low <= size <= high:
        raise TeamworkError(f"teamwork file: a {STRUCTURES[kind][0].lower()} works with {low}"
                            + (f" to {high}" if high != low else "") + f" students, not {size}")
    out = {**data, "kind": kind, "grade": grade, "group_size": size, "minutes": int(data.get("minutes") or 30),
           "subject": data.get("subject", ""), "goal": data.get("goal", ""), "rounds": int(data.get("rounds") or 1),
           "rotate_every": int(data.get("rotate_every") or 1), "class_size": int(data.get("class_size") or 0),
           "materials": _list(data, "materials", "teamwork file"),
           "abilities": _list(data, "abilities", "teamwork file"), "steps": _list(data, "steps", "teamwork file"),
           "debrief": _list(data, "debrief", "teamwork file"), "listen_for": _list(data, "listen_for", "teamwork file"),
           "sources": _list(data, "sources", "teamwork file"), "tokens": _list(data, "tokens", "teamwork file"),
           "parts": _list(data, "parts", "teamwork file"), "cards": _list(data, "cards", "teamwork file")}
    if kind == "lab" and not out["steps"]:
        raise TeamworkError("teamwork file: a lab needs \"steps\": what the group does each round")
    if kind == "jigsaw":
        if not low <= len(out["parts"]) <= high:
            raise TeamworkError(f"teamwork file: a jigsaw needs {low}-{high} \"parts\", one per expert")
        for k, part in enumerate(out["parts"], start=1):
            if not isinstance(part, dict) or not part.get("title") or not part.get("text"):
                raise TeamworkError(f"part {k}: needs \"title\" and \"text\" (and \"teach\": the 2-3 things to teach, "
                                    "and \"check\": a question to ask the home group)")
        out["group_size"] = len(out["parts"])
    if kind == "reciprocal":
        if not 2 <= len(out["parts"]) <= 8:
            raise TeamworkError("teamwork file: reciprocal teaching needs 2-8 \"parts\": the reading in chunks, "
                                "with a stop to talk after each")
        for k, part in enumerate(out["parts"], start=1):
            if not isinstance(part, dict) or not part.get("text"):
                raise TeamworkError(f"part {k}: needs \"text\" (and a \"title\" if the chunk has one)")
    out["parts"] = [_part(part, k) for k, part in enumerate(out["parts"], start=1)]
    if kind in ("pairs", "heads") and not out["cards"]:
        raise TeamworkError(f"teamwork file: {STRUCTURES[kind][0]} needs \"cards\": questions with answers, "
                            "[{\"q\": \"...\", \"a\": \"...\"}]")
    for k, card in enumerate(out["cards"], start=1):
        if not isinstance(card, dict) or not card.get("q") or not card.get("a"):
            raise TeamworkError(f"card {k}: needs \"q\" and \"a\"")
    for k, token in enumerate(out["tokens"], start=1):
        if not isinstance(token, dict) or not token.get("label") or not isinstance(token.get("count"), int):
            raise TeamworkError(f"token {k}: needs \"label\" and a whole-number \"count\" (per group)")
        if not isinstance(token.get("size", 0.75), (int, float)) or not 0.5 <= token.get("size", 0.75) <= 4:
            raise TeamworkError(f"token {k}: \"size\" is the side in inches, 0.5 to 4 (default 0.75)")
        if token.get("pattern", "plain") not in PATTERNS:
            raise TeamworkError(f"token {k}: \"pattern\" is one of {', '.join(PATTERNS)} (so copies stay black "
                                "and white)")
    dice = data.get("dice")
    if dice is not None and (not isinstance(dice, dict) or not isinstance(dice.get("rows"), list) or not dice["rows"]):
        raise TeamworkError("teamwork file: \"dice\" is {\"title\": ..., \"rows\": [[\"1-2\", \"what happens\"], ...]}")
    out["dice"] = dice
    table = data.get("table")
    if table is not None and (not isinstance(table, dict) or not isinstance(table.get("columns"), list)
                              or not 1 <= len(table["columns"]) <= 6 or not isinstance(table.get("rows"), int)):
        raise TeamworkError("teamwork file: \"table\" is {\"title\": ..., \"columns\": [up to 6 headings], "
                            "\"rows\": how many}")
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
            raise TeamworkError(f"teamwork file: \"roles\" replaces the {len(out['roles'])} cards "
                                f"({', '.join(r[0] for r in out['roles'])}): one entry for each, in that order")
        for k, r in enumerate(own, start=1):
            if not isinstance(r, dict) or not r.get("name") or not isinstance(r.get("jobs"), list) or not r["jobs"]:
                raise TeamworkError(f"role {k}: needs \"name\" and \"jobs\" (a list), and \"say\" (a list of "
                                    "sentence starters)")
        out["roles"] = [(r["name"], r["jobs"], r.get("say") or []) for r in own]
    return out


# --- Drawing ----------------------------------------------------------------------------------------

def _size(A: dict, size: float) -> float:
    """Type a student reads: bigger in grades 2-5."""
    return size * (1.25 if A["grade"] <= 3 else 1.12 if A["grade"] <= 5 else 1)


def _header(pen: Pen, A: dict, what: str) -> float:
    c = pen.c
    c.setFillGray(INK)
    c.setFont(pen.f.bold, 16)
    c.drawString(MARGIN, PAGE_H - MARGIN - 14, pen.f.text(what))
    c.setFont(pen.f.regular, 9)
    c.setFillGray(0.4)
    if what != A["title"] and pen.width(what, pen.f.bold, 16) + pen.width(A["title"], pen.f.regular, 9) + 20 \
            < PAGE_W - 2 * MARGIN:  # the activity's name, when there's room beside the heading
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN - 12, pen.f.text(A["title"]))
    c.setFillGray(INK)
    return PAGE_H - MARGIN - 30


def teacher_page(pen: Pen, A: dict, worksheet_note: str, pages: dict[str, str]) -> None:
    name, why = STRUCTURES[A["kind"]]
    y = _header(pen, A, A["title"])
    info = "  |  ".join(x for x in (name, f"grade {A['grade']}", A["subject"], f"groups of {A['group_size']}",
                                    f"about {A['minutes']} minutes") if x)
    y = pen.para(info, MARGIN, y, PAGE_W - 2 * MARGIN, 11, gray=0.35) - 6
    if A["goal"]:
        y = pen.para(f"Goal: {A['goal']}", MARGIN, y, PAGE_W - 2 * MARGIN, 11.5, pen.f.bold) - 6
    y = pen.para(f"Why it works: {why}", MARGIN, y, PAGE_W - 2 * MARGIN, 10) - 10
    rotation = _rotation(A)
    sections = [("Before class", [
        _grouping(A) + _counts(A),
        "This page is for you: print it once. " + _printing(A, pages),
        ("Each group needs: " + "; ".join(A["materials"]) + ".") if A["materials"] else "",
        worksheet_note]),
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
    for head, items in sections:
        if y < 120:
            pen.warnings.append(f"the teacher's page ran out of room at \"{head}\": shorten the goal, "
                                "listen_for, or debrief")
            break
        pen.c.setFont(pen.f.bold, 11.5)
        pen.c.drawString(MARGIN, y - 11, pen.f.text(head))
        y -= 17
        for item in items:
            if item:
                y = pen.para(f"• {item}", MARGIN + 6, y, PAGE_W - 2 * MARGIN - 6, 10) - 3
        y -= 7


def _rotation(A: dict) -> tuple[str, list[str]]:
    kind = A["kind"]
    if kind == "jigsaw":
        return ("Every expert counts", ["Each home group needs every letter. If a student is absent, the home group "
                                        "reads that expert sheet together; if a group has five, two share a letter."])
    if kind == "heads":
        return ("Anyone can be called", ["Roll a die for the number, so every student gets ready, not only the one "
                                         "who usually answers."])
    return ("Jobs rotate", [("Halfway, partners switch, so each is the coach once." if kind == "pairs" else
                             "Pass the role cards one seat to the left " + (
                                 "after each stop" if kind == "reciprocal" else "each round" if A["rotate_every"] == 1
                                 else f"every {A['rotate_every']} rounds")
                             + ", so every student does every job.") + " No one is always the helper or the helped."])


def _counts(A: dict) -> str:
    n, size = A.get("class_size"), A["group_size"]
    if not n:
        return ""
    groups, extra = max(1, n // size), n - max(1, n // size) * size
    what = "pairs" if A["kind"] == "pairs" else "groups"
    return (f" For {n} students: {groups} {what}" + (f", {extra} of them with one more" if extra else "")
            + (" (two students share a letter)" if extra and A["kind"] == "jigsaw" else "") + ".")


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
        return (f"Print one set of role cards{at('Role cards')} and one task card{at('Group task')} per group"
                + (f", and the tokens{at('Tokens')}" if A["tokens"] else "") + ".")
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
                "after the group has tried.", "Before a group moves on, ask the Skeptic: “Can everyone explain "
                "it?” Then pick someone else to explain."]
    if kind == "jigsaw":
        home = 4 * len(A["parts"])
        expert = max(10, A["minutes"] - home - 5)
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
            size = 40 if pen.width(name, pen.f.bold, 40) < x1 - x0 - 40 else 30
            topic = A["parts"][start + k]["title"] if A["kind"] == "jigsaw" and start + k < len(A["parts"]) else ""
            c.setFont(pen.f.bold, size)
            c.drawCentredString(0, -size * 0.35 + (12 if topic else 0), pen.f.text(name))
            if topic:  # so the home group sees who teaches what
                c.setFont(pen.f.regular, 16)
                c.drawCentredString(0, -size * 0.35 - 14, pen.f.text(topic))
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
            c.setFont(pen.f.bold, _size(A, 14))
            c.drawString(x0 + 14, yy, pen.f.text(f"{name}: your job"))
            yy -= 6
            for job in jobs:
                yy = pen.para(f"• {job}", x0 + 18, yy, jw, size) - 2
            yy2 = mid - 16
            c.setFont(pen.f.bold, _size(A, 11))
            c.drawString(sx, yy2, "Say it like this")
            yy2 -= 6
            for stem in stems:
                yy2 = pen.para(f"“{stem}”", sx, yy2, x1 - sx - 14, size, pen.f.oblique) - 3
            c.setFillGray(0.25)
            c.setFont(pen.f.regular, _size(A, 9.5))
            c.drawString(x0 + 14, top - h + 8, pen.f.text("Everyone also does the work, and helps each other." + {
                "lab": (" Next round, pass this card to your left." if A["rotate_every"] == 1 else
                        f" Every {A['rotate_every']} rounds, pass this card to your left."),
                "reciprocal": " After each stop, pass this card to your left.",
                "pairs": " Halfway, switch cards."}.get(A["kind"], "")))
            c.setFillGray(INK)
        yield


def task_card(pen: Pen, A: dict) -> None:
    c = pen.c
    y = _header(pen, A, "Group task")
    if A["goal"]:
        y = pen.para(A["goal"], MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 13), pen.f.bold) - 8
    if A["abilities"]:
        y = pen.para("This task needs " + ", ".join(A["abilities"]) + ". Everyone in your group is good at some of "
                     "these.", MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 10.5), pen.f.oblique) - 10
    for n, step in enumerate(A["steps"], start=1):
        step_number(pen, MARGIN + 9, y - 8, n, 8)
        y = pen.para(step, MARGIN + 24, y, PAGE_W - 2 * MARGIN - 24, _size(A, 12)) - 6
    if A["rounds"] > 1:
        c.setFont(pen.f.bold, 11)
        c.drawString(MARGIN, y - 12, "Rounds:")
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
        y = pen.para("Check off each round. Pass the role cards left after " + (
            "each one." if every == 1 else f"every {every} rounds."), MARGIN, y - 2, PAGE_W - 2 * MARGIN,
            _size(A, 10.5), pen.f.oblique) - 6
    dice = A["dice"]
    if dice:
        c.setFont(pen.f.bold, 12)
        c.drawString(MARGIN, y - 12, pen.f.text(dice.get("title") or "Roll a die"))
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
        c.drawString(MARGIN, y - 12, pen.f.text(table.get("title") or "Our data"))
        y -= 18
        cols = table["columns"]
        weights = [max(len(str(col)), 8) for col in cols]
        widths = [(PAGE_W - 2 * MARGIN) * wt / sum(weights) for wt in weights]
        edges = [MARGIN + sum(widths[:k]) for k in range(len(cols) + 1)]
        head = max(pen.para_height(col, w - 8, 10, pen.f.bold) for col, w in zip(cols, widths)) + 8
        row_h = 22.0
        rows = max(1, min(int(table["rows"]), int((y - head - 60) // row_h)))
        if rows < int(table["rows"]):
            pen.warnings.append(f"the data table has room for {rows} rows, not {table['rows']}: cut steps or dice "
                                "rows, or ask for fewer rows")
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
    c.setFillGray(0.35)
    pen.para("Before you move on, the Skeptic checks: can everyone explain it? Then you each do the worksheet on "
             "your own.", MARGIN, max(y, 70), PAGE_W - 2 * MARGIN, 10, pen.f.oblique, gray=0.35)
    c.setFillGray(INK)


def tokens_page(pen: Pen, A: dict):
    """Cut-out tokens for one group, in patterns that stay distinct on a black-and-white copy. Each kind starts
    a new row, at its own size."""
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
            x0 = MARGIN + col * side
            c.setStrokeGray(0.3)
            c.setLineWidth(0.6)
            c.rect(x0, y - side, side, side, stroke=1, fill=0)
            _pattern(c, token.get("pattern", "plain"), x0 + 6, y - side + 6, side - 12)
            label = token["label"]
            size = min(9 + (side - 54) / 8, 18)
            if pen.width(label, pen.f.bold, size) > side - 8:
                size = max(6.0, size * (side - 8) / pen.width(label, pen.f.bold, size))
            c.setFillGray(1)
            c.rect(x0 + 3, y - side / 2 - size * 0.7, side - 6, size * 1.35, stroke=0, fill=1)
            c.setFillGray(INK)
            c.setFont(pen.f.bold, size)
            c.drawCentredString(x0 + side / 2, y - side / 2 - size * 0.33, pen.f.text(label))
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


def expert_sheets(pen: Pen, A: dict):
    """Jigsaw: one sheet per part, then the home group's note sheet."""
    c = pen.c
    for k, part in enumerate(A["parts"]):
        letter = chr(65 + k)
        y = _header(pen, A, f"Expert {letter}: {part['title']}")
        y = pen.para("1. Read your part with the other experts on it. 2. Agree on what matters most. 3. Fill the "
                     "teach box: you'll teach your home group in about 3 minutes.", MARGIN, y, PAGE_W - 2 * MARGIN,
                     10.5, pen.f.oblique) - 10
        words = len(str(part["text"]).split()) + len(str(part.get("quote", "")).split())
        if words > 220:
            pen.warnings.append(f"part {letter} has {words} words: about 150-200 fit beside the teach box; shorten it")
        y = pen.para(part["text"], MARGIN, y, PAGE_W - 2 * MARGIN, _size(A, 11.5)) - 6
        if part.get("quote"):  # a primary source, set apart from the background text
            top = y
            y = pen.para(f"“{part['quote']}”", MARGIN + 18, y - 2, PAGE_W - 2 * MARGIN - 30, _size(A, 11),
                         pen.f.oblique) - 2
            if part.get("quote_source"):
                y = pen.para(f"— {part['quote_source']}", MARGIN + 18, y, PAGE_W - 2 * MARGIN - 30, 9, gray=0.3) - 2
            c.setStrokeGray(0.4)
            c.setLineWidth(2)
            c.line(MARGIN + 6, top - 2, MARGIN + 6, y + 2)
            c.setLineWidth(1)
            y -= 6
        if part.get("words"):
            y = pen.para("Key words: " + "; ".join(f"{w['word']}: {w['means']}" for w in part["words"]), MARGIN, y,
                         PAGE_W - 2 * MARGIN, _size(A, 10)) - 6
        if part.get("source"):
            y = pen.para(part["source"], MARGIN, y, PAGE_W - 2 * MARGIN, 8, pen.f.oblique, gray=0.35) - 6
        if part.get("teach"):
            y = pen.para("Make sure you teach: " + "; ".join(part["teach"]), MARGIN, y, PAGE_W - 2 * MARGIN,
                         _size(A, 10.5), pen.f.bold) - 8
        if y < 250:
            pen.warnings.append(f"expert sheet {letter} leaves too little room for the teach box: shorten part "
                                f"{letter}'s text (about 150 words fits)")
        c.setFillGray(INK)
        c.setFont(pen.f.bold, 12)
        c.drawString(MARGIN, y - 12, "Teach box")
        c.setFont(pen.f.regular, 9.5)
        c.drawRightString(PAGE_W - MARGIN - 20, y - 11, "Teacher checked")
        c.setStrokeGray(0.3)
        c.rect(PAGE_W - MARGIN - 14, y - 14, 12, 12, stroke=1, fill=0)
        y -= 20
        prompts = ["The most important ideas, in my words:", "1.", "2.", "3.", "An example:"]
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
            y = pen.para("My check question for the group: " + part["check"], MARGIN, y - 6, PAGE_W - 2 * MARGIN,
                         10.5) - 4
            c.setStrokeGray(0.75)
            c.line(MARGIN, y - 20, PAGE_W - MARGIN, y - 20)
            c.setFillGray(INK)
            c.setFont(pen.f.regular, 10.5)
            c.drawString(MARGIN, y - 14, "Its answer:")
            y -= 26
        if y <= 170:
            pen.warnings.append(f"expert sheet {letter} has no room for the sketch box: shorten part {letter}")
        if y > 170:  # a sketch is a second way in, for the teacher and for the group
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 10.5)
            c.drawString(MARGIN, y - 14, "A picture I'll draw to show it:")
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
    y = _header(pen, A, "Read together")
    y = pen.para(f"First, the {names[-1]} looks at the title and guesses what the reading is about. Take turns "
                 "reading each part aloud, going left. After each part, stop and talk.", MARGIN, y,
                 width, _size(A, 10.5)) - 10
    for k, part in enumerate(A["parts"], start=1):
        need = pen.para_height(part["text"], width, size) + (24 if part.get("title") else 6) + 40
        if y - need < 60 and y < PAGE_H - MARGIN - 40:
            yield
            y = _header(pen, A, "Read together")
        if part.get("title"):
            c.setFillGray(INK)
            c.setFont(pen.f.bold, 12)
            c.drawString(MARGIN, y - 12, pen.f.text(f"Part {k}: {part['title']}"))
            y -= 18
        y = pen.para(part["text"], MARGIN, y, width, size) - 4
        if part.get("source"):
            y = pen.para(part["source"], MARGIN, y, width, 8, pen.f.oblique, gray=0.35) - 4
        last = k == len(A["parts"])
        if not last:
            stop = f"Stop and talk, in this order: {', '.join(names)}. Pass the cards left."
        else:  # nothing left to predict: the last job sits out
            stop = f"Last stop: {', '.join(names[:-1] or names)}. Then sum up the whole reading together."
        stop_size = _size(A, 10.5)
        h = pen.para_height(stop, width - 16, stop_size, pen.f.bold) + 8
        c.setFillGray(0.92)
        c.rect(MARGIN, y - h - 2, width, h, stroke=0, fill=1)
        c.setFillGray(INK)
        pen.para(stop, MARGIN + 8, y - 5, width - 16, stop_size, pen.f.bold)
        y -= h + 12
    yield


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
    fonts, _ = F.choose(list(_strings(data)))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "teamwork.pdf"
    worksheet = A.get("worksheet")
    note = (f"Print the worksheet each student does alone at the end ({worksheet}), one per student, with its "
            "versions for the students who need them: all forms are scanned together and marked like any worksheet."
            if worksheet else
            "Add a short worksheet each student does alone at the end: group work pays off only when each student "
            "is accountable on their own.")
    checks: list[str] = []
    if not worksheet:
        checks.append("no \"worksheet\": add the individual worksheet each student hands in (an exit sheet "
                      "Paper Loop marks), so the group's work is also each student's")
    elif not any((json_path.parent / name).exists() for name in (f"{worksheet}.json", f"{worksheet}/key.json")):
        checks.append(f"no worksheet {worksheet!r} beside {json_path.name}: make it with `make` (or fix the id)")
    reading = " ".join(str(part.get("text", "")) for part in A["parts"] if isinstance(part, dict))
    level = SRC.reading_grade(reading) if reading else None
    if level is not None and A["grade"] >= 3 and level > A["grade"] + 2:
        checks.append(f"the reading scores about grade {level:g} (Flesch-Kincaid) for grade {A['grade']}: "
                      "simplify it, unless that's intended")

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
    page_of = {name: f"page {a}" if a == b else f"pages {a}-{b}" for name, a, b in pages}
    pages, warnings = render(str(path), page_of)
    return {"pdf": path, "pages": pages, "warnings": warnings, "structure": STRUCTURES[A["kind"]][0],
            "group_size": A["group_size"]}


# --- Mixed-skill groups from a class's marked work ------------------------------------------------------

def role_names(structure: str, n: int, size: int) -> list[str]:
    """The first-round job for each of n students in a group meant for size."""
    if structure == "jigsaw":
        return [f"Expert {chr(65 + k % size)}" for k in range(n)]  # an extra student doubles up as a second A
    if structure == "heads":
        return [f"Number {k + 1}" for k in range(n)]
    names = [r[0] for r in ROLES.get(structure, ROLES["lab"])]
    if structure == "pairs":
        return [names[0]] + [names[1]] * (n - 1)  # a trio: the players take turns
    return [names[k % len(names)] for k in range(n)]


def form_groups(folder: Path, size: int = 4, skill: str | None = None, roster_path: Path | None = None,
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
    folder = Path(folder)
    roster = P.load_roster(roster_path) if roster_path else None
    runs = PG.collect(folder, roster) if folder.is_dir() else []
    rng = random.Random(seed)
    if runs:
        data = PG.analyze(runs)
        if skill and skill not in data["skills"]:
            raise TeamworkError(f"no skill called {skill!r}; the skills are: {'; '.join(data['skills'])}")

        def score(sid: str) -> float:
            cells = data["students"][sid]
            if skill:
                return cells[skill]["pct"] if skill in cells else 0.5
            return sum(c["pct"] for c in cells.values()) / len(cells) if cells else 0.5

        ids = sorted(data["students"], key=lambda sid: (-score(sid), sid))
        if roster:
            ids += sorted(set(roster) - set(ids))  # no marked work yet: dealt out after the rest
    elif roster:
        ids = sorted(roster)
        rng.shuffle(ids)  # nothing marked yet: at random
        skill = None
    else:
        raise TeamworkError(f"no marked classes under {folder}: groups come from marked work (or pass the IDs "
                            "with --roster to group them at random)")
    if not ids:
        raise TeamworkError("no student IDs to group")
    n_groups = max(1, len(ids) // size)  # extras join groups (a trio, not a student alone)
    groups: list[list[str]] = [[] for _ in range(n_groups)]
    if not runs or (not similar and structure != "pairs"):
        for k, sid in enumerate(ids):  # snake order: 1..n, then n..1
            lap, pos = divmod(k, n_groups)
            groups[pos if lap % 2 == 0 else n_groups - 1 - pos].append(sid)
    elif similar:
        for k, sid in enumerate(ids):  # runs of neighbors; the extras join the last groups
            groups[min(k // size, n_groups - 1)].append(sid)
    else:
        half = -(-len(ids) // 2)
        for k in range(n_groups):
            groups[k] = [ids[k]] + ([ids[half + k]] if half + k < len(ids) else [])
        for k, sid in enumerate(sid for sid in ids if not any(sid in g for g in groups)):
            groups[-1 - k % n_groups].append(sid)  # an odd one out makes a trio
    plan = []
    for g in groups:
        members = list(g)
        rng.shuffle(members)  # who starts with which job: chance, not rank
        plan.append(list(zip(members, role_names(structure, len(members), size))))
    out = Path(out or folder / "progress")
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Groups (for the teacher; don't post)", "",
             (("Similar" if similar else "Paired" if structure == "pairs" else "Mixed")
              + f" by {'“' + skill + '”' if skill else 'all skills so far'}"
              + (": neighbors in skill, for targeted practice. " if similar else
                 ": the top half paired in order with the lower half. " if structure == "pairs" else
                 ": each group has a range. ") if runs
              else "At random: nothing is marked yet. ") +
             "First-round jobs were dealt at random; pass the role cards left each round.", ""]
    for k, g in enumerate(plan, start=1):
        lines.append(f"- Group {k}: " + ", ".join(f"{sid} ({role})" for sid, role in g))
    path = out / f"groups-{structure}{'-similar' if similar else ''}.md"
    path.write_text("\n".join(lines) + "\n")
    return {"groups": plan, "path": path, "skill": skill, "mixed": bool(runs), "similar": similar}
