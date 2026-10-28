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
            source: Path = ROOT / "examples" / "math6-ratios-02.json", blank: tuple[str, ...] = (),
            work_name: str | None = None, pages_of: dict[str, list[int]] | None = None, skills: bool = True) -> Path:
    """A worksheet made in folder/name and a marked class of it, from points per student and question.
    blank: students whose every answer is blank. pages_of: the only questions marked for a student."""
    defn = S.read_json(source)
    for q in defn["questions"]:
        if q.get("q") in SKILLS and skills:
            q["skill"] = SKILLS[q["q"]]
    if not (folder / name / "key.json").exists():
        S.make_worksheet(defn, folder / name, base=source.parent)
    key = S.read_json(folder / name / "key.json")
    work = folder / name / (work_name or f"marking-{day}")
    work.mkdir(parents=True)
    pages = []
    for k, (sid, points) in enumerate(scores.items()):
        boxes = []
        for item in key["items"]:
            if pages_of and sid in pages_of and item["q"] not in pages_of[sid]:
                continue
            got = 0 if sid in blank else points.get(item["q"], item["points"])
            verdict = "blank" if sid in blank else "correct" if got == item["points"] else \
                "incorrect" if got == 0 else "partial"
            boxes.append({"q": item["q"], "type": item["type"], "verdict": verdict, "points_awarded": got,
                          "points_possible": item["points"], "details": []})
        pages.append({"scan_index": k + 1, "student_id": sid, "page": 1, "form": (form or {}).get(sid, ""),
                      "boxes": boxes})
    S.write_json(work / "manifest.json", {"assignment_dir": str(folder / name), "title": defn["title"], "pages": []})
    S.write_json(work / "results.json", {"pages": pages})
    S.write_json(work / "summaries.json", {sid: {"strength": f"Strong table work, {sid}.", "fixes": ["Check units."]}
                                           for sid in scores})
    return work


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


def test_a_missed_stretch_question_is_practiced_again_with_the_worksheet_s_skill(tmp_path):
    from paper_loop_core import practice as PR
    source = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    source.pop("versions")
    source["stretch"] = [{"type": "short", "q": 11, "prompt": "Why does doubling both parts keep a ratio?",
                          "key": "Each part grows by the same factor."},
                         {"type": "short", "q": 12, "prompt": "Make a ratio equal to 3 : 5.", "key": "6 : 10, or any multiple."}]
    S.write_json(tmp_path / "src.json", source)
    cls = tmp_path / "P9"
    _marked(cls, "week1", "2026-10-20", {"0901": {}, "0902": {1: 0}}, source=tmp_path / "src.json")
    first = PR.build(cls / "week1" / "marking-2026-10-20", tmp_path / "practice")
    assert first["stretched"] == ["0901"] and first["questions"]["0901"] == [11, 12]
    key = S.read_json(tmp_path / "practice" / "key.json")
    items = S.form_items(key, "p0901")
    assert items[11]["skill"] == "Smoothie Stand Ratios"  # the worksheet's own, never "Practice: ..."
    again = tmp_path / "pmark"
    again.mkdir()
    S.write_json(again / "manifest.json", {"assignment_dir": str(tmp_path / "practice"), "title": "Practice", "pages": []})
    S.write_json(again / "results.json", {"pages": [{"scan_index": 1, "student_id": "0901", "page": 1, "form": "p0901",
        "boxes": [{"q": 11, "type": "short", "verdict": "incorrect", "points_awarded": 0,
                   "points_possible": items[11]["points"], "comment": "Say what happens to both parts.", "details": []}]}]})
    second = PR.build(again, tmp_path / "practice2")  # was a KeyError: 11
    assert second["questions"]["0901"] == [11]


# --- Regressions from the third code review -------------------------------------------------------

def test_a_blank_sheet_is_absent_not_a_zero(tmp_path):
    from paper_loop_core import teamwork as TW
    cls = tmp_path / "P"
    _marked(cls, "week1", "2026-10-20", {"0101": {}, "0102": {1: 0, 2: 0}, "0103": {}, "0104": {1: 0}})
    _marked(cls, "week2", "2026-10-27", {"0101": {}, "0102": {}, "0103": {}, "0104": {}}, blank=("0101",))
    data = PG.analyze(PG.collect(cls))
    assert all(c["status"] == "got" for c in data["students"]["0101"].values())  # not "still practicing 0%"
    assert [w["students"] for w in data["worksheets"]] == [4, 3]
    similar = TW.form_groups(cls, size=2, structure="pairs", similar=True)
    assert {sid for sid, _ in similar["groups"][0]} == {"0101", "0103"}  # still ranked by the work they did


def test_a_spreadsheet_roster_of_two_digit_ids(tmp_path):
    from paper_loop_core import teamwork as TW
    source = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    source["id_digits"] = 2
    source.pop("versions")
    S.write_json(tmp_path / "src.json", source)
    cls = tmp_path / "Room 12"
    _marked(cls, "week1", "2026-10-20", {"07": {1: 0}, "08": {}}, source=tmp_path / "src.json")
    roster = tmp_path / "ids.csv"
    roster.write_text("id\n7\n8\n11\n")  # a spreadsheet drops the leading zero
    assert PG.class_digits(cls) == 2
    report = PG.build(cls, roster_path=roster)
    assert report["students"] == 2
    groups = TW.form_groups(cls, size=3, roster_path=roster)
    assert sorted(sid for g in groups["groups"] for sid, _ in g) == ["07", "08", "11"]


def test_a_re_marked_scan_counts_once_and_the_latest_marking_wins(tmp_path):
    cls = tmp_path / "P"
    _marked(cls, "week1", "2026-10-20", {"0101": {1: 0}, "0102": {}})
    _marked(cls, "week1", "2026-10-20", {"0101": {}, "0102": {}}, work_name="marking-2026-10-20-redo")
    _marked(cls, "week1", "2026-10-21", {"0103": {2: 0}}, work_name="marking-makeup")  # a make-up joins it
    runs = PG.collect(cls)
    assert len(runs) == 1 and sorted(runs[0]["students"]) == ["0101", "0102", "0103"]
    data = PG.analyze(runs)
    cell = data["students"]["0101"]["I can make equivalent ratios"]
    assert cell["status"] == "got" and len(cell["attempts"]) == 1 and cell["questions"] == 2


def test_practice_counts_toward_the_worksheet_s_skills(tmp_path):
    from paper_loop_core import practice as PR
    source = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    source.pop("versions")
    for q in source["questions"]:
        q.pop("skill", None)
    S.write_json(tmp_path / "src.json", source)
    cls = tmp_path / "P"
    work = _marked(cls, "week1", "2026-10-20", {"0101": {1: 0, 2: 0}, "0102": {}}, source=tmp_path / "src.json",
                   skills=False)
    PR.build(work, cls / "practice")
    key = S.read_json(cls / "practice" / "key.json")
    items = S.form_items(key, "p0101")
    mark = cls / "practice" / "marking-2026-10-22"
    mark.mkdir()
    S.write_json(mark / "manifest.json", {"assignment_dir": str(cls / "practice"), "pages": [],
                                          "title": S.read_json(cls / "practice" / "layout.json")["title"]})
    S.write_json(mark / "results.json", {"pages": [{"scan_index": 1, "student_id": "0101", "page": 1, "form": "p0101",
        "boxes": [{"q": q, "type": i["type"], "verdict": "correct", "points_awarded": i["points"],
                   "points_possible": i["points"], "details": []} for q, i in items.items()]}]})
    data = PG.analyze(PG.collect(cls))
    assert data["skills"] == ["Smoothie Stand Ratios"]  # the worksheet's title, never "Practice: ..."
    cell = data["students"]["0101"]["Smoothie Stand Ratios"]
    assert [a["date"] for a in cell["attempts"]] == ["2026-10-20", "2026-10-22"]


def test_the_family_page_shows_the_attempt_the_status_comes_from():
    item = {"q": 1, "skill": "I can find a unit rate", "points": 2, "prompt": "?"}
    run = lambda day, earned, retry: {"date": day, "title": "T", "items": [item], "saw": [], "summaries": {},  # noqa: E731
                                      "students": {"0101": {"form": "", "support": False, "answers": {1: {
                                          "earned": earned, "possible": 2.0, "verdict": "x", "support": False,
                                          "retry": retry}}}}}
    cell = PG.analyze([run("2026-10-20", 0.0, False), run("2026-10-21", 2.0, True)])["students"]["0101"]
    assert cell["I can find a unit rate"]["latest"]["earned"] == 0.0  # not the retry's 2 of 2


def test_a_translated_label_must_keep_its_blanks(tmp_path):
    import pytest
    cls = tmp_path / "P"
    _marked(cls, "week1", "2026-10-20", {"0104": {}})
    S.write_json(cls / "families.json", {"0104": "es"})
    S.write_json(cls / "parents.es.json", {"labels": {"dates": "Trabajo del {inicio} al {fin}"}})
    with pytest.raises(PG.ProgressError, match=r"keep \{end\}, \{start\}"):
        PG.build(cls)


def test_the_same_choices_in_a_new_order_are_a_retry(tmp_path):
    from paper_loop_core import practice as PR
    source = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    source.pop("versions")
    S.write_json(tmp_path / "src.json", source)
    work = _marked(tmp_path / "P", "week1", "2026-10-20", {"0101": {4: 0}, "0102": {}}, source=tmp_path / "src.json")
    PR.build(work, tmp_path / "practice")
    item = S.form_items(S.read_json(tmp_path / "practice" / "key.json"), "p0101")[4]
    assert item.get("retry") is True  # no new numbers: progress shows it but doesn't count it as new evidence


def test_practice_on_a_version_keeps_its_pages_and_its_language(tmp_path):
    import shutil
    from paper_loop_core import practice as PR
    for lang in ("es", "ar", "bn"):
        shutil.copy(ROOT / "examples" / f"math6-ratios-02.{lang}.json", tmp_path)
    source = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    source["stretch"] = [{"type": "short", "q": 11, "prompt": "Why does doubling both parts keep a ratio?",
                          "key": "Each part grows by the same factor."}]
    S.write_json(tmp_path / "math6-ratios-02.json", source)
    es = S.read_json(tmp_path / "math6-ratios-02.es.json")
    es["questions"]["11"] = "¿Por qué duplicar ambas partes mantiene la razón?"
    S.write_json(tmp_path / "math6-ratios-02.es.json", es)
    work = _marked(tmp_path / "P", "week1", "2026-10-20", {"0102": {1: 0}, "0106": {1: 0}, "0104": {}},
                   form={"0102": "support", "0106": "bn", "0104": "es"}, source=tmp_path / "math6-ratios-02.json")
    report = PR.build(work, tmp_path / "practice")
    extras = " ".join(report["extras"])
    assert "versions/p0102-reference.pdf" in extras and "versions/p0106.docx" in extras  # were dropped
    assert report["stretched"] == ["0104"]
    sheet = next(s for s in S.read_json(tmp_path / "practice" / "source.json")["personal"] if s["student_id"] == "0104")
    assert "¿Por qué duplicar" in json.dumps(sheet["questions"], ensure_ascii=False)  # the stretch, in Spanish too


def test_a_bilingual_practice_sheet_keeps_the_translated_passage(tmp_path):
    from paper_loop_core import practice as PR
    source = S.read_json(ROOT / "examples" / "ela4-garden-01.json")
    source["versions"] = [{"id": "es", "language": "es"}]
    S.write_json(tmp_path / "ela4-garden-01.json", source)
    S.write_json(tmp_path / "ela4-garden-01.es.json", {"language": "es", "title": "El jardín en la azotea",
                                                       "passages": {"story": "Amara plantó frijoles en la azotea."},
                                                       "questions": {"3": "¿Por qué crecieron los frijoles?"}})
    folder = tmp_path / "P"
    S.make_worksheet(source, folder / "garden", base=tmp_path)
    key = S.read_json(folder / "garden" / "key.json")
    work = folder / "garden" / "marking"
    work.mkdir()
    boxes = [{"q": i["q"], "type": i["type"], "verdict": "incorrect" if i["q"] == 3 else "correct",
              "points_awarded": 0 if i["q"] == 3 else i["points"], "points_possible": i["points"], "details": []}
             for i in S.form_items(key, "es").values()]
    S.write_json(work / "manifest.json", {"assignment_dir": str(folder / "garden"), "title": "Garden", "pages": []})
    S.write_json(work / "results.json", {"pages": [{"scan_index": 1, "student_id": "0423", "page": 1, "form": "es",
                                                    "boxes": boxes}]})
    PR.build(work, tmp_path / "practice")
    sheet = S.read_json(tmp_path / "practice" / "source.json")["personal"][0]
    texts = [q.get("text", "") for q in sheet["questions"] if q.get("type") == "passage"]
    assert any("Amara plantó frijoles" in t for t in texts) and len(texts) == 2  # the story, and its translation


def test_a_missed_stretch_question_doesn_t_count_against_the_skill(tmp_path):
    from paper_loop_core import practice as PR
    source = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    source.pop("versions")
    source["stretch"] = [{"type": "short", "q": 11, "prompt": "Why does doubling both parts keep a ratio?",
                          "key": "Each part grows by the same factor."}]
    S.write_json(tmp_path / "src.json", source)
    cls = tmp_path / "P"
    work = _marked(cls, "week1", "2026-10-20", {"0901": {}, "0902": {1: 0}}, source=tmp_path / "src.json")
    PR.build(work, cls / "practice")
    items = S.form_items(S.read_json(cls / "practice" / "key.json"), "p0901")
    assert items[11].get("stretch") is True
    mark = cls / "practice" / "marking"
    mark.mkdir()
    S.write_json(mark / "manifest.json", {"assignment_dir": str(cls / "practice"), "title": "Practice", "pages": []})
    S.write_json(mark / "results.json", {"pages": [{"scan_index": 1, "student_id": "0901", "page": 1, "form": "p0901",
        "boxes": [{"q": 11, "type": "short", "verdict": "incorrect", "points_awarded": 0,
                   "points_possible": items[11]["points"], "details": []}]}]})
    cells = PG.analyze(PG.collect(cls))["students"]["0901"]
    assert all(c["status"] == "got" and len(c["attempts"]) == 1 for c in cells.values())  # beyond the bar
