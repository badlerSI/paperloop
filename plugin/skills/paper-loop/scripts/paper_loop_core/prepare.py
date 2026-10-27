"""Scanned class set -> lined-up pages, ID strips, and answer crops for Claude to mark.

Writes manifest.json in the work folder. Nothing here guesses: a page that can't be lined up,
identified, or matched to a student goes to the review pile with the reason.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import scan as L
from . import sheet as S

BLANK_INK_FRACTION = 0.002
PAGE_MATCH_MIN = 0.75  # pages without a page code must look this much like the template
ID_MIN_INK_PX = 80  # student ink in the ID boxes below this means nothing was written
ID_CONFIDENCE = 0.9  # a misread ID hands one student's work to another
# With a roster, a lower bar is enough when no one-digit slip could reach this ID: on real handwriting
# Claude's confidence sits at 0.6-0.9 even for reads that are right.
ID_CONFIDENCE_ON_ROSTER = 0.5
MIN_INK_PX = 60  # student-ink pixels below which an answer counts as empty
BOX_INSET_PT = 2.0  # crop short answers just inside the printed border
EMPTY_INSET_PT = 4.0  # the empty-answer check stays clear of the printed border
MIN_MARK_PX = 150  # a circle around an option leaves at least this much ink in its row
MARK_AMBIGUOUS = 0.35  # a runner-up row with this share of the top row's ink means two marks


def answer_ink(ink: np.ndarray, box: dict) -> int:
    rects = [spot["rect"] for spot in box["labels"]] if box["type"] == "label" else [box["rect"]]
    return sum(int(L.crop(ink, rect, EMPTY_INSET_PT).sum()) for rect in rects)


def read_choice(ink: np.ndarray, box: dict) -> tuple[str | None, str, list[int]]:
    """From the scan alone: (letter, "scan", ink per option), (None, "blank", ...), or (None, "ambiguous", ...)."""
    counts = [int(L.crop(ink, o["rect"]).sum()) for o in box["options"]]
    order = sorted(range(len(counts)), key=counts.__getitem__, reverse=True)
    best = counts[order[0]]
    runner_up = counts[order[1]] if len(order) > 1 else 0
    if best < MIN_MARK_PX:
        return None, "blank", counts
    if runner_up >= MIN_MARK_PX and runner_up >= MARK_AMBIGUOUS * best:
        return None, "ambiguous", counts
    return box["options"][order[0]]["letter"], "scan", counts


def _identify(canonical: np.ndarray, layout: dict, assignment_dir: Path) -> tuple[int | None, str]:
    """(page number, "code" or "match") or (None, why not). The page code says it outright; older
    sheets (QR code, no page code) are matched against each page of the assignment instead."""
    code = L.read_code(canonical)
    if code is not None:
        digest, page_no = code
        if digest != S.assignment_hash(layout["assignment_id"]):
            return None, "page belongs to a different assignment"
        if page_no not in {p["page"] for p in layout["pages"]}:
            return None, f"{layout['assignment_id']} has no page {page_no}"
        return page_no, "code"
    scores = {}
    for p in layout["pages"]:
        blank = L.template(assignment_dir, p["page"])
        scores[p["page"]] = L.page_match(L.flatten(canonical, blank), blank)
    page_no = max(scores, key=scores.get)
    if scores[page_no] < PAGE_MATCH_MIN:
        return None, f"doesn't look like a page of {layout['assignment_id']} (best match {scores[page_no]:.2f})"
    return page_no, "match"


def prepare(scan_pdfs: list[Path], assignment_dir: Path, work: Path) -> dict:
    assignment_dir, work = Path(assignment_dir).resolve(), Path(work)
    layout = S.read_json(assignment_dir / "layout.json")
    key = S.read_json(assignment_dir / "key.json")
    if any(p.get("id_grid") for p in layout["pages"]):
        raise ValueError("this assignment uses ID bubbles; the skill reads handwritten ID boxes only. "
                         "Remake it with the skill's make command.")
    for sub in ("pages", "raw", "ids", "crops", "marks"):
        (work / sub).mkdir(parents=True, exist_ok=True)

    pages, index = [], 0
    for pdf in scan_pdfs:
        for gray in L.render_pdf(Path(pdf)):
            index += 1
            pages.append(_prepare_page(index, gray, layout, assignment_dir, work))

    # Blank template crops, so Claude can tell printing from student marks on labels and drawings.
    for p in layout["pages"]:
        blank = L.template(assignment_dir, p["page"])
        for box in p["boxes"]:
            if box["type"] in ("label", "draw"):
                L.save_png(L.crop(blank, box["rect"]), work / "crops" / f"blank-q{box['q']}.png")

    manifest = {"assignment_dir": str(assignment_dir), "assignment_id": layout["assignment_id"],
                "title": layout["title"], "subject": key["subject"], "grade_band": key["grade_band"],
                "dpi": S.DPI, "source_pdfs": [str(Path(p).resolve()) for p in scan_pdfs], "pages": pages}
    S.write_json(work / "manifest.json", manifest)
    return manifest


def _prepare_page(index: int, gray: np.ndarray, layout: dict, assignment_dir: Path, work: Path) -> dict:
    page = {"scan_index": index, "status": "review", "reason": None, "assignment_id": None, "page": None,
            "student_id": None, "image": None, "raw_image": None, "id_image": None, "answers": {}}
    markers = L.find_markers(gray)
    if len(markers) < 3:
        if np.mean(gray < L.DARK) < BLANK_INK_FRACTION:
            page["status"] = "blank"
            return page
        page["raw_image"] = f"raw/scan-{index:03}.png"
        L.save_png(gray, work / page["raw_image"])
        page["reason"] = f"found {len(markers)} of 4 corner squares; can't line the page up"
        return page
    canonical, error = L.register(gray, markers)
    if error > L.MAX_REPROJECTION_PX:
        page["raw_image"] = f"raw/scan-{index:03}.png"
        L.save_png(gray, work / page["raw_image"])
        page["reason"] = f"page didn't line up cleanly (error {error:.1f}px); torn or folded?"
        return page

    page_no, how = _identify(canonical, layout, assignment_dir)
    page["image"] = f"pages/scan-{index:03}.png"
    if page_no is None:
        L.save_png(canonical, work / page["image"])
        page["reason"] = how
        return page
    page["identified_by"] = how
    blank = L.template(assignment_dir, page_no)
    canonical = L.flatten(canonical, blank)
    L.save_png(canonical, work / page["image"])
    page.update(assignment_id=layout["assignment_id"], page=page_no)
    page_layout = next(p for p in layout["pages"] if p["page"] == page_no)
    ink = L.student_ink(canonical, blank)

    boxes = page_layout["id_boxes"]
    region = (min(b[0] for b in boxes) - 3, min(b[1] for b in boxes) - 3,
              max(b[2] for b in boxes) + 3, max(b[3] for b in boxes) + 3)
    if int(L.crop(ink, region).sum()) < ID_MIN_INK_PX:
        page["reason"] = "no ID written"
        return page
    page["id_image"] = f"ids/scan-{index:03}.png"
    L.save_png(L.crop(canonical, region), work / page["id_image"])
    page["status"], page["reason"] = "ok", "ID not read yet"

    for box in page_layout["boxes"]:
        crop = f"crops/scan-{index:03}-q{box['q']}.png"
        L.save_png(L.crop(canonical, box["rect"], BOX_INSET_PT if box["type"] == "short" else 0.0), work / crop)
        answer = {"crop": crop, "status": "mark", "read": None, "ink": []}
        if box["type"] == "choice":
            letter, how, counts = read_choice(ink, box)
            answer.update(ink=counts, read=letter, status={"scan": "scan", "blank": "blank"}.get(how, "mark"))
        elif answer_ink(ink, box) < MIN_INK_PX:
            answer["status"] = "blank"
        page["answers"][str(box["q"])] = answer
    return page


# --- IDs ------------------------------------------------------------------------------

def load_roster(path: Path | None) -> set[str] | None:
    """Valid IDs from a CSV: an "id" column, or the first column. Numbers only; never names."""
    if path is None:
        return None
    with Path(path).open(newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return set()
    header = [h.strip().lower() for h in rows[0]]
    col = header.index("id") if "id" in header else 0
    start = 1 if not rows[0][col].strip().isdigit() else 0
    return {r[col].strip().zfill(S.ID_DIGITS) for r in rows[start:] if len(r) > col and r[col].strip().isdigit()}


def _one_digit_apart(a: str, b: str) -> bool:
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def route(work: Path, roster: set[str] | None = None) -> dict:
    """Apply Claude's ID reads (ids.json) to the pages: route the sure ones, send the rest to review."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    reads = S.read_json(work / "ids.json")
    for page in manifest["pages"]:
        if not page.get("id_image"):
            continue  # blank, or already in the review pile for a reason an ID can't fix
        page["status"], page["student_id"], page["reason"] = "review", None, None
        read = reads.get(str(page["scan_index"]))
        if read is None:
            page["reason"] = "ID not read yet"
            continue
        digits, confidence = str(read.get("digits", "")), float(read.get("confidence", 0))
        if len(digits) != S.ID_DIGITS or not digits.isdigit():
            page["reason"] = f"ID read as {digits or 'nothing'!r}: not {S.ID_DIGITS} clear digits"
            continue
        if confidence < ID_CONFIDENCE:
            if roster is None or digits not in roster or confidence < ID_CONFIDENCE_ON_ROSTER:
                page["reason"] = f"ID read as {digits}, but only {confidence:.2f} sure"
                continue
            neighbor = next((other for other in sorted(roster) if _one_digit_apart(other, digits)), None)
            if neighbor:
                page["reason"] = (f"ID read as {digits} ({confidence:.2f} sure), but {neighbor} on the roster "
                                  "is one digit away")
                continue
        if roster is not None and digits not in roster:
            page["reason"] = f"ID {digits} isn't on the class roster"
            continue
        page["status"], page["student_id"] = "ok", digits
        page["id_confidence"], page["id_by_roster"] = confidence, confidence < ID_CONFIDENCE

    seen: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for p in manifest["pages"]:
        if p["status"] == "ok" and p["student_id"]:
            seen[(p["student_id"], p["page"])].append(p)
    for (student_id, page_no), dupes in seen.items():
        if len(dupes) > 1:
            where = ", ".join(str(p["scan_index"]) for p in dupes)
            for p in dupes:
                p["status"], p["student_id"] = "review", None
                p["reason"] = f"student {student_id} page {page_no} appears more than once (scans {where})"
    S.write_json(work / "manifest.json", manifest)
    return manifest


def all_blank(manifest: dict) -> list[dict]:
    """Routed pages where the student wrote an ID and nothing else: absent, or their work is elsewhere."""
    return [p for p in manifest["pages"] if p["status"] == "ok" and p["student_id"] and p["answers"]
            and all(a["status"] == "blank" for a in p["answers"].values())]


# --- The marking work order ------------------------------------------------------------

SHAPES = {
    "short": '{"transcription": "...", "uncertain_words": [], "verdict": "correct|partial|incorrect|blank|unreadable", '
             '"comment": "...", "confidence": <0 to 1>, "key_ambiguous": false, "note": "(optional)"}',
    "choice": '{"selected": ["<letter>"], "crossed_out": [], "confidence": <0 to 1>}',
    "label": '{"labels": [{"n": 1, "transcription": "...", "verdict": "correct|incorrect|blank|unreadable", '
             '"confidence": <0 to 1>}], "comment": "...", "confidence": <0 to 1>}',
    "draw": '{"description": "...", "items": [{"n": 1, "met": "yes|no|unclear", "note": "..."}], '
            '"comment": "...", "confidence": <0 to 1>}',
}


def todo(work: Path) -> list[Path]:
    """One work order per question that has answers to mark, in todo/qN.md. Returns their paths."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    key = S.read_json(Path(manifest["assignment_dir"]) / "key.json")
    (work / "todo").mkdir(exist_ok=True)
    for old in (work / "todo").glob("q*.md"):
        old.unlink()
    written = []
    for item in key["items"]:
        q = str(item["q"])
        answers = [(p["scan_index"], p["answers"][q]) for p in manifest["pages"]
                   if p["status"] == "ok" and p["student_id"] and q in p["answers"]
                   and p["answers"][q]["status"] == "mark"]
        if not answers:
            continue
        lines = [f"# Question {q}: {item['type']}, {item['points']} point{'s' if item['points'] != 1 else ''}",
                 "", f"{manifest['title']}, a {key['grade_band']} {key['subject']} worksheet. "
                     f"Write `{(work / 'marks' / f'q{q}.json').resolve()}`. Rules: the \"{item['type']}\" section of references/marking-rules.md "
                     "in the skill's folder.",
                 "", f"**Prompt:** {item['prompt']}", ""]
        if item["type"] == "short":
            lines += [f"**Key:** {item['key']}"]
        elif item["type"] == "choice":
            lines += ["**Options:**", *[f"- {o['letter']}. {o['text']}" for o in item["options"]],
                      "", f"**Answer:** {item['answer']} (you only read what was circled; the script judges it)"]
        elif item["type"] == "label":
            lines += [f"**Printed diagram:** {item['diagram']}"]
            if item["word_bank"]:
                lines += [f"**Word bank printed on the page:** {', '.join(item['word_bank'])}"]
            lines += ["**Expected labels:**", *[
                f"- Box {s['n']}: {s['answer']}" + (f" (also accept: {', '.join(s['accept'])})" if s["accept"] else "")
                for s in item["labels"]]]
        else:
            lines += [f"**What's printed:** {item['diagram']}", "**Checklist:**",
                      *[f"{n}. {c['item']}" for n, c in enumerate(item["checklist"], start=1)]]
        if item["type"] in ("label", "draw"):
            lines += ["", "**The area as printed, before any student touched it** (look at it first): "
                          f"`{(work / 'crops' / f'blank-q{q}.png').resolve()}`"]
        lines += ["", "**Answers to mark** (look at each crop; the scan number is the key in your file):",
                  *[f"- scan {s}: `{(work / a['crop']).resolve()}`" for s, a in answers], "",
                  "**File shape:**", "```json",
                  f'{{"q": {q}, "marks": {{"{answers[0][0]}": {SHAPES[item["type"]]}, ...}}}}', "```", ""]
        path = work / "todo" / f"q{q}.md"
        path.write_text("\n".join(lines))
        written.append(path)
    return written
