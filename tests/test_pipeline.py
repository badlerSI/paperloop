"""End-to-end checks on simulated scans with the stand-in marker (no API calls)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from pypdf import PdfReader, PdfWriter

from paperloop import template as T
from paperloop.ingest import ingest, read_student_id
from paperloop.make import load_assignment, make_worksheet
from paperloop.mark import MockMarker, mark
from paperloop.render import RenderBlocked, printable, render
from paperloop.review import review
from paperloop.schemas import WorksheetDef, load
from paperloop.simulate import simulate

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sci7-density-01.json"


@pytest.fixture(scope="module")
def assignment(tmp_path_factory):
    out = tmp_path_factory.mktemp("assignment")
    make_worksheet(load(WorksheetDef, EXAMPLE), out)
    return out


@pytest.fixture(scope="module")
def scan(assignment, tmp_path_factory):
    return simulate(assignment, tmp_path_factory.mktemp("scans") / "class.pdf")


@pytest.fixture(scope="module")
def ingested(scan, assignment, tmp_path_factory):
    work = tmp_path_factory.mktemp("work")
    return work, ingest(scan, assignment, work)


def test_layout(assignment):
    layout, key = load_assignment(assignment)
    assert [[b.q for b in p.boxes] for p in layout.pages] == [[1, 2, 3], [4, 5]]
    assert [p.qr for p in layout.pages] == ["sci7-density-01|p1", "sci7-density-01|p2"]
    assert [i.q for i in key.items] == [1, 2, 3, 4, 5]
    for p in layout.pages:
        for b in p.boxes:
            assert b.rect[2] < b.feedback_rect[0], "comment gutter must sit beside the box, not on it"
            assert b.rect[1] > T.SUMMARY_RECT[3]


def test_every_page_routed(scan, ingested):
    """Page routing target: 100%, including an upside-down sheet and a blank page."""
    truth = json.loads(scan.with_suffix(".truth.json").read_text())
    _, result = ingested
    assert len(result.pages) == len(truth["scan_pages"])
    for t, page in zip(truth["scan_pages"], result.pages):
        if t.get("blank"):
            assert page.status == "blank"
        else:
            assert (page.status, page.student_id, page.page) == ("ok", t["student_id"], t["page"])


def test_fronts_and_backs_as_separate_scans(scan, assignment, tmp_path):
    """A one-sided scanner gives two PDFs; ingesting both routes the same pages."""
    reader = PdfReader(scan)
    halves = []
    for name, pages in (("fronts.pdf", reader.pages[::2]), ("backs.pdf", reader.pages[1::2])):
        writer = PdfWriter()
        for page in pages:
            writer.add_page(page)
        writer.write(tmp_path / name)
        halves.append(tmp_path / name)
    result = ingest(halves, assignment, tmp_path / "work")
    routed = sorted((p.student_id, p.page) for p in result.pages if p.status == "ok")
    assert routed == sorted((s, n) for s in ("0006", "0417", "2093", "3158") for n in (1, 2))


def test_two_bubbles_in_one_digit_goes_to_review(ingested, assignment):
    work, result = ingested
    page = next(p for p in result.pages if p.status == "ok")
    canonical = cv2.imread(str(work / page.image), cv2.IMREAD_GRAYSCALE)
    grid = load_assignment(assignment)[0].page(page.page).id_grid
    wrong = (int(page.student_id[0]) + 5) % 10
    cx, cy = T.pt_to_px(*grid.centers[0][wrong])
    cv2.circle(canonical, (round(cx), round(cy)), 12, 40, -1)
    student_id, problem = read_student_id(canonical, grid, T.DPI)
    assert student_id is None
    assert "two bubbles" in problem


class RecordingMarker(MockMarker):
    def __init__(self):
        self.images = []

    def mark_box(self, item, png):
        self.images.append(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE))
        return super().mark_box(item, png)


def test_mock_pipeline_end_to_end(ingested):
    work, _ = ingested
    marker = RecordingMarker()
    feedback = mark(work, marker)

    # Only answer-box crops leave the machine: every image is box-sized, never a page or the ID area.
    box_px = (88 - 4) * T.scale()  # 4 writing lines of 22pt, minus the inset on both edges
    assert marker.images and all(abs(img.shape[0] - box_px) < 3 for img in marker.images)

    # The blank copy is settled locally; everyone else's boxes went to the marker.
    for page in feedback.pages:
        expected_blank = page.student_id == "0006"
        assert all((b.verdict == "blank") == expected_blank for b in page.boxes)
    assert len(marker.images) == 15

    with pytest.raises(RenderBlocked):
        render(work)  # flagged answers must be reviewed first
    assert review(work, accept_all=True, say=lambda _: None) == 0

    result = render(work, grade="csv")
    assert len(PdfReader(result["returned"]).pages) == 8
    with open(result["grades"]) as f:
        rows = list(csv.DictReader(f))
    assert [r["student_id"] for r in rows] == ["0006", "0417", "2093", "3158"]
    assert rows[0]["total"] == "0"


def test_printable_keeps_pdf_fonts_happy():
    assert printable("density → mass ÷ volume ≥ 1 “ok”") == "density -> mass / volume >= 1 “ok”"
    assert printable("emoji 🙂") == "emoji ?"
