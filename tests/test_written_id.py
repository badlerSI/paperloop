"""One-page compact worksheet with a handwritten ID, read by a stand-in reader."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from paperloop.ingest import flatten, ingest
from paperloop.raster import load_template, student_ink
from paperloop.make import load_assignment, make_worksheet
from paperloop.schemas import IdRead, Usage, WorksheetDef, load
from paperloop.simulate import simulate

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sci6-water-01.json"


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    root = tmp_path_factory.mktemp("water")
    make_worksheet(load(WorksheetDef, EXAMPLE), root / "assignment")
    return root, simulate(root / "assignment", root / "class.pdf")


def test_six_questions_fit_one_page(scan):
    root, _ = scan
    layout, _ = load_assignment(root / "assignment")
    assert len(layout.pages) == 1
    page = layout.pages[0]
    assert [b.q for b in page.boxes] == [1, 2, 3, 4, 5, 6]
    assert page.id_grid is None and len(page.id_boxes) == 4
    assert all(b.rect[1] > page.summary_rect[3] for b in page.boxes)
    # Options in columns: question 2's four options sit side by side in one row.
    q2 = page.boxes[1]
    assert len({o.rect[1] for o in q2.options}) == 1 and len({o.rect[0] for o in q2.options}) == 4


class ScriptedReader:
    """Stands in for the model: replies from a script, and records what it was shown."""

    def __init__(self, replies):
        self.replies, self.shown = list(replies), []

    def __call__(self, png, n_digits):
        self.shown.append((len(png), n_digits))
        digits, confidence = self.replies.pop(0)
        return IdRead(digits=list(digits), confidence=confidence), Usage(cost_usd=0.001)


def test_written_ids_route_only_when_sure(scan, tmp_path):
    root, pdf = scan
    # Scan order from simulate (seed 7): 0417, 2093, blank, 0006, 3158.
    reader = ScriptedReader([("0417", 0.97), ("2O93", 0.95), ("0006", 0.85), ("3158", 0.96)])
    result = ingest(pdf, root / "assignment", tmp_path / "work", id_reader=reader, roster={"0417", "2093", "3158"})
    status = [(p.status, p.student_id, p.reason) for p in result.pages]
    assert status[0] == ("ok", "0417", None)
    assert status[1][0] == "review" and "not 4 clear digits" in status[1][2]  # an O isn't a 0
    assert status[2][0] == "blank"
    assert status[3][0] == "review" and "0.85 sure" in status[3][2]
    assert status[4] == ("ok", "3158", None)
    # The blank page never reaches the reader; every request carries only the ID strip.
    assert len(reader.shown) == 4 and all(n == 4 for _, n in reader.shown)
    assert result.id_usage.cost_usd == pytest.approx(0.004)


def test_roster_catches_a_confident_misread(scan, tmp_path):
    root, pdf = scan
    reader = ScriptedReader([("0417", 0.97), ("2098", 0.95), ("0006", 0.97), ("3158", 0.96)])
    result = ingest(pdf, root / "assignment", tmp_path / "work", id_reader=reader,
                    roster={"0417", "2093", "0006", "3158"})
    assert result.pages[1].status == "review" and "isn't on the class roster" in result.pages[1].reason


def test_without_a_reader_nothing_is_guessed(scan, tmp_path):
    root, pdf = scan
    result = ingest(pdf, root / "assignment", tmp_path / "work")
    assert {p.status for p in result.pages} == {"review", "blank"}


def test_roster_accepts_a_hesitant_read_no_slip_could_reach(scan, tmp_path):
    root, pdf = scan
    # Real handwriting gets 0.6-0.9 even when read right. 3157 is one digit from 3158, so 3158 still waits.
    reader = ScriptedReader([("0417", 0.6), ("2093", 0.6), ("0006", 0.6), ("3158", 0.6)])
    result = ingest(pdf, root / "assignment", tmp_path / "work", id_reader=reader,
                    roster={"0417", "2093", "0006", "3158", "3157"})
    status = [(p.status, p.student_id) for p in result.pages]
    assert status[:4] == [("ok", "0417"), ("ok", "2093"), ("blank", None), ("ok", "0006")]
    assert result.pages[4].status == "review" and "3157 on the roster is one digit away" in result.pages[4].reason


def test_hesitant_reads_wait_without_a_roster(scan, tmp_path):
    root, pdf = scan
    reader = ScriptedReader([("0417", 0.6), ("2093", 0.6), ("0006", 0.6), ("3158", 0.6)])
    result = ingest(pdf, root / "assignment", tmp_path / "work", id_reader=reader)
    assert {p.status for p in result.pages} == {"review", "blank"}


def test_flatten_takes_the_bow_out_of_a_curled_page(scan):
    root, _ = scan
    blank = load_template(str(root / "assignment"), 1)
    h, w = blank.shape
    # Like the worst real HP scan: the corners line up, the middle of the page sits ~4px right and 7px down.
    u = np.linspace(-0.5, 0.5, w, dtype=np.float32)[None, :]
    v = np.linspace(-0.5, 0.5, h, dtype=np.float32)[:, None]
    dx, dy = 4 * (1 - 4 * v * v) + 0 * u, 7 * (1 - 4 * u * u) * (1 - 4 * v * v)
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    bowed = cv2.remap(blank, xs - dx, ys - dy, cv2.INTER_LINEAR, borderValue=255)
    before, after = int(student_ink(bowed, blank).sum()), int(student_ink(flatten(bowed, blank), blank).sum())
    assert before > 1000  # drifted printing shows up as "student ink" and fakes answers
    assert after < before / 20
    assert flatten(blank, blank) is blank  # a flat page isn't resampled
