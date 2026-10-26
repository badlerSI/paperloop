"""Review: show the teacher only flagged items before anything prints.

Flagged means low confidence, unreadable, an ambiguous key, or a box the model
couldn't mark. Pages ingest couldn't route are listed too; they go to the
review pile instead of being guessed at.
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .mark import points_for
from .schemas import BoxResult, Feedback, IngestResult, PageFeedback, load, save

VERDICTS = ["correct", "partial", "incorrect", "blank", "unreadable"]


def pending(feedback: Feedback) -> list[tuple[PageFeedback, BoxResult]]:
    return [(p, b) for p in sorted(feedback.pages, key=lambda p: (p.student_id, p.page))
            for b in p.boxes if b.flagged and not b.reviewed]


def write_review_html(workdir: Path, feedback: Feedback, ingested: IngestResult) -> Path:
    """One page listing every flagged box with its crop, plus pages that couldn't be routed."""
    workdir = Path(workdir)
    rows = []
    for page, box in [(p, b) for p in feedback.pages for b in p.boxes if b.flagged]:
        state = "reviewed" if box.reviewed else "needs review"
        rows.append(
            f"<section><h2>Student {page.student_id}, page {page.page}, question {box.q} "
            f"<small>({state})</small></h2><img src='{html.escape(box.crop)}'>"
            f"<p><b>Why flagged:</b> {html.escape('; '.join(box.flag_reasons))}</p>"
            f"<p><b>Read as:</b> {html.escape(box.transcription)!s}"
            f"{' (unsure: ' + html.escape(', '.join(box.uncertain_words)) + ')' if box.uncertain_words else ''}</p>"
            f"<p><b>Verdict:</b> {box.verdict} ({box.points_awarded:g}/{box.points_possible})"
            f" &middot; <b>Comment:</b> {html.escape(box.comment)}</p></section>"
        )
    for p in ingested.pages:
        if p.status == "review":
            rows.append(f"<section><h2>Scan page {p.scan_index}: not routed</h2>"
                        f"<p>{html.escape(p.reason or '')}</p><img src='{html.escape(p.raw_image or '')}'></section>")
    body = "\n".join(rows) or "<p>Nothing needs review.</p>"
    out = workdir / "review.html"
    out.write_text(
        "<!doctype html><meta charset='utf-8'><title>Paper Loop review</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em}"
        "img{max-width:100%;border:1px solid #ccc}section{border-bottom:1px solid #ddd;padding:1em 0}"
        "h2{font-size:1.1em}</style>"
        f"<h1>Review: {html.escape(feedback.assignment_id)}</h1>{body}"
    )
    return out


def review(workdir: Path, accept_all: bool = False, ask: Callable[[str], str] = input,
           say: Callable[[str], None] = print) -> int:
    """Walk the teacher through flagged boxes. Returns how many are still unreviewed."""
    workdir = Path(workdir)
    feedback = load(Feedback, workdir / "feedback.json")
    ingested = load(IngestResult, workdir / "ingest.json")
    html_path = write_review_html(workdir, feedback, ingested)
    unrouted = [p for p in ingested.pages if p.status == "review"]
    if unrouted:
        say(f"{len(unrouted)} scanned pages couldn't be routed and will print in the review pile:")
        for p in unrouted:
            say(f"  scan page {p.scan_index}: {p.reason}")

    items = pending(feedback)
    if not items:
        say("No flagged answers to review.")
        return 0
    say(f"{len(items)} flagged answers. Crops and details: {html_path}")
    if accept_all:
        for _, box in items:
            box.reviewed = True
        save(feedback, workdir / "feedback.json")
        say("Accepted all flagged answers as marked.")
        return 0

    for n, (page, box) in enumerate(items, start=1):
        while True:
            say("")
            say(f"[{n}/{len(items)}] Student {page.student_id}, page {page.page}, question {box.q}"
                f"  ({'; '.join(box.flag_reasons)})")
            say(f"  read as:  {box.transcription!r}"
                + (f"  unsure: {', '.join(box.uncertain_words)}" if box.uncertain_words else ""))
            say(f"  verdict:  {box.verdict} ({box.points_awarded:g}/{box.points_possible})")
            for d in box.details:
                if box.type == "label":
                    say(f"    label {d['n']}: {d['read']!r} -> {d['verdict']} (expected {d['answer']})")
                elif box.type == "draw":
                    say(f"    item {d['n']}: {d['met']}: {d['item']}" + (f" ({d['note']})" if d.get("note") else ""))
            say(f"  comment:  {box.comment}")
            choice = ask("  [a]ccept, [e]dit comment, [v]erdict, [s]kip comment, [o]pen image, [q]uit: ")
            choice = (choice.strip().lower() or "a")[0]
            if choice == "a":
                box.reviewed = True
                break
            if choice == "e":
                box.comment = ask("  new comment: ").strip()
                box.reviewed = True
                break
            if choice == "v":
                picked = ask(f"  verdict ({'/'.join(VERDICTS)}): ").strip().lower()
                if picked in VERDICTS:
                    box.verdict = picked
                    box.points_awarded = points_for(picked, box.points_possible)
            elif choice == "s":
                box.comment = ""
                box.reviewed = True
                break
            elif choice == "o":
                _open(workdir / box.crop)
            elif choice == "q":
                save(feedback, workdir / "feedback.json")
                return len(pending(feedback))
        save(feedback, workdir / "feedback.json")
    return len(pending(feedback))


def _open(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=False)
