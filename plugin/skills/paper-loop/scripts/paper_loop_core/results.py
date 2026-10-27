"""Claude's marks (marks/qN.json) -> checked results, flags, and the per-page summary work order.

`check` reports what's wrong with a marks file in words Claude can act on, so a bad file gets fixed
instead of rendered. Results are written in the Paper Loop CLI's feedback.json format, so the CLI's
`score` command can compare them with a known answer key.
"""

from __future__ import annotations

from pathlib import Path

from . import sheet as S

THRESHOLD = 0.8  # flag answers Claude is less sure of than this for the teacher
COMMENT_MAX_WORDS = 15
STRENGTH_MAX_WORDS = 20
VERDICTS = {"correct", "partial", "incorrect", "blank", "unreadable"}
LABEL_VERDICTS = {"correct", "incorrect", "blank", "unreadable"}
MET = {"yes", "no", "unclear"}


class MarksError(ValueError):
    pass


def _points_for(verdict: str, possible: int) -> float:
    return {"correct": float(possible), "partial": possible / 2}.get(verdict, 0.0)


def _graded(earned: float, possible: int) -> str:
    return "correct" if earned >= possible else "incorrect" if earned == 0 else "partial"


def _result(box: dict, crop: str, *, transcription: str, verdict: str, comment: str, confidence: float,
            points: float | None = None, reasons: list[str] | None = None, details: list[dict] | None = None,
            uncertain_words: list[str] | None = None, key_ambiguous: bool = False, reviewed: bool = False) -> dict:
    confidence = min(max(float(confidence), 0.0), 1.0)
    reasons = list(reasons or [])
    if verdict == "unreadable" and "unreadable" not in reasons:
        reasons.append("unreadable")
    if confidence < THRESHOLD:
        reasons.append(f"confidence {confidence:.2f}")
    if key_ambiguous:
        reasons.append("the key doesn't settle this answer")
    return {"transcription": transcription, "uncertain_words": uncertain_words or [], "verdict": verdict,
            "comment": comment, "confidence": confidence, "key_ambiguous": key_ambiguous, "q": box["q"],
            "type": box["type"], "points_possible": box["points"],
            "points_awarded": _points_for(verdict, box["points"]) if points is None else points,
            "flagged": bool(reasons), "flag_reasons": reasons, "reviewed": reviewed, "crop": crop,
            "details": details or []}


def _blank(box: dict, crop: str) -> dict:
    return _result(box, crop, transcription="", verdict="blank", confidence=1.0,
                   comment="No answer circled." if box["type"] == "choice" else "No answer yet.")


def _choice(box: dict, item: dict, selected: list[str], source: str, crop: str, confidence: float = 1.0,
            crossed: list[str] = (), ink: list[int] = (), reviewed: bool = False) -> dict:
    details = [{"selected": "+".join(selected) or None, "answer": item["answer"], "source": source,
                "crossed_out": list(crossed), "ink": list(ink)}]
    if not selected:
        r = _blank(box, crop)
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


def _label(box: dict, item: dict, mark: dict, crop: str) -> dict:
    reads = {int(r["n"]): r for r in mark["labels"]}
    details, reasons, earned = [], [], 0.0
    confidence = float(mark["confidence"])
    for spot in item["labels"]:
        read = reads.get(spot["n"])
        if read is None:
            reasons.append(f"label {spot['n']} wasn't read")
            details.append({"n": spot["n"], "read": "", "verdict": "unreadable", "answer": spot["answer"]})
            continue
        confidence = min(confidence, float(read["confidence"]))
        if read["verdict"] == "unreadable":
            reasons.append(f"label {spot['n']} unreadable")
        earned += spot["points"] if read["verdict"] == "correct" else 0
        details.append({"n": spot["n"], "read": read["transcription"], "verdict": read["verdict"],
                        "answer": spot["answer"]})
    verdict = "blank" if all(d["verdict"] == "blank" for d in details) else _graded(earned, box["points"])
    return _result(box, crop, transcription="; ".join(f"{d['n']}: {d['read']}" for d in details), verdict=verdict,
                   comment=mark["comment"], confidence=confidence, points=earned, reasons=reasons, details=details,
                   reviewed=bool(mark.get("reviewed")))


def _draw(box: dict, item: dict, mark: dict, crop: str) -> dict:
    checks = {int(c["n"]): c for c in mark["items"]}
    details, reasons, earned = [], [], 0.0
    for n, check in enumerate(item["checklist"], start=1):
        got = checks.get(n)
        met = got["met"] if got else "unclear"
        if met == "unclear":
            reasons.append(f"checklist item {n} unclear")
        earned += check["points"] if met == "yes" else 0
        details.append({"n": n, "item": check["short"] or check["item"], "met": met,
                        "note": got.get("note", "") if got else ""})
    return _result(box, crop, transcription=mark["description"], verdict=_graded(earned, box["points"]),
                   comment=mark["comment"], confidence=mark["confidence"], points=earned, reasons=reasons,
                   details=details, reviewed=bool(mark.get("reviewed")))


def _validate(kind: str, mark, where: str, item: dict) -> list[str]:
    """Problems with one mark, each phrased as what to fix."""
    if not isinstance(mark, dict):
        return [f"{where}: should be an object"]
    problems = []

    def need(field: str, types, allowed=None):
        if field not in mark:
            problems.append(f"{where}: missing \"{field}\"")
        elif not isinstance(mark[field], types):
            problems.append(f"{where}: \"{field}\" has the wrong type")
        elif allowed is not None and mark[field] not in allowed:
            problems.append(f"{where}: \"{field}\" must be one of {', '.join(sorted(allowed))}")

    need("confidence", (int, float))
    if kind == "short":
        need("transcription", str), need("verdict", str, VERDICTS), need("comment", str)
    elif kind == "choice":
        need("selected", list)
        letters = {o["letter"] for o in item["options"]}
        marked = [m for field in ("selected", "crossed_out") if isinstance(mark.get(field), list) for m in mark[field]]
        bad = [s for s in marked if s not in letters]
        if bad:
            problems.append(f"{where}: {', '.join(map(str, bad))} isn't an option letter ({', '.join(sorted(letters))})")
    elif kind == "label":
        need("labels", list), need("comment", str)
        expected = {s["n"] for s in item["labels"]}
        got = set()
        for n, read in enumerate(mark.get("labels", []) if isinstance(mark.get("labels"), list) else []):
            if not isinstance(read, dict) or "n" not in read:
                problems.append(f"{where}: labels[{n}] needs \"n\"")
                continue
            got.add(int(read["n"]))
            for field in ("transcription", "verdict", "confidence"):
                if field not in read:
                    problems.append(f"{where}: label {read['n']} is missing \"{field}\"")
            if read.get("verdict") not in LABEL_VERDICTS:
                problems.append(f"{where}: label {read['n']} verdict must be one of {', '.join(sorted(LABEL_VERDICTS))}")
        if expected - got:
            problems.append(f"{where}: no reading for label box {', '.join(map(str, sorted(expected - got)))}")
    elif kind == "draw":
        need("description", str), need("items", list), need("comment", str)
        expected = set(range(1, len(item["checklist"]) + 1))
        got = set()
        for n, check in enumerate(mark.get("items", []) if isinstance(mark.get("items"), list) else []):
            if not isinstance(check, dict) or "n" not in check:
                problems.append(f"{where}: items[{n}] needs \"n\"")
                continue
            got.add(int(check["n"]))
            if check.get("met") not in MET:
                problems.append(f"{where}: checklist item {check['n']} \"met\" must be yes, no, or unclear")
        if expected - got:
            problems.append(f"{where}: no answer for checklist item {', '.join(map(str, sorted(expected - got)))}")
    return problems


def check(work: Path) -> dict:
    """Build every routed page's results from the scan and Claude's marks. Returns
    {"errors": [...], "warnings": [...], "flagged": [...], "pages": [...]}, and writes results.json."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    layout = S.read_json(Path(manifest["assignment_dir"]) / "layout.json")
    key = {item["q"]: item for item in S.read_json(Path(manifest["assignment_dir"]) / "key.json")["items"]}
    marks, errors, warnings = {}, [], []
    for path in sorted((work / "marks").glob("q*.json")):
        try:
            data = S.read_json(path)
        except ValueError as e:
            errors.append(f"{path.name}: not valid JSON ({e})")
            continue
        q = int(data.get("q", path.stem[1:]))
        marks[q] = {str(k): v for k, v in data.get("marks", {}).items()}

    pages = []
    for page in manifest["pages"]:
        if page["status"] != "ok" or not page["student_id"]:
            continue
        page_layout = next(p for p in layout["pages"] if p["page"] == page["page"])
        boxes = []
        for box in page_layout["boxes"]:
            item, answer = key[box["q"]], page["answers"][str(box["q"])]
            scan, where = str(page["scan_index"]), f"marks/q{box['q']}.json, scan {page['scan_index']}"
            if answer["status"] == "blank":
                r = _blank(box, answer["crop"])
                if box["type"] == "choice":
                    r["details"] = [{"selected": None, "answer": item["answer"], "source": "scan",
                                     "crossed_out": [], "ink": answer["ink"]}]
                boxes.append(r)
                continue
            if answer["status"] == "scan":
                boxes.append(_choice(box, item, [answer["read"]], "scan", answer["crop"], ink=answer["ink"]))
                continue
            mark = marks.get(box["q"], {}).get(scan)
            if mark is None:
                errors.append(f"{where}: no mark yet (crop {answer['crop']})")
                continue
            problems = _validate(box["type"], mark, where, item)
            if problems:
                errors += problems
                continue
            if box["type"] == "short":
                r = _result(box, answer["crop"], transcription=mark["transcription"], verdict=mark["verdict"],
                            comment=mark["comment"], confidence=mark["confidence"],
                            uncertain_words=mark.get("uncertain_words", []),
                            key_ambiguous=bool(mark.get("key_ambiguous")), reviewed=bool(mark.get("reviewed")),
                            details=[{"note": mark["note"]}] if mark.get("note") else None)
            elif box["type"] == "choice":
                r = _choice(box, item, mark["selected"], "model", answer["crop"], mark["confidence"],
                            mark.get("crossed_out", []), answer["ink"], reviewed=bool(mark.get("reviewed")))
            elif box["type"] == "label":
                r = _label(box, item, mark, answer["crop"])
            else:
                r = _draw(box, item, mark, answer["crop"])
            words = len(r["comment"].split())
            if words > COMMENT_MAX_WORDS:
                warnings.append(f"{where}: comment is {words} words; keep it to {COMMENT_MAX_WORDS} or fewer")
            boxes.append(r)
        pages.append({"scan_index": page["scan_index"], "student_id": page["student_id"], "page": page["page"],
                      "boxes": boxes})

    flagged = [f"scan {p['scan_index']} (ID {p['student_id']}) Q{b['q']}: {'; '.join(b['flag_reasons'])}; "
               f"scored {b['points_awarded']:g}/{b['points_possible']} ({b['verdict']}) for now, crop {b['crop']}"
               + (" [reviewed]" if b["reviewed"] else "")
               for p in pages for b in p["boxes"] if b["flagged"]]
    S.write_json(work / "results.json", {"pages": pages})
    return {"errors": errors, "warnings": warnings, "flagged": flagged, "pages": pages}


def summary_todo(work: Path, pages: list[dict]) -> Path:
    """What Claude needs to write each page's strength and next steps: summaries/todo.md."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    key = {item["q"]: item for item in S.read_json(Path(manifest["assignment_dir"]) / "key.json")["items"]}
    lines = ["# Page summaries", "",
             "Write `summaries.json`: one entry per scan, keyed by scan number. Rules: the \"summary\" section "
             "of references/marking-rules.md.", "",
             "```json", '{"1": {"strength": "...", "fixes": ["...", "..."]}, ...}', "```", ""]
    for page in pages:
        lines += [f"## Scan {page['scan_index']}", ""]
        for b in page["boxes"]:
            item = key[b["q"]]
            lines.append(f"- Q{b['q']} ({b['type']}): {item['prompt']}")
            lines.append(f"  - Answer: {b['transcription']!r}; verdict: {b['verdict']}; comment beside it: {b['comment']!r}")
            if b["type"] == "draw" and b["details"]:
                lines.append("  - Checklist: " + "; ".join(
                    f"{item['checklist'][d['n'] - 1]['item']} ({d['met']})" for d in b["details"]))
            if b["type"] == "label" and b["details"]:
                lines.append("  - Labels: " + "; ".join(
                    f"box {d['n']} {d['read']!r} ({d['verdict']}, expected {d['answer']})" for d in b["details"]))
        lines.append("")
    path = work / "summaries" / "todo.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    return path


def summaries(work: Path, pages: list[dict]) -> tuple[dict, list[str], list[str]]:
    """(summaries by scan, errors, warnings) from summaries.json."""
    path = Path(work) / "summaries.json"
    if not path.exists():
        return {}, ["summaries.json doesn't exist yet"], []
    data = {str(k): v for k, v in S.read_json(path).items()}
    errors, warnings = [], []
    for page in pages:
        s = data.get(str(page["scan_index"]))
        where = f"summaries.json, scan {page['scan_index']}"
        if not isinstance(s, dict) or not isinstance(s.get("strength"), str) or not isinstance(s.get("fixes"), list):
            errors.append(f"{where}: needs {{\"strength\": \"...\", \"fixes\": [...]}}")
            continue
        if len(s["fixes"]) > 2:
            errors.append(f"{where}: at most two next steps")
        if len(s["strength"].split()) > STRENGTH_MAX_WORDS:
            warnings.append(f"{where}: strength is {len(s['strength'].split())} words; keep it under {STRENGTH_MAX_WORDS}")
        for fix in s["fixes"]:
            if len(str(fix).split()) > COMMENT_MAX_WORDS:
                warnings.append(f"{where}: a next step is {len(str(fix).split())} words; keep it to {COMMENT_MAX_WORDS}")
    return data, errors, warnings


def write_cli_files(work: Path, pages: list[dict], summary_by_scan: dict) -> None:
    """feedback.json and ingest.json in the Paper Loop CLI's format, for `paperloop score` and records."""
    work = Path(work)
    manifest = S.read_json(work / "manifest.json")
    zero = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "cost_usd": 0.0}
    feedback = {"assignment_id": manifest["assignment_id"], "model": "claude (Paper Loop skill)",
                "effort": "subscription", "threshold": THRESHOLD, "totals": zero,
                "pages": [{**p, "summary": summary_by_scan.get(str(p["scan_index"]), {"strength": "", "fixes": []}),
                           "usage": zero} for p in pages]}
    ingest = {"source_pdfs": manifest["source_pdfs"], "assignment_dir": manifest["assignment_dir"],
              "dpi": manifest["dpi"], "id_usage": zero,
              "pages": [{k: p[k] for k in ("scan_index", "status", "reason", "assignment_id", "page", "student_id",
                                           "image", "raw_image")} for p in manifest["pages"]]}
    S.write_json(work / "feedback.json", feedback)
    S.write_json(work / "ingest.json", ingest)
