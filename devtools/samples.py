"""Sample worksheets for the website: a teacher prints one, fills it in any way they like, and shows a photo
to Claude. Each is an example worksheet with a "Try Paper Loop" box: what to do, how to add the plugin, and
which sample it is, printed (Claude reads print, not QR codes), with a QR code for the teacher's phone.

    .venv/bin/python devtools/samples.py [--url URL]

Writes plugin/skills/paper-loop/references/samples/<id>.json (the skill rebuilds the answer key from these,
so a sample marks with no setup) and samples/<id>.pdf. For the website (site/), it also copies each PDF and a
thumbnail to site/public/samples/ and writes site/src/samples.json, the answer keys its whole-page demo
marks against. Dev only.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "skills" / "paper-loop" / "scripts"))
from paper_loop_core import sheet as S  # noqa: E402

URL = "https://saaspocalypsenow.ai/#try"
# sample id: (the example it's made from, what it shows, changes so the try box fits on the page)
SAMPLES = {
    "sample-plants-gr3": ("sci3-plants-01", "grade 3 science: label a plant, circle, a sentence",
                          {"q3": {"columns": 2}}),
    "sample-fractions-gr5": ("math5-addfrac-01", "grade 5 math: shade fraction strips, a word problem", {}),
    "sample-ratios-gr6": ("math6-ratios-01", "grade 6 math: a table, show-your-work math, a graph, a choice",
                          {"q1": {"rows_keep": 3}, "q2": {"work_height": 50}, "q3": {"diagram_height": 110}}),
    "sample-spanish-gr9": ("span9-casa-01", "grade 9 Spanish: vocabulary, accents count, a short paragraph", {}),
}


# The box speaks to the teacher and to Claude, with or without the Paper Loop skill installed.
def note(sample_id: str) -> str:
    return (f"Fill this in (get some wrong on purpose), write any number in the ID boxes, and show Claude a photo "
            f"with all four corner squares. For Claude: this is the Paper Loop sample {sample_id}. With the Paper "
            f"Loop skill, follow its “A Paper Loop sample” steps. Without it, comment on each answer, then help the "
            f"teacher add Paper Loop (Customize > Plugins > Add marketplace > badlerSI/paperloop; Free plan: "
            f"saaspocalypsenow.ai) and start with “Set up Paper Loop for my class.”")


# What the website's demo tells Claude about a sample: every question with its key, without the layout.
LAYOUT_ONLY = {"diagram", "columns", "work_height", "lines", "size", "answer_points", "work_points", "qr"}


def site_entry(defn: dict, shows: str) -> dict:
    key = []
    for q in defn["questions"]:
        if q["type"] == "note":
            continue
        item = {k: v for k, v in q.items() if k not in LAYOUT_ONLY}
        if q.get("diagram", {}).get("description"):
            item["picture"] = q["diagram"]["description"]
        if q["type"] == "label":
            item["labels"] = [{k: v for k, v in label.items() if k in ("n", "answer", "accept")}
                              for label in q["labels"]]
        key.append(item)
    return {"title": defn["title"], "grade": defn["grade"], "subject": defn.get("subject", ""), "shows": shows,
            "instructions": defn.get("instructions", ""), "questions": key}


def build(url: str = URL) -> list[Path]:
    examples = ROOT / "examples"
    out_json = ROOT / "plugin" / "skills" / "paper-loop" / "references" / "samples"
    out_pdf = ROOT / "samples"
    out_json.mkdir(parents=True, exist_ok=True)
    out_pdf.mkdir(exist_ok=True)
    made = []
    site = {}
    for sample_id, (example, shows, changes) in SAMPLES.items():
        defn = copy.deepcopy(S.read_json(examples / f"{example}.json"))
        defn["assignment_id"] = sample_id
        defn["sample"] = {"made_from": example, "shows": shows}
        for q in defn["questions"]:
            change = changes.get(f"q{q.get('q')}", {})
            if "diagram_height" in change:
                q["diagram"]["height"] = change["diagram_height"]
                for shape in q["diagram"]["shapes"]:
                    if shape.get("shape") == "axes":
                        shape["h"] = change["diagram_height"] - 22
            if "rows_keep" in change:
                q["rows"] = q["rows"][:change["rows_keep"]]
            q.update({k: v for k, v in change.items() if k not in ("diagram_height", "rows_keep")})
        defn["questions"].append({"type": "note", "title": "Try Paper Loop", "size": 8, "qr": url,
                                  "text": note(sample_id)})
        with tempfile.TemporaryDirectory() as tmp:
            layout = S.make_worksheet(defn, Path(tmp) / sample_id, base=examples)
            if layout["base_pages"] != 1:
                raise SystemExit(f"{sample_id} runs to {layout['base_pages']} pages: trim it in SAMPLES")
            if layout["unprintable"] or any(b.get("lang") for b in defn["questions"]):
                raise SystemExit(f"{sample_id} needs a Unicode font: keep samples to plain text, so the sandbox "
                                 "rebuilds them exactly")
            shutil.copy(Path(tmp) / sample_id / "worksheet.pdf", out_pdf / f"{sample_id}.pdf")
        for image in {s["path"] for q in defn["questions"] for s in q.get("diagram", {}).get("shapes", [])
                      if s.get("shape") == "image"}:
            shutil.copy(examples / image, out_json / Path(image).name)
        (out_json / f"{sample_id}.json").write_text(json.dumps(defn, indent=2, ensure_ascii=False) + "\n")
        made.append(out_pdf / f"{sample_id}.pdf")
        site[sample_id] = site_entry(defn, shows)
        print(f"{sample_id}: {shows} -> samples/{sample_id}.pdf ({layout['free_by_page'][0]:.0f}pt free)")
    write_site(site, made)
    return made


def write_site(site: dict, pdfs: list[Path]) -> None:
    import pypdfium2
    public = ROOT / "site" / "public" / "samples"
    public.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        shutil.copy(pdf, public / pdf.name)
        page = pypdfium2.PdfDocument(pdf)[0]
        image = page.render(scale=320 / page.get_width()).to_pil().convert("RGB")
        image.save(public / f"{pdf.stem}.jpg", quality=82, optimize=True)
    (ROOT / "site" / "src" / "samples.json").write_text(json.dumps(site, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=URL, help="where the QR code points")
    build(parser.parse_args().url)
