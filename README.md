# Paper Loop

Print worksheets, scan the class stack on the school copier, and get marked-up paper back: comments beside every answer, a strength and next steps at the bottom, the grade only if you want it. The copier only scans and prints; everything else runs on the teacher's laptop.

Status: Day 1 of v0.1. [SPEC.md](SPEC.md) is the plan, [NOTES.md](NOTES.md) is where Day 1 stands.

## Setup

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
3. Scan the four sheets at 300 dpi grayscale into `scans/day1/`. On an HP Color LaserJet Pro MFP 3301sdw, put them in the document feeder and choose two-sided scanning to PDF. One PDF or several is fine, in any order: if a scanner only does one side at a time, scan the fronts, flip the stack, and scan the backs.
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
| Ingest | `ingest` | Straightens each page using the corner squares, reads the QR code (assignment and page) and the ID bubbles. Anything uncertain goes to the review pile. |
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
