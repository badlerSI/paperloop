"""A fill-in guide for testing a plugin worksheet with real handwriting.

    .venv/bin/python devtools/guide.py ASSIGNMENT_DIR STUDENTS.json OUT_DIR

Writes OUT_DIR/worksheet.pdf (print one copy per page of the guide), OUT_DIR/guide.pdf (each copy as it
should look when filled in: copy it in your own handwriting), OUT_DIR/assignment/ (what marking needs) and
OUT_DIR/truth.json (the students file, for devtools/score.py once the scan is marked). The guide pictures come from devtools/fill.py's simulated
handwriting, without the scan damage. Dev only, never shipped.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fill import L, S, fill_page  # noqa: E402

KINDS = {"short": "write", "choice": "circle", "label": "boxes", "blanks": "boxes", "match": "boxes",
         "table": "boxes", "math": "work and answer", "draw": "draw"}


def notes(answers: dict, key: dict) -> list[str]:
    """One line per question saying what to do, for things a picture doesn't make obvious."""
    out = []
    for item in key["items"]:
        a = answers.get(str(item["q"]))
        if not a:
            out.append(f"Q{item['q']}: leave blank")
        elif item["type"] == "choice":
            marks = a["circle"]
            out.append(f"Q{item['q']}: " + ", then ".join(
                f"circle {m.strip('~')} and cross it out" if m.startswith("~~") else f"circle {m}" for m in marks))
        elif item["type"] == "short":
            out.append(f"Q{item['q']}: \"{a['text']}\" (keep any misspellings)")
        elif item["type"] == "math":
            out.append(f"Q{item['q']}: work " + " / ".join(f"\"{w}\"" for w in a.get("work", [])) +
                       (f"; answer \"{a['answer']}\"" if a.get("answer") else "; no answer"))
        elif "boxes" in a:
            filled = [f"{n}: {t}" for n, t in a["boxes"].items() if t]
            out.append(f"Q{item['q']}: " + ", ".join(filled))
        else:
            out.append(f"Q{item['q']}: draw what the picture shows")
    return out


def main(assignment: Path, students_path: Path, out_dir: Path) -> None:
    layout = S.read_json(assignment / "layout.json")
    key = S.read_json(assignment / "key.json")
    roster = json.loads(students_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(assignment / "worksheet.pdf", out_dir / "worksheet.pdf")
    (out_dir / "assignment").mkdir(exist_ok=True)  # what marking the scan needs, as `make` wrote it
    for name in ("worksheet.pdf", "worksheet.json", "layout.json", "key.json"):
        shutil.copy(assignment / name, out_dir / "assignment" / name)
    blanks = L.render_pdf(assignment / "worksheet.pdf")
    rng = random.Random(5)
    c = canvas.Canvas(str(out_dir / "guide.pdf"), pagesize=letter)
    W, H = letter
    copies = len(roster["students"]) * len(layout["pages"])
    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, H - 72, f"Fill-in guide: {layout['title']}")
    c.setFont("Helvetica", 11)
    lines = [f"Print {len(roster['students'])} copies of worksheet.pdf ({copies} sheets). Fill in each copy to match its "
             "page in this guide, in your own handwriting: same ID, same answers, mistakes and crossings-out "
             "included. Pencil or pen both work. Then scan the stack in any order and mark it with the skill, "
             "using the assignment folder beside this guide.", "",
             *[f"ID {s['id']} ({s.get('style', 'clean')}): " + "; ".join(notes(s["answers"], key))
               for s in roster["students"]]]
    y = H - 100
    for line in lines:
        for part in simpleSplit(line, "Helvetica", 10, W - 108) or [""]:
            c.drawString(54, y, part)
            y -= 14
    c.showPage()
    for n, student in enumerate(roster["students"], start=1):
        for page in layout["pages"]:
            filled = fill_page(blanks[page["page"] - 1], page, key, layout.get("style", "standard"), student, rng)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(36, H - 24, f"Copy {n}: ID {student['id']}, page {page['page']} of {len(layout['pages'])}")
            scale = (H - 40) / H
            c.drawImage(ImageReader(Image.fromarray(filled)), (W - W * scale) / 2, 4, W * scale, H * scale)
            c.showPage()
    c.save()
    (out_dir / "truth.json").write_text(json.dumps({"assignment_id": layout["assignment_id"],
                                                    "students": roster["students"]}, indent=1) + "\n")
    print(f"wrote {out_dir}/worksheet.pdf, guide.pdf ({copies} copies), and truth.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
