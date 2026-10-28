# Lesson format

A lesson is one JSON file you write beside the worksheet. `PL lesson` turns it into four things for the
teacher:

| File | What it is |
| --- | --- |
| `lesson-plan.docx` | The plan: objectives, standards, materials, vocabulary, a timed sequence with slide numbers, checks for understanding, misconceptions, differentiation, assessment, and every worksheet answer worked through. Opens in Word, Google Docs, or Pages. |
| `slides.pptx` | The lesson's slides, in order, with what to say in the speaker notes. Opens in PowerPoint, Keynote, or Google Slides (File > Import). `slides.pdf` is the same deck. |
| `go-over.pptx` | Each worksheet question as printed, then its answer written in and worked through. For going over the sheet the next day. `go-over.pdf` is the same deck. |
| `answer-key.pdf` | The worksheet with every answer filled in, and the key beside each question. |
| `worksheet.pdf` | A copy of the worksheet, so everything to print is in one folder. Marking still uses the folder `make` wrote. |

After marking, `PL goover` makes a better go-over deck from the class's results (see the end of this file).
The next day's lesson can open with it: a phase with `"review"` (below) puts the most-missed questions, how
the class answered them, and a "Fix it" slide into that lesson's own slides.

Make the worksheet first (`PL make`), then the lesson: the lesson points at the folder `make` wrote.

## A short example

```json
{
  "title": "Equivalent Ratios at the Smoothie Stand",
  "subject": "Math",
  "grade_band": "6th grade",
  "minutes": 50,
  "worksheet": "math6-ratios-01",
  "objectives": ["Students will be able to make equivalent ratios by multiplying both quantities by the same number."],
  "sequence": [
    {"phase": "Warm-up", "minutes": 5, "teacher": "...", "students": "...", "slides": [
      {"type": "question", "title": "Warm-up", "prompt": "1 scoop of mix makes 4 cups. How much water for 3 scoops?",
       "answer": "12 cups", "why": "3 times the mix needs 3 times the water."}]},
    {"phase": "Mini-lesson", "minutes": 15, "slides": [...]},
    {"phase": "Worksheet", "minutes": 20, "worksheet": true},
    {"phase": "Go over it", "minutes": 8, "walkthrough": [1, 4]},
    {"phase": "Exit ticket", "minutes": 2, "slides": [...]}
  ],
  "walkthrough": [
    {"q": 1, "think": "What happens to both amounts from 1 batch to 2?", "idea": "Multiply both parts by the number of batches.",
     "steps": ["2 batches: 2 × 2 = 4 cups mango.", "..."], "mistakes": ["Adding 2 to each row instead of multiplying."]}
  ]
}
```

`references/examples/` has full lessons (`*-lesson.json`), each beside its worksheet. Read the one closest
to yours:

| Lesson | Grade | Shows |
| --- | --- | --- |
| `sci3-plants-lesson.json` | 3 | big type, a diagram beside points, hold-up-fingers checks, a drawn plant reused from the worksheet |
| `mus5-notes-lesson.json` | 5 | staffs on slides, a question with a picture, a drawn answer (notes on a staff) |
| `math6-ratios-lesson.json` | 6 | worked examples revealed a step at a time, compare, whiteboard checks, a plotted answer |
| `cs10-loops-lesson.json` | 10 | code slides, a traced loop, a code passage shown before its questions |
| `ela11-argument-lesson.json` | 11 | a passage with line numbers, a model paragraph for a rubric question, standards |

## Designing the lesson

A lesson a coach would sign off on, not just a deck:

- **Teach and practice everything the worksheet asks.** For each kind of question on the worksheet
  (plotting points, tracing a loop with an `if`, drawing notes, citing a line), the lesson models it on a
  slide and then has the class do one together ("we do"). Use different numbers, a different text, or a
  different example than the worksheet: a slide that shows a worksheet answer turns the worksheet into
  copying. `lesson` warns when a slide before the worksheet shows one of its answers.
- **Guided practice is one item per skill**, not a single multiple-choice question.
- **End with collecting, then an exit ticket.** Collect the worksheets, then give a written exit ticket on a
  new item (one each, on a sticky note or card) that checks the main learning target. Keep its answer in
  `say`: a phase named "Exit ticket" never gets an answer slide, so students still writing can't copy.
- **Go over the worksheet the next day**, from the marked sheets (`go-over.pptx`, or `PL goover` after
  marking). A same-day walkthrough comes only after the sheets are collected.
- **Close the loop**: the exit ticket or a last slide goes back to the learning targets.
- **Leave 2-5 minutes for transitions.** The plan shows them as a buffer.
- **Everything the plan promises is in the materials.** If differentiation mentions picture cards, a
  bilingual vocabulary slide, or sentence frames, put them on a slide or the worksheet.
- **Check every fact**, and choose simplifications that stay true at the next grade ("leaves use light,
  air, and water to make food", not "leaves make food from sunlight"). A question that says "the points
  from the table" uses the table's points. Every wrong choice's explanation matches the text.
- **Say what mastery looks like** in `assessment`: what a student who got it can do.
- **Music**: when the choices are note names, give the question `"choice_labels": "numbers"` so the
  choices are 1-4, not A-D.

## The lesson

| Field | |
| --- | --- |
| `lesson_id` | A short name for the files, such as `math6-ratios-lesson`: save the lesson as `<lesson_id>.json`. |
| `title` | The lesson's name, on the title slide and the plan. Short: it's 40-56pt on the slide. |
| `subject`, `grade_band` | As on the worksheet ("Science", "3rd grade"). The grade sets type sizes; the subject sets the colors. |
| `minutes` | The class period. The sequence's minutes should add up to it. |
| `worksheet` | The folder `make` wrote, relative to this file. Leave it out for a lesson with no worksheet. |
| `objectives` | What students will be able to do, as the teacher writes it ("Students will be able to..."). |
| `targets` | (optional) The same for students, for the learning-target slide ("I can..."). Made from the objectives if left out. |
| `standards` | (optional) Only standards the teacher gave you, or codes you're certain of, with a few words each. Never guess a code. |
| `materials` | (optional) What the teacher needs besides the slides and the worksheet, which are listed for you. |
| `vocabulary` | (optional) `[{"term", "meaning", "example"}]`. In the plan, and on a `vocab` slide that has no words of its own. Keep meanings to about 12 words, or the slide runs over its word limit; give the `vocab` slide its own shorter `words` if the plan needs longer ones. |
| `sequence` | The lesson, phase by phase (below). |
| `checks` | (optional) Questions to ask during the lesson to check understanding. |
| `misconceptions` | (optional) `[{"misconception", "response"}]`: what students tend to get wrong, and how to answer it. |
| `differentiation` | (optional) `{"support": [...], "extension": [...], "language": [...], "accommodations": [...]}`. "language" is for multilingual learners; "accommodations" for IEP and 504 plans (read-aloud, extended time, large print). The plan always adds extended time for the worksheet. |
| `assessment` | What mastery looks like: what a student who met the objective can do. The worksheet's part is written for you. |
| `homework`, `notes` | (optional) A sentence or two each, for the plan. |
| `walkthrough` | How to explain each worksheet question (below). |
| `skip` | (optional) Opening slides to leave out: any of `"title"`, `"targets"`, `"agenda"`. |
| `subtitle`, `say` | (optional) A line under the title, and notes for the title slide. |

The deck opens with a title slide, the learning targets, and an agenda ("Today") made from the sequence.

## The sequence

Each phase: `{"phase": "Mini-lesson", "minutes": 15, "teacher": "...", "students": "...", "slides": [...]}`.

- `teacher` and `students` say what each does, for the plan's table. `teacher` also heads the notes of
  the phase's first slide.
- `slides`: the phase's slides, in order (types below). A phase can have none (a lab, a discussion).
- `"worksheet": true` adds a "Worksheet time" slide: a picture of page 1, the minutes, and a reminder to
  write the class ID number, not a name. `"then"`: what to do when finished.
- `"walkthrough": true` (every question) or `[1, 4]` (those questions) adds the go-over slides for them.
  On the same day as the worksheet, collect the sheets first: the scan has to show each student's own
  work, so students shouldn't correct their sheets as you go over them. `lesson` puts that reminder in
  the plan and the notes. Going over the marked sheets the next day (`go-over.pptx`, or `PL goover` after
  marking) is usually better.
- `"divider": true` opens the phase with a dark section slide.
- `"review": "<marking folder>"` (a path from the lesson file) opens with an earlier worksheet's go-over,
  from its marked class. You get:
  - how each question went;
  - the most-missed questions (`"most": 2` keeps it short; about 3 minutes each), each with how the class
    answered, the common mistake, and the worked answer;
  - a "Fix it" slide, where students fix one mistake on their marked copy.

  Its explanations come from that marking's `goover.json`; write it first (see the end of this file). The
  plan reminds the teacher to bring the marked copies. Use it to open the next day's lesson: feedback
  matters most while the work is fresh.

  ```json
  {"phase": "Yesterday's worksheet", "minutes": 8, "review": "../math6-ratios-01/marking-2026-10-27", "most": 2,
   "teacher": "Go over the two most-missed questions; students fix one mistake on their marked copy."}
  ```

Typical phases: Warm-up (or Do now), Mini-lesson, Guided practice, Worksheet, Go over it, Exit ticket.
Plan time the way the teacher would: a 15-minute worksheet with 6 questions is about right for grade 6;
younger students need longer per question.

## Slides

Every slide takes `"say"`: what the teacher says or asks, in the speaker notes. Put the teaching there,
and keep the slide itself short: the type is big enough for the back row, so it holds few words. `lesson`
warns when a slide has more words than the grade's limit, or text that won't fit.

Write `**bold**` for emphasis. Math reads as typed: "2 : 3", "3 × 4 = 12", "x ≤ 5", "½".

| `type` | Fields | Use it for |
| --- | --- | --- |
| `points` | `title`, `points` (2-4 short lines), and optionally `callout` (one key sentence in a card at the bottom), `image` or `diagram` (beside short points, or below them when it's wide) | Explaining an idea. Leave out `points` for a slide that's just the picture, full size: a labeled diagram, a map, a timeline. |
| `example` | `title`, `problem`, `steps`, `answer`, optionally `diagram`/`image`, `"reveal": true`, `"code": true` (the problem is code, shown line for line in a monospace font) | A worked example. With `reveal`, one slide per step, so the class can predict each step before it appears. |
| `vocab` | optionally `title`, `words` (`[{"term", "meaning", "example"}]`, up to 6) | Key words, as cards. Without `words` it uses the lesson's `vocabulary`. |
| `question` | `prompt`, optionally `title` (default "Quick check"), `choices` (2-6), `answer` (a letter for choices, else the answer), `why`, `mode` ("Turn and talk", "Whiteboards", "Thumbs"), `minutes`, `diagram`/`image`, `answer_say` (notes for the answer slide; `say` is for the question slide), `choice_labels` (`"numbers"` for 1-4 instead of A-D) | A question for the whole class: warm-up, check for understanding, exit ticket. With `answer`, a second slide shows it (except in an exit-ticket phase, where the answer goes in the notes). The plan lists every slide question with its answer. |
| `compare` | `title`, `left` and `right` (each `{"heading", "points"}`), optionally `callout` | Two things side by side: right and wrong method, two characters, before and after. |
| `passage` | `title`, `text`, optionally `source`, `line_numbers`, `first_line`, `focus` (a question about it), `focus_label` | A short text to read together: a stanza, a quote, a primary source excerpt. Quote only the part you'll discuss. Each `\n` starts a new line (and a new number): use it for verse, code, and numbered lines; write prose as one paragraph per `\n`, not with the worksheet's line breaks. |
| `code` | as `passage`; numbered by default | Code to read or trace, in a monospace font. |
| `section` | `title`, optionally `subtitle`, `chip` | A dark divider slide. |

Any slide also takes `chip`: a short label beside the title ("Try it", "2 min").

A primary source or a quotation must be word for word. Quote one only if you're sure of its exact
wording, or the teacher gave it to you, and tell the teacher where to check it (the Avalon Project, the
National Archives, a published edition). Otherwise paraphrase, and say it's a paraphrase.

`diagram` is the worksheet diagram format (`references/worksheet-format.md`: shapes, `axes`,
`number_line`, `fraction`, `bar_chart`, `staff`, and the rest), drawn as a picture on the slide. `image`
is a picture file the teacher gave you (a photo, a map), relative to the lesson file; add `alt`, a few
words saying what it shows.

## Walkthrough: explaining each worksheet question

`walkthrough` is a list, one entry per worksheet question:

| Field | |
| --- | --- |
| `q` | The question's number. |
| `think` | A question to ask before showing the answer ("What do you divide to find the cost of one?"). On the question slide. |
| `idea` | The one idea the question tests, in a sentence. At the top of the answer slide. |
| `steps` | How to get the answer, 1-4 short steps. They're numbered for you: don't number or letter them. |
| `mistakes` | The likely wrong turns, a sentence each ("Adding 2 to each row instead of multiplying."). |
| `model` | For a written answer: a model answer at the grade's level (it replaces the key on the slide). |
| `draw` | For a drawing or labeling question: the answer, drawn on the question's diagram in color (below). |
| `say`, `ask` | Notes for the answer slide and the question slide. |

The question slide shows the question exactly as printed. The answer slide shows it again with the key's
answers written in: words in each box, the right letter circled, the math answer beside the steps.

`draw` takes shapes in the question diagram's own coordinates (the same ones its `shapes` use: points, with
x to the right and y up from the diagram's bottom-left corner), plus two helpers that use its scale instead:
- `{"shape": "plot", "points": [[2, 3], [4, 6]], "line": true}`: points on the diagram's `axes`, in graph
  units, joined if `line` is true. `"extend": true` instead draws the line through the first and last
  points across the whole grid (through the origin, if it passes there).
- `{"shape": "mark", "at": [0.75]}`: points on its `number_line`.

For example, an arrow from (40, 60) to (120, 60) is `{"shape": "arrow", "points": [[40, 60], [120, 60]]}`.
The drawing goes on the answer slide and in the answer key.

Write a walkthrough for every question. The go-over deck shows a question without one with only its key.

## After marking: `PL goover`

`PL goover "<work>" [--lesson "<folder>/<lesson>.json"] [--most N] [--out "<folder>"]` reads the marking
run's results and makes `<work>/out/go-over.pptx` (and `.pdf`; `--out` puts them elsewhere):
1. "How it went": full credit on each question, as a bar chart.
2. "You've got these": questions 85% or more of the class got, with their key idea.
3. For every other question, most missed first: the question with how the class answered (a chart of the
   letters chosen, or full, partial, and no credit), the wrong answers two or more students gave, and what
   you noticed; then its answer worked through.

Each question gone over takes about 2 minutes. For a short go-over, `--most 3` takes only the three most
missed (the overview still shows them all).

Run it once: it also writes `<work>/out/go-over-todo.md`, listing for each question it goes over the
wrong answers two or more students gave and the crops of the answers that missed. If you marked this
scan in this session, you already know what went wrong; if not, look at those crops. Then write
`<work>/goover.json` and run `goover` again:

```json
{"questions": [
  {"q": 1, "saw": "Most of you got 2 batches right, then added 2 for 4 batches instead of doubling again."},
  {"q": 4, "saw": "C was popular: it adds 2 to each part.", "think": "Does adding keep the taste the same?"}
]}
```

`saw` is one or two sentences to the class about the mistake you saw most, with no student named or
identifiable. An entry can also carry any walkthrough field, which replaces the lesson's for that
question; without a lesson file, give each question you'll go over its `idea`, `steps`, and `mistakes`
here.

Nothing on these slides identifies a student: there are only class totals, and a wrong answer appears
only when two or more students gave it.

## Checking the deck

1. Fix every `Check:` line `lesson` prints.
2. `PL preview "<out>/slides.pdf" --sheet` shows nine slides to an image: look at each sheet for text
   that's cramped, a picture too small to read, or a slide with nothing on it but a title.
3. Open any slide that looks wrong on its own (`PL preview "<out>/slides.pdf" --page N`).
4. Check the go-over deck the same way: is each answer written in the right box, and the right letter circled?
5. `PL preview "<out>/lesson-plan.docx"` prints the plan's text, to read through.
6. Delete the `preview` folders when you're done: they're for you, not the teacher.
