"""Lesson plans, slides, go-over decks, and answer keys (the plugin's `lesson` and `goover` commands)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import deck as DK  # noqa: E402
from paper_loop_core import goover as G  # noqa: E402
from paper_loop_core import lesson as LS  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402
from paper_loop_core import slides as K  # noqa: E402
from paper_loop_core import walk as WK  # noqa: E402

pptx = pytest.importorskip("pptx")
LESSONS = sorted((ROOT / "examples").glob("*-lesson.json"))
BLOCKER = (Path(__file__).parent / "test_plugin.py").read_text().split('BLOCKER = """')[1].split('"""')[0]


def build_example(path: Path, tmp: Path) -> tuple[dict, Path]:
    """The lesson's worksheet made beside a copy of the lesson file, then the lesson built."""
    lesson = json.loads(path.read_text())
    if lesson.get("worksheet"):
        S.make_worksheet(S.read_json(ROOT / "examples" / f"{lesson['worksheet']}.json"), tmp / lesson["worksheet"],
                         base=ROOT / "examples")
    shutil.copy(path, tmp / path.name)
    return LS.build(tmp / path.name, tmp / "out"), tmp / "out"


def texts(prs) -> list[str]:
    return [p.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame
            for p in shape.text_frame.paragraphs]


@pytest.mark.parametrize("path", LESSONS, ids=lambda p: p.stem)
def test_every_example_lesson_builds_clean(path, tmp_path):
    report, out = build_example(path, tmp_path)
    assert report["warnings"] == []
    prs = pptx.Presentation(str(out / "slides.pptx"))
    assert len(prs.slides) == report["slides"]
    assert prs.slide_width == int(K.W * K.EMU) and prs.slide_height == int(K.H * K.EMU)
    for slide in prs.slides:  # every slide titled, for outlines and screen readers
        assert slide.shapes.title is not None and slide.shapes.title.text.strip()
    lesson = json.loads(path.read_text())
    phases = [p["phase"] for p in lesson["sequence"]]
    assert [r for r in report["ranges"] if r] == sorted(r for r in report["ranges"] if r)
    assert len(report["ranges"]) == len(phases)
    go = pptx.Presentation(str(out / "go-over.pptx"))
    answers = [s for s in go.slides if any(sh.has_text_frame and sh.text_frame.text == "Answer" for sh in s.shapes)]
    assert answers and all(s.has_notes_slide and "Answer:" in s.notes_slide.notes_text_frame.text for s in answers)
    with zipfile.ZipFile(out / "lesson-plan.docx") as z:
        for name in z.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                ElementTree.fromstring(z.read(name))  # well-formed
        body = z.read("word/document.xml").decode()
    for heading in ("Learning objectives", "Lesson sequence", "Worksheet answers"):
        assert heading in body
    assert (out / "answer-key.pdf").exists() and (out / "slides.pdf").exists()


def test_lesson_runs_in_the_sandbox_without_the_cli_packages(tmp_path):
    path = ROOT / "examples" / "math6-ratios-lesson.json"
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "math6-ratios-01")
    shutil.copy(path, tmp_path / path.name)
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "lesson",
                          str(tmp_path / path.name), "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr + run.stdout
    assert "Slides by phase: Warm-up 4-5" in run.stdout and "Check:" not in run.stdout


def test_answers_are_written_where_the_key_says(tmp_path):
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "ws")
    ws = WK.Worksheet(tmp_path / "ws")
    table = ws.marks(1)
    assert [m.text for m in table] == ["4", "12", "10", "15"]
    region = ws.region(1)
    assert all(region[0] <= m.rect[0] and m.rect[2] <= region[2] and region[1] <= m.rect[1] and m.rect[3] <= region[3]
               for m in table)
    circle = ws.marks(4)[0]
    letter = next(o for o in ws.boxes[4]["options"] if o["letter"] == "B")["letter_at"]
    assert circle.kind == "circle"
    assert abs((circle.rect[0] + circle.rect[2]) / 2 - letter[0]) < 0.01
    assert ws.answer_text(2) == "$2.50"
    region2 = ws.region(2)  # a math question's picture is its prompt, so its answer box is left off it
    assert region2[1] > ws.boxes[2]["answer_rect"][3]


def test_a_drawn_answer_lands_on_the_axes(tmp_path):
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "ws")
    ws = WK.Worksheet(tmp_path / "ws")
    shapes = ws.answer_drawing(3, [{"shape": "plot", "points": [[0, 0], [10, 12]], "line": True}])
    dots = [s for s in shapes if s["shape"] == "circle"]
    axes = next(s for s in ws.question_def(3)["diagram"]["shapes"] if s["shape"] == "axes")
    assert (dots[0]["x"], dots[0]["y"]) == (axes["x"], axes["y"])
    assert (dots[1]["x"], dots[1]["y"]) == (axes["x"] + axes["w"], axes["y"] + axes["h"])
    path = tmp_path / "q3.png"
    ws.crop(3, path, shapes, "2453A6")
    from PIL import Image
    import numpy as np
    img = np.asarray(Image.open(path).convert("RGB")).astype(int)
    blue = (img[..., 2] - img[..., 0] > 80).sum()
    assert blue > 200  # the line and dots, in color on the gray question
    with pytest.raises(ValueError, match="number line"):
        ws.answer_drawing(3, [{"shape": "mark", "at": [1]}])
    with pytest.raises(ValueError, match="no diagram"):
        ws.answer_drawing(2, [{"shape": "plot", "points": [[1, 1]]}])


@pytest.mark.parametrize("change, message", [
    (lambda L: L.pop("title"), 'missing "title"'),
    (lambda L: L["sequence"][0]["slides"].append({"type": "chart", "title": "x"}), '"type" must be one of'),
    (lambda L: next(s for s in L["sequence"][2]["slides"] if s.get("choices")).update(answer="E"),
     "letter of the right one"),
    (lambda L: L["walkthrough"].append({"q": 9}), "walkthrough for question 9"),
    (lambda L: L["sequence"][1]["slides"].append({"type": "points", "title": "x"}), 'needs "points"'),
    (lambda L: L.update(differentiation={"ell": ["x"]}), 'use "support", "extension", "language", or'),
])
def test_lesson_errors_say_what_to_fix(change, message, tmp_path):
    lesson = json.loads((ROOT / "examples" / "math6-ratios-lesson.json").read_text())
    change(lesson)
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "math6-ratios-01")
    (tmp_path / "l.json").write_text(json.dumps(lesson))
    with pytest.raises(DK.LessonError, match=message):
        LS.build(tmp_path / "l.json", tmp_path / "out")


def test_timing_and_word_count_warnings(tmp_path):
    lesson = json.loads((ROOT / "examples" / "math6-ratios-lesson.json").read_text())
    lesson["minutes"] = 45
    lesson["sequence"][1]["slides"][1]["points"] = ["word " * 40, "more words " * 20]
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "math6-ratios-01")
    (tmp_path / "l.json").write_text(json.dumps(lesson))
    report = LS.build(tmp_path / "l.json", tmp_path / "out")
    assert any("adds up to 47 minutes, but the lesson is 45" in w for w in report["warnings"])
    assert any("A ratio is a recipe" in w and "words" in w for w in report["warnings"])


def test_ratios_stay_on_one_line_and_code_keeps_its_indent():
    m = K.Measure()
    para = K.Para(K.runs("so 2 : 3 becomes 4 : 6 and 3 × 4 = 12"))
    lines = m.wrap(para, 120, 20)
    flat = ["".join(p for p, _ in line) for line in lines]
    assert any("2\u00a0:\u00a03" in f for f in flat) and any("3\u00a0×\u00a04\u00a0=\u00a012" in f for f in flat)
    assert not any(f.lstrip()[:1] in (":", "×", "=") or f.rstrip()[-1:] in (":", "×", "=") for f in flat)
    code = m.wrap(K.Para([K.Run("    total = total + n")]), 600, 20, mono=True)
    assert code[0][0][0] == "    "


def test_subject_colors():
    assert K.theme_for("Computer Science") != K.theme_for("Science")
    assert K.theme_for("English language arts") != K.theme_for("World Languages")
    assert K.theme_for("AP Biology") == K.theme_for("Science")


def fake_results(ws: WK.Worksheet) -> dict:
    """Ten students: Q1 (table) mostly wrong in box 2 with "8" (four times) and "7" (once); Q4 (choice) half C."""
    pages = []
    for k in range(10):
        sid = f"{1000 + k}"
        q1_wrong = k < 6
        details = [{"n": 1, "read": "4", "verdict": "correct", "answer": "4"},
                   {"n": 2, "read": ("8" if k < 4 else "7" if k == 4 else "9") if q1_wrong else "12",
                    "verdict": "incorrect" if q1_wrong else "correct", "answer": "12"},
                   {"n": 3, "read": "10", "verdict": "correct", "answer": "10"},
                   {"n": 4, "read": "15", "verdict": "correct", "answer": "15"}]
        pick = "C" if k < 5 else "B"
        boxes = [
            {"q": 1, "type": "table", "verdict": "partial" if q1_wrong else "correct", "details": details},
            {"q": 2, "type": "math", "verdict": "correct", "details": [{"part": "answer", "read": "$2.50",
                                                                          "verdict": "correct"}]},
            {"q": 3, "type": "draw", "verdict": "correct", "details": []},
            {"q": 4, "type": "choice", "verdict": "correct" if pick == "B" else "incorrect",
             "details": [{"selected": pick, "answer": "B"}]},
        ]
        pages.append({"scan_index": k + 1, "student_id": sid, "page": 1, "boxes": boxes})
    return {"pages": pages}


def test_go_over_puts_the_most_missed_first_and_names_no_one(tmp_path):
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "math6-ratios-01")
    ws = WK.Worksheet(tmp_path / "math6-ratios-01")
    work = tmp_path / "work"
    work.mkdir()
    S.write_json(work / "manifest.json", {"assignment_dir": str(tmp_path / "math6-ratios-01"), "pages": []})
    S.write_json(work / "results.json", fake_results(ws))
    S.write_json(work / "goover.json", {"questions": [{"q": 1, "saw": "Many doubled the 4-batch row wrong."}]})
    shutil.copy(ROOT / "examples" / "math6-ratios-lesson.json", tmp_path / "lesson.json")
    report = G.build(work, tmp_path / "lesson.json")
    assert report["go_over"] == [1, 4] and report["got_it"] == [2, 3]
    todo = (work / "out" / "go-over-todo.md").read_text()
    assert "## Question 4 (50% full credit)" in todo and "Letters chosen: B 5, C 5" in todo
    assert any("no \"saw\" for question 4" in w for w in report["warnings"])
    prs = pptx.Presentation(str(work / "out" / "go-over.pptx"))
    words = " ".join(texts(prs))
    assert '4 wrote "8" in box 2' in words  # four students: shown
    assert '"7"' not in words  # one student: never on the projector
    assert not any(f"{1000 + k}" in words for k in range(10))
    assert "Many doubled the 4-batch row wrong." in words
    titles = [s.shapes.title.text for s in prs.slides]
    assert titles[:3] == ["Going over: Smoothie Stand Ratios", "How it went", "You've got these"]
    assert titles.index("Question 1") < titles.index("Question 4")
    charts = [sh for s in prs.slides for sh in s.shapes if sh.has_chart]
    assert len(charts) == 3  # the overview, and how the class answered Q1 and Q4
    picks = next(c.chart for c in charts if list(c.chart.plots[0].categories) == ["D", "C", "B", "A"])  # bottom-up
    assert list(picks.plots[0].series[0].values) == [0, 5, 5, 0]
    assert G.build(work, tmp_path / "lesson.json", most=1)["go_over"] == [1]


def test_go_over_needs_marks(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(DK.LessonError, match="no results.json"):
        G.build(work)


def test_a_lesson_without_a_worksheet(tmp_path):
    lesson = json.loads((ROOT / "examples" / "math6-ratios-lesson.json").read_text())
    lesson.pop("worksheet")
    lesson.pop("walkthrough")
    lesson["sequence"] = [p for p in lesson["sequence"] if not p.get("worksheet") and not p.get("walkthrough")]
    lesson["minutes"] = sum(p["minutes"] for p in lesson["sequence"])
    (tmp_path / "l.json").write_text(json.dumps(lesson))
    report = LS.build(tmp_path / "l.json", tmp_path / "out")
    assert report["warnings"] == [] and "go_over" not in report
    assert not (tmp_path / "out" / "answer-key.pdf").exists()
    with zipfile.ZipFile(tmp_path / "out" / "lesson-plan.docx") as z:
        assert "Worksheet answers" not in z.read("word/document.xml").decode()


def test_the_lesson_command_explains_a_bad_file(tmp_path):
    (tmp_path / "l.json").write_text(json.dumps({"title": "x", "grade_band": "5th grade", "minutes": 30,
                                                 "objectives": ["y"], "sequence": [{"phase": "Warm-up",
                                                 "minutes": 30, "slides": [{"type": "points"}]}]}))
    run = subprocess.run([sys.executable, str(SCRIPTS / "paper_loop.py"), "lesson", str(tmp_path / "l.json"), "--out",
                          str(tmp_path / "out")], capture_output=True, text=True)
    assert run.returncode == 1
    assert 'sequence 1 (Warm-up), slide 1: missing "title"' in run.stdout


def test_an_extended_plot_runs_edge_to_edge_of_the_axes(tmp_path):
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "ws")
    ws = WK.Worksheet(tmp_path / "ws")
    shapes = ws.answer_drawing(3, [{"shape": "plot", "points": [[2, 3], [6, 9]], "extend": True}])
    line = next(s for s in shapes if s["shape"] == "line")
    axes = next(s for s in ws.question_def(3)["diagram"]["shapes"] if s["shape"] == "axes")
    (ax, ay), (bx, by) = line["points"]
    assert (ax, ay) == (axes["x"], axes["y"])  # through (0, 0)
    assert abs(by - (axes["y"] + axes["h"])) < 1e-6  # out to y = 12, at x = 8
    assert abs(bx - (axes["x"] + 8 / 10 * axes["w"])) < 1e-6


def lesson_with(tmp_path, change) -> tuple[dict, Path]:
    lesson = json.loads((ROOT / "examples" / "math6-ratios-lesson.json").read_text())
    change(lesson)
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "math6-ratios-01")
    (tmp_path / "l.json").write_text(json.dumps(lesson))
    return LS.build(tmp_path / "l.json", tmp_path / "out"), tmp_path / "out"


def test_a_slide_that_gives_away_a_worksheet_answer_is_flagged(tmp_path):
    def leak(L):
        L["sequence"][1]["slides"][0]["words"] = [{"term": "unit rate", "meaning": "How much for one.",
                                                   "example": "$2.50 per smoothie"}]
    report, _ = lesson_with(tmp_path, leak)
    assert any("shows question 2's answer" in w and "$2.50" in w for w in report["warnings"])


def test_an_exit_ticket_keeps_its_answer_in_the_notes(tmp_path):
    report, out = lesson_with(tmp_path, lambda L: None)
    prs = pptx.Presentation(str(out / "slides.pptx"))
    last = prs.slides[len(prs.slides) - 1]
    assert last.shapes.title.text == "Exit ticket"
    assert "$0.50" in last.notes_slide.notes_text_frame.text
    assert not any(sh.has_text_frame and "$0.50" in sh.text_frame.text for sh in last.shapes)


def test_powerpoint_wraps_where_the_pdf_does(tmp_path):
    _, out = lesson_with(tmp_path, lambda L: None)
    prs = pptx.Presentation(str(out / "slides.pptx"))
    for shape in prs.slides[1].shapes:
        if shape.has_text_frame and shape.text_frame.text:
            assert abs(shape.text_frame.margin_right - shape.width * (1 - K.SLACK)) <= 2


def test_worksheet_text_keeps_its_stars_and_the_plan_survives_control_characters(tmp_path):
    def change(L):
        L["notes"] = "Pasted from Word:\vsecond line\x07."
    report, out = lesson_with(tmp_path, change)
    with zipfile.ZipFile(out / "lesson-plan.docx") as z:
        xml = z.read("word/document.xml").decode()
    ElementTree.fromstring(xml)
    assert "<w:br/>" in xml and "\x07" not in xml
    m = K.Measure()
    assert "".join(r.text for r in K.runs("2 ** 3", markup=False)) == "2 ** 3"


def test_targets_speak_for_the_student():
    assert LS._target("Students will be able to explain in their own words why they agree") == \
        "I can explain in my own words why I agree"


def test_an_older_worksheet_still_gets_its_reading_slide(tmp_path):
    S.make_worksheet(S.read_json(ROOT / "examples" / "cs10-loops-01.json"), tmp_path / "cs10-loops-01")
    layout = json.loads((tmp_path / "cs10-loops-01" / "layout.json").read_text())
    for page in layout["pages"]:
        page.pop("passages", None)  # as a worksheet made before passages were placed
    (tmp_path / "cs10-loops-01" / "layout.json").write_text(json.dumps(layout))
    shutil.copy(ROOT / "examples" / "cs10-loops-lesson.json", tmp_path / "l.json")
    LS.build(tmp_path / "l.json", tmp_path / "out")
    prs = pptx.Presentation(str(tmp_path / "out" / "go-over.pptx"))
    assert "Program A" in [s.shapes.title.text for s in prs.slides]


def test_a_phone_photo_stands_up(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (600, 300), "white")
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 degrees to display
    img.save(tmp_path / "photo.jpg", exif=exif)
    lesson = {"title": "Photo", "grade_band": "5th grade", "minutes": 10, "objectives": ["See a photo."],
              "sequence": [{"phase": "Look", "minutes": 10, "slides": [{"type": "points", "title": "A photo",
                                                                        "image": "photo.jpg"}]}]}
    (tmp_path / "l.json").write_text(json.dumps(lesson))
    LS.build(tmp_path / "l.json", tmp_path / "out")
    prs = pptx.Presentation(str(tmp_path / "out" / "slides.pptx"))
    pic = next(sh for s in prs.slides for sh in s.shapes if sh.shape_type == 13)
    assert pic.height > pic.width


def test_the_next_lesson_opens_with_the_last_worksheet_gone_over(tmp_path):
    S.make_worksheet(S.read_json(ROOT / "examples" / "math6-ratios-01.json"), tmp_path / "math6-ratios-01")
    ws = WK.Worksheet(tmp_path / "math6-ratios-01")
    work = tmp_path / "math6-ratios-01" / "marking-2026-10-27"
    work.mkdir()
    S.write_json(work / "manifest.json", {"assignment_dir": str(tmp_path / "math6-ratios-01"), "pages": []})
    S.write_json(work / "results.json", fake_results(ws))
    S.write_json(work / "goover.json", {"questions": [{"q": 1, "saw": "Many doubled the 4-batch row wrong."}]})
    lesson = S.read_json(ROOT / "examples" / "math6-ratios-lesson.json")
    lesson["sequence"].insert(0, {"phase": "Yesterday's worksheet", "minutes": 8, "most": 1,
                                  "review": "math6-ratios-01/marking-2026-10-27"})
    lesson["minutes"] += 8
    S.write_json(tmp_path / "day2.json", lesson)
    report = LS.build(tmp_path / "day2.json", tmp_path / "day2")
    prs = pptx.Presentation(str(tmp_path / "day2" / "slides.pptx"))
    titles = [s.shapes.title.text for s in prs.slides]
    start = titles.index("How “Smoothie Stand Ratios” went")
    assert titles[start:start + 4] == ["How “Smoothie Stand Ratios” went", "Question 1", "Question 1", "Fix it"]
    assert report["ranges"][0] == (start + 1, start + 4)
    assert "Many doubled the 4-batch row wrong." in " ".join(texts(prs))
    assert "Hand back the marked copies" in prs.slides[start].notes_slide.notes_text_frame.text
    plan = zipfile.ZipFile(tmp_path / "day2" / "lesson-plan.docx").read("word/document.xml").decode()
    assert "Bring the marked copies of" in plan
    lesson["sequence"][0]["review_skip"] = ["fix_it"]  # the marked copies aren't back yet
    S.write_json(tmp_path / "day2b.json", lesson)
    LS.build(tmp_path / "day2b.json", tmp_path / "day2b")
    titles = [s.shapes.title.text for s in pptx.Presentation(str(tmp_path / "day2b" / "slides.pptx")).slides]
    assert "Fix it" not in titles and "How “Smoothie Stand Ratios” went" in titles
    lesson["sequence"][0]["review_skip"] = ["slides"]
    S.write_json(tmp_path / "bad.json", lesson)
    with pytest.raises(DK.LessonError, match="review_skip"):
        LS.build(tmp_path / "bad.json", tmp_path / "bad")
    lesson["sequence"][0]["review_skip"] = []
    lesson["sequence"][0]["review"] = "nowhere"
    S.write_json(tmp_path / "bad.json", lesson)
    with pytest.raises(DK.LessonError, match="has no results.json"):
        LS.build(tmp_path / "bad.json", tmp_path / "bad")


def test_go_over_doesnt_compare_letters_across_copies_with_different_choices(tmp_path):
    from paper_loop_core import goover as G
    defn = {"assignment_id": "mix-01", "title": "Mix", "grade": 6, "variants": {"count": 4},
            "questions": [
                {"type": "choice", "q": 1, "prompt": "Which is even?", "answer": "A",
                 "options": [{"letter": "A", "text": "4", "why": "Even."}, {"letter": "B", "text": "5", "why": "Odd."}],
                 "pool": [{"prompt": "Which is odd?", "options": [{"letter": "A", "text": "7", "why": "Odd."},
                                                                  {"letter": "B", "text": "8", "why": "Even."}]}]},
                {"type": "choice", "q": 2, "prompt": "Which is bigger?", "answer": "A", "shuffle_choices": True,
                 "options": [{"letter": "A", "text": "9", "why": "Yes."}, {"letter": "B", "text": "3", "why": "No."}]}]}
    S.make_worksheet(defn, tmp_path / "mix")
    ws = WK.Worksheet(tmp_path / "mix")
    assert G._mixed_choices(ws, 1) and not G._mixed_choices(ws, 2)  # another item vs. just a new order
