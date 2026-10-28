"""Scanned class set -> lined-up pages, ID strips, and answer crops for Claude to mark.

Writes manifest.json in the work folder. Nothing here guesses: a page that can't be lined up,
identified, or matched to a student goes to the review pile with the reason.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import scan as L
from . import script as SC
from . import sheet as S

PAGE_MATCH_MIN = 0.75  # pages without a page code must look this much like the template
ID_MIN_INK_PX = 80  # student ink in the ID boxes below this means nothing was written
ID_CONFIDENCE = 0.9  # a misread ID hands one student's work to another
# With a roster, a lower bar is enough when no one-digit slip could reach this ID: on real handwriting
# Claude's confidence sits at 0.6-0.9 even for reads that are right.
ID_CONFIDENCE_ON_ROSTER = 0.5
MIN_INK_PX = 60  # student-ink pixels below which an answer counts as empty
BOX_INSET_PT = 2.0  # crop short answers just inside the printed border
BELOW_PT = 14.0  # and this far below it: a last line written under the box still shows
EMPTY_INSET_PT = 4.0  # the empty-answer check stays clear of the printed border
MIN_MARK_PX = 150  # a circle around an option leaves at least this much ink in its row
OUTSIDE_INK_PX = 300  # this much student ink outside a question's answer areas is worth a look
SCRIBBLE_PX = 1500  # far more ink than a circle: a scribble or a cross-out, so Claude looks


BOXES = {"label", "blanks", "match", "table"}  # answers written in numbered boxes, read one box at a time


def answer_ink(ink: np.ndarray, box: dict) -> int:
    rects = [spot["rect"] for spot in box["labels"]] if box["type"] in BOXES else [box["rect"]]
    return sum(int(L.crop(ink, rect, EMPTY_INSET_PT).sum()) for rect in rects)


def outside_ink(ink: np.ndarray, box: dict) -> tuple[int, tuple]:
    """Student ink in the question's block (prompt to bottom, left margin to the right edge of the comment column)
    but outside its answer areas: an answer written beside the box, in the empty column where comments print
    later, or a correction moved outside it. Returns (pixels, block rect)."""
    block = (S.LEFT - S.OPTION_REACH, box["rect"][1] - BELOW_PT, S.GUTTER_RIGHT + 8, box["feedback_rect"][3])
    left, top, right, bottom = S.rect_to_px(block)
    h, w = ink.shape
    region = ink[max(top, 0):min(bottom, h), max(left, 0):min(right, w)].copy()
    areas = [spot["rect"] for spot in box["labels"]] if box["type"] in BOXES else [box["rect"]]
    if box.get("answer_rect"):
        areas.append(box["answer_rect"])
    for rect in areas:
        x0, y0, x1, y1 = S.rect_to_px((rect[0] - 3, rect[1] - 3, rect[2] + 3, rect[3] + 3))
        region[max(y0 - top, 0):max(y1 - top, 0), max(x0 - left, 0):max(x1 - left, 0)] = False
    return int(region.sum()), block


def read_choice(ink: np.ndarray, box: dict) -> tuple[str | None, str, list[int]]:
    """From the scan alone: (letter, "scan", ink per option), (None, "blank", ...), or (None, "ambiguous", ...)."""
    counts = [int(L.crop(ink, o["rect"]).sum()) for o in box["options"]]
    order = sorted(range(len(counts)), key=counts.__getitem__, reverse=True)
    best = counts[order[0]]
    runner_up = counts[order[1]] if len(order) > 1 else 0
    if best < MIN_MARK_PX:
        return None, "blank", counts
    if runner_up >= MIN_MARK_PX or best >= SCRIBBLE_PX:
        return None, "ambiguous", counts  # two marked options (a changed answer), or one scribbled over
    return box["options"][order[0]]["letter"], "scan", counts


def _identify(canonical: np.ndarray, layout: dict, assignment_dir: Path) -> tuple[int | None, str]:
    """(page number, "code" or "match") or (None, why not). The page code says it outright; older
    sheets (QR code, no page code) are matched against each page of the assignment instead."""
    code = L.read_code(canonical)
    if code is not None:
        digest, page_no = code
        forms = layout.get("forms") or [{"id": "", "code_id": layout["assignment_id"]}]
        form = next((f for f in forms if S.assignment_hash(f["code_id"]) == digest), None)
        if form is None:
            return None, "page belongs to a different assignment"
        page = next((p for p in layout["pages"] if p.get("form", "") == form["id"]
                     and p.get("form_page", p["page"]) == page_no), None)
        if page is None:
            return None, f"{layout['assignment_id']} has no page {page_no}" + (f" in form {form['label']}" if form["id"] else "")
        return page["page"], "code"
    if len(layout.get("forms") or []) > 1:  # copies look alike: only the code can say which one this is
        return None, ("the page code in the top-left corner can't be read, and this worksheet has several "
                      "versions or copies: sort it by hand (the copy's form is in the footer)")
    scores = {}
    for p in S.form_pages(layout):
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
        for gray in L.load_pages(Path(pdf)):
            index += 1
            pages.append(_prepare_page(index, gray, layout, assignment_dir, work))

    # Blank template crops, so Claude can tell printing from student marks on labels and drawings: the
    # base form's, and those of any other form in this scan (named blank-qN-<form>.png).
    scanned = {p["page"] for p in pages if p.get("page")}
    forms_seen = {""} | {p.get("form", "") for p in layout["pages"] if p["page"] in scanned}
    for p in layout["pages"]:
        if p.get("form", "") not in forms_seen:
            continue
        blank = None
        for box in p["boxes"]:
            if box["type"] in ("label", "draw", "table") and box.get("part", 1) == 1:
                blank = L.template(assignment_dir, p["page"]) if blank is None else blank
                suffix = f"-{p['form']}" if p.get("form") else ""
                L.save_png(L.crop(blank, box["rect"]), work / "crops" / f"blank-q{box['q']}{suffix}.png")

    sheets = id_sheets(pages, work)
    manifest = {"assignment_dir": str(assignment_dir), "assignment_id": layout["assignment_id"],
                "id_sheets": sheets,
                "title": layout["title"], "subject": key["subject"], "grade_band": key["grade_band"],
                "grade": key.get("grade"),
                "dpi": S.DPI, "source_pdfs": [str(Path(p).resolve()) for p in scan_pdfs], "pages": pages}
    S.write_json(work / "manifest.json", manifest)
    return manifest


ID_SHEET_ROWS, ID_SHEET_COLS = 10, 2


def id_sheets(pages: list[dict], work: Path) -> list[str]:
    """Contact sheets of the ID strips, each labeled with its scan number: a class's IDs in a few images
    instead of one image per student."""
    from PIL import Image, ImageDraw, ImageFont
    strips = [(p["scan_index"], L.load_png(work / p["id_image"])) for p in pages if p.get("id_image")]
    if not strips:
        return []
    w = max(s.shape[1] for _, s in strips)
    h = max(s.shape[0] for _, s in strips)
    label_w, pad = 130, 14
    try:
        font = ImageFont.load_default(34)
    except TypeError:  # Pillow before 10.1
        font = ImageFont.load_default()
    out, per = [], ID_SHEET_ROWS * ID_SHEET_COLS
    for k in range(0, len(strips), per):
        chunk = strips[k:k + per]
        rows = min(ID_SHEET_ROWS, len(chunk))
        cols = (len(chunk) + rows - 1) // rows
        sheet = Image.new("L", (cols * (label_w + w + pad), rows * (h + pad)), 255)
        draw = ImageDraw.Draw(sheet)
        for i, (scan, strip) in enumerate(chunk):
            col, row = divmod(i, rows)
            x, y = col * (label_w + w + pad), row * (h + pad)
            draw.text((x + 6, y + h // 2 - 18), f"scan {scan}", fill=0, font=font)
            sheet.paste(Image.fromarray(strip), (x + label_w, y))
        path = f"ids/sheet-{k // per + 1}.png"
        sheet.save(work / path)
        out.append(path)
    return out


def _prepare_page(index: int, gray: np.ndarray, layout: dict, assignment_dir: Path, work: Path) -> dict:
    page = {"scan_index": index, "status": "review", "reason": None, "assignment_id": None, "page": None,
            "student_id": None, "image": None, "raw_image": None, "id_image": None, "answers": {}}
    markers = L.find_markers(gray)
    if len(markers) < 3:
        if L.looks_blank(gray):
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
    page_layout = next(p for p in layout["pages"] if p["page"] == page_no)
    page.update(assignment_id=layout["assignment_id"], page=page_no, form=page_layout.get("form", ""))
    ink = L.student_ink(canonical, blank)

    boxes = page_layout["id_boxes"]
    page["id_digits"] = len(boxes)
    region = (min(b[0] for b in boxes) - 3, min(b[1] for b in boxes) - 3,
              max(b[2] for b in boxes) + 3, max(b[3] for b in boxes) + 3)
    if page_layout.get("student_id"):  # made for one student (a practice sheet): the ID is printed, not read
        page.update(status="ok", reason=None, student_id=page_layout["student_id"], id_printed=True)
    elif int(L.crop(ink, region).sum()) < ID_MIN_INK_PX:
        page["reason"] = "no ID written"
        return page
    else:
        page["id_image"] = f"ids/scan-{index:03}.png"
        L.save_png(L.crop(canonical, region), work / page["id_image"])
        page["status"], page["reason"] = "ok", "ID not read yet"

    for box in page_layout["boxes"]:
        crop = f"crops/scan-{index:03}-q{box['q']}.png"
        rect = box["rect"]
        if box["type"] in ("short", "math"):  # writing often runs past the last line: keep what's just below it
            rect = (rect[0], rect[1] - BELOW_PT, rect[2], rect[3])
        L.save_png(L.crop(canonical, rect, BOX_INSET_PT if box["type"] == "short" else 0.0), work / crop)
        answer = {"crop": crop, "status": "mark", "read": None, "ink": []}
        if box.get("part"):
            answer["part"] = box["part"]  # an essay running across pages: which page of it this is
        if box.get("answer_rect"):  # math: the final answer, cropped on its own too
            answer["answer_crop"] = f"crops/scan-{index:03}-q{box['q']}-answer.png"
            close = L.crop(canonical, box["answer_rect"], -3)
            L.save_png(np.kron(close, np.ones((2, 2), np.uint8)), work / answer["answer_crop"])
        if box["type"] == "choice":
            letter, how, counts = read_choice(ink, box)
            answer.update(ink=counts, read=letter, status={"scan": "scan", "blank": "blank"}.get(how, "mark"))
        elif answer_ink(ink, box) < MIN_INK_PX:
            answer["status"] = "blank"
        outside, block = outside_ink(ink, box)
        if outside >= OUTSIDE_INK_PX:
            answer["outside_crop"] = f"crops/scan-{index:03}-q{box['q']}-whole.png"
            L.save_png(L.crop(canonical, block), work / answer["outside_crop"])
            if answer["status"] in ("blank", "scan"):
                answer["status"] = "mark"  # something beside the answer area: Claude looks at the whole question
        page["answers"][str(box["q"])] = answer
    return page


# --- IDs ------------------------------------------------------------------------------

def load_roster(path: Path | None, digits: int = 4) -> set[str] | None:
    """Valid IDs from a CSV: an "id" column, or the first column. Numbers only; never names."""
    if path is None:
        return None
    with Path(path).open(newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel's "CSV UTF-8" adds a BOM
        rows = list(csv.reader(f))
    if not rows:
        return set()
    header = [h.strip().lower() for h in rows[0]]
    col = header.index("id") if "id" in header else 0
    start = 1 if not rows[0][col].strip().isdigit() else 0
    return {r[col].strip().zfill(digits) for r in rows[start:] if len(r) > col and r[col].strip().isdigit()}


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
        n = page.get("id_digits", 4)
        if len(digits) != n or not digits.isdigit():
            page["reason"] = f"ID read as {digits or 'nothing'!r}: not {n} clear digits"
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

    forms_of: dict[str, set] = defaultdict(set)
    for p in manifest["pages"]:
        if p["status"] == "ok" and p["student_id"]:
            forms_of[p["student_id"]].add(p.get("form", ""))
    for p in manifest["pages"]:  # two different copies under one ID: a spoiled sheet, or a misread ID
        if p["status"] == "ok" and p["student_id"] and len(forms_of[p["student_id"]]) > 1:
            p["reason"] = (f"student {p['student_id']} handed in pages from more than one copy (forms "
                           f"{', '.join(sorted(f or 'A' for f in forms_of[p['student_id']]))}): keep the one they used")
            p["status"], p["student_id"] = "review", None
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
    """Routed pages of students who wrote an ID and nothing else, on every page they handed in: absent, or
    their work is elsewhere. (A blank second page from a student who did the first isn't listed.)"""
    by_student = defaultdict(list)
    for p in manifest["pages"]:
        if p["status"] == "ok" and p["student_id"]:
            by_student[p["student_id"]].append(p)
    return [p for pages in by_student.values()
            if any(not _continues_only(page) for page in pages)  # a short essay leaves its later pages blank
            and all(a["status"] == "blank" for page in pages for a in page["answers"].values())
            for p in pages]


def _continues_only(page: dict) -> bool:
    """A page that holds nothing but the rest of an essay."""
    return all(a.get("part", 1) > 1 for a in page["answers"].values())


def settled_count(manifest: dict) -> int:
    """Answers the scan settled (blank, or one clear circle), counting an essay across pages once."""
    routed = [p for p in manifest["pages"] if p["status"] == "ok" and p["student_id"]]
    essays = {(p["student_id"], q) for p in routed for q, a in p["answers"].items()
              if a.get("part") and a["status"] != "blank"}
    return sum(a["status"] != "mark" and (p["student_id"], q) not in essays
               for p in routed for q, a in p["answers"].items() if a.get("part", 1) == 1)


def blank_pages(manifest: dict) -> list[dict]:
    """Routed pages with every answer blank, from students who answered something on another page. A page
    that only continues an essay isn't listed: a short essay leaves it blank."""
    whole = {p["scan_index"] for p in all_blank(manifest)}
    routed = [p for p in manifest["pages"] if p["status"] == "ok" and p["student_id"] and p["answers"]]
    essays = {(p["student_id"], q) for p in routed for q, a in p["answers"].items()
              if a.get("part") and a["status"] != "blank"}  # an essay with writing on any of its pages

    def empty(p: dict, q: str, a: dict) -> bool:
        return a["status"] == "blank" and (a.get("part", 1) > 1 or (p["student_id"], q) not in essays)

    return [p for p in routed if p["scan_index"] not in whole and not _continues_only(p)
            and all(empty(p, q, a) for q, a in p["answers"].items())]


# --- The marking work order ------------------------------------------------------------

_BOXES_SHAPE = ('{"labels": [{"n": 1, "transcription": "...", "verdict": "correct|incorrect|blank|unreadable", '
                '"confidence": <0 to 1>}], "comment": "...", "confidence": <0 to 1>, "key_ambiguous": false, '
                '"note": "(optional)"}')
SHAPES = {
    "short": '{"transcription": "...", "uncertain_words": [], "verdict": "correct|partial|incorrect|blank|unreadable", '
             '"comment": "...", "confidence": <0 to 1>, "key_ambiguous": false, "note": "(optional)"}',
    "rubric": '{"transcription": "...", "uncertain_words": [], "criteria": [{"n": 1, "level": <0 to its top level>, '
              '"alt": <optional: the other level it could be>, "note": "..."}], "comment": "...", "confidence": <0 to 1>, '
              '"key_ambiguous": false, "note": "(optional)"}',
    "choice": '{"selected": ["<letter>"], "crossed_out": [], "confidence": <0 to 1>}',
    "label": _BOXES_SHAPE, "blanks": _BOXES_SHAPE, "match": _BOXES_SHAPE, "table": _BOXES_SHAPE,
    "draw": '{"description": "...", "items": [{"n": 1, "met": "yes|no|unclear", "note": "..."}], '
            '"comment": "...", "confidence": <0 to 1>}',
    "math": '{"work": "...", "answer": "...", "uncertain_words": [], "answer_verdict": '
            '"correct|incorrect|blank|unreadable", "work_verdict": "correct|partial|incorrect|blank", '
            '"comment": "...", "confidence": <0 to 1>, "key_ambiguous": false, "note": "(optional)"}',
}
RULES = {"short": "short", "choice": "choice", "draw": "draw", "math": "math",
         "label": "boxes", "blanks": "boxes", "match": "boxes", "table": "boxes"}


def _expected(entries: list[dict], name: str) -> list[str]:
    return [f"- {name} {e['n']}" + (f" ({e['where']})" if e.get("where") else "")
            + (f" \"{e['text']}\"" if e.get("text") else "") + f": {e['answer']}"
            + (f" (also accept: {', '.join(e['accept'])})" if e.get("accept") else "") for e in entries]


_MENTIONS_TEXT = re.compile(r"\b(story|passage|text|source|article|poem|speech|excerpt|author|lines?)\b", re.I)


def _passage(key: dict, item: dict) -> list[str]:
    """The passages a question is about: the ones it names, or the only one when the prompt points at a text."""
    passages = key.get("passages", [])
    wanted = item.get("passages") or ([item["passage"]] if item.get("passage") else [])
    chosen = [p for p in passages if p["id"] in wanted]
    if not chosen and len(passages) == 1 and item["type"] != "choice" and _MENTIONS_TEXT.search(
            " ".join([item["prompt"], item.get("key", ""), item.get("notes", "")])):
        chosen = passages[:1]
    out = []
    for p in chosen:
        title = f" ({p['title']})" if p["title"] else ""
        lines = [f"{n or '':>3}  {line}" if n or line.strip() else "" for n, line in p["lines"]]
        out += [f"**The passage{title}, as printed, with its line numbers:**", "```", *lines, "```", ""]
    return out


def _key_lines(item: dict) -> list[str]:
    """What a question expects, for a work order: its key, options, expected boxes, or checklist."""
    kind = item["type"]
    lines = []
    if kind == "short":
        lines += [f"**Key:** {item['key']}"]
        if item.get("rubric"):
            lines += ["", "**Rubric** (score each criterion; level 0 is the first description):"]
            for c in item["rubric"]:
                lines.append(f"{c['n']}. {c['criterion']}")
                lines += [f"   - level {k}: {desc}" for k, desc in enumerate(c["levels"])]
    elif kind == "choice":
        lines += ["**Options:**", *[f"- {o['letter']}. {o['text']}" for o in item["options"]],
                  "", f"**Answer:** {item['answer']} (you only read what was circled; the script judges it)"]
    elif kind == "label":
        lines += [f"**Printed diagram:** {item['diagram']}"]
        if item["word_bank"]:
            lines += [f"**Word bank printed on the page:** {', '.join(item['word_bank'])}"]
        lines += ["**Expected labels:**", *_expected(item["labels"], "Box")]
    elif kind == "blanks":
        lines += ["**The text, with each numbered blank shown as [blank n]:**", "",
                  "> " + re.sub(r"\{(\d+)\}", r"[blank \1]", item["text"]).replace("\n", "\n> "), ""]
        if item["word_bank"]:
            lines += [f"**Word bank printed on the page:** {', '.join(item['word_bank'])}", ""]
        lines += ["**Expected:**", *_expected(item["labels"], "Blank")]
    elif kind == "match":
        if item.get("choices"):
            lines += ["**Choices printed on the page:**", *[f"- {c['letter']}. {c['text']}" for c in item["choices"]],
                      "", "The items print with no number of their own, top to bottom; the item numbers below are "
                          "for your file. In a comment, name an item by its words.", ""]
        else:
            lines += ["No choices are printed: the student writes a number or word in each box (an order, T/F, "
                      "and so on). The items are lettered on the page; the box numbers below are for your file.", ""]

        def printed(e: dict) -> str:  # with choices, an item prints as its words alone (sheet.py)
            return e["text"] if item.get("choices") else f"{e.get('name', e['n'])}. {e['text']}"

        lines += ["**Each item's box should hold:**",
                  *[f"- Item {e['n']} (printed as \"{printed(e)}\"): {e['answer']}"
                    + (f" (also accept: {', '.join(e['accept'])})" if e.get("accept") else "") for e in item["labels"]]]
    elif kind == "table":
        lines += ["**The table as printed** (cells to fill shown as [n]):", "",
                  "| " + " | ".join(item["columns"]) + " |", "|" + "---|" * len(item["columns"]),
                  *["| " + " | ".join(row) + " |" for row in item["rows"]], "",
                  "**Expected:**", *_expected(item["labels"], "Cell")]
    elif kind == "math":
        accept = f" (also accept: {', '.join(item['accept'])})" if item.get("accept") else ""
        units = f" {item['units']} (printed beside the box)" if item.get("units") else ""
        lines += [f"**Answer:** {item['answer']}{units}{accept}",
                  f"**What the work should show:** {item['key'] or 'any correct method'}",
                  f"**Points:** {item['answer_points']} for the answer, {item['work_points']} for the work"]
        if not item["work_points"]:  # a version's work_optional: a calculator or a scribe, as the student's plan says
            lines.append("**The work is optional here:** a right answer earns full credit with or without work. Still "
                         "judge any work shown, but when the answer is right, don't ask for the steps.")
    else:
        lines += [f"**What's printed:** {item['diagram']}", "**Checklist:**",
                  *[f"{n}. {c['item']}" for n, c in enumerate(item["checklist"], start=1)]]
        if item.get("answer"):
            accept = f" (also accept: {', '.join(item['accept'])})" if item.get("accept") else ""
            lines += ["", f"**It also has an answer box:** {item['answer']}"
                          f"{' ' + item['units'] + ' (printed beside the box)' if item.get('units') else ''}"
                          f"{accept}. Read it and judge it as in the \"math\" rules (answer, answer_verdict)."]
    return lines


_EXPECTS = ("key", "answer", "accept", "labels", "options", "checklist", "rubric", "text", "rows", "units",
            "answer_points", "work_points")  # work_optional moves the work's points to the answer


def _form_lines(base: dict, item: dict, form: dict, base_language: str, words: int) -> list[str]:
    """How a version or a student's copy printed this question differently, and what that changes for
    marking. Empty when it printed the same."""
    lines = []
    if item["prompt"] != base["prompt"]:
        lines.append(f"**Prompt as printed on these copies:** {item['prompt']}")
    for aside in item.get("asides", []):
        text = aside["text"] if isinstance(aside["text"], str) else "; ".join(aside["text"])
        label = {"example": "A worked example", "hint": "A hint", "steps": "Steps", "words": "Key words",
                 "bank": "A word bank", "translation": f"A translation ({form.get('language_name', '')})",
                 "last": "The comment this student got last time",
                 "last_other": "The comment this student got last time, on a copy with other numbers"}[aside["kind"]]
        lines.append(f"- Printed under the prompt: {label}: {text}")
    if item.get("frame"):
        lines.append("- Printed in gray on the first writing lines (a sentence starter, not the student's words): "
                     + " / ".join(item["frame"]).rstrip(".") + ". Read the student's writing as finishing it.")
    expects_differ = any(item.get(k) != base.get(k) for k in _EXPECTS)
    if expects_differ:
        lines += ["**What this copy expects:**", *_key_lines(item)]
    if item.get("notes") and item.get("notes") != base.get("notes"):
        lines.append(f"**Notes for marking this copy:** {item['notes']}")
    language = form.get("comment_language") or base_language
    if form.get("language"):
        lines.append(f"- Students with these copies may answer in {form.get('language_english') or form['language']} "
                     "or English: mark what they mean. Spelling counts only where the key says it does.")
    if language != base_language:
        each = " in each language" if len(SC.comment_languages(language)) > 1 else ""
        lines.append(f"- Comments for these students: in {language}, {words} words at most{each}.")
    return lines


def scanned_items(manifest: dict, key: dict, layout: dict) -> dict[int, dict]:
    """Every question on a routed page, by number: the worksheet's own first, then any that only some copies
    have, such as the stretch questions on a full-credit student's practice sheet."""
    form_of_page = {p["page"]: p.get("form", "") for p in layout["pages"]}
    items = {item["q"]: item for item in key["items"]}
    here = {q for p in manifest["pages"] if p["status"] == "ok" and p["student_id"] for q in p["answers"]}
    for form in dict.fromkeys(form_of_page.get(p["page"], "") for p in manifest["pages"] if p.get("page")):
        for q, item in sorted(S.form_items(key, form).items()):
            items.setdefault(q, item)
    return {q: item for q, item in items.items() if str(q) in here}


def todo(work: Path) -> list[Path]:
    """One work order per question that has answers to mark, in todo/qN.md. Returns their paths."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    key = S.read_json(Path(manifest["assignment_dir"]) / "key.json")
    layout = S.read_json(Path(manifest["assignment_dir"]) / "layout.json")
    forms = key.get("forms", {})
    form_of_page = {p["page"]: p.get("form", "") for p in layout["pages"]}
    words = key.get("comment_words", 15)
    band = key["grade_band"] if re.search(r"\d", key["grade_band"]) or key.get("grade") is None \
        else f"{key['grade_band']} (grade {key['grade']})"
    subject = key["subject"]
    if subject and re.search(rf"\b{re.escape(subject.lower())}\b", band.lower()):
        subject = ""  # "10th grade chemistry" already says it
    elif subject and subject.split()[0].lower() in band.lower().split():
        band, subject = f"{band} ({subject})", ""
    style = {"hint": "point toward the fix (a step, a line, an idea) without writing the right answer",
             "answer": "comments may give the right answer"}[key.get("feedback", "hint")]
    (work / "todo").mkdir(exist_ok=True)
    for old in (work / "todo").glob("q*.md"):
        old.unlink()
    written = []
    for item in scanned_items(manifest, key, layout).values():
        q = str(item["q"])
        routed = [p for p in manifest["pages"] if p["status"] == "ok" and p["student_id"] and q in p["answers"]]
        essay = {p["page"]: b["part"] for p in layout["pages"] for b in p["boxes"] if b["q"] == item["q"] and b.get("part")}
        more = {}  # an essay across pages: the first page's scan -> every page's (scan, answer, part)
        form_of_scan = {p["scan_index"]: form_of_page.get(p["page"], "") for p in routed}
        if essay:
            by_student = defaultdict(dict)
            for p in routed:  # a form that fits the essay on one page has no parts: that page is part 1
                by_student[p["student_id"]][essay.get(p["page"], 1)] = p
            answers, settled = [], []
            for got in by_student.values():
                first = got[min(got)]  # page 1 of the answer, or the earliest one routed
                if any(page["answers"][q]["status"] == "mark" for page in got.values()):
                    answers.append((first["scan_index"], first["answers"][q]))
                    more[first["scan_index"]] = [(got[k]["scan_index"], got[k]["answers"][q], k) for k in sorted(got)]
                else:
                    settled.append(first["scan_index"])
            answers.sort(key=lambda a: a[0])
            settled.sort()
        else:
            answers = [(p["scan_index"], p["answers"][q]) for p in routed if p["answers"][q]["status"] == "mark"]
            settled = [p["scan_index"] for p in routed if p["answers"][q]["status"] != "mark"]
        if not answers:
            continue
        kind = item["type"]
        rubric = kind == "short" and item.get("rubric")
        rules = "rubric" if rubric else RULES[kind]
        title = {"short": "written answer scored on a rubric" if rubric else "short answer", "choice": "multiple choice",
                 "label": "labels on a diagram", "blanks": "fill in the blanks", "draw": "drawing",
                 "match": "matching" if item.get("choices") else "ordering or write-in boxes",
                 "table": "table to fill", "math": "math: work and an answer box"}[kind]
        language = key.get("comment_language", "English")
        each = " in each language" if len(SC.comment_languages(language)) > 1 else ""
        comments = "" if kind == "choice" else (f" Comments: {words} words at most{each}, in {language}; feedback "
                                                 f"style: {style}.")
        lines = [f"# Question {q}: {title}, {item['points']} point{'s' if item['points'] != 1 else ''}", "",
                 f"{manifest['title']}, a worksheet for {' '.join(filter(None, [band, subject]))}. "
                 f"Write `{(work / 'marks' / f'q{q}.json').resolve()}`. Rules: the \"{rules}\" section of "
                 f"references/marking-rules.md in the skill's folder.{comments}", "",
                 *_passage(key, item), f"**Prompt:** {item['prompt']}", ""]
        if key.get("instructions"):
            lines[-2:-2] = [f"**Printed at the top of the worksheet:** {key['instructions']}", ""]
        if item.get("notes"):
            lines += [f"**Notes for marking:** {item['notes']}", ""]
        if item.get("spelling"):
            lines += ["**Spelling counts on this question:** an answer is right only if it's spelled right, "
                      "accents included.", ""]
        lines += _key_lines(item)
        if item.get("varies"):
            lines += ["", "(Each student had their own copy of this question, with other numbers or another item. "
                          "The copy above is for reference: mark each scan against its own copy, listed below.)"]
        printed = work / "crops" / f"blank-q{q}.png"  # the worksheet's own; a question only some copies have has none
        if kind in ("label", "draw", "table") and printed.exists():
            lines += ["", "**The area as printed, before any student touched it** (look at it first): "
                          f"`{printed.resolve()}`"]

        # Answers from copies that printed this question differently are listed under their own heading.
        groups: dict[str, list] = defaultdict(list)
        notes: dict[str, list[str]] = {}
        for s_, a in answers:
            fid = form_of_scan.get(s_, "")
            if fid and fid in forms:
                if fid not in notes:
                    fitem = S.form_items(key, fid).get(item["q"], item)
                    notes[fid] = _form_lines(item, fitem, forms[fid], language, words)
                if notes[fid] or (forms[fid]["kind"] == "variant" and item.get("varies")):
                    groups[fid].append((s_, a))  # each student's own copy gets its own heading
                    continue
            groups[""].append((s_, a))

        def scan_line(s_, a) -> str:
            extra = ""
            own = form_of_scan.get(s_, "")
            blank = work / "crops" / f"blank-q{q}-{own}.png"
            if own and kind in ("label", "draw", "table") and blank.exists() and (s_, a) in groups.get("", []):
                extra += f"; compare with this copy as printed, `{blank.resolve()}`"
            if a.get("outside_crop"):
                extra += (f"; there's also writing outside the answer area, so look at the whole question: "
                          f"`{(work / a['outside_crop']).resolve()}`")
            if s_ in more:
                pieces = [f"then scan {s2} (page {k} of the answer{', blank' if a2['status'] == 'blank' else ''}): "
                          f"`{(work / a2['crop']).resolve()}`" for s2, a2, k in more[s_][1:]]
                missing = [k for k in range(1, max(essay.values()) + 1) if k not in {k2 for *_, k2 in more[s_]}]
                extra += "".join(f"; {piece}" for piece in pieces)
                if missing:
                    extra += f"; page{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))} of the answer isn't in the scan"
            return f"- scan {s_}: `{(work / a['crop']).resolve()}`{extra}"

        lines += ["", "**Answers to mark** (look at each crop; the scan number is the key in your file):"]
        if essay:
            parts = max(essay.values())
            lines.append(f"(This answer runs across {parts} pages. Each student's pages are listed together, in "
                         "order: read them all as one answer and write one mark, keyed by the first scan listed. "
                         "A page marked blank had no writing on it, so you needn't open it; a short essay often "
                         "stops early. In the transcription, write [page 2] where the next page starts.)")
        if settled:
            lines.append(f"(Settled from the scan, nothing for you to do: scan{'s' if len(settled) > 1 else ''} "
                         f"{', '.join(map(str, settled))}.)")
        if any(a.get("answer_crop") for _, a in answers):
            lines.append("(Each crop includes the answer box at its bottom right. If an answer is hard to read, a "
                         "2x close-up is beside the crop: same name, ending in -answer.png.)")
        lines += [scan_line(s_, a) for s_, a in groups.get("", [])]
        for fid, group in groups.items():
            if not fid:
                continue
            f = forms[fid]
            head = (f"Copy {f['label']}" + ("" if notes[fid] else " (the same as the copy above)")) \
                if f["kind"] == "variant" else f"Version {f['label']} ({f['name']}): printed differently"
            lines += ["", f"### {head}", "", *notes[fid]]
            blank = work / "crops" / f"blank-q{q}-{fid}.png"
            if kind in ("label", "draw", "table") and blank.exists():
                lines.append(f"- The area as printed on these copies: `{blank.resolve()}`")
            lines += ["", *[scan_line(s_, a) for s_, a in group]]
        shape = SHAPES["rubric" if rubric else kind]
        if kind == "draw" and item.get("answer"):
            shape = shape[:-1] + ', "answer": "...", "answer_verdict": "correct|incorrect|blank|unreadable"}'
        lines += ["", "**File shape:**", "```json", f'{{"q": {q}, "marks": {{"{answers[0][0]}": {shape}, ...}}}}',
                  "```", ""]
        path = work / "todo" / f"q{q}.md"
        path.write_text("\n".join(lines))
        written.append(path)
    return written
