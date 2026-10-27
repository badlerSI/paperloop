"""Data formats passed between pipeline steps (see SPEC.md, "Data formats").

Rects are PDF points [x0, y0, x1, y1], origin bottom-left.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, Union

from pydantic import BaseModel, Discriminator, Field, Tag

Rect = tuple[float, float, float, float]
QuestionType = Literal["short", "choice", "label", "draw"]


# --- Worksheet definition (input to make) -----------------------------------

class Shape(BaseModel):
    """One element of a printed diagram. Coordinates are points inside the diagram, origin bottom-left."""

    shape: Literal["rect", "circle", "line", "arrow", "polyline", "polygon", "text"]
    id: str | None = None  # lets the simulator find regions, e.g. the "iron" box
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    r: float = 0
    points: list[tuple[float, float]] = Field(default_factory=list)  # line, arrow, polyline, polygon
    text: str = ""
    size: float = 9
    bold: bool = False
    align: Literal["left", "center", "right"] = "left"
    fill: float | None = None  # gray level, 0 black to 1 white; None for no fill
    stroke: float | None = 0.0  # gray level of the outline; None for no outline
    width: float = 1.0


class Diagram(BaseModel):
    width: float
    height: float
    shapes: list[Shape] = Field(default_factory=list)
    description: str = ""  # plain words for the model: what's printed, before the student touches it


class Option(BaseModel):
    letter: str
    text: str
    why: str = ""  # printed beside the question when this option is chosen


class LabelSpot(BaseModel):
    n: int
    box: tuple[float, float, float, float]  # x, y, w, h inside the diagram
    points_to: tuple[float, float] | None = None
    answer: str
    accept: list[str] = Field(default_factory=list)
    points: int = 1


class CheckItem(BaseModel):
    item: str  # what the model checks for, in observable terms
    short: str = ""  # shorter wording printed on the returned page
    points: int = 1


class ShortQ(BaseModel):
    type: Literal["short"] = "short"
    q: int
    prompt: str
    key: str
    points: int = 2
    lines: int = 4  # writing lines in the answer box


class ChoiceQ(BaseModel):
    type: Literal["choice"] = "choice"
    q: int
    prompt: str
    options: list[Option]
    answer: str
    points: int = 1
    columns: int = 1  # options side by side, for short options on a packed page


class LabelQ(BaseModel):
    type: Literal["label"] = "label"
    q: int
    prompt: str
    diagram: Diagram
    labels: list[LabelSpot]
    word_bank: list[str] = Field(default_factory=list)

    @property
    def points(self) -> int:
        return sum(spot.points for spot in self.labels)


class DrawQ(BaseModel):
    type: Literal["draw"] = "draw"
    q: int
    prompt: str
    diagram: Diagram  # the printed scaffold; its size is the drawing area
    checklist: list[CheckItem]

    @property
    def points(self) -> int:
        return sum(c.points for c in self.checklist)


def _question_type(value: Any) -> str:
    return value.get("type", "short") if isinstance(value, dict) else getattr(value, "type", "short")


Question = Annotated[
    Union[Annotated[ShortQ, Tag("short")], Annotated[ChoiceQ, Tag("choice")],
          Annotated[LabelQ, Tag("label")], Annotated[DrawQ, Tag("draw")]],
    Discriminator(_question_type),
]


class WorksheetDef(BaseModel):
    assignment_id: str
    title: str
    subject: str = "science"
    grade_band: str = "middle school"
    instructions: str = "Answer each question in its box. Write your ID number, not your name."
    # "bubbles" are read on the laptop. "write" is four handwritten digits, read by the model in a
    # request that carries only the ID boxes, never any answers.
    id_style: Literal["bubbles", "write"] = "bubbles"
    compact: bool = False  # tighter spacing and a smaller summary box, to fit more on a page
    questions: list[Question]


# --- Layout and key (output of make) ----------------------------------------

class OptionSpot(BaseModel):
    letter: str
    rect: Rect  # the whole option row; a circle anywhere in it counts as choosing it
    letter_at: tuple[float, float]  # center of the printed letter


class LabelBoxSpot(BaseModel):
    n: int
    rect: Rect


class Box(BaseModel):
    q: int
    type: QuestionType = "short"
    rect: Rect  # region cropped for marking
    feedback_rect: Rect  # gutter beside the box where comments get stamped
    prompt: str
    points: int
    lines: int = 0  # short answers: ruled writing lines in the box
    options: list[OptionSpot] = Field(default_factory=list)
    labels: list[LabelBoxSpot] = Field(default_factory=list)


class IdGrid(BaseModel):
    digits: int
    bubble_r: float
    writein_rects: list[Rect]
    centers: list[list[tuple[float, float]]]  # centers[digit][value]


class PageLayout(BaseModel):
    page: int
    qr: str
    qr_rect: Rect
    id_grid: IdGrid | None = None  # bubble ID
    id_boxes: list[Rect] = Field(default_factory=list)  # handwritten ID, one digit per box
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
    type: QuestionType = "short"
    prompt: str
    points: int
    key: str = ""  # short
    options: list[Option] = Field(default_factory=list)  # choice
    answer: str = ""  # choice
    labels: list[LabelSpot] = Field(default_factory=list)  # label
    word_bank: list[str] = Field(default_factory=list)  # label
    checklist: list[CheckItem] = Field(default_factory=list)  # draw
    diagram: str = ""  # label and draw: what's printed, in words


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
    id_usage: "Usage" = Field(default_factory=lambda: Usage())  # model calls that read handwritten IDs


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


class IdRead(BaseModel):
    """The model's reading of a handwritten ID: one character per box, "?" where it can't tell."""

    digits: list[str]
    confidence: float


class ChoiceRead(BaseModel):
    """The model's reading of a circle-the-answer question the scan alone couldn't settle."""

    selected: list[str]
    crossed_out: list[str] = Field(default_factory=list)
    confidence: float


class LabelRead(BaseModel):
    n: int
    transcription: str
    verdict: Literal["correct", "incorrect", "blank", "unreadable"]
    confidence: float


class LabelMark(BaseModel):
    labels: list[LabelRead]
    comment: str
    confidence: float


class ItemCheck(BaseModel):
    n: int
    met: Literal["yes", "no", "unclear"]
    note: str = ""


class DrawMark(BaseModel):
    description: str  # what the student drew, before any judging
    items: list[ItemCheck]
    comment: str
    confidence: float


class BoxResult(BoxMark):
    q: int
    type: QuestionType = "short"
    points_possible: int
    points_awarded: float
    flagged: bool
    flag_reasons: list[str] = Field(default_factory=list)
    reviewed: bool = False
    crop: str
    # Per-part results: a choice's reading, each label, or each checklist item.
    details: list[dict[str, Any]] = Field(default_factory=list)


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
