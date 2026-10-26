"""Data formats passed between pipeline steps (see SPEC.md, "Data formats").

Rects are PDF points [x0, y0, x1, y1], origin bottom-left.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

Rect = tuple[float, float, float, float]


# --- Worksheet definition (input to make) -----------------------------------

class Question(BaseModel):
    q: int
    prompt: str
    key: str
    points: int = 2
    lines: int = 4  # writing lines in the answer box


class WorksheetDef(BaseModel):
    assignment_id: str
    title: str
    subject: str = "science"
    grade_band: str = "middle school"
    instructions: str = "Answer each question in its box. Write your ID number, not your name."
    questions: list[Question]


# --- Layout and key (output of make) ----------------------------------------

class Box(BaseModel):
    q: int
    rect: Rect
    feedback_rect: Rect  # gutter beside the box where comments get stamped
    prompt: str
    points: int


class IdGrid(BaseModel):
    digits: int
    bubble_r: float
    writein_rects: list[Rect]
    centers: list[list[tuple[float, float]]]  # centers[digit][value]


class PageLayout(BaseModel):
    page: int
    qr: str
    qr_rect: Rect
    id_grid: IdGrid
    summary_rect: Rect
    boxes: list[Box]


class Layout(BaseModel):
    assignment_id: str
    title: str
    page_size: tuple[float, float]
    markers: dict[int, Rect]
    pages: list[PageLayout]

    def page(self, n: int) -> PageLayout:
        for p in self.pages:
            if p.page == n:
                return p
        raise KeyError(f"{self.assignment_id} has no page {n}")


class KeyItem(BaseModel):
    q: int
    prompt: str
    key: str
    points: int


class AnswerKey(BaseModel):
    assignment_id: str
    subject: str
    grade_band: str
    items: list[KeyItem]

    def item(self, q: int) -> KeyItem:
        return next(i for i in self.items if i.q == q)


# --- Ingest -------------------------------------------------------------------

class PageScan(BaseModel):
    scan_index: int  # 1-based page number across the scanned PDFs, in the order given
    status: Literal["ok", "blank", "review"]
    reason: str | None = None
    assignment_id: str | None = None
    page: int | None = None
    student_id: str | None = None
    image: str | None = None  # deskewed page, relative to the work dir
    raw_image: str | None = None  # page as scanned, for the review pile


class IngestResult(BaseModel):
    source_pdfs: list[str]
    assignment_dir: str
    dpi: int
    pages: list[PageScan]


# --- Mark ----------------------------------------------------------------------

Verdict = Literal["correct", "partial", "incorrect", "blank", "unreadable"]


class BoxMark(BaseModel):
    """What the model returns for one answer box."""

    transcription: str
    uncertain_words: list[str] = Field(default_factory=list)
    verdict: Verdict
    comment: str
    confidence: float
    key_ambiguous: bool = False


class BoxResult(BoxMark):
    q: int
    points_possible: int
    points_awarded: float
    flagged: bool
    flag_reasons: list[str] = Field(default_factory=list)
    reviewed: bool = False
    crop: str


class PageSummary(BaseModel):
    strength: str
    fixes: list[str] = Field(default_factory=list)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cost_usd += other.cost_usd


class PageFeedback(BaseModel):
    scan_index: int
    student_id: str
    page: int
    boxes: list[BoxResult]
    summary: PageSummary
    usage: Usage = Field(default_factory=Usage)


class Feedback(BaseModel):
    assignment_id: str
    model: str
    effort: str
    threshold: float
    pages: list[PageFeedback]
    totals: Usage = Field(default_factory=Usage)


M = TypeVar("M", bound=BaseModel)


def load(model: type[M], path: Path) -> M:
    return model.model_validate_json(Path(path).read_text())


def save(obj: BaseModel, path: Path) -> None:
    Path(path).write_text(json.dumps(obj.model_dump(mode="json"), indent=2) + "\n")
