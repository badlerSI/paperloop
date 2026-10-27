# Lesson plans and slides

October 27, 2026. Paper Loop now plans the lesson around the worksheet, and goes over the worksheet
afterward, inside the same Cowork plugin. There's still no API key and nothing to install: it runs on the
Claude a teacher already has through Claude for Teachers.

## What a teacher gets

Ask "Plan a 50-minute 6th grade lesson on equivalent ratios with slides and a Paper Loop worksheet", and
Claude writes one lesson file (JSON) beside the worksheet. `PL lesson` turns it into:

| File | What it is |
| --- | --- |
| `lesson-plan.docx` | Objectives (and student-facing "I can" targets), standards, materials, vocabulary, a timed sequence with the slide numbers for each phase, checks for understanding, misconceptions with responses, differentiation (support, extension, multilingual learners), assessment, homework, and every worksheet answer worked through. |
| `slides.pptx` + `slides.pdf` | The lesson in order: title, learning targets, agenda, then each phase's slides, with what to say in the speaker notes. |
| `go-over.pptx` + `go-over.pdf` | Each worksheet question as printed, then the same question with the key's answers written in, the idea it tests, the steps, and the likely mistakes. |
| `answer-key.pdf` | The worksheet with every answer filled in, and the key beside each question. |

After marking, `PL goover` builds a better go-over deck from the class's results: how each question went,
then the most-missed questions first, each with how the class answered and then the answer worked through.

## How it's built

- **One lesson file, Claude's judgment in it, layout in the scripts.** Claude writes the teaching: phases,
  slide text, speaker notes, the walkthrough of each question. The scripts do every pixel: sizes for the
  grade, colors for the subject, text that fits, and pictures of the worksheet.
- **Slides are classroom slides.** Type is sized for the back row: titles 36-44pt and body 26-32pt by grade
  band, with a words-per-slide limit (45 for grades 2-3, 70 for 4-8, 90 for 9-12) that `lesson` warns
  about. The teaching goes in the speaker notes. Text shrinks to fit down to a floor, then warns.
- **Slide types**: points (with a picture or diagram beside them), worked examples (optionally revealed
  one step per slide), vocabulary cards, class questions (multiple choice cards, then the answer
  highlighted with why), compare, passages and code (with line numbers), and section dividers. Diagrams
  use the worksheet diagram format, so number lines, axes, fraction bars, staffs, and bar charts all work
  on slides.
- **The worksheet, as printed.** A question slide is a crop of worksheet.pdf at 300 dpi, so students see
  exactly what's on their sheet. The answers go on top as separate, editable text and circles placed from
  layout.json: words in label, blank, match, and table boxes; the right letter circled; a math answer
  beside the steps. A drawing question's answer is drawn on in color from shapes Claude gives
  (`plot` points on the question's axes, `mark` points on its number line, or any diagram shape).
- **Readings and code come first.** Before the first question about a passage, the deck shows the
  passage: as big native text when its printed lines are short (code, a poem), else as printed.
- **Two outputs from one layout.** Every slide is a list of placed elements, written once as an editable
  .pptx (python-pptx: real title placeholders, bullets, native charts, speaker notes, slide-number fields)
  and once as a PDF (reportlab). Text is measured in Helvetica, which has Arial's widths, and the .pptx
  names Arial, so lines break in the same places. Characters Helvetica lacks (π, →, ≤) are drawn from
  DejaVu Sans in the PDF; PowerPoint finds them in its own fonts.
- **The plan is a real Word file.** python-docx isn't in every sandbox, so `wordfile.py` writes the
  .docx's XML itself: styles, headings, bullets, numbered steps, and tables with a shaded header row.
- **Go-over decks never point at a student.** Only class totals appear, and a wrong answer is shown only
  when two or more students gave it.
- **Go-over decks fit the time.** About 2 minutes a question; `--most N` takes only the N most missed.
  The first run writes `go-over-todo.md` with the wrong answers and their crops, so a session that didn't
  do the marking can see what went wrong before writing what it noticed.
- **It runs on older sandboxes.** Built and checked with python-pptx 1.0.2 and 0.6.22, the oldest that
  runs on current Python.

## Checks

- The .pptx and .docx files pass the validator from Anthropic's own pptx and docx skills
  (`scripts/office/validate.py`: schema, relationships, content types), and python-pptx and python-docx
  read them back.
- Five example lessons build with no warnings (after the fixes below): grade 3 science (plant parts), grade 5 music (notes on the
  treble staff), grade 6 math (equivalent ratios), grade 10 computer science (tracing loops), grade 11
  English (evaluating a counterargument).
  They're in `references/examples/` for Claude to start from.
- `tests/test_lessons.py`: every example builds clean and opens; it runs with the CLI's packages blocked;
  answers land in their boxes and the circle on the right letter; a plotted answer lands on the axes;
  bad lesson files get errors that say what to fix; timing and word-count warnings; no-break spaces keep
  "2 : 3" together and code keeps its indentation; the go-over deck orders questions by how many missed
  them, shows a wrong answer four students gave but not one only one student gave, and names no one.

## Trials: fresh agents as a teacher's Claude

Four agents worked in sandbox-like folders (the skill, a `python3` with the CLI's packages blocked, an empty
"My Lessons" folder), each from a teacher's message alone, and reported every place they got stuck.

| Request | What it made |
| --- | --- |
| 4th grade, comparing fractions, 45 min | 26 slides, a 1-page worksheet (5 questions: shade strips, >/</=, choice, a word problem, explain an error), plan, key |
| 8th grade US history, the Stamp Act to the Tea Party, 50 min | 22 slides with a timeline, a 1-page worksheet around a Stamp Act Congress excerpt (3 questions, a rubric) |
| 9th grade biology, animal cell organelles, 55 min | 31 slides, a 2-page worksheet with a cell to label, matching, a rubric question |
| Go over a marked 6th grade class, 10 minutes | a 10-slide deck from 16 students' results, most missed first |

Every command ran; the only `Check:` lines were word counts. What they found, and what changed:
- **Teachers couldn't see the scoring.** Rubrics weren't in the plan or the key, and long keys were cut off
  in the key's margins. Now the plan lists every rubric level, the key writes model answers on the lines
  and the expected work in math work areas, and a scoring page ends the key.
- **Going over the sheet before it's scanned** lets students fix answers first. The plan and notes now
  say to collect first, and the examples go over the sheet the next day.
- **Pictures beside points were too small to read**, and nothing warned. Wide pictures now go below the
  points, the text column shrinks to fit short points, and `lesson` warns when a picture's smallest text
  is under 14pt (18pt for grades 2-3). Axes, number lines, bar charts, and timelines take a `size`.
- **Go-over decks didn't fit the time**, and a session that hadn't marked had nothing to go on. `--most N`
  takes the N most missed; `go-over-todo.md` lists the wrong answers and their crops.
- **Primary sources quoted from memory.** The history agent flagged its own quotation for the teacher
  to check; the guide now says to quote only exact wording and say where to check it.
- Smaller: two blanks on a line (`\t`), word answers in math, label box sizes, a plan preview
  (`preview lesson-plan.docx`), `lesson_id` documented, `answer_say` for answer slides, and image folders
  no longer left in the teacher's folder.

## Review by an instructional coach

An agent playing a 20-year teacher and coach reviewed the five example lessons. Generator changes:
- `lesson` warns when a slide before the worksheet shows one of its answers. It caught both leaks the
  coach found: a vocabulary example of "$2.50 per smoothie" (a worksheet answer) and a worked example
  that was the essay question's model answer.
- No answer slide after an exit ticket (students still writing would copy it); the answer goes in the
  notes.
- The plan starts with "Before class" (copies, the class ID list, materials), lists every slide question
  with its answer, adds accommodations (extended time always), says what mastery looks like, ends with
  "After class" (collect, scan, mark, hand back, go over), and shows unplanned minutes as a buffer.
- Answer slides keep text at the grade's floor, dropping the "watch out" line to the notes before
  shrinking further; steps are bullets so they don't read as the sheet's box numbers; "Watch out" is
  dark text with an accent label, not gray.
- Worked examples can show code (`"code": true`); questions can number their choices (music).
- The guide gained a "Designing the lesson" section: model and practice every worksheet skill with
  different numbers, one "we do" item per skill, a written exit ticket on a new item, go over the next
  day, close on the targets, and check every fact.

Content fixes in the examples: the math sheet asked students to plot a point that wasn't in its table; an
English choice explained as "a detail from the text" wasn't in the text (rewritten, and the op-ed's study
figures corrected to a median at one of two schools); the science lesson said leaves make food "from
sunlight" (now light, air, and water; "soil" is now the distractor); music choices are numbered so they
don't collide with note names, and the staff to draw on is bigger. Each lesson now models and practices
what its worksheet asks.

## Code review

A separate agent read the new modules and confirmed 17 bugs with reproductions; all are fixed:
- PowerPoint now wraps text where the PDF does (a right inset of the measuring slack), which fixed a
  title chip covering the title, answers spilling out of their boxes, and misaligned line numbers.
- Worksheets made before this change (no passage positions in layout.json) still get their reading
  slide, drawn from key.json.
- Blank code lines keep their height in Keynote and Quick Look (no-break spaces).
- `**` in worksheet or student text is Python's power, not bold.
- Control characters (a pasted `\v`) no longer break the Word file.
- Phone photos are turned upright (EXIF).
- The answer key's font covers every character it prints; characters no font here has (Chinese, emoji)
  are named in a warning, since the PDF shows them blank and the .pptx doesn't.
- `--out` pointing at the worksheet's folder no longer crashes; "You've got these" never shows a whole
  marking key; a rubric question without a model shows its criteria; a drawing question with steps still
  shows its checklist; a long passage source is measured; bad input (a string where a list belongs, 9
  choices, a list for `say`) gets an error that says where; targets say "my", not "their".
- `goover --lesson` refuses a lesson written for a different worksheet.

84 tests pass (29 for lessons). Built and checked with python-pptx 1.0.2 and 0.6.22. `devtools/oracle.py` marks a
simulated class perfectly from its truth file, for testing what comes after marking (render, goover).

## Not done

- The .pptx files pass the schema validator, reopen in python-pptx, and render in Quick Look (Apple's
  Office renderer), but nobody has opened one in PowerPoint or Google Slides yet.
- Worksheet print is 10-11pt for grades 4-12; a large-print style would help students with low vision.
- Slides can't yet show a native table, so a trace table on a slide is a code listing or the worksheet's
  picture.
