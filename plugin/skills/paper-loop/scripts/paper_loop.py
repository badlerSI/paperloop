#!/usr/bin/env python3
"""Paper Loop: the scripted half of the skill. Claude does the reading and judging in between.

    make WORKSHEET.json --out DIR        lay out a printable worksheet
    prepare SCAN.pdf... --assignment DIR --work DIR
                                         line up pages, crop ID strips and answers
    ids WORK [--roster ids.csv]          route pages using Claude's ID reads (WORK/ids.json)
    todo WORK                            write one marking work order per question (WORK/todo/)
    zoom IMAGE [--region l,t,r,b]        an enlarged, darkened copy of a crop, for faint or small details
    preview PDF                          each page as a PNG you can look at (a worksheet, or returned.pdf)
    check WORK                           check Claude's marks and summaries, list flags
    render WORK [--grade off|back|csv] [--accept-flags]
                                         the marked PDF to print (WORK/out/returned.pdf)
    status WORK                          where a marking run stands, and what to do next

Needs only numpy, scipy, Pillow, pypdfium2, and reportlab.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paper_loop_core import prepare as P  # noqa: E402
from paper_loop_core import render as R  # noqa: E402
from paper_loop_core import results as X  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402


def cmd_make(args) -> int:
    try:
        defn = S.normalize(S.read_json(args.worksheet))
        layout = S.make_worksheet(defn, args.out, base=Path(args.worksheet).resolve().parent)
    except (S.WorksheetError, ValueError, OSError) as e:
        print(f"Can't make the worksheet: {e}")
        return 1
    except (KeyError, TypeError, IndexError, AttributeError) as e:
        print(f"Can't make the worksheet: a field is missing or the wrong type ({type(e).__name__}: {e}). "
              "Check it against references/worksheet-format.md.")
        return 1
    n = len(layout["pages"])
    questions = [b for b in defn["questions"] if b["type"] != "passage"]
    print(f"Wrote {Path(args.out) / 'worksheet.pdf'}: {n} page{'s' if n > 1 else ''}, {len(questions)} question{'s' if len(questions) != 1 else ''}, "
          f"{sum(q['points'] for q in questions):g} points. Style {defn['style']} (grade {defn['grade']}), "
          f"{defn['id_digits']}-digit IDs.")
    for page, free, blocks in zip(layout["pages"], layout["free_by_page"], layout["blocks_by_page"]):
        print(f"  page {page['page']}: {', '.join(f'{name} {h:.0f}pt' for name, h in blocks)} ({free:.0f}pt free)")
    for passage in layout["passages"]:
        if passage["line_numbers"]:
            print(f"  {passage['id']} line numbers, as printed (cite these in questions):")
            for number, line in passage["lines"]:
                if number or line.strip():  # a wrapped code line has text but no number
                    print(f"    {number or '':>3}  {line}")
    for problem in layout["citation_problems"]:
        print(f"  Check: {problem}.")
    if layout["teacher_notes"]:
        print(f"  Notes for the teacher (not printed): {layout['teacher_notes']}")
    if layout["unprintable"]:
        print(f"  These characters will print as \"?\": {layout['unprintable']}. No Unicode font was found; "
              "write them in words, or install DejaVu Sans (pip install matplotlib brings it).")
    essay = any(b.get("parts", 1) > 1 for page in layout["pages"] for b in page["boxes"])
    if n > 1 and essay:
        print("  More than one page: print double-sided. The essay runs across pages, so the page count follows "
              "its lines.")
    elif n > 1:
        st = S.STYLES[defn["style"]]
        print(f"  More than one page: print double-sided. To fit on {n - 1} page{'s' if n > 2 else ''}, cut about "
              f"{layout['shortfall']:.0f}pt: a writing line is {st['line_spacing']:g}pt, and the gap between "
              f"questions is {st['block_gap']:g}pt. Shorter prompts, fewer lines, smaller diagrams or work areas"
              + (", or \"compact\": true" if defn["style"] == "standard" else "") + " all help.")
    return 0


def cmd_prepare(args) -> int:
    work = Path(args.work)
    if any((work / name).exists() for name in ("ids.json", "summaries.json")) or any((work / "marks").glob("q*.json")):
        print(f"{work} already has IDs or marks from an earlier run. Use a new work folder, so the old marks "
              "can't be mixed with a new scan.")
        return 1
    manifest = P.prepare(args.scans, args.assignment, args.work)
    pages = manifest["pages"]
    ok = [p for p in pages if p["status"] == "ok"]
    print(f"{len(pages)} scanned pages: {len(ok)} ready, {sum(p['status'] == 'blank' for p in pages)} blank, "
          f"{sum(p['status'] == 'review' for p in pages)} for the review pile.")
    for p in pages:
        if p["status"] == "review":
            print(f"  scan {p['scan_index']}: {p['reason']}")
        elif p["status"] == "blank":
            print(f"  scan {p['scan_index']}: an empty sheet (no worksheet on it); it's left out of the printout. "
                  "Mention it to the teacher.")
    if ok:
        print("\nNext: read the handwritten IDs, then write ids.json (see SKILL.md, step 2). Each sheet shows "
              "up to 20 ID strips, labeled with their scan numbers:")
        for sheet in manifest["id_sheets"]:
            print(f"  {Path(args.work) / sheet}")
        print(f"If a strip is hard to read on the sheet, open it on its own: {Path(args.work) / 'ids'}/scan-NNN.png")
    return 0


def cmd_ids(args) -> int:
    pages = S.read_json(Path(args.work) / "manifest.json")["pages"]
    digits = next((p["id_digits"] for p in pages if p.get("id_digits")), 4)
    roster = P.load_roster(args.roster, digits)
    manifest = P.route(args.work, roster)
    pages = manifest["pages"]
    routed = [p for p in pages if p["status"] == "ok" and p["student_id"]]
    print(f"{len(routed)} pages matched to students"
          + (f" (checked against a roster of {len(roster)})" if roster is not None else " (no roster given)") + ".")
    for p in routed:
        note = (f" (read at {p['id_confidence']:.2f}: accepted because it's on the roster and no other ID is "
                "one digit away)") if p.get("id_by_roster") else ""
        print(f"  scan {p['scan_index']}: ID {p['student_id']}{note}")
    pile = [p for p in pages if p["status"] == "review"]
    for p in pile:
        print(f"  scan {p['scan_index']} -> review pile: {p['reason']}")
    if pile and roster is None:
        print("A roster (a CSV of the class's ID numbers, no names) lets less certain reads through safely.")
    print("Next: run `todo`.")
    return 0


def cmd_todo(args) -> int:
    paths = P.todo(args.work)
    manifest = S.read_json(Path(args.work) / "manifest.json")
    settled = P.settled_count(manifest)
    _blank_notes(manifest)
    if not paths:
        print(f"Nothing for Claude to mark ({settled} answers settled from the scan). Run `check` next.")
        return 0
    print(f"{settled} answers settled from the scan (blank, or one clear circle). Work orders to mark:")
    for path in paths:
        print(f"  {path}")
    key = S.read_json(Path(manifest["assignment_dir"]) / "key.json")
    marked = {int(path.stem[1:]) for path in paths}
    settled_qs = [str(item["q"]) for item in key["items"] if item["q"] not in marked]
    if settled_qs:
        print(f"Settled from the scan for every student, no work order: Q{', Q'.join(settled_qs)}.")
    return 0


def cmd_preview(args) -> int:
    import pypdfium2 as pdfium
    pdf = Path(args.pdf)
    out = pdf.parent / "preview"
    out.mkdir(exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i in range(len(doc)):
            if args.page and i + 1 != args.page:
                continue
            path = out / f"{pdf.stem}-p{i + 1}.png"
            doc[i].render(scale=1.5).to_pil().convert("L").save(path)
            print(path)
    finally:
        doc.close()
    return 0


def _blank_notes(manifest: dict) -> None:
    if not P.all_blank(manifest) and not P.blank_pages(manifest):
        print("No student left a whole page blank.")
    absent = {}
    for p in P.all_blank(manifest):
        absent.setdefault(p["student_id"], []).append(str(p["scan_index"]))
    for student, scans in absent.items():
        print(f"ID {student} (scan{'s' if len(scans) > 1 else ''} {', '.join(scans)}): every answer the student "
              "handed in is blank. Tell the teacher: the student may have been absent or used another sheet.")
    for p in P.blank_pages(manifest):
        print(f"Scan {p['scan_index']} (ID {p['student_id']}, page {p['page']}): every answer on this page is blank, "
              "though the student answered elsewhere. Tell the teacher: they may have missed the back or run out "
              "of time.")


def cmd_zoom(args) -> int:
    from PIL import Image, ImageOps
    img = Image.open(args.image).convert("L")
    if args.region:
        left, top, right, bottom = (float(v) for v in args.region.split(","))
        img = img.crop((round(left * img.width), round(top * img.height),
                        round(right * img.width), round(bottom * img.height)))
    factor = max(1.0, min(4.0, 1400 / max(img.width, img.height)))
    img = ImageOps.autocontrast(img.resize((round(img.width * factor), round(img.height * factor)),
                                           Image.LANCZOS), cutoff=1)
    stem = Path(args.image).stem
    out = Path(args.image).parent / "zoom" / f"{stem}-zoom{len(list(Path(args.image).parent.glob(f'zoom/{stem}-zoom*'))) + 1}.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out)
    print(f"{out} ({factor:.1f}x)")
    return 0


def _report(result: dict) -> None:
    for e in result["errors"]:
        print(f"  ERROR {e}")
    for w in result["warnings"]:
        print(f"  shorten: {w}")


def cmd_check(args) -> int:
    result = X.check(args.work)
    _report(result)
    if result["errors"]:
        print(f"{len(result['errors'])} problems to fix in the marks files, then run `check` again.")
        return 1
    boxes = sum(len(p["boxes"]) for p in result["pages"])
    print(f"Marks: all {boxes} answers on {len(result['pages'])} pages are marked.")
    if result["warnings"]:
        print("Shorten the comments above, then run `check` again before writing summaries.")
        return 1
    manifest = S.read_json(Path(args.work) / "manifest.json")
    _blank_notes(manifest)
    if result["flagged"]:
        print(f"{len(result['flagged'])} flagged for the teacher (show each one: crop, reading, verdict, comment, "
              "and what changes if they decide the other way):")
        for f in result["flagged"]:
            print(f"  {f}")
    else:
        print("0 flagged: nothing needs the teacher's decision.")
    todo = X.summary_todo(args.work, result["pages"])
    if not (Path(args.work) / "summaries.json").exists():
        print(f"Next: write summaries.json from {todo}, then run `check` again.")
        return 0
    _, errors, warnings = X.summaries(args.work, result["pages"])
    for w in warnings:
        print(f"  shorten: {w}")
    for e in errors:
        print(f"  ERROR {e}")
    if errors:
        print("Summaries: fix the problems above, then run `check` again.")
        return 1
    print("Summaries: clean." + (" Next: teacher review of the flags, then `render`." if result["flagged"]
                                 else " Next: `render`."))
    return 0


def cmd_render(args) -> int:
    result = X.check(args.work)
    if result["errors"]:
        _report(result)
        print("Fix the marks first (see `check`).")
        return 1
    summaries, errors, warnings = X.summaries(args.work, result["pages"])
    for w in warnings:
        print(f"  shorten: {w}")
    if errors:
        for e in errors:
            print(f"  ERROR {e}")
        return 1
    unreviewed = [f for f in result["flagged"] if not f.endswith("[reviewed]")]
    if unreviewed and not args.accept_flags:
        print(f"{len(unreviewed)} flagged answers haven't been reviewed by the teacher:")
        for f in unreviewed:
            print(f"  {f}")
        print("Show them to the teacher. Mark each one \"reviewed\": true in its marks file once the teacher has "
              "checked it, or use --accept-flags if the teacher says to print as marked.")
        return 1
    X.write_cli_files(args.work, result["pages"], summaries)
    out = R.render(args.work, result["pages"], summaries, args.grade)
    sides = "double-sided" if out["double_sided"] else "single-sided"
    print(f"Wrote {out['returned']}: {out['students']} students, {out['sheets']} pages. Print {sides}.")
    print({"off": "No scores printed.", "back": "Each student's score is on their last page.",
           "csv": "No scores printed; they're in grades.csv."}[args.grade])
    if "grades" in out:
        print(f"Grades: {out['grades']}")
    if "review_pile" in out:
        print(f"Review pile (pages that couldn't be read): {out['review_pile']}")
    for sid, pages in out["missing"].items():
        print(f"ID {sid} has no page {', '.join(map(str, pages))} in this scan (missing, or in the review pile): "
              "tell the teacher. Scores are out of the whole worksheet.")
    return 0


def cmd_status(args) -> int:
    work = Path(args.work)
    if not (work / "manifest.json").exists():
        print("Not prepared yet: run `prepare`.")
        return 0
    manifest = S.read_json(work / "manifest.json")
    pages = manifest["pages"]
    print(f"{manifest['title']} ({manifest['assignment_id']}): {len(pages)} scanned pages.")
    waiting = [p for p in pages if p["status"] == "ok" and not p["student_id"]]
    if not (work / "ids.json").exists() or waiting:
        print("Next: read the ID strips into ids.json, then run `ids`.")
        return 0
    todo = sorted((work / "todo").glob("q*.md")) if (work / "todo").exists() else []
    if not (work / "todo").exists():
        print("Next: run `todo`.")
        return 0
    missing = [t for t in todo if not (work / "marks" / f"{t.stem}.json").exists()]
    if missing:
        print("Next: mark " + ", ".join(t.stem.upper() for t in missing) + " (work orders in todo/).")
        return 0
    if not (work / "summaries.json").exists():
        print("Next: run `check`, fix anything it reports, then write summaries.json.")
        return 0
    returned = work / "out" / "returned.pdf"
    inputs = [*(work / "marks").glob("q*.json"), work / "summaries.json", work / "manifest.json"]
    if returned.exists() and returned.stat().st_mtime >= max(f.stat().st_mtime for f in inputs):
        print(f"Done: {returned} is ready to print. (Change a mark or a summary and render again to update it.)")
        return 0
    print("Next: run `check` until marks and summaries are clean, review flags with the teacher, then `render`.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="paper_loop.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("make")
    p.add_argument("worksheet", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_make)
    p = sub.add_parser("prepare")
    p.add_argument("scans", type=Path, nargs="+")
    p.add_argument("--assignment", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("ids")
    p.add_argument("work", type=Path)
    p.add_argument("--roster", type=Path)
    p.set_defaults(func=cmd_ids)
    p = sub.add_parser("preview")
    p.add_argument("pdf", type=Path)
    p.add_argument("--page", type=int, help="only this page")
    p.set_defaults(func=cmd_preview)
    p = sub.add_parser("zoom")
    p.add_argument("image", type=Path)
    p.add_argument("--region", help="left,top,right,bottom as fractions of the image, e.g. 0.5,0,1,0.5")
    p.set_defaults(func=cmd_zoom)
    for name, func in (("todo", cmd_todo), ("check", cmd_check), ("status", cmd_status)):
        p = sub.add_parser(name)
        p.add_argument("work", type=Path)
        p.set_defaults(func=func)
    p = sub.add_parser("render")
    p.add_argument("work", type=Path)
    p.add_argument("--grade", choices=["off", "back", "csv"], default="off")
    p.add_argument("--accept-flags", action="store_true")
    p.set_defaults(func=cmd_render)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
