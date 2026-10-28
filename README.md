# Paper Loop

Print worksheets, scan the class stack on the school copier, and get marked-up paper back: comments beside every answer, a strength and next steps at the bottom, the grade only if you want it. The copier only scans and prints.

It comes two ways: a Claude Cowork plugin, where Claude marks the work within a teacher's Claude account, and a command-line version that calls the API with your own key. The command-line version is the test bench for accuracy.

Status: v0.3. [SPEC.md](SPEC.md) is the plan, [NOTES.md](NOTES.md) is where things stand.

## For teachers: use it inside Claude, no setup

Paper Loop is also a plugin for Claude Cowork. Claude does the marking itself, so there's no API key and nothing to install on your computer. Cowork works in the Claude desktop app and in a web browser, including on a Chromebook. US K-12 teachers can get it free through [Claude for Teachers](https://www.anthropic.com/news/claude-for-teachers).

1. In Claude, open Cowork, then **Customize → Plugins**, and add the marketplace `Badlerz/paperloop`. Install **Paper Loop**. You can also zip the `plugin/` folder and upload it there.
2. **Plan a lesson**, if you want one: "Plan a 50-minute 6th grade lesson on equivalent ratios, with slides and a one-page Paper Loop worksheet." You get:
   - `lesson-plan.docx`: objectives, materials, vocabulary, a timed sequence with slide numbers, checks for understanding, misconceptions, differentiation, and every worksheet answer worked through;
   - `slides.pptx`: the lesson, with what to say in the speaker notes. It opens in PowerPoint, Keynote, or Google Slides, and `slides.pdf` is the same deck;
   - `go-over.pptx`: each worksheet question as printed, then its answer written in and explained;
   - `answer-key.pdf`, and the worksheet itself.
3. **Make a worksheet**, in any subject from grade 2 to grade 12: "Make me a one-page Paper Loop worksheet on the water cycle for 6th grade: two multiple choice, a short answer, a diagram to label, and one to draw." Print the PDF it gives you. A worksheet can have:
   - reading passages with line numbers, and code listings;
   - short answers, paragraphs scored on a rubric, and essays that run onto more pages;
   - multiple choice, fill-in-the-blank, matching, ordering, and tables to fill;
   - show-your-work math with a separate answer box;
   - diagrams to label, maps (your own image), coordinate grids, number lines, fraction models, clocks, timelines, bar charts, music on a staff or a rhythm line, and drawings judged on a checklist.

   Grades 2-3 get big print, primary-ruled lines, and 2-digit class numbers. Math symbols, chemical formulas, and accents print as written.

   **Every student, the same high bar:**
   - **Versions.** Ask for versions of the same sheet for the students who need them: scaffolds (plain wording, a hint, steps, a worked example, sentence starters, a word bank), large print, more room to write, fewer per page, graph paper, a multiplication chart, or the student's home language. Translations cover the 30-plus most common home languages of US English learners; Bengali, Nepali, Burmese and other scripts the PDF can't shape go on a Word page. Each version looks like everyone else's sheet, and they're all marked from one scan.
   - **Homework.** Ask for "a different copy for each student" and every copy gets its own numbers, items, and choice order, so copying a neighbor stops working.
   - **Enrichment.** Ask for a reading on anything and Claude adapts one from Wikipedia, Simple English Wikipedia, Project Gutenberg, or a government source. The credit line the license asks for prints under it.
4. Students write their class ID number in the boxes, never their name.
5. Scan the stack on the copier (to Google Drive, email, or USB), in any order and orientation. Give Claude the PDF: "Mark this scan of Water's Wild Ride."
6. Claude reads every answer, asks you about anything it isn't sure of, and gives you one PDF to print and hand back.
7. **Go over it**: "Make slides to go over what they missed." The deck starts with how the class did on each question, then takes the most-missed questions first: how the class answered (a chart of the letters chosen, the wrong answers two or more students gave), then the answer worked through, and ends with students fixing one mistake on their marked copy. Nothing on it identifies a student. Planning tomorrow's lesson? It can open with these slides.
8. **Practice what they missed**: "Make practice sheets." Each student gets a sheet of the questions they missed, with new numbers and last time's comment above each one, and their ID already printed. Scan them back the same way.
9. **See progress**: "How is my class doing?" You get:
   - a dashboard that opens in any browser (skills student by student, groups for the next lesson, what marking noticed);
   - a progress page for each family, in their language if you like;
   - a gradebook file.

   Students are known only by class ID; the family page has a line for you to write the name.

Privacy: Claude only looks at the cropped answers and the ID boxes, never the whole page, and never sees names. On your own Claude for Teachers account, keep student work de-identified (class ID numbers, no names) unless your school or district has authorized Claude for student records. See [Anthropic's terms for teachers](https://support.claude.com/en/articles/15926041-claude-for-teachers-your-data-and-our-terms).

The plugin is in [`plugin/`](plugin/). Its scripts use only numpy, scipy, Pillow, pypdfium2, reportlab, and python-pptx, which Claude's sandboxes ship with. The skill's instructions are [`plugin/skills/paper-loop/SKILL.md`](plugin/skills/paper-loop/SKILL.md).

## Setup (the command-line version, for testing and development)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # then paste your Anthropic API key into .env
```

Commands below assume the venv is active (`source .venv/bin/activate`).

## Try it without a printer

`simulate` writes a fake scanned class set: four students in handwriting fonts, one sheet upside down, a blank page, pages shuffled. `--mock` marks without calling the model.

```bash
paperloop make examples/sci7-density-01.json
paperloop simulate assignments/sci7-density-01
paperloop run scans/sim/sim-class.pdf --assignment assignments/sci7-density-01 --mock --accept-all
open runs/sim-class/out/returned.pdf
```

Drop `--mock` once `.env` has a key, then compare the marks with what the fake students wrote:

```bash
paperloop score runs/sim-class --truth scans/sim/sim-class.truth.json
```

## Day 1 with real paper

1. `paperloop make examples/sci7-density-02.json`, then print `assignments/sci7-density-02/worksheet.pdf` four times, double-sided. (`sci7-density-01` is the plain short-answer version.)
2. `paperloop fill-guide assignments/sci7-density-02 --truth scans/day1/truth.json` prints what to write, circle, label, and draw on each copy (clean, messy, crossed out with misspellings, blank) and saves the matching answer key.
3. Scan the four sheets at 300 dpi grayscale into `scans/day1/`. One PDF or several is fine, in any order and any orientation. A feeder that scans one side at a time (like the HP 3301sdw's) works fine: scan the fronts to one PDF, flip the stack, and scan the backs to a second PDF. On a Mac, the built-in Image Capture app can scan straight into the folder.
4. `paperloop run scans/day1/*.pdf --assignment assignments/sci7-density-02 --work runs/day1`
5. `paperloop score runs/day1 --truth scans/day1/truth.json`
6. Print `runs/day1/out/returned.pdf` and mark every misread and every wrong or unhelpful comment.

## Writing a worksheet

A worksheet is a JSON file; see [examples/sci7-density-02.json](examples/sci7-density-02.json) ("Density Detectives") for every question type. Each question has a `type`:

| Type | Students | How it's marked |
| --- | --- | --- |
| `short` | write in a ruled box | The model transcribes literally, then judges against `key`. |
| `choice` | circle one letter | Read from the scan: no model call. Only an unclear mark (say, one circled, crossed out, and another circled) goes to the model. Each option's `why` is printed beside the question when it's chosen. |
| `label` | write in numbered boxes on a printed diagram | The model reads each box against its `answer` and `accept` list. Misspellings that still name the right thing count. |
| `draw` | draw into a frame over a printed scaffold | The model first describes what's drawn, then checks each `checklist` item ("yes", "no", "unclear"). One point per item. |

Worksheet-level settings:
- **`"compact": true`** tightens spacing to fit more on a page; see [examples/sci6-water-01.json](examples/sci6-water-01.json) for 6 questions on one sheet.
- **`"columns"`** on a choice question puts short options side by side.
- **`"id_style": "write"`** swaps the bubble grid for four handwritten ID boxes. These are read by the model in a request containing only the ID strip. An unclear digit, or an ID missing from `--roster`, goes to the review pile. With a roster, an ID read at 0.5 confidence or more is accepted when no classmate's ID is one digit away; otherwise it needs 0.9. Give a roster: on real handwriting the model is right but rarely above 0.9 sure. The default is `"bubbles"`, which are read on the laptop.

Diagrams for `label` and `draw` are a list of `shapes` (`rect`, `circle`, `line`, `arrow`, `polyline`, `polygon`, `text`) in points, with the origin at the diagram's bottom-left. For labels and drawings, the model gets the blank printed region next to the student's version, so it can tell their marks from the printing. Write checklist items as things you can see on the page ("the iron box has clearly more particles"), not as judgments ("shows understanding of density").

Each worksheet's simulated students live in `examples/<assignment_id>.students.json`, and `simulate` and `fill-guide` read them.

## Compare models and effort levels

`sweep` re-marks one ingested scan set with every model and effort combination and scores each run against the truth file. It spends API credit: about $2–3 for 3 models × 3 efforts × 3 repeats on the simulated set.

```bash
paperloop sweep runs/day1 --truth scans/day1/truth.json --reps 3
```

## The pipeline

| Step | Command | What happens |
| --- | --- | --- |
| Make | `make` | Lays out the worksheet PDF and writes `layout.json` (every box's position) and `key.json`. |
| Ingest | `ingest` | Straightens each page using the corner squares, then takes out paper curl by lining up the printing. Reads the QR code (assignment and page) and the student ID. Anything uncertain goes to the review pile. |
| Mark | `mark` | Crops each answer box and sends it to Claude with the key, one box at a time; empty boxes never leave the laptop. Writes `feedback.json` with tokens and cost. |
| Review | `review` | Walks you through flagged answers (low confidence, unreadable, unclear key). Nothing renders until they're done. `review.html` shows the crops. |
| Render | `render` | Stamps comments beside each box and the summary at the bottom; one PDF sorted by student ID. `--grade off/back/csv`. |
| Clean | `clean` | Deletes scans and crops after printing. |

`run` does ingest through render in one go.

## Privacy

- Students write a 4-digit ID, never a name. Bubbles are read on the laptop, never by the model.
- Only cropped answer boxes go to the API: never the header, the ID area, or the margins.
- Real student work needs a district-owned key under Anthropic's [US K-12 terms](https://anthropic.com/legal/k12-terms) and [K-12 DPA](https://anthropic.com/legal/k12-dpa); confirm they cover API use first. Day 1 uses only Ben's handwriting.
- `runs/`, `scans/`, and `.env` are gitignored.

## License

Apache 2.0. Runtime dependencies are all Apache-compatible: reportlab (BSD), pypdf (BSD), pypdfium2 (Apache 2.0/BSD), OpenCV (Apache 2.0), qrcode (BSD), anthropic (MIT), pydantic (MIT), typer (MIT), python-dotenv (BSD), numpy (BSD), Pillow (MIT-CMU). Plom (AGPL) is used as a design reference only; see [docs/plom-spike.md](docs/plom-spike.md).
