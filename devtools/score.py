"""Score a skill marking run against the answers devtools/fill.py wrote.

    .venv/bin/python devtools/score.py WORK_DIR TRUTH.json

Compares results.json (written by the skill's `check`) with each answer's expected verdicts: whole-question
verdicts, each box, a math answer and its work, rubric levels, and drawing checklist items. Also counts
flags, misspellings lost, and comments over the grade's word limit. Dev only, never shipped.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


def words(text: str) -> list[str]:
    return re.findall(r"[\w'/.-]+", text.lower())


def score(work: Path, truth: dict) -> dict:
    results = json.loads((work / "results.json").read_text())
    manifest = json.loads((work / "manifest.json").read_text())
    key = json.loads((Path(manifest["assignment_dir"]) / "key.json").read_text())
    max_words = key.get("comment_words", 15)
    answers = {s["id"]: s["answers"] for s in truth["students"]}
    expected_pages = {t["scan_index"]: t for t in truth.get("scan_pages", [])}
    tally: Counter = Counter()
    misses: list[str] = []

    routed = {p["scan_index"]: p.get("student_id") for p in manifest["pages"]}
    if not expected_pages:  # a real scan (devtools/guide.py): the stack's order isn't known, so check the IDs
        pages_per = len({p["page"] for p in manifest["pages"] if p.get("page")})
        found = Counter(sid for sid in routed.values() if sid)
        for sid in answers:
            tally["pages"] += pages_per
            tally["routed"] += min(found.get(sid, 0), pages_per)
            if found.get(sid, 0) != pages_per:
                misses.append(f"ID {sid}: {found.get(sid, 0)} pages routed, expected {pages_per}")
        misses += [f"ID {sid}: not in the class" for sid in found if sid not in answers]
    for i, t in expected_pages.items():
        tally["pages"] += 1
        ok = routed.get(i) is None if t.get("blank") else routed.get(i) == t["student_id"]
        tally["routed"] += ok
        if not ok:
            misses.append(f"scan {i}: routed to {routed.get(i)}, expected {t.get('student_id', 'blank')}")

    def agree(name: str, got, want, where: str) -> None:
        tally[f"{name}_total"] += 1
        if got == want:
            tally[f"{name}_ok"] += 1
        else:
            misses.append(f"{where}: {name} {got}, expected {want}")

    for page in results["pages"]:
        sid = page["student_id"]
        for b in page["boxes"]:
            where = f"{sid} Q{b['q']}"
            a = answers.get(sid, {}).get(str(b["q"]))
            tally["boxes"] += 1
            tally["flagged"] += b["flagged"]
            if b["verdict"] != "blank" and len(b["comment"].split()) > max_words:
                tally["long_comments"] += 1
            if a is None:
                agree("verdict", b["verdict"], "blank", where)
                continue
            if "expected" in a and isinstance(a["expected"], str):
                agree("verdict", b["verdict"], a["expected"], where)
            if isinstance(a.get("expected"), dict):
                got = {str(d["n"]): d["verdict"] for d in b["details"]}
                for n, want in a["expected"].items():
                    agree("box", got.get(n), want, f"{where} box {n}")
            if "expected_answer" in a:
                ans, wk = (b["details"] + [{}, {}])[:2]
                agree("math_answer", ans.get("verdict"), a["expected_answer"], where)
                agree("math_work", wk.get("verdict"), a["expected_work"], where)
            if "expected_levels" in a:
                got = {str(d["n"]): d["level"] for d in b["details"]}
                for n, want in a["expected_levels"].items():
                    agree("rubric_level", got.get(n), want, f"{where} criterion {n}")
                    tally["rubric_within1_total"] += 1
                    tally["rubric_within1_ok"] += got.get(n) is not None and abs(got[n] - want) <= 1
            if "expected_items" in a:
                got = {str(d["n"]): d["met"] for d in b["details"]}
                for n, want in a["expected_items"].items():
                    agree("item", got.get(n), want, f"{where} item {n}")
            for word in a.get("misspellings", []):
                tally["misspellings"] += 1
                if word.lower() in words(b["transcription"]):
                    tally["misspellings_kept"] += 1
                else:
                    misses.append(f"{where}: misspelling {word!r} lost in {b['transcription']!r}")
    return {"tally": tally, "misses": misses}


def report(s: dict) -> str:
    t = s["tally"]
    lines = [f"Pages routed: {t['routed']}/{t['pages']}"]
    for name, label in (("verdict", "Question verdicts"), ("box", "Boxes"), ("math_answer", "Math answers"),
                        ("math_work", "Math work"), ("rubric_level", "Rubric levels (exact)"),
                        ("rubric_within1", "Rubric levels (within 1)"), ("item", "Drawing checklist items")):
        if t[f"{name}_total"]:
            lines.append(f"{label}: {t[f'{name}_ok']}/{t[f'{name}_total']}")
    if t["misspellings"]:
        lines.append(f"Misspellings kept: {t['misspellings_kept']}/{t['misspellings']}")
    lines.append(f"Flagged: {t['flagged']}/{t['boxes']}; comments over the limit: {t['long_comments']}")
    lines += [f"  {m}" for m in s["misses"]]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(score(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text()))))
