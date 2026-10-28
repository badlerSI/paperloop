---
name: paper-loop
description: "Turns the school copier into a feedback machine for any subject, grades 2-12. Makes printable worksheets that can be marked from a scan (passages, written answers and essays, multiple choice, tables, show-your-work math, labeled diagrams, graphs, drawings, chemical equations, music), in versions with scaffolds, IEP accommodations, or home-language translations, a different copy for each student, or enrichment from free sources like Wikipedia. Plans lessons with a Word plan and PowerPoint slides. Makes group work where students teach each other (labs, jigsaws, peer tutoring, with role cards) and paper review games. Marks scanned class sets: reads every answer, writes a comment beside it, and returns marked pages to hand back, then a go-over deck, practice sheets, a progress dashboard, and family pages. Use when a teacher wants a worksheet, lesson, slides, differentiated copies, group activity, review game, or progress report, or has a scan of completed Paper Loop worksheets to mark or grade."
---

# Paper Loop

Students do a worksheet on paper. The teacher scans the stack on the school copier. You read every answer
and write a short comment beside it. The teacher checks anything you flagged, then prints the marked pages
and hands them back. The scripts handle the paper: lining up pages, cropping answers, reading circled
letters, and laying out the PDF. You do the reading and judging.

Run the scripts as `python3 <this skill's folder>/scripts/paper_loop.py <command>`, written `PL` below.
They need numpy, scipy, Pillow, pypdfium2, and reportlab, and python-pptx for slides, which Claude's
sandboxes include. If an import fails, `pip install` the missing one. `PL source` needs the internet; if the
sandbox can't reach the site, use your web tool and save the text yourself. `PL preview` puts page images in a
`preview` folder beside the file, for you to check; delete those folders before you give the teacher the files.

## Privacy: always

- Students write a class ID number (4 digits, or 2 for grades 2-3), never their name. Never ask for,
  accept, or write down student names. If the teacher offers a roster with names, ask for a CSV of just
  the ID numbers. Many teachers already give each student a class number; that works.
- Look only at the crops and ID strips the scripts make. Don't open the scanned PDF or the full page
  images: the crops leave out everything else a student wrote on the page. The crops reach a little below
  each writing box, and a work order adds a crop of the whole question when there's writing outside its
  box, so an answer that runs over is still in view.
- If a crop shows a student's name or other personal details, don't repeat them. Tell the teacher which
  scan has a name on it.
- On a teacher's own Claude for Teachers account, student work must stay de-identified unless their
  school or district has authorized Claude for student records. If the teacher plans to use names or
  district student numbers, tell them that first.
- Never send the teacher's or a student's name, email, or other details to a website, such as in a request
  header or a search.
- Never ask for or record who has an IEP or 504 plan, who is learning English, or anything else about a
  student's background. The teacher hands out versions to whoever needs them; Paper Loop only knows which
  form a class ID turned in. Family pages have a line where the teacher writes the name by hand.

## Making a worksheet

1. Find out the subject, grade, topic, how many questions, and whether it must fit on one page. Ask only
   for what the teacher hasn't said. If they gave you a lesson, a standard, or their own worksheet, build
   from that. Comments on wrong answers give hints, not answers, unless the teacher asks otherwise
   (`feedback` in the format guide).
2. Read `references/worksheet-format.md`, then the example in `references/examples/` closest in grade and
   subject. Write the worksheet as JSON. Mix question types. Write keys as what full credit needs, rubrics
   with levels a stranger could apply, and drawing checklists as things you can see on the page. Give each
   question the `skill` it practices, so progress reports can follow it. For a reading, start from a free,
   human-written source (Wikipedia, Simple English Wikipedia, Project Gutenberg, a US government site:
   `PL source`) and credit it with `cite`; otherwise write it yourself. A picture the teacher supplies (a
   map, a photo) goes beside the JSON, referenced by its file name.
   - If some students need supports (scaffolds, large print, more room, a home language) or the teacher
     wants a different copy for each student (homework), read `references/versions.md` and add `versions`
     or `variants`. One scan of every copy marks them all.
   - Enrichment ("something more for the ones who finish", "go deeper on X") is a worksheet too: a
     reading from a free source, adapted for the grade, with questions that stretch.
   - Add one or two `stretch` questions (format guide): after marking, students with full credit practice
     those, so every student gets a practice sheet.
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
5. Give the teacher `<folder>/<assignment_id>/worksheet.pdf` to print and `answer-key.pdf` (the sheet with
   its answers written in), or `copies.pdf` when each student gets their own copy (with `copies-key.pdf`,
   every copy's answers), along with anything `make` printed as
   notes for them: each version's PDF and how many to print, Word pages for home languages, reference pages,
   and any translation a bilingual adult should check before it prints. Keep the folder: marking needs
   `layout.json` and `key.json` from it.

## Planning a lesson

When the teacher wants a lesson plan or slides, offer a worksheet to go with it, since it's what Paper Loop
marks; if they want one, make it first (above), then the lesson around it. A lesson without a worksheet
works too. The plan reminds the teacher to bring marked copies when the lesson opens with a `review`, so
don't list them in `materials` too.

1. Find out the class length and anything the teacher wants included (a standard, a text, an activity, a
   warm-up routine). Ask only for what they haven't said.
2. Read `references/lesson-format.md`, then the example lesson in `references/examples/` closest in grade
   and subject. Write the lesson as JSON: a timed sequence of phases with their slides, and a walkthrough
   for every worksheet question (the idea it tests, the steps, the likely mistakes). Put what the teacher
   says in each slide's `say`, and keep the slides to a few words.
3. Save it as `<folder>/<lesson_id>.json` beside the worksheet's JSON and run
   `PL lesson "<folder>/<lesson_id>.json" --out "<folder>/<lesson_id>"`. Fix every `Check:` line it prints.
4. Look at the slides: `PL preview "<folder>/<lesson_id>/slides.pdf" --sheet` (nine slides to an image),
   then `go-over.pdf` the same way. Check that text fits, pictures are readable, and each answer is
   written in the right box. Change the JSON and run `lesson` again to fix anything.
5. Give the teacher `lesson-plan.docx`, `slides.pptx`, `go-over.pptx`, and `answer-key.pdf`, with the
   worksheet. The .pptx files open in PowerPoint, Keynote, or Google Slides; the .pdf copies are the same
   slides, for presenting from any computer.

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

8. **Go-over deck** (when the teacher wants one, or offer it): run `PL goover "<work>"`, adding
   `--lesson "<lesson file>"` if there's a lesson for this worksheet and `--most N` to fit the time (about
   2 minutes a question). Then write `<work>/goover.json` with what you saw on each question it goes over
   (`<work>/out/go-over-todo.md` lists the answers that missed, if you didn't mark this scan yourself), and
   run it again. Give the teacher `<work>/out/go-over.pptx`: most-missed questions first, each with how
   the class answered and its answer worked through, ending with a "Fix it" slide for the marked copies.
   If you're planning the next day's lesson, open it with a `"review"` phase instead: the same slides go
   into that lesson's deck. Details: the end of `references/lesson-format.md`.
9. **Practice sheets** (offer them when several students missed things):
   - Run `PL practice "<work>"`. It makes a sheet for each student with the questions they missed, the
     comment they got last time above each one, and new numbers where the worksheet has variables.
   - Each sheet has the student's ID printed. Students can do them as homework or a warm-up.
   - Scan them back like any worksheet (`prepare` with `--assignment` set to the practice folder), then go
     straight to `todo`: there are no IDs to read.
   - Details: `references/versions.md`.

The printed page shows each comment beside its question, a check or cross on each box the student wrote in
and on each math answer box, the drawing checklist and (from grade 6) rubric scores under the comment, and
the student's summary on their last page. Your transcriptions, drawing descriptions, and notes aren't
printed. They're for the teacher and for checking.

## Cards, games, and foldables

For review that isn't a worksheet: "make flashcards", "a review game for Friday", "something hands-on for
centers", or anything a teacher would otherwise do with Quizlet, Kahoot, or Blooket.

1. Read `references/pieces-format.md`, then the closest example in `references/examples/` (`*-pieces.json`).
   Write one file of question-and-answer cards, with a level from 1 to 3 on each, and the pieces to make:
   - fold-over cards (no two-sided printing), and blank cards for students to write their own;
   - board games for any checker or chess board and a die: Snake Race, Question Checkers, Four in a Row,
     Chess Quiz;
   - a printable board, a paper die, a spinner, and tent pawns;
   - a fortune teller, an eight-page mini-book from one sheet, ABCD answer cards for the whole class, and
     bingo.
2. Run `PL pieces "<folder>/<name>-pieces.json" --out "<folder>/<name>-pieces"`. Fix every `Check:` line it
   prints, then look at every page full size with `PL preview "<folder>/<name>-pieces/pieces.pdf"`.
3. Give the teacher `pieces.pdf`. Its first page lists what's in it, what to print on, prep time, and
   materials.

Cards work best when every card makes students recall an answer before they check it, so write questions,
not facts to read. Making their own cards is good practice too.

To group students for a card game (similar skills at a center, say), run `PL groups "<class folder>"
--structure game --size 4 --similar`: groups with no jobs, never more players than the game takes (for a
two-player game, an odd one out joins a pair, and the three take turns). When the
teacher also wants an exit sheet, roles, or a game on its own board (a number line, a grid), build it as a
lab under "Group work and labs", with a `board`.

## Group work and labs

When a teacher wants students working together: "a lab", "group roles", "a jigsaw", "peer tutoring",
"students helping each other", or a paper version of a simulation (PhET, NOVA Labs, Gizmos).

1. Read `references/teamwork-format.md` and the closest example in `references/examples/` (`*-teamwork.json`).
   Pick the structure: a `lab` for an investigation with dice, tokens, or measuring; `pairs` for practice
   with right answers; `reciprocal` for a reading; a `jigsaw` when the topic splits into 3-5 parts; `heads`
   for quick review. Take ideas from simulations and online labs, but write the text and questions yourself,
   and use real data where it's free (the format's last sections say which sources allow what).
2. Write the exit sheet first: a worksheet each student does alone at the end, made with `PL make` like any
   other, in the same folder (one page; two is fine in grades 2-3). Then write the activity with
   `"worksheet"` set to its id. A reading for `reciprocal` or `jigsaw` comes from `PL source` like any
   passage: put its credit line in the part's `source`.
3. Run `PL teamwork "<folder>/<name>-teamwork.json" --out "<folder>/<name>-teamwork"`, fix every `Check:`
   line, and look at every page full size: `PL preview "<folder>/<name>-teamwork/teamwork.pdf"` (not
   `--sheet`, which is too small to judge type).
4. Groups: run `PL groups "<class folder>" --size <the activity's group_size> --structure <structure> --roster
   "<ids.csv>"` (with nothing marked and no roster, ask the teacher for a CSV of class ID numbers). With marked
   work it mixes skill in each group (`--similar` instead puts like skills together, for practicing one
   skill, listed from highest to lowest for the teacher; `--skill "..."` sorts by one skill); with nothing
   marked, it groups at random. Give the teacher `progress/groups-<structure>.md` (`-similar` when similar).
   It uses class IDs only, and stays with the teacher: never write on student pages why a student is in a
   group.
5. Give the teacher `teamwork.pdf` and the exit sheet. Page 1 is theirs: what to print (with page numbers),
   materials, and how to run it.

For students who need other words, add `versions` to the activity (plain English, or a home language) the way
a worksheet has versions: same work, their words. After the class, mark the exit sheets like any worksheet:
that's what shows each student learned it. Then `PL teampoints "<class folder>" --worksheet <exit sheet id>`
scores each team by its members' improvement, a page to post with no names or IDs on it.

## A Paper Loop sample

Teachers can print sample worksheets from the Paper Loop website and fill them in to try it out. When a
teacher shares a photo or scan of a page with a "Try Paper Loop" box, the box and the footer name the
sample (such as `sample-ratios-gr6`):

1. Rebuild it: run `PL make "<this skill's folder>/references/samples/<sample id>.json" --out "<folder>/<sample
   id>"`. The `<folder>` is the teacher's worksheets folder, or a "Paper Loop samples" folder. This makes
   the same sheet and its answer key.
2. Mark the photo as in "Marking a scan", with that folder as the assignment. A phone photo works when all
   four corner squares are in it. Any number in the ID boxes will do.
3. Give the teacher the marked page, and in a few lines say what Paper Loop did at each step:
   - it lined the page up;
   - it read the circled letters itself;
   - you read the rest and wrote the comments;
   - it flagged anything you were unsure of.

   Then offer to make a worksheet for their own class.

If the sample id isn't in `references/samples/`, it comes from a newer version of the plugin: say so, and
offer to make a worksheet like it instead.

## Progress across worksheets

When the teacher asks how the class or a student is doing over time, or wants something for families:

1. Run `PL progress "<folder>"`, where the folder holds the class's worksheets and their marking folders.
   Add `--roster "<ids.csv>"` for one class period, and `--class-name "Period 3 Math"`. It reads every
   marked class under the folder and writes `<folder>/progress/`:
   - `dashboard.html`: the teacher's dashboard, one file that opens in any browser and needs no internet.
     It shows each skill, student by student (got it, getting there, still practicing), groups for the
     next lesson, how each worksheet went, what marking noticed, and, for students who had help on the
     page, whether it's fading as their scores hold.
   - `parents.docx`: a page for each family in plain words. It covers what the class is learning, how
     their child is doing on each skill, their latest feedback, and something to try at home. A line for
     the teacher to write the name.
   - `progress.csv`: the latest score on each skill, for a gradebook.
   - `supports.csv`: which version and supports each class ID had on each worksheet, the record a case
     manager keeps (when any student had a version).
2. If it lists a `progress-todo.md`, fill in what it asks, then run it again:
   - `skills.json` in the folder: each skill in everyday words, and a ten-minute thing to try at home with
     nothing a family might not have.
   - Family pages in another language: `families.json` maps a class ID to a language code, such as
     `{"0412": "es"}`. List only families who asked for school letters in another language (the home
     language survey records this), and ask which language they *read*. Write `parents.<code>.json` with the
     translated labels, skills, and each student's latest feedback, in the shape `progress-todo.md` shows.
     A bilingual adult (not a student or a sibling) reads it before it goes home. After they have, add
     `"reviewed_by"` with their role. `families.json` records a family's language, so it belongs where the
     teacher keeps student records. Delete it when it's no longer needed.
3. Tell the teacher what the dashboard shows that matters: the skills most students are still practicing,
   and the groups for the next lesson.
   - Scores on questions that printed help (hints, worked examples, steps, or fewer choices) are marked
     "with help on the page".
   - Each status comes from the skill's most recent new evidence: a later worksheet, or a practice sheet
     with new numbers. Practicing the very same question again doesn't change a status.
   - Family pages don't replace IEP progress reports; the case manager writes those.

## Reporting back

Keep it short. Say how many students were marked, what you flagged and what the teacher decided, any pages
in the review pile, empty sheets, and students or pages with every answer blank. Then give one or two
patterns across the class that would change tomorrow's lesson, such as "most students think heavier
objects fall faster". With fewer than about six students there's no pattern to report: say what each
student needs next instead.
