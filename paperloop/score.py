"""Score: compare feedback.json with known answers, using the metrics in SPEC.md's test plan.

Truth comes from `simulate` (truth.json) or from `fill-guide --truth` when the
copies were filled in by hand following the guide. Answers are described per
question type: "text" (written), "circle" (letters circled, ~~X~~ = circled
then crossed out), "labels" (by number), and "particles" (drawn per region).
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from .schemas import Feedback, IngestResult, load

COMMENT_MAX_WORDS = 15  # marking rule 4


def _circle_words(marks: list[str]) -> str:
    parts = []
    for mark in marks:
        letter = mark.strip("~")
        parts.append(f"circle {letter}, then cross it out" if mark.startswith("~~") else f"circle {letter}")
    return ", then ".join(parts)


def _particle_words(particles: dict) -> str:
    return " and ".join(
        f"{spec['count']} {'dots' if spec.get('style') == 'dot' else 'small circles'} in the {region} box"
        for region, spec in particles.items()
    )


def guide_text(roster: dict) -> str:
    """What to write on each copy, so hand-filled scans have a known answer key."""
    lines = ["Fill in one printed copy per student below, exactly like this. ~~word~~ means write it, then cross",
             "it out. Keep the misspellings: they test whether the model silently fixes them.", ""]
    for s in roster["students"]:
        lines.append(f"Copy {s['style']}: ID {s['id']} (write the digits and fill the bubbles on every page)")
        if not s["answers"]:
            lines.append("  Leave every answer empty.")
        for q, a in sorted(s["answers"].items(), key=lambda kv: int(kv[0])):
            if "text" in a:
                lines.append(f"  Q{q}: write \"{a['text']}\"")
            if "circle" in a:
                lines.append(f"  Q{q}: {_circle_words(a['circle'])}")
            if "labels" in a:
                labels = ", ".join(f"{n}: \"{t}\"" for n, t in sorted(a["labels"].items()))
                lines.append(f"  Q{q}: label {labels}")
            if "particles" in a:
                lines.append(f"  Q{q}: draw {_particle_words(a['particles'])}, spread evenly")
        lines.append("")
    return "\n".join(lines)


def guide_truth(roster: dict) -> dict:
    return {"assignment_id": roster.get("assignment_id"), "students": roster["students"]}


def _words(text: str) -> list[str]:
    text = re.sub(r"~~[^~]+~~", " ", text)  # truth: struck-through words aren't part of the answer
    text = re.sub(r"\[crossed out:[^\]]*\]", " ", text, flags=re.I)  # model's notation for the same
    return re.findall(r"[a-z0-9/]+", text.lower())


def _truth_text(answer: dict) -> str | None:
    if "text" in answer:
        return answer["text"]
    if "labels" in answer:
        return "; ".join(f"{n}: {t}" for n, t in sorted(answer["labels"].items(), key=lambda kv: int(kv[0])))
    return None


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

    autocorrected, false_correct, mismatched, long_comments, choice_misreads = [], [], [], [], []
    misspellings = judged = matched_words = total_words = choices = choices_by_model = 0
    items_agree = items_total = 0
    for page in feedback.pages:
        for box in page.boxes:
            where = f"{page.student_id} Q{box.q}"
            if len(box.comment.split()) > COMMENT_MAX_WORDS:
                long_comments.append(f"{where} ({len(box.comment.split())} words)")
            answer = answers.get((page.student_id, box.q))
            if answer is None:
                continue
            judged += 1
            if box.verdict != answer["expected"]:
                mismatched.append(f"{where}: {box.verdict}, expected {answer['expected']}")
            if box.verdict == "correct" and answer["expected"] == "incorrect":
                false_correct.append(where)

            if "circle" in answer:
                choices += 1
                kept = [mark for mark in answer["circle"] if not mark.startswith("~~")]
                read = box.details[0].get("selected") if box.details else None
                choices_by_model += bool(box.details and box.details[0].get("source") == "model")
                if read != (kept[-1] if kept else None):
                    choice_misreads.append(f"{where}: read {read}, circled {kept[-1] if kept else 'nothing'}")

            truth_text = _truth_text(answer)
            if truth_text is not None:
                read_words = _words(box.transcription)
                for word in answer.get("misspellings", []):
                    misspellings += 1
                    if word.lower() not in read_words:
                        autocorrected.append(f"{where} '{word}' read as {box.transcription!r}")
                want = _words(truth_text)
                sm = difflib.SequenceMatcher(a=want, b=read_words, autojunk=False)
                matched_words += sum(block.size for block in sm.get_matching_blocks())
                total_words += len(want)

            if "expected_items" in answer:
                got = {str(d.get("n")): d.get("met") for d in box.details}
                for n, met in answer["expected_items"].items():
                    items_total += 1
                    items_agree += got.get(n) == met

    boxes = [b for p in feedback.pages for b in p.boxes]
    answered = [b for b in boxes if b.verdict != "blank"]
    m.update(
        misspellings=misspellings, autocorrected=autocorrected, false_correct=false_correct,
        judged=judged, verdict_mismatches=mismatched,
        words_matched=matched_words, words_total=total_words,
        choices=choices, choices_by_model=choices_by_model, choice_misreads=choice_misreads,
        items_agree=items_agree, items_total=items_total,
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
    ]
    if m["choices"]:
        lines.append(f"Circled answers read right: {m['choices'] - len(m['choice_misreads'])}/{m['choices']} "
                     f"({m['choices_by_model']} needed the model)")
        lines += [f"  {c}" for c in m["choice_misreads"]]
    if m["items_total"]:
        lines.append(f"Drawing checklist items matching expected: {m['items_agree']}/{m['items_total']}")
    lines += [
        f"Flag rate: {m['flagged']}/{m['boxes']} boxes ({m['flagged'] / max(m['boxes'], 1):.0%}, target under 15%)",
        f"Comments over {COMMENT_MAX_WORDS} words: {len(m['long_comments'])}/{m['answered']}",
        f"Cost: ${m['cost_usd']:.4f} total, ${m['cost_usd'] / pages:.4f}/page "
        f"({m['model']}, effort {m['effort']}; target under $0.03/page)",
    ]
    return "\n".join(lines)


def score(workdir: Path, truth_path: Path) -> str:
    return report(metrics(workdir, json.loads(Path(truth_path).read_text())))
