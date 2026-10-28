"""Group work where students teach each other: role cards, tasks, and mixed-skill groups (the plugin's
`teamwork` and `groups`)."""

from __future__ import annotations

import subprocess
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
    assert "For 31 students: 7 groups, 3 of them with one more (two students share a letter)." in pages[0]
    assert "The transit method" in pages[1]  # the tent names the expert's topic, for the home group
    assert "How the parts connect" in pages[-1] and "your own words" in pages[-1]
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
    sheets = [p for p in pages if "Teach box" in p]
    assert len(sheets) == 4 and all(sheets[k].startswith(f"Expert {x}: ") for k, x in enumerate("ABCD"))
    assert "Its answer" in sheets[0] and "A picture I'll draw" in sheets[0]
    assert "Home group notes" in pages[-1]
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
    ({"tokens": [{"label": "green", "count": "40"}]}, "whole-number \"count\""),
    ({"tokens": [{"label": "green", "count": 40, "pattern": "red"}]}, "black and white"),
    ({"tokens": [{"label": "lynx", "count": 4, "size": 5}]}, "0.5 to 4"),
    ({"table": {"columns": ["a"] * 7, "rows": 3}}, "up to 6 headings"),
    ({"structure": "jigsaw", "parts": [{"title": "A", "text": "x"}]}, "needs 3-5 \"parts\""),
    ({"structure": "pairs", "group_size": 2}, "needs \"cards\""),
    ({"structure": "reciprocal", "parts": [{"title": "only"}, {"text": "x"}]}, "part 1: needs \"text\""),
])
def test_bad_activities_are_refused_with_the_fix(change, message):
    data = {**S.read_json(ROOT / "examples" / "sci7-selection-teamwork.json"), **change}
    with pytest.raises(TW.TeamworkError, match=message.replace("(", r"\(").replace(")", r"\)")):
        TW.normalize(data)


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
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "groups", str(tmp_path / "c"),
                          "--roster", str(roster), "--size", "2", "--structure", "pairs"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "2 groups, at random" in run.stdout and "(Coach)" in run.stdout
