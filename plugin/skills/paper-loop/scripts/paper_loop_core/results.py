"""Claude's marks (marks/qN.json) -> checked results, flags, and the per-page summary work order.

`check` reports what's wrong with a marks file in words Claude can act on, so a bad file gets fixed
instead of rendered. Results are written in the Paper Loop CLI's feedback.json format, so the CLI's
`score` command can compare them with a known answer key (for the question types the CLI has).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from . import script as SC
from . import sheet as S

THRESHOLD = 0.8  # flag answers Claude is less sure of than this for the teacher
STRENGTH_MAX_WORDS = 20
VERDICTS = {"correct", "partial", "incorrect", "blank", "unreadable"}
BOX_VERDICTS = {"correct", "incorrect", "blank", "unreadable"}
WORK_VERDICTS = {"correct", "partial", "incorrect", "blank"}
MET = {"yes", "no", "unclear"}
BOXES = {"label", "blanks", "match", "table"}


class MarksError(ValueError):
    pass


def _points_for(verdict: str, possible: int) -> float:
    return {"correct": float(possible), "partial": possible / 2}.get(verdict, 0.0)


def _graded(earned: float, possible: int) -> str:
    return "correct" if earned >= possible else "incorrect" if earned == 0 else "partial"


def _result(box: dict, crop: str, *, transcription: str, verdict: str, comment: str, confidence: float,
            points: float | None = None, reasons: list[str] | None = None, details: list[dict] | None = None,
            uncertain_words: list[str] | None = None, key_ambiguous: bool = False, reviewed: bool = False,
            note: str = "") -> dict:
    confidence = min(max(float(confidence), 0.0), 1.0)
    reasons = list(reasons or [])
    if verdict == "unreadable" and "unreadable" not in reasons:
        reasons.append("unreadable")
    if confidence < THRESHOLD:
        reasons.append(f"confidence {confidence:.2f}")
    if key_ambiguous:
        reasons.append("the key doesn't settle this answer")
    return {"transcription": transcription, "uncertain_words": uncertain_words or [], "verdict": verdict,
            "comment": comment, "confidence": confidence, "key_ambiguous": key_ambiguous, "q": box["q"], "note": note,
            "type": box["type"], "points_possible": box["points"],
            "points_awarded": _points_for(verdict, box["points"]) if points is None else points,
            "flagged": bool(reasons), "flag_reasons": reasons, "reviewed": reviewed, "crop": crop,
            "details": details or []}


def _blank(box: dict, crop: str, said: dict | None = None) -> dict:
    """A blank answer, with the comment for it in the student's comment languages (a version's blank_comments)."""
    said = said or {}
    return _result(box, crop, transcription="", verdict="blank", confidence=1.0,
                   comment=said.get("circled", S.NO_CIRCLE) if box["type"] == "choice"
                   else said.get("answer", S.NO_ANSWER))


def _choice(box: dict, item: dict, selected: list[str], source: str, crop: str, confidence: float = 1.0,
            crossed: list[str] = (), ink: list[int] = (), reviewed: bool = False, said: dict | None = None) -> dict:
    details = [{"selected": "+".join(selected) or None, "answer": item["answer"], "source": source,
                "crossed_out": list(crossed), "ink": list(ink)}]
    bases = {o["letter"]: o.get("base", o["letter"]) for o in item["options"]}
    if len(selected) == 1 and bases.get(selected[0], selected[0]) != selected[0]:
        details[0]["base_selected"] = bases[selected[0]]  # a shuffled copy: the letter on the base copy
    if not selected:
        r = _blank(box, crop, said)
        r["details"] = details
        return r
    if len(selected) > 1:
        return _result(box, crop, transcription=f"marked {' and '.join(selected)}", verdict="unreadable",
                       comment="", confidence=confidence, reasons=["more than one answer marked"],
                       details=details, reviewed=reviewed)
    letter = selected[0]
    option = next((o for o in item["options"] if o["letter"] == letter), None)
    crossed_note = f" (crossed out {', '.join(crossed)})" if crossed else ""
    return _result(box, crop, transcription=f"circled {letter}{crossed_note}",
                   verdict="correct" if letter == item["answer"] else "incorrect",
                   comment=option["why"] if option else "", confidence=confidence, details=details,
                   reviewed=reviewed)


def _boxes(box: dict, item: dict, mark: dict, crop: str) -> dict:
    """label, blanks, match, table: one reading and verdict per numbered box."""
    reads = {int(r["n"]): r for r in mark["labels"]}
    details, reasons, earned = [], [], 0.0
    confidence = float(mark["confidence"])
    for spot in item["labels"]:
        read = reads.get(spot["n"])
        if read is None:
            reasons.append(f"box {spot['n']} wasn't read")
            details.append({"n": spot["n"], "read": "", "verdict": "unreadable", "answer": spot["answer"]})
            continue
        confidence = min(confidence, float(read["confidence"]))
        if read["verdict"] == "unreadable":
            reasons.append(f"box {spot['n']} unreadable")
        elif float(read["confidence"]) < THRESHOLD:
            reasons.append(f"box {spot['n']} uncertain")
        earned += spot["points"] if read["verdict"] == "correct" else 0
        details.append({"n": spot["n"], "read": read["transcription"], "verdict": read["verdict"],
                        "answer": spot["answer"]})
    verdict = "blank" if all(d["verdict"] == "blank" for d in details) else _graded(earned, box["points"])
    return _result(box, crop, transcription="; ".join(f"{d['n']}: {d['read']}" for d in details), verdict=verdict,
                   comment=mark["comment"], confidence=confidence, points=earned, reasons=reasons, details=details,
                   key_ambiguous=bool(mark.get("key_ambiguous")), reviewed=bool(mark.get("reviewed")),
                   note=mark.get("note", ""))


def _answered(item: dict, mark: dict) -> bool:
    """A drawing's answer box has something in it, whatever the frame holds."""
    return bool(item.get("answer")) and mark.get("answer_verdict") not in (None, "blank")


def _draw(box: dict, item: dict, mark: dict, crop: str, said: dict | None = None) -> dict:
    empty = mark.get("verdict") == "blank"  # nothing drawn in the frame
    if empty and not _answered(item, mark):
        return _result(box, crop, transcription=mark.get("description", ""), verdict="blank", confidence=1.0,
                       comment=(said or {}).get("answer", S.NO_ANSWER), reviewed=bool(mark.get("reviewed")))
    checks = {} if empty else {int(c["n"]): c for c in mark["items"]}
    details, reasons, earned = [], [], 0.0
    for n, check in enumerate(item["checklist"], start=1):
        got = checks.get(n)
        met = got["met"] if got else "no" if empty else "unclear"  # an empty frame meets no item
        if met == "unclear":
            reasons.append(f"checklist item {n} unclear")
        earned += check["points"] if met == "yes" else 0
        details.append({"n": n, "item": check["short"] or check["item"], "met": met,
                        "note": got.get("note", "") if got else ""})
    if item.get("answer"):
        verdict = mark["answer_verdict"]
        earned += item["answer_points"] if verdict == "correct" else 0
        details.append({"part": "answer", "read": mark["answer"], "verdict": verdict, "answer": item["answer"]})
        reasons += _answer_check(mark["answer"], verdict, item)
    return _result(box, crop, transcription=mark.get("description") or "nothing drawn",
                   verdict=_graded(earned, box["points"]),
                   comment=mark["comment"], confidence=mark["confidence"], points=earned, reasons=reasons,
                   details=details, reviewed=bool(mark.get("reviewed")), note=mark.get("note", ""))


def _rubric(box: dict, item: dict, mark: dict, crop: str) -> dict:
    levels = {int(c["n"]): c for c in mark["criteria"]}
    details, earned, reasons = [], 0.0, []
    for c in item["rubric"]:
        got = levels.get(c["n"], {})
        level = int(got.get("level", 0))
        earned += level
        details.append({"n": c["n"], "criterion": c["short"] or c["criterion"], "level": level, "max": c["max"],
                        "note": got.get("note", "")})
        if isinstance(got.get("alt"), int) and got["alt"] != level:
            reasons.append(f"{c['short'] or 'criterion ' + str(c['n'])} could be {got['alt']} instead of {level}")
    verdict = mark.get("verdict") if mark.get("verdict") in ("blank", "unreadable") else _graded(earned, box["points"])
    return _result(box, crop, transcription=mark["transcription"], verdict=verdict, comment=mark["comment"],
                   confidence=mark["confidence"], points=0.0 if verdict in ("blank", "unreadable") else earned,
                   uncertain_words=mark.get("uncertain_words", []), details=details, reasons=reasons,
                   key_ambiguous=bool(mark.get("key_ambiguous")), reviewed=bool(mark.get("reviewed")),
                   note=mark.get("note", ""))


_NUMBER = re.compile(r"(?<![\d.])(-?\d+)\s+(\d+)\s*/\s*(\d+)|(-?\d+)\s*/\s*(\d+)|(-?\d[\d,]*\.?\d*|-?\.\d+)(\s*%)?")


def as_number(text: str) -> Fraction | None:
    """The one number in a written answer ("3/4", "1 1/2", "0.75", "75%", "$1,200", "12 cm"), or None when
    there's no number, more than one, or an inequality (x ≥ -4 and x ≤ -4 hold the same number)."""
    if any(ch in text for ch in "<>≤≥≠"):
        return None
    found = [m for m in _NUMBER.finditer(text.replace("−", "-")) if m.group(0).strip()]
    if len(found) != 1:
        return None
    m = found[0]
    try:
        if m.group(1):
            whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return (abs(whole) + Fraction(num, den)) * (-1 if whole < 0 else 1)
        if m.group(4):
            return Fraction(int(m.group(4)), int(m.group(5)))
        value = Fraction(m.group(6).replace(",", ""))
        return value / 100 if m.group(7) else value
    except (ValueError, ZeroDivisionError):
        return None


def _unit_words(text: str) -> set[str]:
    """Units written with an answer ("3.60 mol" has mol); a variable before "=" isn't one."""
    return {w.lower() for w in re.findall(r"[A-Za-zµ°Ω]+", text.split("=")[-1])}


def _places(text: str) -> int:
    m = re.search(r"\d*\.(\d+)", text.replace(",", ""))
    return len(m.group(1)) if m else 0


def _round(value: Fraction, places: int) -> Fraction:
    scale = 10 ** places
    return Fraction(math.floor(abs(value) * scale + Fraction(1, 2)), scale) * (1 if value >= 0 else -1)


def _rounds_to(read: Fraction, key: Fraction, read_text: str, key_text: str) -> bool:
    """One is the other rounded to the decimal places it's written with. Two whole numbers never are."""
    if read.denominator == 1 and key.denominator == 1:
        return False
    return _round(key, _places(read_text)) == read or _round(read, _places(key_text)) == key


def _answer_check(read_text: str, verdict: str, item: dict) -> list[str]:
    """Flags when the number Claude read and the key disagree with Claude's verdict."""
    if verdict == "unreadable":
        return ["answer unreadable"]
    read, keys = as_number(read_text), [as_number(k) for k in [item["answer"], *item.get("accept", [])]]
    if read is None or not keys or any(k is None for k in keys):
        return []
    texts = [item["answer"], *item.get("accept", [])]
    if read not in keys and any(_rounds_to(read, k, read_text, t) for k, t in zip(keys, texts)):
        return []  # the key at another precision (0.17 for 1/6): whether precision counts is Claude's call
    if read in keys and verdict == "incorrect" and _unit_words(item["answer"]) - _unit_words(read_text):
        return []  # the right number without the units the key requires ("3.60" for "3.60 mol")
    if (read in keys) != (verdict == "correct"):
        return [f"the answer check disagrees: read {read_text!r}, key {item['answer']!r}, marked {verdict}"]
    return []


def _math(box: dict, item: dict, mark: dict, crop: str) -> dict:
    a_verdict, w_verdict = mark["answer_verdict"], mark["work_verdict"]
    earned = (item["answer_points"] if a_verdict == "correct" else 0) + \
        {"correct": item["work_points"], "partial": item["work_points"] / 2}.get(w_verdict, 0)
    reasons = _answer_check(mark["answer"], a_verdict, item)
    if a_verdict == "blank" and w_verdict == "blank":
        verdict = "blank"
    elif a_verdict == "unreadable":
        verdict = "unreadable"
    else:
        verdict = _graded(earned, box["points"])
    details = [{"part": "answer", "read": mark["answer"], "verdict": a_verdict, "answer": item["answer"]},
               {"part": "work", "verdict": w_verdict}]
    return _result(box, crop, transcription=f"work: {mark['work']} | answer: {mark['answer']}", verdict=verdict,
                   comment=mark["comment"], confidence=mark["confidence"], points=earned, reasons=reasons,
                   details=details, uncertain_words=mark.get("uncertain_words", []),
                   key_ambiguous=bool(mark.get("key_ambiguous")), reviewed=bool(mark.get("reviewed")),
                   note=mark.get("note", ""))


def _whole(value) -> int | None:
    """A box, item, or criterion number as Claude wrote it (3, or "3"); None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) or isinstance(value, float) and value.is_integer():
        return int(value)
    return int(value) if isinstance(value, str) and value.strip().isdigit() else None


def _fraction(value) -> bool:
    """A confidence: a number from 0 to 1."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _validate(kind: str, mark, where: str, item: dict) -> list[str]:
    """Problems with one mark, each phrased as what to fix."""
    if not isinstance(mark, dict):
        return [f"{where}: should be an object"]
    problems = []

    def need(field: str, types, allowed=None, obj=None, label=None):
        obj = mark if obj is None else obj
        name = label or f"\"{field}\""
        if field not in obj:
            problems.append(f"{where}: missing {name}")
        elif not isinstance(obj[field], types) or isinstance(obj[field], bool) and types != bool:
            problems.append(f"{where}: {name} has the wrong type")
        elif allowed is not None and obj[field] not in allowed:
            problems.append(f"{where}: {name} must be one of {', '.join(sorted(allowed))}")

    need("confidence", (int, float))
    if isinstance(mark.get("confidence"), (int, float)) and not 0 <= mark["confidence"] <= 1:
        problems.append(f"{where}: \"confidence\" must be between 0 and 1 (0.85, not 85)")
    if kind == "short" and item.get("rubric"):
        need("transcription", str), need("criteria", list), need("comment", str)
        got = set()
        for n, c in enumerate(mark.get("criteria", []) if isinstance(mark.get("criteria"), list) else []):
            if not isinstance(c, dict) or "n" not in c:
                problems.append(f"{where}: criteria[{n}] needs \"n\"")
                continue
            if _whole(c["n"]) is None:
                problems.append(f"{where}: criteria[{n}] \"n\" is the criterion's number, such as 1")
                continue
            got.add(_whole(c["n"]))
            top = next((r["max"] for r in item["rubric"] if r["n"] == _whole(c["n"])), None)
            if top is None:
                problems.append(f"{where}: there's no rubric criterion {c['n']}")
            elif not isinstance(c.get("level"), int) or isinstance(c.get("level"), bool) or not 0 <= c["level"] <= top:
                problems.append(f"{where}: criterion {c['n']} \"level\" must be a whole number from 0 to {top}")
            elif "alt" in c and (not isinstance(c["alt"], int) or isinstance(c["alt"], bool) or not 0 <= c["alt"] <= top):
                problems.append(f"{where}: criterion {c['n']} \"alt\" must be a whole number from 0 to {top}, or left out")
        missing = {r["n"] for r in item["rubric"]} - got
        if missing and mark.get("verdict") not in ("blank", "unreadable"):
            problems.append(f"{where}: no level for rubric criterion {', '.join(map(str, sorted(missing)))}")
    elif kind == "short":
        need("transcription", str), need("verdict", str, VERDICTS), need("comment", str)
    elif kind == "choice":
        need("selected", list)
        letters = {o["letter"] for o in item["options"]}
        marked = [m for field in ("selected", "crossed_out") if isinstance(mark.get(field), list) for m in mark[field]]
        bad = [s for s in marked if s not in letters]
        if bad:
            problems.append(f"{where}: {', '.join(map(str, bad))} isn't an option letter ({', '.join(sorted(letters))})")
    elif kind in BOXES:
        need("labels", list), need("comment", str)
        expected = {s["n"] for s in item["labels"]}
        got = set()
        for n, read in enumerate(mark.get("labels", []) if isinstance(mark.get("labels"), list) else []):
            if not isinstance(read, dict) or "n" not in read:
                problems.append(f"{where}: labels[{n}] needs \"n\"")
                continue
            if _whole(read["n"]) is None:
                problems.append(f"{where}: labels[{n}] \"n\" is the box's number, such as 1")
                continue
            got.add(_whole(read["n"]))
            for field in ("transcription", "verdict", "confidence"):
                if field not in read:
                    problems.append(f"{where}: box {read['n']} is missing \"{field}\"")
            if read.get("verdict") not in BOX_VERDICTS:
                problems.append(f"{where}: box {read['n']} verdict must be one of {', '.join(sorted(BOX_VERDICTS))}")
            if "transcription" in read and not isinstance(read["transcription"], str):
                problems.append(f"{where}: box {read['n']} \"transcription\" is text, \"\" for an empty box")
            if "confidence" in read and not _fraction(read["confidence"]):
                problems.append(f"{where}: box {read['n']} \"confidence\" must be a number between 0 and 1 "
                                "(0.85, not 85 or \"high\")")
        if expected - got:
            problems.append(f"{where}: no reading for box {', '.join(map(str, sorted(expected - got)))}")
    elif kind == "draw" and mark.get("verdict") == "blank":
        if _answered(item, mark):  # nothing drawn, but an answer in the box: that answer is marked
            need("answer", str), need("answer_verdict", str, BOX_VERDICTS), need("comment", str)
    elif kind == "draw":
        need("description", str), need("items", list), need("comment", str)
        expected = set(range(1, len(item["checklist"]) + 1))
        got = set()
        for n, check in enumerate(mark.get("items", []) if isinstance(mark.get("items"), list) else []):
            if not isinstance(check, dict) or "n" not in check:
                problems.append(f"{where}: items[{n}] needs \"n\"")
                continue
            if _whole(check["n"]) is None:
                problems.append(f"{where}: items[{n}] \"n\" is the checklist item's number, such as 1")
                continue
            got.add(_whole(check["n"]))
            if check.get("met") not in MET:
                problems.append(f"{where}: checklist item {check['n']} \"met\" must be yes, no, or unclear")
        if expected - got:
            problems.append(f"{where}: no answer for checklist item {', '.join(map(str, sorted(expected - got)))}")
        if item.get("answer"):
            need("answer", str), need("answer_verdict", str, BOX_VERDICTS)
    elif kind == "math":
        need("work", str), need("answer", str), need("comment", str)
        need("answer_verdict", str, BOX_VERDICTS), need("work_verdict", str, WORK_VERDICTS)
    return problems


def _key(work: Path) -> tuple[dict, dict, dict]:
    manifest = S.read_json(work / "manifest.json")
    layout = S.read_json(Path(manifest["assignment_dir"]) / "layout.json")
    key = S.read_json(Path(manifest["assignment_dir"]) / "key.json")
    return manifest, layout, key


def check(work: Path) -> dict:
    """Build every routed page's results from the scan and Claude's marks. Returns
    {"errors": [...], "warnings": [...], "flagged": [...], "pages": [...]}, and writes results.json."""
    work = Path(work)
    manifest, layout, key_file = _key(work)
    max_words = key_file.get("comment_words", 15)
    young = key_file.get("grade", 7) <= 3
    forms = key_file.get("forms", {})
    marks, errors, warnings = {}, [], []
    for path in sorted((work / "marks").glob("q*.json")):
        try:
            data = S.read_json(path)
        except ValueError as e:
            errors.append(f"{path.name}: not valid JSON ({e})")
            continue
        q = _whole(data.get("q", path.stem[1:])) if isinstance(data, dict) else None
        if q is None or not isinstance(data.get("marks", {}), dict):
            errors.append(f"{path.name}: should be {{\"q\": <question number>, \"marks\": {{\"<scan number>\": "
                          "{...}}}}, as the work order's file shape shows")
            continue
        marks[q] = {str(k): v for k, v in data.get("marks", {}).items()}

    routed = {(p["student_id"], p["page"]): p for p in manifest["pages"] if p["status"] == "ok" and p["student_id"]}
    essay_pages = defaultdict(list)  # an essay across pages: its page numbers in each form, in order
    for p in layout["pages"]:
        for b in p["boxes"]:
            if b.get("part"):
                essay_pages[(p.get("form", ""), b["q"])].append(p["page"])
    pages = []
    for page in manifest["pages"]:
        if page["status"] != "ok" or not page["student_id"]:
            continue
        page_layout = next(p for p in layout["pages"] if p["page"] == page["page"])
        form = page_layout.get("form", "")
        key = S.form_items(key_file, form)
        said = forms.get(form, {}).get("blank_comments")  # "No answer yet." in the student's comment languages
        limit = _comment_limit(key_file, form)
        boxes = []
        for box in page_layout["boxes"]:
            part, pages_of = box.get("part", 1), essay_pages.get((form, box["q"]), [])
            if part > 1:  # an essay's later page: its mark goes with the first page of it that was routed
                if any(routed.get((page["student_id"], n)) for n in pages_of[:part - 1]):
                    continue
                box = {**box, "points": key[box["q"]]["points"]}
            item, answer = key[box["q"]], page["answers"][str(box["q"])]
            scan, where = str(page["scan_index"]), f"marks/q{box['q']}.json, scan {page['scan_index']}"
            later = [routed.get((page["student_id"], n)) for n in pages_of[part:]]
            if answer["status"] == "blank" and any(p and p["answers"][str(box["q"])]["status"] != "blank" for p in later):
                answer = {**answer, "status": "mark"}  # the essay starts further on
            if answer["status"] == "blank":
                r = _blank(box, answer["crop"], said)
                if box["type"] == "choice":
                    r["details"] = [{"selected": None, "answer": item["answer"], "source": "scan",
                                     "crossed_out": [], "ink": answer["ink"]}]
                boxes.append(r)
                continue
            if answer["status"] == "scan":
                boxes.append(_choice(box, item, [answer["read"]], "scan", answer["crop"], ink=answer["ink"], said=said))
                continue
            mark = marks.get(box["q"], {}).get(scan)
            if mark is None:
                errors.append(f"{where}: no mark yet (crop {answer['crop']})")
                continue
            problems = _validate(box["type"], mark, where, item)
            if problems:
                errors += problems
                continue
            kind = box["type"]
            if kind == "short" and item.get("rubric"):
                r = _rubric(box, item, mark, answer["crop"])
            elif kind == "short":
                r = _result(box, answer["crop"], transcription=mark["transcription"], verdict=mark["verdict"],
                            comment=mark["comment"], confidence=mark["confidence"],
                            uncertain_words=mark.get("uncertain_words", []),
                            key_ambiguous=bool(mark.get("key_ambiguous")), reviewed=bool(mark.get("reviewed")),
                            note=mark.get("note", ""))
            elif kind == "choice":
                r = _choice(box, item, mark["selected"], "model", answer["crop"], mark["confidence"],
                            mark.get("crossed_out", []), answer["ink"], reviewed=bool(mark.get("reviewed")), said=said)
            elif kind in BOXES:
                r = _boxes(box, item, mark, answer["crop"])
            elif kind == "math":
                r = _math(box, item, mark, answer["crop"])
            else:
                r = _draw(box, item, mark, answer["crop"], said)
            r["more_crops"] = [p["answers"][str(box["q"])]["crop"] for p in later if p]  # an essay's later pages
            scripts = SC.complex_scripts(r["comment"])
            if scripts:
                errors.append(f"{where}: the comment is in {', '.join(scripts)}, which can't print on the marked page "
                              "here. Write it in English, or in English first and then a short version the page "
                              "can print; the student's Word page can carry the rest")
                continue
            words = len(r["comment"].split())
            if words > limit and box["type"] != "choice":
                warnings.append(f"{where}: comment is {words} words; keep it to {limit} or fewer"
                                + (f" ({max_words} in each language)" if limit > max_words else ""))
            if young and box["type"] != "choice" and re.search(r";|:(?!\d)|—", r["comment"]):
                warnings.append(f"{where}: for grades 2-3 use only periods, question marks, and commas")
            boxes.append(r)
        pages.append({"scan_index": page["scan_index"], "student_id": page["student_id"], "page": page["page"],
                      "form": form, "boxes": boxes})

    flagged = [f"scan {p['scan_index']} (ID {p['student_id']}) Q{b['q']}: {'; '.join(b['flag_reasons'])}; "
               f"scored {b['points_awarded']:g}/{b['points_possible']} ({b['verdict']}) for now, "
               f"crop{'s' if b.get('more_crops') else ''} {', '.join([b['crop'], *b.get('more_crops', [])])}"
               + (" [reviewed]" if b["reviewed"] else "")
               for p in pages for b in p["boxes"] if b["flagged"]]
    S.write_json(work / "results.json", {"pages": pages})
    return {"errors": errors, "warnings": warnings, "flagged": flagged, "pages": pages}


def _detail_lines(b: dict, item: dict) -> list[str]:
    if b["type"] == "draw" and b["details"]:
        return ["  - Checklist: " + "; ".join(
            f"{item['checklist'][d['n'] - 1]['item']} ({d['met']})" if "n" in d
            else f"answer {d['read']!r} ({d['verdict']}, key {d['answer']})" for d in b["details"])]
    if b["type"] in BOXES and b["details"]:
        return ["  - Boxes: " + "; ".join(
            f"{d['n']} {d['read']!r} ({d['verdict']}, expected {d['answer']})" for d in b["details"])]
    if b["type"] == "math" and b["details"]:
        a, w = b["details"]
        return [f"  - Answer {a['read']!r} ({a['verdict']}, key {a['answer']}); work: {w['verdict']}"]
    if b["type"] == "short" and item.get("rubric") and b["details"]:
        return ["  - Rubric: " + "; ".join(f"{d['criterion']} {d['level']}/{d['max']}" for d in b["details"])]
    return []


def _languages(key_file: dict, form: str = "") -> int:
    """How many languages a form's comments are in: 2 for "English, then Spanish", which says each thing twice."""
    language = key_file.get("forms", {}).get(form, {}).get("comment_language") or key_file.get("comment_language")
    return max(1, len(SC.comment_languages(language)))


def _comment_limit(key_file: dict, form: str = "") -> int:
    """Words a comment may have: the worksheet's limit, for each language it's in."""
    return key_file.get("comment_words", 15) * _languages(key_file, form)


def _limits(key_file: dict) -> tuple[int, int]:
    words = key_file.get("comment_words", 15)
    return words, key_file.get("strength_words", STRENGTH_MAX_WORDS if words >= 15 else words + 4)


def by_student(pages: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for page in sorted(pages, key=lambda p: p["page"]):
        out.setdefault(page["student_id"], []).append(page)
    return out


def summary_todo(work: Path, pages: list[dict]) -> Path:
    """What Claude needs to write each student's one summary (printed on their last page): summaries/todo.md.
    Each question's prompt is listed once at the top; each student gets one compact line per answer."""
    work = Path(work)
    _, _, key_file = _key(work)
    words, strength = _limits(key_file)
    lines = ["# Summaries: one per student", "",
             "Write `summaries.json`, keyed by student ID. Rules: the \"summary\" section of "
             f"references/marking-rules.md. The strength is under {strength} words and each next step {words} "
             f"words at most. Next steps follow the feedback style: {key_file.get('feedback', 'hint')}.", "",
             "```json", '{"<ID>": {"strength": "...", "fixes": ["...", "..."]}, ...}', "```", "", "## The questions", ""]
    items = {item["q"]: item for item in key_file["items"]}
    for page in pages:  # and any question only some copies have, such as a practice sheet's stretch questions
        for q, item in S.form_items(key_file, page.get("form", "")).items():
            items.setdefault(q, item)
    asked = {b["q"] for page in pages for b in page["boxes"]}
    for item in items.values():
        if item["q"] in asked:
            lines.append(f"- Q{item['q']} ({'rubric' if item.get('rubric') else item['type']}): {item['prompt']}")
    lines.append("")
    forms = key_file.get("forms", {})
    for student, student_pages in by_student(pages).items():
        scans = ", ".join(str(p["scan_index"]) for p in student_pages)
        form = student_pages[0].get("form", "")
        extra = ""
        if form in forms:
            f = forms[form]
            extra = f", {'copy' if f['kind'] == 'variant' else 'version'} {f['label']}"
            if f.get("comment_language") and f["comment_language"] != key_file.get("comment_language", "English"):
                extra += f"; write this summary in {f['comment_language']}"
                if _languages(key_file, form) > 1:
                    extra += " (the word limits are for each language)"
        lines += [f"## ID {student} (scan{'s' if len(student_pages) > 1 else ''} {scans}{extra})", ""]
        key = S.form_items(key_file, form)
        for page in student_pages:
            for b in page["boxes"]:
                item = key[b["q"]]
                answer = b["transcription"]
                if b["type"] == "choice" and b["details"] and b["details"][0].get("selected"):
                    chosen = next((o["text"] for o in item["options"] if o["letter"] == b["details"][0]["selected"]), "")
                    answer = f"{answer} ({chosen})" if chosen else answer
                lines.append(f"- Q{b['q']}: {b['verdict']}; read {answer!r}; comment {b['comment']!r}")
                lines += _detail_lines(b, item)
        lines.append("")
    path = work / "summaries" / "todo.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    return path


def summaries(work: Path, pages: list[dict]) -> tuple[dict, list[str], list[str]]:
    """(summaries by student ID, errors, warnings) from summaries.json."""
    path = Path(work) / "summaries.json"
    if not path.exists():
        return {}, ["summaries.json doesn't exist yet"], []
    _, _, key_file = _key(Path(work))
    data = {str(k): v for k, v in S.read_json(path).items()}
    errors, warnings = [], []
    students = by_student(pages)
    for student in students:
        s = data.get(student)
        where = f"summaries.json, ID {student}"
        languages = _languages(key_file, students[student][0].get("form", ""))
        words, strength_words = (n * languages for n in _limits(key_file))  # for each language it's written in
        if not isinstance(s, dict) or not isinstance(s.get("strength"), str) or not isinstance(s.get("fixes"), list):
            errors.append(f"{where}: needs {{\"strength\": \"...\", \"fixes\": [...]}} (summaries are keyed by "
                          "student ID, one per student)")
            continue
        if len(s["fixes"]) > 2:
            errors.append(f"{where}: at most two next steps")
        if len(s["strength"].split()) > strength_words:
            warnings.append(f"{where}: strength is {len(s['strength'].split())} words; keep it under {strength_words}")
        scripts = SC.complex_scripts(" ".join([str(s.get("strength", "")), *map(str, s["fixes"])]))
        if scripts:
            errors.append(f"{where}: written in {', '.join(scripts)}, which can't print on the marked page here; "
                          "write the summary in English")
        for fix in s["fixes"]:
            if len(str(fix).split()) > words:
                warnings.append(f"{where}: a next step is {len(str(fix).split())} words; keep it to {words}")
    extra = sorted(set(data) - set(students))
    if extra:
        errors.append(f"summaries.json: {', '.join(extra)} aren't students in this scan (keys are student IDs)")
    return data, errors, warnings


def write_cli_files(work: Path, pages: list[dict], summary_by_student: dict) -> None:
    """feedback.json and ingest.json in the Paper Loop CLI's format, for `paperloop score` and records."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    zero = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "cost_usd": 0.0}
    feedback = {"assignment_id": manifest["assignment_id"], "model": "claude (Paper Loop skill)",
                "effort": "subscription", "threshold": THRESHOLD, "totals": zero,
                "pages": [{**p, "summary": summary_by_student.get(p["student_id"], {"strength": "", "fixes": []})
                           if p is by_student(pages)[p["student_id"]][-1] else {"strength": "", "fixes": []},
                           "usage": zero} for p in pages]}
    ingest = {"source_pdfs": manifest["source_pdfs"], "assignment_dir": manifest["assignment_dir"],
              "dpi": manifest["dpi"], "id_usage": zero,
              "pages": [{k: p[k] for k in ("scan_index", "status", "reason", "assignment_id", "page", "student_id",
                                           "image", "raw_image")} for p in manifest["pages"]]}
    S.write_json(work / "feedback.json", feedback)
    S.write_json(work / "ingest.json", ingest)
