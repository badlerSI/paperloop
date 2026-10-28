"""Practice sheets after marking: each student gets another try at the questions they missed.

Feedback works when students use it. A practice sheet gives each student up to three questions they didn't
get full credit on, each with the comment they got last time printed above it, and with new numbers where
the worksheet has variables (or another item from its pool), so the fix is theirs and not a copy. A
student who worked on a version (support, large print, a home language) practices on that version.

Each sheet is made for one student, with their class ID printed in its boxes, so a scan of the practice
routes itself. Questions keep their numbers from the worksheet, so progress reports count the practice
toward the same skills.
"""

from __future__ import annotations

import random
import zlib
import re
from datetime import date
from pathlib import Path

from . import forms as FM
from . import sheet as S
from .deck import LessonError


def _assignment(work: Path, manifest: dict) -> Path:
    folder = Path(manifest["assignment_dir"])
    for candidate in (folder, work.parent / folder.name, work.parent):
        if (candidate / "layout.json").exists():
            return candidate
    raise LessonError(f"can't find the worksheet folder for {work} (it was {folder})")


def _fresh(question: dict, avoid: str, seed: str) -> dict:
    """The question with other values for its variables, or another item from its pool, than the prompt the
    student already saw. As written when it has neither."""
    rng = random.Random(seed)
    alternatives = [FM._strip(question)] + [{**FM._strip(question), **alt} for alt in question.get("pool", [])]
    rng.shuffle(alternatives)
    if question.get("vars"):
        _, allowed = FM._assignments(question, f"question {question['q']}")
        rng.shuffle(allowed)
        options = [FM._fill(alt, values) for alt in alternatives for values in allowed[:20]]
    else:
        options = alternatives
    chosen = next((o for o in options if o.get("prompt") != avoid), options[0])
    return FM._shuffle(chosen, rng)  # a choice's right letter moves, so it isn't A on every practice sheet


def build(work: Path, out: Path | None = None, most: int = 3) -> dict:
    work = Path(work)
    if not (work / "results.json").exists():
        raise LessonError(f"{work} has no results.json yet: run `check` until the marks are clean")
    manifest = S.read_json(work / "manifest.json")
    assignment = _assignment(work, manifest)
    if not (assignment / "source.json").exists():
        raise LessonError(f"{assignment} was made before practice sheets existed: run `make` on its worksheet "
                          "again (the page codes don't change), then try again")
    source = S.read_json(assignment / "source.json")
    key = S.read_json(assignment / "key.json")
    results = S.read_json(work / "results.json")
    expanded = FM.expand(source, assignment)
    forms = {form["id"]: defn for form, defn in expanded}
    metas = {form["id"]: form for form, _ in expanded}
    raw_questions = {q["q"]: q for q in source["questions"] if q.get("type", "short") not in ("passage", "note")}

    notes_path = work / "practice-notes.json"
    written = S.read_json(notes_path) if notes_path.exists() else {}  # Claude's own notes, by ID and question
    todo, left_off = [], {}
    by_student: dict[str, dict] = {}
    for page in results["pages"]:
        st = by_student.setdefault(page["student_id"], {"form": page.get("form", ""), "boxes": []})
        st["boxes"] += page["boxes"]
    sheets, all_right, absent = [], [], []
    for sid in sorted(by_student):
        st = by_student[sid]
        boxes = [b for b in st["boxes"] if b.get("points_possible")]
        if all(b["verdict"] == "blank" for b in boxes):
            absent.append(sid)
            continue
        missed = sorted((b for b in boxes if b["verdict"] != "correct"),
                        key=lambda b: (b["points_awarded"] / b["points_possible"], b["q"]))
        if len(missed) > most:
            left_off[sid] = sorted(b["q"] for b in missed[most:])
        missed = missed[:most]
        if not missed:
            all_right.append(sid)
            continue
        defn = forms.get(st["form"]) or forms[""]
        printed = {q["q"]: q for q in defn["questions"] if q.get("type", "short") not in ("passage", "note")}
        meta = metas.get(st["form"], {})
        variant = meta.get("kind") == "variant"
        questions, passages = [], set()
        for b in sorted(missed, key=lambda b: b["q"]):
            old = S.form_items(key, st["form"])[b["q"]]
            if variant or st["form"] == "":  # new numbers or another item where the worksheet has them
                q = _fresh(raw_questions[b["q"]], old["prompt"], f"{sid}-{b['q']}")
            else:  # a version: the same question, with the version's supports
                q = dict(printed[b["q"]])
            changed = q.get("prompt") != old["prompt"]
            if not changed and q.get("type") == "choice":
                changed = q.get("options") != old.get("options")
            if not changed:  # the same question again: a retry, which progress reports don't count as new
                q["retry"] = True
            q.pop("support", None)
            # Practice counts toward the same skill: the question's own, or the worksheet's title.
            q["skill"] = old.get("skill") or q.get("skill") or manifest.get("title") or source["title"]
            pid = q.get("passage")
            if pid and pid not in passages:
                passage = next((p for p in defn["questions"] if p.get("type") == "passage" and p.get("id") == pid), None)
                if passage:
                    questions.append(passage)
                    passages.add(pid)
            last = b["comment"] or ("No answer yet." if b["verdict"] == "blank" else "")
            mine = (written.get(sid) or {}).get(str(b["q"]))
            if mine:
                q["asides"] = [{"kind": "last", "text": mine}] + list(q.get("asides", []))
            elif last:  # last time's comment; with new numbers it may name the old ones, so it says so
                q["asides"] = [{"kind": "last_other" if changed else "last", "text": last}] + list(q.get("asides", []))
                if changed and re.search(r"\d", last):
                    todo.append((sid, b["q"], last, q.get("prompt", "")))
            questions.append(q)
        sheet = {"student_id": sid, "questions": questions}
        if meta.get("kind") == "version":  # practice on the version they had: its print size and languages
            sheet.update({k: meta[k] for k in ("print", "comment_language", "language", "language_name",
                                                "language_english") if meta.get(k)})
        sheets.append(sheet)
    if not sheets:
        raise LessonError("every student got full credit on every question (or left it all blank): no practice "
                          "to make")

    day = date.today().isoformat()
    # Named for the marking it came from, so two classes' practice on one day never share a page code.
    tag = f"{zlib.crc32(str(work.resolve()).encode()) & 0xFFFF:04x}"
    practice = {**{k: v for k, v in source.items() if k not in ("versions", "variants", "personal", "questions")},
                "assignment_id": f"{key['assignment_id']}-practice-{day}-{tag}", "practice_of": str(work.resolve()),
                "title": f"Practice: {manifest.get('title') or source['title']}",
                "instructions": "A few questions to try again. Your ID is already printed. Read last time's note "
                                "first.",
                "questions": [{k: v for k, v in q.items() if k not in ("vars", "where", "pool", "support")}
                              for q in forms[""]["questions"]],
                "personal": sheets}
    out = Path(out or assignment.parent / f"{key['assignment_id']}-practice-{day}-{tag}")
    earlier = out / "source.json"
    if earlier.exists() and S.read_json(earlier).get("practice_of") != str(work.resolve()):
        raise LessonError(f"{out} holds practice sheets from another marking; choose another --out")
    S.make_worksheet(practice, out, base=assignment)
    todo_path = work / "practice-todo.md"
    if todo:
        lines = ["# Practice notes", "",
                 f"These comments from marking name numbers from the student's old copy, but the practice question "
                 f"has new ones. Write `{notes_path}` with a short note for each: what to watch for, in the words "
                 "you'd say to the student, with no numbers from the old copy. Then run `practice` again.", "",
                 "```json", '{"<ID>": {"<question number>": "Multiply both parts by the same number."}}', "```", ""]
        for sid, qn, last, prompt in todo:
            lines += [f"- ID {sid}, Q{qn}: last time \"{last}\". Now: {prompt}"]
        todo_path.write_text("\n".join(lines) + "\n")
    elif todo_path.exists():
        todo_path.unlink()
    return {"out": out, "sheets": len(sheets), "all_right": all_right, "absent": absent, "left_off": left_off,
            "todo": todo_path if todo else None,
            "questions": {s["student_id"]: [q["q"] for q in s["questions"] if "q" in q] for s in sheets}}
