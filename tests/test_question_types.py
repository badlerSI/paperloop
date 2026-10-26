"""Circle-the-answer, labeling, and drawing questions, on simulated scans with a stand-in marker."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from pypdf import PdfReader

from paperloop.ingest import ingest
from paperloop.make import load_assignment, make_worksheet
from paperloop.mark import MockMarker, mark
from paperloop.render import render
from paperloop.schemas import WorksheetDef, load
from paperloop.score import metrics
from paperloop.simulate import simulate

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sci7-density-02.json"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("detectives")
    make_worksheet(load(WorksheetDef, EXAMPLE), root / "assignment")
    scan = simulate(root / "assignment", root / "class.pdf")
    ingest(scan, root / "assignment", root / "work")
    return root, scan


class CountingMarker(MockMarker):
    def __init__(self):
        self.calls = []

    def _record(self, kind, item, *pngs):
        shapes = [cv2.imdecode(np.frombuffer(p, np.uint8), cv2.IMREAD_GRAYSCALE).shape for p in pngs]
        self.calls.append((kind, item.q, shapes))

    def mark_box(self, item, png):
        self._record("short", item, png)
        return super().mark_box(item, png)

    def read_choice(self, item, png):
        self._record("choice", item, png)
        return super().read_choice(item, png)

    def mark_labels(self, item, blank_png, png):
        self._record("label", item, blank_png, png)
        return super().mark_labels(item, blank_png, png)

    def mark_drawing(self, item, blank_png, png):
        self._record("draw", item, blank_png, png)
        return super().mark_drawing(item, blank_png, png)


def test_layout_has_every_type(run):
    root, _ = run
    layout, key = load_assignment(root / "assignment")
    assert [[b.type for b in p.boxes] for p in layout.pages] == [["choice", "choice", "short"], ["label", "draw"]]
    assert [len(b.options) for b in layout.pages[0].boxes[:2]] == [4, 4]
    assert [s.n for s in layout.pages[1].boxes[0].labels] == [1, 2, 3]
    assert [i.points for i in key.items] == [1, 1, 2, 3, 3]
    assert (root / "assignment" / "template-p2.png").exists()


def test_marking_settles_what_it_can_from_the_scan(run):
    root, scan = run
    marker = CountingMarker()
    feedback = mark(root / "work", marker)
    truth = json.loads(scan.with_suffix(".truth.json").read_text())

    # Single circles are read from the scan; only the circled-then-crossed-out answer goes to the model.
    assert [(kind, q) for kind, q, _ in marker.calls if kind == "choice"] == [("choice", 1)]
    m = metrics(root / "work", truth)
    assert m["choices"] == 6 and m["choice_misreads"] == []

    # The blank copy never reaches the model: 3 students x (short, label, draw) + 1 choice.
    assert len(marker.calls) == 10
    blank = [b for p in feedback.pages if p.student_id == "0006" for b in p.boxes]
    assert all(b.verdict == "blank" for b in blank)

    # Labels and drawings are sent as a matching pair: the blank printed region and the student's.
    for kind, _, shapes in marker.calls:
        if kind in ("label", "draw"):
            assert len(shapes) == 2 and shapes[0] == shapes[1]

    pdf = render(root / "work", grade="back", force=True)["returned"]
    assert len(PdfReader(pdf).pages) == 8
