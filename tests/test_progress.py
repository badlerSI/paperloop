"""Progress across worksheets: the teacher's dashboard, family pages, and the gradebook file."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import progress as PG  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402

BLOCKER = (Path(__file__).parent / "test_plugin.py").read_text().split('BLOCKER = """')[1].split('"""')[0]
SKILLS = {1: "I can make equivalent ratios", 2: "I can find a unit rate", 3: "I can graph a ratio",
          4: "I can make equivalent ratios"}


def _marked(folder: Path, name: str, day: str, scores: dict[str, dict[int, float]], form: dict[str, str] = None,
            source: Path = ROOT / "examples" / "math6-ratios-02.json") -> None:
    """A worksheet made in folder/name and a marked class of it, from points per student and question."""
    defn = S.read_json(source)
    for q in defn["questions"]:
        if q.get("q") in SKILLS:
            q["skill"] = SKILLS[q["q"]]
    S.make_worksheet(defn, folder / name, base=source.parent)
    key = S.read_json(folder / name / "key.json")
    work = folder / name / f"marking-{day}"
    work.mkdir(parents=True)
    pages = []
    for k, (sid, points) in enumerate(scores.items()):
        boxes = []
        for item in key["items"]:
            got = points.get(item["q"], item["points"])
            verdict = "correct" if got == item["points"] else "incorrect" if got == 0 else "partial"
            boxes.append({"q": item["q"], "type": item["type"], "verdict": verdict, "points_awarded": got,
                          "points_possible": item["points"], "details": []})
        pages.append({"scan_index": k + 1, "student_id": sid, "page": 1, "form": (form or {}).get(sid, ""),
                      "boxes": boxes})
    S.write_json(work / "manifest.json", {"assignment_dir": str(folder / name), "title": defn["title"], "pages": []})
    S.write_json(work / "results.json", {"pages": pages})
    S.write_json(work / "summaries.json", {sid: {"strength": f"Strong table work, {sid}.", "fixes": ["Check units."]}
                                           for sid in scores})


def test_progress_follows_each_skill_and_marks_support(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"0101": {1: 0, 2: 0}, "0102": {}, "0103": {1: 2}})
    _marked(cls, "week2", "2026-10-27", {"0101": {}, "0102": {1: 0}, "0103": {}}, form={"0103": "support"})
    report = PG.build(cls)
    data = S.read_json(report["out"] / "progress.json")
    assert data["skills"] == ["I can make equivalent ratios", "I can find a unit rate", "I can graph a ratio",
                              "I can explain ratio reasoning"]
    ratios = data["students"]["0101"]["I can make equivalent ratios"]
    assert [round(a["pct"], 2) for a in ratios["attempts"]] == [0.2, 1.0] and ratios["status"] == "got"
    assert ratios["trend"] == 1
    assert data["students"]["0102"]["I can make equivalent ratios"]["status"] == "practicing"
    assert data["students"]["0103"]["I can make equivalent ratios"]["support"] is True  # hints and fewer choices
    assert data["groups"]["I can make equivalent ratios"]["practicing"] == ["0102"]
    rows = list(csv.reader((report["out"] / "progress.csv").open()))
    assert rows[0][:3] == ["student_id", "I can make equivalent ratios", "I can make equivalent ratios: help on the page"]
    assert rows[3][1:3] == ["100", "yes"]  # scores stay numbers; help on the page is its own column
    assert report["missing"] == data["skills"]  # no skills.json yet: a work order lists what to write
    log = list(csv.reader((report["out"] / "supports.csv").open()))
    assert log[0][:4] == ["student_id", "date", "worksheet", "version"]
    assert [r[0] for r in log[1:]] == ["0103"] and "supports on the page" in log[1][4]  # for a case manager
    fading = data["help_over_time"]
    assert list(fading) == ["0103"] and [r["help"] for r in fading["0103"]] == [False, True]
    assert "Help on the page, over time" in (report["out"] / "dashboard.html").read_text()
    todo = (report["out"] / "progress-todo.md").read_text()
    assert "I can find a unit rate" in todo and '"home"' in todo


def test_the_dashboard_stands_alone_and_names_no_one(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"0101": {1: 0}, "0102": {}})
    report = PG.build(cls, class_name="Period 3 Math")
    page = (report["out"] / "dashboard.html").read_text()
    assert not re.search(r"<(script|link|img)[^>]+(src|href)=\"https?://", page)  # nothing loads from the web
    assert "Period 3 Math: progress" in page and '"0101"' in page
    assert "prefers-color-scheme: dark" in page


def test_family_pages_have_a_line_for_the_name_and_speak_the_family_language(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"0101": {1: 0}, "0104": {}})
    S.write_json(cls / "skills.json", {"skills": {s: {"family": f"In plain words: {s}.", "home": f"Try at home: {s}."}
                                                  for s in [*SKILLS.values(), "I can explain ratio reasoning"]}})
    S.write_json(cls / "families.json", {"0104": "es"})
    report = PG.build(cls)
    assert report["languages"] == [("es", ["0104"])] and not (report["out"] / "parents-es.docx").exists()
    S.write_json(cls / "parents.es.json", {"labels": {"title": "Informe de progreso", "student": "Estudiante",
                                                      "months": ["enero"] * 9 + ["octubre", "nov", "dic"],
                                                      "date": "{day} de {month}"},
                                           "skills": {SKILLS[1]: {"family": "Hacer razones equivalentes."}},
                                           "feedback": {"0104": {"strength": "Buen trabajo con la tabla.",
                                                                 "fixes": ["Revisa las unidades."]}},
                                           "reviewed_by": "bilingual aide"})
    report = PG.build(cls)
    english = zipfile.ZipFile(report["out"] / "parents.docx").read("word/document.xml").decode()
    assert "Student: ______" in english and "In plain words: I can find a unit rate." in english
    assert "Try at home: I can make equivalent ratios." in english  # 0101 is still practicing it
    assert "0101" in english and "0104" not in english  # 0104's family gets theirs in Spanish
    assert "AI tool (Claude)" in english and "interpreter" in english
    spanish = zipfile.ZipFile(report["out"] / "parents-es.docx").read("word/document.xml").decode()
    assert "Estudiante: ______" in spanish and "20 de octubre" in spanish and "Hacer razones equivalentes." in spanish
    assert "Buen trabajo con la tabla." in spanish and "Strong table work" not in spanish
    assert "0101" not in spanish and report["unreviewed"] == []  # only the families who read Spanish
    assert not (report["out"] / "progress-todo.md").exists()


def test_progress_runs_in_the_sandbox(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"0101": {1: 0}, "0102": {}})
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "progress", str(cls)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "dashboard.html" in run.stdout and "Still practicing \"I can make equivalent ratios\": IDs 0101" in run.stdout
    empty = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "progress", str(tmp_path / "x")],
                           capture_output=True, text=True)
    assert empty.returncode == 1 and "no marked classes" in empty.stdout


def test_a_retry_of_the_same_question_is_shown_but_doesnt_set_the_status():
    item = {"q": 1, "skill": "I can find a unit rate", "points": 2, "prompt": "?"}
    run = lambda day, earned, retry: {"date": day, "title": "T", "items": [item], "saw": [], "summaries": {},  # noqa: E731
                                      "students": {"0101": {"form": "", "support": False, "answers": {1: {
                                          "earned": earned, "possible": 2.0, "verdict": "x", "support": False,
                                          "retry": retry}}}}}
    data = PG.analyze([run("2026-10-20", 0.0, False), run("2026-10-21", 2.0, True)])
    cell = data["students"]["0101"]["I can find a unit rate"]
    assert cell["status"] == "practicing" and len(cell["attempts"]) == 2  # the retry shows, but isn't new evidence
    data = PG.analyze([run("2026-10-20", 0.0, False), run("2026-10-21", 2.0, False)])
    assert data["students"]["0101"]["I can find a unit rate"]["status"] == "got"
