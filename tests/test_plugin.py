"""The Cowork plugin's scripts: same sheets as the CLI, no OpenCV, and Claude's marks in between."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import prepare as P  # noqa: E402
from paper_loop_core import results as X  # noqa: E402
from paper_loop_core import scan as L  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402

from paperloop.make import make_worksheet  # noqa: E402
from paperloop.schemas import Feedback, IngestResult, WorksheetDef, load  # noqa: E402
from paperloop.simulate import simulate  # noqa: E402

EXAMPLE = ROOT / "examples" / "sci6-water-01.json"
BLOCKER = """
import runpy, sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"cv2", "pydantic", "qrcode", "typer", "anthropic", "paperloop", "dotenv"}:
            raise ImportError(name + " isn't in Claude's sandbox")
sys.meta_path.insert(0, Block())
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


@pytest.fixture(scope="module")
def water(tmp_path_factory):
    """The water worksheet made by the plugin, and a simulated class set of it (handwriting fonts,
    tilt, blur, one sheet upside down, a blank page, shuffled)."""
    root = tmp_path_factory.mktemp("plugin")
    S.make_worksheet(S.read_json(EXAMPLE), root / "assignment")
    pdf = simulate(root / "assignment", root / "class.pdf")
    return root, pdf, json.loads(pdf.with_suffix(".truth.json").read_text())


def test_runs_without_opencv_or_pydantic(tmp_path):
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "make", str(EXAMPLE),
                          "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "out" / "worksheet.pdf").exists()


def test_layout_matches_the_cli(water, tmp_path):
    root, _, _ = water
    make_worksheet(load(WorksheetDef, EXAMPLE), tmp_path / "cli")
    ours, cli = S.read_json(root / "assignment" / "layout.json"), S.read_json(tmp_path / "cli" / "layout.json")
    plugin_only = ("line_spacing", "scale")  # fields the plugin adds for versions and its simulator
    strip = lambda page: [{k: v for k, v in b.items() if k not in plugin_only} for b in page["boxes"]]  # noqa: E731
    assert json.loads(json.dumps(strip(ours["pages"][0]))) == strip(cli["pages"][0])
    ours_key, cli_key = S.read_json(root / "assignment" / "key.json"), S.read_json(tmp_path / "cli" / "key.json")
    assert [{k: item[k] for k in cli_item} for item, cli_item in zip(ours_key["items"], cli_key["items"])] \
        == cli_key["items"]  # the plugin's key adds fields, but agrees on every one the CLI has


def test_page_code_round_trip_and_checksum():
    code = S.page_code("sci6-water-01", 3)
    bits = S.code_bits(code)
    assert S.parse_code(bits) == (S.assignment_hash("sci6-water-01"), 3)
    for i in (0, 13, 31):  # any one square misread fails the checksum instead of naming the wrong page
        flipped = list(bits)
        flipped[i] ^= 1
        assert S.parse_code(flipped) is None


@pytest.mark.parametrize("quarter_turns", [0, 1, 2, 3])
def test_markers_found_in_any_orientation(water, quarter_turns):
    root, _, _ = water
    page = np.rot90(L.template(root / "assignment", 1), quarter_turns).copy()
    markers = L.find_markers(page)
    assert sorted(markers) == [0, 1, 2, 3]
    canonical, error = L.register(page, markers)
    assert error < 1.0
    assert L.read_code(canonical) == (S.assignment_hash("sci6-water-01"), 1)


def test_simulated_class_set_is_read_like_the_cli_reads_it(water, tmp_path):
    root, pdf, truth = water
    manifest = P.prepare([pdf], root / "assignment", tmp_path / "work")
    expected = {t["scan_index"]: t for t in truth["scan_pages"]}
    answers = {s["id"]: s["answers"] for s in truth["students"]}
    for page in manifest["pages"]:
        t = expected[page["scan_index"]]
        if t.get("blank"):
            assert page["status"] == "blank"
            continue
        assert page["status"] == "ok" and page["identified_by"] == "code" and page["id_image"]
        for q, answer in page["answers"].items():
            written = answers[t["student_id"]].get(q)
            assert (answer["status"] == "blank") == (not written), f"scan {page['scan_index']} Q{q}"
            if written and "circle" in written and not any(m.startswith("~~") for m in written["circle"]):
                assert answer["status"] == "scan" and answer["read"] == written["circle"][-1]


def test_roster_neighbor_rule(water, tmp_path):
    root, pdf, truth = water
    work = tmp_path / "work"
    manifest = P.prepare([pdf], root / "assignment", work)
    ids = {t["scan_index"]: t["student_id"] for t in truth["scan_pages"] if not t.get("blank")}
    reads = {str(scan): {"digits": sid, "confidence": 0.6} for scan, sid in ids.items()}
    (work / "ids.json").write_text(json.dumps(reads))
    roster = set(ids.values()) | {"3157"}  # one digit from 3158
    routed = {p["scan_index"]: (p["status"], p["student_id"], p["reason"]) for p in P.route(work, roster)["pages"]}
    for scan, sid in ids.items():
        if sid == "3158":
            assert routed[scan][0] == "review" and "3157 on the roster is one digit away" in routed[scan][2]
        else:
            assert routed[scan][:2] == ("ok", sid)
    unrouted = {p["scan_index"]: p["status"] for p in P.route(work, None)["pages"] if p.get("id_image")}
    assert set(unrouted.values()) == {"review"}  # 0.6 isn't enough without a roster
    assert len(manifest["pages"]) == len(routed)


def test_marks_to_printed_pdf_in_the_cli_format(water, tmp_path):
    root, pdf, truth = water
    work = tmp_path / "work"
    P.prepare([pdf], root / "assignment", work)
    ids = {t["scan_index"]: t["student_id"] for t in truth["scan_pages"] if not t.get("blank")}
    (work / "ids.json").write_text(json.dumps({str(s): {"digits": i, "confidence": 0.95} for s, i in ids.items()}))
    P.route(work)
    shapes = {
        "short": {"transcription": "x", "verdict": "partial", "comment": "Say where the water came from.",
                  "confidence": 0.9},
        "choice": {"selected": ["A"], "crossed_out": ["C"], "confidence": 0.9},
        "label": {"labels": [{"n": n, "transcription": "x", "verdict": "correct", "confidence": 0.9}
                             for n in (1, 2, 3)], "comment": "Each label fits its arrow.", "confidence": 0.9},
        "draw": {"description": "x", "items": [{"n": n, "met": "yes"} for n in range(1, 5)],
                 "comment": "Clear cycle.", "confidence": 0.9},
    }
    for path in P.todo(work):
        q = int(path.stem[1:])
        kind = S.read_json(root / "assignment" / "key.json")["items"][q - 1]["type"]
        scans = [line.split(":")[0].split()[-1] for line in path.read_text().splitlines() if line.startswith("- scan ")]
        (work / "marks" / f"q{q}.json").write_text(json.dumps({"q": q, "marks": {s: shapes[kind] for s in scans}}))

    result = X.check(work)
    assert any("no answer for checklist item 5" in e for e in result["errors"])  # the draw mark skipped item 5
    marks = S.read_json(work / "marks" / "q5.json")
    for mark in marks["marks"].values():
        mark["items"].append({"n": 5, "met": "unclear"})
    S.write_json(work / "marks" / "q5.json", marks)
    result = X.check(work)
    assert not result["errors"] and any("checklist item 5 unclear" in f for f in result["flagged"])

    summaries = {p["student_id"]: {"strength": "A start.", "fixes": []} for p in result["pages"]}
    S.write_json(work / "summaries.json", summaries)
    run = subprocess.run([sys.executable, str(SCRIPTS / "paper_loop.py"), "render", str(work)],
                         capture_output=True, text=True)
    assert run.returncode == 1 and "haven't been reviewed" in run.stdout  # the teacher sees flags first
    run = subprocess.run([sys.executable, str(SCRIPTS / "paper_loop.py"), "render", str(work), "--accept-flags"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert (work / "out" / "returned.pdf").exists()
    feedback = load(Feedback, work / "feedback.json")  # readable by the CLI's `score`
    load(IngestResult, work / "ingest.json")
    assert sorted(p.student_id for p in feedback.pages) == sorted(ids.values())


def test_roster_survives_a_spreadsheet(tmp_path):
    roster = tmp_path / "ids.csv"
    roster.write_text("id\n417\n2093\n6\n")  # leading zeros dropped, as a spreadsheet saves them
    assert P.load_roster(roster) == {"0417", "2093", "0006"}
    roster.write_text("3158\n0417\n")  # no header
    assert P.load_roster(roster) == {"3158", "0417"}


def test_blank_pages_are_named_and_zoom_enlarges(water, tmp_path):
    root, pdf, truth = water
    work = tmp_path / "work"
    P.prepare([pdf], root / "assignment", work)
    ids = {t["scan_index"]: t["student_id"] for t in truth["scan_pages"] if not t.get("blank")}
    (work / "ids.json").write_text(json.dumps({str(s): {"digits": i, "confidence": 0.95} for s, i in ids.items()}))
    manifest = P.route(work)
    blank_students = {s["id"] for s in truth["students"] if not s["answers"]}
    assert {p["student_id"] for p in P.all_blank(manifest)} == blank_students
    crop = next(work / a["crop"] for p in manifest["pages"] if p["status"] == "ok" for a in p["answers"].values())
    run = subprocess.run([sys.executable, str(SCRIPTS / "paper_loop.py"), "zoom", str(crop), "--region",
                          "0,0,0.5,0.5"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    zoomed = Path(run.stdout.split(" (")[0])
    assert zoomed.exists() and L.load_png(zoomed).shape[1] > L.load_png(crop).shape[1] / 2


# --- All subjects, grades 2-12 -------------------------------------------------------------

PLUGIN_EXAMPLES = sorted(p for p in (ROOT / "plugin" / "skills" / "paper-loop" / "references" / "examples").glob("*.json")
                         if not p.stem.endswith(("-lesson", "-pieces"))  # lessons: tests/test_lessons.py
                         and "." not in p.stem)  # a version's translation (math6-ratios-02.es.json)
PAGE_BUDGET = {"math6-ratios-01": 1, "span9-casa-01": 1, "sci3-plants-01": 1, "ela11-argument-01": 1,
               "cs10-loops-01": 1, "chem10-moles-01": 1, "mus5-notes-01": 1, "math7-data-01": 1}


@pytest.mark.parametrize("path", PLUGIN_EXAMPLES, ids=lambda p: p.stem)
def test_every_example_worksheet_makes(path, tmp_path):
    defn = S.read_json(path)
    layout = S.make_worksheet(defn, tmp_path / path.stem, base=path.parent)
    assert layout["unprintable"] == ""
    assert layout["base_pages"] <= PAGE_BUDGET.get(path.stem, 2)
    key = S.read_json(tmp_path / path.stem / "key.json")
    assert key["grade"] == S.normalize(defn)["grade"]
    for page in layout["pages"]:
        for box in page["boxes"]:
            x0, y0, x1, y1 = box["rect"]
            assert y0 > page["summary_rect"][3] and y1 <= S.CONTENT_TOP + 1  # nothing runs into the header or summary
            for spot in box["labels"]:
                sx0, sy0, sx1, sy1 = spot["rect"]
                assert sx1 > sx0 and sy1 > sy0


def test_grade_sets_style_ids_and_comment_length(tmp_path):
    base = {"assignment_id": "t", "title": "T", "questions": [{"type": "short", "q": 1, "prompt": "p", "key": "k"}]}
    young = S.make_worksheet({**base, "grade": 2}, tmp_path / "young")
    older = S.make_worksheet({**base, "grade": 10}, tmp_path / "older")
    assert young["style"] == "primary" and len(young["pages"][0]["id_boxes"]) == 2
    assert older["style"] == "standard" and len(older["pages"][0]["id_boxes"]) == 4
    assert S.read_json(tmp_path / "young" / "key.json")["comment_words"] == 16  # two short sentences
    assert S.read_json(tmp_path / "older" / "key.json")["comment_words"] == 25
    assert S.normalize({**base, "grade_band": "middle school (grade 6)"})["grade"] == 6


def test_math_symbols_get_a_font_that_prints_them(tmp_path):
    defn = {"assignment_id": "t", "title": "Roots", "grade": 9,
            "questions": [{"type": "math", "q": 1, "prompt": "Simplify √49 + π·0", "answer": "7"}]}
    layout = S.make_worksheet(defn, tmp_path / "m")
    assert layout["unprintable"] == ""


def test_code_keeps_its_lines_indentation_and_numbers(tmp_path):
    code = "total = 0\nfor n in range(3):\n    total = total + n  # " + "x" * 90 + "\n\nprint(total)"
    defn = {"assignment_id": "t", "title": "Code", "grade": 10, "questions": [
        {"type": "passage", "id": "code", "mono": True, "line_numbers": True, "text": code},
        {"type": "blanks", "q": 1, "mono": True, "prompt": "Fill in the loop.", "text": "x = 0\nwhile x < {1}:\n    x = x + 1\nprint(x)",
         "answers": [{"n": 1, "answer": "5"}]}]}
    layout = S.make_worksheet(defn, tmp_path / "c")
    lines = layout["passages"][0]["lines"]
    assert [n for n, _ in lines] == [1, 2, 3, None, 4, 5]  # a wrapped part gets no number; a blank line counts
    assert lines[2][1].startswith("    total")
    norm = S.normalize(defn)
    L = S.Layout(norm, S.F.choose([code])[0], tmp_path)
    heights = L.blank_heights(norm["questions"][1])
    assert len(heights) == 4 and heights[1] == L.blank_line_h(norm["questions"][1]) > heights[0] == heights[2]


def test_staff_pitches_are_checked_and_drawn(tmp_path):
    staff = {"shape": "staff", "x": 10, "y": 20, "w": 300, "h": 36, "clef": "treble",
             "notes": [{"pitch": "F#4", "x": 60}, {"pitch": "Bb4", "x": 100}, {"pitch": "C4", "x": 140, "filled": False}]}
    defn = {"assignment_id": "t", "title": "Notes", "grade": 5, "questions": [
        {"type": "label", "q": 1, "prompt": "Name the notes.", "diagram": {"width": 330, "height": 90, "shapes": [staff]},
         "labels": [{"n": 1, "box": [40, 0, 40, 18], "answer": "F sharp"}]}]}
    S.make_worksheet(defn, tmp_path / "ok")
    staff["notes"][0]["pitch"] = "H4"
    with pytest.raises(S.WorksheetError, match="pitch"):
        S.make_worksheet(defn, tmp_path / "bad")
    rhythm = {"shape": "staff", "x": 10, "y": 30, "w": 300, "lines": 1, "clef": "none", "time": "4/4", "bars": [160],
              "final_bar": True, "notes": [{"x": 50, "duration": "half", "dot": True}, {"rest": "quarter", "x": 120},
                                           {"x": 200, "duration": "eighth"}, {"x": 220, "duration": "eighth"}]}
    defn["questions"][0]["diagram"]["shapes"] = [rhythm]
    S.make_worksheet(defn, tmp_path / "rhythm")  # a rhythm line needs no pitches
    rhythm["notes"][1]["rest"] = "sixteenth"
    with pytest.raises(S.WorksheetError, match="rest"):
        S.make_worksheet(defn, tmp_path / "bad-rest")


def test_grade_band_wording_and_the_answer_check():
    assert [S.grade_of({"grade_band": b}) for b in ("Spanish 2 (high school)", "AP Biology", "grades 6-8",
                                                    "5th-grade science", "Algebra 1")] == [10, 10, 6, 5, 7]
    check = lambda read, key, verdict: X._answer_check(read, verdict, {"answer": key, "accept": []})  # noqa: E731
    assert check("622", "623", "correct") and check("99", "100", "correct")  # slips aren't rounding
    assert not check("0.17", "1/6", "correct") and not check("0.4995", "0.500", "correct")
    assert not check("3.60", "3.60 mol", "incorrect") and check("4", "t = 4", "incorrect")


def test_work_orders_keep_code_braces(tmp_path):
    defn = {"assignment_id": "t", "title": "Java", "grade": 10, "questions": [
        {"type": "blanks", "q": 1, "mono": True, "prompt": "Fill in.",
         "text": "for (int i = 0; i < {1}; i++) {\n\ttotal += nums[{2}];\n}",
         "answers": [{"n": 1, "answer": "5"}, {"n": 2, "answer": "i"}]}]}
    S.make_worksheet(defn, tmp_path / "a")
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(json.dumps({"assignment_dir": str(tmp_path / "a"), "title": "Java", "pages": [
        {"scan_index": 1, "status": "ok", "student_id": "1234", "page": 1,
         "answers": {"1": {"crop": "crops/scan-001-q1.png", "status": "mark"}}}]}))
    order = P.todo(work)[0].read_text()
    assert "i < [blank 1]; i++) {" in order and "nums[[blank 2]];" in order
    with pytest.raises(S.WorksheetError, match="clef"):
        S.make_worksheet({"assignment_id": "t", "title": "T", "grade": 5, "questions": [
            {"type": "draw", "q": 1, "prompt": "p", "checklist": [{"item": "x"}], "diagram": {"width": 300, "height": 60,
             "shapes": [{"shape": "staff", "x": 0, "y": 10, "w": 300, "clef": "none", "notes": [{"pitch": "G4", "x": 60}]}]}}]},
            tmp_path / "b")


def test_make_warns_when_a_passage_and_its_questions_part():
    defn = {"questions": [{"type": "passage", "id": "b", "title": "Program B"},
                          {"type": "short", "q": 1, "passage": "b"}]}
    assert "Program B ends on page 1" in S._separated_passages(defn, [[(0, (0, 5))], [(1, None)]])[0]
    assert not S._separated_passages(defn, [[(0, (0, 5)), (1, None)]])


def test_answer_check_reads_numbers_but_not_inequalities():
    from paper_loop_core.results import as_number
    from fractions import Fraction
    assert as_number("1 1/2") == Fraction(3, 2) == as_number("1.5")
    assert as_number("x = 17") == 17 and as_number("75%") == Fraction(3, 4) and as_number("$1,200") == 1200
    assert as_number("x >= -4") is None and as_number("3:30") is None and as_number("2x + 3") is None


def test_new_question_types_mark_end_to_end(tmp_path):
    """fill -> prepare -> perfect marks -> check: every box, math part, rubric level, and item scores right."""
    sys.path.insert(0, str(ROOT / "devtools"))
    import fill
    import score as devscore
    assignment = tmp_path / "assignment"
    S.make_worksheet(S.read_json(ROOT / "examples" / "math9-linear-01.json"), assignment)
    students = tmp_path / "students.json"
    students.write_text((ROOT / "devtools" / "students" / "math9-linear-01.json").read_text())
    fill.main(assignment, students, tmp_path / "scan.pdf")
    truth = json.loads((tmp_path / "scan.truth.json").read_text())
    work = tmp_path / "work"
    P.prepare([tmp_path / "scan.pdf"], assignment, work)
    ids = {str(t["scan_index"]): {"digits": t["student_id"], "confidence": 0.95}
           for t in truth["scan_pages"] if not t.get("blank")}
    (work / "ids.json").write_text(json.dumps(ids))
    P.route(work)
    answers = {s["id"]: s["answers"] for s in truth["students"]}
    key = {i["q"]: i for i in S.read_json(assignment / "key.json")["items"]}
    manifest = S.read_json(work / "manifest.json")
    by_scan = {str(p["scan_index"]): p["student_id"] for p in manifest["pages"] if p.get("student_id")}
    for path in P.todo(work):
        q = int(path.stem[1:])
        marks = {}
        for line in path.read_text().splitlines():
            if not line.startswith("- scan "):
                continue
            scan = line.split(":")[0].split()[-1]
            a, kind = answers[by_scan[scan]].get(str(q), {}), key[q]["type"]
            if kind == "math":
                marks[scan] = {"work": "; ".join(a.get("work", [])), "answer": a.get("answer", ""),
                               "answer_verdict": a["expected_answer"], "work_verdict": a["expected_work"],
                               "comment": "Check the first step.", "confidence": 0.9}
            elif kind == "table":
                marks[scan] = {"labels": [{"n": int(n), "transcription": a["boxes"][n], "verdict": v, "confidence": 0.9}
                                          for n, v in a["expected"].items()], "comment": "Square first.", "confidence": 0.9}
            elif kind == "draw":
                marks[scan] = {"description": "a line", "items": [{"n": int(n), "met": v} for n, v in a["expected_items"].items()],
                               "comment": "Check the slope.", "confidence": 0.9}
            elif kind == "choice":
                marks[scan] = {"selected": [c for c in a["circle"] if not c.startswith("~~")][-1:],
                               "crossed_out": [c.strip("~") for c in a["circle"] if c.startswith("~~")], "confidence": 0.9}
        (work / "marks" / f"q{q}.json").write_text(json.dumps({"q": q, "marks": marks}))
    result = X.check(work)
    assert not result["errors"], result["errors"]
    tally = devscore.score(work, truth)["tally"]
    assert tally["routed"] == tally["pages"]
    for name in ("verdict", "box", "math_answer", "math_work", "item"):
        assert tally[f"{name}_ok"] == tally[f"{name}_total"] > 0, (name, devscore.score(work, truth)["misses"])
    assert tally["flagged"] == 0  # the numeric check doesn't trip on inequalities or equivalent forms


def test_an_essay_runs_across_pages_and_is_marked_once(tmp_path):
    sys.path.insert(0, str(ROOT / "devtools"))
    import fill
    defn = {"assignment_id": "essay-t", "title": "Essay", "grade": 11, "questions": [
        {"type": "short", "q": 1, "prompt": "Should schools start later? Argue for a side.", "lines": 50,
         "rubric": [{"criterion": "Claim", "short": "Claim", "levels": ["none", "vague", "clear"]}]},
        {"type": "choice", "q": 2, "prompt": "Pick one.", "answer": "A",
         "options": [{"letter": "A", "text": "yes"}, {"letter": "B", "text": "no"}]}]}
    assignment = tmp_path / "assignment"
    layout = S.make_worksheet(defn, assignment)
    parts = [[(b["q"], b.get("part"), b["points"]) for b in p["boxes"]] for p in layout["pages"]]
    assert parts[0] == [(1, 1, 2)] and parts[1] == [(1, 2, 0)] and (1, 3, 0) in parts[2]
    long = "Schools should start later because teenagers need more sleep to learn well in class. " * 6
    students = {"students": [
        {"id": "1111", "answers": {"1": {"text": long, "more": [long]}, "2": {"circle": ["A"]}}},
        {"id": "2222", "answers": {"1": {"text": long}, "2": {"circle": ["B"]}}},  # stops on page 1
        {"id": "3333", "answers": {"1": {"more": [long]}, "2": {"circle": ["A"]}}},  # starts on page 2
        {"id": "4444", "answers": {"2": {"circle": ["A"]}}},
        {"id": "5555", "answers": {"1": {"text": long, "more": [long]}, "2": {"circle": ["A"]}}},  # page 1 unrouted
        {"id": "6666", "answers": {"1": {"text": long}}}]}  # never reached page 3
    (tmp_path / "students.json").write_text(json.dumps(students))
    fill.main(assignment, tmp_path / "students.json", tmp_path / "scan.pdf")
    truth = json.loads((tmp_path / "scan.truth.json").read_text())
    work = tmp_path / "work"
    P.prepare([tmp_path / "scan.pdf"], assignment, work)
    (work / "ids.json").write_text(json.dumps({str(t["scan_index"]): {"digits": t["student_id"], "confidence": 0.95}
                                               for t in truth["scan_pages"] if not t.get("blank")
                                               and (t["student_id"], t["page"]) != ("5555", 1)}))
    P.route(work)
    manifest = S.read_json(work / "manifest.json")
    first = {p["student_id"]: p["scan_index"] for p in manifest["pages"] if p.get("page") == 1}
    # 4444 skipped the essay and 6666 page 3; 2222 wrote a short essay and 3333 started it on page 2
    assert sorted((p["student_id"], p["page"]) for p in P.blank_pages(manifest)) == [("4444", 1), ("6666", 3)]
    first["5555"] = next(p["scan_index"] for p in manifest["pages"] if p.get("student_id") == "5555" and p["page"] == 2)
    order = (work / "todo" / "q1.md").read_text() if P.todo(work) else ""
    listed = [line for line in order.splitlines() if line.startswith("- scan ")]
    assert len(listed) == 5 and "runs across 3 pages" in order  # 4444 left it blank: settled
    assert sum(line.count("then scan") == 2 for line in listed) == 4
    assert "page 1 of the answer isn't in the scan" in next(l for l in listed if f"scan {first['5555']}:" in l)
    marks = {str(first[sid]): {"transcription": "...", "criteria": [{"n": 1, "level": 2}], "comment": "Clear claim.",
                               "confidence": 0.9} for sid in ("1111", "2222", "3333", "5555", "6666")}
    (work / "marks" / "q1.json").write_text(json.dumps({"q": 1, "marks": marks}))
    result = X.check(work)
    assert not result["errors"], result["errors"]
    essay = [b for p in result["pages"] for b in p["boxes"] if b["q"] == 1]
    assert len(essay) == 6 and sorted(b["verdict"] for b in essay) == ["blank"] + ["correct"] * 5
    assert all(b["points_possible"] == 2 for b in essay)  # 5555's page 2 carries the essay's points


def test_answer_written_beside_the_box_gets_looked_at(water, tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    root, _, _ = water
    layout = S.read_json(root / "assignment" / "layout.json")
    page = Image.fromarray(L.template(root / "assignment", 1))
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(36)
    for digit, rect in zip("2093", layout["pages"][0]["id_boxes"]):
        draw.text(S.pt_to_px(rect[0] + 7, rect[3] - 6), digit, fill=30, font=font)
    q3 = next(b for b in layout["pages"][0]["boxes"] if b["q"] == 3)
    x, y = S.pt_to_px(q3["rect"][2] - 48, q3["rect"][3] + 8)  # past the end of the prompt, just above the empty box
    draw.text((x, y - 30), "drops", fill=30, font=font, stroke_width=2, stroke_fill=30)
    page.save(tmp_path / "scan.pdf", resolution=200)
    manifest = P.prepare([tmp_path / "scan.pdf"], root / "assignment", tmp_path / "work")
    answers = manifest["pages"][0]["answers"]
    assert answers["3"]["status"] == "mark" and answers["3"].get("outside_crop")
    assert all(not a.get("outside_crop") for q, a in answers.items() if q != "3")


def test_phone_photos_read_like_scans(water, tmp_path):
    """Tilt, a shadow, a warm cast, a dark table around the page, JPEG: same reads as the flatbed scan."""
    sys.path.insert(0, str(ROOT / "devtools"))
    import photo
    root, pdf, truth = water
    flat = P.prepare([pdf], root / "assignment", tmp_path / "flat")
    files = []
    for i, page in enumerate(L.load_pages(pdf), start=1):
        files.append(tmp_path / f"IMG_{i}.jpg")
        photo.photo(page, tilt=4 + 3 * i, shadow=0.15 + 0.1 * i, seed=i).save(files[-1], quality=80)
    shot = P.prepare(files, root / "assignment", tmp_path / "photos")
    for f, s in zip(flat["pages"], shot["pages"]):
        assert (f["status"], f.get("page")) == (s["status"], s.get("page")), (s["scan_index"], s["reason"])
        assert {q: (a["status"], a["read"]) for q, a in f["answers"].items()} == \
               {q: (a["status"], a["read"]) for q, a in s["answers"].items()}
    assert any(p["status"] == "blank" for p in shot["pages"])  # the empty sheet, on a dark table


def test_rubric_doubt_and_math_key_doubt_reach_the_teacher():
    from paper_loop_core import results as R
    box = {"q": 2, "type": "short", "points": 4}
    item = {"rubric": [{"n": 1, "criterion": "Claim", "short": "Claim", "levels": ["a", "b", "c"], "max": 2},
                       {"n": 2, "criterion": "Evidence", "short": "Evidence", "levels": ["a", "b", "c"], "max": 2}]}
    mark = {"transcription": "t", "criteria": [{"n": 1, "level": 2}, {"n": 2, "level": 1, "alt": 2}],
            "comment": "c", "confidence": 0.9}
    r = R._rubric(box, item, mark, "crop.png")
    assert r["points_awarded"] == 3 and r["verdict"] == "partial" and r["flagged"]
    assert any("Evidence could be 2 instead of 1" in f for f in r["flag_reasons"])
    assert R._validate("short", {**mark, "criteria": [{"n": 1, "level": 2, "alt": 5}, {"n": 2, "level": 1}]},
                       "q2", item)  # an alternative past the top level is an error
    m = R._math({"q": 1, "type": "math", "points": 2}, {"answer": "7", "accept": [], "answer_points": 1, "work_points": 1},
                {"work": "w", "answer": "7", "answer_verdict": "correct", "work_verdict": "correct", "comment": "c",
                 "confidence": 0.95, "key_ambiguous": True, "note": "the key doesn't say whether 7.0 counts"}, "crop.png")
    assert m["flagged"] and m["note"]
