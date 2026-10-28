"""Regressions from the marking reviews and a teacher trial: work orders, checks, layout, and the marked page."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import diagrams as D  # noqa: E402
from paper_loop_core import fonts as F  # noqa: E402
from paper_loop_core import forms as FM  # noqa: E402
from paper_loop_core import prepare as P  # noqa: E402
from paper_loop_core import render as R  # noqa: E402
from paper_loop_core import results as X  # noqa: E402
from paper_loop_core import scan as L  # noqa: E402
from paper_loop_core import script as SC  # noqa: E402
from paper_loop_core import sheet as S  # noqa: E402

EXAMPLES = ROOT / "examples"
VERSIONS = EXAMPLES / "math6-ratios-02.json"
PL = [sys.executable, str(SCRIPTS / "paper_loop.py")]


def _pdf_text(path: Path) -> str:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(path))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def _chars(path: Path, page: int, text: str) -> list[tuple[float, float, float, float]]:
    """The boxes of the first run of text on a page of a PDF, in points."""
    import pypdfium2 as pdfium
    tp = pdfium.PdfDocument(str(path))[page].get_textpage()
    found = tp.get_text_range()
    start = found.find(text)
    assert start >= 0, f"{text!r} isn't on page {page + 1}"
    return [tp.get_charbox(k) for k in range(start, start + len(text)) if found[k].strip()]


def _class(tmp: Path, defn: dict, students: dict[str, str], pages: dict[str, list[int]] | None = None,
           comment: str = "Right.") -> tuple[Path, list[dict]]:
    """A made worksheet and a marked class without a scan: each student's pages are the blank form, every answer
    right with the same comment. students maps an ID to its form; pages, an ID to the form pages handed in.
    Returns (work folder, check's pages)."""
    S.make_worksheet(defn, tmp / "ws", base=EXAMPLES)
    layout, key = S.read_json(tmp / "ws" / "layout.json"), S.read_json(tmp / "ws" / "key.json")
    work = tmp / "work"
    (work / "pages").mkdir(parents=True)
    manifest_pages, results, n = [], [], 0
    for sid, form in students.items():
        items = S.form_items(key, form)
        for page in S.form_pages(layout, form):
            if pages and page["form_page"] not in pages.get(sid, [page["form_page"]]):
                continue
            n += 1
            image = f"pages/scan-{n:03}.png"
            L.save_png(L.template(tmp / "ws", page["page"]), work / image)
            manifest_pages.append({"scan_index": n, "status": "ok", "reason": None, "student_id": sid,
                                   "page": page["page"], "form": form, "image": image, "raw_image": None,
                                   "answers": {}})
            results.append({"scan_index": n, "student_id": sid, "page": page["page"], "form": form, "boxes": [
                {"q": b["q"], "type": b["type"], "verdict": "correct", "comment": comment, "details": [],
                 "points_awarded": items[b["q"]]["points"], "points_possible": items[b["q"]]["points"]}
                for b in page["boxes"]]})
    S.write_json(work / "manifest.json", {"assignment_dir": str(tmp / "ws"), "assignment_id": layout["assignment_id"],
                                          "title": layout["title"], "pages": manifest_pages})
    return work, results


def _todo_class(tmp: Path, defn: dict, answers: dict[str, dict[int, str]], forms: dict[str, str] | None = None
                ) -> Path:
    """A made worksheet and a prepared, routed class whose answers all need marking: answers maps an ID to
    {question: "mark" or "blank"}. Returns the work folder (crops aren't real images)."""
    S.make_worksheet(defn, tmp / "ws", base=EXAMPLES)
    layout = S.read_json(tmp / "ws" / "layout.json")
    work, pages, n = tmp / "work", [], 0
    for sid, qs in answers.items():
        for page in S.form_pages(layout, (forms or {}).get(sid, "")):
            n += 1
            pages.append({"scan_index": n, "status": "ok", "reason": None, "student_id": sid, "page": page["page"],
                          "form": page["form"], "image": None, "raw_image": None, "answers": {
                              str(b["q"]): {"crop": f"crops/scan-{n:03}-q{b['q']}.png", "status": qs.get(b["q"], "blank"),
                                            "read": None, "ink": []} for b in page["boxes"]}})
    (work / "marks").mkdir(parents=True)
    S.write_json(work / "manifest.json", {"assignment_dir": str(tmp / "ws"), "assignment_id": layout["assignment_id"],
                                          "title": layout["title"], "subject": "", "grade_band": "grade 6", "grade": 6,
                                          "pages": pages})
    return work


SHORT3 = {"assignment_id": "ds-01", "title": "Ratios Check", "grade": 6, "compact": True,
          "questions": [{"type": "short", "q": n, "prompt": p, "key": "A comparison.", "lines": 2}
                        for n, p in ((1, "What is a ratio?"), (2, "Give an example."), (3, "Why?"))]}


def test_every_student_starts_a_new_sheet_when_any_copy_runs_two_pages(tmp_path):
    defn = {**SHORT3, "versions": [{"id": "lp", "name": "Large print", "large_print": True, "per_page": 2}]}
    work, pages = _class(tmp_path, defn, {"0101": "", "0102": "", "0104": "lp"})
    out = R.render(work, pages, {sid: {"strength": "Clear.", "fixes": []} for sid in ("0101", "0102", "0104")})
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(out["returned"]))
    filled = [doc[i].get_textpage().count_chars() > 0 for i in range(len(doc))]
    assert out["double_sided"] and filled == [True, False, True, False, True, True]  # a blank back after 0101, 0102
    single = R.render(work, [p for p in pages if p["student_id"] != "0104"], {})  # nobody here had the long copy
    assert not single["double_sided"] and single["sheets"] == 2


def test_an_answer_written_in_the_comment_column_is_seen_not_settled_blank(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    defn = {"assignment_id": "gutter-01", "title": "Gutter", "grade": 6,
            "questions": [{"type": "math", "q": 1, "prompt": "6 smoothies cost $15. What does 1 cost?",
                           "answer": "2.50", "key": "15 / 6.", "work_height": 70}]}
    S.make_worksheet(defn, tmp_path / "ws")
    page = S.read_json(tmp_path / "ws" / "layout.json")["pages"][0]
    img = Image.fromarray(L.template(tmp_path / "ws", 1).copy())
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(44)
    except TypeError:  # Pillow before 10.1
        pytest.skip("this Pillow can't size its default font")
    for digit, rect in zip("6123", page["id_boxes"]):
        draw.text(S.pt_to_px(rect[0] + 7, rect[3] - 4), digit, fill=30, font=font)
    box = page["boxes"][0]
    draw.text(S.pt_to_px(S.GUTTER_LEFT + 10, box["rect"][3] - 10), "15 / 6 = 2.50", fill=30, font=font)
    img.save(tmp_path / "scan.pdf", resolution=S.DPI)
    manifest = P.prepare([tmp_path / "scan.pdf"], tmp_path / "ws", tmp_path / "work")
    answer = manifest["pages"][0]["answers"]["1"]
    assert answer["status"] == "mark" and answer.get("outside_crop")  # not "No answer yet." over the writing


def test_stretch_questions_on_practice_sheets_get_work_orders_and_grade_columns(tmp_path):
    base = S.read_json(VERSIONS)
    base.pop("versions")
    q11 = {"type": "short", "q": 11, "prompt": "Why does doubling both parts keep a ratio?", "key": "Same factor.",
           "stretch": True}
    practice = {**base, "assignment_id": "ratios-practice", "personal": [{"student_id": "0901", "questions": [q11]}]}
    work = _todo_class(tmp_path, practice, {"0901": {11: "mark"}}, {"0901": "p0901"})
    key = S.read_json(tmp_path / "ws" / "key.json")
    assert S.form_items(key, "p0901")[11]["stretch"] is True  # progress tells stretch questions apart
    assert [p.name for p in P.todo(work)] == ["q11.md"]
    S.write_json(work / "marks" / "q11.json", {"q": 11, "marks": {"1": {
        "transcription": "x", "verdict": "correct", "comment": "Right.", "confidence": 1}}})
    result = X.check(work)
    assert not result["errors"] and "Q11 (short)" in X.summary_todo(work, result["pages"]).read_text()
    manifest = S.read_json(work / "manifest.json")
    for p in manifest["pages"]:
        L.save_png(L.template(tmp_path / "ws", p["page"]), work / f"scan-{p['scan_index']}.png")
        p["image"] = f"scan-{p['scan_index']}.png"
    S.write_json(work / "manifest.json", manifest)
    out = R.render(work, result["pages"], {"0901": {"strength": "Clear.", "fixes": []}}, "csv")
    assert out["grades"].read_text().splitlines() == ["student_id,q11,total,possible", "0901,2,2,2"]


def test_a_stretch_question_is_on_the_answer_key_and_checked_when_the_worksheet_is_made(tmp_path):
    defn = S.read_json(VERSIONS)
    defn["versions"] = []
    defn["stretch"] = [{"type": "math", "q": 11, "prompt": "{{n}} cups for {{n}} people: how many for one?",
                        "vars": {"n": {"choose": [3, 4], "base": 4}}, "answer": "1", "key": "Divides."}]
    run = subprocess.run(PL + ["make", str(_write(tmp_path / "s.json", defn)), "--out", str(tmp_path / "s")],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout
    stretch = S.read_json(tmp_path / "s" / "key.json")["stretch"]
    assert stretch[0]["prompt"].startswith("4 cups for 4 people") and stretch[0]["stretch"] is True
    assert "Stretch questions" in _pdf_text(tmp_path / "s" / "answer-key.pdf")
    defn["stretch"] = [{"type": "short", "q": 1, "prompt": "Again?", "key": "k"}]
    with pytest.raises(S.WorksheetError, match="its own \"q\" number"):
        S.make_worksheet(defn, tmp_path / "t", base=EXAMPLES)


def _write(path: Path, data: dict) -> Path:
    S.write_json(path, data)
    return path


DRAW_ANSWER = {"assignment_id": "drawans-01", "title": "Fraction Strips", "grade": 5, "questions": [
    {"type": "draw", "q": 1, "prompt": "Shade 1/3 and 1/4 of the strip, then write the sum.",
     "diagram": {"width": 300, "height": 60, "description": "A strip in 12 parts.", "shapes": [
         {"shape": "fraction", "kind": "bar", "x": 10, "y": 15, "w": 280, "h": 30, "parts": 12}]},
     "checklist": [{"item": "4 parts shaded for 1/3.", "short": "1/3"}, {"item": "3 more parts shaded.", "short": "1/4"}],
     "answer": "7/12"}]}


def test_an_empty_drawing_with_a_written_answer_is_marked_not_a_crash(tmp_path):
    work = _todo_class(tmp_path, DRAW_ANSWER, {"5101": {1: "mark"}})
    mark = {"verdict": "blank", "confidence": 1, "answer": "7/12", "answer_verdict": "correct"}
    S.write_json(work / "marks" / "q1.json", {"q": 1, "marks": {"1": mark}})
    assert X.check(work)["errors"] == ["marks/q1.json, scan 1: missing \"comment\""]
    mark["comment"] = "7/12 is right. Shade the strip to show it."
    S.write_json(work / "marks" / "q1.json", {"q": 1, "marks": {"1": mark}})
    result = X.check(work)
    box = result["pages"][0]["boxes"][0]
    assert not result["errors"] and (box["verdict"], box["points_awarded"]) == ("partial", 1.0)
    assert [d.get("met") for d in box["details"][:2]] == ["no", "no"]  # nothing drawn meets no item


def test_check_says_what_to_fix_when_a_box_number_or_confidence_isnt_a_number(tmp_path):
    defn = {"assignment_id": "boxes-01", "title": "Blanks", "grade": 6, "questions": [
        {"type": "blanks", "q": 1, "text": "2 + 2 = {1}, 3 + 3 = {2}", "answers": [{"n": 1, "answer": "4"},
                                                                                 {"n": 2, "answer": "6"}]}]}
    work = _todo_class(tmp_path, defn, {"0101": {1: "mark"}})
    labels = [{"n": "one", "transcription": "4", "verdict": "correct", "confidence": 1},
              {"n": 2, "transcription": "6", "verdict": "correct", "confidence": "high"}]
    S.write_json(work / "marks" / "q1.json", {"q": 1, "marks": {"1": {"labels": labels, "comment": "Right.",
                                                                       "confidence": 1}}})
    errors = X.check(work)["errors"]
    assert any("labels[0] \"n\" is the box's number" in e for e in errors)
    assert any("box 2 \"confidence\" must be a number between 0 and 1" in e for e in errors)
    S.write_json(work / "marks" / "q1.json", {"q": "first", "marks": []})
    assert any("should be {\"q\": <question number>" in e for e in X.check(work)["errors"])


def test_a_question_about_two_sources_makes_with_versions(tmp_path):
    defn = {"assignment_id": "two-src-01", "title": "Two Sources", "grade": 8, "questions": [
        {"type": "passage", "id": "still", "title": "Source A", "text": "The first source says one thing."},
        {"type": "passage", "id": "douglass", "title": "Source B", "text": "The second source says another."},
        {"type": "short", "q": 1, "passage": ["still", "douglass"], "prompt": "Compare them.", "key": "A difference."},
        {"type": "short", "q": 2, "prompt": "Anything else?", "key": "k"}],
            "versions": [{"id": "lp", "name": "Large print", "large_print": True},
                         {"id": "one", "name": "Shorter", "only": [1]}]}
    S.make_worksheet(defn, tmp_path / "w")
    text = _pdf_text(tmp_path / "w" / "versions" / "one.pdf")
    assert "Source A" in text and "Source B" in text  # a shortened version keeps both of its question's sources


def test_a_work_optional_version_tells_the_marker_the_work_is_optional(tmp_path):
    defn = {"assignment_id": "wo-test-01", "title": "Unit Price", "grade": 6, "compact": True, "questions": [
        {"type": "math", "q": 1, "prompt": "6 smoothies cost $15. How much is 1?", "answer": "$2.50", "key": "15 / 6."}],
            "versions": [{"id": "calc", "name": "Calculator", "work_optional": True}]}
    work = _todo_class(tmp_path, defn, {"1111": {1: "mark"}, "2222": {1: "mark"}}, {"2222": "calc"})
    order = P.todo(work)[0].read_text()
    base, calc = order.split("### Version B (Calculator)")
    assert "1 for the answer, 1 for the work" in base and "scan 1" in base and "scan 2" not in base
    assert "2 for the answer, 0 for the work" in calc and "The work is optional here" in calc and "scan 2" in calc


def test_a_matching_work_order_shows_items_as_printed_without_numbers(tmp_path):
    work = _todo_class(tmp_path, S.read_json(EXAMPLES / "ela4-garden-01.json"), {"4101": {4: "mark"}})
    order = (work / "todo" / "q4.md").read_text() if P.todo(work) else ""
    assert '(printed as "exhaust (line 2)")' in order and "1. exhaust" not in order


def test_make_reports_a_shortened_version(tmp_path, capsys):
    defn = S.read_json(VERSIONS)
    defn["versions"] = [{"id": "short", "name": "Shorter", "only": [1, 2]}]
    run = subprocess.run(PL + ["make", str(_write(tmp_path / "w.json", defn)), "--out", str(tmp_path / "w")],
                         capture_output=True, text=True, cwd=EXAMPLES)
    assert "only Q1, Q2" in next(line for line in run.stdout.splitlines() if "Version B" in line), run.stdout


def _layout(defn: dict, scale: float = 1.0) -> S.Layout:
    d = S.normalize({**defn, "print": {"scale": scale}})
    return S.Layout(d, F.choose(S.all_texts(d))[0], EXAMPLES)


def test_large_print_choices_and_table_headers_stay_in_their_columns():
    from reportlab.pdfbase.pdfmetrics import stringWidth
    choice = {"assignment_id": "c", "title": "T", "grade": 5, "questions": [
        {"type": "choice", "q": 1, "prompt": "Which?", "answer": "B", "columns": 4, "options": [
            {"letter": k, "text": w}
            for k, w in zip("ABCD", ("evaporation", "condensation", "precipitation", "collection"))]}]}
    for scale, columns in ((1.0, 4), (18 / 11, 2)):
        lay = _layout(choice, scale)
        got, col_w, indent, lines = lay.option_geometry(lay.defn["questions"][0])
        widest = max(stringWidth(line, lay.f.regular, lay.st["option_size"]) for o in lines for line in o)
        assert got == columns and widest <= col_w - indent + 6  # short of the next column's letter
    table = {"assignment_id": "t", "title": "T", "grade": 6, "questions": [
        {"type": "table", "q": 1, "prompt": "Fill in.",
         "columns": ["Minute", "Temperature (°C)", "Observation", "Change"],
         "rows": [["0", "20", "still", {"answer": "none"}], ["5", {"answer": "60"}, "bubbles", "up"]]}]}
    for scale in (1.0, 18 / 11, 2.2):
        lay = _layout(table, scale)
        widths, header, _, _, _, size = lay.table_geometry(lay.defn["questions"][0])
        assert abs(sum(widths) - (S.BOX_RIGHT - S.LEFT)) < 0.5
        for w, lines in zip(widths, header):
            assert all(stringWidth(line, lay.f.bold, size) <= w - 4 for line in lines)


def test_large_print_directions_wrap_short_of_the_id_boxes():
    from reportlab.pdfbase.pdfmetrics import stringWidth
    defn = S.read_json(VERSIONS)
    for scale in (1.0, 18 / 10.5, 2.0):
        lay = _layout(defn, scale)
        boxes = S.id_boxes(lay.defn["id_digits"], lay.defn["style"], lay.k)
        assert all(S.HEADER_X + stringWidth(line, lay.f.regular, lay.header_size) < boxes[0][0] - 6
                   for line in lay.header_lines)
    assert _layout(defn).header_lines == _layout(defn, 1.0).header_lines  # the regular sheet wraps as before


def test_a_long_answer_label_and_units_stay_on_the_page(tmp_path):
    defn = {"assignment_id": "label-test-01", "title": "Trip Costs", "grade": 7, "questions": [
        {"type": "math", "q": 1, "prompt": "The bus costs $240 for 30 students. What does each pay?", "answer": "8",
         "units": "dollars for each student", "answer_label": "Cost for one student:", "key": "240 / 30 = 8."}],
            "versions": [{"id": "lp", "name": "Large print", "large_print": True}]}
    S.make_worksheet(defn, tmp_path / "w")
    layout = S.read_json(tmp_path / "w" / "layout.json")
    for pdf, form in (("worksheet.pdf", ""), ("versions/lp.pdf", "lp")):
        page = S.form_pages(layout, form)[0]
        answer = page["boxes"][0]["answer_rect"]
        label = _chars(tmp_path / "w" / pdf, 0, "Cost for one")
        units = _chars(tmp_path / "w" / pdf, 0, "dollars for")
        assert min(b[0] for b in label) >= S.LEFT - 1 and max(b[2] for b in label) < answer[0]
        assert max(b[2] for b in units) <= S.BOX_RIGHT + 6 and answer[2] - answer[0] >= 60
    lp = _chars(tmp_path / "w" / "versions" / "lp.pdf", 0, "Cost")
    assert lp[0][3] - lp[0][1] > 10  # still large: on two lines rather than shrunk to regular print


def test_a_bengali_version_takes_comments_in_english_and_a_bengali_comment_language_is_refused(tmp_path):
    S.make_worksheet(S.read_json(VERSIONS), tmp_path / "w", base=EXAMPLES)
    key = S.read_json(tmp_path / "w" / "key.json")
    assert key["forms"]["bn"]["comment_language"] == "English"  # the translation asked for Bengali: it can't print
    defn = S.read_json(VERSIONS)
    defn["versions"] = [{"id": "bn", "name": "Bengali", "language": "bn", "language_mode": "companion",
                         "comment_language": "English, then Bengali"}]
    with pytest.raises(S.WorksheetError, match="comments in Bengali can't print"):
        S.make_worksheet(defn, tmp_path / "x", base=EXAMPLES)
    assert SC.complex_scripts("যোগ করলে অনুপাত বদলে যায়।") == ["Bengali"]  # a danda isn't Devanagari here


def _summary_patch_gray(path: Path, page: int, rect) -> int:
    """Mid-gray pixels (the printed "Feedback summary" placeholder) left in the top of a summary box."""
    import numpy as np
    import pypdfium2 as pdfium
    img = np.asarray(pdfium.PdfDocument(str(path))[page].render(scale=2).to_pil().convert("RGB")).astype(int)
    x0, _, _, y1 = rect
    region = img[int((792 - y1 + 2) * 2):int((792 - y1 + 22) * 2), int((x0 + 4) * 2):int((x0 + 120) * 2)]
    gray = (abs(region[..., 0] - region[..., 2]) < 12) & (region[..., 0] > 110) & (region[..., 0] < 200)
    return int(gray.sum())


def test_large_print_covers_the_summary_placeholder_and_prints_the_summary_large(tmp_path):
    defn = {**SHORT3, "versions": [{"id": "lp", "name": "Large print", "large_print": True}]}
    work, pages = _class(tmp_path, defn, {"0101": "", "0104": "lp"})
    summary = {"strength": "Clear table.", "fixes": ["Check units."]}
    out = R.render(work, pages, {"0101": summary, "0104": summary})
    rects = {p["form"]: p["summary_rect"] for p in S.read_json(tmp_path / "ws" / "layout.json")["pages"]}
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(out["returned"]))
    lp = next(i for i in range(1, len(doc)) if doc[i].get_textpage().count_chars())  # 0104's page, after 0101's
    assert _summary_patch_gray(out["returned"], lp, rects["lp"]) < 30
    size = lambda i: max(b[3] - b[1] for b in _chars(out["returned"], i, "Strength"))  # noqa: E731
    assert size(lp) > size(0) * 1.2


def test_a_long_practice_footer_stays_between_the_corner_squares(tmp_path):
    base = S.read_json(VERSIONS)
    q5 = next(q for q in base["questions"] if q.get("q") == 5)
    practice = {**{k: v for k, v in base.items() if k not in ("versions",)},
                "assignment_id": "math6-ratios-02-practice-2026-10-28-0dcc",
                "personal": [{"student_id": "0103", "questions": [q5], "print": {"scale": 18 / 10.5}}]}
    S.make_worksheet(practice, tmp_path / "p", base=EXAMPLES)
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(tmp_path / "p" / "copies.pdf"))
    for i in range(len(doc)):
        tp = doc[i].get_textpage()
        boxes = [tp.get_charbox(k) for k in range(tp.count_chars())]
        footer = [b for b in boxes if b[3] < 60]
        assert footer and min(b[0] for b in footer) > 54 and max(b[2] for b in footer) < 558


def test_an_essay_counts_toward_per_page():
    defn = {"assignment_id": "x", "title": "T", "grade": 9, "questions": [
        {"type": "short", "q": n, "prompt": "Why?", "key": "k", "lines": 40 if n == 3 else 2} for n in (1, 2, 3, 4)]}
    lay = S.Layout(S.normalize({**defn, "print": {"per_page": 2}}), F.choose(["x"])[0], EXAMPLES)
    first = [lay.defn["questions"][i]["q"] for i, _ in lay.paginate()[0]]
    assert first == [1, 2]  # the essay starts the next page


def test_a_comment_in_english_then_arabic_keeps_its_english_line_flush_left(tmp_path):
    comment = "Multiply both parts by the same number to keep the ratio. اضرب الجزأين في العدد نفسه."
    work, pages = _class(tmp_path, SHORT3, {"0101": ""}, comment=comment)
    out = R.render(work, pages, {"0101": {"strength": "Clear.", "fixes": []}})
    english = _chars(out["returned"], 0, "Multiply")
    assert abs(english[0][0] - (S.GUTTER_LEFT + 22)) < 1.5  # after the check mark, not set flush right
    assert R._directions(["Multiply both by 3.", "اضرب الجزأين"], True) == [False, True]
    assert R._directions(["اضرب في 3", "CO2 ينتج"], True) == [True, True]  # Arabic first: right to left throughout


def test_an_essay_whose_first_page_is_missing_gets_its_comment_above_the_writing(tmp_path):
    defn = {"assignment_id": "essay-01", "title": "Essay", "grade": 10, "questions": [
        {"type": "short", "q": 1, "prompt": "Argue a side.", "key": "A claim with evidence.", "lines": 40}]}
    comment = "A clear claim with a strong first reason. Add a quote from the memo to support your second reason."
    work, pages = _class(tmp_path, defn, {"0101": ""}, pages={"0101": [2]}, comment=comment)
    out = R.render(work, pages, {"0101": {"strength": "Clear.", "fixes": []}})
    layout = S.read_json(tmp_path / "ws" / "layout.json")
    box = next(b for b in layout["pages"][1]["boxes"] if b.get("part") == 2)
    text = _pdf_text(out["returned"]).replace("\r\n", " ")
    assert "second reason" in text or "…" in text  # the whole comment, or as much as fits
    ends = _chars(out["returned"], 0, "A clear claim") + _chars(out["returned"], 0, "the memo")
    assert min(b[1] for b in ends) >= box["rect"][3] - 1  # above the box's top edge, not over the lines


def test_previewing_copies_keeps_the_copies_key_previews(tmp_path):
    from reportlab.pdfgen import canvas
    for name in ("copies.pdf", "copies-key.pdf"):
        c = canvas.Canvas(str(tmp_path / name))
        c.drawString(72, 720, name)
        c.showPage()
        c.save()
    for name in ("copies-key.pdf", "copies.pdf"):
        subprocess.run(PL + ["preview", str(tmp_path / name)], capture_output=True, text=True, check=True)
    assert sorted(p.name for p in (tmp_path / "preview").glob("*.png")) == ["copies-key-p1.png", "copies-p1.png"]


def test_todo_before_ids_says_to_read_the_ids_first(tmp_path):
    work = _todo_class(tmp_path, SHORT3, {"0101": {1: "mark"}})
    manifest = S.read_json(work / "manifest.json")
    manifest["pages"][0].update(student_id=None, reason="ID not read yet")
    S.write_json(work / "manifest.json", manifest)
    run = subprocess.run(PL + ["todo", str(work)], capture_output=True, text=True)
    assert run.returncode == 1 and "haven't been read yet" in run.stdout and "run `ids`" in run.stdout


ERIE_MAP = {"type": "label", "q": 3, "prompt": "Map It: Write the name of each place in its box.",
            "word_bank": ["Lake Erie", "Erie Canal", "Hudson River"],
            "diagram": {"width": 330, "height": 78, "description": "A simple map of New York State.", "shapes": [
                {"shape": "polygon", "points": [[5, 20], [40, 38], [70, 49], [78, 40], [45, 24], [10, 11]], "fill": 0.85},
                {"shape": "polygon", "points": [[98, 72], [162, 78], [165, 63], [102, 57]], "fill": 0.85},
                {"shape": "text", "x": 114, "y": 64, "text": "Lake Ontario", "size": 6.5},
                {"shape": "polyline", "points": [[73, 44], [105, 50], [135, 47], [165, 50], [190, 44]], "width": 2.5},
                {"shape": "text", "x": 78, "y": 30, "text": "Buffalo", "size": 7},
                {"shape": "polyline", "points": [[194, 78], [190, 44], [196, 20], [200, 6]], "width": 1.5},
                {"shape": "text", "x": 196, "y": 38, "text": "Albany", "size": 7},
                {"shape": "text", "x": 206, "y": 3, "text": "New York City", "size": 7}]},
            "labels": [{"n": 1, "box": [2, 52, 86, 24], "points_to": [30, 24], "answer": "Lake Erie"},
                       {"n": 2, "box": [106, 8, 86, 24], "points_to": [135, 47], "answer": "Erie Canal"},
                       {"n": 3, "box": [222, 52, 106, 24], "points_to": [193, 64], "answer": "Hudson River"}]}


def test_large_print_grows_a_full_width_maps_boxes_and_words_where_there_is_room(tmp_path):
    defn = {"assignment_id": "erie-01", "title": "Erie Canal", "grade": 5, "compact": True, "questions": [ERIE_MAP],
            "versions": [{"id": "lp", "name": "Large print", "large_print": True}]}
    layout = S.make_worksheet(defn, tmp_path / "w")
    rects = {p["form"]: [s["rect"] for s in p["boxes"][0]["labels"]] for p in layout["pages"]}
    height = lambda r: r[3] - r[1]  # noqa: E731
    assert sum(map(height, rects["lp"])) > sum(map(height, rects[""])) * 1.15  # bigger boxes to write in
    for k, a in enumerate(rects["lp"]):  # still apart from each other
        assert all(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1] for b in rects["lp"][k + 1:])
    lp = next(f for f in layout["forms_made"] if f["id"] == "lp")
    assert "draw it at most" in lp["print_notes"][0]
    lay = S.Layout(S.normalize({**defn, "print": {"scale": 18 / 10.5}}), F.choose(["x"])[0], tmp_path)
    q = lay.defn["questions"][0]
    diagram, boxes = lay.grown(q)
    ink = D.outlines(q["diagram"], lambda t, b, s: lay._width(t, lay.f.regular, s))
    for (x, y, w, h), spot in zip(boxes, q["labels"]):  # no printed line or word under a grown box that wasn't
        bx, by, bw, bh = spot["box"]
        before = {n for n, piece in enumerate(ink) if D.touches((bx, by, bx + bw, by + bh), piece)}
        assert {n for n, piece in enumerate(ink) if D.touches((x, y, x + w, y + h), piece)} <= before
    assert any(s["shape"] == "text" and s["size"] > 8 for s in diagram["shapes"])  # some place names grew


SPANISH = {"language": "es", "title": "El canal", "instructions": "Contesta cada pregunta.",
           "passages": {"canal": "Antes de 1825, llevar mercancías era lento."},
           "passage_titles": {"canal": "Un camino de agua"},
           "questions": {"1": {"prompt": "¿Por qué costaba tanto?", "options": {"A": "Carretas.", "B": "Granjas."},
                               "why": {"A": "Sí: los caminos eran malos.", "B": "Vuelve a leer la línea 1."}},
                         "2": {"prompt": "Completa la tabla.", "words": {"Before the canal": "Antes del canal"}}},
           "no_answer": "Todavía no hay respuesta.", "no_answer_circled": "No encerraste ninguna letra.",
           "comment_language": "English, then Spanish"}
ERIE = {"assignment_id": "erie-02", "title": "Erie Canal", "grade": 5, "compact": True, "questions": [
    {"type": "passage", "id": "canal", "title": "A Water Road", "text": "Before 1825, moving goods was slow.",
     "cite": {"title": "Erie Canal", "author": "Simple English Wikipedia contributors",
              "url": "https://simple.wikipedia.org/w/index.php?title=Erie_Canal&oldid=1", "license": "CC BY-SA 4.0",
              "changes": "shortened"}},
    {"type": "choice", "q": 1, "passage": "canal", "prompt": "Why was shipping costly?", "answer": "A", "options": [
        {"letter": "A", "text": "Wagons.", "why": "Yes: rough roads."},
        {"letter": "B", "text": "Farms.", "why": "Reread line 1."}]},
    {"type": "table", "q": 2, "prompt": "Fill in the table.", "columns": ["", "Before the canal"],
     "rows": [["Flour", {"answer": "$3"}]]}],
    "versions": [{"id": "es", "name": "Spanish", "language": "es"}], "translations": {"es": SPANISH}}


def test_two_language_comments_cover_the_scripts_own_comments_and_their_word_limit(tmp_path):
    S.make_worksheet(json.loads(json.dumps(ERIE)), tmp_path / "w")
    key = S.read_json(tmp_path / "w" / "key.json")
    es = key["forms"]["es"]
    why = {o["letter"]: o["why"] for o in S.form_items(key, "es")[1]["options"]}
    assert why["A"] == "Yes: rough roads. Sí: los caminos eran malos."
    assert es["blank_comments"] == {"answer": "No answer yet. Todavía no hay respuesta.",
                                    "circled": "No answer circled. No encerraste ninguna letra."}
    box = {"q": 1, "type": "choice", "points": 1}
    assert X._blank(box, "c.png", es["blank_comments"])["comment"].endswith("ninguna letra.")
    assert (X._comment_limit(key, "es"), X._comment_limit(key, "")) == (2 * key["comment_words"], key["comment_words"])
    text = _pdf_text(tmp_path / "w" / "versions" / "es.pdf")
    assert "Before the canal = Antes del canal" in text  # words outside the prompt have a place to go
    page = zipfile.ZipFile(tmp_path / "w" / "versions" / "es.docx").read("word/document.xml").decode()
    assert "Un camino de agua" in page and "CC BY-SA" in page and "Translated into Spanish" in page
    missing = json.loads(json.dumps(ERIE))
    del missing["translations"]["es"]["no_answer"]
    form = next(f for f, _ in FM.expand(missing, tmp_path) if f["id"] == "es")
    assert form["untranslated_comments"] == ['"no_answer"']


def test_a_bilingual_version_isnt_asked_to_cut_to_the_base_length(tmp_path, capsys):
    import paper_loop
    version = {"id": "es", "kind": "version", "label": "C", "name": "Spanish", "pdf": "versions/es.pdf",
               "pages": [3, 4], "language": "es", "language_name": "Español", "language_mode": "bilingual",
               "shortfall": 474.0, "free_by_page": [93, 6], "blocks_by_page": [], "comment_language": "English"}
    layout = {"forms_made": [{"id": ""}, version], "base_pages": 1, "version_notes": []}
    paper_loop._forms_report(layout, tmp_path)
    out = capsys.readouterr().out
    assert "cut about" not in out and "its translations take the room" in out
    paper_loop._forms_report({**layout, "forms_made": [{"id": ""}, {**version, "language_mode": "glossary"}]}, tmp_path)
    assert "Check: version C runs to 2 pages" in capsys.readouterr().out  # a glossary box alone shouldn't need a page


def test_practice_sheets_get_every_students_answers_and_a_versions_extras(tmp_path):
    base = S.read_json(VERSIONS)
    base["stretch"] = [{"type": "short", "q": 11, "prompt": "Why does doubling keep a ratio?", "key": "Same factor.",
                        "support": {"hint": "Think of a table."}}]
    forms = {f["id"]: f for f, _ in FM.expand(base, EXAMPLES)}
    assert [a["kind"] for a in forms["support"]["stretch"][0]["asides"]] == ["hint"]  # with the version's help
    assert "vars" not in forms["es"]["stretch"][0] and forms["es"]["stretch"][0]["q"] == 11
    q5 = next(q for q in base["questions"] if q.get("q") == 5)
    practice = {**{k: v for k, v in base.items() if k not in ("versions", "stretch")},
                "assignment_id": "ratios-practice-01",
                "personal": [{"student_id": "0106", "questions": [dict(q5)], "language": "bn", "language_mode": "companion",
                              "translation": forms["bn"]["translation"], "version_name": "Bengali"},
                             {"student_id": "0102", "questions": [dict(q5), {**forms["support"]["stretch"][0],
                                                                              "stretch": True}],
                              "reference": forms["support"]["reference"],
                              "glossary_terms": forms["support"]["glossary_terms"]}]}
    S.make_worksheet(practice, tmp_path / "p", base=EXAMPLES)
    made = sorted(p.name for p in (tmp_path / "p" / "versions").iterdir())
    assert made == ["p0102-reference.pdf", "p0106.docx"]
    key = _pdf_text(tmp_path / "p" / "copies-key.pdf")
    assert "every student's answers" in key and "ID 0102" in key and "Q11 (stretch)" in key
    assert "Your Bengali page goes with this sheet" in _pdf_text(tmp_path / "p" / "copies.pdf")


def test_a_no_derivatives_passage_isn_t_translated(tmp_path):
    import pytest
    source = S.read_json(ROOT / "examples" / "ela4-garden-01.json")
    story = next(q for q in source["questions"] if q.get("type") == "passage")
    story["cite"] = {"title": "A story", "author": "A. Writer", "url": "https://example.org/story",
                     "license": "CC BY-ND 4.0"}
    source["versions"] = [{"id": "es", "language": "es"}]
    S.write_json(tmp_path / "ela4-garden-01.json", source)
    S.write_json(tmp_path / "ela4-garden-01.es.json", {"language": "es", "passages": {"story": "Una historia."}})
    with pytest.raises(S.WorksheetError, match="allows no changes"):
        S.make_worksheet(source, tmp_path / "out", base=tmp_path)
