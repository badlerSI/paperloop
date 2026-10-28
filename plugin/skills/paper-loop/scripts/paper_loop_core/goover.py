"""The go-over deck after marking: what the class missed, first.

Reads a marking run's results.json (written by `check`) and builds slides from it: how each question went,
then the questions the class missed most, first, with a slide each for the question (with how the class
answered) and its answer worked through. Explanations come from the lesson file's walkthrough, if there
is one, and from Claude's notes on what it saw while marking (WORK/goover.json).

Only class totals appear. A wrong answer is shown only when two or more students gave it, so nothing on
the projector points at one student.
"""

from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from pathlib import Path

from . import deck as DK
from . import lesson as LS
from . import sheet as S
from . import slides as K
from . import walk as WK
from .deck import LessonError
from .slides import MUTED, Bars, Para, Run

GOT_IT = 0.85  # this share of full credit or more: on the "got it" slide, not gone over


def stats(results: dict, ws: WK.Worksheet) -> dict[int, dict]:
    """Per question: students, full and partial credit, blanks, and the answers given."""
    out = {q: {"n": 0, "full": 0, "partial": 0, "blank": 0, "picks": Counter(), "wrong": Counter(),
               "boxes": Counter(), "crops": []} for q in ws.questions}
    seen = set()
    for page in results["pages"]:
        for b in page["boxes"]:
            q = b["q"]
            if q not in out or (page["student_id"], q) in seen:
                continue
            seen.add((page["student_id"], q))
            st = out[q]
            st["n"] += 1
            verdict = b["verdict"]
            if verdict == "correct":
                st["full"] += 1
            elif verdict == "partial":
                st["partial"] += 1
            elif verdict == "blank":
                st["blank"] += 1
            if verdict not in ("correct", "blank") and b.get("crop"):
                st["crops"] += [b["crop"], *b.get("more_crops", [])]
            if b["type"] == "choice":
                d = (b["details"] or [{}])[0]
                st["picks"][d.get("base_selected") or d.get("selected") or "blank"] += 1  # base copy's letters
                continue
            if ws.items[q].get("varies"):
                continue  # each copy had its own numbers: no answers in common to show
            for d in b["details"]:
                read = str(d.get("read") or "").strip()
                if d.get("verdict") == "incorrect" and read:
                    st["wrong"][(d.get("n"), _norm(read))] += 1
                    if d.get("n") is not None:
                        st["boxes"][d["n"]] += 1
    return out


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _assignment(work: Path, manifest: dict) -> Path:
    """The assignment folder: where the manifest says, or beside the work folder if the teacher moved both."""
    folder = Path(manifest["assignment_dir"])
    if not (folder / "layout.json").exists() and (work.parent / folder.name / "layout.json").exists():
        return work.parent / folder.name
    return folder


def _prepare(work: Path, lesson_path: Path | None = None) -> dict:
    """A marked class, ready to go over: its worksheet, how each question went, and the explanations."""
    work = Path(work)
    if not (work / "results.json").exists():
        raise LessonError(f"{work} has no results.json yet: run `check` until the marks are clean")
    manifest = S.read_json(work / "manifest.json")
    folder = _assignment(work, manifest)
    ws = WK.Worksheet(folder)
    results = S.read_json(work / "results.json")
    walk: dict[int, dict] = {}
    subject, grade_band = ws.key.get("subject", ""), ws.key.get("grade_band", "")
    if lesson_path:
        L = LS.normalize(S.read_json(lesson_path))
        if L["worksheet"] and Path(L["worksheet"]).name != ws.layout["assignment_id"]:
            raise LessonError(f"the lesson is for worksheet {Path(L['worksheet']).name}, but this scan is of "
                              f"{ws.layout['assignment_id']}")
        walk = {q: dict(w) for q, w in L["walk"].items()}
        subject, grade_band = L["subject"] or subject, L["grade_band"]
    notes_path = work / "goover.json"
    if notes_path.exists():
        notes = S.read_json(notes_path)
        for k, w in enumerate(notes.get("questions", []), start=1):
            if not isinstance(w, dict) or not isinstance(w.get("q"), int):
                raise LessonError(f"goover.json: question {k} needs \"q\", the question's number")
            for name in ("steps", "mistakes"):
                w[name] = LS._strings(w, f"goover.json question {w['q']}", name)
            walk[w["q"]] = {**walk.get(w["q"], {}), **{key: v for key, v in w.items() if v not in ("", [])}}
    for q, spec in walk.items():
        if q not in ws.items:
            raise LessonError(f"there's an explanation for question {q}, but the worksheet has questions "
                              f"{', '.join(map(str, ws.questions))}")
        if spec.get("draw"):
            try:
                spec["drawing"] = ws.answer_drawing(q, spec["draw"])
            except ValueError as e:
                raise LessonError(str(e)) from None
    st = stats(results, ws)
    marked = [q for q in ws.questions if st[q]["n"]]
    if not marked:
        raise LessonError("results.json has no marked answers")
    share = {q: st[q]["full"] / st[q]["n"] for q in marked}
    missed = sorted((q for q in marked if share[q] < GOT_IT), key=lambda q: (share[q], q))
    got_it = [q for q in marked if share[q] >= GOT_IT]
    return {"work": work, "ws": ws, "folder": folder, "walk": walk, "st": st, "marked": marked, "share": share,
            "missed": missed, "got_it": got_it, "subject": subject, "grade_band": grade_band}


def texts(ctx: dict) -> list[str]:
    """Every string the go-over slides may print, for choosing fonts."""
    ws = ctx["ws"]
    return DK._strings(ctx["walk"]) + [i["prompt"] for i in ws.items.values()] + [i["key"] for i in ws.items.values()]


def build(work: Path, lesson_path: Path | None = None, out: Path | None = None, most: int | None = None) -> dict:
    """most: go over only this many questions, the most missed."""
    ctx = _prepare(work, lesson_path)
    go_over = ctx["missed"][:most] if most else ctx["missed"]
    measure = K.Measure(texts(ctx))
    theme = K.theme_for(ctx["subject"])
    work = ctx["work"]
    out = Path(out) if out else work / "out"
    shutil.rmtree(out / "go-over-images", ignore_errors=True)  # from an earlier version, which kept them
    images = Path(tempfile.mkdtemp(prefix="paper-loop-goover-"))
    try:
        return _build(ctx, go_over, measure, theme, out, images)
    finally:
        shutil.rmtree(images, ignore_errors=True)


def _questions(b: DK.Builder, ctx: dict, go_over: list[int]) -> None:
    """For each question gone over: the question as printed, with how the class answered, then its answer."""
    ws, st, walk = ctx["ws"], ctx["st"], ctx["walk"]
    shown = set()
    for q in go_over:
        pid = ws.items[q].get("passage")
        if pid and (pid in ws.passages or ws.passage(pid)) and pid not in shown:
            b.walk_passage(ws, pid, [x for x in go_over if ws.items[x].get("passage") == pid])
            shown.add(pid)
        spec = walk.get(q, {})
        b.walk_question(ws, q, spec, chip=f"{st[q]['full']} of {st[q]['n']} got it", notes=_notes(ws, q, st[q], spec),
                        side_extra=lambda s, x, y, w, h, q=q, spec=spec: class_panel(b, ws, q, st[q], spec, s, x, y, w, h),
                        words=int(b.sz["words"] * 1.3))
        b.walk_answer(ws, q, spec, notes=LS._answer_notes(ws, q, spec))


def _warnings(ctx: dict, go_over: list[int], todo: Path) -> list[str]:
    walk = ctx["walk"]
    unexplained = [q for q in go_over if not walk.get(q, {}).get("steps") and not walk.get(q, {}).get("idea")]
    unseen = [q for q in go_over if not walk.get(q, {}).get("saw")]
    warnings = []
    if unexplained:
        warnings.append(f"no explanation for question{'s' if len(unexplained) > 1 else ''} "
                        f"{', '.join(map(str, unexplained))}: its answer slide shows only the key. Add \"idea\", "
                        "\"steps\", and \"mistakes\" to goover.json")
    if unseen:
        warnings.append(f"no \"saw\" for question{'s' if len(unseen) > 1 else ''} {', '.join(map(str, unseen))}: "
                        f"{todo} lists the answers that missed, to look at")
    return warnings


def _build(ctx: dict, go_over: list[int], measure, theme, out: Path, images: Path) -> dict:
    ws, st, marked = ctx["ws"], ctx["st"], ctx["marked"]
    grade = S.grade_of({"grade_band": ctx["grade_band"], "grade": ws.key.get("grade")})
    b = DK.Builder(theme, grade, measure, images, ctx["folder"])
    chip = " · ".join(x[:1].upper() + x[1:] for x in (ctx["subject"], ctx["grade_band"]) if x)
    b.title_slide(f"Going over: {ws.title}", "", chip)
    overview(b, ws, st, marked, go_over)
    if ctx["got_it"]:
        nailed(b, ws, st, ctx["got_it"], ctx["walk"])
    _questions(b, ctx, go_over)
    fix_it(b)
    title = f"Going over: {ws.title}"
    K.write_pptx(b.slides, out / "go-over.pptx", title)
    K.write_pdf(b.slides, out / "go-over.pdf", title, measure)
    todo = out / "go-over-todo.md"
    _todo(todo, ws, st, go_over, ctx["walk"], ctx["share"])
    return {"slides": len(b.slides), "go_over": go_over, "got_it": ctx["got_it"],
            "left_out": ctx["missed"][len(go_over):], "warnings": list(b.warnings) + _warnings(ctx, go_over, todo),
            "share": ctx["share"], "students": max(st[q]["n"] for q in marked), "out": out}


def review(b: DK.Builder, ctx: dict, most: int | None = None) -> dict:
    """The go-over of an earlier worksheet, inside another deck (the next day's lesson): how it went, the
    most-missed questions with how the class answered, and a slide for fixing mistakes on the marked copy."""
    ws, st = ctx["ws"], ctx["st"]
    go_over = ctx["missed"][:most] if most else ctx["missed"]
    overview(b, ws, st, ctx["marked"], go_over, title=f"How \u201c{ws.title}\u201d went")
    _questions(b, ctx, go_over)
    fix_it(b)
    todo = Path(ctx["work"]) / "out" / "go-over-todo.md"
    _todo(todo, ws, st, go_over, ctx["walk"], ctx["share"])
    return {"go_over": go_over, "got_it": ctx["got_it"], "left_out": ctx["missed"][len(go_over):],
            "warnings": _warnings(ctx, go_over, todo), "title": ws.title}


def fix_it(b: DK.Builder) -> None:
    """Feedback works when students use it: a few minutes to fix one mistake on their own marked copy."""
    s = b.new("Fix it", "Hand back the marked sheets before this slide. Give 3 to 5 minutes. Walk around: a fix "
                        "that explains why is worth more than a new answer. Collect them again if you want to see "
                        "the fixes, or have partners check each other's.")
    top = b.heading(s, "Fix it", "On your marked sheet", chip_fill=b.t.dark)
    size = b.sz["body"]
    points = ["Find **one question** with a comment.", "Read the comment, then **redo it** beside the box.",
              "Write **one sentence**: what you'll do differently next time.", "Done? Check a partner's fix."]
    b.text(s, DK.X0, top, DK.X1 - DK.X0, DK.BOTTOM - top, b.bullets(points, size), size, b.sz["dense"])
    b.finish(s)


def _todo(path: Path, ws: WK.Worksheet, st: dict, go_over: list[int], walk: dict, share: dict) -> None:
    """What goover.json needs, and the crops of the answers that missed, for a session that didn't mark."""
    lines = [f"# Going over {ws.title}", "",
             "Write goover.json in the marking folder: for each question below, `saw` (one or two sentences to the class "
             "about the most common mistake, naming no one), and `idea`, `steps`, and `mistakes` if there's no lesson "
             "file. For a written question, add `model`: a short model answer for the answer slide, which otherwise "
             "shows the whole marking key. If you didn't mark this scan in this session, look at the crops listed "
             "under each question first. Then run `goover` again.", ""]
    for q in go_over:
        item, s = ws.items[q], st[q]
        lines += [f"## Question {q} ({share[q]:.0%} full credit): {item['prompt']}", "",
                  f"Key: {ws.answer_text(q)}", ""]
        common = [f"\"{read}\"" + (f" in box {n}" if n is not None else "") + f": {c} students"
                  for (n, read), c in s["wrong"].most_common(5) if c >= 2]
        if common:
            lines += ["Wrong answers two or more gave: " + "; ".join(common), ""]
        if s["picks"]:
            lines += ["Letters chosen: " + ", ".join(f"{k} {v}" for k, v in sorted(s["picks"].items())), ""]
        if walk.get(q, {}).get("saw"):
            lines += [f"Already in goover.json: {walk[q]['saw']}", ""]
        lines += ["Answers that missed (crops):", *[f"- `{c}`" for c in s["crops"][:30]], ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def overview(b: DK.Builder, ws: WK.Worksheet, st: dict, marked: list[int], go_over: list[int],
             title: str = "How it went") -> None:
    order = ", ".join(f"question {q}" for q in go_over)
    note = ("Full credit on each question. " + (f"Next, most missed first: {order}." if go_over else
                                                 "Every question was 85% or better.")
            + (" The darker bars are the ones we'll go over." if 0 < len(go_over) < len(marked) else ""))
    s = b.new(title, note)
    top = b.heading(s, title, "Full credit", chip_fill=b.t.dark)
    labels = [f"Q{q}" for q in marked]
    values = [round(100 * st[q]["full"] / st[q]["n"]) for q in marked]
    colors = [b.t.accent if q in go_over else b.t.soft for q in marked]
    h = min(DK.BOTTOM - top, 56 * len(marked) + 20)
    s.elements.append(Bars(DK.X0, top, DK.X1 - DK.X0, h, labels, values, colors, b.sz["small"], K.INK, "%"))
    b.finish(s)


def nailed(b: DK.Builder, ws: WK.Worksheet, st: dict, qs: list[int], walk: dict) -> None:
    s = b.new("You've got these")
    top = b.heading(s, "You've got these")
    points = []
    for q in qs:
        item = ws.items[q]
        short = ws.answer_text(q) if item["type"] in ("choice", "math") else ""  # never a whole marking key
        idea = walk.get(q, {}).get("idea") or short
        points.append(f"**Question {q}** ({st[q]['full']} of {st[q]['n']})" + (f": {idea}" if idea else ""))
    size = b.sz["body"]
    b.text(s, DK.X0, top, DK.X1 - DK.X0, DK.BOTTOM - top, b.bullets(points, size), size, b.sz["dense"])
    b.finish(s)


def class_panel(b: DK.Builder, ws: WK.Worksheet, q: int, st: dict, spec: dict, s: K.Slide, x: float, y: float,
                w: float, h: float) -> float:
    """How the class answered, beside or below the question. Returns where the text after it can start."""
    size = b.sz["dense"]
    item = ws.items[q]
    bottom = y + h
    if item["type"] == "choice":  # one color: the answer comes on the next slide
        letters = [o["letter"] for o in item["options"]]
        labels = letters + (["blank"] if st["picks"].get("blank") else [])
        values = [st["picks"].get(lbl, 0) for lbl in labels]
        colors = [b.t.accent] * len(labels)
    else:
        labels = ["Full credit", "Partial", "Not yet", "Blank"]
        not_yet = st["n"] - st["full"] - st["partial"] - st["blank"]
        values = [st["full"], st["partial"], not_yet, st["blank"]]
        labels, values = zip(*[(lbl, v) for lbl, v in zip(labels, values) if v or lbl == "Full credit"])
        labels, values = list(labels), list(values)
        colors = [b.t.accent] + ["B8BEC6"] * (len(labels) - 1)
    chart_h = min(max(h * 0.55, 30 * len(labels)), 34 * len(labels) + 10)
    wide = w >= 700  # below a strip-shaped question: the chart on the left, the words beside it
    chart_w = 400.0 if wide else w
    s.elements.append(Bars(x, y, chart_w, chart_h, labels, values, colors, size, K.INK))
    tx, ty, tw = (x + chart_w + 30, y, w - chart_w - 30) if wide else (x, y + chart_h + 14, w)
    lines = []
    common = [(n, read, c) for (n, read), c in st["wrong"].most_common(3) if c >= 2]
    if common:
        said = "; ".join(f"{c} wrote \"{read}\"" + (f" in box {n}" if n is not None else "") for n, read, c in common)
        lines.append(Para([Run("Common wrong answers: ", bold=True), *K.runs(f"{said}.", markup=False)],
                          space_after=size * 0.5))
    if spec.get("saw"):
        lines.append(Para(K.runs(f"**What I noticed:** {spec['saw']}", MUTED)))
    if item.get("varies"):
        lines.append(Para(K.runs("Everyone had their own numbers. This is one version.", MUTED)))
    end = (y + chart_h) if wide else ty
    if lines:
        t = b.text(s, tx, ty, tw, max(bottom - ty, size * 1.2), lines, size, size - 2)
        end = max(end, ty + t.h)
    return end + 10


def _notes(ws: WK.Worksheet, q: int, st: dict, spec: dict) -> str:
    parts = [f"{st['full']} of {st['n']} students got full credit"
             + (f", {st['partial']} partial" if st["partial"] else "")
             + (f", {st['blank']} left it blank" if st["blank"] else "") + "."]
    if spec.get("saw"):
        parts.append(f"What I noticed while marking: {spec['saw']}")
    if ws.items[q].get("varies"):
        parts.append("Each student had a different copy of this question; the slide shows the base copy. Ask "
                     "students to check their own numbers against these steps.")
    if spec.get("think"):
        parts.append(f"Ask: {spec['think']}")
    if spec.get("ask"):
        parts.append(spec["ask"])
    return "\n\n".join(K.plain(p) for p in parts)
