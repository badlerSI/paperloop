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
from collections import defaultdict
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


def collect(folder: Path, roster: set[str] | None = None) -> list[dict]:
    """Every marked class under folder, oldest first: its title, date, key, and each student's answers."""
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
                helped = bool(item.get("scaffolded"))  # help on this very question that changes what it measures
                st["support"] = st["support"] or helped
                st["answers"][b["q"]] = {"earned": float(b["points_awarded"]), "possible": float(b["points_possible"]),
                                         "verdict": b["verdict"], "support": helped, "retry": bool(item.get("retry"))}
        if not students:
            continue
        summaries = S.read_json(work / "summaries.json") if (work / "summaries.json").exists() else {}
        saw = []
        if (work / "goover.json").exists():
            for spec in S.read_json(work / "goover.json").get("questions", []):
                if spec.get("saw"):
                    saw.append({"q": spec["q"], "saw": spec["saw"]})
        source = S.read_json(assignment / "source.json") if (assignment / "source.json").exists() else {}
        raw = {str(v.get("id")): v for v in source.get("versions", []) if isinstance(v, dict)}
        versions = {fid: {**raw.get(fid, {}), **f} for fid, f in (key.get("forms") or {}).items()
                    if f.get("kind") == "version"}
        runs.append({"work": str(work), "assignment_id": key["assignment_id"], "title": manifest.get("title", ""),
                     "versions": {fid: {"name": f.get("name") or fid, "supports": _supports(f),
                                        "help": list(f.get("modifies") or [])} for fid, f in versions.items()},
                     "date": _date(work), "subject": key.get("subject", ""), "grade_band": key.get("grade_band", ""),
                     "items": [{"q": i["q"], "skill": i.get("skill") or manifest.get("title", ""),
                                "points": i["points"], "prompt": i["prompt"]} for i in key["items"]],
                     "students": students, "summaries": summaries, "saw": saw})
    runs.sort(key=lambda r: (r["date"], r["title"]))
    return runs


def _supports(form: dict) -> list[str]:
    """A version's supports in plain words, for a case manager's records."""
    out = []
    if form.get("scaffolds"):
        scaffolds = form["scaffolds"]
        out.append("supports on the page: " + (", ".join(scaffolds) if isinstance(scaffolds, list) else str(scaffolds)))
    lp = form.get("large_print")
    if lp:
        out.append("large print" + ("" if lp is True else f" ({lp}pt)" if isinstance(lp, (int, float)) and lp > 2
                                    else f" ({lp})"))
    if form.get("space"):
        out.append(f"more room to write ({form['space']}x)")
    if form.get("per_page"):
        out.append(f"at most {form['per_page']} question{'s' if form['per_page'] > 1 else ''} a page")
    if form.get("max_choices"):
        out.append(f"{form['max_choices']} answer choices at most")
    if form.get("grid"):
        out.append("graph paper for work")
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
        by_q = {i["q"]: i for i in run["items"]}
        for item in run["items"]:
            if item["skill"] not in skills:
                skills.append(item["skill"])
        for sid, st in run["students"].items():
            per_skill: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0, False, True])
            for q, a in st["answers"].items():
                if q in by_q:
                    acc = per_skill[by_q[q]["skill"]]
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
        full = {i["q"]: sum(1 for st in run["students"].values() if st["answers"].get(i["q"], {}).get("verdict")
                            == "correct") for i in run["items"]}
        n = len(run["students"])
        earned = sum(a["earned"] for st in run["students"].values() for a in st["answers"].values())
        possible = sum(a["possible"] for st in run["students"].values() for a in st["answers"].values())
        worksheets.append({"title": run["title"], "date": run["date"], "students": n,
                           "average": earned / possible if possible else 0,
                           "questions": [{"q": i["q"], "skill": i["skill"], "full": full[i["q"]] / n if n else 0}
                                         for i in run["items"]],
                           "saw": run["saw"], "supported": sum(st["support"] for st in run["students"].values())})
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
                            "trend": trend, "attempts": tries,
                            "questions": sum(t.get("questions", 1) for t in counted)}  # how much it rests on
        students[sid] = cells
    groups = {skill: {status: [sid for sid, cells in students.items() if skill in cells
                               and cells[skill]["status"] == status] for status in STATUS} for skill in skills}
    trends = {skill: [{"date": run["date"], "got": _share_got(run, skill)} for run in runs
                      if any(i["skill"] == skill for i in run["items"])] for skill in skills}
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


def _share_got(run: dict, skill: str) -> float:
    qs = [i["q"] for i in run["items"] if i["skill"] == skill]
    shares = []
    for st in run["students"].values():
        earned = sum(st["answers"].get(q, {}).get("earned", 0) for q in qs)
        possible = sum(st["answers"].get(q, {}).get("possible", 0) for q in qs)
        if possible:
            shares.append(earned / possible >= GOT)
    return sum(shares) / len(shares) if shares else 0.0


def build(folder: Path, out: Path | None = None, roster_path: Path | None = None, class_name: str = "") -> dict:
    """dashboard.html, progress.csv, and parents.docx (with a page per family language that has a
    translation) in out (default: FOLDER/progress). Returns a report with what's still missing."""
    from . import prepare as P
    folder = Path(folder)
    roster = P.load_roster(roster_path) if roster_path else None
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
            last = cell["attempts"][-1]
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
<title>{{TITLE}}</title>
<style>
:root { --bg:#fbfaf7; --card:#ffffff; --ink:#1f2328; --muted:#5f6670; --line:#e3e0d8; --accent:#2453a6;
  --got:#2e7d4f; --got-bg:#e2f2e7; --getting:#9a6700; --getting-bg:#fbf0d3; --pract:#b4423a; --pract-bg:#f9e1de;
  --none-bg:#f1efe9; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --card:#1f2226; --ink:#e8e6e1; --muted:#a3a8ae;
  --line:#33373c; --accent:#8fb0f0; --got:#7fd29e; --got-bg:#1d3527; --getting:#e6c06a; --getting-bg:#3a3020;
  --pract:#f0928a; --pract-bg:#3d2422; --none-bg:#25282c; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font: 15px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
main { max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; } h2 { font-size: 18px; margin: 32px 0 10px; }
.sub { color: var(--muted); margin: 0 0 16px; }
.note { font-size: 13px; color: var(--muted); border-left: 3px solid var(--line); padding: 2px 10px; margin: 10px 0 0; }
.cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.big { font-size: 28px; font-weight: 700; } .label { color: var(--muted); font-size: 13px; }
.scroll { overflow-x: auto; background: var(--card); border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 7px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
th { font-weight: 600; color: var(--muted); background: var(--card); position: sticky; top: 0; cursor: pointer; }
th.skill { min-width: 120px; max-width: 200px; white-space: normal; }
td.cell { text-align: center; white-space: nowrap; font-variant-numeric: tabular-nums; }
.got { background: var(--got-bg); color: var(--got); } .getting { background: var(--getting-bg); color: var(--getting); }
.practicing { background: var(--pract-bg); color: var(--pract); } .none { background: var(--none-bg); color: var(--muted); }
.s { font-size: 11px; font-weight: 700; border: 1px solid currentColor; border-radius: 4px; padding: 0 3px; margin-left: 3px; }
.bars { display:flex; gap:3px; align-items:flex-end; height: 34px; }
.bars span { width: 14px; background: var(--accent); border-radius: 2px 2px 0 0; opacity: .85; }
.groups { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.pill { display:inline-block; padding: 1px 8px; border-radius: 999px; margin: 2px 4px 2px 0; font-size: 13px; font-variant-numeric: tabular-nums; }
.legend span { margin-right: 14px; font-size: 13px; }
a { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
select, button { font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--card); color: var(--ink); }
.muted { color: var(--muted); }
@media print { body { background: #fff; } .noprint { display: none; } .scroll { overflow: visible; } th { position: static; }
  body.one main > *:not(#detail):not(#one-title) { display: none; } }
#one-title { display: none; } body.one #one-title { display: block; }
</style></head>
<body><main>
<h1 id="title"></h1>
<p class="sub" id="subtitle"></p>
<div class="cards" id="cards"></div>
<p class="note">Students appear by class ID only. Names stay with you, and this file stays on this computer: it needs no
internet and sends nothing anywhere. A box marked <span class="s">S</span> was earned with support (hints, worked
examples, laid-out steps, or fewer choices).</p>

<h2>Skills, student by student</h2>
<p class="legend"><span class="pill got">✓ Got it, 80%+</span><span class="pill getting">~ Getting there, 50%+</span>
<span class="pill practicing">· Still practicing</span><span class="pill none">not yet seen</span>
<span class="muted noprint">Click a column to sort by it. The most recent attempt counts; ↑ ↓ show the change from
the one before.</span></p>
<div class="scroll"><table id="grid"></table></div>

<h2>Groups for the next lesson</h2>
<div class="groups" id="groups"></div>

<h2>Worksheets</h2>
<div class="scroll"><table id="sheets"></table></div>

<div id="fading-section"><h2>Help on the page, over time</h2>
<p class="note">For each student who had help on the page (hints, worked examples, laid-out steps, fewer choices):
their score on each worksheet, and <span class="s">S</span> where the help printed. Fading means the help comes off
while the score holds. The student's plan decides supports; this shows what happened on paper.</p>
<div class="scroll"><table id="fading"></table></div></div>

<h2>What marking noticed</h2>
<div id="saw"></div>

<h2>One student</h2>
<p class="noprint"><select id="pick"></select> <button onclick="printOne()">Print this student only</button>
<button onclick="window.print()">Print everything</button></p>
<h1 id="one-title"></h1>
<div id="detail"></div>
</main>
<script type="application/json" id="data">{{DATA}}</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined;  // a skill named "constructor" too
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e[k] = v; else e.setAttribute(k, v); }
  for (const kid of kids.flat()) e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return e; };
const pct = x => Math.round(x * 100) + "%";
const mark = {got: "✓", getting: "~", practicing: "·"};
const word = {got: "Got it", getting: "Getting there", practicing: "Still practicing"};
const ids = Object.keys(D.students);
const when = iso => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString(undefined, {month: "short", day: "numeric"}); };

document.getElementById("title").textContent = D.class + ": progress";
document.getElementById("subtitle").textContent = `${ids.length} students, ${D.worksheets.length} worksheet${D.worksheets.length === 1 ? "" : "s"} marked, ${when(D.dates[0])} to ${when(D.dates[1])}`;
const latest = D.worksheets[D.worksheets.length - 1];
const needs = ids.filter(id => Object.values(D.students[id]).some(c => c.status === "practicing")).length;
const cell = (id, s) => own(D.students[id], s);
const cards = [[pct(latest.average), `class average on ${latest.title}`], [D.skills.length, "skills tracked"],
  [needs, "students still practicing at least one skill"], [latest.supported, "used a support version last time"]];
for (const [n, label] of cards) document.getElementById("cards").append(el("div", {class: "card"}, el("div", {class: "big"}, n), el("div", {class: "label"}, label)));

let sortSkill = null;
function grid() {
  const t = document.getElementById("grid"); t.replaceChildren();
  const head = el("tr", {}, el("th", {onclick: () => { sortSkill = null; grid(); }}, "ID"));
  D.skills.forEach(s => head.append(el("th", {class: "skill", title: "Sort by this skill", onclick: () => { sortSkill = s; grid(); }}, s)));
  t.append(el("thead", {}, head));
  const order = [...ids];
  const rank = {practicing: 0, getting: 1, got: 2};
  if (sortSkill) order.sort((a, b) => ((cell(a, sortSkill) ? rank[cell(a, sortSkill).status] : 3) - (cell(b, sortSkill) ? rank[cell(b, sortSkill).status] : 3)) || a.localeCompare(b));
  const body = el("tbody");
  for (const id of order) {
    const row = el("tr", {}, el("td", {}, el("a", {href: "#detail", onclick: () => show(id)}, id)));
    for (const s of D.skills) {
      const c = cell(id, s);
      if (!c) { row.append(el("td", {class: "cell none"}, "—")); continue; }
      const arrow = c.trend > 0 ? " ↑" : c.trend < 0 ? " ↓" : "";
      const td = el("td", {class: "cell " + c.status, title: c.attempts.map(a => `${when(a.date)} ${a.title}: ${a.earned}/${a.possible}${a.support ? " (with support)" : ""}`).join("\n")},
        `${mark[c.status]} ${pct(c.pct)}${arrow}`);
      if (c.support) td.append(el("span", {class: "s", title: "with support"}, "S"));
      row.append(td);
    }
    body.append(row);
  }
  t.append(body);
}
grid();

for (const s of D.skills) {
  const g = own(D.groups, s);
  const box = el("div", {class: "card"}, el("strong", {}, s));
  const trend = own(D.trends, s) || [];
  if (trend.length) box.append(el("div", {class: "label"}, "Got it, by worksheet: " + trend.map(t => `${when(t.date)} ${pct(t.got)}`).join(" → ")));
  for (const status of ["practicing", "getting"]) {
    if (!g[status].length) continue;
    box.append(el("div", {}, el("span", {class: "label"}, word[status] + ": "), ...g[status].map(id => el("span", {class: "pill " + status}, id))));
  }
  if (!g.practicing.length && !g.getting.length) box.append(el("div", {class: "label"}, "Everyone has it."));
  document.getElementById("groups").append(box);
}

const st = document.getElementById("sheets");
st.append(el("thead", {}, el("tr", {}, ...["Date", "Worksheet", "Students", "Average", "Full credit by question"].map(h => el("th", {}, h)))));
const sb = el("tbody");
for (const w of [...D.worksheets].reverse()) {
  const bars = el("div", {class: "bars"}, ...w.questions.map(q => el("span", {style: `height:${Math.max(2, q.full * 34)}px`, title: `Q${q.q}: ${pct(q.full)} full credit (${q.skill})`})));
  sb.append(el("tr", {}, el("td", {}, when(w.date)), el("td", {}, w.title), el("td", {}, w.students), el("td", {}, pct(w.average)), el("td", {}, bars)));
}
st.append(sb);

const fadingIds = Object.keys(D.help_over_time || {});
if (!fadingIds.length) document.getElementById("fading-section").remove();
else {
  const ft = document.getElementById("fading");
  const dates = [...new Set(fadingIds.flatMap(id => D.help_over_time[id].map(r => r.date + "|" + r.title)))].sort();
  ft.append(el("thead", {}, el("tr", {}, el("th", {}, "ID"), ...dates.map(d => el("th", {}, `${when(d.split("|")[0])} ${d.split("|").slice(1).join("|")}`)))));
  const fb = el("tbody");
  for (const id of fadingIds) {
    const byDate = Object.fromEntries(D.help_over_time[id].map(r => [r.date + "|" + r.title, r]));
    fb.append(el("tr", {}, el("td", {}, id), ...dates.map(d => { const r = byDate[d];
      if (!r) return el("td", {class: "cell none"}, "—");
      const td = el("td", {class: "cell " + (r.pct >= 0.8 ? "got" : r.pct >= 0.5 ? "getting" : "practicing")}, pct(r.pct));
      if (r.help) td.append(el("span", {class: "s", title: "help on the page"}, "S"));
      return td; })));
  }
  ft.append(fb);
}

const saw = document.getElementById("saw");
const notes = D.worksheets.flatMap(w => w.saw.map(s => ({...s, title: w.title, date: w.date})));
if (!notes.length) saw.append(el("p", {class: "muted"}, "When you make a go-over deck after marking, what Claude noticed about the class's mistakes shows up here."));
for (const n of notes.reverse()) saw.append(el("p", {}, el("strong", {}, `${when(n.date)}, ${n.title}, Q${n.q}: `), n.saw));

const pick = document.getElementById("pick");
ids.forEach(id => pick.append(el("option", {value: id}, "ID " + id)));
pick.onchange = () => show(pick.value);
function show(id) {
  pick.value = id;
  const box = document.getElementById("detail"); box.replaceChildren();
  const s = D.summaries[id];
  if (s) box.append(el("div", {class: "card"}, el("div", {class: "label"}, `Latest feedback (${s.title})`), el("p", {}, s.strength || ""), ...(s.fixes || []).map(f => el("p", {}, "Next: " + f))));
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, ...["Skill", "Status", "Attempts"].map(h => el("th", {}, h)))));
  const b = el("tbody");
  for (const sk of D.skills) {
    const c = cell(id, sk); if (!c) continue;
    b.append(el("tr", {}, el("td", {}, sk), el("td", {class: "cell " + c.status}, word[c.status] + (c.support ? " (with support)" : "")),
      el("td", {}, c.attempts.map(a => `${when(a.date)}: ${a.earned}/${a.possible}${a.support ? " S" : ""}`).join(", "))));
  }
  t.append(b);
  box.append(el("div", {class: "scroll", style: "margin-top:12px"}, t));
}
function printOne() {  // a conference copy: one student's skills, none of the class's
  document.getElementById("one-title").textContent = `${D.class}: ID ${pick.value}`;
  document.body.classList.add("one");
  window.print();
  document.body.classList.remove("one");
}
if (ids.length) show(ids[0]);
</script></body></html>
"""
