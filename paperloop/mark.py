"""Mark: crop each answer box, send it to the model one region at a time, save feedback.json.

Only cropped answer boxes leave the laptop: never the header, the ID bubbles,
or the margins. Empty boxes are caught locally and never sent. Each page then
gets a text-only summary call (one strength, at most two fixes).
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import anthropic
import cv2
import numpy as np

from . import template as T
from .ingest import DARK
from .make import load_assignment
from .schemas import (
    AnswerKey, Box, BoxMark, BoxResult, Feedback, IngestResult, KeyItem, PageFeedback, PageSummary, Usage, load, save,
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

MIN_INK_PX = 60  # dark pixels left after removing specks; below this a box counts as empty
BOX_INSET_PT = 2.0  # crop just inside the printed border

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
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"strength": {"type": "string"}, "fixes": {"type": "array", "items": {"type": "string"}}},
    "required": ["strength", "fixes"],
    "additionalProperties": False,
}


class MarkError(Exception):
    """A box or page the model couldn't mark; it goes to teacher review instead."""


# Errors that would hit every call the same way: stop instead of flagging each box.
FATAL = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)
RECOVERABLE = (MarkError, anthropic.APIStatusError, anthropic.APIConnectionError, ValueError)


def _prompt(name: str, key: AnswerKey) -> str:
    text = (PROMPTS_DIR / name).read_text()
    return text.replace("{grade_band}", key.grade_band).replace("{subject}", key.subject)


def crop_box(canonical: np.ndarray, box: Box, dpi: int) -> np.ndarray:
    x0, y0, x1, y1 = box.rect
    i = BOX_INSET_PT
    left, top, right, bottom = T.rect_to_px((x0 + i, y0 + i, x1 - i, y1 - i), dpi)
    return canonical[top:bottom, left:right]


def is_blank(crop: np.ndarray) -> bool:
    ink = (crop < DARK).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return int(ink.sum()) < MIN_INK_PX


def points_for(verdict: str, possible: int) -> float:
    return {"correct": float(possible), "partial": possible / 2}.get(verdict, 0.0)


class ClaudeMarker:
    """Marks boxes and pages with the Anthropic API."""

    def __init__(self, key: AnswerKey, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT,
                 client: anthropic.Anthropic | None = None):
        self.key, self.model, self.effort = key, model, effort
        self.client = client or anthropic.Anthropic()
        self.use_fallbacks = model in FALLBACK_MODELS
        self.box_system = _prompt("mark_region.md", key)
        self.summary_system = _prompt("page_summary.md", key)

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
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
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
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(png).decode()}},
            {"type": "text", "text": f"Question {item.q} ({item.points} points): {item.prompt}\n"
                                     f"Answer key: {item.key}\n"
                                     "The image is the student's answer box for this question."},
        ]
        data, usage = self._call(self.box_system, content, BOX_SCHEMA)
        return BoxMark.model_validate(data), usage

    def summarize(self, boxes: list[BoxResult]) -> tuple[PageSummary, Usage]:
        lines = []
        for b in boxes:
            item = self.key.item(b.q)
            lines.append(f"Question {b.q}: {item.prompt}\nStudent wrote: {b.transcription!r}\n"
                         f"Verdict: {b.verdict}\nComment beside the box: {b.comment}")
        data, usage = self._call(self.summary_system, [{"type": "text", "text": "\n\n".join(lines)}], SUMMARY_SCHEMA)
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


def _box_result(box: Box, mark: BoxMark, crop: str, threshold: float) -> BoxResult:
    mark.confidence = min(max(mark.confidence, 0.0), 1.0)
    reasons = []
    if mark.verdict == "unreadable":
        reasons.append("unreadable")
    if mark.confidence < threshold:
        reasons.append(f"confidence {mark.confidence:.2f}")
    if mark.key_ambiguous:
        reasons.append("the key doesn't settle this answer")
    return BoxResult(**mark.model_dump(), q=box.q, points_possible=box.points,
                     points_awarded=points_for(mark.verdict, box.points),
                     flagged=bool(reasons), flag_reasons=reasons, crop=crop)


def mark(workdir: Path, marker=None, threshold: float = DEFAULT_THRESHOLD, workers: int = 4,
         progress: Callable[[str], None] = lambda _: None) -> Feedback:
    workdir = Path(workdir)
    ingested = load(IngestResult, workdir / "ingest.json")
    layout, key = load_assignment(Path(ingested.assignment_dir))
    marker = marker or ClaudeMarker(key)
    (workdir / "crops").mkdir(exist_ok=True)

    # One job per non-empty box; empty boxes are settled here without a model call.
    jobs, results = [], {}
    pages = [p for p in ingested.pages if p.status == "ok"]
    for page in pages:
        canonical = cv2.imread(str(workdir / page.image), cv2.IMREAD_GRAYSCALE)
        for box in layout.page(page.page).boxes:
            crop = crop_box(canonical, box, ingested.dpi)
            crop_path = workdir / "crops" / f"{page.student_id}-p{page.page}-q{box.q}.png"
            cv2.imwrite(str(crop_path), crop)
            rel = str(crop_path.relative_to(workdir))
            if is_blank(crop):
                blank = BoxMark(transcription="", verdict="blank", comment="No answer yet.", confidence=1.0)
                results[(page.scan_index, box.q)] = (_box_result(box, blank, rel, threshold), Usage())
            else:
                jobs.append((page, box, rel, cv2.imencode(".png", crop)[1].tobytes()))
    progress(f"{len(pages)} pages, {len(jobs) + len(results)} boxes ({len(results)} empty, not sent)")

    def run(job):
        page, box, rel, png = job
        try:
            box_mark, usage = marker.mark_box(key.item(box.q), png)
        except RECOVERABLE as e:
            if isinstance(e, FATAL):
                raise
            failed = BoxMark(transcription="", verdict="unreadable", comment="", confidence=0.0)
            result = _box_result(box, failed, rel, threshold)
            result.flag_reasons = [f"not marked: {e}"]
            return (page.scan_index, box.q), (result, Usage())
        return (page.scan_index, box.q), (_box_result(box, box_mark, rel, threshold), usage)

    if jobs:
        # The first call runs alone so a missing or bad key fails once, not thirty times.
        done = [run(jobs[0])]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for n, item in enumerate(pool.map(run, jobs[1:]), start=2):
                done.append(item)
                if n % 5 == 0 or n == len(jobs):
                    progress(f"marked {n}/{len(jobs)} boxes")
        results.update(done)

    def page_feedback(page) -> PageFeedback:
        boxes, usage = [], Usage()
        for box in layout.page(page.page).boxes:
            result, u = results[(page.scan_index, box.q)]
            boxes.append(result)
            usage.add(u)
        if all(b.verdict == "blank" for b in boxes):
            summary = PageSummary(strength="", fixes=["Answer each question in its box."])
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
    lines.append(f"flagged for review: {flagged} of {boxes} boxes ({flagged / max(boxes, 1):.0%})")
    return "\n".join(lines)
