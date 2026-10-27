"""Mark a simulated class from its truth file, so later steps (render, goover) have real results to work on.

    .venv/bin/python devtools/oracle.py WORK_DIR TRUTH.json

WORK_DIR is a `prepare`d work folder for the scan devtools/fill.py wrote; TRUTH.json is the scan's
.truth.json. Writes ids.json from the true IDs, routes, writes every mark as the truth expects it (a
perfect marker), and runs `check`. Tests the steps after marking, not Claude's marking. Dev only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "skills" / "paper-loop" / "scripts"))
from paper_loop_core import prepare as P  # noqa: E402
from paper_loop_core import results as X  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402


def mark(item: dict, a: dict) -> dict:
    kind = item["type"]
    if kind == "short" and item.get("rubric"):
        levels = a.get("expected_levels", {})
        return {"transcription": a.get("text", ""), "uncertain_words": [], "comment": "Noted.", "confidence": 1.0,
                "criteria": [{"n": c["n"], "level": int(levels.get(str(c["n"]), c["max"]))} for c in item["rubric"]]}
    if kind == "short":
        return {"transcription": a.get("text", ""), "verdict": a.get("expected", "correct"), "comment": "Noted.",
                "confidence": 1.0}
    if kind == "choice":
        circled = [m for m in a.get("circle", []) if not m.startswith("~~")]
        crossed = [m.strip("~") for m in a.get("circle", []) if m.startswith("~~")]
        return {"selected": circled[-1:], "crossed_out": crossed, "confidence": 1.0}
    if kind in ("label", "blanks", "match", "table"):
        expected = a.get("expected", {})
        boxes = a.get("boxes", {})
        return {"labels": [{"n": spot["n"], "transcription": boxes.get(str(spot["n"]), ""),
                            "verdict": expected.get(str(spot["n"]), "correct" if boxes.get(str(spot["n"])) else "blank"),
                            "confidence": 1.0} for spot in item["labels"]],
                "comment": "Noted.", "confidence": 1.0}
    if kind == "math":
        return {"work": "; ".join(a.get("work", [])), "answer": a.get("answer", ""),
                "answer_verdict": a.get("expected_answer", "correct" if a.get("answer") else "blank"),
                "work_verdict": a.get("expected_work", "correct" if a.get("work") else "blank"),
                "comment": "Noted.", "confidence": 1.0}
    items = a.get("expected_items", {})
    out = {"description": "sketch", "comment": "Noted.", "confidence": 1.0, "verdict": "",
           "items": [{"n": n, "met": items.get(str(n), "yes")} for n in range(1, len(item["checklist"]) + 1)]}
    if item.get("answer"):
        out.update(answer=a.get("answer", ""), answer_verdict=a.get("expected_answer", "correct"))
    return out


def main(work: Path, truth_path: Path) -> None:
    truth = json.loads(truth_path.read_text())
    ids = {str(p["scan_index"]): {"digits": p["student_id"], "confidence": 1.0}
           for p in truth["scan_pages"] if p.get("student_id")}
    S.write_json(work / "ids.json", ids)
    P.route(work)
    manifest = S.read_json(work / "manifest.json")
    key = S.read_json(Path(manifest["assignment_dir"]) / "key.json")
    items = {i["q"]: i for i in key["items"]}
    answers = {s["id"]: s["answers"] for s in truth["students"]}
    marks: dict[int, dict] = {q: {} for q in items}
    for page in manifest["pages"]:
        if page["status"] != "ok":
            continue
        for q, item in items.items():
            a = answers.get(page["student_id"], {}).get(str(q))
            if a and str(q) in page["answers"]:
                marks[q][str(page["scan_index"])] = mark(item, a)
    (work / "marks").mkdir(exist_ok=True)
    for q, m in marks.items():
        S.write_json(work / "marks" / f"q{q}.json", {"q": q, "marks": m})
    report = X.check(work)
    print(f"{len(report['pages'])} pages marked, {len(report['errors'])} errors, {len(report['flagged'])} flagged")
    for e in report["errors"][:10]:
        print("  error:", e)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
