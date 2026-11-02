"""The gradebook page: worksheet scores by class ID, for the teacher to match to their gradebook's file."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from test_progress import BLOCKER, SCRIPTS, _marked

from paper_loop_core import gradebook as GB  # noqa: E402

IDS = ["1012", "1023", "1034", "1045", "1056"]  # setup's numbers: the class, the place, a check digit


def _data(page: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1))


def test_the_page_holds_each_score_by_class_id_in_class_list_order(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"1034": {1: 0}, "1012": {}, "1023": {1: 1}}, pages_of={"1023": [1, 2]})
    (cls / "roster.csv").write_text("id\n" + "\n".join(reversed(IDS)) + "\n")
    report = GB.build(cls, class_name="Period 3 Math")
    page = report["out"].read_text()
    data = _data(page)
    assert data["ids"] == IDS and data["numbered"] and data["roster"]  # the roster in the folder, in place order
    sheet = data["worksheets"][0]
    assert sheet["possible"] == 13 and set(sheet["students"]) == {"1012", "1023", "1034"}
    assert sheet["students"]["1012"] == {"earned": 13, "possible": 13, "missing": [], "help": False, "version": ""}
    assert sheet["students"]["1034"]["earned"] == 9  # Q1, worth 4, missed
    assert sheet["students"]["1023"]["missing"] == [3, 4, 5]  # still in the review pile: left blank, not a low score
    assert report["incomplete"] == [(sheet["title"], "1023", [3, 4, 5])]
    # Names only ever come from files the teacher opens in the page, which can't send anything anywhere.
    assert re.search(r'<meta http-equiv="Content-Security-Policy" content="default-src \'none\';', page)
    assert not re.search(r"<(script|link|img)[^>]+(src|href)=\"https?://", page)
    assert "Period 3 Math: gradebook" in page and "prefers-color-scheme: dark" in page
    assert "{{" not in page
    for gradebook in ("canvas", "classroom", "powerteacher", "schoology", "campus", "skyward", "aeries", "brightspace"):
        assert f'id: "{gradebook}"' in page


def test_the_page_s_script_parses(tmp_path):
    import shutil
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node isn't installed")
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"1012": {}})
    page = GB.build(cls)["out"].read_text()
    script = tmp_path / "page.js"
    script.write_text(page.split('<script>', 1)[1].split("</script>", 1)[0])
    run = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_practice_sheets_and_blank_pages_aren_t_graded(tmp_path):
    from paper_loop_core import practice as PR
    from paper_loop_core import sheet as S
    cls = tmp_path / "Period 3"
    work = _marked(cls, "week1", "2026-10-20", {"1012": {1: 0}, "1023": {}, "1034": {}}, blank=("1034",))
    PR.build(work, cls / "practice")
    items = S.form_items(S.read_json(cls / "practice" / "key.json"), "p1012")
    mark = cls / "practice" / "marking-2026-10-22"
    mark.mkdir()
    S.write_json(mark / "manifest.json", {"assignment_dir": str(cls / "practice"), "pages": [],
                                          "title": S.read_json(cls / "practice" / "layout.json")["title"]})
    S.write_json(mark / "results.json", {"pages": [{"scan_index": 1, "student_id": "1012", "page": 1, "form": "p1012",
        "boxes": [{"q": q, "type": i["type"], "verdict": "correct", "points_awarded": i["points"],
                   "points_possible": i["points"], "details": []} for q, i in items.items()]}]})
    data = _data(GB.build(cls)["out"].read_text())
    assert len(data["worksheets"]) == 1  # practice sheets differ by student: not a grade
    assert set(data["worksheets"][0]["students"]) == {"1012", "1023"}  # 1034 was absent: blank, not a zero
    assert data["roster"] is False and data["ids"] == ["1012", "1023"]


def test_ids_not_made_by_setup_are_matched_by_the_teacher_s_list(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"4411": {}, "9273": {1: 0}})
    data = _data(GB.build(cls)["out"].read_text())
    assert data["numbered"] is False and data["ids"] == ["4411", "9273"]


def test_the_gradebook_page_runs_in_the_sandbox(tmp_path):
    cls = tmp_path / "Period 3"
    _marked(cls, "week1", "2026-10-20", {"1012": {1: 0}, "1023": {}})
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "gradebook", str(cls)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "gradebook.html" in run.stdout and "2 scored, out of 13 points" in run.stdout
    assert "never ask for it" in run.stdout
    empty = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "gradebook", str(tmp_path / "x")],
                           capture_output=True, text=True)
    assert empty.returncode == 1 and "no marked worksheets" in empty.stdout
