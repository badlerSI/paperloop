"""Command line: make, simulate, ingest, mark, review, render, run, clean."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import anthropic
import typer
from dotenv import load_dotenv

from . import ingest as ingest_mod
from . import mark as mark_mod
from . import render as render_mod
from . import review as review_mod
from . import score as score_mod
from .make import load_assignment, make_worksheet
from .schemas import IngestResult, WorksheetDef, load
from .simulate import load_students
from .simulate import simulate as simulate_scans

app = typer.Typer(help="Print worksheets, scan the class stack, get marked-up paper back.",
                  no_args_is_help=True, add_completion=False)

GRADES = ("off", "back", "csv")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


@app.callback()
def main() -> None:
    load_dotenv()  # ANTHROPIC_API_KEY from .env in the current folder or above


def _fail(message: str) -> None:
    typer.secho(message, fg="red", err=True)
    raise typer.Exit(1)


@app.command()
def make(worksheet: Path = typer.Argument(..., help="Worksheet definition JSON (see examples/)."),
         out: Path = typer.Option(None, help="Output folder. Default: assignments/<assignment_id>.")) -> None:
    """Lay out a printable worksheet and write layout.json and key.json."""
    defn = load(WorksheetDef, worksheet)
    out = out or Path("assignments") / defn.assignment_id
    pdf, layout, _ = make_worksheet(defn, out)
    counts = ", ".join(f"page {p.page}: questions {', '.join(str(b.q) for b in p.boxes)}" for p in layout.pages)
    typer.echo(f"Wrote {pdf} ({counts})")
    typer.echo(f"Print it double-sided, then copy it for the class. Layout and key are in {out}/.")


@app.command()
def simulate(assignment: Path = typer.Argument(..., help="Assignment folder from `make`."),
             out: Path = typer.Option(Path("scans/sim/sim-class.pdf"), help="Fake scan PDF to write."),
             students: Path = typer.Option(None, help="Students file. Default: examples/<id>.students.json."),
             seed: int = typer.Option(7, help="Random seed for handwriting wobble and page order.")) -> None:
    """Write a fake filled-in, scanned class set for testing without a printer."""
    pdf = simulate_scans(assignment, out, seed=seed, students=students)
    typer.echo(f"Wrote {pdf} and {pdf.with_suffix('.truth.json')}")


@app.command()
def ingest(scans: list[Path] = typer.Argument(..., help="Scanned class-set PDF(s), in any page order."),
           assignment: Path = typer.Option(..., help="Assignment folder from `make`."),
           work: Path = typer.Option(None, help="Work folder. Default: runs/<first scan's name>.")) -> None:
    """Split, deskew, and route each scanned page by its QR code and ID bubbles."""
    work = work or Path("runs") / scans[0].stem
    _ingest(scans, assignment, work)


def _ingest(scans: list[Path], assignment: Path, work: Path) -> IngestResult:
    for scan in scans:
        if not scan.exists():
            _fail(f"No scan at {scan}")
    result = ingest_mod.ingest(scans, assignment, work)
    layout, _ = load_assignment(assignment)
    typer.echo(ingest_mod.page_map(result, len(layout.pages)))
    return result


def _marker(work: Path, model: str, effort: str, mock: bool):
    if mock:
        return mark_mod.MockMarker()
    if effort not in EFFORTS:
        _fail(f"--effort must be one of {', '.join(EFFORTS)}")
    _, key = load_assignment(Path(load(IngestResult, work / "ingest.json").assignment_dir))
    try:
        return mark_mod.ClaudeMarker(key, model=model, effort=effort)
    except anthropic.AnthropicError as e:
        _fail(f"Couldn't set up the Anthropic client: {e}\nAdd ANTHROPIC_API_KEY to .env (see .env.example).")


def _mark(work: Path, model: str, effort: str, mock: bool, threshold: float, workers: int) -> None:
    marker = _marker(work, model, effort, mock)
    try:
        feedback = mark_mod.mark(work, marker, threshold=threshold, workers=workers, progress=typer.echo)
    except mark_mod.FATAL as e:
        _fail(f"The API refused the request ({type(e).__name__}): {e}\n"
              "Check ANTHROPIC_API_KEY in .env and that the key can use this model.")
    except TypeError as e:  # raised by the SDK when it finds no credentials at all
        if "auth" not in str(e).lower():
            raise
        _fail("No Anthropic API key found. Copy .env.example to .env and paste your key there.")
    typer.echo(mark_mod.cost_report(feedback))


@app.command()
def mark(work: Path = typer.Argument(..., help="Work folder from `ingest`."),
         model: str = typer.Option(mark_mod.DEFAULT_MODEL, help="Model for marking."),
         effort: str = typer.Option(mark_mod.DEFAULT_EFFORT, help="low, medium, high, xhigh, or max."),
         mock: bool = typer.Option(False, help="Use a stand-in marker; no API calls."),
         threshold: float = typer.Option(mark_mod.DEFAULT_THRESHOLD, help="Flag answers below this confidence."),
         workers: int = typer.Option(4, help="Boxes marked at once.")) -> None:
    """Send each answer box to the model and save feedback.json with tokens and cost."""
    _mark(work, model, effort, mock, threshold, workers)


@app.command()
def review(work: Path = typer.Argument(..., help="Work folder from `mark`."),
           accept_all: bool = typer.Option(False, help="Accept every flagged answer as marked.")) -> None:
    """Go through flagged answers before anything prints."""
    left = review_mod.review(work, accept_all=accept_all, ask=input, say=typer.echo)
    if left:
        typer.echo(f"{left} flagged answers still need review.")


@app.command()
def render(work: Path = typer.Argument(..., help="Work folder from `review`."),
           grade: str = typer.Option("off", help="off, back (score on the last page), or csv."),
           force: bool = typer.Option(False, help="Render even with unreviewed flags."),
           duplex: bool = typer.Option(True, help="Pad odd page counts so each student starts a new sheet.")) -> None:
    """Stamp comments and summaries onto the scans; write one PDF sorted by student ID."""
    _render(work, grade, force, duplex)


def _render(work: Path, grade: str, force: bool, duplex: bool = True) -> None:
    if grade not in GRADES:
        _fail(f"--grade must be one of {', '.join(GRADES)}")
    try:
        result = render_mod.render(work, grade=grade, force=force, duplex=duplex)
    except render_mod.RenderBlocked as e:
        _fail(str(e))
    typer.echo(f"Wrote {result['returned']}: {result['students']} students, {result['pages']} pages. "
               "Print double-sided and hand back.")
    if "grades" in result:
        typer.echo(f"Grades: {result['grades']}")
    if "review_pile" in result:
        typer.echo(f"Pages that couldn't be routed: {result['review_pile']}")
    typer.echo(f"When it's printed, `paperloop clean {work}` deletes the scans and crops.")


@app.command()
def run(scans: list[Path] = typer.Argument(..., help="Scanned class-set PDF(s), in any page order."),
        assignment: Path = typer.Option(..., help="Assignment folder from `make`."),
        work: Path = typer.Option(None, help="Work folder. Default: runs/<first scan's name>."),
        model: str = typer.Option(mark_mod.DEFAULT_MODEL, help="Model for marking."),
        effort: str = typer.Option(mark_mod.DEFAULT_EFFORT, help="low, medium, high, xhigh, or max."),
        mock: bool = typer.Option(False, help="Use a stand-in marker; no API calls."),
        threshold: float = typer.Option(mark_mod.DEFAULT_THRESHOLD, help="Flag answers below this confidence."),
        grade: str = typer.Option("off", help="off, back (score on the last page), or csv."),
        accept_all: bool = typer.Option(False, help="Skip interactive review and accept every flag.")) -> None:
    """Scan in, marked PDF out: ingest, mark, review, render."""
    work = work or Path("runs") / scans[0].stem
    typer.secho("1/4 Reading the scan", bold=True)
    _ingest(scans, assignment, work)
    typer.secho("2/4 Marking", bold=True)
    _mark(work, model, effort, mock, threshold, workers=4)
    typer.secho("3/4 Review", bold=True)
    left = review_mod.review(work, accept_all=accept_all, ask=input, say=typer.echo)
    if left:
        _fail(f"{left} flagged answers still need review. Finish with `paperloop review {work}`, "
              f"then `paperloop render {work}`.")
    typer.secho("4/4 Rendering", bold=True)
    _render(work, grade, force=False)


@app.command("fill-guide")
def fill_guide(assignment: Path = typer.Argument(..., help="Assignment folder from `make`."),
               students: Path = typer.Option(None, help="Students file. Default: examples/<id>.students.json."),
               truth: Path = typer.Option(None, help="Also write the matching truth JSON for `score`.")) -> None:
    """Print what to write, circle, label, and draw on each test copy."""
    layout, _ = load_assignment(assignment)
    roster = load_students(layout.assignment_id, students)
    typer.echo(score_mod.guide_text(roster))
    if truth:
        truth.parent.mkdir(parents=True, exist_ok=True)
        truth.write_text(json.dumps(score_mod.guide_truth(roster), indent=2) + "\n")
        typer.echo(f"Wrote {truth}")


@app.command()
def score(work: Path = typer.Argument(..., help="Work folder from `mark`."),
          truth: Path = typer.Option(..., help="truth.json from `simulate` or `fill-guide --truth`.")) -> None:
    """Measure misreads, silent autocorrect, false 'correct', flag rate, and cost against known answers."""
    typer.echo(score_mod.score(work, truth))


@app.command("sweep")
def sweep_cmd(work: Path = typer.Argument(..., help="Work folder from `ingest` to re-mark."),
              truth: Path = typer.Option(..., help="truth.json from `simulate` or `fill-guide --truth`."),
              out: Path = typer.Option(None, help="Where runs go. Default: <work>-sweep."),
              models: str = typer.Option("claude-sonnet-5-5,claude-haiku-5-5,claude-opus-5-5",
                                         help="Comma-separated model IDs."),
              efforts: str = typer.Option("low,medium,high", help="Comma-separated effort levels."),
              reps: int = typer.Option(1, help="Runs per model and effort."),
              threshold: float = typer.Option(mark_mod.DEFAULT_THRESHOLD, help="Flag answers below this confidence."),
              parallel: int = typer.Option(3, help="Runs at once (each marks 4 boxes at a time).")) -> None:
    """Compare models and effort levels on the same scans; writes sweep.csv. Spends API credit."""
    from . import sweep as sweep_mod

    out = out or work.with_name(work.name + "-sweep")
    rows = sweep_mod.sweep(work, truth, out, [m.strip() for m in models.split(",")],
                           [e.strip() for e in efforts.split(",")], reps=reps, threshold=threshold,
                           parallel=parallel, progress=typer.echo)
    typer.echo("")
    typer.echo(sweep_mod.summary(rows))
    typer.echo(f"\nPer-run details: {out}/sweep.csv; each run's feedback.json is in {out}/<model>-<effort>-r<rep>/")


@app.command()
def clean(work: Path = typer.Argument(..., help="Work folder to clean."),
          yes: bool = typer.Option(False, "--yes", help="Don't ask first.")) -> None:
    """Delete scans and crops from a work folder; keep feedback.json and the output PDFs."""
    targets = [work / d for d in ("pages", "raw", "crops") if (work / d).exists()]
    if not targets:
        typer.echo("Nothing to delete.")
        return
    if not yes and not typer.confirm(f"Delete {', '.join(str(t) for t in targets)}?"):
        raise typer.Exit()
    for t in targets:
        shutil.rmtree(t)
    typer.echo("Deleted scans and crops. The returned PDF still shows student work; delete it once printed.")
