"""Mark: crop each question, judge it, save feedback.json.

Only cropped question regions leave the laptop: never the header, the ID
bubbles, or the margins. What can be settled from the scan alone is: empty
answers, and circle-the-answer questions with one clear mark. Everything else
goes to the model one region at a time. Labels and drawings are sent with the
blank printed region beside the student's, so the model can tell their marks
from the printing. Each page then gets a text-only summary call.
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import anthropic
import cv2
import numpy as np

from . import raster
from .make import load_assignment
from .schemas import (
    AnswerKey, Box, BoxMark, BoxResult, ChoiceRead, DrawMark, Feedback, IngestResult, KeyItem, LabelMark,
    PageFeedback, PageScan, PageSummary, Usage, load, save,
)

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"
DEFAULT_THRESHOLD = 0.8
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# USD per million tokens: input, output, cache read, cache write (5-minute). List prices, Oct 2026.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}
# Server-side refusal fallback; Haiku has none, so it's sent only for these.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MIN_INK_PX = 60  # student-ink pixels below which an answer counts as empty
BOX_INSET_PT = 2.0  # crop short answers just inside the printed border
MIN_MARK_PX = 150  # a circle around an option leaves at least this much ink in its row
MARK_AMBIGUOUS = 0.35  # a runner-up row with this share of the top row's ink means two marks

BOX_SCHEMA = {
    "type": "object",
    "properties": {
        # Transcription comes first so the model reads before it judges.
        "transcription": {"type": "string"},
        "uncertain_words": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect", "blank", "unreadable"]},
        "comment": {"type": "string"},
        "confidence": {"type": "number"},
        "key_ambiguous": {"type": "boolean"},
    },
    "required": ["transcription", "uncertain_words", "verdict", "comment", "confidence", "key_ambiguous"],
    "additionalProperties": False,
}
CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "selected": {"type": "array", "items": {"type": "string"}},
        "crossed_out": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["selected", "crossed_out", "confidence"],
    "additionalProperties": False,
}
LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "transcription": {"type": "string"},
                "verdict": {"type": "string", "enum": ["correct", "incorrect", "blank", "unreadable"]},
                "confidence": {"type": "number"},
            },
            "required": ["n", "transcription", "verdict", "confidence"],
            "additionalProperties": False,
        }},
        "comment": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["labels", "comment", "confidence"],
    "additionalProperties": False,
}
DRAW_SCHEMA = {
    "type": "object",
    "properties": {
        # The literal description comes first so credit rests on what's actually drawn.
        "description": {"type": "string"},
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "n": {"type": "integer"},
                "met": {"type": "string", "enum": ["yes", "no", "unclear"]},
                "note": {"type": "string"},
            },
            "required": ["n", "met", "note"],
            "additionalProperties": False,
        }},
        "comment": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["description", "items", "comment", "confidence"],
    "additionalProperties": False,
}
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"strength": {"type": "string"}, "fixes": {"type": "array", "items": {"type": "string"}}},
    "required": ["strength", "fixes"],
    "additionalProperties": False,
}


class MarkError(Exception):
    """A question or page the model couldn't mark; it goes to teacher review instead."""


# Errors that would hit every call the same way: stop instead of flagging each question.
FATAL = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)
RECOVERABLE = (MarkError, anthropic.APIStatusError, anthropic.APIConnectionError, ValueError)


def _prompt(name: str, key: AnswerKey) -> str:
    text = (PROMPTS_DIR / name).read_text()
    return text.replace("{grade_band}", key.grade_band).replace("{subject}", key.subject)


def _image(png: bytes) -> dict:
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(png).decode()}}


def _png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def points_for(verdict: str, possible: int) -> float:
    return {"correct": float(possible), "partial": possible / 2}.get(verdict, 0.0)


def read_choice(ink: np.ndarray, box: Box, dpi: int) -> tuple[str | None, str, list[int]]:
    """From the scan alone: (letter, "scan", ink per option), (None, "blank", ...), or (None, "ambiguous", ...)."""
    counts = [int(raster.crop(ink, o.rect, dpi).sum()) for o in box.options]
    order = sorted(range(len(counts)), key=counts.__getitem__, reverse=True)
    best = counts[order[0]]
    runner_up = counts[order[1]] if len(order) > 1 else 0
    if best < MIN_MARK_PX:
        return None, "blank", counts
    if runner_up >= MIN_MARK_PX and runner_up >= MARK_AMBIGUOUS * best:
        return None, "ambiguous", counts
    return box.options[order[0]].letter, "scan", counts


class ClaudeMarker:
    """Marks questions and pages with the Anthropic API."""

    def __init__(self, key: AnswerKey, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT,
                 client: anthropic.Anthropic | None = None):
        self.key, self.model, self.effort = key, model, effort
        self.client = client or anthropic.Anthropic()
        self.use_fallbacks = model in FALLBACK_MODELS
        self.systems = {name: _prompt(f"{name}.md", key)
                        for name in ("mark_region", "read_choice", "mark_labels", "mark_drawing", "page_summary")}

    def _create(self, **kwargs):
        if self.use_fallbacks:
            try:
                return self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                self.use_fallbacks = False  # this account or platform has no server-side fallback
        return self.client.messages.create(**kwargs)

    def _call(self, system: str, content: list, schema: dict) -> tuple[dict, Usage]:
        response = self._create(
            model=self.model,
            max_tokens=8000,
            system=[{"type": "text", "text": self.systems[system], "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        usage = usage_of(response)
        if response.stop_reason == "refusal":
            raise MarkError("the model declined to mark this")
        if response.stop_reason == "max_tokens":
            raise MarkError("the model's answer was cut off")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise MarkError("the model returned no answer")
        return json.loads(text), usage

    def mark_box(self, item: KeyItem, png: bytes) -> tuple[BoxMark, Usage]:
        content = [_image(png), {"type": "text", "text": (
            f"Question {item.q} ({item.points} points): {item.prompt}\n"
            f"Answer key: {item.key}\n"
            "The image is the student's answer box for this question.")}]
        data, usage = self._call("mark_region", content, BOX_SCHEMA)
        return BoxMark.model_validate(data), usage

    def read_choice(self, item: KeyItem, png: bytes) -> tuple[ChoiceRead, Usage]:
        options = "\n".join(f"{o.letter}. {o.text}" for o in item.options)
        content = [_image(png), {"type": "text", "text": f"Question {item.q}: {item.prompt}\nOptions:\n{options}"}]
        data, usage = self._call("read_choice", content, CHOICE_SCHEMA)
        return ChoiceRead.model_validate(data), usage

    def mark_labels(self, item: KeyItem, blank_png: bytes, png: bytes) -> tuple[LabelMark, Usage]:
        expected = "\n".join(
            f"Box {s.n}: {s.answer}" + (f" (also accept: {', '.join(s.accept)})" if s.accept else "")
            for s in item.labels)
        bank = f"Word bank printed on the page: {', '.join(item.word_bank)}\n" if item.word_bank else ""
        content = [{"type": "text", "text": "Image 1, the diagram as printed:"}, _image(blank_png),
                   {"type": "text", "text": "Image 2, the student's work:"}, _image(png),
                   {"type": "text", "text": (f"Question {item.q}: {item.prompt}\nThe diagram: {item.diagram}\n"
                                             f"{bank}Expected labels:\n{expected}")}]
        data, usage = self._call("mark_labels", content, LABEL_SCHEMA)
        return LabelMark.model_validate(data), usage

    def mark_drawing(self, item: KeyItem, blank_png: bytes, png: bytes) -> tuple[DrawMark, Usage]:
        checklist = "\n".join(f"{n}. {c.item}" for n, c in enumerate(item.checklist, start=1))
        content = [{"type": "text", "text": "Image 1, the drawing area as printed:"}, _image(blank_png),
                   {"type": "text", "text": "Image 2, the student's work:"}, _image(png),
                   {"type": "text", "text": (f"Question {item.q}: {item.prompt}\nWhat's printed: {item.diagram}\n"
                                             f"Checklist:\n{checklist}")}]
        data, usage = self._call("mark_drawing", content, DRAW_SCHEMA)
        return DrawMark.model_validate(data), usage

    def summarize(self, boxes: list[BoxResult]) -> tuple[PageSummary, Usage]:
        lines = []
        for b in boxes:
            item = self.key.item(b.q)
            lines.append(f"Question {b.q} ({b.type}): {item.prompt}\nStudent's answer: {b.transcription!r}\n"
                         f"Verdict: {b.verdict}\nComment beside it: {b.comment}")
        data, usage = self._call("page_summary", [{"type": "text", "text": "\n\n".join(lines)}], SUMMARY_SCHEMA)
        return PageSummary.model_validate(data), usage


class MockMarker:
    """Stand-in that calls no model, for testing the pipeline without an API key."""

    model, effort = "mock", "none"

    def mark_box(self, item: KeyItem, png: bytes) -> tuple[BoxMark, Usage]:
        return BoxMark(
            transcription="(mock: no model was called)", verdict="partial",
            comment=f"Mock comment for question {item.q}.",
            # A low score on question 2 exercises the review step.
            confidence=0.6 if item.q == 2 else 0.9,
        ), Usage()

    def read_choice(self, item: KeyItem, png: bytes) -> tuple[ChoiceRead, Usage]:
        return ChoiceRead(selected=[item.answer], confidence=0.9), Usage()

    def mark_labels(self, item: KeyItem, blank_png: bytes, png: bytes) -> tuple[LabelMark, Usage]:
        reads = [{"n": s.n, "transcription": "(mock)", "verdict": "correct", "confidence": 0.9} for s in item.labels]
        return LabelMark.model_validate({"labels": reads, "comment": "Mock label comment.", "confidence": 0.9}), Usage()

    def mark_drawing(self, item: KeyItem, blank_png: bytes, png: bytes) -> tuple[DrawMark, Usage]:
        checks = [{"n": n, "met": "yes"} for n in range(1, len(item.checklist) + 1)]
        return DrawMark.model_validate({"description": "(mock)", "items": checks,
                                        "comment": "Mock drawing comment.", "confidence": 0.9}), Usage()

    def summarize(self, boxes: list[BoxResult]) -> tuple[PageSummary, Usage]:
        return PageSummary(strength="Mock strength: no model was called.",
                           fixes=["Mock next step one.", "Mock next step two."]), Usage()


def usage_of(response) -> Usage:
    u = response.usage
    usage = Usage(
        input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )
    p_in, p_out, p_read, p_write = PRICES.get(response.model, PRICES[DEFAULT_MODEL])
    usage.cost_usd = (usage.input_tokens * p_in + usage.output_tokens * p_out
                      + usage.cache_read_input_tokens * p_read + usage.cache_creation_input_tokens * p_write) / 1e6
    return usage


# --- Turning marks into results ------------------------------------------------

def _result(box: Box, crop: str, threshold: float, *, transcription: str, verdict: str, comment: str,
            confidence: float, points: float | None = None, reasons: list[str] | None = None,
            details: list[dict] | None = None, uncertain_words: list[str] | None = None,
            key_ambiguous: bool = False) -> BoxResult:
    confidence = min(max(confidence, 0.0), 1.0)
    reasons = list(reasons or [])
    if verdict == "unreadable" and "unreadable" not in reasons:
        reasons.append("unreadable")
    if confidence < threshold:
        reasons.append(f"confidence {confidence:.2f}")
    if key_ambiguous:
        reasons.append("the key doesn't settle this answer")
    return BoxResult(
        transcription=transcription, uncertain_words=uncertain_words or [], verdict=verdict, comment=comment,
        confidence=confidence, key_ambiguous=key_ambiguous, q=box.q, type=box.type, points_possible=box.points,
        points_awarded=points_for(verdict, box.points) if points is None else points,
        flagged=bool(reasons), flag_reasons=reasons, crop=crop, details=details or [],
    )


def _graded(earned: float, possible: int) -> str:
    return "correct" if earned >= possible else "incorrect" if earned == 0 else "partial"


def blank_result(box: Box, crop: str, threshold: float) -> BoxResult:
    comment = "No answer circled." if box.type == "choice" else "No answer yet."
    return _result(box, crop, threshold, transcription="", verdict="blank", comment=comment, confidence=1.0)


def short_result(box: Box, mark: BoxMark, crop: str, threshold: float) -> BoxResult:
    return _result(box, crop, threshold, transcription=mark.transcription, verdict=mark.verdict,
                   comment=mark.comment, confidence=mark.confidence, uncertain_words=mark.uncertain_words,
                   key_ambiguous=mark.key_ambiguous)


def choice_result(box: Box, item: KeyItem, selected: list[str], source: str, crop: str, threshold: float,
                  confidence: float = 1.0, crossed: list[str] = (), ink: list[int] = ()) -> BoxResult:
    details = [{"selected": "+".join(selected) or None, "answer": item.answer, "source": source,
                "crossed_out": list(crossed), "ink": list(ink)}]
    if not selected:
        r = blank_result(box, crop, threshold)
        r.details = details
        return r
    if len(selected) > 1:
        return _result(box, crop, threshold, transcription=f"marked {' and '.join(selected)}", verdict="unreadable",
                       comment="", confidence=confidence, reasons=["more than one answer marked"], details=details)
    letter = selected[0]
    option = next((o for o in item.options if o.letter == letter), None)
    crossed_note = f" (crossed out {', '.join(crossed)})" if crossed else ""
    return _result(box, crop, threshold, transcription=f"circled {letter}{crossed_note}",
                   verdict="correct" if letter == item.answer else "incorrect",
                   comment=option.why if option else "", confidence=confidence, details=details)


def label_result(box: Box, item: KeyItem, mark: LabelMark, crop: str, threshold: float) -> BoxResult:
    reads = {r.n: r for r in mark.labels}
    details, reasons, earned = [], [], 0.0
    confidence = mark.confidence
    for spot in item.labels:
        read = reads.get(spot.n)
        if read is None:
            reasons.append(f"label {spot.n} wasn't read")
            details.append({"n": spot.n, "read": "", "verdict": "unreadable", "answer": spot.answer})
            continue
        confidence = min(confidence, read.confidence)
        if read.verdict == "unreadable":
            reasons.append(f"label {spot.n} unreadable")
        earned += spot.points if read.verdict == "correct" else 0
        details.append({"n": spot.n, "read": read.transcription, "verdict": read.verdict, "answer": spot.answer})
    verdict = "blank" if all(d["verdict"] == "blank" for d in details) else _graded(earned, box.points)
    return _result(box, crop, threshold, transcription="; ".join(f"{d['n']}: {d['read']}" for d in details),
                   verdict=verdict, comment=mark.comment, confidence=confidence, points=earned,
                   reasons=reasons, details=details)


def draw_result(box: Box, item: KeyItem, mark: DrawMark, crop: str, threshold: float) -> BoxResult:
    checks = {c.n: c for c in mark.items}
    details, reasons, earned = [], [], 0.0
    for n, check in enumerate(item.checklist, start=1):
        got = checks.get(n)
        met = got.met if got else "unclear"
        if met == "unclear":
            reasons.append(f"checklist item {n} unclear")
        earned += check.points if met == "yes" else 0
        details.append({"n": n, "item": check.short or check.item, "met": met, "note": got.note if got else ""})
    return _result(box, crop, threshold, transcription=mark.description, verdict=_graded(earned, box.points),
                   comment=mark.comment, confidence=mark.confidence, points=earned, reasons=reasons,
                   details=details)


# --- The marking run -----------------------------------------------------------

@dataclass
class Job:
    page: PageScan
    box: Box
    item: KeyItem
    crop: str
    png: bytes
    blank_png: bytes | None = None
    ink: tuple[int, ...] = ()


def _answer_ink(ink: np.ndarray, box: Box, dpi: int) -> int:
    if box.type == "label":
        return sum(int(raster.crop(ink, spot.rect, dpi).sum()) for spot in box.labels)
    inset = BOX_INSET_PT if box.type == "short" else 2.0
    return int(raster.crop(ink, box.rect, dpi, inset).sum())


def mark(workdir: Path, marker=None, threshold: float = DEFAULT_THRESHOLD, workers: int = 4,
         progress: Callable[[str], None] = lambda _: None) -> Feedback:
    workdir = Path(workdir)
    ingested = load(IngestResult, workdir / "ingest.json")
    layout, key = load_assignment(Path(ingested.assignment_dir))
    marker = marker or ClaudeMarker(key)
    dpi = ingested.dpi
    (workdir / "crops").mkdir(exist_ok=True)

    jobs: list[Job] = []
    results: dict[tuple[int, int], tuple[BoxResult, Usage]] = {}
    pages = [p for p in ingested.pages if p.status == "ok"]
    for page in pages:
        canonical = cv2.imread(str(workdir / page.image), cv2.IMREAD_GRAYSCALE)
        blank_page = raster.load_template(ingested.assignment_dir, page.page)
        ink = raster.student_ink(canonical, blank_page)
        for box in layout.page(page.page).boxes:
            item = key.item(box.q)
            inset = BOX_INSET_PT if box.type == "short" else 0.0
            crop = raster.crop(canonical, box.rect, dpi, inset)
            crop_path = workdir / "crops" / f"{page.student_id}-p{page.page}-q{box.q}.png"
            cv2.imwrite(str(crop_path), crop)
            rel = str(crop_path.relative_to(workdir))
            where = (page.scan_index, box.q)

            if box.type == "choice":
                letter, how, counts = read_choice(ink, box, dpi)
                if how != "ambiguous":
                    results[where] = (choice_result(box, item, [letter] if letter else [], "scan", rel, threshold,
                                                    ink=counts), Usage())
                else:
                    jobs.append(Job(page, box, item, rel, _png(crop), ink=tuple(counts)))
            elif _answer_ink(ink, box, dpi) < MIN_INK_PX:
                results[where] = (blank_result(box, rel, threshold), Usage())
            else:
                blank_png = _png(raster.crop(blank_page, box.rect, dpi)) if box.type in ("label", "draw") else None
                jobs.append(Job(page, box, item, rel, _png(crop), blank_png))
    progress(f"{len(pages)} pages, {len(jobs) + len(results)} questions "
             f"({len(results)} settled from the scan, {len(jobs)} sent to the model)")

    def run(job: Job):
        where = (job.page.scan_index, job.box.q)
        try:
            if job.box.type == "short":
                m, usage = marker.mark_box(job.item, job.png)
                return where, (short_result(job.box, m, job.crop, threshold), usage)
            if job.box.type == "choice":
                r, usage = marker.read_choice(job.item, job.png)
                return where, (choice_result(job.box, job.item, r.selected, "model", job.crop, threshold,
                                             r.confidence, r.crossed_out, list(job.ink)), usage)
            if job.box.type == "label":
                m, usage = marker.mark_labels(job.item, job.blank_png, job.png)
                return where, (label_result(job.box, job.item, m, job.crop, threshold), usage)
            m, usage = marker.mark_drawing(job.item, job.blank_png, job.png)
            return where, (draw_result(job.box, job.item, m, job.crop, threshold), usage)
        except RECOVERABLE as e:
            if isinstance(e, FATAL):
                raise
            failed = _result(job.box, job.crop, threshold, transcription="", verdict="unreadable", comment="",
                             confidence=0.0, reasons=[f"not marked: {e}"])
            return where, (failed, Usage())

    if jobs:
        # The first call runs alone so a missing or bad key fails once, not thirty times.
        done = [run(jobs[0])]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for n, item in enumerate(pool.map(run, jobs[1:]), start=2):
                done.append(item)
                if n % 5 == 0 or n == len(jobs):
                    progress(f"marked {n}/{len(jobs)}")
        results.update(done)

    def page_feedback(page: PageScan) -> PageFeedback:
        boxes, usage = [], Usage()
        for box in layout.page(page.page).boxes:
            result, u = results[(page.scan_index, box.q)]
            boxes.append(result)
            usage.add(u)
        if all(b.verdict == "blank" for b in boxes):
            summary = PageSummary(strength="", fixes=["Answer each question on the page."])
        else:
            try:
                summary, u = marker.summarize(boxes)
                summary.fixes = summary.fixes[:2]
                usage.add(u)
            except RECOVERABLE as e:
                if isinstance(e, FATAL):
                    raise
                summary = PageSummary(strength="", fixes=[])
                progress(f"summary failed for student {page.student_id} page {page.page}: {e}")
        return PageFeedback(scan_index=page.scan_index, student_id=page.student_id, page=page.page,
                            boxes=boxes, summary=summary, usage=usage)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        page_results = list(pool.map(page_feedback, pages))

    feedback = Feedback(assignment_id=layout.assignment_id, model=marker.model, effort=marker.effort,
                        threshold=threshold, pages=page_results)
    for p in page_results:
        feedback.totals.add(p.usage)
    save(feedback, workdir / "feedback.json")
    return feedback


def cost_report(feedback: Feedback) -> str:
    lines = [f"{'student':<8} {'page':>4} {'in tok':>7} {'cached':>7} {'out tok':>7} {'cost':>8}"]
    for p in sorted(feedback.pages, key=lambda p: (p.student_id, p.page)):
        u = p.usage
        cached = u.cache_read_input_tokens + u.cache_creation_input_tokens
        lines.append(f"{p.student_id:<8} {p.page:>4} {u.input_tokens:>7} {cached:>7} {u.output_tokens:>7} "
                     f"${u.cost_usd:>7.4f}")
    t, n = feedback.totals, max(len(feedback.pages), 1)
    flagged = sum(b.flagged for p in feedback.pages for b in p.boxes)
    boxes = sum(len(p.boxes) for p in feedback.pages)
    lines.append(f"total ${t.cost_usd:.4f} for {len(feedback.pages)} pages = ${t.cost_usd / n:.4f}/page "
                 f"({feedback.model}, effort {feedback.effort})")
    lines.append(f"flagged for review: {flagged} of {boxes} questions ({flagged / max(boxes, 1):.0%})")
    return "\n".join(lines)
