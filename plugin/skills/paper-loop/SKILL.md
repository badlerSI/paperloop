---
name: paper-loop
description: Turns the school copier into a feedback machine for any subject, grades 2-12. Makes printable worksheets (reading passages, short and rubric-scored written answers and multi-page essays, multiple choice, fill-in-the-blank, matching, tables, show-your-work math, labeled diagrams, maps, graphs and bar charts, drawings, code listings, chemical equations, music on a staff) that can be marked from a scan, and marks scanned class sets of them - reads every answer, writes a short comment beside it, and returns one PDF of marked pages to print and hand back. Use when a teacher wants a worksheet made for Paper Loop, or has a scan of completed Paper Loop worksheets to mark, grade, or give feedback on.
---

# Paper Loop

Students do a worksheet on paper. The teacher scans the stack on the school copier. You read every answer
and write a short comment beside it. The teacher checks anything you flagged, then prints the marked pages
and hands them back. The scripts handle the paper: lining up pages, cropping answers, reading circled
letters, and laying out the PDF. You do the reading and judging.

Run the scripts as `python3 <this skill's folder>/scripts/paper_loop.py <command>`, written `PL` below.
They need numpy, scipy, Pillow, pypdfium2, and reportlab, which Claude's sandboxes include. If an import
fails, `pip install` the missing one.

## Privacy: always

- Students write a class ID number (4 digits, or 2 for grades 2-3), never their name. Never ask for,
  accept, or write down student names. If the teacher offers a roster with names, ask for a CSV of just
  the ID numbers. Many teachers already give each student a class number; that works.
- Look only at the crops and ID strips the scripts make. Don't open the scanned PDF or the full page
  images: the crops leave out everything else a student wrote on the page.
- If a crop shows a student's name or other personal details, don't repeat them. Tell the teacher which
  scan has a name on it.
- On a teacher's own Claude for Teachers account, student work must stay de-identified unless their
  school or district has authorized Claude for student records. If the teacher plans to use names or
  district student numbers, tell them that first.

## Making a worksheet

1. Find out the subject, grade, topic, how many questions, and whether it must fit on one page. Ask only
   for what the teacher hasn't said. If they gave you a lesson, a standard, or their own worksheet, build
   from that. Comments on wrong answers give hints, not answers, unless the teacher asks otherwise
   (`feedback` in the format guide).
2. Read `references/worksheet-format.md`, then the example in `references/examples/` closest in grade and
   subject. Write the worksheet as JSON. Mix question types. Write keys as what full credit needs, rubrics
   with levels a stranger could apply, and drawing checklists as things you can see on the page. Reading
   passages must be your own writing or public domain. A picture the teacher supplies (a map, a photo) goes
   beside the JSON, referenced by its file name.
3. Save the JSON as `<folder>/<assignment_id>.json` and run
   `PL make "<folder>/<assignment_id>.json" --out "<folder>/<assignment_id>"`. `<folder>` is wherever the
   teacher keeps worksheets. It reports each page's blocks with their heights, its free space, and how many
   points to cut to lose a page. Fit the page the teacher asked for:
   shorten prompts, use fewer lines, or shrink work areas and diagrams, then run it again. To change the
   worksheet, edit your JSON and run `make` again, not the `worksheet.json` copy it keeps. For a passage with
   line numbers, `make` prints the numbered lines: check that every line your questions cite says what you
   think it says.
4. Look at every page before giving it to the teacher: `PL preview "<folder>/<assignment_id>/worksheet.pdf"`
   saves each page as a PNG (use `PL zoom` on it to look closer). Check that nothing overlaps, that diagrams
   look like what they're meant to be, and that label boxes and leader lines point at the right things.
5. Give the teacher `<folder>/<assignment_id>/worksheet.pdf` to print, along with anything `make` printed as
   notes for them. Keep the folder: marking needs `layout.json` and `key.json` from it.

## Marking a scan

You need the scan PDF and the assignment folder `make` wrote. Use a new work folder for each scan, such as
`<assignment folder>/marking-<date>`. Folder names often have spaces or apostrophes, so put every path in
double quotes. If you lose track at any point, `PL status "<work>"` says what's next.

1. **Prepare.** `PL prepare "<scan.pdf>" ["<more.pdf>"] --assignment "<folder>" --work "<work>"`. Pages
   can be in any order and orientation, and fronts and backs can be separate PDFs. Phone photos work too
   (JPG or PNG, one page per photo): each page flat, all four corner squares in the frame, no glare on
   them. iPhone HEIC photos need converting to JPEG first (sharing or exporting them usually does it). It lists pages it
   couldn't use, empty sheets that went through the copier (left out of the printout), and the ID strip
   image for each page it could.
2. **Read the IDs.** Look at the ID sheets `prepare` lists (up to 20 strips each, labeled with scan
   numbers; open a single strip if one is hard to read) and write `<work>/ids.json` (rules: "ids" in
   `references/marking-rules.md`). Then run `PL ids "<work>"`, adding `--roster "<ids.csv>"` if the teacher
   has a class list of ID numbers. The script accepts a read at 0.9 confidence or more. With a roster, it
   also accepts a read down to 0.5 if that ID is on the roster and no other roster ID is one digit away:
   a one-digit slip can't then hand a classmate's work to this student. So suggest a roster if several
   pages land in the review pile.
   - A roster is a CSV with a column named `id` (or a single column), one ID per row. Leading zeros that a
     spreadsheet dropped are fine: `6` means `0006`. If the teacher types the IDs in chat, write the CSV.
   - With 2-digit class numbers (grades 2-3), most IDs are one digit from another, so a roster mostly
     catches numbers that aren't in the class; reads still need 0.9.
3. **Get the work orders.** `PL todo "<work>"` writes `todo/qN.md` for each question with answers to mark.
   Blank answers and clearly circled letters are already settled, with the comments the worksheet itself
   provides ("No answer yet", or the reason printed for each choice), so there's nothing to review there.
   It also lists students whose every answer is blank (absent, or their work is on another sheet) and pages
   left blank by a student who did the rest (a missed back side, or out of time). Tell the teacher about
   both. An essay's later pages aren't listed when they're blank: a short essay often stops early. Those pages are still in the printout, with "No answer yet" beside each question, and the teacher
   can pull them out.
4. **Mark one question at a time, across the whole class**, the way a teacher marks a stack. For each
   work order: read the rules for its type in `references/marking-rules.md`; look at the blank crop
   first when there is one (labels, drawings, tables); then look at every crop it lists. If a detail is too faint or small to
   judge (an arrowhead, a crossed-out letter, a single word), zoom in with
   `PL zoom "<crop>" [--region left,top,right,bottom]`, where the region is in fractions of the image
   (`0.5,0,1,0.5` is the top-right quarter). It saves an enlarged, darkened copy and prints its path.
   Write `<work>/marks/qN.json` in the shape the work order shows.
   If you can start subagents, give each question to its own subagent and run them in parallel. Brief
   each one with the work order's path, the rules file's path, and the output path, and tell it to look
   only at the crops listed. Otherwise, mark the questions in order and write each file before starting
   the next.
5. **Check and summarize.** Run `PL check "<work>"` and fix every error it lists, shortening any comment it
   says is too long. When the marks are clean (no errors, no comments too long), it writes
   `<work>/summaries/todo.md`. Write
   `<work>/summaries.json` from that file (rules: "summary"): one summary per student, keyed by student ID,
   printed on their last page. Then run `check` again until it reports both the marks and the summaries are
   clean.
6. **Teacher review.** `check` lists each flagged answer with how it's scored for now. A flagged answer
   prints exactly as marked: an "unclear" checklist item, and an unreadable label or answer, earn nothing
   until the teacher decides otherwise.
   - If the teacher is there, show each one: the crop, what you read, the verdict, the comment, and what
     would change if they decide differently (for a rubric, which criterion is in doubt). Make any change
     in the marks file, add `"reviewed": true` to that mark, and run `check` again.
   - If the teacher has said to print without reviewing, use `--accept-flags` in the next step. List every
     flag in your report the same way: the crop's path, what you read, how it's scored, and what changes if
     they decide the other way.
7. **Render.** `PL render "<work>"`, adding `--accept-flags` if the teacher said to print flags as marked
   (it isn't needed when nothing is flagged), `--grade back` to put the score on the last page, or
   `--grade csv` for a gradebook file (use one when the teacher asks for scores or grades). By default no score is printed. Give the teacher
   `<work>/out/returned.pdf` and say whether to print it single- or double-sided. If there's a
   `review_pile.pdf`, say which pages are in it and why. Those are usually a smudged or missing ID, which
   the teacher can sort by hand.

The printed page shows each comment beside its question, a check or cross on each box the student wrote in
and on each math answer box, the drawing checklist and (from grade 6) rubric scores under the comment, and
the student's summary on their last page. Your transcriptions, drawing descriptions, and notes aren't
printed. They're for the teacher and for checking.

## Reporting back

Keep it short. Say how many students were marked, what you flagged and what the teacher decided, any pages
in the review pile, empty sheets, and students or pages with every answer blank. Then give one or two
patterns across the class that would change tomorrow's lesson, such as "most students think heavier
objects fall faster". With fewer than about six students there's no pattern to report: say what each
student needs next instead.
