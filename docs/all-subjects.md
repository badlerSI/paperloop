# Paper Loop for every subject, grades 2-12

Overnight work log (started Oct 26, 2026). Goal: the Cowork plugin (`plugin/`) can make and mark worksheets
for any K-12 subject from grade 2 to grade 12. Nothing here is committed until Ben says so.

## What each subject and grade band needs

| | Needs | How Paper Loop does it |
| --- | --- | --- |
| **Grades 2-3** | Big print and big writing space, primary-ruled lines (dashed midline), short 2-digit class numbers, comments a child can read or a teacher can read aloud (10 words or fewer), phonetic spelling accepted unless spelling is the point | `grade` sets a primary style; `id_digits: 2`; grade-aware comment length; `spelling: true` only where spelling is assessed |
| **Grades 4-8** | Mixed question types, diagrams, short constructed responses | Current types, plus the ones below |
| **Grades 9-12** | Longer written responses scored on a rubric, formulas and symbols, primary sources, graphs | `rubric` on written answers; Unicode font for math symbols; `passage`; `axes` |
| **Math** | Show-your-work problems with a final answer, equivalent answers (1/2 = 0.5), units, number lines, fraction models, clocks, coordinate grids, tables to fill | `math` type (work area + answer line, numeric check on the answer); `table`; diagram helpers `number_line`, `fraction`, `clock`, `axes` |
| **ELA** | Reading passages with line numbers, cloze, vocabulary, constructed responses with evidence, grammar, spelling tests, paragraphs scored on a rubric | `passage`; `blanks`; `match`; `rubric`; `spelling` |
| **Social studies** | Maps to label, timelines, primary-source excerpts, matching terms, claim-evidence-reasoning | `image` in diagrams (a map), `label`; `match` (ordering and matching); `passage` with a source line; `rubric` |
| **Science** | Already covered: labels, drawings with checklists, data tables, graphs | `table`, `axes` added |
| **World languages** | Accents, vocabulary, translation, spelling that counts | Unicode font; `spelling: true`; `blanks`, `match` |
| **Arts, music, PE, CTE** | Label a diagram or an image, short responses, draw | `image`, `label`, `draw`, `short` |

## Plan

1. **Foundations:**
   - `grade` (2-12) on the worksheet sets the style, the comment length, and the default ID length;
   - primary-ruled lines for grades 2-3;
   - `id_digits` (2-4);
   - a Unicode font when the text needs one (DejaVu Sans, which ships with matplotlib in Claude's sandboxes), with Helvetica otherwise, so old layouts don't change.
2. **New blocks and question types:**
   - `passage`: printed text, not marked;
   - `blanks`: cloze, fill in the blanks inside a sentence;
   - `match`: items with an answer box each, plus lettered choices; covers matching, ordering, true/false;
   - `table`: a printed table with empty cells to fill;
   - `math`: a work area plus an answer line;
   - `rubric` on `short`: criteria with levels.

   `blanks`, `match`, and `table` mark like `label`, one box at a time.
3. **Diagram helpers:** `axes` (a coordinate grid), `number_line`, `fraction` (shaded bar or circle), `clock`, `image` (a teacher's PNG or JPG, such as a map), `timeline`.
4. **Marking rules by subject and grade:**
   - math: final answer and method, equivalent forms, units, partial credit for method;
   - ELA and social studies: evidence and reasoning, rubric levels;
   - spelling counts only when `spelling` is set;
   - early grades: simple comments.
5. **Example worksheets:** at least one per subject family, spread over grades 2-12, each checked by eye.
6. **Dev tools, not shipped:** a simulator that fills any layout with handwriting fonts and scan damage, and a scorer that compares results with the answers it wrote.
7. **Trials:**
   - fresh agents mark simulated class sets through the skill, scored and fed back into the skill;
   - fresh agents write worksheets from teacher requests, checked for fit and quality.

## Progress

- **Foundations done:**
  - `grade`, with styles standard, compact, and primary (primary-ruled lines, big print);
  - `id_digits`;
  - Unicode font: DejaVu from matplotlib, falling back to Helvetica.

  The water worksheet's layout is unchanged; the test against the CLI passes.
- **New blocks done:**
  - `passage`: full width, splits across pages, numbers text lines only, and `make` prints the numbered lines;
  - `blanks`: text flows around inline boxes, `\n` starts a new line;
  - `match`: items with answer boxes, plus lettered choices;
  - `table`: numbered cells to fill;
  - `math`: work area plus an answer box, cropped separately;
  - `rubric` on `short`: criteria with levels.
- **Diagram helpers done:** `axes`, `number_line`, `fraction`, `clock`, `timeline`, `image` (copied beside the worksheet in gray, and lightened in draw questions).
- **Marking:**
  - the "boxes" rules cover label, blanks, match, and table;
  - math scores the answer and the work separately, and a numeric check flags disagreements (1/2 = 0.5 = 50%);
  - rubrics are scored per criterion;
  - comment length depends on grade;
  - spelling counts only when the question says so;
  - rules cover passage evidence and grades 2-3.
- **Rendering:**
  - feedback lines show Answer/Work marks, rubric scores ("Claim: 2/3"), and grouped box results ("Right: 1, 2, 4");
  - a ½ mark for partial;
  - grades 2-3 get bigger comment text.
- **Authoring:**
  - `make` reports how many points to cut to lose a page, and the numbered passage lines;
  - `preview` renders pages to PNG for checking.
- **Examples, checked by eye** (in `examples/` and the skill's `references/examples/`):
  - math2-time-01;
  - sci3-plants-01;
  - ela4-garden-01;
  - math6-ratios-01 (one page);
  - ss7-founding-01 (with a generated map image);
  - math9-linear-01 (Unicode symbols);
  - span9-casa-01 (accents);
  - ela11-argument-01 (four-criterion rubric).

## Trials, round 1 (simulated class sets, fresh agents following the skill)

Each set has 4 students (clean, messy with typical mistakes, partial, mostly blank), handwriting fonts, scan
damage, one sheet upside down, and an empty sheet in the stack. `devtools/fill.py` writes them and
`devtools/score.py` scores them.

| Worksheet | Routing | Verdicts | Boxes | Math answer / work | Rubric levels | Drawing items |
| --- | --- | --- | --- | --- | --- | --- |
| Grade 2 math (clock, add, number line, blanks) | 9/9 | 3/3 | 10/10 | 3/3, 3/3 | n/a | 8/9 |
| Grade 9 algebra (equations, inequality, graph, table) | 9/9 | 7/7 | 9/9 | 7/7, 7/7 | n/a | 9/9 |
| Grade 4 ELA (passage, blanks, rubric, matching) | 9/9 | 7/7 | 18/18 | n/a | 5/6 (6/6 within 1) | n/a |
| Grade 7 social studies (source, rubric, order, map, timeline) | 9/9 | 3/3 | 28/28 | n/a | 6/6 | 6/6 |

- **The two misses are judgment calls**, and the agents raised both themselves:
  - four jumps on a number line asked for three;
  - a made-up story detail scored as a "vague detail" (level 1) rather than "no detail" (level 0). This one was flagged.
- **Cost:** each run used 110-120k tokens and 37-53 tool calls, and took 5-6 minutes for 4 students.
- **Authoring trials:** three fresh agents made worksheets from a teacher request:
  - grade 5 fractions: one good page, now in the examples;
  - grade 8 Civil War: a Lincoln primary source and an ordering question;
  - a grade 3 spelling test: dictation via a table.

  All printed cleanly.

**Fixed from their feedback:**
- **Blank pages and sheets:**
  - a blank page from a student who did page 1 is now reported, as well as a student who left everything blank;
  - empty sheets in the stack are named.
- **`status`:** knows when render has run.
- **Work orders:**
  - no duplicated grade, and the question type is named in plain words;
  - a passage is included only when the question uses it;
  - choice questions don't ask for comments.
- **`check`:** over-long comments block the summary step.
- **Output size:** returned.pdf embeds JPEGs, 16 MB down to 2.9 MB for 8 pages.
- **Printed text:**
  - ordering items print as letters;
  - the passage source line wraps;
  - em dashes and curly quotes print as is.
- **`make` reports:** free space per page, citations of lines the passage doesn't have, and `teacher_notes`.
- **New options:**
  - `notes` on any question: guidance for marking, not printed;
  - `feedback`: "hint" or "answer", which is Ben's open teaching call;
  - `box_height` for big writers;
  - an answer box on drawing questions ("shade it, then write the sum").
- **Defaults:** `subject` no longer defaults to "science".
- **Rules added:**
  - extra marks on drawings, point and tick tolerance;
  - ordering comments;
  - partial math work earns half;
  - a right answer with no work;
  - rubric answers between levels go to the lower level, flagged;
  - multi-page summaries;
  - capitals in spelling tests.
- **Format guide:** documents defaults, the comment column, box sizes, dictation, adapting primary sources, line-number workflow, and checklist design.

## Trials, round 2

| Worksheet | Routing | Verdicts | Boxes | Math | Rubric levels | Drawing items |
| --- | --- | --- | --- | --- | --- | --- |
| Grade 5 fractions (draw with answer, math, choice) | 5/5 | 4/4 | n/a | 8/8 | n/a | 8/8 |
| Spanish 1 (spelling counts, matching, rubric) | 5/5 | 6/6 | 24/24 | n/a | 9/9 | n/a |
| Grade 11 ELA (four-part rubric paragraph) | 5/5 | 5/5 | n/a | n/a | 11/12 (12/12 within 1) | n/a |
| Grade 3 science (labels, short answer) | 5/5 | 8/8 | 16/16 | n/a | n/a | n/a |

The one rubric miss was flagged. "grownd" was transcribed as "ground": the grade 2-3 rule said "read them as
what the child meant". It now says to judge what the child meant but transcribe exactly what's written.

## Second pass (after "take another full pass")

- **Phone photos.**
  - Marker finding now compares each pixel with its neighbourhood instead of using one cutoff, judges marker size relative to the image, and finds corners from each marker's outline, so any angle and perspective work.
  - Pages are relit after straightening, so shadows and color casts drop out.
  - `prepare` takes JPG and PNG photos as well as PDFs.
  - Empty sheets are recognized by counting marks, so the dark table around a photographed page doesn't count.
  - **Test:** a simulated class photographed at 4-16 degrees of tilt, with shadows, a warm cast, a dark table, and JPEG compression, read 52/52 answers the same as the flatbed scan. Day-2 real scan reads are unchanged.
- **A full class.**
  - **16 students:** 17/17 routed, 18/18 verdicts, 56/56 cells, 32/32 math parts, 64/64 graph items.
  - **Usage:** 162k tokens, against about 110k for 4 students, so about 4-5k tokens per extra student. A class of 30 is roughly 220k.
  - **Fixes:** ID strips now come as contact sheets (20 per image instead of one each); work orders list settled scans, and answer close-ups are mentioned once.
- **Code review** (15 confirmed bugs, all fixed):
  - a crossed-out choice was read as the answer;
  - pencil on a light fill was invisible, so the answer was marked blank (PRINTED is now 170, and `make` warns about dark fills);
  - a draw question with an answer box crashed `make`;
  - a missing page shrank the score's denominator (the score is now out of the whole worksheet, and missing pages are named);
  - old templates were reused when a worksheet was remade;
  - transparent PNGs printed black;
  - question numbers given as strings broke `check`;
  - poems lost their line breaks, and line citations were checked against the wrong passage;
  - long titles ran into the ID boxes, and instructions ran into the header rule;
  - word banks overflowed into the comment column;
  - `status` was stuck when nothing needed marking;
  - missing fields crashed with tracebacks;
  - a long choice `why` blocked `check`;
  - an Excel CSV roster lost its first ID (BOM);
  - checklist marks could be dropped.

  Also fixed: confidence values outside 0-1 are rejected, and `prepare` refuses a work folder that already has marks.
- **Veteran-teacher review of the returned pages** (grades 2, 7, 11). Changes made:
  - a ✓ or ✗ now sits on each box the student wrote in and on math answer boxes; no internal labels ("Label 1", "Blank 2", "½ Work") are printed;
  - no ½ or dash marks;
  - rubric scores show from grade 6 only;
  - one summary per student, under a "Feedback" heading on their last page, with earlier pages pointing to it;
  - grades 2-3 get upright comments as big as the question print;
  - a thin bar beside each comment sets it apart on black-and-white copies;
  - comment limits are 16 words (two short sentences) for grades 2-3, 15 for 4-8, and 25 for 9-12, and `check` flags semicolons and colons for grades 2-3.
  - **Rules:**
    - say "is right" in words;
    - marks must agree with comments;
    - hints never contain the target word or number;
    - strengths must be true and never praise a wrong answer;
    - a blank answer's next step is a concrete first move;
    - full-marks students get a stretch step;
    - be direct with high schoolers who answered a different question;
    - never say evidence "proves" a claim.

## New subjects (second pass, continued)

**New to the format:**
- **Code.** `"mono": true` on a passage prints a code listing: fixed-width, indentation kept, every line numbered as in an editor (a wrapped line keeps one number). On blanks it gives fill-in-the-code, and lines without a blank take less room. On choice options and table cells it prints `[]` and `x += 1` as code.
- **Chemistry.** Formulas, ions, and equations in Unicode (H₂O, Cl⁻, ¹²C, →) print in prompts, blanks, tables, and comments. A `math` answer that needs units leaves `units` empty and puts them in `answer`.
- **Music.** A `staff` shape draws:
  - treble and bass clefs (drawn as curves, since no bundled font has them);
  - notes at their pitches, with sharps, flats, and ledger lines;
  - whole, half, quarter, and eighth notes, and dotted notes;
  - rests, time signatures, bar lines, and a final double bar;
  - a one-line rhythm staff.
  
  Note positions now use diagram coordinates like every other shape.
- **Bar charts.** A `bar_chart` shape draws bars to read, or empty axes for "draw the bars".
- **Essays across pages.** A `short` answer with more lines than fit continues onto the next page or pages, full width, with "continued (part 2 of 3)". It's marked as one answer:
  - the work order lists each student's pages together, keyed by the first;
  - the comment and rubric scores print beside the first page;
  - continuation pages a short essay left blank aren't reported as blank pages.
- **`make`** lists each page's blocks with their heights, and warns when a passage ends on one page and its first question starts on the next.

**Trials, round 3** (fresh agents, simulated class sets):

| Worksheet | Routing | Verdicts | Boxes | Math answer / work | Drawing items |
| --- | --- | --- | --- | --- | --- |
| Grade 10 code tracing (trace table, fill-in code, predict) | 6/6 | 11/11 | 28/28 | n/a | n/a |
| Grade 10 chemistry (balance, particle table, molar mass) | 5/5 | n/a | 28/28 | 8/8, 7/8 | n/a |
| Grade 5 music (name notes, draw whole notes, beats) | 5/5 | 4/4 | 28/28 | n/a | 12/12 |
| Grade 7 statistics (read a bar chart, draw bars, mean) | 5/5 | n/a | 16/16 | 4/4, 2/4 | 16/16 |

- **Grade 11 two-page essay** (a source memo, a 40-line essay across two pages, a three-part rubric; four students, one who stopped on page 1 and one who left it blank): 9/9 routed, 9/9 rubric levels exact, 1 flag (Evidence 0 or 1 for a vague essay). The agent paired each student's pages from the work order without trouble. Fixed from its notes: the "settled" count counts an essay once, an all-blank student gets one line instead of one per page, flags list every page's crop, transcriptions mark page breaks, rubric marks take `key_ambiguous`, and the rules say how to comment on a top-level criterion and on parts the rubric doesn't score.
- **The three math-work misses were judgment calls**, and the rules now settle them:
  - "26 / 4" with no addition shown: the agent gave partial and flagged it. A step done in the head counts when its result shows.
  - Counting one oxygen atom instead of three, and dividing by the wrong count: the agents gave partial and the truth file said incorrect. A miscount is now named as partial.
- **Rules added:**
  - code blanks that work but aren't the key's answer;
  - a faint minus sign;
  - carried errors in trace tables;
  - empty boxes that could mean 1;
  - note names in lower case;
  - counts like "1 2";
  - True/true in traces;
  - balanced coefficients not in lowest terms;
  - bar-top and staff line-or-space tolerances;
  - rounding versus significant figures;
  - units in the work;
  - using one's own earlier wrong answer.

  The summary rules no longer contradict each other on the stretch step.
- **Script changes:**
  - box-level "uncertain" flags name the box;
  - `key_ambiguous` and `note` are accepted on box questions;
  - the answer check tolerates rounding within 1% and doesn't flag a right number marked wrong for missing required units;
  - work orders carry the printed instructions and say when units are printed beside the box;
  - "chemistry chemistry" in work-order headers is gone.
- **Authoring trials** (grade 11 Python, grade 11 stoichiometry, grade 4 music) each made a clean worksheet. Their friction became:
  - the note-position fix and staff features above;
  - block heights in `make`;
  - the passage-split warning;
  - `mono` options and cells;
  - documented minimum work areas, multi-step keys, required units, `\n` in prompts, shared data in the instructions, and code line citations.

**Real-handwriting test kits:** `scans/day3/<worksheet>/` holds:
- `worksheet.pdf` to print;
- `guide.pdf`, a cover sheet listing each copy's answers plus a picture of every copy filled in;
- the `assignment/` folder for marking;
- `truth.json` for `devtools/score.py`.

The kits are code tracing (5 copies), chemistry (4), music (4), and bar charts (4). `devtools/score.py` now checks routing by ID when the scan order isn't known. `devtools/guide.py` makes a kit for any worksheet and students file.

**Code review of the new code** (a fresh agent, every bug reproduced by running it; all 12 fixed and covered by tests):
- **Essays:**
  - a page the student skipped wasn't reported when an essay ended on it;
  - an essay whose first page went to the review pile was never marked (it's now keyed by the earliest page that was routed, and the work order says page 1 is missing);
  - a short essay's blank continuation page made the student look absent;
  - a one-line essay tail sat alone on the next page (later parts now get at least four lines).
- **Answer check:** the 1% tolerance let ones-digit slips through (622 for 623). Rounding now means the same number at the precision written: 0.17 for 1/6, never one whole number for another. A variable before "=" ("t = 4") no longer counts as a unit.
- **Work orders:**
  - code braces turned into brackets (blanks now show as [blank 1]);
  - printed units on a drawing's answer box weren't marked as printed;
  - "PE" matched inside "special ed";
  - wrapped code lines were dropped (from `make`'s printout too).
- **Grades:** "Spanish 2 (high school)" and "Algebra 1" were read as grades 2 and 1. Only grade wording counts now ("9th grade", "grade 9"), and AP, IB, honors, and "high school" mean high school.
- **Staffs and code:**
  - a five-line staff with no clef crashed `make` (it's now a clear error);
  - a dotted rest lost its dot;
  - tab-indented code in blanks lost its indentation.

