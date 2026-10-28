#!/usr/bin/env python3
"""Paper Loop: the scripted half of the skill. Claude does the reading and judging in between.

    make WORKSHEET.json --out DIR        lay out a printable worksheet
    prepare SCAN.pdf... --assignment DIR --work DIR
                                         line up pages, crop ID strips and answers
    ids WORK [--roster ids.csv]          route pages using Claude's ID reads (WORK/ids.json)
    todo WORK                            write one marking work order per question (WORK/todo/)
    zoom IMAGE [--region l,t,r,b]        an enlarged, darkened copy of a crop, for faint or small details
    preview PDF [--sheet]                each page as a PNG you can look at (a worksheet, returned.pdf, or
                                         slides); --sheet puts nine slides on one image. A .docx (the
                                         lesson plan) prints its text instead
    lesson LESSON.json --out DIR         a lesson plan (.docx), its slides (.pptx and .pdf), a go-over deck,
                                         and an answer key, from Claude's lesson file and a made worksheet
    goover WORK [--lesson LESSON.json] [--most N] [--out DIR]
                                         after marking: a go-over deck, most-missed questions first, with
                                         how the class answered (WORK/out/go-over.pptx and .pdf)
    check WORK                           check Claude's marks and summaries, list flags
    render WORK [--grade off|back|csv] [--accept-flags]
                                         the marked PDF to print (WORK/out/returned.pdf)
    status WORK                          where a marking run stands, and what to do next
    practice WORK [--most N]             after marking: a practice sheet for each student, of what they missed
    progress FOLDER [--roster ids.csv]   a dashboard, family pages, and a gradebook file across marked classes
    source wikipedia|simple|gutenberg NAME --out FILE.json
                                         a free text to read and adapt, with its license and link
    pieces PIECES.json --out DIR         cards, board games for a checker or chess board, dice, a spinner,
                                         pawns, a fortune teller, a mini-book, ABCD cards, and bingo
    teamwork ACTIVITY.json --out DIR     group work where students teach each other: role cards, the task,
                                         jigsaw expert sheets, coach-and-player sheets, tokens to cut out
    teampoints FOLDER --worksheet ID      after the exit sheet is marked: team points by each student's improvement
    groups FOLDER [--size 4] [--skill S] [--structure lab] [--similar] [--roster ids.csv]
                                         groups from a class's marked work, by class ID: mixed (or
                                         --similar for targeted practice); random from a roster alone

Needs only numpy, scipy, Pillow, pypdfium2, and reportlab; slides also need python-pptx.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paper_loop_core import prepare as P  # noqa: E402
from paper_loop_core import render as R  # noqa: E402
from paper_loop_core import results as X  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402


def cmd_make(args) -> int:
    try:
        layout = S.make_worksheet(S.read_json(args.worksheet), args.out, base=Path(args.worksheet).resolve().parent)
    except (S.WorksheetError, ValueError, OSError) as e:
        print(f"Can't make the worksheet: {e}")
        return 1
    except (KeyError, TypeError, IndexError, AttributeError) as e:
        print(f"Can't make the worksheet: a field is missing or the wrong type ({type(e).__name__}: {e}). "
              "Check it against references/worksheet-format.md.")
        return 1
    defn = layout["defn"]
    n = layout["base_pages"]
    try:  # the worksheet with its answers written in, for the teacher (a lesson writes a fuller one)
        from paper_loop_core import walk as WK
        ws = WK.Worksheet(args.out)
        drawings = {}
        for q in defn["questions"]:  # a drawn answer, in red on the key: bars, plotted points, arrows
            if q.get("key_draw"):
                try:
                    drawings[q["q"]] = ws.answer_drawing(q["q"], q["key_draw"])
                except ValueError as e:
                    print(f"  Check: question {q['q']}'s key_draw: {e}.")
        WK.answer_key(ws, Path(args.out) / "answer-key.pdf", drawings)
    except Exception as e:  # the key is a convenience: a worksheet without one still prints and marks
        print(f"  (No answer-key.pdf: {type(e).__name__}: {e})")
    questions = [b for b in defn["questions"] if b["type"] != "passage"]
    print(f"Wrote {Path(args.out) / 'worksheet.pdf'} and answer-key.pdf: {n} page{'s' if n > 1 else ''}, {len(questions)} question{'s' if len(questions) != 1 else ''}, "
          f"{sum(q['points'] for q in questions):g} points. Style {defn['style']} (grade {defn['grade']}), "
          f"{defn['id_digits']}-digit IDs.")
    for page, free, blocks in zip(layout["pages"], layout["free_by_page"], layout["blocks_by_page"]):
        print(f"  page {page['page']}: {', '.join(f'{name} {h:.0f}pt' for name, h in blocks)} ({free:.0f}pt free)")
    _forms_report(layout, Path(args.out))
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
    shared = [lic for lic in layout["licenses"] if "-sa" in lic]
    if shared:
        print(f"  A passage is {shared[0].upper().replace('CC ', 'CC ')}: its credit line prints under it. Anyone may "
              "copy and share the worksheet; the adapted passage stays under the same license (the questions are the "
              "teacher's).")
    if any("-nc" in lic for lic in layout["licenses"]):
        print("  A passage is noncommercial (NC): fine for a class, not for selling.")
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


def _forms_report(layout: dict, out: Path) -> None:
    """The other forms make wrote: what each is, where it is, and how many pages."""
    forms = [f for f in layout["forms_made"] if f["id"]]
    if not forms:
        return
    versions = [f for f in forms if f["kind"] == "version"]
    variants = [f for f in forms if f["kind"] == "variant"]
    for f in versions:
        what = []
        if f.get("scaffolds"):
            what.append("scaffolds: " + ", ".join(f["scaffolds"]))
        if f.get("large_print"):
            what.append(f"large print ({f['large_print']:g}pt)")
        if f.get("space"):
            what.append(f"more room to write ({f['space']:g}x)")
        if f.get("per_page"):
            what.append(f"at most {f['per_page']} question{'s' if f['per_page'] > 1 else ''} a page")
        if f.get("max_choices"):
            what.append(f"{f['max_choices']} choices at most")
        if f.get("grid"):
            what.append("graph paper for work")
        if f.get("work_optional"):
            what.append("work optional on math (the answer earns full credit)")
        if f.get("language"):
            what.append(f"{f['language_name']} ({f['language_mode']})")
        if f.get("only"):
            what.append(f"only Q{', Q'.join(map(str, f['only']))}")
        copies = f" Print {f['copies']}." if f.get("copies") else ""
        print(f"  Version {f['label']}, {f['name']}: {out / f['pdf']}, {len(f['pages'])} page"
              f"{'s' if len(f['pages']) > 1 else ''}. {'; '.join(what) or 'as written'}.{copies}")
        pages_over = len(f["pages"]) - layout["base_pages"]
        if pages_over > 0 and f.get("language_mode") == "bilingual":  # a translation under each question takes room
            print(f"    Version {f['label']} runs to {len(f['pages'])} pages, {pages_over} more than the base sheet: "
                  "its translations take the room. That's expected for a bilingual sheet; nothing to cut.")
        elif pages_over > 0 and not (f.get("large_print") or f.get("space") or f.get("per_page")):
            print(f"  Check: version {f['label']} runs to {len(f['pages'])} pages, {pages_over} more than everyone "
                  "else's, so it stands out. Shorten it (or the base sheet) until they match"
                  + (f": cut about {f['shortfall']:.0f}pt." if f.get("shortfall") else "."))
            for k, (free, blocks) in enumerate(zip(f.get("free_by_page", []), f.get("blocks_by_page", [])), start=1):
                print(f"    version {f['label']} page {k}: {', '.join(f'{name} {h:.0f}pt' for name, h in blocks)} "
                      f"({free:.0f}pt free)")
        for note in f.get("print_notes", []):
            print(f"  Check: version {f['label']}: {note}.")
        if f.get("untranslated_comments"):
            print(f"  Check: comments for version {f['label']} are in {f['comment_language']}, but the translation has "
                  f"no words for {', '.join(f['untranslated_comments'])}, so those print in English only. Add them "
                  "(see \"Comments in a home language\" in references/versions.md).")
        if f.get("comment_language_dropped"):
            print(f"    Comments for these students will be in {f['comment_language']}: "
                  f"{f['comment_language_dropped']} can't print on the marked page here. Their Word page carries "
                  "the translation.")
        if f.get("modifies"):
            print(f"    Help that changes what's measured: {', '.join(f['modifies'])}. Scores on those questions show "
                  "what students do with help, and progress reports mark them \"with help on the page\". For "
                  "test-like checks, use what each student's plan lists.")
        quality = f.get("language_quality")
        if quality in ("medium", "low", "unknown") and not f.get("reviewed"):
            print(f"  Check: Claude's {f['language_english']} isn't reliable enough to print unchecked. Ask the teacher to have a bilingual adult read the translation, then add "
                  "\"reviewed_by\" (a role, not a name: \"bilingual aide\") to the translation file"
                  + ("; until then, keep it to key words and directions" if quality != "medium" else "") + ".")
    for note in layout.get("variant_notes", []):
        print(f"  Check: {note}.")
    if variants:
        pages = len(variants[0]["pages"])
        print(f"  {len(variants)} different copies, one per student: {out / 'copies.pdf'} ({len(variants)} x {pages} "
              f"page{'s' if pages > 1 else ''}; print it once, single-sided{' or double-sided' if pages > 1 else ''}, "
              f"and hand them out in any order). Every copy's answers: {out / 'copies-key.pdf'}.")
    for note in layout["version_notes"]:
        print(f"  {note}")
    print("  Every form has its own page code: scan them together in one stack, and marking sorts them out.")


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
    if ok and not manifest["id_sheets"]:  # every page made for one student, with its ID printed
        S.write_json(work / "ids.json", {})
        manifest = P.route(work)  # still catches a sheet fed twice
        pile = [p for p in manifest["pages"] if p["status"] == "review"]
        for p in pile:
            print(f"  scan {p['scan_index']} -> review pile: {p['reason']}")
        print("\nThe IDs are printed on these sheets, so there's nothing to read. Next: run `todo`.")
    elif ok:
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
    manifest = S.read_json(Path(args.work) / "manifest.json")
    unread = [p for p in manifest["pages"] if p["status"] == "ok" and not p["student_id"]]
    if unread:  # `ids` hasn't run: no page belongs to a student yet, so every work order would be empty
        print(f"The IDs on {len(unread)} page{'s' if len(unread) > 1 else ''} haven't been read yet. Read the ID "
              "strips into ids.json and run `ids` (SKILL.md, step 2), then run `todo` again.")
        return 1
    paths = P.todo(args.work)
    settled = P.settled_count(manifest)
    _blank_notes(manifest)
    if not paths:
        print(f"Nothing for Claude to mark ({settled} answers settled from the scan). Run `check` next.")
        return 0
    print(f"{settled} answers settled from the scan (blank, or one clear circle). Work orders to mark:")
    for path in paths:
        print(f"  {path}")
    assignment = Path(manifest["assignment_dir"])
    items = P.scanned_items(manifest, S.read_json(assignment / "key.json"), S.read_json(assignment / "layout.json"))
    marked = {int(path.stem[1:]) for path in paths}
    settled_qs = [str(q) for q in items if q not in marked]
    if settled_qs:
        print(f"Settled from the scan for every student, no work order: Q{', Q'.join(settled_qs)}.")
    return 0


def _docx_text(path: Path) -> str:
    """A Word file's text, a paragraph a line, table cells separated by " | "."""
    import re
    import zipfile
    from xml.sax.saxutils import unescape
    xml = zipfile.ZipFile(path).read("word/document.xml").decode()
    out = []
    for para in re.findall(r"<w:p[ >].*?</w:p>|<w:p/>", xml, flags=re.S):
        text = "".join(unescape(t) for t in re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.S))
        style = re.search(r'<w:pStyle w:val="(\w+)"', para)
        lead = {"Title": "# ", "Heading1": "## ", "Heading2": "### ", "ListParagraph": "- "}.get(
            style.group(1) if style else "", "")
        out.append(lead + text)
    return "\n".join(line for line in out if line.strip())


def cmd_preview(args) -> int:
    import pypdfium2 as pdfium
    from PIL import Image
    pdf = Path(args.pdf)
    if pdf.suffix.lower() == ".docx":  # a lesson plan: its text, to read through
        print(_docx_text(pdf))
        return 0
    out = pdf.parent / "preview"
    out.mkdir(exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf))
    # A shorter remake mustn't leave old pages behind. A full run replaces everything it makes; one page
    # (--page) replaces only itself, as a page image even with --sheet.
    for old in out.glob(f"{pdf.stem}-*.png"):
        # Only this PDF's own pages and sheets: copies.pdf's previews, not copies-key.pdf's.
        number = re.fullmatch(re.escape(pdf.stem) + r"-(p|sheet)(\d+)\.png", old.name)
        if not number:
            continue
        stale = number.group(1) == "p" and int(number.group(2)) > len(doc)
        if stale or (not args.page and (args.sheet and number.group(1) == "sheet" or not args.sheet)):
            old.unlink()
    if args.page:
        args.sheet = False
    try:
        pages = []
        for i in range(len(doc)):
            if args.page and i + 1 != args.page:
                continue
            img = doc[i].render(scale=1.5 if not args.sheet else 0.62).to_pil()
            pages.append((i + 1, img.convert("RGB")))
        if not args.sheet:
            for n, img in pages:
                path = out / f"{pdf.stem}-p{n}.png"
                img.save(path)
                print(path)
            return 0
        for start in range(0, len(pages), 9):  # nine to a sheet, numbered, for a first look at a deck
            group = pages[start:start + 9]
            cw, ch = group[0][1].size
            cols = min(3, len(group))
            sheet = Image.new("RGB", (cols * (cw + 12) + 12, -(-len(group) // 3) * (ch + 34) + 12), "white")
            from PIL import ImageDraw
            draw = ImageDraw.Draw(sheet)
            for k, (n, img) in enumerate(group):
                x, y = 12 + (k % 3) * (cw + 12), 12 + (k // 3) * (ch + 34)
                sheet.paste(img.convert("RGB"), (x, y + 22))
                draw.rectangle((x - 1, y + 21, x + cw, y + 22 + ch), outline=(150, 150, 150))
                draw.text((x, y + 4), f"{n}", fill=(0, 0, 0))
            path = out / f"{pdf.stem}-sheet{start // 9 + 1}.png"
            sheet.save(path)
            print(f"{path} (pages {group[0][0]}-{group[-1][0]})")
    finally:
        doc.close()
    return 0


def cmd_goover(args) -> int:
    try:
        from paper_loop_core import goover as G
        report = G.build(args.work, args.lesson, args.out, args.most)
    except ModuleNotFoundError as e:
        print(f"Can't make the slides: {e.name} isn't installed. Run `pip install python-pptx` and try again.")
        return 1
    except (ValueError, OSError) as e:
        print(f"Can't make the go-over deck: {e}")
        return 1
    except (KeyError, TypeError, IndexError, AttributeError) as e:
        print(f"Can't make the go-over deck: a field is missing or the wrong type ({type(e).__name__}: {e}). "
              "Check goover.json against references/lesson-format.md.")
        return 1
    out = report["out"]
    print(f"Wrote {out / 'go-over.pptx'} ({report['slides']} slides) and go-over.pdf, from "
          f"{report['students']} students. About 2 minutes a question.")
    for q in report["go_over"]:
        print(f"  Q{q}: {report['share'][q]:.0%} full credit, gone over")
    for q in report["left_out"]:
        print(f"  Q{q}: {report['share'][q]:.0%} full credit, left out (--most)")
    for q in report["got_it"]:
        print(f"  Q{q}: {report['share'][q]:.0%} full credit, on the \"got these\" slide")
    for warning in report["warnings"]:
        print(f"  Check: {warning}.")
    return 0


def cmd_lesson(args) -> int:
    try:
        from paper_loop_core import lesson as LS
        report = LS.build(args.lesson, args.out)
    except ModuleNotFoundError as e:
        print(f"Can't make the slides: {e.name} isn't installed. Run `pip install python-pptx` and try again.")
        return 1
    except (ValueError, OSError) as e:
        print(f"Can't make the lesson: {e}")
        return 1
    except (KeyError, TypeError, IndexError, AttributeError) as e:
        print(f"Can't make the lesson: a field is missing or the wrong type ({type(e).__name__}: {e}). "
              "Check it against references/lesson-format.md.")
        return 1
    out = Path(args.out)
    made = f"lesson-plan.docx, slides.pptx ({report['slides']} slides) and slides.pdf"
    if "go_over" in report:
        made += (f", go-over.pptx ({report['go_over']} slides) and go-over.pdf, answer-key.pdf, and a copy of "
                 "worksheet.pdf to print (marking uses the worksheet's own folder)")
    print(f"Wrote {out}: {made}.")
    spans = [f"{name} {r[0]}" + (f"-{r[1]}" if r[1] != r[0] else "") for name, r in zip(report["phases"], report["ranges"]) if r]
    if spans:
        print(f"  Slides by phase: {', '.join(spans)}.")
    for warning in report["warnings"]:
        print(f"  Check: {warning}.")
    return 0


def cmd_source(args) -> int:
    from paper_loop_core import sources as SR
    if args.site == "gutenberg" and not Path(args.name).is_file():
        book = args.name.strip() if args.name.strip().isdigit() else "<book number>"
        print(f"Can't get it: {SR.GUTENBERG.format(book=book)}.")
        return 1
    try:
        got = SR.gutenberg(Path(args.name)) if args.site == "gutenberg" else SR.wikipedia(
            args.name, simple=args.site == "simple", site="en.wikisource.org" if args.site == "wikisource" else None)
    except (S.WorksheetError, ValueError) as e:
        print(f"Can't get it: {e}")
        return 1
    except OSError as e:
        if getattr(e, "code", None) == 429:
            print(f"{args.site} is limiting requests right now. Wait a minute and run this again (don't add a name or "
                  "email to the request).")
            return 1
        print(f"Can't reach {args.site} from here ({e}). Use your web tool to open the page, save its text, and "
              "note the address (for Wikipedia, the \"Permanent link\" in the Tools menu, which names the revision).")
        return 1
    S.write_json(args.out, got)
    words = len(got["text"].split())
    grade = SR.reading_grade(got["text"][:6000])
    print(f"Saved {args.out}: \"{got['title']}\" ({words:,} words"
          + (f", about grade {grade:g} to read" if grade is not None else "") + f"), {got['license']}.")
    print(f"  Credit it with \"cite\": {json.dumps({'title': got['title'], 'author': got['author'], 'url': got['url'], 'license': got['license'], 'changes': '...'}, ensure_ascii=False)}")
    if got.get("check"):
        print(f"  Check: {got['check']}.")
    print("  Quote it exactly, or abridge and adapt it (say how in \"changes\": \"shortened\", \"simplified for grade "
          "4\"), and set \"reading_level\" to the grade you adapted it for.")
    return 0


def cmd_teamwork(command: str, argv: list[str]) -> int:
    """teamwork ACTIVITY.json --out DIR: role cards, the group's task, and what to cut out.
    groups FOLDER [--size 4] [--skill "..."] [--roster ids.csv] [--structure lab]: mixed-skill groups."""
    from paper_loop_core import teamwork as TW
    parser = argparse.ArgumentParser(prog=f"paper_loop.py {command}")
    if command == "teamwork":
        parser.add_argument("activity", type=Path)
        parser.add_argument("--out", type=Path, required=True)
    elif command == "teampoints":
        parser.add_argument("folder", type=Path)
        parser.add_argument("--worksheet", required=True, help="the exit sheet's assignment_id")
        parser.add_argument("--groups", type=Path, help="a groups-*.json (default: the newest in progress/)")
    else:
        parser.add_argument("folder", type=Path)
        parser.add_argument("--size", type=int, default=None, help="group size (default 4; 2 for pairs)")
        parser.add_argument("--seed", type=int, default=1, help="another number deals new first jobs")
        parser.add_argument("--skill")
        parser.add_argument("--roster", type=Path)
        parser.add_argument("--structure", default="lab", choices=list(TW.STRUCTURES) + ["game"],
                            help="the activity's structure, or game: groups with no jobs, never above --size")
        parser.add_argument("--similar", action="store_true",
                            help="similar-skill groups for targeted practice (default: mixed)")
    args = parser.parse_args(argv)
    try:
        if command == "teamwork":
            report = TW.build(args.activity, args.out)
        elif command == "teampoints":
            report = TW.team_points(args.folder, args.worksheet, args.groups)
        else:
            report = TW.form_groups(args.folder, args.size, args.skill, args.roster, args.structure,
                                    seed=args.seed, similar=args.similar)
    except (TW.TeamworkError, ValueError, OSError) as e:
        print(f"Can't make the {'group work' if command == 'teamwork' else 'team points' if command == 'teampoints' else 'groups'}: {e}")
        return 1
    if command == "teampoints":
        print(f"Wrote {report['pdf']} (to post: teams and points only) and {report['md']} (for you: each class ID's "
              f"points, against their average on {report['earlier']} earlier worksheets). Teams from "
              f"{report['groups'].name}.")
        for k, members, average in report["teams"]:
            print(f"  Team {k}: " + (f"{average:.0f}" if average is not None else "no exit sheets"))
        if report["unfinished"]:
            print(f"  Check: a page of {', '.join(report['unfinished'])}'s exit sheet isn't marked yet (the review "
                  "pile?), so they aren't counted. Finish the marking and run teampoints again.")
        return 0
    if command == "teamwork":
        print(f"Wrote {report['pdf']}: {report['structure']}, groups of {report['group_size']}.")
        for path in report.get("word_files", []):
            print(f"  {path}: a version in a script these pages can't shape. Print it from Word or Google Docs.")
        for name, first, last in report["pages"]:
            print(f"  {'page ' + str(first) if first == last else f'pages {first}-{last}'}: {name}")
        for w in report["warnings"]:
            print(f"  Check: {w}.")
        return 0
    kind = "similar" if report["similar"] else "paired" if args.structure == "pairs" else "mixed"
    how = f"{kind} by {report['skill'] or 'all skills so far'}" if report["mixed"] else "at random (nothing marked yet)"
    print(f"{len(report['groups'])} groups, {how} (for the teacher only): {report['path']}")
    for k, g in enumerate(report["groups"], start=1):
        print(f"  Group {k}: " + ", ".join(f"{sid} ({role})" if role else sid for sid, role in g))
    return 0


def cmd_practice(args) -> int:
    from paper_loop_core import practice as PR
    try:
        report = PR.build(args.work, args.out, args.most)
    except (ValueError, OSError) as e:
        print(f"Can't make practice sheets: {e}")
        return 1
    out = report["out"]
    print(f"Wrote {out / 'copies.pdf'}: a practice sheet for each of {report['sheets']} students, each with their "
          "class ID printed, the questions they missed (new numbers where the worksheet has them), and the comment "
          "they got last time above each one.")
    for sid, qs in report["questions"].items():
        print(f"  ID {sid}: Q{', Q'.join(map(str, qs))}")
    for note in report.get("extras", []):
        print(f"  Also print: {note}.")
    for note in report.get("notes", []):
        print(f"  Check: {note}.")
    if report["stretched"]:
        print(f"  Full credit on everything, a stretch sheet instead: IDs {', '.join(report['stretched'])}.")
    no_sheet = [sid for sid in report["all_right"] if sid not in report["stretched"]]
    if no_sheet:
        print(f"  Full credit on everything, no sheet: IDs {', '.join(no_sheet)}. Add 1-2 \"stretch\" questions to "
              "the worksheet so every student gets one (then a sheet says nothing about who struggled).")
    if report["absent"]:
        print(f"  Blank worksheet (absent?), no sheet: IDs {', '.join(report['absent'])}.")
    for sid, qs in report["left_off"].items():
        print(f"  ID {sid} also missed Q{', Q'.join(map(str, qs))}, left off (--most {args.most}).")
    if report["todo"]:
        print(f"Check: some last-time comments name the old copy's numbers; they print as \"Last time (other "
              f"numbers)\". For clearer sheets, write the notes {report['todo']} asks for, then run `practice` again.")
    print(f"Print copies.pdf and hand each student the sheet with their ID; {out / 'copies-key.pdf'} has every "
          f"student's answers. To mark them, scan them like any worksheet with --assignment \"{out}\": the IDs are "
          "printed, so there's nothing to read.")
    return 0


def cmd_progress(args) -> int:
    from paper_loop_core import progress as PG
    try:
        report = PG.build(args.folder, args.out, args.roster, args.class_name or "")
    except (PG.ProgressError, ValueError, OSError) as e:
        print(f"Can't make the progress report: {e}")
        return 1
    out = report["out"]
    print(f"Read {report['runs']} marked class{'es' if report['runs'] != 1 else ''}: {report['students']} students, "
          f"{len(report['skills'])} skill{'s' if len(report['skills']) != 1 else ''}.")
    print(f"  {out / 'dashboard.html'}: the teacher's dashboard (opens in any browser; nothing leaves the computer)")
    print(f"  {out / 'parents.docx'}: a page for each family, with a line to write the student's name")
    print(f"  {out / 'progress.csv'}: each student's latest score on each skill, for a gradebook")
    if report.get("supported"):
        print(f"  {out / 'supports.csv'}: which version and supports each class ID had on each worksheet "
              f"({report['supported']} rows), for a case manager's records")
    for lang, path in report["made"].items():
        if lang != "en":
            print(f"  {path}: family pages in {lang}")
    for skill, groups in report["groups"].items():
        if groups["practicing"]:
            print(f"  Still practicing \"{skill}\": IDs {', '.join(groups['practicing'])}")
    for lang in report["unreviewed"]:
        print(f"  Check: the {lang} family pages haven't been read by a bilingual adult. Before they go home, have "
              f"one check them (a qualified adult, not a student or a sibling), then add \"reviewed_by\" (a role) "
              f"to parents.{lang}.json.")
    if report["in_language"]:
        print(f"  parents.docx leaves out IDs {', '.join(report['in_language'])}: their pages are in their family's "
              "language.")
    if report["missing"] or report["languages"]:
        print(f"Next: fill in what {out / 'progress-todo.md'} lists (skills in everyday words and things to try at "
              "home" + (", and family pages in other languages" if report["languages"] else "") +
              "), then run `progress` again.")
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
    if not (work / "todo").exists() and not any((work / "marks").glob("q*.json")):
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
    if len(sys.argv) > 1 and sys.argv[1] == "pieces":  # cards, games, and foldables: their own small CLI
        from paper_loop_core import pieces
        return pieces.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in ("teamwork", "groups", "teampoints"):
        return cmd_teamwork(sys.argv[1], sys.argv[2:])
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
    p.add_argument("--sheet", action="store_true", help="nine pages to an image, for a first look at slides")
    p.set_defaults(func=cmd_preview)
    p = sub.add_parser("lesson")
    p.add_argument("lesson", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=cmd_lesson)
    p = sub.add_parser("goover")
    p.add_argument("work", type=Path)
    p.add_argument("--lesson", type=Path)
    p.add_argument("--out", type=Path, help="where the deck goes (default: WORK/out)")
    p.add_argument("--most", type=int, help="go over only this many questions, the most missed")
    p.set_defaults(func=cmd_goover)
    p = sub.add_parser("practice")
    p.add_argument("work", type=Path, help="a marking folder whose marks `check` has accepted")
    p.add_argument("--out", type=Path, help="where the practice worksheet goes (default: beside the worksheet)")
    p.add_argument("--most", type=int, default=3, help="questions per student, the ones they did worst on (default 3)")
    p.set_defaults(func=cmd_practice)
    p = sub.add_parser("source")
    p.add_argument("site", choices=["wikipedia", "simple", "wikisource", "gutenberg"],
                   help="wikipedia, simple (Simple English Wikipedia), wikisource (primary sources), or gutenberg")
    p.add_argument("name", help="the article's title, or for gutenberg the book's plain-text file the teacher "
                                "downloaded")
    p.add_argument("--out", type=Path, required=True, help="where to save it (a .json file)")
    p.set_defaults(func=cmd_source)
    p = sub.add_parser("progress")
    p.add_argument("folder", type=Path, help="the folder that holds this class's worksheets and marking folders")
    p.add_argument("--out", type=Path, help="where the reports go (default: FOLDER/progress)")
    p.add_argument("--roster", type=Path, help="only these class IDs (a CSV), for one class period")
    p.add_argument("--class-name", help="the name printed on the reports (default: the folder's name)")
    p.set_defaults(func=cmd_progress)
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
    for name in ("pieces", "teamwork", "groups", "teampoints"):  # handled above; listed so --help shows them
        sub.add_parser(name, help=f"see `paper_loop.py {name} --help`")
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
