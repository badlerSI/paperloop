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
    strip = lambda page: [{k: v for k, v in b.items()} for b in page["boxes"]]  # noqa: E731
    assert json.loads(json.dumps(strip(ours["pages"][0]))) == strip(cli["pages"][0])
    assert S.read_json(root / "assignment" / "key.json") == S.read_json(tmp_path / "cli" / "key.json")


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

    summaries = {str(p["scan_index"]): {"strength": "A start.", "fixes": []} for p in result["pages"]}
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
