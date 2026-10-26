"""Score: compare feedback.json with known answers, using the metrics in SPEC.md's test plan.

Truth comes from `simulate` (truth.json) or from `fill-guide --truth` when the
copies were filled in by hand following the guide.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from .schemas import Feedback, IngestResult, load
from .simulate import STUDENTS

COMMENT_MAX_WORDS = 15  # marking rule 4


def guide_text() -> str:
    """What to write on each of the four Day 1 copies, so the scans have a known answer key."""
    lines = ["Fill in four printed copies exactly like this. ~~word~~ means write the word, then cross it out.",
             "Keep the misspellings: they test whether the model silently fixes them.", ""]
    for s in STUDENTS:
        lines.append(f"Copy {s['style']}: ID {s['id']} (write the digits and fill the bubbles on both pages)")
        if not s["answers"]:
            lines.append("  Leave every answer box empty.")
        for q, (text, _, _) in sorted(s["answers"].items()):
            lines.append(f"  Q{q}: {text}")
        lines.append("")
    return "\n".join(lines)


def guide_truth() -> dict:
    return {"students": [
        {"id": s["id"], "style": s["style"],
         "answers": {str(q): {"text": t, "misspellings": m, "expected": e} for q, (t, m, e) in s["answers"].items()}}
        for s in STUDENTS
    ]}


def _words(text: str) -> list[str]:
    text = re.sub(r"~~[^~]+~~", " ", text)  # truth: struck-through words aren't part of the answer
    text = re.sub(r"\[crossed out:[^\]]*\]", " ", text, flags=re.I)  # model's notation for the same
    return re.findall(r"[a-z0-9/]+", text.lower())


def metrics(workdir: Path, truth: dict) -> dict:
    """Test-plan metrics for one marked work folder, plus the details behind each count."""
    workdir = Path(workdir)
    feedback = load(Feedback, workdir / "feedback.json")
    ingested = load(IngestResult, workdir / "ingest.json")
    answers = {(s["id"], int(q)): a for s in truth["students"] for q, a in s["answers"].items()}

    m: dict = {"model": feedback.model, "effort": feedback.effort}
    if "scan_pages" in truth:
        m["routed"] = sum(
            (p.status == "blank") if t.get("blank") else
            (p.status == "ok" and p.student_id == t["student_id"] and p.page == t["page"])
            for t, p in zip(truth["scan_pages"], ingested.pages)
        )
        m["scan_pages"] = len(truth["scan_pages"])
    m["students_found"] = sorted({p.student_id for p in ingested.pages if p.status == "ok"})
    m["students_expected"] = sorted(s["id"] for s in truth["students"])

    autocorrected, false_correct, mismatched, long_comments = [], [], [], []
    misspellings = judged = matched_words = total_words = 0
    for page in feedback.pages:
        for box in page.boxes:
            where = f"{page.student_id} Q{box.q}"
            if len(box.comment.split()) > COMMENT_MAX_WORDS:
                long_comments.append(f"{where} ({len(box.comment.split())} words)")
            truth_answer = answers.get((page.student_id, box.q))
            if truth_answer is None:
                continue
            judged += 1
            if box.verdict != truth_answer["expected"]:
                mismatched.append(f"{where}: {box.verdict}, expected {truth_answer['expected']}")
            if box.verdict == "correct" and truth_answer["expected"] == "incorrect":
                false_correct.append(where)
            read = _words(box.transcription)
            for word in truth_answer["misspellings"]:
                misspellings += 1
                if word.lower() not in read:
                    autocorrected.append(f"{where} '{word}' read as {box.transcription!r}")
            want = _words(truth_answer["text"])
            sm = difflib.SequenceMatcher(a=want, b=read, autojunk=False)
            matched_words += sum(block.size for block in sm.get_matching_blocks())
            total_words += len(want)

    boxes = [b for p in feedback.pages for b in p.boxes]
    answered = [b for b in boxes if b.verdict != "blank"]
    m.update(
        misspellings=misspellings, autocorrected=autocorrected, false_correct=false_correct,
        judged=judged, verdict_mismatches=mismatched,
        words_matched=matched_words, words_total=total_words,
        boxes=len(boxes), flagged=sum(b.flagged for b in boxes),
        answered=len(answered), long_comments=long_comments,
        pages=len(feedback.pages), cost_usd=feedback.totals.cost_usd,
        output_tokens=feedback.totals.output_tokens,
    )
    return m


def report(m: dict) -> str:
    pages = max(m["pages"], 1)
    lines = []
    if "routed" in m:
        lines.append(f"Page routing: {m['routed']}/{m['scan_pages']}")
    else:
        lines.append(f"Students found: {m['students_found']} (expected {m['students_expected']})")
    lines += [
        f"Silent autocorrect: {len(m['autocorrected'])} of {m['misspellings']} misspellings lost (target 0)",
        *[f"  {a}" for a in m["autocorrected"]],
        f"False 'correct' on wrong answers: {len(m['false_correct'])} (target 0) {', '.join(m['false_correct'])}".rstrip(),
        f"Verdicts matching the expected verdict: {m['judged'] - len(m['verdict_mismatches'])}/{m['judged']}",
        *[f"  {v}" for v in m["verdict_mismatches"]],
        f"Transcription accuracy: {m['words_matched']}/{m['words_total']} words "
        f"({m['words_matched'] / max(m['words_total'], 1):.0%})",
        f"Flag rate: {m['flagged']}/{m['boxes']} boxes ({m['flagged'] / max(m['boxes'], 1):.0%}, target under 15%)",
        f"Comments over {COMMENT_MAX_WORDS} words: {len(m['long_comments'])}/{m['answered']}",
        f"Cost: ${m['cost_usd']:.4f} total, ${m['cost_usd'] / pages:.4f}/page "
        f"({m['model']}, effort {m['effort']}; target under $0.03/page)",
    ]
    return "\n".join(lines)


def score(workdir: Path, truth_path: Path) -> str:
    return report(metrics(workdir, json.loads(Path(truth_path).read_text())))
