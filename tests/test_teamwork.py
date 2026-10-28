"""Group work where students teach each other: role cards, tasks, and mixed-skill groups (the plugin's
`teamwork` and `groups`)."""

from __future__ import annotations

import subprocess
import zipfile
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import sheet as S  # noqa: E402
from paper_loop_core import teamwork as TW  # noqa: E402

EXAMPLES = sorted((ROOT / "examples").glob("*-teamwork.json"))
REFERENCE = ROOT / "plugin" / "skills" / "paper-loop" / "references" / "examples"
BLOCKER = (Path(__file__).parent / "test_plugin.py").read_text().split('BLOCKER = """')[1].split('"""')[0]


def text_of(pdf: Path) -> list[str]:
    doc = pdfium.PdfDocument(str(pdf))
    return [doc[i].get_textpage().get_text_range().replace("\r\n", " ") for i in range(len(doc))]


# --- The examples -----------------------------------------------------------------------------

def test_every_structure_has_an_example():
    assert {S.read_json(p)["structure"] for p in EXAMPLES} == set(TW.STRUCTURES)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_builds_clean_with_its_own_worksheet(path, tmp_path):
    report = TW.build(path, tmp_path)
    assert report["warnings"] == []
    doc = pdfium.PdfDocument(str(report["pdf"]))
    assert report["pages"][-1][2] == len(doc)
    assert all(abs(doc[i].get_size()[0] - 612) < 0.01 for i in range(len(doc)))
    assert (REFERENCE / path.name).read_text() == path.read_text()  # the plugin's copy is the same file
    worksheet = ROOT / "examples" / f"{S.read_json(path)['worksheet']}.json"
    assert (REFERENCE / worksheet.name).read_text() == worksheet.read_text()
    layout = S.make_worksheet(S.read_json(worksheet), tmp_path / "ws", base=worksheet.parent)
    assert layout["base_pages"] <= (1 if "sci" in worksheet.stem else 2)  # the new exit sheets fit one page


def test_a_lab_prints_jobs_that_rotate_a_task_and_tokens(tmp_path):
    report = TW.build(ROOT / "examples" / "sci7-selection-teamwork.json", tmp_path)
    assert [name for name, *_ in report["pages"]] == ["Teacher's page", "Role cards", "Group task", "Tokens"]
    pages = text_of(report["pdf"])
    assert "Pass the role cards one seat to the left each round" in pages[0]
    assert all(role in "".join(pages[1:3]) for role in ("Facilitator", "Recorder", "Skeptic", "Reporter"))
    assert "Materials" not in "".join(pages[1:3])  # groups of 4: four jobs
    assert "How do you know?" in "".join(pages[1:3])


def test_the_teacher_page_gives_page_numbers_materials_and_honest_evidence(tmp_path):
    report = TW.build(ROOT / "examples" / "sci7-predators-teamwork.json", tmp_path)
    teacher = text_of(report["pdf"])[0]
    assert "This page is for you: print it once." in teacher
    assert "role cards (pages 2-3)" in teacher and "task card (page 4)" in teacher and "tokens (page 5)" in teacher
    assert "plus about 10 for the exit sheet" in teacher
    assert "Each group needs: one sheet of plain paper" in teacher
    assert "every 2 rounds" in teacher and "+0.32" in teacher
    task = text_of(report["pdf"])[3]
    assert all(str(r) in task for r in range(1, 11)) and "after every 2 rounds" in task  # ten rounds, wrapped to fit
    jigsaw = text_of(TW.build(ROOT / "examples" / "sci9-exoplanets-teamwork.json", tmp_path / "j")["pdf"])
    assert "results are mixed" in jigsaw[0] and "Check each expert's box" in jigsaw[0]
    assert all("Teacher checked" in p for p in jigsaw if "Teach box" in p)
    assert "little rigorous research" in text_of(TW.build(ROOT / "examples" / "chem10-moles-teamwork.json",
                                                          tmp_path / "h")["pdf"])[0]


def test_an_author_can_word_the_role_cards(tmp_path):
    data = S.read_json(ROOT / "examples" / "ela4-garden-teamwork.json")
    data["grade"] = 3
    data["roles"] = [{"name": "Sum It Up", "jobs": ["Tell the big idea."], "say": ["It's mostly about __."]},
                     {"name": "Ask", "jobs": ["Ask a question."]},
                     {"name": "Fix It", "jobs": ["Find a hard word."]},
                     {"name": "Guess", "jobs": ["Guess what's next."]}]
    S.write_json(tmp_path / "r.json", data)
    pages = text_of(TW.build(tmp_path / "r.json", tmp_path / "out")["pdf"])
    assert "Sum It Up: your job" in "".join(pages) and "Predictor" not in pages[-1]
    assert "Last stop: Sum It Up, Ask, Fix It." in pages[-1]
    data["roles"] = data["roles"][:3]
    with pytest.raises(TW.TeamworkError, match="replaces the 4 cards"):
        TW.normalize(data)


def test_jigsaw_parts_take_quotes_key_words_and_checked_credits(tmp_path):
    data = S.read_json(ROOT / "examples" / "sci9-exoplanets-teamwork.json")
    data["class_size"] = 31
    part = data["parts"][0]
    part.pop("source")
    part["cite"] = {"title": "Transit photometry", "url": "https://en.wikipedia.org/w/index.php?oldid=1",
                    "license": "CC BY-SA 4.0", "changes": "shortened"}
    part["quote"] = "The planet blocks a tiny bit of the star's light."
    part["quote_source"] = "a made-up quote for this test"
    part["words"] = [{"word": "transit", "means": "passing in front"}]
    S.write_json(tmp_path / "j.json", data)
    report = TW.build(tmp_path / "j.json", tmp_path / "out")
    pages = text_of(report["pdf"])
    sheet = next(p for p in pages if p.startswith("Expert A: "))
    assert "“The planet blocks a tiny bit" in sheet and "Key words: transit: passing in front" in sheet
    assert "CC BY-SA 4.0" in sheet and "Transit photometry" in sheet
    assert "For 31 students: 7 groups (3 of 5, 4 of 4), two students sharing a letter in the bigger ones." in pages[0]
    assert "The transit method" in pages[1]  # the tent names the expert's topic, for the home group
    notes = next(p for p in pages if p.startswith("Home group notes"))
    assert "How the parts connect" in notes and "your own words" in notes
    part["cite"]["url"] = "https://www.commonlit.org/en/texts/x"
    S.write_json(tmp_path / "j.json", data)
    with pytest.raises(TW.TeamworkError, match="CommonLit"):
        TW.build(tmp_path / "j.json", tmp_path / "out")
    part.pop("cite")
    part["source"] = "Adapted from a ReadWorks passage"
    with pytest.raises(TW.TeamworkError, match="ReadWorks"):
        TW.normalize(data)
    part["source"] = "Written for Paper Loop."
    part["text"] = "word " * 400
    S.write_json(tmp_path / "long.json", data)
    warnings = TW.build(tmp_path / "long.json", tmp_path / "long")["warnings"]
    assert any("part A has 4" in w for w in warnings) and any("no room for the sketch box" in w for w in warnings)


def test_missing_worksheets_and_hard_readings_are_flagged(tmp_path):
    data = S.read_json(ROOT / "examples" / "ela4-garden-teamwork.json")
    data["worksheet"] = "ela4-nothing-01"
    data["parts"][0]["text"] = ("Photosynthetic organisms synthesize carbohydrates utilizing electromagnetic radiation, "
                                "atmospheric carbon dioxide, and environmental water, simultaneously liberating "
                                "molecular oxygen through complicated biochemical transformations.") * 3
    S.write_json(tmp_path / "hard.json", data)
    warnings = TW.build(tmp_path / "hard.json", tmp_path / "out")["warnings"]
    assert any("no worksheet 'ela4-nothing-01'" in w for w in warnings)
    assert any("Flesch-Kincaid" in w for w in warnings)


def test_labs_print_their_data_and_boards(tmp_path):
    report = TW.build(ROOT / "examples" / "sci9-plates-teamwork.json", tmp_path)
    names = [name for name, *_ in report["pages"]]
    assert names == ["Teacher's page", "Role cards", "Group task", "Data", "Board"]
    pages = text_of(report["pdf"])
    assert "558" in pages[4] and "Kauai" in pages[4]  # real USGS values, in full
    assert "distance east of the trench (km)" in pages[5] and "600" in pages[5]
    assert "Per group, print the role cards (pages 2-3), the task card (page 4), the data (page 5) and the board (page 6)." in pages[0]
    for name in ("math4-fractions", "math3-area", "sci7-greenhouse"):
        out = TW.build(ROOT / "examples" / f"{name}-teamwork.json", tmp_path / name)
        assert "Board" in [n for n, *_ in out["pages"]] and out["warnings"] == []


@pytest.mark.parametrize("board, message", [
    ({"kind": "maze"}, "one of grid"),
    ({"kind": "grid", "cols": 10}, "needs rows"),
    ({"kind": "grid", "cols": 100, "rows": 5}, "2-40 columns"),
    ({"kind": "number_line", "min": 0.5, "max": 2, "parts": 4}, "whole number"),
    ({"kind": "rows", "rows": ["only one"]}, "2-12 names"),
    ({"kind": "graph", "xmin": 0, "xmax": 10, "xstep": 0.1, "ymin": 0, "ymax": 1, "ystep": 1}, "40 or fewer"),
    ({"kind": "graph", "xmin": "a", "xmax": 10, "xstep": 1, "ymin": 0, "ymax": 1, "ystep": 1}, "are numbers"),
])
def test_bad_boards_are_refused_with_the_fix(board, message):
    data = {**S.read_json(ROOT / "examples" / "sci7-selection-teamwork.json"), "board": board}
    with pytest.raises(TW.TeamworkError, match=message):
        TW.normalize(data)


def test_a_lab_table_is_blank_and_tokens_come_in_sizes(tmp_path):
    report = TW.build(ROOT / "examples" / "sci7-predators-teamwork.json", tmp_path)
    pages = text_of(report["pdf"])
    task = next(p for p in pages if p.startswith("Group task"))
    assert "Our forest" in task and task.count("Generation") == 2 and "Hares" in task
    tokens = [p for p in pages if p.startswith("Tokens for one group")]
    assert len(tokens) == 1 and tokens[0].count("hare") == 60 and tokens[0].count("LYNX") == 6
    data = S.read_json(ROOT / "examples" / "sci7-predators-teamwork.json")
    data["table"]["rows"] = 40  # more than the page holds
    S.write_json(tmp_path / "big.json", data)
    assert any("room for" in w for w in TW.build(tmp_path / "big.json", tmp_path / "big")["warnings"])


def test_a_jigsaw_gives_each_expert_a_letter_and_a_sheet(tmp_path):
    report = TW.build(ROOT / "examples" / "sci9-exoplanets-teamwork.json", tmp_path)
    pages = text_of(report["pdf"])
    cards = "".join(pages[1:3])
    assert all(f"Expert {x}: your job" in cards for x in "ABCD") and "Listener" not in cards
    assert "Your part: The transit method." in cards
    sheets = [p for p in pages if "Teach box" in p and "(Plain English)" not in p and "(Español)" not in p]
    assert len(sheets) == 4 and all(sheets[k].startswith(f"Expert {x}: ") for k, x in enumerate("ABCD"))
    assert "Its answer" in sheets[0] and "A picture I'll draw" in sheets[0]
    assert any(p.startswith("Home group notes") for p in pages)
    assert "Every expert counts" in pages[0]


def test_reading_groups_stop_after_each_part(tmp_path):
    report = TW.build(ROOT / "examples" / "ela4-garden-teamwork.json", tmp_path)
    reading = text_of(report["pdf"])[-1]
    assert reading.count("Stop and talk, in this order: Summarizer, Questioner, Clarifier, Predictor") == 3
    assert "Last stop: Summarizer, Questioner, Clarifier. Then sum up the whole reading" in reading  # nothing to predict
    assert reading.startswith("Read together") and "the Predictor looks at the title" in reading and "Amara" in reading


def test_coach_and_player_switch_halfway(tmp_path):
    report = TW.build(ROOT / "examples" / "math6-ratios-teamwork.json", tmp_path)
    sheet = text_of(report["pdf"])[-1]
    assert sheet.count("Switch jobs here") == 1
    assert sheet.index("6.") < sheet.index("Switch jobs here") < sheet.index("7.")
    cards = text_of(report["pdf"])[1]
    assert "Say “Check it,” and let them try again." in cards and "Give a hint, then show it." in cards
    assert "turn the folded sheet around" in sheet


def test_numbered_heads_cards_are_numbers_and_questions_run_onto_more_pages(tmp_path):
    data = S.read_json(ROOT / "examples" / "chem10-moles-teamwork.json")
    data["cards"] = data["cards"] * 6  # 48 questions: more than one page
    path = tmp_path / "heads.json"
    S.write_json(path, data)
    report = TW.build(path, tmp_path / "out")
    pages = text_of(report["pdf"])
    assert all(f"Number {n}: your job" in "".join(pages) for n in range(1, 5))
    asked = "".join(p for p in pages if "Questions to ask" in p)
    assert asked.count("Answer: 2, 1, 2") == 6 and "48." in asked  # every question, none dropped


# --- Errors that say what to fix --------------------------------------------------------------

@pytest.mark.parametrize("change, message", [
    ({"structure": "fishbowl"}, "\"structure\" is one of"),
    ({"group_size": 6}, "works with 3 to 5 students"),
    ({"colour": "red"}, "unknown field colour"),
    ({"steps": []}, "a lab needs \"steps\""),
    ({"tokens": [{"label": "green", "count": "40"}]}, "\"count\" is a whole number"),
    ({"tokens": [{"label": "green", "count": 40, "pattern": "red"}]}, "black and white"),
    ({"tokens": [{"label": "lynx", "count": 4, "size": 5}]}, "0.5 to 4"),
    ({"table": {"columns": ["a"] * 7, "rows": 3}}, "up to 6 headings"),
    ({"structure": "jigsaw", "parts": [{"title": "A", "text": "x"}]}, "needs 3-5 \"parts\""),
    ({"structure": "pairs", "group_size": 2}, "needs \"cards\""),
    ({"structure": "reciprocal", "parts": [{"title": "only"}, {"text": "x"}]}, "part 1: needs \"text\""),
    ({"rounds": "three"}, "\"rounds\" is a whole number"),
    ({"rounds": [3]}, "\"rounds\" is a whole number"),
    ({"grade": [7]}, "\"grade\" is a whole number from 2 to 12"),
    ({"grade": 14}, "from 2 to 12"),
    ({"structure": ["lab"]}, "\"structure\" is one of"),
    ({"title": {"x": 1}}, "\"title\" is text"),
    ({"materials": "one die"}, "\"materials\" is a list of texts"),
    ({"steps": [["Roll."]]}, "\"steps\" is a list of texts"),
    ({"dice": {"rows": [6]}}, "\"dice\" is"),
    ({"structure": "jigsaw", "parts": [{"title": "A", "text": "x", "teach": "why it dips"}] * 3}, "\"teach\" is a list"),
    ({"structure": "pairs", "group_size": 2, "cards": [{"q": "6 x 7", "a": 42}], "tokens": [{"label": "x", "count": 1}]},
     "print only in a lab"),
])
def test_bad_activities_are_refused_with_the_fix(change, message):
    base = S.read_json(ROOT / "examples" / "sci7-selection-teamwork.json")
    if change.get("structure", "lab") != "lab" and "tokens" not in change:
        base = {k: v for k, v in base.items() if k not in TW.LAB_ONLY and k != "group_size"}
    data = {**base, **change}
    with pytest.raises(TW.TeamworkError, match=message.replace("(", r"\(").replace(")", r"\)")):
        TW.normalize(data)


def test_number_answers_and_zero_are_fine_on_cards(tmp_path):
    data = {"title": "Facts", "grade": 3, "structure": "pairs", "cards": [{"q": "6 x 7", "a": 42}, {"q": "5 - 5", "a": 0}]}
    S.write_json(tmp_path / "f.json", data)
    sheet = text_of(TW.build(tmp_path / "f.json", tmp_path / "out")["pdf"])[-1]
    assert "42" in sheet and "5 - 5" in sheet


def test_no_worksheet_is_flagged(tmp_path):
    data = S.read_json(ROOT / "examples" / "sci7-selection-teamwork.json")
    del data["worksheet"]
    S.write_json(tmp_path / "lab.json", data)
    report = TW.build(tmp_path / "lab.json", tmp_path / "out")
    assert any("individual worksheet" in w for w in report["warnings"])


# --- Mixed-skill groups -----------------------------------------------------------------------

def _marked_class(folder: Path, scores: dict[str, float]) -> None:
    """A marked worksheet where each student got the given fraction of every question."""
    from test_progress import _marked
    source = ROOT / "examples" / "math6-ratios-02.json"
    key_items = S.read_json(source)["questions"]
    points = {}
    for sid, frac in scores.items():
        points[sid] = {q["q"]: (0 if frac < 0.5 else None) for q in key_items if q.get("q")}
        points[sid] = {q: v for q, v in points[sid].items() if v is not None}
    _marked(folder, "week1", "2026-10-20", points)


def test_groups_mix_the_range_and_deal_jobs_at_random(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    scores = {f"01{k:02d}": (1.0 if k < 8 else 0.0) for k in range(16)}  # 8 got everything, 8 nothing
    _marked_class(tmp_path / "P3", scores)
    report = TW.form_groups(tmp_path / "P3", size=4)
    assert len(report["groups"]) == 4 and report["mixed"]
    for g in report["groups"]:
        ids = [sid for sid, _ in g]
        assert sum(scores[sid] for sid in ids) == 2  # two from the top half, two from the bottom, in every group
        assert sorted(role for _, role in g) == sorted(r[0] for r in TW.ROLES["lab"][:4])
    first_jobs = [dict(g) for g in report["groups"]]
    top_jobs = {first_jobs[k][sid] for k, g in enumerate(report["groups"]) for sid, _ in g if scores[sid] == 1}
    assert len(top_jobs) > 1  # strong students don't all start as the same job
    text = report["path"].read_text()
    assert "don't post" in text and "0100" in text and report["path"].name == "groups-lab.md"


def test_pairs_follow_pals_and_similar_groups_keep_neighbors(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    scores = {f"01{k:02d}": (1.0 if k < 4 else 0.0) for k in range(8)}  # 0100-0103 strong, 0104-0107 not yet
    _marked_class(tmp_path / "P3", scores)
    pairs = TW.form_groups(tmp_path / "P3", size=2, structure="pairs")
    assert len(pairs["groups"]) == 4
    for g in pairs["groups"]:  # one from each half: never two strong or two still learning together
        assert sorted(scores[sid] for sid, _ in g) == [0.0, 1.0]
    similar = TW.form_groups(tmp_path / "P3", size=4, similar=True)
    assert sorted(sorted(scores[sid] for sid, _ in g) for g in similar["groups"]) == [[0.0] * 4, [1.0] * 4]
    assert similar["path"].name == "groups-lab-similar.md" and pairs["path"].name == "groups-pairs.md"
    assert pairs["path"].exists() and similar["path"].exists()  # one doesn't replace the other


def test_groups_never_leave_a_student_alone_and_name_each_structure_s_jobs(tmp_path):
    roster = tmp_path / "ids.csv"
    roster.write_text("id\n" + "\n".join(f"02{k:02d}" for k in range(9)) + "\n")
    (tmp_path / "none").mkdir()
    pairs = TW.form_groups(tmp_path / "none", size=2, roster_path=roster, structure="pairs")
    assert not pairs["mixed"] and sorted(len(g) for g in pairs["groups"]) == [2, 2, 2, 3]
    trio = next(g for g in pairs["groups"] if len(g) == 3)
    assert [role for _, role in trio] == ["Coach", "Player", "Player"]
    jig = TW.form_groups(tmp_path / "none", size=4, roster_path=roster, structure="jigsaw", out=tmp_path / "j")
    assert sorted(len(g) for g in jig["groups"]) == [4, 5]
    five = next(g for g in jig["groups"] if len(g) == 5)
    assert [role for _, role in five] == ["Expert A", "Expert B", "Expert C", "Expert D", "Expert A"]
    heads = TW.form_groups(tmp_path / "none", size=3, roster_path=roster, structure="heads", out=tmp_path / "h")
    assert all([role for _, role in g] == ["Number 1", "Number 2", "Number 3"] for g in heads["groups"])
    with pytest.raises(TW.TeamworkError, match="no marked classes"):
        TW.form_groups(tmp_path / "none", size=4)
    with pytest.raises(TW.TeamworkError, match="no folder"):
        TW.form_groups(tmp_path / "typo", size=4, roster_path=roster)
    with pytest.raises(TW.TeamworkError, match="works with groups of 3 to 5, not 0"):
        TW.form_groups(tmp_path / "none", size=0, roster_path=roster)


def test_teamwork_and_groups_run_in_the_sandbox(tmp_path):
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "teamwork",
                          str(ROOT / "examples" / "sci9-exoplanets-teamwork.json"), "--out", str(tmp_path / "out")],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "Jigsaw, groups of 4" in run.stdout and "Expert sheets" in run.stdout and "Check:" not in run.stdout
    roster = tmp_path / "ids.csv"
    roster.write_text("0101\n0102\n0103\n0104\n")
    (tmp_path / "c").mkdir()
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "groups", str(tmp_path / "c"),
                          "--roster", str(roster), "--size", "2", "--structure", "pairs"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "2 groups, at random" in run.stdout and "(Coach)" in run.stdout


# --- Regressions from the code review ----------------------------------------------------------

def test_groups_stay_inside_each_structure_s_sizes_and_spread_the_extras(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    scores = {f"03{k:02d}": k / 27 for k in range(27)}
    _marked_class(tmp_path / "P4", {sid: (1.0 if v >= 0.5 else 0.0) for sid, v in scores.items()})
    similar = TW.form_groups(tmp_path / "P4", size=4, similar=True)
    assert sorted(len(g) for g in similar["groups"]) == [3, 4, 4, 4, 4, 4, 4]  # not six of 4 and one of 7
    heads = TW.form_groups(tmp_path / "P4", size=5, structure="heads")
    assert max(len(g) for g in heads["groups"]) == 5
    assert {role for g in heads["groups"] for _, role in g} <= {f"Number {n}" for n in range(1, 6)}
    lab = TW.form_groups(tmp_path / "P4", size=4)
    assert {role for g in lab["groups"] for _, role in g} <= {r[0] for r in TW.ROLES["lab"][:4]}  # printed cards only
    assert TW.group_sizes(7, 4, 3, 5) == [4, 3] and TW.group_sizes(3, 4, 3, 5) == [3]
    assert TW.group_sizes(31, 4, *TW.group_range("jigsaw", 4)) == [5, 5, 5, 4, 4, 4, 4]


def test_the_teacher_s_group_count_is_right_for_any_class(tmp_path):
    for n, expect in ((3, "For 3 students: 1 group of 3."), (7, "For 7 students: 2 groups (1 of 4, 1 of 3)."),
                      (28, "For 28 students: 7 groups of 4.")):
        data = {"title": "L", "grade": 7, "structure": "lab", "steps": ["Roll."], "class_size": n}
        S.write_json(tmp_path / "l.json", data)
        assert expect in text_of(TW.build(tmp_path / "l.json", tmp_path / f"o{n}")["pdf"])[0]


def test_reading_parts_print_key_words_and_quotes_and_long_parts_are_flagged(tmp_path):
    data = {"title": "R", "grade": 4, "structure": "reciprocal",
            "parts": [{"text": "Amara planted beans by the vent.", "words": [{"word": "vent", "means": "an opening"}],
                       "quote": "Beans need warm soil.", "quote_source": "Mr. Ortiz"}, {"text": "The beans grew."}]}
    S.write_json(tmp_path / "r.json", data)
    reading = text_of(TW.build(tmp_path / "r.json", tmp_path / "out")["pdf"])[-1]
    assert "Key words: vent: an opening" in reading and "“Beans need warm soil.”" in reading and "Mr. Ortiz" in reading
    data["parts"][1]["text"] = "The beans grew tall and green in the sun. " * 90
    S.write_json(tmp_path / "long.json", data)
    assert any("longer than a page" in w for w in TW.build(tmp_path / "long.json", tmp_path / "l")["warnings"])


def test_overflows_are_flagged_not_silent(tmp_path):
    lab = S.read_json(ROOT / "examples" / "sci7-selection-teamwork.json")
    lab["steps"] = ["Roll the die, then move each beetle token one square toward the edge of the desk, and say "
                    "out loud what happened so the Recorder can write it down."] * 16
    lab["debrief"] = ["Ask each group to report what changed in their population, and why they think so."] * 18
    S.write_json(tmp_path / "l.json", lab)
    warnings = TW.build(tmp_path / "l.json", tmp_path / "out")["warnings"]
    assert any("task card runs off the page" in w for w in warnings)
    assert any("teacher's page ran out of room" in w for w in warnings)
    jig = S.read_json(ROOT / "examples" / "sci9-exoplanets-teamwork.json")
    jig["title"] = "How Do Astronomers Find Planets Around Other Stars When They Cannot See Them Directly"
    jig["minutes"] = 20
    jig["parts"][0]["words"] = [{"word": "transit", "means": "عبور"}]
    S.write_json(tmp_path / "j.json", jig)
    report = TW.build(tmp_path / "j.json", tmp_path / "j")
    assert any("needs about 31 minutes" in w for w in report["warnings"])
    assert any("can't shape right-to-left" in w for w in report["warnings"])


def test_a_key_s_label_comes_off_but_its_conditions_stay():
    assert S.unlabeled("Full credit (2 points): wind") == "wind"
    assert S.unlabeled("Full credit: wind") == "wind"
    assert S.unlabeled("Full credit for any two of: wind, water, ice").startswith("Full credit for any two of")


def test_preview_replaces_only_what_it_makes(tmp_path):
    from reportlab.pdfgen import canvas as cv
    pdf = tmp_path / "deck.pdf"
    c = cv.Canvas(str(pdf))
    for _ in range(3):
        c.showPage()
    c.save()
    out = tmp_path / "preview"
    out.mkdir()
    for name in ("deck-p1.png", "deck-p2.png", "deck-p7.png", "deck-sheet1.png"):
        (out / name).write_bytes(b"old")
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / "paper_loop.py"), "preview", str(pdf), *a],  # noqa: E731
                                    capture_output=True, text=True)
    assert run("--page", "2").returncode == 0
    names = sorted(p.name for p in out.iterdir())
    assert "deck-p7.png" not in names and (out / "deck-p1.png").read_bytes() == b"old" and "deck-sheet1.png" in names
    assert run().returncode == 0
    assert sorted(p.name for p in out.iterdir()) == ["deck-p1.png", "deck-p2.png", "deck-p3.png"]


# --- Versions and team points ------------------------------------------------------------------

def test_versions_print_plain_and_latin_languages_and_put_other_scripts_in_word(tmp_path):
    report = TW.build(ROOT / "examples" / "sci9-exoplanets-teamwork.json", tmp_path)
    names = [name for name, *_ in report["pages"]]
    assert "Plain English: expert sheets" in names and "Español: expert sheets" in names
    pages = text_of(report["pdf"])
    assert "Plain English (pages 9-12); Español (pages 13-16)" in pages[0]
    assert any(p.startswith("Expert B: El método del bamboleo") for p in pages)
    data = S.read_json(ROOT / "examples" / "sci9-exoplanets-teamwork.json")
    data["versions"] = [{"id": "ar", "language": "ar", "parts": [{"title": "طريقة العبور", "text": "عندما يمر كوكب أمام نجمه."}]
                         + [{}] * 3}]
    S.write_json(tmp_path / "ar.json", data)
    report = TW.build(tmp_path / "ar.json", tmp_path / "ar")
    assert report["word_files"] and Path(report["word_files"][0]).name == "ar.docx"
    assert "العبور" in zipfile.ZipFile(report["word_files"][0]).read("word/document.xml").decode()
    assert "the Word file versions/ar.docx" in text_of(report["pdf"])[0]
    data["versions"] = [{"id": "x"}]
    with pytest.raises(TW.TeamworkError, match="changes nothing"):
        TW.normalize(data)


def test_team_points_reward_each_student_s_own_improvement(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from test_progress import _marked
    cls = tmp_path / "P5"
    ids = ["0501", "0502", "0503", "0504"]
    _marked(cls, "week1", "2026-10-20", {"0501": {1: 0, 2: 0, 3: 0}, "0502": {}, "0503": {1: 0}, "0504": {}})
    exit_sheet = S.read_json(ROOT / "examples" / "math6-ratios-02.json")
    exit_sheet["assignment_id"] = "exit-01"
    exit_sheet.pop("versions", None)
    S.write_json(tmp_path / "exit-01.json", exit_sheet)
    _marked(cls, "exit", "2026-10-27", {"0501": {}, "0502": {}, "0503": {1: 0, 2: 0, 3: 0, 4: 0}},
            source=tmp_path / "exit-01.json")
    (cls / "progress").mkdir()
    S.write_json(cls / "progress" / "groups-lab.json",
                 {"groups": [[{"id": "0501", "job": "Recorder"}, {"id": "0502", "job": "Skeptic"}],
                             [{"id": "0503", "job": "Recorder"}, {"id": "0504", "job": "Skeptic"}]]})
    report = TW.team_points(cls, "exit-01")
    (_, t1, avg1), (_, t2, avg2) = report["teams"]
    assert dict((sid, pts) for sid, _, _, pts in t1) == {"0501": 30, "0502": 30}  # a big gain and a perfect paper
    assert dict((sid, pts) for sid, _, _, pts in t2) == {"0503": 5, "0504": None}  # well below their usual; absent
    assert avg1 == 30 and avg2 == 5
    posted = text_of(report["pdf"])[0]
    assert "Team 1" in posted and "0501" not in posted  # the posted page names no one
    assert "0503: " in report["md"].read_text()
    with pytest.raises(TW.TeamworkError, match="no marked class of 'nope'"):
        TW.team_points(cls, "nope")


def test_game_groups_have_no_jobs_and_unmarked_students_go_in_the_middle(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    scores = {f"06{k:02d}": (1.0 if k < 6 else 0.0) for k in range(12)}
    _marked_class(tmp_path / "P6", scores)
    roster = tmp_path / "ids.csv"
    roster.write_text("\n".join([*scores, "0690", "0691"]) + "\n")
    report = TW.form_groups(tmp_path / "P6", size=4, structure="game", similar=True, roster_path=roster)
    assert all(role == "" for g in report["groups"] for _, role in g)
    assert max(len(g) for g in report["groups"]) <= 4  # never more players than the game takes
    text = report["path"].read_text()
    assert "Listed from the highest recent scores (Group 1)" in text and "(Facilitator)" not in text
    first, last = report["groups"][0], report["groups"][-1]
    assert not {"0690", "0691"} & {sid for sid, _ in first + last}  # in the middle, not at the teacher's table


def test_the_ranking_counts_every_point_the_same(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from test_progress import _marked
    # 0701 misses the 1-point choice (Q4) only; 0702 misses the big table (Q1) and the work (Q2)
    _marked(tmp_path / "P7", "w1", "2026-10-20", {"0701": {4: 0}, "0702": {1: 0, 2: 0}, "0703": {}, "0704": {1: 0, 2: 0, 3: 0}})
    report = TW.form_groups(tmp_path / "P7", size=2, structure="pairs")
    pairs = [sorted(sid for sid, _ in g) for g in report["groups"]]
    assert ["0701", "0702"] in pairs or ["0701", "0704"] in pairs  # 0701 ranks in the top half


def test_boards_can_be_pictures_and_data_can_have_blanks(tmp_path):
    data = S.read_json(ROOT / "examples" / "sci7-selection-teamwork.json")
    data["board"] = [{"kind": "diagram", "title": "The track", "width": 300, "height": 120,
                      "shapes": [{"shape": "polyline", "points": [[10, 100], [80, 10], [150, 70], [220, 30], [290, 90]]},
                                 {"shape": "text", "x": 10, "y": 106, "text": "A (8 m)"}]},
                     {"kind": "rows", "rows": ["PE", "KE", "Thermal"]}]
    data["data"] = [{"title": "Track points", "columns": ["Point", "Height (m)", "PE", "KE"],
                     "rows": [["A", "8", "", ""], ["B", "0", "", ""]]}]
    data["launch"] = ["Sketch the track on the board and model the first move."]
    data["class_size"] = 29
    data["tokens"] = [{"label": "500 J", "count": 12, "pattern": "dots"}]  # a small set: several groups to a page
    S.write_json(tmp_path / "t.json", data)
    report = TW.build(tmp_path / "t.json", tmp_path / "out")
    pages = text_of(report["pdf"])
    names = [n for n, *_ in report["pages"]]
    assert names.count("Board") == 1 and report["pages"][names.index("Board")][2] - report["pages"][names.index("Board")][1] == 1
    assert any("A (8 m)" in p for p in pages) and any("Thermal" in p for p in pages)
    assert "Launch, with the whole class" in pages[0] and "In a group of 5, two students share a job card." in pages[0]
    assert "the boards (pages" in pages[0]
    assert "one page holds" in pages[0] and any(p.startswith("Tokens: ") and "groups' sets" in p for p in pages)
