"""Sweep: mark the same ingested scans with several models and effort levels, then score each.

Every run reuses one ingest (same crops in, same truth out), so differences
come from the marker. Model outputs vary run to run; use --reps to see how much.
"""

from __future__ import annotations

import csv
import itertools
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .make import load_assignment
from .mark import ClaudeMarker, mark
from .schemas import IngestResult, load
from .score import metrics

COLUMNS = ["model", "effort", "rep", "seconds", "cost_usd", "cost_per_page", "output_tokens",
           "autocorrected", "misspellings", "false_correct", "verdict_matches", "judged",
           "words_matched", "words_total", "flagged", "boxes", "long_comments", "answered"]


def _run_one(base: Path, out: Path, truth: dict, model: str, effort: str, rep: int, threshold: float) -> dict:
    work = out / f"{model}-{effort}-r{rep}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy(base / "ingest.json", work / "ingest.json")
    (work / "pages").symlink_to((base / "pages").resolve(), target_is_directory=True)
    _, key = load_assignment(Path(load(IngestResult, base / "ingest.json").assignment_dir))

    started = time.monotonic()
    mark(work, ClaudeMarker(key, model=model, effort=effort), threshold=threshold, workers=4)
    m = metrics(work, truth)
    return {
        "model": model, "effort": effort, "rep": rep, "seconds": round(time.monotonic() - started, 1),
        "cost_usd": round(m["cost_usd"], 5), "cost_per_page": round(m["cost_usd"] / max(m["pages"], 1), 5),
        "output_tokens": m["output_tokens"],
        "autocorrected": len(m["autocorrected"]), "misspellings": m["misspellings"],
        "false_correct": len(m["false_correct"]),
        "verdict_matches": m["judged"] - len(m["verdict_mismatches"]), "judged": m["judged"],
        "words_matched": m["words_matched"], "words_total": m["words_total"],
        "flagged": m["flagged"], "boxes": m["boxes"],
        "long_comments": len(m["long_comments"]), "answered": m["answered"],
    }


def sweep(base: Path, truth_path: Path, out: Path, models: list[str], efforts: list[str], reps: int = 1,
          threshold: float = 0.8, parallel: int = 3, progress: Callable[[str], None] = lambda _: None) -> list[dict]:
    base, out = Path(base), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    truth = json.loads(Path(truth_path).read_text())
    configs = list(itertools.product(models, efforts, range(1, reps + 1)))
    progress(f"{len(configs)} runs: {len(models)} models x {len(efforts)} efforts x {reps} reps")

    def go(config):
        model, effort, rep = config
        try:
            row = _run_one(base, out, truth, model, effort, rep, threshold)
        except Exception as e:  # one bad config shouldn't sink the sweep
            progress(f"  {model} {effort} r{rep}: failed ({type(e).__name__}: {e})")
            return None
        progress(f"  {model} {effort} r{rep}: ${row['cost_usd']:.4f}, {row['seconds']}s, "
                 f"autocorrect {row['autocorrected']}, false correct {row['false_correct']}, "
                 f"verdicts {row['verdict_matches']}/{row['judged']}, flagged {row['flagged']}/{row['boxes']}")
        return row

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        rows = [r for r in pool.map(go, configs) if r]
    with (out / "sweep.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def summary(rows: list[dict]) -> str:
    """One line per model and effort, totals across reps."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["model"], r["effort"]), []).append(r)
    header = (f"{'model':<18} {'effort':<7} {'reps':>4} {'¢/page':>7} {'autocorr':>8} {'false ok':>8} "
              f"{'verdicts':>9} {'words':>6} {'flagged':>8} {'long cmt':>8} {'sec':>5}")
    lines = [header]
    for (model, effort), rs in sorted(groups.items()):
        s = {k: sum(r[k] for r in rs) for k in COLUMNS[3:]}
        n = len(rs)
        lines.append(
            f"{model:<18} {effort:<7} {n:>4} {100 * s['cost_per_page'] / n:>7.2f} "
            f"{s['autocorrected']:>3}/{s['misspellings']:<4} {s['false_correct']:>8} "
            f"{s['verdict_matches']:>4}/{s['judged']:<4} {s['words_matched'] / max(s['words_total'], 1):>6.0%} "
            f"{s['flagged'] / max(s['boxes'], 1):>8.0%} {s['long_comments']:>3}/{s['answered']:<4} {s['seconds'] / n:>5.0f}"
        )
    return "\n".join(lines)
