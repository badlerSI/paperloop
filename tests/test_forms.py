"""Versions and per-student copies: one worksheet, several printed forms, one stack to mark."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "devtools"))

from paper_loop_core import forms as FM  # noqa: E402
from paper_loop_core import goover as G  # noqa: E402
from paper_loop_core import prepare as P  # noqa: E402
from paper_loop_core import results as X  # noqa: E402
from paper_loop_core import script as SC  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402

BLOCKER = (Path(__file__).parent / "test_plugin.py").read_text().split('BLOCKER = """')[1].split('"""')[0]
VERSIONS = ROOT / "examples" / "math6-ratios-02.json"
HOMEWORK = ROOT / "examples" / "math6-ratios-hw-01.json"


def _simulate(assignment: Path, students: Path, tmp: Path) -> Path:
    """A filled, scanned class (devtools/fill.py's handwriting fonts), prepared and marked perfectly."""
    fill = pytest.importorskip("fill")
    try:
        fill.font("Noteworthy.ttc", 20)
    except OSError:
        pytest.skip("the handwriting fonts the simulator uses aren't on this machine")
    import oracle
    pdf = tmp / "scan" / "class.pdf"
    fill.main(assignment, students, pdf)
    work = tmp / "work"
    P.prepare([pdf], assignment, work)
    oracle.main(work, pdf.with_suffix(".truth.json"))
    return work


def test_versions_are_marked_from_one_mixed_stack(tmp_path):
    layout = S.make_worksheet(S.read_json(VERSIONS), tmp_path / "a", base=VERSIONS.parent)
    forms = {f["id"]: f for f in layout["forms_made"]}
    assert set(forms) == {"", "support", "lp", "es", "ar", "bn"}
    assert len({f["code_id"] for f in forms.values()}) == 6  # every form its own page code
    assert forms["support"]["modifies"] == ["a worked example", "fewer answer choices", "hints", "the steps laid out"]
    assert forms["lp"]["modifies"] == [] and forms["es"]["modifies"] == []
    assert forms[""]["label"] == "A" and forms["lp"]["large_print"] == 18  # every copy names its form; 18pt
    key = S.read_json(tmp_path / "a" / "key.json")
    support = S.form_items(key, "support")
    assert support[1]["scaffolded"] == ["a worked example", "hints"] and "scaffolded" not in support[5]
    for name in ("worksheet.pdf", "versions/support.pdf", "versions/lp.pdf", "versions/es.pdf", "versions/ar.pdf",
                 "versions/bn.pdf", "versions/support-reference.pdf", "versions/es.docx", "versions/bn.docx"):
        assert (tmp_path / "a" / name).exists(), name

    work = _simulate(tmp_path / "a", ROOT / "devtools" / "students" / "math6-ratios-02.json", tmp_path)
    manifest = S.read_json(work / "manifest.json")
    truth = S.read_json(tmp_path / "scan" / "class.truth.json")
    expected = {p["scan_index"]: (p["student_id"], p["form"]) for p in truth["scan_pages"] if p.get("student_id")}
    got = {p["scan_index"]: (p["student_id"], p["form"]) for p in manifest["pages"] if p["status"] == "ok"}
    assert got == expected  # each page routed to its student and its form
    report = X.check(work)
    assert not report["errors"]
    P.todo(work)
    q5 = (work / "todo" / "q5.md").read_text()
    assert "### Version B (Hints and steps): printed differently" in q5
    assert "Maya is ___ because ___. Read the student's writing" in q5
    assert "may answer in Spanish or English" in q5 and "Comments for these students: in Spanish" in q5
    assert "Version C" not in q5  # large print printed the question the same way: no section of its own


def test_every_student_gets_a_different_copy_marked_against_its_own_key(tmp_path):
    S.make_worksheet(S.read_json(HOMEWORK), tmp_path / "hw", base=HOMEWORK.parent)
    key = S.read_json(tmp_path / "hw" / "key.json")
    copies = [key["forms"][str(n)]["items"] for n in range(1, 31)]
    assert len({tuple(i["prompt"] for i in items) for items in copies}) == 30
    assert all(i["varies"] for i in key["items"])
    for items in copies:
        unit = items[0]
        price = Fraction(unit["answer"].strip("$"))
        n = int(unit["prompt"].split()[2])
        assert f"${float(price * n):,.2f}" in unit["prompt"]  # the answer matches its own numbers
        choice = items[2]
        right = next(o for o in choice["options"] if o["letter"] == choice["answer"])
        assert right["base"] == "A"  # shuffled, but it remembers the base copy's letter
    work = _simulate(tmp_path / "hw", ROOT / "devtools" / "students" / "math6-ratios-hw-01.json", tmp_path)
    results = X.check(work)
    assert not results["errors"]
    picks = [b["details"][0] for p in results["pages"] for b in p["boxes"] if b["type"] == "choice"]
    assert all(d.get("base_selected", d["selected"]) in "AC" for d in picks)  # right (A) or the flip (C)
    P.todo(work)
    q1 = (work / "todo" / "q1.md").read_text()
    assert "### Copy 1" in q1 and "mark each scan against its own copy" in q1
    S.write_json(work / "summaries.json", {})
    report = G.build(work)
    assert report["students"] == 6


def test_expressions():
    env = {"a": 6, "b": 4, "p": Fraction("2.25")}
    assert FM.show(FM.evaluate("a / b", env)) == "1.5"
    assert FM.show(FM.evaluate("frac(a, b)", env)) == "3/2"
    assert FM.show(FM.evaluate("1 / 3", env)) == "1/3"
    assert FM.evaluate("money(a * p)", env) == "$13.50"
    assert FM.evaluate("mixed(7/2)", env) == "3 1/2"
    assert FM.evaluate("a > b and gcd(a, b) == 2", env) is True
    with pytest.raises(S.WorksheetError, match="no variable named 'c'"):
        FM.evaluate("c + 1", env)
    with pytest.raises(S.WorksheetError, match="only arithmetic"):
        FM.evaluate("__import__('os')", env)
    with pytest.raises(S.WorksheetError, match="divides by zero"):
        FM.evaluate("a / (b - 4)", env)


def test_a_language_that_needs_shaping_goes_on_the_word_page(tmp_path):
    defn = S.read_json(VERSIONS)
    defn["versions"] = [{"id": "bn", "name": "Bengali", "language": "bn", "language_mode": "bilingual"}]
    with pytest.raises(S.WorksheetError, match="companion"):
        S.make_worksheet(defn, tmp_path / "a", base=VERSIONS.parent)
    defn["versions"][0]["language_mode"] = "companion"
    S.make_worksheet(defn, tmp_path / "b", base=VERSIONS.parent)
    xml = zipfile.ZipFile(tmp_path / "b" / "versions" / "bn.docx").read("word/document.xml").decode()
    assert "অনুপাত" in xml and 'w:val="bn"' in xml


def test_arabic_is_joined_and_reads_right_to_left(tmp_path):
    shaped = SC.shape("سلام")
    assert [hex(ord(c)) for c in shaped] == ["0xfeb3", "0xfefc", "0xfee1"]  # seen, lam-alef ligature, final meem
    assert SC.visual("ثمن 6 أكواب") == "باوكأ 6 نمث"
    assert SC.rtl_line("ثمن 6") and not SC.rtl_line("ratio = نسبة")
    S.make_worksheet(S.read_json(VERSIONS), tmp_path / "a", base=VERSIONS.parent)
    xml = zipfile.ZipFile(tmp_path / "a" / "versions" / "ar.docx").read("word/document.xml").decode()
    assert "<w:bidi/>" in xml and "<w:rtl/>" in xml


def test_fewer_choices_keep_their_letters_and_large_print_scales(tmp_path):
    S.make_worksheet(S.read_json(VERSIONS), tmp_path / "a", base=VERSIONS.parent)
    key, layout = S.read_json(tmp_path / "a" / "key.json"), S.read_json(tmp_path / "a" / "layout.json")
    support = S.form_items(key, "support")[4]
    assert [o["letter"] for o in support["options"]] == ["A", "B", "C"]  # D dropped first, as its support says
    base_q3 = next(b for p in S.form_pages(layout) for b in p["boxes"] if b["q"] == 3)
    lp_q3 = next(b for p in S.form_pages(layout, "lp") for b in p["boxes"] if b["q"] == 3)
    width = lambda b: b["rect"][2] - b["rect"][0]  # noqa: E731
    assert lp_q3["scale"] == pytest.approx(18 / 10.5)  # true is 18pt; the compact sheet prints at 10.5pt
    assert width(lp_q3) == pytest.approx(width(base_q3) * 18 / 10.5)
    assert all(len([b for b in p["boxes"]]) <= 2 for p in S.form_pages(layout, "lp"))  # per_page


def test_versions_make_in_the_sandbox(tmp_path):
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(SCRIPTS / "paper_loop.py"), "make", str(VERSIONS),
                          "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "Version B, Hints and steps" in run.stdout and "with help on the page" in run.stdout
    assert "Check: Claude's Bengali isn't reliable enough" in run.stdout


def test_version_errors_say_what_to_fix(tmp_path):
    defn = S.read_json(VERSIONS)
    for change, message in [({"scaffolds": ["hints"]}, "unknown scaffold hints"),
                            ({"large_print": 3}, "large_print"),
                            ({"language": "xx"}, "xx.json"),
                            ({"color": "blue"}, "unknown field color")]:
        defn["versions"] = [{"id": "v", **change}]
        with pytest.raises(S.WorksheetError, match=message):
            S.make_worksheet(defn, tmp_path / "x", base=VERSIONS.parent)
    hw = S.read_json(HOMEWORK)
    hw.pop("variants")
    with pytest.raises(S.WorksheetError, match="add \"variants\""):
        S.make_worksheet(hw, tmp_path / "y", base=HOMEWORK.parent)
    hw["variants"] = {"count": 3}
    hw["questions"][0]["where"] = "n > 100"
    with pytest.raises(S.WorksheetError, match="no values of the variables meet"):
        S.make_worksheet(hw, tmp_path / "z", base=HOMEWORK.parent)


def test_practice_sheets_give_each_student_their_misses_and_scan_back_on_their_own(tmp_path):
    from paper_loop_core import practice as PR
    S.make_worksheet(S.read_json(HOMEWORK), tmp_path / "hw", base=HOMEWORK.parent)
    work = _simulate(tmp_path / "hw", ROOT / "devtools" / "students" / "math6-ratios-hw-01.json", tmp_path)
    X.check(work)
    report = PR.build(work, tmp_path / "practice")
    missed = {sid: qs for sid, qs in report["questions"].items() if sid in ("0203", "0206")}
    assert missed == {"0203": [2, 3, 4], "0206": [2, 3, 4]}  # every third student slipped on 2-4
    assert report["all_right"] == ["0201", "0202", "0204", "0205"]
    assert report["stretched"] == report["all_right"]  # full credit: a stretch sheet, so every student gets one
    assert all(1 <= len(report["questions"][sid]) <= 2 for sid in report["stretched"])
    key = S.read_json(tmp_path / "practice" / "key.json")
    hw_key = S.read_json(tmp_path / "hw" / "key.json")
    sheet = S.form_items(key, "p0203")
    assert sheet[2]["prompt"] != S.form_items(hw_key, "3")[2]["prompt"]  # new numbers, not the copy they had
    assert sheet[3]["asides"][0] == {"kind": "last_other", "text": "That flips the ratio: more mango than yogurt."}
    layout = S.read_json(tmp_path / "practice" / "layout.json")
    assert {p["student_id"] for p in layout["pages"] if p.get("student_id")} == {"0201", "0202", "0203", "0204",
                                                                                   "0205", "0206"}
    fill = pytest.importorskip("fill")
    students = {"students": [{"id": sid, "form": f"p{sid}", "style": "clean", "answers": {
        "4": {"text": "times 3, so 15", "expected": "correct"}}} for sid in ("0203", "0206")]}
    (tmp_path / "practice-students.json").write_text(json.dumps(students))
    fill.main(tmp_path / "practice", tmp_path / "practice-students.json", tmp_path / "pscan" / "p.pdf")
    manifest = P.prepare([tmp_path / "pscan" / "p.pdf"], tmp_path / "practice", tmp_path / "pwork")
    routed = {p["student_id"] for p in manifest["pages"] if p["status"] == "ok"}
    assert routed == {"0203", "0206"} and not manifest["id_sheets"]  # no handwriting to read


SAMPLES = ROOT / "plugin" / "skills" / "paper-loop" / "references" / "samples"


@pytest.mark.parametrize("path", sorted(SAMPLES.glob("sample-*.json")), ids=lambda p: p.stem)
def test_a_website_sample_rebuilds_exactly_and_its_qr_points_home(path, tmp_path):
    """The skill rebuilds a sample from references/samples, and the rebuild prints the same page as the PDF
    on the website, so a teacher's photo of the website copy lines up with the rebuilt answer key."""
    import numpy as np
    import pypdfium2 as pdfium
    S.make_worksheet(S.read_json(path), tmp_path / path.stem, base=path.parent)
    render = lambda pdf: np.array(pdfium.PdfDocument(str(pdf))[0].render(scale=2).to_pil().convert("L"))  # noqa: E731
    site, rebuilt = render(ROOT / "samples" / f"{path.stem}.pdf"), render(tmp_path / path.stem / "worksheet.pdf")
    assert site.shape == rebuilt.shape and np.abs(site.astype(int) - rebuilt.astype(int)).max() == 0
    layout = S.read_json(tmp_path / path.stem / "layout.json")
    assert len(layout["pages"]) == 1
    defn = S.read_json(path)
    note = defn["questions"][-1]
    assert note["type"] == "note" and note["qr"].startswith("https://") and path.stem in note["text"]
    cv2 = pytest.importorskip("cv2")
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(rebuilt)
    assert decoded == note["qr"]


def test_home_language_comments_print_right_to_left_and_unprintable_ones_are_refused(tmp_path):
    import pypdfium2 as pdfium
    from paper_loop_core import render as R
    S.make_worksheet(S.read_json(VERSIONS), tmp_path / "a", base=VERSIONS.parent)
    work = _simulate(tmp_path / "a", ROOT / "devtools" / "students" / "math6-ratios-02.json", tmp_path)
    manifest = S.read_json(work / "manifest.json")
    arabic = next(p["scan_index"] for p in manifest["pages"] if p.get("form") == "ar" and "5" in p["answers"])
    marks = S.read_json(work / "marks" / "q5.json")
    marks["marks"][str(arabic)]["comment"] = "ضرب العددين يحافظ على النسبة."
    S.write_json(work / "marks" / "q5.json", marks)
    summaries = {sid: {"strength": "Clear work.", "fixes": []} for sid in ("0101", "0102", "0103", "0104", "0105")}
    summaries["0105"] = {"strength": "عمل واضح في الجدول.", "fixes": []}
    S.write_json(work / "summaries.json", summaries)
    result = X.check(work)
    assert not result["errors"]
    data, errors, _ = X.summaries(work, result["pages"])
    assert not errors
    out = R.render(work, result["pages"], data)
    doc = pdfium.PdfDocument(str(out["returned"]))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "ضرب العددين يحافظ على النسبة." in text and "عمل واضح في الجدول." in text  # printed, and it reads back
    marks["marks"][str(arabic)]["comment"] = "অনুপাত ঠিক রাখতে গুণ করো।"
    S.write_json(work / "marks" / "q5.json", marks)
    assert any("Bengali" in e and "can't print" in e for e in X.check(work)["errors"])


def test_dari_hamza_and_brackets():
    assert SC.compose("خانه" + chr(0x654)) == "خانۀ"
    assert SC.visual("x (ابت)") == "x (تبا)"


def test_a_key_words_page_needs_no_glossary_on_the_sheet_and_a_long_version_says_what_to_cut(tmp_path):
    import pypdfium2 as pdfium
    defn = S.read_json(VERSIONS)
    defn["versions"] = [{"id": "kw", "name": "Key words page", "scaffolds": ["hint"], "reference": ["glossary"]},
                        {"id": "roomy", "name": "Roomy", "scaffolds": "all"}]
    layout = S.make_worksheet(defn, tmp_path / "w", base=VERSIONS.parent)
    page = pdfium.PdfDocument(str(tmp_path / "w" / "versions" / "kw-reference.pdf"))[0]
    assert "Key words" in page.get_textpage().get_text_range()
    roomy = next(f for f in layout["forms_made"] if f["id"] == "roomy")
    if len(roomy["pages"]) > layout["base_pages"]:  # every support printed: longer, and make says by how much
        assert roomy["shortfall"] > 0 and roomy["blocks_by_page"] and len(roomy["free_by_page"]) == len(roomy["pages"])


def test_matching_items_beside_choices_carry_no_numbers_of_their_own(tmp_path):
    import pypdfium2 as pdfium
    path = ROOT / "examples" / "ela4-garden-01.json"
    S.make_worksheet(S.read_json(path), tmp_path / "g", base=path.parent)
    doc = pdfium.PdfDocument(str(tmp_path / "g" / "worksheet.pdf"))
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "exhaust (line 2)" in text and "1. exhaust" not in text and "A. light in color" in text
