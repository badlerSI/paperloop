"""Progress across worksheets: a dashboard for the teacher, a page for each family, and a gradebook file.

Reads every marked class under a folder (each work folder's results.json, with its worksheet's key) and
follows each student, by class ID only, skill by skill. A question's skill is its "skill" in the worksheet
("I can find a unit rate"), or the worksheet's title when it has none. A skill's status is its most recent
attempt: got it (80% or more), getting there (50% or more), or still practicing. A score earned on a
version with hints, worked examples, laid-out steps, or fewer choices is marked "with support", so nobody
mistakes it for the same thing.

Nothing here knows a name. The family page has a line for the teacher to write one in.
"""

from __future__ import annotations

import csv
import html
import json
import re
import string
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from . import sheet as S
from . import wordfile as WF

GOT, GETTING = 0.8, 0.5
STATUS = ("got", "getting", "practicing")
LABELS = {
    "title": "Progress report", "student": "Student", "teacher_id": "class ID",
    "dates": "Work from {start} to {end}", "dates_one": "Work from {start}", "learning": "What we've been learning",
    "support_note": "\u201cWith help on the page\u201d means hints, worked steps, or fewer choices were printed on "
                    "those questions. It shows what your child can do with that help.",
    "interpreter": "You can ask for an interpreter or a translation of this page at no cost. Ask the school office "
                   "or the teacher.",
    "got": "Got it", "getting": "Getting there", "practicing": "Still practicing", "support": "with help on the page",
    "latest": "Most recent: {earned} of {possible} points", "latest_one": "Most recent: {earned} of 1 point",
    "evidence": "{n} questions so far", "evidence_one": "1 question so far",
    "skill": "What it means", "how": "How it's going",
    "feedback": "From your child's latest feedback", "strength": "Going well", "next": "Next",
    "home": "How you can help at home",
    "home_intro": "Ten minutes, a few times a week, makes a difference. Try one of these:",
    "notes": "Notes from the teacher",
    "foot": "This report comes from your child's worksheets, marked with help from an AI tool (Claude) and "
            "reviewed by the teacher. Please ask the teacher about anything on it.",
    "months": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"],
    "date": "{month} {day}",
}


class ProgressError(ValueError):
    pass


def _status(pct: float) -> str:
    return "got" if pct >= GOT else "getting" if pct >= GETTING else "practicing"


def _date(work: Path) -> str:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", work.name)
    if m:
        return m.group(0)
    return datetime.fromtimestamp((work / "results.json").stat().st_mtime).date().isoformat()


def _assignment_dir(work: Path, manifest: dict) -> Path | None:
    folder = Path(manifest["assignment_dir"])
    for candidate in (folder, work.parent / folder.name, work.parent):
        if (candidate / "key.json").exists():
            return candidate
    return None


def class_digits(folder: Path) -> int:
    """How many digits this class's IDs have, from its worksheets (grades 2-3 write 2), so a roster saved by a
    spreadsheet ("7" for "07") reads right."""
    counts = Counter(S.read_json(k).get("id_digits") for k in Path(folder).rglob("key.json"))
    counts.pop(None, None)
    return counts.most_common(1)[0][0] if counts else 4


def collect(folder: Path, roster: set[str] | None = None) -> list[dict]:
    """Every marked worksheet under folder, oldest first: its title, date, key, and each student's answers.
    Every marking of one printed worksheet (one assignment folder) counts as one: two scans, a make-up, a
    re-mark. A student's latest marking wins. The same worksheet made again in another folder is another."""
    runs = []
    for results_path in sorted(Path(folder).rglob("results.json")):
        work = results_path.parent
        if not (work / "manifest.json").exists():
            continue
        manifest = S.read_json(work / "manifest.json")
        assignment = _assignment_dir(work, manifest)
        if assignment is None:
            continue
        key = S.read_json(assignment / "key.json")
        results = S.read_json(results_path)
        source = S.read_json(assignment / "source.json") if (assignment / "source.json").exists() else {}
        title = manifest.get("title", "")
        # A practice sheet's questions count toward the worksheet's own skills, never "Practice: ..."
        base_title = re.sub(r"^(Practice: )+", "", title)
        base_skill = {i["q"]: i.get("skill") for i in key["items"]}
        students: dict[str, dict] = {}
        for page in results["pages"]:
            sid = page["student_id"]
            if roster is not None and sid not in roster:
                continue
            form = page.get("form", "")
            items = S.form_items(key, form)
            st = students.setdefault(sid, {"form": form, "support": False, "answers": {}})
            for b in page["boxes"]:
                item = items.get(b["q"], {})
                if item.get("stretch"):
                    continue  # beyond the worksheet's bar: a miss there says nothing about the skill
                helped = bool(item.get("scaffolded"))  # help on this very question that changes what it measures
                st["support"] = st["support"] or helped
                st["answers"][b["q"]] = {"earned": float(b["points_awarded"]), "possible": float(b["points_possible"]),
                                         "verdict": b["verdict"], "support": helped, "retry": bool(item.get("retry")),
                                         "skill": item.get("skill") or base_skill.get(b["q"]) or base_title}
        # Every answer blank: absent, or the work went on another sheet. Not a zero.
        absent = sorted(sid for sid, st in students.items()
                        if all(a["verdict"] == "blank" for a in st["answers"].values()))
        students = {sid: st for sid, st in students.items() if sid not in absent}
        for st in students.values():  # questions with no page marked (a page still in the review pile)
            form_items = S.form_items(key, st["form"])
            st["missing"] = sorted(q for q, i in form_items.items() if q not in st["answers"] and not i.get("stretch"))
        if not students:
            continue
        summaries = S.read_json(work / "summaries.json") if (work / "summaries.json").exists() else {}
        saw = []
        if (work / "goover.json").exists():
            for spec in S.read_json(work / "goover.json").get("questions", []):
                if spec.get("saw"):
                    saw.append({"q": spec["q"], "saw": spec["saw"]})
        raw = {str(v.get("id")): v for v in source.get("versions", []) if isinstance(v, dict)}
        versions = {fid: {**raw.get(fid, {}), **f} for fid, f in (key.get("forms") or {}).items()
                    if f.get("kind") == "version"}
        marked = results_path.stat().st_mtime
        runs.append({"work": str(work), "works": [str(work)], "assignment_id": key["assignment_id"], "title": title,
                     "assignment_dir": str(assignment.resolve()),
                     "practice": bool(source.get("practice_of")), "marked": marked, "first_marked": marked,
                     "versions": {fid: {"name": f.get("name") or fid, "supports": _supports(f),
                                        "help": list(f.get("modifies") or [])} for fid, f in versions.items()},
                     "date": _date(work), "subject": key.get("subject", ""), "grade_band": key.get("grade_band", ""),
                     "items": [{"q": i["q"], "skill": i.get("skill") or base_title,
                                "points": i["points"], "prompt": i["prompt"]} for i in key["items"]],
                     "students": students, "summaries": summaries, "saw": saw})
    runs.sort(key=lambda r: (r["date"], r["marked"]))
    merged: dict[str, dict] = {}
    for run in runs:  # in marking order, so a re-mark replaces what it re-marked
        first = merged.get(run["assignment_dir"])
        if first is None:
            merged[run["assignment_dir"]] = run
            continue
        first["students"].update(run["students"])
        first["summaries"].update(run["summaries"])
        first["saw"] = run["saw"] or first["saw"]
        first["versions"].update(run["versions"])
        first["works"].append(run["work"])
        first["work"], first["marked"] = run["work"], run["marked"]
    return list(merged.values())


def _supports(form: dict) -> list[str]:
    """A version's supports in plain words, for a case manager's records."""
    out = []
    if form.get("scaffolds"):
        scaffolds = form["scaffolds"]
        plain = {"plain": "plain wording", "hint": "hints", "steps": "the steps laid out", "example": "a worked example",
                 "frame": "sentence starters", "word_bank": "a word bank", "glossary": "key words with meanings"}
        named = ([plain.get(x, x) for x in scaffolds] if isinstance(scaffolds, list) else
                 ["every support" if scaffolds == "all" else str(scaffolds)])
        out.append("supports on the page: " + ", ".join(named))
    lp = form.get("large_print")
    if lp:
        out.append("large print" + ("" if lp is True else f" ({lp}pt)" if isinstance(lp, (int, float)) and lp > 2
                                    else f" ({lp})"))
    if form.get("space"):
        out.append("more room to write" + (f" ({form['space']}x)" if form["space"] is not True else ""))
    if form.get("per_page"):
        out.append(f"at most {form['per_page']} question{'s' if form['per_page'] > 1 else ''} a page")
    if form.get("max_choices"):
        out.append(f"{form['max_choices']} answer choices at most")
    if form.get("grid"):
        out.append("graph paper for work")
    if form.get("work_optional"):
        out.append("work optional: full credit from a correct answer (calculator or scribe)")
    if form.get("only"):
        out.append("shortened: questions " + ", ".join(map(str, form["only"])))
    if form.get("language"):
        out.append(f"{form.get('language_name') or form['language']} ({form.get('language_mode') or 'bilingual'})")
    if form.get("reference"):
        out.append("reference page: " + ", ".join(form["reference"]))
    if form.get("notes"):
        out.append(f"note: {form['notes']}")
    return out


def _supports_csv(runs: list[dict], path: Path) -> int:
    """Which supports each class ID had on each worksheet: the record a case manager keeps. IDs only."""
    rows = []
    for run in runs:
        for sid, st in sorted(run["students"].items()):
            version = run.get("versions", {}).get(st.get("form", ""))
            if version:
                rows.append([sid, run["date"], run["title"], version["name"], "; ".join(version["supports"]),
                             "; ".join(version["help"])])
    if not rows:
        if path.exists():
            path.unlink()  # no one had a version: no log
        return 0
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "date", "worksheet", "version", "supports", "help that changes what's measured"])
        w.writerows(rows)
    return len(rows)


def analyze(runs: list[dict]) -> dict:
    """Per student and skill: every attempt, the latest status, and its trend; per worksheet: how it went."""
    skills: list[str] = []
    attempts: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    worksheets = []
    for run in runs:
        by_q = {i["q"]: i["skill"] for i in run["items"]}
        for skill in [i["skill"] for i in run["items"] if not run.get("practice")] + \
                [_skill(q, a, by_q) for st in run["students"].values() for q, a in st["answers"].items()]:
            if skill and skill not in skills:
                skills.append(skill)
        for sid, st in run["students"].items():
            per_skill: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0, False, True])
            for q, a in st["answers"].items():
                if not _skill(q, a, by_q):
                    continue
                acc = per_skill[_skill(q, a, by_q)]
                acc[0] += a["earned"]
                acc[1] += a["possible"]
                acc[2] += 1
                acc[3] = acc[3] or a["support"]
                acc[4] = acc[4] and a["retry"]
            for skill, (earned, possible, questions, support, retry) in per_skill.items():
                if possible:
                    attempts[sid][skill].append({"date": run["date"], "title": run["title"], "earned": earned,
                                                 "possible": possible, "pct": earned / possible,
                                                 "support": support, "retry": retry, "questions": questions})
        answered = {i["q"]: [st["answers"][i["q"]] for st in run["students"].values() if i["q"] in st["answers"]]
                    for i in run["items"]}  # out of those who had it: a shortened version or a practice sheet skips some
        n = len(run["students"])
        earned = sum(a["earned"] for st in run["students"].values() for a in st["answers"].values())
        possible = sum(a["possible"] for st in run["students"].values() for a in st["answers"].values())
        worksheets.append({"title": run["title"], "date": run["date"], "students": n, "practice": run.get("practice", False),
                           "average": earned / possible if possible else 0,
                           "questions": [{"q": i["q"], "skill": i["skill"], "prompt": _short(i.get("prompt", "")),
                                          "answered": len(answered[i["q"]]),
                                          "full": (sum(a["verdict"] == "correct" for a in answered[i["q"]])
                                                   / len(answered[i["q"]])) if answered[i["q"]] else 0}
                                         for i in run["items"] if answered[i["q"]] or not run.get("practice")],
                           "saw": run["saw"], "supported": sum(st["support"] for st in run["students"].values()),
                           "on_version": sum(st["form"] in run.get("versions", {}) for st in run["students"].values())})
    students = {}
    for sid in sorted(attempts):
        cells = {}
        for skill, tries in attempts[sid].items():
            # The latest new evidence: a retry of the very same question (a practice sheet without new numbers)
            # shows in the attempts but doesn't set the status.
            counted = [t for t in tries if not t.get("retry")] or tries
            last = counted[-1]
            trend = 0 if len(counted) < 2 else (1 if last["pct"] > counted[-2]["pct"] + 0.05
                                                else -1 if last["pct"] < counted[-2]["pct"] - 0.05 else 0)
            cells[skill] = {"status": _status(last["pct"]), "pct": last["pct"], "support": last["support"],
                            "trend": trend, "attempts": tries, "latest": last,
                            "questions": sum(t.get("questions", 1) for t in counted)}  # how much it rests on
        students[sid] = cells
    groups = {skill: {status: [sid for sid, cells in students.items() if skill in cells
                               and cells[skill]["status"] == status] for status in STATUS} for skill in skills}
    trends = {skill: [{"date": run["date"], "got": _share_got(run, skill)} for run in runs
                      if not run.get("practice") and any(i["skill"] == skill for i in run["items"])] for skill in skills}
    latest = {}
    for run in runs:
        for sid, summary in run["summaries"].items():
            if sid in students:
                latest[sid] = {"title": run["title"], **summary}
    # Help on the page, worksheet by worksheet, for each student who ever had it: is it coming off as scores hold?
    help_over_time: dict[str, list[dict]] = {}
    for run in runs:
        for sid, st in run["students"].items():
            new = [a for a in st["answers"].values() if not a.get("retry")]
            possible = sum(a["possible"] for a in new)
            if possible:
                help_over_time.setdefault(sid, []).append({"date": run["date"], "title": run["title"],
                                                           "pct": sum(a["earned"] for a in new) / possible,
                                                           "help": bool(st["support"])})
    help_over_time = {sid: rows for sid, rows in sorted(help_over_time.items()) if any(r["help"] for r in rows)}
    return {"skills": skills, "students": students, "groups": groups, "worksheets": worksheets, "trends": trends,
            "help_over_time": help_over_time,
            "summaries": latest,
            "dates": [runs[0]["date"], runs[-1]["date"]] if runs else ["", ""]}


def _short(text, limit: int = 160) -> str:
    """A question's prompt on one line, cut at a word near the limit, for the dashboard."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _skill(q: int, answer: dict, by_q: dict) -> str | None:
    """The skill an answer counts toward: its own (a practice sheet's question keeps the worksheet's), or its
    question's."""
    return answer.get("skill") or by_q.get(q)


def _share_got(run: dict, skill: str) -> float:
    by_q = {i["q"]: i["skill"] for i in run["items"]}
    shares = []
    for st in run["students"].values():
        mine = [a for q, a in st["answers"].items() if _skill(q, a, by_q) == skill]
        possible = sum(a["possible"] for a in mine)
        if possible:
            shares.append(sum(a["earned"] for a in mine) / possible >= GOT)
    return sum(shares) / len(shares) if shares else 0.0


def build(folder: Path, out: Path | None = None, roster_path: Path | None = None, class_name: str = "") -> dict:
    """dashboard.html, progress.csv, and parents.docx (with a page per family language that has a
    translation) in out (default: FOLDER/progress). Returns a report with what's still missing."""
    from . import prepare as P
    folder = Path(folder)
    roster = P.load_roster(roster_path, class_digits(folder)) if roster_path else None
    runs = collect(folder, roster)
    if not runs:
        raise ProgressError(f"no marked classes under {folder}: progress reads each marking folder's "
                            "results.json, which `check` writes")
    data = analyze(runs)
    out = Path(out or folder / "progress")
    out.mkdir(parents=True, exist_ok=True)
    skills_file = folder / "skills.json"
    descriptions = S.read_json(skills_file).get("skills", {}) if skills_file.exists() else {}
    name = class_name or folder.name
    data["class"] = name
    data["descriptions"] = descriptions
    S.write_json(out / "progress.json", data)
    (out / "dashboard.html").write_text(dashboard_html(data))
    _csv(data, out / "progress.csv")
    supported = _supports_csv(runs, out / "supports.csv")
    families = S.read_json(folder / "families.json") if (folder / "families.json").exists() else {}
    todo, made, unreviewed = [], {}, []
    missing = [s for s in data["skills"] if not (descriptions.get(s) or {}).get("family")
               or not (descriptions.get(s) or {}).get("home")]
    for lang in sorted(set(families.values())):
        ids = sorted(sid for sid, code in families.items() if code == lang and sid in data["students"])
        tr_path = folder / f"parents.{lang}.json"
        if not tr_path.exists():
            todo.append((lang, ids))
            continue
        tr = S.read_json(tr_path)
        for label, text in (tr.get("labels") or {}).items():
            _same_blanks(label, text, tr_path.name)
        if not tr.get("reviewed_by"):
            unreviewed.append(lang)
        labels = {**LABELS, **tr.get("labels", {})}
        missing_feedback = [sid for sid in ids if data["summaries"].get(sid) and sid not in tr.get("feedback", {})]
        if missing_feedback:
            todo.append((lang, ids))
        made[lang] = parents_docx(data, {**descriptions, **tr.get("skills", {})}, labels,
                                  out / f"parents-{lang}.docx", ids, lang, tr.get("feedback", {}))
    in_language = {sid for lang, path in made.items() for sid, code in families.items() if code == lang}
    english = [sid for sid in data["students"] if sid not in in_language]
    made["en"] = parents_docx(data, descriptions, LABELS, out / "parents.docx", english)
    if missing or todo:
        _todo(out / "progress-todo.md", data, descriptions, missing, todo, folder)
    elif (out / "progress-todo.md").exists():
        (out / "progress-todo.md").unlink()
    return {"out": out, "runs": len(runs), "students": len(data["students"]), "skills": data["skills"],
            "missing": missing, "languages": todo, "made": made, "groups": data["groups"],
            "in_language": sorted(in_language), "unreviewed": unreviewed, "supported": supported}


def _blanks(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def _same_blanks(label: str, text, where: str) -> None:
    """A translated label keeps the English one's {start}, {end}... exactly: they're filled in, not read."""
    english = LABELS.get(label)
    if not isinstance(english, str) or not isinstance(text, str):
        return
    try:
        ours = _blanks(text)
    except ValueError:
        ours = None
    want = _blanks(english)
    if ours != want:
        keep = ", ".join("{" + b + "}" for b in sorted(want)) or "no {...} at all"
        raise ProgressError(f"{where}: the label \"{label}\" has to keep {keep} exactly as written in English "
                            f"(it has: {text!r}); translate the words around them")


def _csv(data: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", *[c for s in data["skills"] for c in (s, f"{s}: help on the page")]])
        for sid, cells in data["students"].items():  # scores stay numbers; help is its own column
            w.writerow([sid, *[c for s in data["skills"] for c in (
                (f"{cells[s]['pct'] * 100:.0f}", "yes" if cells[s]["support"] else "no") if s in cells else ("", ""))]])


def _todo(path: Path, data: dict, descriptions: dict, missing: list[str], languages: list, folder: Path) -> None:
    lines = ["# Progress: what's missing", ""]
    if missing:
        lines += [f"## Skills for families: `{folder / 'skills.json'}`", "",
                  "For each skill, write what it means in everyday words (`family`, one sentence a parent with no "
                  "background understands) and one thing to try at home in ten minutes (`home`, with no materials "
                  "a family might not have). Keep the skill names exactly as written. Then run `progress` again.", "",
                  "```json", json.dumps({"skills": {s: {"family": (descriptions.get(s) or {}).get("family", "..."),
                                                        "home": (descriptions.get(s) or {}).get("home", "...")}
                                                    for s in data["skills"]}}, indent=2, ensure_ascii=False), "```", ""]
    for lang, ids in languages:
        feedback = {sid: data["summaries"][sid] for sid in ids if data["summaries"].get(sid)}
        lines += [f"## Family pages in `{lang}` (IDs {', '.join(ids)}): `{folder / f'parents.{lang}.json'}`", "",
                  "Translate the labels, each skill's `family` and `home`, and each student's latest feedback, into "
                  "plain words a family reads easily. The feedback was written to the student: keep its meaning, "
                  "and leave out question numbers the family can't see. Keep `{start}`, `{end}`, `{earned}`, "
                  "`{possible}`, `{n}`, `{month}`, and `{day}` as they are. If the language is one Claude "
                  "translates less reliably, tell the teacher to have a bilingual colleague read it.",
                  "", "```json", json.dumps({"labels": LABELS, "skills": {s: {"family": "...", "home": "..."}
                                                                         for s in data["skills"]},
                                             "feedback": {sid: {"strength": f.get("strength", ""),
                                                                "fixes": list(f.get("fixes", []))}
                                                          for sid, f in feedback.items()}},
                                            indent=2, ensure_ascii=False), "```", ""]
    path.write_text("\n".join(lines))


# --- Family pages ---------------------------------------------------------------------------------

def _when(iso: str, labels: dict = LABELS) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return labels["date"].format(month=labels["months"][d.month - 1], day=d.day)


def parents_docx(data: dict, descriptions: dict, labels: dict, path: Path, ids: list[str] | None,
                 lang: str | None = None, feedback: dict | None = None) -> Path:
    """One page per student, in plain words: what the class has been learning, how this student is doing on
    each skill, one strength, what's next, and something to try at home. A blank line for the name."""
    from . import script as SC
    rtl = bool(lang) and SC.has_rtl(json.dumps(labels, ensure_ascii=False))
    doc = WF.Doc()
    students = [sid for sid in data["students"] if ids is None or sid in ids]
    start, end = (_when(d, labels) for d in data["dates"])
    for k, sid in enumerate(students):
        cells = data["students"][sid]
        if k:
            doc.page_break()
        doc.para(f"{labels['title']}: {data['class']}", bold=True, size=18, markup=False, lang=lang, rtl=rtl)
        doc.para(f"{labels['student']}: ______________________________   ({labels['teacher_id']}: {sid})", size=13,
                 markup=False, lang=lang, rtl=rtl)
        dates = labels["dates_one"].format(start=start) if start == end else labels["dates"].format(start=start, end=end)
        doc.para(dates, italic=True, color="5F6670", markup=False, lang=lang, rtl=rtl)
        doc.heading(labels["learning"], 2)
        rows = [[labels["skill"], labels["how"]]]
        for skill in data["skills"]:
            if skill not in cells:
                continue
            cell = cells[skill]
            last = cell.get("latest") or cell["attempts"][-1]  # the attempt the status comes from, not a retry
            what = (descriptions.get(skill) or {}).get("family") or skill
            status = labels[cell["status"]] + (f" ({labels['support']})" if cell["support"] else "")
            score = (labels["latest_one"] if last["possible"] == 1 else labels["latest"]).format(
                earned=f"{last['earned']:g}", possible=f"{last['possible']:g}")
            n = cell.get("questions", 1)
            count = labels["evidence_one"] if n == 1 else labels["evidence"].format(n=n)
            rows.append([what, f"{status}\n\n{score} ({count})"])
        doc.table(rows, [4.2, 2.3], lang=lang, rtl_columns=(0, 1) if rtl else ())
        if any(cells[skill]["support"] for skill in cells):
            doc.para(labels["support_note"], italic=True, size=9, color="5F6670", markup=False, lang=lang, rtl=rtl)
        summary = (feedback or {}).get(sid) or data["summaries"].get(sid) or {}
        if summary.get("strength") or summary.get("fixes"):  # written to the student when their work was marked
            doc.heading(labels["feedback"], 2)
            if summary.get("strength"):
                doc.para(f"{labels['strength']}: {summary['strength']}", markup=False, lang=lang, rtl=rtl)
            for fix in summary.get("fixes", []):
                doc.para(f"{labels['next']}: {fix}", markup=False, lang=lang, rtl=rtl)
        tips = [(descriptions.get(skill) or {}).get("home") for skill in data["skills"]
                if skill in cells and cells[skill]["status"] != "got"]
        tips = [t for t in tips if t][:2]
        if tips:
            doc.heading(labels["home"], 2)
            doc.para(labels["home_intro"], markup=False, lang=lang, rtl=rtl)
            for tip in tips:
                doc.para(f"• {tip}", markup=False, lang=lang, rtl=rtl)
        doc.heading(labels["notes"], 2)
        for _ in range(3):
            doc.para("_" * 70, color="9AA0A6", markup=False)
        doc.para(labels["interpreter"], size=9, markup=False, lang=lang, rtl=rtl)
        doc.para(labels["foot"], italic=True, size=9, color="5F6670", markup=False, lang=lang, rtl=rtl)
    doc.save(path, f"{labels['title']}: {data['class']}")
    return path


# --- The teacher's dashboard ----------------------------------------------------------------------

def dashboard_html(data: dict) -> str:
    """One self-contained page: open it in any browser, with no internet. Student IDs only."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")  # no "</script>" or "<!--" inside
    return _PAGE.replace("{{TITLE}}", html.escape(f"{data['class']}: progress")).replace("{{DATA}}", payload)




_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{{TITLE}}</title>
<style>
:root { --bg:#fbfaf7; --card:#ffffff; --ink:#1f2328; --muted:#5f6670; --line:#e3e0d8; --accent:#2453a6;
  --accent-bg:#eaf0fb; --got:#2e7d4f; --got-bg:#e2f2e7; --getting:#8a5d00; --getting-bg:#fbf3df; --pract:#a8392f;
  --pract-bg:#fbe8e5; --none-bg:#f4f2ed; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --card:#1f2226; --ink:#e8e6e1; --muted:#a3a8ae;
  --line:#33373c; --accent:#8fb0f0; --accent-bg:#22304a; --got:#7fd29e; --got-bg:#1d3527; --getting:#e6c06a;
  --getting-bg:#332b1d; --pract:#f0928a; --pract-bg:#3a2321; --none-bg:#23262a; } }
* { box-sizing: border-box; }
html { scroll-padding-top: 72px; }
body { margin:0; background:var(--bg); color:var(--ink); font: 15px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
main { max-width: 1180px; margin: 0 auto; padding: 20px 16px 64px; }
nav.top { position: sticky; top: 0; z-index: 3; background: var(--bg); border-bottom: 1px solid var(--line); }
nav.top div { max-width: 1180px; margin: 0 auto; padding: 10px 16px; display: flex; gap: 6px 16px; flex-wrap: wrap; font-size: 14px; }
nav.top a { font-weight: 500; text-decoration: none; }
h1 { font-size: 26px; margin: 0 0 4px; } h2 { font-size: 19px; margin: 36px 0 10px; }
.sub { color: var(--muted); margin: 0 0 14px; }
.note { font-size: 13px; color: var(--muted); border-left: 3px solid var(--line); padding: 2px 10px; margin: 10px 0 0; }
.cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.big { font-size: 28px; font-weight: 700; } .label { color: var(--muted); font-size: 13px; }
.todo { display: grid; gap: 10px; }
.todo .card { display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; align-items: start; }
.todo h3 { margin: 0; font-size: 16px; }
.todo p { margin: 2px 0 0; }
.prompt { grid-column: 1 / -1; display: flex; gap: 8px; align-items: center; background: var(--accent-bg); border-radius: 8px; padding: 6px 6px 6px 10px; }
.prompt code { flex: 1; font: 13px/1.4 ui-monospace, Menlo, Consolas, monospace; white-space: normal; }
.scroll { overflow-x: auto; background: var(--card); border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 7px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
th { font-weight: 600; color: var(--muted); background: var(--card); position: sticky; top: 0; }
th button { all: unset; cursor: pointer; } th button:focus-visible { outline: 2px solid var(--accent); }
th[aria-sort] button { color: var(--ink); }
th.skill { min-width: 120px; max-width: 200px; white-space: normal; }
td.cell { text-align: center; white-space: nowrap; font-variant-numeric: tabular-nums; }
.got { color: var(--got); } .getting { background: var(--getting-bg); color: var(--getting); }
.practicing { background: var(--pract-bg); color: var(--pract); } .none { background: var(--none-bg); color: var(--muted); }
.pill.got { background: var(--got-bg); }
.s { font-size: 11px; font-weight: 700; border: 1px solid currentColor; border-radius: 4px; padding: 0 3px; margin-left: 3px; }
.id { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.qbars { display: flex; gap: 6px; align-items: flex-end; }
.qbar { display: grid; justify-items: center; gap: 2px; font-size: 11px; color: var(--muted); }
.qbar i { display: block; width: 18px; background: var(--accent); border-radius: 2px 2px 0 0; opacity: .8; }
.qbar.low i { background: var(--pract); }
.groups { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.spark { display: flex; gap: 10px; align-items: center; margin: 4px 0 8px; }
.spark svg { flex: none; }
.pill { display:inline-block; padding: 1px 8px; border-radius: 999px; margin: 2px 4px 2px 0; font-size: 13px; font-variant-numeric: tabular-nums; }
.legend span { margin-right: 14px; font-size: 13px; }
.missed p { margin: 6px 0; }
.missed .q { font-weight: 600; }
a { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
select, button, textarea, input { font: inherit; color: var(--ink); }
select, button { padding: 6px 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--card); cursor: pointer; }
button:focus-visible, a:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
textarea { width: 100%; min-height: 120px; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); }
.names { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 0 0 14px; }
#names-panel { margin: 0 0 14px; }
#names-panel .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
.muted { color: var(--muted); }
[hidden] { display: none !important; }
@media print { body { background: #fff; } .noprint, nav.top { display: none !important; } .scroll { overflow: visible; }
  th { position: static; } body.one main > *:not(#student) { display: none; }
  body.one #student > *:not(#detail):not(#one-title) { display: none; } }
#one-title { display: none; } body.one #one-title { display: block; }
</style></head>
<body>
<nav class="top" aria-label="Sections"><div>
<a href="#next">What to do next</a><a href="#skills">Skills</a><a href="#groups-section">Groups</a>
<a href="#worksheets">Worksheets</a><a href="#missed">Most missed</a><a href="#fading-section" id="nav-fading">Help over time</a>
<a href="#student">One student</a></div></nav>
<main>
<h1 id="title"></h1>
<p class="sub" id="subtitle"></p>
<div class="names noprint"><button type="button" id="names-btn" aria-expanded="false" aria-controls="names-panel">Show names</button>
<span class="muted" id="names-state">Students appear by class ID.</span></div>
<div class="card noprint" id="names-panel" hidden>
<label for="names-text"><strong>Your class list</strong></label>
<p class="label">Paste the names in the order of your class list, one per line, so the 1st name is the 1st class number.
Or paste rows with each student's class ID and name, or open a CSV of them. The list stays in this page while it's
open: it isn't saved, and this file sends nothing anywhere. Don't give Claude the list, or a picture of this page with
names on it.</p>
<textarea id="names-text" spellcheck="false" autocomplete="off"></textarea>
<div class="row"><button type="button" id="names-use">Show these names</button>
<label class="muted">or open a file <input type="file" id="names-file" accept=".csv,.txt,text/csv,text/plain"></label>
<button type="button" id="names-clear">Hide names</button></div>
<p class="label" id="names-msg" role="status"></p>
</div>
<div class="cards" id="cards"></div>
<p class="note">This file stays on this computer: it needs no internet and sends nothing anywhere. A box marked
<span class="s">S</span> was earned with help on the page (hints, worked examples, laid-out steps, or fewer choices).</p>

<section id="next"><h2>What to do next</h2>
<p class="label noprint">Copy a request and paste it to Claude, in the chat or project where you use Paper Loop. They use class IDs, never names.</p>
<div class="todo" id="todo"></div></section>

<section id="skills"><h2>Skills, student by student</h2>
<p class="legend"><span class="pill practicing">· Still practicing, under 50%</span><span class="pill getting">~ Getting there, 50%+</span>
<span class="pill got">✓ Got it, 80%+</span><span class="pill none">— not yet seen</span>
<span class="muted noprint" id="sort-note"></span></p>
<div class="scroll"><table id="grid"></table></div></section>

<section id="groups-section"><h2>Groups for the next lesson</h2>
<p class="label">For each skill: the share of students who had it, worksheet by worksheet, and who still needs it.</p>
<div class="groups" id="groups"></div></section>

<section id="worksheets"><h2>Worksheets</h2>
<p class="label">Each bar is a question: the taller it is, the more students got full credit. Red ones were under half.</p>
<div class="scroll"><table id="sheets"></table></div></section>

<section id="missed" class="missed"><h2>Most-missed questions</h2><div id="saw"></div></section>

<section id="fading-section"><h2>Help on the page, over time</h2>
<p class="note">For each student who had help on the page (hints, worked examples, laid-out steps, fewer choices):
their score on each worksheet, and <span class="s">S</span> where the help printed. Fading means the help comes off
while the score holds. The student's plan decides supports; this shows what happened on paper.</p>
<div class="scroll"><table id="fading"></table></div></section>

<section id="student"><h2>One student</h2>
<p class="noprint"><select id="pick" aria-label="Student"></select> <button type="button" id="print-one">Print this student only</button>
<button type="button" id="print-all">Print everything</button></p>
<h1 id="one-title"></h1>
<div id="detail"></div></section>
</main>
<script type="application/json" id="data">{{DATA}}</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined;  // a skill named "constructor" too
const $ = id => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (v === undefined || v === null) continue;
    if (k === "class") e.className = v; else if (k.startsWith("on")) e[k] = v; else e.setAttribute(k, v); }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return e; };
const svg = (tag, attrs = {}) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const pct = x => Math.round(x * 100) + "%";
const mark = {got: "✓", getting: "~", practicing: "·"};
const word = {got: "Got it", getting: "Getting there", practicing: "Still practicing"};
const rank = {practicing: 0, getting: 1, got: 2};
const ids = Object.keys(D.students);
const when = iso => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString(undefined, {month: "short", day: "numeric"}); };
const cell = (id, s) => own(D.students[id], s);
const quote = s => `“${s}”`;
const list = xs => xs.length < 3 ? xs.join(" and ") : xs.slice(0, -1).join(", ") + ", and " + xs[xs.length - 1];

// Names come only from the teacher's own list, pasted or opened here, and live only in this variable.
let names = {};
const named = id => own(names, id);
const who = id => named(id) ? [named(id), " ", el("span", {class: "id"}, id)] : [id];
const whoText = id => named(id) ? `${named(id)} (${id})` : id;

const sheets = D.worksheets.filter(w => !w.practice);
const latest = sheets[sheets.length - 1] || D.worksheets[D.worksheets.length - 1];
const need = id => Object.values(D.students[id]).reduce((n, c) => n + (c.status === "practicing" ? 2 : c.status === "getting" ? 1 : 0), 0);

$("title").textContent = D.class + ": progress";
$("subtitle").textContent = `${ids.length} students, ${D.worksheets.length} worksheet${D.worksheets.length === 1 ? "" : "s"} marked, ${when(D.dates[0])} to ${when(D.dates[1])}`;

function cards() {
  const box = $("cards"); box.replaceChildren();
  const practicing = ids.filter(id => Object.values(D.students[id]).some(c => c.status === "practicing")).length;
  const rows = [[practicing, `of ${ids.length} students still practicing at least one skill`],
    [pct(latest.average), `average on the latest worksheet, ${latest.title}`], [D.skills.length, "skills tracked so far"]];
  if (latest.on_version) rows.push([latest.on_version, "had their own version of the latest worksheet (supports or another language)"]);
  for (const [n, label] of rows) box.append(el("div", {class: "card"}, el("div", {class: "big"}, n), el("div", {class: "label"}, label)));
}

// What to do next: from the skills most students still need, the few who need one, and who slipped.
function todo() {
  const box = $("todo"); box.replaceChildren();
  const items = [];
  const bySkill = D.skills.map(s => { const g = own(D.groups, s) || {practicing: [], getting: [], got: []};
    const seen = g.practicing.length + g.getting.length + g.got.length;
    return {s, g, seen, share: seen ? g.practicing.length / seen : 0}; }).filter(x => x.seen);
  bySkill.sort((a, b) => (b.share - a.share) || (b.g.getting.length - a.g.getting.length));
  const reteach = bySkill.filter(x => x.share >= 0.3).slice(0, 1);
  for (const x of reteach) items.push({title: `Reteach ${quote(x.s)}`,
    text: `${x.g.practicing.length} of ${x.seen} students are still practicing it` + (x.g.getting.length ? `, and ${x.g.getting.length} more are getting there.` : "."),
    prompt: `For ${D.class}: make a short reteach of "${x.s}", a worked example and then 3 practice questions, as a Paper Loop worksheet.`});
  const worst = latest && [...latest.questions].sort((a, b) => a.full - b.full)[0];
  if (worst && worst.full < 0.5) items.push({title: `Go over ${latest.title}`,
    text: `Question ${worst.q} was the most missed: ${pct(worst.full)} got full credit.`,
    prompt: `Make go-over slides for my last marking of "${latest.title}" in ${D.class}.`});
  const small = bySkill.filter(x => x.g.practicing.length && x.share < 0.3).slice(0, 2);
  for (const x of small) items.push({title: `A small group for ${quote(x.s)}`, ids: x.g.practicing,
    text: `Still practicing it: `,
    prompt: `For ${D.class}: make a Paper Loop practice sheet on "${x.s}" for a small group (class IDs ${x.g.practicing.join(", ")}), with the steps laid out.`});
  const slipped = ids.filter(id => Object.values(D.students[id]).some(c => c.trend < 0 && c.status !== "got"));
  if (slipped.length) items.push({title: "Check in", ids: slipped, text: "Lower than last time on a skill: "});
  if (!items.length) items.push({title: "Everyone has every skill so far",
    text: "Time for something harder.",
    prompt: `For ${D.class}: make a stretch worksheet that builds on ${list(D.skills.map(s => `"${s}"`))}.`});
  for (const it of items.slice(0, 5)) {
    const card = el("div", {class: "card"}, el("div", {}, el("h3", {}, it.title),
      el("p", {}, it.text, ...(it.ids ? it.ids.slice(0, 12).flatMap((id, k) => [k ? ", " : "", ...who(id)]) : []),
        it.ids && it.ids.length > 12 ? `, and ${it.ids.length - 12} more` : "")));
    if (it.prompt) {
      const code = el("code", {}, it.prompt);
      const btn = el("button", {type: "button", class: "noprint"}, "Copy");
      btn.onclick = () => copy(it.prompt, code, btn);
      card.append(el("div", {class: "prompt"}, code, btn));
    }
    box.append(card);
  }
}
function copy(text, code, btn) {
  const done = () => { btn.textContent = "Copied"; setTimeout(() => (btn.textContent = "Copy"), 1600); };
  const select = () => { const r = document.createRange(); r.selectNodeContents(code); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    btn.textContent = "Press Ctrl+C or ⌘C"; };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, select); else select();
}

// The grid: students who need the most help first, until a column is chosen.
let sortBy = "need";
function grid() {
  const t = $("grid"); t.replaceChildren();
  const sortable = (key, text, cls) => el("th", {class: cls, "aria-sort": sortBy === key ? (key === "id" ? "ascending" : "descending") : undefined},
    el("button", {type: "button", onclick: () => { sortBy = key; grid(); }}, text));
  const head = el("tr", {}, sortable("id", "Student"), ...D.skills.map(s => sortable("skill:" + s, s, "skill")));
  t.append(el("thead", {}, head));
  const order = [...ids];
  if (sortBy === "need") order.sort((a, b) => need(b) - need(a) || a.localeCompare(b));
  else if (sortBy.startsWith("skill:")) { const s = sortBy.slice(6);
    order.sort((a, b) => ((cell(a, s) ? rank[cell(a, s).status] : 3) - (cell(b, s) ? rank[cell(b, s).status] : 3)) || a.localeCompare(b)); }
  else order.sort((a, b) => a.localeCompare(b));
  $("sort-note").textContent = sortBy === "need" ? "Students who need the most help come first. Click a column to sort by it."
    : sortBy === "id" ? "Sorted by class ID." : `Sorted by ${quote(sortBy.slice(6))}, those still practicing first.`;
  const body = el("tbody");
  for (const id of order) {
    const row = el("tr", {}, el("td", {}, el("a", {href: "#student", onclick: () => show(id)}, ...who(id))));
    for (const s of D.skills) {
      const c = cell(id, s);
      if (!c) { row.append(el("td", {class: "cell none"}, "—")); continue; }
      const arrow = c.trend > 0 ? " ↑" : c.trend < 0 ? " ↓" : "";
      const td = el("td", {class: "cell " + c.status, title: c.attempts.map(a => `${when(a.date)} ${a.title}: ${a.earned}/${a.possible}${a.support ? " (with help on the page)" : ""}`).join("\n")},
        `${mark[c.status]} ${pct(c.pct)}${arrow}`);
      if (c.support) td.append(el("span", {class: "s", title: "with help on the page"}, "S"));
      row.append(td);
    }
    body.append(row);
  }
  t.append(body);
}

function spark(points) {  // the share who had it, worksheet by worksheet
  const w = 120, h = 30, pad = 4;
  const s = svg("svg", {width: w, height: h, viewBox: `0 0 ${w} ${h}`, "aria-hidden": "true"});
  s.append(svg("line", {x1: pad, x2: w - pad, y1: h - pad, y2: h - pad, stroke: "var(--line)"}));
  const xy = points.map((p, k) => [points.length === 1 ? w / 2 : pad + k * (w - 2 * pad) / (points.length - 1), h - pad - p.got * (h - 2 * pad)]);
  if (xy.length > 1) s.append(svg("polyline", {points: xy.map(p => p.join(",")).join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 2, "stroke-linejoin": "round"}));
  xy.forEach(([x, y], k) => s.append(svg("circle", {cx: x, cy: y, r: k === xy.length - 1 ? 3.5 : 2.5, fill: "var(--accent)"})));
  return s;
}
function groups() {
  const box = $("groups"); box.replaceChildren();
  for (const s of D.skills) {
    const g = own(D.groups, s);
    const card = el("div", {class: "card"}, el("strong", {}, s));
    const trend = own(D.trends, s) || [];
    if (trend.length) card.append(el("div", {class: "spark", title: trend.map(t => `${when(t.date)}: ${pct(t.got)} had it`).join("\n")}, spark(trend),
      el("span", {class: "label"}, trend.length > 1 ? `Had it: ${pct(trend[0].got)} → ${pct(trend[trend.length - 1].got)}` : `Had it: ${pct(trend[0].got)}`)));
    for (const status of ["practicing", "getting"]) {
      if (!g[status].length) continue;
      card.append(el("div", {}, el("span", {class: "label"}, word[status] + ": "), ...g[status].map(id => el("span", {class: "pill " + status}, ...who(id)))));
    }
    if (!g.practicing.length && !g.getting.length) card.append(el("div", {class: "label"}, "Everyone has it."));
    box.append(card);
  }
}

function worksheets() {
  const t = $("sheets"); t.replaceChildren();
  t.append(el("thead", {}, el("tr", {}, ...["Date", "Worksheet", "Students", "Average", "Full credit, question by question"].map(h => el("th", {}, h)))));
  const body = el("tbody");
  for (const w of [...D.worksheets].reverse()) {
    const bars = el("div", {class: "qbars", role: "img", "aria-label": w.questions.map(q => `question ${q.q}: ${pct(q.full)}`).join(", ")},
      ...w.questions.map(q => el("div", {class: "qbar" + (q.full < 0.5 ? " low" : ""), title: `Q${q.q}: ${pct(q.full)} full credit (${q.skill})`},
        el("i", {style: `height:${Math.max(2, Math.round(q.full * 36))}px`}), `Q${q.q}`)));
    body.append(el("tr", {}, el("td", {}, when(w.date)), el("td", {}, w.title + (w.practice ? " (practice)" : "")), el("td", {}, w.students), el("td", {}, pct(w.average)), el("td", {}, bars)));
  }
  t.append(body);
}

function missed() {  // the questions fewest students got, with what Claude noticed when it made a go-over deck
  const box = $("saw"); box.replaceChildren();
  let any = false;
  for (const w of [...sheets].reverse().slice(0, 4)) {
    const saw = Object.fromEntries((w.saw || []).map(s => [s.q, s.saw]));
    const qs = w.questions.filter(q => q.answered && (q.full < 0.6 || own(saw, q.q))).sort((a, b) => a.full - b.full).slice(0, 3);
    if (!qs.length) continue;
    any = true;
    box.append(el("h3", {}, `${when(w.date)}, ${w.title}`));
    for (const q of qs) box.append(el("p", {}, el("span", {class: "q"}, `Q${q.q}, ${pct(q.full)} full credit: `), q.prompt || q.skill,
      el("span", {class: "label"}, ` (${q.skill})`), own(saw, q.q) ? el("div", {class: "note"}, own(saw, q.q)) : null));
  }
  if (!any) box.append(el("p", {class: "muted"}, "Most students got full credit on every question."));
  const decks = sheets.some(w => (w.saw || []).length);
  if (!decks) box.append(el("p", {class: "label"}, "After you make go-over slides, what Claude noticed about the class's mistakes shows up here too."));
}

function fading() {
  const fadingIds = Object.keys(D.help_over_time || {});
  if (!fadingIds.length) { $("fading-section").hidden = true; $("nav-fading").hidden = true; return; }
  const t = $("fading"); t.replaceChildren();
  const dates = [...new Set(fadingIds.flatMap(id => D.help_over_time[id].map(r => r.date + "|" + r.title)))].sort();
  t.append(el("thead", {}, el("tr", {}, el("th", {}, "Student"), ...dates.map(d => el("th", {}, `${when(d.split("|")[0])} ${d.split("|").slice(1).join("|")}`)))));
  const body = el("tbody");
  for (const id of fadingIds) {
    const byDate = Object.fromEntries(D.help_over_time[id].map(r => [r.date + "|" + r.title, r]));
    body.append(el("tr", {}, el("td", {}, ...who(id)), ...dates.map(d => { const r = byDate[d];
      if (!r) return el("td", {class: "cell none"}, "—");
      const td = el("td", {class: "cell " + (r.pct >= 0.8 ? "got" : r.pct >= 0.5 ? "getting" : "practicing")}, pct(r.pct));
      if (r.help) td.append(el("span", {class: "s", title: "help on the page"}, "S"));
      return td; })));
  }
  t.append(body);
}

const pick = $("pick");
function picker() {
  const now = pick.value;
  const key = id => named(id) ? "0" + named(id) : "1" + id;  // by name once there are names, else by ID
  pick.replaceChildren(...[...ids].sort((a, b) => key(a).localeCompare(key(b))).map(id => el("option", {value: id}, whoText(id))));
  if (now) pick.value = now;
}
pick.onchange = () => show(pick.value);
function show(id) {
  pick.value = id;
  const box = $("detail"); box.replaceChildren();
  const s = own(D.summaries, id);
  if (s) box.append(el("div", {class: "card"}, el("div", {class: "label"}, `Latest feedback (${s.title})`), el("p", {}, s.strength || ""), ...(s.fixes || []).map(f => el("p", {}, "Next: " + f))));
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, ...["Skill", "Status", "Attempts"].map(h => el("th", {}, h)))));
  const b = el("tbody");
  for (const sk of D.skills) {
    const c = cell(id, sk); if (!c) continue;
    b.append(el("tr", {}, el("td", {}, sk), el("td", {class: "cell " + c.status}, word[c.status] + (c.support ? " (with help on the page)" : "")),
      el("td", {}, c.attempts.map(a => `${when(a.date)}: ${a.earned}/${a.possible}${a.support ? " S" : ""}`).join(", "))));
  }
  t.append(b);
  box.append(el("div", {class: "scroll", style: "margin-top:12px"}, t));
}
$("print-one").onclick = () => {  // a conference copy: one student's skills, none of the class's
  $("one-title").textContent = `${D.class}: ${whoText(pick.value)}`;
  document.body.classList.add("one");
  window.print();
  document.body.classList.remove("one");
};
$("print-all").onclick = () => window.print();

// --- Names, from the teacher's own list --------------------------------------------------------------
const width = Math.max(2, ...ids.map(id => id.length));
function fields(line) {  // one CSV or tab-separated row, quotes allowed
  const out = []; let cur = "", q = false;
  for (let i = 0; i < line.length; i++) { const ch = line[i];
    if (q) { if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; }
    else if (ch === '"') q = true; else if (ch === "," || ch === "\t") { out.push(cur.trim()); cur = ""; } else cur += ch; }
  out.push(cur.trim()); return out;
}
// Class numbers made by Paper Loop's setup: the class, the place in the class list (01-99), and a check digit.
const place = id => id.length <= 2 ? +id : (id.length === 4 && (+id[0] + +id[1] + +id[2]) % 10 === +id[3]) ? +id.slice(1, 3) : null;
function readNames(text) {
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const byId = {};
  for (const line of lines) {
    const f = fields(line); const k = f.findIndex(x => /^\d{1,6}$/.test(x));
    if (k < 0) continue;
    const name = f.filter((x, j) => j !== k && x).join(" ");
    if (name) byId[f[k].padStart(width, "0")] = name;
  }
  if (Object.keys(byId).length) {
    const found = ids.filter(id => own(byId, id));
    return {names: Object.fromEntries(found.map(id => [id, byId[id]])), msg: `Matched ${found.length} of ${ids.length} students by class ID.`};
  }
  const classes = new Set(ids.filter(id => id.length === 4).map(id => id[0]));
  if (classes.size > 1) return {names: {}, msg: "This page has more than one class, so a list in order can't say whose is whose. Paste each student's class ID beside their name instead."};
  const out = {};
  for (const id of ids) { const p = place(id); if (p && p <= lines.length) out[id] = lines[p - 1]; }
  const n = Object.keys(out).length;
  const first = ids.find(id => place(id) === 1);
  return {names: out, msg: n ? `Matched ${n} of ${ids.length} students by their place in your list${first ? ` (ID ${first} is the 1st name)` : ""}. Check a few before you rely on it.`
    : "None matched. Paste each student's class ID beside their name instead."};
}
function useNames(text) {
  const r = readNames(text);
  names = r.names;
  $("names-msg").textContent = r.msg;
  $("names-text").value = "";
  render();
}
$("names-btn").onclick = () => { const p = $("names-panel"); p.hidden = !p.hidden; $("names-btn").setAttribute("aria-expanded", String(!p.hidden)); if (!p.hidden) $("names-text").focus(); };
$("names-use").onclick = () => useNames($("names-text").value);
$("names-file").onchange = e => { const f = e.target.files[0]; if (!f) return; f.text().then(useNames); e.target.value = ""; };
$("names-clear").onclick = () => { names = {}; $("names-msg").textContent = "Names hidden."; render(); };

function render() {
  const n = Object.keys(names).length;
  $("names-state").textContent = n ? `Showing ${n} name${n === 1 ? "" : "s"} from your list, in this page only. Close it and they're gone.` : "Students appear by class ID.";
  $("names-btn").textContent = n ? "Change names" : "Show names";
  cards(); todo(); grid(); groups(); worksheets(); missed(); fading(); picker();
  if (ids.length) show(pick.value);
}
render();
</script></body></html>
"""
