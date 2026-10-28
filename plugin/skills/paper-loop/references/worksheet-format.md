# Worksheet format

A worksheet is one JSON object. `references/examples/` has a worksheet for each grade band and subject
family. Find the closest one, read it, and model yours on it.

| Example | Grade | Shows |
| --- | --- | --- |
| `math2-time-01.json` | 2 | primary style, clock, number line, show-your-work math, blanks |
| `sci3-plants-01.json` | 3 | label a drawn diagram, primary-ruled short answer |
| `ela4-garden-01.json` | 4 | passage with line numbers, blanks with word bank, rubric, matching |
| `math6-ratios-01.json` | 6 | table to fill, math with an answer box, coordinate grid |
| `ss7-founding-01.json` | 7 | primary source, rubric (claim and evidence), ordering, a map image, timeline |
| `math9-linear-01.json` | 9 | equations and inequalities with math symbols, graphing, table |
| `span9-casa-01.json` | 9 | world language: spelling and accents count, matching, rubric |
| `ela11-argument-01.json` | 11 | argument passage, a paragraph scored on a four-part rubric |
| `ela11-startlate-01.json` | 11 | a source memo and a two-page argument essay scored on a rubric |
| `example-density.json` | 7 | science: label, draw with a checklist |
| `math5-addfrac-01.json` | 5 | fraction strips (draw with a checklist), word problem with units, a choice that catches adding denominators |
| `mus5-notes-01.json` | 5 | music: name notes on a staff, draw notes on a staff, blanks with a word bank |
| `math7-data-01.json` | 7 | statistics: read a bar chart, draw the bars, find the mean |
| `chem10-moles-01.json` | 10 | chemistry: balance an equation (blanks), a table of particles, molar mass and moles with units |
| `cs10-loops-01.json` | 10 | computer science: a code listing, a trace table, fill-in-the-code blanks, predict the output |
| `sci5-photosynthesis-enrich-01.json` | 5 | enrichment: a passage adapted from Simple English Wikipedia with its credit line, a reading level, a "Done early?" note |
| `math6-ratios-02.json` | 6 | versions: support, large print, Spanish, Arabic, Bengali (see `references/versions.md`) |
| `math6-ratios-hw-01.json` | 6 | a different copy for each of 30 students: variables, a pool, shuffled choices |

To print versions for students who need supports (scaffolds, large print, a home language) or a different
copy for each student, read `references/versions.md` too.

```json
{
  "assignment_id": "sci6-plants-02",
  "title": "Plant Power",
  "subject": "science",
  "grade": 6,
  "grade_band": "6th grade",
  "instructions": "Write your ID in the boxes at the top right, not your name.",
  "compact": true,
  "questions": [ ... ]
}
```

- `assignment_id`: short, unique for this teacher, no spaces (subject, grade, topic, number). It's printed in
  the footer and in the page code that tells the scanner which worksheet a page belongs to.
- `title` and `instructions` print in the header (instructions default to "Answer each question in its box.
  Write your ID number, not your name."). `subject` (free text) and `grade_band` (such as "4th grade" or "AP
  Biology") aren't printed; marking reads them.
- `feedback`: "hint" (the default) means comments on wrong answers point toward the fix without giving the
  answer. "answer" lets comments say the right answer. Ask the teacher if they have a preference.
- `teacher_notes`: anything for the teacher that mustn't print, such as the words to read aloud for a
  spelling test. `make` prints it back.
- `comment_language`: the language of the comments printed beside answers (default "English"). A world
  language teacher may want short comments in the target language.
- `grade` (2-12) sets the defaults. Grades 2-3 get the **primary** style: bigger print, primary-ruled writing
  lines (dashed midline), bigger boxes, 2-digit class numbers, and comments of two short sentences. Other
  grades get 4-digit IDs, and comments of 15 words (grades 4-8) or 25 (grades 9-12).
- `compact`: tighter spacing, to fit more on a page (not for grades 2-3). One US Letter page holds about 6
  short questions compact, or 4-5 otherwise. `style` ("primary", "standard", "compact") and `id_digits` (2-4)
  override the defaults.
- Every page gets the ID boxes at the top right and a feedback summary box at the bottom. `make` reports the
  pages, the free space, and how much to cut to lose a page.

## Blocks

`questions` is a list of blocks, printed in order. Every question has `q` (its number) and `prompt`. Where it
fits, start prompts with a short, catchy name and a real situation ("Closet Bean: Two bean plants get the
same water for a week..."). Any question can add:
- `"spelling": true` when spelling counts (spelling tests, vocabulary, world languages);
- `"passage": "<its id>"` when it's about a passage, so marking sees the text;
- `"notes"`: guidance for marking that isn't printed ("capital letters don't matter", "accept any two of the
  four causes");
- `"skill"`: the "I can" statement it practices ("I can find a unit rate"). Progress reports follow each
  student skill by skill across worksheets, so use the same wording every time a skill comes back. Without
  one, the worksheet's title stands in;
- `"support"`: scaffolds that versions can print (`references/versions.md`).

Questions sit in the left part of the page (344 points wide); the right column is left empty for the
comments Paper Loop prints beside each answer. Default points: short 2, choice 1, math 1 for the answer and 1
for the work, and 1 per box, label, blank, cell, item, or checklist item (set `points` on any of them).

### passage: printed text, not marked

```json
{"type": "passage", "id": "story", "title": "The Rooftop Garden", "line_numbers": true,
 "text": "First paragraph...\n\nSecond paragraph...", "source": "An original story written for this worksheet."}
```

- Spans the full page width and runs onto the next page if it's long. Separate paragraphs with a blank line.
  A 13-line passage takes about 40% of a page.
- `line_numbers` prints every fifth line number in the margin. Blank lines between paragraphs aren't counted.
  Line numbers depend on the layout, so write questions that cite lines after the first `make`: it prints
  the numbered lines, and it warns when a question cites a line the passage doesn't have.
- `mono: true` prints code: a fixed-width font, every line and its indentation kept as written (one `\n`
  per line), and with `line_numbers` every line numbered, as in an editor. Use a short `title` ("Program A")
  so prompts can refer to it. Keep code lines under about 70 characters; longer ones wrap.
- Only use text you wrote, text in the public domain, or openly licensed text, and credit it. Don't
  reproduce copyrighted readings. To make an old text readable, you may define hard words in [brackets]
  and mark cuts with "...". If you quote a public-domain text from memory, tell the teacher, so they can
  check it against a published copy.

#### Readings from free, human-written sources

For enrichment, or a reading on any topic, start from a real text rather than writing one. Good sources:
- Wikipedia, and Simple English Wikipedia for younger readers (CC BY-SA);
- Project Gutenberg and Wikisource (public domain);
- US government sites: NASA, NOAA, USGS, the Library of Congress.

`PL source wikipedia "<article title>" --out "<folder>/sources/<name>.json"` saves an article's plain text
with a link to the exact revision. The other sources:
- `simple` for Simple English Wikipedia;
- `wikisource "<page title>"` for primary sources: speeches, laws, letters, old books;
- `gutenberg <book number>` for a book.

A text you fetched another way (with your web tool) needs the same credit: its title, author, address, and
license go in `cite`.

**Quote primary sources from a scan-backed edition**, never from a quotation inside an encyclopedia article,
which may be slightly wrong. Good sources:
- Wikisource pages marked as checked against a scan;
- the Library of Congress;
- the Avalon Project;
- the first printing.

Gutenberg's plain text sometimes drops punctuation or changes small capitals and dashes. Check a quote
against a scan when the exact words matter. Read it, then quote it exactly or abridge and adapt it for the grade. Credit it with `cite` on
the passage:

```json
{"type": "passage", "id": "leaf", "title": "Plants Make Their Own Food", "reading_level": 5, "text": "...",
 "cite": {"title": "Photosynthesis", "author": "Simple English Wikipedia contributors",
          "url": "https://simple.wikipedia.org/w/index.php?title=Photosynthesis&oldid=10903963",
          "license": "CC BY-SA 4.0", "changes": "shortened and simplified for grade 5"}}
```

- **The credit line.** The worksheet prints the line the license asks for under the passage: title,
  authors, link, license, and what changed. An adapted CC BY-SA passage stays CC BY-SA (`make` says so);
  the questions are the teacher's.
- **`license`.** One of: public domain, US government work, CC0, CC BY 4.0, CC BY-SA 4.0, CC BY-NC 4.0, CC
  BY-NC-SA 4.0, CC BY-ND 4.0, CC BY-NC-ND 4.0, or "written for this worksheet". An ND license allows no
  `changes`.
- **`changes`.** Say how you changed it: "shortened", "simplified for grade 4", "excerpted". Leave it out
  only for an exact quote.
- **`reading_level`.** The grade you adapted it for. `make` estimates every English passage's reading level
  (Flesch-Kincaid) and warns when a passage reads well above the worksheet's grade, or above its
  `reading_level`. It's a rough guide: short sentences and everyday words bring it down.
- **Sources that refuse adaptation.** Some free sites forbid adapting their texts (`make` refuses):
  CommonLit, ReadWorks, and CK-12 forbid rewriting or AI use, newer OpenStax books forbid AI use, and
  Newsela is licensed. For those, find the same topic on Wikipedia, or the public-domain original on
  Gutenberg or Wikisource.
- **Wikipedia text.** Formulas in Wikipedia text come through as `[formula]`: write them yourself, as plain
  text with Unicode subscripts.
- **Be accurate.** When adapting, keep the facts right: simplify the words, not the science.
- **Notes and line breaks.** Bracketed definitions or background notes inside a quotation are fine:
  "[ham = an escaping person]". Say so in `changes` ("excerpted, with bracketed definitions"). A single line
  break (`\n`) in a passage is kept, for telegrams, poems, and lists; a blank line starts a new paragraph.
- **A question about two sources.** Use `"passage": ["still", "douglass"]`; marking sees both.
- **Primary sources run hard.** They often read well above grade level; `make` warns only when that looks
  unintended. For younger readers, read them aloud, or add a short adapted summary beside the original.

### note: printed text, not a reading

```json
{"type": "note", "title": "Done early?", "text": "Draw a leaf. Use arrows to show what goes in and comes out."}
```

A dashed box, full width, for directions, an extension task, or a key-word list. It isn't marked, and
marking never sends it to Claude as a passage. `"size": 8.5` prints it small (a note for an adult), and
`"qr": "<url>"` adds a QR code at its right for a phone camera. Claude can't read a QR code from a photo
reliably, so print in the text whatever Claude should know.

### short: writes in a ruled box

```json
{"type": "short", "q": 3, "prompt": "...", "key": "The window plant: it uses light to make its food (photosynthesis). Full credit needs the window plant and light for making food; 'because of the sun' alone is partial.", "points": 2, "lines": 2}
```

- `key`: what full credit needs, and what's partial or wrong if that's likely. Marking reads this, rubric
  or not: with a rubric it's what a top answer looks like.
- `lines`: ruled writing lines (default 4; 2 is enough for one sentence; 8-10 for a paragraph). An essay
  can have more lines than fit on a page: it continues onto the next page or pages, full width, marked as
  one answer. About 23 lines fit on a page (25 compact); 50 lines is about two and a half pages.
- `rubric` (instead of `points`): criteria scored on levels, lowest first. Each criterion is worth its top
  level, so 3 levels make 2 points. Spelling, accents, and grammar count only if a criterion says so, so add
  a conventions criterion when they matter (always, in a world language). Spell out anything a criterion
  depends on, such as the unit's vocabulary list, rather than "etc.".

  ```json
  "rubric": [
    {"criterion": "Claim: says where government gets its power (the consent of the governed).", "short": "Claim",
     "levels": ["missing or wrong", "partly right or vague", "clear and accurate"]},
    {"criterion": "Evidence: quotes or cites the line that shows it.", "short": "Evidence",
     "levels": ["none", "doesn't support the claim", "accurate quote or line"]}
  ]
  ```

  `short` is the name printed beside the answer ("Claim: 2/2").

### choice: circles one letter

```json
{"type": "choice", "q": 1, "prompt": "...", "answer": "B", "columns": 2,
 "options": [
   {"letter": "A", "text": "From the soil", "why": "Roots take in water and minerals, but not most of the plant's mass."},
   {"letter": "B", "text": "From the air", "why": "Yes: leaves take in carbon dioxide and build sugar from it."}
 ]}
```

- `why` is printed beside the question when the student picks that option. Write one for every option:
  the right one says why it's right (not just "Yes!"), and each wrong one names the misconception. With
  `"feedback": "hint"`, a wrong option's `why` points toward the idea without stating the right answer.
- `columns` puts short options side by side (1, 2, or 4).

### blanks: fills in blanks inside a sentence

```json
{"type": "blanks", "q": 2, "prompt": "Use words from the story.", "word_bank": ["vent", "seed swap"],
 "text": "Amara got her beans from the library's {1}. She moved the bucket next to the warm air {2}.",
 "answers": [{"n": 1, "answer": "seed swap"}, {"n": 2, "answer": "vent", "accept": ["air vent"]}]}
```

- `{1}`, `{2}` mark the blanks. `\n` starts a new line, so one block can hold several short items
  ("6 + 7 = {1}\n8 + 5 = {2}"). Runs of spaces print as one space; `\t` starts the next item halfway
  across the line, for two short items side by side ("a. 3/4 {1} 5/8\tb. 2/5 {2} 1/2").
- Each answer can have `accept` (other right answers), `points` (default 1), and `width` (default 80pt; 100
  for grades 2-3). `box_height` makes every box in the question taller (default 22pt; 20 compact; 32 for
  grades 2-3).
- `mono: true` prints the text as code, keeping indentation: fill-in-the-code questions ("for n in
  range(1, {1}):"). Lines without a blank take less room.
- Don't let one question's prompt or word bank give away another question's answers.

### match: writes a letter (or number, or T/F) beside each item

```json
{"type": "match", "q": 4, "prompt": "Match each word to its meaning. Write the letter in the box.",
 "items": [{"text": "exhaust (line 2)", "answer": "C"}, {"text": "pale (line 6)", "answer": "A"}],
 "choices": [{"letter": "A", "text": "light in color"}, {"letter": "B", "text": "very tall"},
             {"letter": "C", "text": "smoky air from engines"}]}
```

- Leave out `choices` for ordering ("write 1 for the earliest"), or for true/false ("write T or F"); the
  prompt says what goes in the box. Items are then printed with letters (A, B, C), so their labels can't be
  mistaken for the numbers students write. With choices, items print with no label of their own (numbers
  under the question's number read as more questions): in a comment, name an item by its words.
- The item and choice columns split the width by how much each has to say, so long items (events, causes)
  get room and short ones (vocabulary words) don't waste it.
- With choices, add one that nobody should pick, so the last one isn't free. `box_height` works as in
  blanks.
- Ordering marks more reliably from a scan than placing events on a timeline. Use a `timeline` in a draw
  question when reading the scale is the skill being taught.

### table: fills in the empty cells of a printed table

```json
{"type": "table", "q": 1, "prompt": "Fill in the table.", "columns": ["Batches", "Mango (cups)", "Yogurt (cups)"],
 "rows": [["1", "2", "3"], ["2", {"answer": "4"}, "6"], ["4", "8", {"answer": "12"}]]}
```

- A cell is printed text, or `{"answer": ..., "accept": [...]}` for a cell to fill. Cells to fill are
  numbered in reading order, across each row, and the number prints small in the cell's corner.
- `col_widths` (points, adding up to 344) and `row_height` (default 32pt; 30 compact; 42 for grades 2-3; the header row keeps its own height)
  are optional. A table with tall rows is the easiest way to give big writing boxes.
- **Dictation** (a spelling test, a dictated sentence): use a table with a number column and empty cells to
  write in, and `"spelling": true`. The words go in the answers and in `teacher_notes`, never in the
  printed text.

### math: shows work, then writes the final answer in its own box

```json
{"type": "math", "q": 2, "prompt": "Unit Price: 6 smoothies cost $15. How much does 1 smoothie cost?",
 "answer": "$2.50", "accept": ["2.5", "2.50"], "units": "",
 "key": "Divides 15 by 6 (or halves the cost of 2) to get $2.50 per smoothie.",
 "answer_points": 1, "work_points": 1, "work_height": 80, "grid": false}
```

- `answer`: the final answer. Equal values in other forms count (0.5 for 1/2; "1 1/10", written with a space,
  for 11/10), and a script double-checks the numbers, so `accept` is for other ways of writing the answer,
  such as "x = 17" for "17". An answer can be a word ("Maya", for "who ran farther?"); then the number
  check is skipped and `accept` lists the other ways to say it. An answer that differs only by rounding (0.4995 for 0.500) counts unless the
  key or `notes` ask for significant figures or decimal places; say so there if they're graded.
- `units` prints after the answer box, so students don't have to write them. To make students write the
  units, leave `units` empty and put them in `answer` ("3.60 mol"): an answer without them is then wrong.
- `key`: what the work should show, and the mistake to look for ("not flipping the inequality sign"). Work
  is judged correct, partial (half the work points), or incorrect. For a multi-step problem, raise
  `work_points` and list the steps the work should show. One box holds one result: to score two results
  ("which reactant is limiting, and how many grams"), use two questions, or ask for the other in the work.
- `work_height`: the work area in points (default 100; 86 compact; 130 for grades 2-3). Give one-step work
  at least 70 and multi-step work at least 120. `grid: true` prints faint graph paper in it.

### label: writes in numbered boxes on a printed diagram

```json
{"type": "label", "q": 4, "prompt": "...", "word_bank": ["roots", "stem", "leaf", "flower"],
 "diagram": {"width": 300, "height": 150, "description": "A simple plant: roots below a ground line... Box 1 points to the roots...", "shapes": [ ... ]},
 "labels": [
   {"n": 1, "box": [180, 10, 75, 22], "points_to": [120, 25], "answer": "roots", "accept": ["root"]}
 ]}
```

- `box`: x, y, width, height of the label box inside the diagram. `points_to` (optional) draws a leader line
  to that point. Handwriting needs room: about 9pt of width a letter for grades 4-12 (110-120pt for
  "mitochondrion"), 12pt for grades 2-3, and a box at least 24pt tall.
- `description`: plain words for what's printed, before any student touches it. Marking reads it.
- A label question can also show a picture and ask for one answer, such as a clock and "what time is it?"
  with a single box.

### draw: draws in a frame

```json
{"type": "draw", "q": 5, "prompt": "Draw what goes into a leaf and what comes out. Use arrows and label each one.",
 "diagram": {"width": 344, "height": 140, "description": "A large leaf outline in the middle of the frame.", "shapes": [ ... ]},
 "checklist": [
   {"item": "An arrow goes into the leaf labeled carbon dioxide (or CO2, any spelling).", "short": "CO2 in"},
   {"item": "An arrow comes out of the leaf labeled oxygen (any spelling).", "short": "Oxygen out"}
 ]}
```

- `checklist`: one point per item. Write items as things you can see on the page ("an arrow comes out of
  the leaf, labeled oxygen"), not judgments ("shows understanding of photosynthesis"). `short` is the wording
  printed beside the drawing.
- Graphing, plotting points, number-line jumps, and graphic organizers (a Venn diagram, a T-chart) are draw
  questions with a scaffold and a checklist.
- Write each checklist item so that one mistake costs one item. "Three jumps of 5" and "the last jump lands
  on 35" are two items, not one. Be specific about what's checked: "two points on the line y = 2x − 1 are
  marked", not "points are marked".
- A drawing can also have an answer box for a result: `"answer": "7/12"` (plus `accept`, `units`,
  `answer_points`) adds "Answer: [ ]" below the frame (`answer_label` changes the word: "Total:", "Slope:"; it
  works on math questions too). Use it for "shade it, then write the sum" or "plot it,
  then give the slope".

## Diagram shapes

Coordinates are points (1/72 inch) inside the diagram, origin at its bottom-left. A diagram is at most 344
points wide.

| shape | fields |
| --- | --- |
| `rect` | `x`, `y`, `w`, `h` |
| `circle` | `x`, `y` (center), `r` |
| `line`, `arrow`, `polyline`, `polygon` | `points`: [[x, y], ...]. An arrow gets a head at its last point. |
| `text` | `x`, `y` (the baseline of the first line), `text`, `size` (default 9), `bold`, `align` (left, center, right), `wrap` (a width, to wrap long text) |
| `axes` | `x`, `y`, `w`, `h`, `xmin`, `xmax`, `ymin`, `ymax`, `xstep`, `ystep`, `label_every`, `grid` (default true), `xlabel`, `ylabel`, `size` (labels, default 7): a coordinate grid |
| `number_line` | `x`, `y`, `w`, `min`, `max`, `step`, `label_every`, `labels` ("decimal", "fraction", or "none"), `minor` (ticks between steps), `arrows`, `size` (labels, default 8) |
| `fraction` | `kind` ("bar" with `x`, `y` (bottom-left), `w`, `h`; or "circle" with `x`, `y` (center), `r`), `parts`, `shaded` (how many parts, from the left or from 12 o'clock, are filled light gray) |
| `clock` | `x`, `y` (center), `r`, `hour` and `minute` for hands (leave them out for "draw the hands") |
| `timeline` | `x`, `y`, `w`, `start`, `end`, `step`, `label_every`, `events`: [{"at": 1776, "text": "..."}] (leave events out for "place the events"); `size` (event labels, default 7.5; bigger on a slide), `levels` (how many heights labels stagger across, default 2; 3 when events are close together) |
| `bar_chart` | `x`, `y` (where the axes meet), `w`, `h`, `categories`, `values` (one per category; leave it empty, or use null for a bar, for "draw the bars"), `ymax`, `ystep`, `label_every`, `ylabel`, `bar_fill` (default 0.7), `size` (labels, default 8). Category names print under the axis, so leave about 14 points below `y`. |
| `staff` | `x`, `y` (the bottom line), `w`, `h` (bottom line to top line, default 32), `clef` ("treble", "bass", or "none"), `lines` (5, or 1 for a rhythm line), `time` ("4/4"), `bars` (x of each bar line), `final_bar` (a double bar at the right end), `notes`. A note is `{"pitch": "G4", "x": 60, "duration": "half", "dot": true}`: `x` is in the diagram's coordinates like every other shape, `duration` is "whole", "half", "quarter" (the default), or "eighth", and a pitch like "F#4" or "Bb3" gets a sharp or flat. A rest is `{"rest": "quarter", "x": 90}`. On a rhythm line, notes need no pitch. See "Music" below. |
| `image` | `x`, `y`, `w`, `h`, `path` (a PNG or JPG beside the worksheet JSON, such as a map). It prints in gray; `faint: true` lightens it so pencil on top stays readable (the default in draw questions). |

All basic shapes also take `fill` and `stroke` (gray from 0 black to 1 white, or null for none; stroke defaults to
black, fill to none) and `width` (line width, default 1). Keep fills light (0.6 or lighter) so pencil shows on
them.

## Stretch questions for practice

`"stretch": [ ...questions... ]` at the top level holds one or two harder questions on the same skills, with
their own `q` numbers (say 11 and 12). They don't print on the worksheet. After marking, `practice` gives them
to students who had full credit, so every student gets a practice sheet and getting one says nothing about
who struggled. Without them, full-credit students get new numbers on the class's two hardest questions (where
the worksheet has `vars` or a `pool`), or no sheet.

## Writing a good worksheet

- **Match the grade.** In grades 2-3, use fewer questions, one idea per question, and lots of room. In
  grades 9-12, use passages, rubric-scored writing, and multi-step problems. Students circle the letter in
  every grade (that's what the scan reads); through grade 5, say "Circle the letter." in choice prompts or in
  the instructions.
- **Keep text short where it prints beside answers.** A choice's `why` is 15 words at most (10 for grades
  2-3). A checklist `short` or a rubric `short` is a few words. A rubric `criterion` isn't printed, so it can
  be as long as the marking needs.
- **Mix types** when the teacher hasn't said what they want: choice for misconceptions, `math` or `short`
  for explaining, and `label`, `draw`, or `table` for showing. If they listed the questions, build those.
- **Write keys a stranger could mark from:** what full credit needs, what's partial, and the likely wrong
  answer. For math, say which mistake to look for.
- **Math symbols** (≤, √, π, x², θ) and accented letters print as written. So do chemical formulas
  and equations written with Unicode subscripts, superscripts, and arrows (H₂O, CO₃²⁻, ¹²C, ⇌). A plain arrow
  (→) or minus sign (−) prints as written when the sheet has another such symbol, and otherwise as -> or -.
  Don't use LaTeX or HTML tags.
- **Fit the page.** `make` lists each page's blocks with their heights, its free space, and how many points
  to cut to lose a page. Lines, work areas, and diagram heights are the easiest places to save space. Give
  spare space to writing and work areas. Don't add questions the teacher didn't ask for. A question without
  room to answer is worse than a second page: if the teacher allows two pages, use them before squeezing
  work below the minimums above. The header holds 3 lines of instructions; more push the questions down.
- **Line breaks:** `\n` in a prompt starts a new line. Put each equation on its own line so it doesn't break
  in the middle.
- **Shared data** (molar masses, a formula, a word list every question uses) goes in `instructions` or in a
  passage block, once.
- **Science equations with blanks:** a four-term equation fits on one line with 30pt boxes (`width`).
- **Code:** a listing is a `mono` passage; questions about it say "Program A, line 4". Line numbers in code
  come from the code itself, so after editing a listing, recheck every prompt and key that cites a line.
  Code in options or table cells (`[]`, `x += 1`) prints in the regular font unless the question has
  `"mono": true`. For a fix that's a word or a number, use a mono blank; for a fix that moves or reindents a
  line, ask for it in words (`short`).
- **Music:** pitches use scientific names: middle C is C4; the treble staff's bottom line is E4 and top line
  F5; the bass staff's bottom line is G2 and top line A3. The clef and time signature take the first 40
  points of a staff at the default size, so start notes after that. Notes below the middle line have stems
  up; from the middle line up, stems go down about 26 points (3.3 line spaces) from the head, so leave
  room before any label boxes under the staff, and make boxes under two-count notes wider. For answers with
  several counts ("1 2" under a half note), list the forms you'll accept ("1-2", "12").
- **Where files go:** `<folder>` is wherever the teacher keeps worksheets (a `Worksheets/` folder, if they
  have one). Save your JSON as `<folder>/<assignment_id>.json` and make it with
  `--out "<folder>/<assignment_id>"`. `make` keeps a filled-in copy as `worksheet.json` inside that folder;
  edit your JSON, not the copy, and run `make` again.
