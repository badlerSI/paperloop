"""Lessons: a lesson plan and the slides to teach it, built around a Paper Loop worksheet.

Claude writes one lesson file (JSON, described in references/lesson-format.md). `build` writes:
- lesson-plan.docx: objectives, materials, the timed sequence with its slide numbers, checks for
  understanding, misconceptions, differentiation, and every worksheet answer with how to get it
- slides.pptx, and slides.pdf (the same slides): the lesson in order
- go-over.pptx and go-over.pdf: each worksheet question, then its answer worked through
- answer-key.pdf: the worksheet with the answers written in
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from . import deck as DK
from . import sheet as S
from . import slides as K
from . import walk as WK
from . import wordfile as WF
from .deck import LessonError

SLIDE_TYPES = ("points", "example", "vocab", "question", "compare", "passage", "code", "section")
COLLECT = ("Collect the worksheets before going over them, so the scan shows each student's own work. Students "
           "fix mistakes on the marked copy they get back. If anyone is still working (extended time), go over it "
           "tomorrow instead.")
EXIT = re.compile(r"\bexit\b", re.I)
SKIPPABLE = ("title", "targets", "agenda")


def _period(text: str) -> str:
    """Text ending in one full stop: "fine." stays "fine.", not "fine.."."""
    text = text.rstrip()
    return text if text.endswith((".", "!", "?", ".\u201d", ".\"")) else text + "."


def _need(obj: dict, name: str, where: str):
    if obj.get(name) in (None, "", []):
        raise LessonError(f"{where}: missing \"{name}\"")
    return obj[name]


def _strings(obj, where: str, name: str) -> list[str]:
    value = obj.get(name, [])
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise LessonError(f"{where}: \"{name}\" must be a list of strings")
    return value


def _target(objective: str) -> str:
    """'Students will be able to explain X' as a student would say it."""
    for lead in ("Students will be able to ", "Students will ", "SWBAT ", "Students can "):
        if objective.lower().startswith(lead.lower()):
            rest = objective[len(lead):]
            for theirs, mine in ((r"\btheir\b", "my"), (r"\bthemselves\b", "myself"), (r"\bthey\b", "I")):
                rest = re.sub(theirs, mine, rest)
            return "I can " + rest[:1].lower() + rest[1:]
    return objective


def normalize(lesson: dict) -> dict:
    """Defaults filled in and every field checked, with errors that say what to fix."""
    L = {"subject": "", "worksheet": "", "subtitle": "", "standards": [], "materials": [], "vocabulary": [],
         "checks": [], "misconceptions": [], "differentiation": {}, "homework": "", "notes": "", "assessment": "",
         "walkthrough": [], "skip": [], **lesson}
    for name in ("title", "grade_band", "minutes", "objectives", "sequence"):
        _need(L, name, "lesson")
    L["lesson_id"] = L.get("lesson_id") or L["title"]
    L["grade"] = S.grade_of(L)
    L["objectives"] = _strings(L, "lesson", "objectives")
    L["targets"] = _strings(L, "lesson", "targets") or [_target(o) for o in L["objectives"]]
    for name in ("standards", "materials", "checks"):
        L[name] = _strings(L, "lesson", name)
    bad = [s for s in L["skip"] if s not in SKIPPABLE]
    if bad:
        raise LessonError(f"lesson: \"skip\" can hold {', '.join(SKIPPABLE)}, not {', '.join(map(str, bad))}")
    try:
        L["minutes"] = int(L["minutes"])
    except (TypeError, ValueError):
        raise LessonError("lesson: \"minutes\" must be a number") from None
    for k, v in enumerate(L["vocabulary"], start=1):
        if not isinstance(v, dict) or not v.get("term") or not v.get("meaning"):
            raise LessonError(f"lesson: vocabulary {k} needs \"term\" and \"meaning\"")
    for k, m in enumerate(L["misconceptions"], start=1):
        if not isinstance(m, dict) or not m.get("misconception") or not m.get("response"):
            raise LessonError(f"lesson: misconception {k} needs \"misconception\" and \"response\" (how to answer it)")
    if not isinstance(L["differentiation"], dict):
        raise LessonError("lesson: \"differentiation\" must be an object with \"support\", \"extension\", and/or "
                          "\"language\" lists")
    for name in L["differentiation"]:
        if name not in ("support", "extension", "language", "accommodations"):
            raise LessonError(f"lesson: differentiation \"{name}\": use \"support\", \"extension\", \"language\", or "
                              "\"accommodations\"")
        L["differentiation"][name] = _strings(L["differentiation"], "lesson differentiation", name)

    phases = []
    for k, raw in enumerate(L["sequence"], start=1):
        where = f"sequence {k}"
        if not isinstance(raw, dict):
            raise LessonError(f"{where}: each step of the sequence is an object with \"phase\" and \"minutes\"")
        p = {"teacher": "", "students": "", "slides": [], "worksheet": False, "walkthrough": False,
             "divider": False, "then": "", "review": "", "most": None, **raw}
        _need(p, "phase", where)
        where = f"sequence {k} ({p['phase']})"
        try:
            p["minutes"] = int(p.get("minutes", 0))
        except (TypeError, ValueError):
            raise LessonError(f"{where}: \"minutes\" must be a number") from None
        if (p["worksheet"] or p["walkthrough"]) and not L["worksheet"]:
            raise LessonError(f"{where}: uses the worksheet, but the lesson has no \"worksheet\" (the folder "
                              "`make` wrote)")
        if p["walkthrough"] not in (True, False) and not (isinstance(p["walkthrough"], list)
                                                           and all(isinstance(q, int) for q in p["walkthrough"])):
            raise LessonError(f"{where}: \"walkthrough\" is true (every question) or a list of question numbers")
        if not isinstance(p["review"], str):
            raise LessonError(f"{where}: \"review\" is the marking folder of an earlier worksheet, as a path from "
                              "the lesson file")
        if p["most"] is not None and (not isinstance(p["most"], int) or p["most"] < 1):
            raise LessonError(f"{where}: \"most\" is how many of the most-missed questions to go over, 1 or more")
        for n, s in enumerate(p["slides"], start=1):
            _check_slide(s, f"{where}, slide {n}")
        phases.append(p)
    L["sequence"] = phases

    walk = {}
    for k, w in enumerate(L["walkthrough"], start=1):
        if not isinstance(w, dict) or not isinstance(w.get("q"), int):
            raise LessonError(f"lesson: walkthrough {k} needs \"q\", the worksheet question's number")
        for name in ("steps", "mistakes"):
            w[name] = _strings(w, f"walkthrough for question {w['q']}", name)
        walk[w["q"]] = w
    L["walk"] = walk
    return L


def _check_slide(s, where: str) -> None:
    if not isinstance(s, dict):
        raise LessonError(f"{where}: a slide is an object with \"type\"")
    for name in ("say", "answer_say", "title", "prompt", "problem", "text", "callout", "why", "focus", "source"):
        if name in s and not isinstance(s[name], str):
            raise LessonError(f"{where}: \"{name}\" must be a string")
    if "first_line" in s and not isinstance(s["first_line"], int):
        raise LessonError(f"{where}: \"first_line\" must be a whole number")
    kind = s.get("type")
    if kind not in SLIDE_TYPES:
        raise LessonError(f"{where}: \"type\" must be one of {', '.join(SLIDE_TYPES)}")
    if kind not in ("vocab", "question"):
        _need(s, "title", where)
    if kind == "points" and not (s.get("points") or s.get("image") or s.get("diagram")):
        raise LessonError(f"{where}: a points slide needs \"points\", or a picture (\"image\" or \"diagram\")")
    if kind == "points":
        s["points"] = _strings(s, where, "points")
    if kind == "example":
        _need(s, "problem", where)
        s["steps"] = _strings(s, where, "steps")
    if kind == "question":
        _need(s, "prompt", where)
        s["choices"] = _strings(s, where, "choices")
        if s["choices"] and not 2 <= len(s["choices"]) <= 8:
            raise LessonError(f"{where}: give 2 to 8 choices (or none, for an open question)")
        answer = str(s.get("answer", "")).strip()
        labels = "12345678" if s.get("choice_labels") == "numbers" else "ABCDEFGH"
        if s["choices"] and answer and (len(answer) != 1 or answer.upper() not in labels[:len(s["choices"])]):
            raise LessonError(f"{where}: with choices, \"answer\" is the {'number' if labels[0] == '1' else 'letter'} "
                              f"of the right one ({labels[0]}-{labels[len(s['choices']) - 1]})")
    if kind in ("passage", "code"):
        _need(s, "text", where)


def _phase_rows(L: dict) -> list[tuple[str, int]]:
    return [(p["phase"], p["minutes"]) for p in L["sequence"]]


def _walk_questions(p: dict, ws: WK.Worksheet) -> list[int]:
    return ws.questions if p["walkthrough"] is True else list(p["walkthrough"])


def _question_notes(q: int, spec: dict) -> str:
    think = spec.get("think", "")
    return (f"Question {q}, as it was printed." + (f" Ask: {think}" if think else "")
            + (f"\n\n{spec['ask']}" if spec.get("ask") else ""))


def _answer_notes(ws: WK.Worksheet, q: int, spec: dict) -> str:
    parts = [f"Answer: {ws.answer_text(q)}"]
    if spec.get("idea"):
        parts.append(f"Key idea: {spec['idea']}")
    if spec.get("steps"):
        parts.append("Steps: " + " ".join(f"({k}) {s}" for k, s in enumerate(spec["steps"], start=1)))
    if spec.get("mistakes"):
        parts.append("Watch for: " + " ".join(spec["mistakes"]))
    if spec.get("say"):
        parts.append(spec["say"])
    return "\n\n".join(K.plain(p) for p in parts)


def walkthrough(b: DK.Builder, ws: WK.Worksheet, qs: list[int], walk: dict) -> None:
    shown = set()
    for q in qs:
        pid = ws.items[q].get("passage")
        if pid and (pid in ws.passages or ws.passage(pid)) and pid not in shown:  # the reading first, as printed
            b.walk_passage(ws, pid, [x for x in qs if ws.items[x].get("passage") == pid])
            shown.add(pid)
        spec = walk.get(q, {})
        b.walk_question(ws, q, spec, chip="Think first", notes=_question_notes(q, spec))
        b.walk_answer(ws, q, spec, notes=_answer_notes(ws, q, spec))


def _slide(b: DK.Builder, s: dict, where: str, L: dict, exit_ticket: bool = False) -> None:
    kind = s["type"]
    if kind == "question" and exit_ticket and s.get("answer"):
        # No answer slide after an exit ticket: students still writing would copy it. It goes in the notes.
        answer = f"Answer (in the notes only, so no one copies it): {_period(s['answer'])}" + (f" {s['why']}" if s.get("why") else "")
        s = {**s, "answer": "", "why": "", "say": K.plain(s.get("say", "") + ("\n\n" if s.get("say") else "") + answer)}
    if kind == "points":
        b.points(s, where)
    elif kind == "example":
        b.example(s, where)
    elif kind == "vocab":
        b.vocab({**s, "words": s.get("words") or L["vocabulary"]}, where)
    elif kind == "question":
        b.question(s, where)
    elif kind == "compare":
        b.compare(s, where)
    elif kind == "passage":
        b.passage(s, where)
    elif kind == "code":
        b.passage(s, where, mono=True)
    elif kind == "section":
        b.section(s["title"], s.get("subtitle", ""), s.get("chip", ""), s.get("say", ""))


def build(lesson_path: Path, out_dir: Path) -> dict:
    lesson_path, out_dir = Path(lesson_path), Path(out_dir)
    base = lesson_path.resolve().parent
    L = normalize(S.read_json(lesson_path))
    ws = WK.Worksheet(base / L["worksheet"]) if L["worksheet"] else None
    warnings = []
    if ws:
        unknown = sorted(set(L["walk"]) - set(ws.questions))
        if unknown:
            raise LessonError(f"lesson: walkthrough for question{'s' if len(unknown) > 1 else ''} "
                              f"{', '.join(map(str, unknown))}, but the worksheet has questions "
                              f"{', '.join(map(str, ws.questions))}")
        for p in L["sequence"]:
            if p["walkthrough"] not in (True, False):
                missing = sorted(set(p["walkthrough"]) - set(ws.questions))
                if missing:
                    raise LessonError(f"sequence ({p['phase']}): walkthrough lists question "
                                      f"{', '.join(map(str, missing))}, which the worksheet doesn't have")
        for q, spec in L["walk"].items():
            if spec.get("draw"):
                try:
                    spec["drawing"] = ws.answer_drawing(q, spec["draw"])
                except ValueError as e:
                    raise LessonError(str(e)) from None
        missing = [q for q in ws.questions if q not in L["walk"]]
        if missing:
            warnings.append(f"no walkthrough for question{'s' if len(missing) > 1 else ''} "
                            f"{', '.join(map(str, missing))}: its answer slide shows only the key")
    total = sum(p["minutes"] for p in L["sequence"])
    if total > L["minutes"]:
        warnings.append(f"the sequence adds up to {total} minutes, but the lesson is {L['minutes']}")
    elif total < L["minutes"] - 10:
        warnings.append(f"the sequence adds up to {total} minutes, leaving {L['minutes'] - total} of the "
                        f"{L['minutes']} unplanned (2-5 minutes for transitions is about right)")

    texts = DK._strings(S.read_json(lesson_path))
    if ws:
        texts += [i["prompt"] for i in ws.items.values()] + [i["key"] for i in ws.items.values()]
    from . import goover as G  # goover imports this module
    for p in L["sequence"]:
        if p["review"]:  # an earlier worksheet's go-over, from its marked class
            work = base / p["review"]
            if not (work / "results.json").exists():
                raise LessonError(f"sequence ({p['phase']}): \"review\" points at {work}, which has no results.json: "
                                  "it's the marking folder of a worksheet whose marks `check` has accepted")
            p["_review"] = G._prepare(work)
            texts += G.texts(p["_review"])
    measure = K.Measure(texts)
    theme = K.theme_for(L["subject"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in ("slide-images", "go-over-images"):  # from an earlier version, which kept them
        shutil.rmtree(out_dir / old, ignore_errors=True)
    images = Path(tempfile.mkdtemp(prefix="paper-loop-slides-"))  # the decks carry their own copies
    try:
        return _build(L, ws, warnings, measure, theme, out_dir, images, base)
    finally:
        shutil.rmtree(images, ignore_errors=True)


def _build(L: dict, ws, warnings: list, measure, theme, out_dir: Path, images: Path, base: Path) -> dict:
    b = DK.Builder(theme, L["grade"], measure, images / "slides", base)
    chip = " · ".join(x for x in (L["subject"], L["grade_band"]) if x)
    if "title" not in L["skip"]:
        b.title_slide(L["title"], L["subtitle"], chip, L.get("say", ""))
    if "targets" not in L["skip"]:
        b.targets(L["targets"])
    if "agenda" not in L["skip"]:
        b.agenda(_phase_rows(L))
    ranges = []
    worksheet_done = False
    teaching: list[int] = []  # the lesson's own slides before the worksheet
    for k, p in enumerate(L["sequence"], start=1):
        start = len(b.slides) + 1
        if p["divider"]:
            b.section(p["phase"], "", f"{p['minutes']} min" if p["minutes"] else "")
        if p["worksheet"]:
            b.worksheet_time(ws, p["minutes"], p["then"])
            worksheet_done = True
        for n, s in enumerate(p["slides"], start=1):
            before = len(b.slides)
            _slide(b, s, f"sequence {k} ({p['phase']}), slide {n}", L, bool(EXIT.search(p["phase"])))
            if not worksheet_done:  # before the worksheet, a slide mustn't give its answers away
                teaching += range(before, len(b.slides))
        if p["review"]:
            from . import goover as G
            first_review = len(b.slides)
            done = G.review(b, p["_review"], p["most"])
            warnings += [f"review of {done['title']}: {w}" for w in done["warnings"]]
            if first_review < len(b.slides):
                b.slides[first_review].notes = (f"Hand back the marked copies of {done['title']} now (returned.pdf "
                                                "from its marking). " + b.slides[first_review].notes)
        if p["walkthrough"]:
            start_walk = len(b.slides)
            walkthrough(b, ws, _walk_questions(p, ws), L["walk"])
            if worksheet_done and start_walk < len(b.slides):  # the same day: the sheets go in before the answers
                first = b.slides[start_walk]
                first.notes = COLLECT + ("\n\n" + first.notes if first.notes else "")
        end = len(b.slides)
        ranges.append((start, end) if end >= start else None)
        if end >= start:  # the phase's plan, at the top of its first slide's notes
            first = b.slides[start - 1]
            head = f"{p['phase']} ({p['minutes']} min)." + (f" {p['teacher']}" if p["teacher"] else "")
            first.notes = K.plain(head + ("\n\n" + first.notes if first.notes else ""))
    warnings += b.warnings
    if ws:
        warnings += answer_leaks(ws, L["walk"], [(i + 1, b.slides[i]) for i in teaching])
    title = L["title"]
    K.write_pptx(b.slides, out_dir / "slides.pptx", title)
    K.write_pdf(b.slides, out_dir / "slides.pdf", title, measure)
    if measure.missing:
        warnings.append(f"slides.pdf can't show {' '.join(sorted(measure.missing))} (no font here has them): they're "
                        "blank in the PDF but fine in slides.pptx, so present from the .pptx")
    report = {"slides": len(b.slides), "ranges": ranges, "phases": [p["phase"] for p in L["sequence"]],
              "warnings": warnings, "files": ["lesson-plan.docx",
              "slides.pptx", "slides.pdf"]}

    if ws:
        g = DK.Builder(theme, L["grade"], measure, images / "go-over", base)
        g.title_slide(f"Going over: {ws.title}", "", chip)
        walkthrough(g, ws, ws.questions, L["walk"])
        report["warnings"] += [f"go-over {w}" for w in g.warnings if w not in b.warnings]
        K.write_pptx(g.slides, out_dir / "go-over.pptx", f"Going over: {ws.title}")
        K.write_pdf(g.slides, out_dir / "go-over.pdf", f"Going over: {ws.title}", measure)
        WK.answer_key(ws, out_dir / "answer-key.pdf", {q: w.get("drawing") for q, w in L["walk"].items()},
                      models={q: w["model"] for q, w in L["walk"].items() if w.get("model")})
        if ws.folder.resolve() != out_dir.resolve():  # everything to print, in one place
            shutil.copy(ws.folder / "worksheet.pdf", out_dir / "worksheet.pdf")
        report["go_over"] = len(g.slides)
        report["files"] += ["go-over.pptx", "go-over.pdf", "answer-key.pdf", "worksheet.pdf"]

    plan(L, ws, ranges, len(b.slides), theme, out_dir / "lesson-plan.docx")
    return report


_SHINGLE = 6  # words in a row that make a written answer recognizable


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$.%/]+", K.plain(text).lower().replace("\u00a0", " "))


def answer_leaks(ws: WK.Worksheet, walk: dict, slides: list[tuple[int, K.Slide]]) -> list[str]:
    """Teaching slides that show a worksheet answer: the worksheet then checks copying, not understanding.
    Words students are learning (labels, blanks) are fine; final answers, the right choice, and written
    answers are not."""
    out = []
    for n, slide in slides:
        text = " ".join(r.text for e in slide.elements if isinstance(e, K.Text) and e.role != "title"
                        for para in e.paras for r in para.runs).replace("\u00a0", " ")
        words = _words(text)
        flat = " " + " ".join(words) + " "
        for q in ws.questions:
            item = ws.items[q]
            found = None
            if item["type"] in ("math", "draw") and item.get("answer"):
                for a in [item["answer"], *item.get("accept", [])]:
                    a = " ".join(_words(a))
                    if (len(a) >= 3 or re.search(r"[$./]", a)) and f" {a} " in flat:
                        found = a
                        break
            elif item["type"] == "choice":
                right = next((o["text"] for o in item["options"] if o["letter"] == item["answer"]), "")
                if len(right.split()) >= 3 and f" {' '.join(_words(right))} " in flat:
                    found = right
            elif item["type"] == "short":
                for source in (walk.get(q, {}).get("model", ""), item["key"]):
                    sw = _words(source)
                    for i in range(len(sw) - _SHINGLE + 1):
                        piece = " ".join(sw[i:i + _SHINGLE])
                        if f" {piece} " in flat:
                            found = piece
                            break
                    if found:
                        break
            if found:
                out.append(f"slide {n} ({slide.title}) shows question {q}'s answer (\"{found}\"): teach it with "
                           "different numbers or a different text, so the worksheet still shows what students can do")
    return out


def _span(r) -> str:
    if not r:
        return ""
    return str(r[0]) if r[0] == r[1] else f"{r[0]}-{r[1]}"


def _slide_questions(L: dict) -> list[tuple[str, dict]]:
    return [(p["phase"], s) for p in L["sequence"] for s in p["slides"] if s["type"] == "question"]


def plan(L: dict, ws: WK.Worksheet | None, ranges: list, n_slides: int, theme: K.Theme, path: Path) -> None:
    """The plan a teacher, a substitute, or an administrator reads: prep first, then the lesson, then what
    happens after class, then the worksheet's answers."""
    doc = WF.Doc(theme.accent, theme.tint)
    doc.title(L["title"])
    doc.para(" · ".join(x for x in (L["subject"], L["grade_band"], f"{L['minutes']} minutes") if x),
             color="5F6670", after=40)
    files = [f"slides.pptx ({n_slides} slides)"]
    if ws:
        files += ["worksheet.pdf", "answer-key.pdf", "go-over.pptx"]
    doc.para("Goes with " + ", ".join(files[:-1]) + (", and " if len(files) > 1 else "") + files[-1] + ".",
             italic=True, color="5F6670", size=9.5)

    doc.heading("Before class")
    prep = []
    if ws:
        pages = len(S.form_pages(ws.layout))
        forms = [f for f in ws.layout.get("forms", []) if f["id"]]
        versions = [f for f in forms if f["kind"] == "version"]
        if any(f["kind"] == "variant" for f in forms):
            prep.append(f"Print copies.pdf once: a different copy of \"{ws.title}\" for each student "
                        f"({sum(f['kind'] == 'variant' for f in forms)} copies). Hand them out in any order.")
        else:
            prep.append(f"Print the worksheet, \"{ws.title}\" (worksheet.pdf): one copy per student, {pages} page"
                        + ("s, double-sided" if pages > 1 else "") + (", minus the versions below" if versions else "")
                        + ".")
        for f in versions:
            prep.append(f"Print version {f['label']} ({f['name']}, versions/{f['id']}.pdf)"
                        + (f": {f['copies']} cop{'ies' if f['copies'] != 1 else 'y'}" if f.get("copies") else "")
                        + " for the students who need it. Every version is marked from the same scan.")
        prep.append("Have the class ID list handy: students write their class ID number on the worksheet, never "
                    "their name. A substitute needs it too.")
    for p in L["sequence"]:
        if p.get("_review"):
            prep.append(f"Bring the marked copies of \"{p['_review']['ws'].title}\" (returned.pdf in its marking "
                        f"folder) to hand back during {p['phase']}: students fix one mistake on them.")
    prep.append(f"Open slides.pptx ({n_slides} slides; slides.pdf is the same deck). What to say is in the speaker notes.")
    prep += L["materials"]
    doc.bullets(prep)

    doc.heading("Learning objectives")
    doc.bullets(L["objectives"])
    if L["targets"] != L["objectives"]:
        doc.para("On the slides, for students:", bold=True, after=40)
        doc.bullets(L["targets"])
    if L["standards"]:
        doc.heading("Standards")
        doc.bullets(L["standards"])

    if L["vocabulary"]:
        doc.heading("Vocabulary")
        rows = [["Term", "Meaning", "Example"]] + [[v["term"], v["meaning"], v.get("example", "")]
                                                   for v in L["vocabulary"]]
        if not any(v.get("example") for v in L["vocabulary"]):
            rows = [r[:2] for r in rows]
        doc.table(rows, [1.5, 5.5] if len(rows[0]) == 2 else [1.4, 3.3, 2.3])

    doc.heading("Lesson sequence")
    rows = [["Time", "Phase", "Teacher", "Students", "Slides"]]
    t = 0
    for i, (p, r) in enumerate(zip(L["sequence"], ranges)):
        what = p["teacher"]
        handed = re.search(r"\bhand(?:ed|ing|s)? (?:\w+ )?out\b|\bpass(?:ed|es)? (?:\w+ )?out\b|\bdistribut",
                           " ".join(x["teacher"] for x in L["sequence"][:i + 1]), re.I)
        if p["worksheet"] and ws:
            what = ("" if handed else f"Hand out \"{ws.title}\". ") + \
                "Students write their class ID number, not their name." + ("\n\n" + what if what else "")
        if p["walkthrough"] and any(x["worksheet"] for x in L["sequence"][:i]):
            what = "Collect the worksheets first." + ("\n\n" + what if what else "")
        rows.append([f"{t}-{t + p['minutes']} min", p["phase"], what, p["students"], _span(r)])
        t += p["minutes"]
    if t < L["minutes"]:
        rows.append([f"{t}-{L['minutes']} min", "Buffer", "Transitions, or time to finish.", "", ""])
    doc.table(rows, [0.8, 1.1, 2.6, 1.9, 0.6])

    questions = _slide_questions(L)
    if questions:
        doc.heading("Questions on the slides")
        for phase, q in questions:
            line = f"**{phase}:** {K.plain(q['prompt'])}"
            if q.get("choices"):
                labels = "12345678" if q.get("choice_labels") == "numbers" else "ABCDEFGH"
                line += " " + "; ".join(f"{labels[k]}. {c}" for k, c in enumerate(q["choices"]))
            if q.get("answer"):
                line += f" **Answer:** {_period(K.plain(str(q['answer'])))}" + (f" {K.plain(q['why'])}" if q.get("why") else "")
            doc.bullets([line])
    if L["checks"]:
        doc.heading("Checks for understanding")
        doc.bullets(L["checks"])
    if L["misconceptions"]:
        doc.heading("Misconceptions to watch for")
        doc.table([["Misconception", "How to respond"]] + [[m["misconception"], m["response"]]
                                                          for m in L["misconceptions"]], [3.0, 4.0])
    if any(L["differentiation"].get(k) for k in ("support", "extension", "language")):
        doc.heading("Differentiation")
        for name, label in (("support", "Support"), ("extension", "Extension"), ("language", "Multilingual learners")):
            if L["differentiation"].get(name):
                doc.heading(label, 2)
                doc.bullets(L["differentiation"][name])
    accommodations = list(L["differentiation"].get("accommodations", []))
    if ws:
        accommodations.append("Extended time: a student can finish the worksheet later. Collect it then, and go over "
                              "it only once everyone's sheet is in.")
    if accommodations:
        doc.heading("Accommodations (IEP and 504 plans)")
        doc.bullets(accommodations)

    doc.heading("Assessment")
    if L["assessment"]:
        doc.para(L["assessment"])
    if ws:
        n = len(ws.questions)
        points = sum(i["points"] for i in ws.items.values())
        doc.para(f"The worksheet: {n} question{'s' if n != 1 else ''}, {points:g} points. Answers and scoring are "
                 "at the end of this plan and in answer-key.pdf.")
        doc.heading("After class")
        doc.numbered(["Collect every worksheet, including any finished later.",
                      "Scan the stack on the copier, in any order, and give the PDF to Claude: \"Mark this scan of "
                      f"{ws.title}.\" Each student gets their own sheet back with a comment beside every answer.",
                      "Hand back the marked sheets. Students fix their mistakes on them.",
                      "Go over it: go-over.pptx shows every question, then its answer. After marking, Claude can "
                      "make a shorter deck from what the class actually missed (\"make slides to go over what they "
                      "missed\"); use that one if you have it."])
    if L["homework"]:
        doc.heading("Homework")
        doc.para(L["homework"])
    if L["notes"]:
        doc.heading("Notes")
        doc.para(L["notes"])

    if ws:
        doc.page_break()
        doc.heading("Worksheet answers")
        for q in ws.questions:
            item, spec = ws.items[q], L["walk"].get(q, {})
            pts = item["points"]
            doc.heading(f"Question {q} ({pts:g} point{'s' if pts != 1 else ''})", 2)
            doc.para(" ".join(item["prompt"].split()), italic=True, color="5F6670", markup=False)
            for line in WK.key_lines(item):
                label, _, rest = line.partition(": ")
                doc.labeled(label, rest)
            if item.get("rubric"):
                doc.bullets([f"{c.get('short') or c['criterion']}: "
                             + "; ".join(f"{n} {lvl}" for n, lvl in enumerate(c["levels"])) for c in item["rubric"]],
                            markup=False)
            if spec.get("model"):
                doc.para(f"**A strong answer:** {spec['model']}")
            if spec.get("idea"):
                doc.para(f"**Key idea:** {spec['idea']}")
            if spec.get("steps"):
                doc.numbered(spec["steps"])
            if spec.get("mistakes"):
                doc.para("**Watch for:** " + " ".join(spec["mistakes"]))
    doc.save(path, L["title"])
