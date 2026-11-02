"""ID cards: a class list for the teacher, then a card for each class ID (the plugin's `cards`)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import cards as C  # noqa: E402


def roster(folder: Path, ids: list[str], header: str = "id") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "roster.csv"
    path.write_text(header + "\n" + "\n".join(ids) + "\n", encoding="utf-8")
    return path


def page_texts(pdf: Path) -> list[str]:
    doc = pdfium.PdfDocument(str(pdf))
    return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]


def test_a_class_list_then_ten_cards_a_page(tmp_path):
    ids = [f"3{p:02d}{(3 + p // 10 + p % 10) % 10}" for p in range(1, 24)]
    path = roster(tmp_path / "Period 3 Science", list(reversed(ids)))
    report = C.build([path], tmp_path / "cards.pdf")
    assert report["classes"] == [{"class": "Period 3 Science", "ids": 23}]
    texts = page_texts(tmp_path / "cards.pdf")
    assert len(texts) == report["pages"] == 1 + 3
    assert "Period 3 Science: class numbers" in texts[0]
    assert [i for i in ids if i in texts[0]] == ids  # every ID, on the teacher's list
    assert texts[0].index(ids[0]) < texts[0].index(ids[-1])  # in order, whatever the roster's order
    assert "3014" in texts[1] and "3104" in texts[1] and "3115" in texts[2]
    assert texts[1].count("Period 3 Science") == 10 and texts[3].count("Period 3 Science") == 3
    assert "never your name" in texts[1]


def test_two_digit_ids_stay_two_digits(tmp_path):
    path = roster(tmp_path / "Room 12", ["1", "02", "3"], header="ID")
    assert C.read_ids(path) == ["01", "02", "03"]
    C.build([path], tmp_path / "cards.pdf")
    assert "0001" not in page_texts(tmp_path / "cards.pdf")[1]


def test_several_classes_are_named_by_their_folders(tmp_path):
    a = roster(tmp_path / "Period 1", ["1012", "1023"])
    b = roster(tmp_path / "Period 2", ["2013"])
    report = C.build([a, b], tmp_path / "cards.pdf")
    assert [k["class"] for k in report["classes"]] == ["Period 1", "Period 2"]
    assert report["pages"] == 4
    with pytest.raises(ValueError, match="names one class"):
        C.build([a, b], tmp_path / "x.pdf", class_name="Science")


def test_a_roster_without_numbers_is_refused(tmp_path):
    path = roster(tmp_path / "Period 4", ["first", "second"], header="name")
    with pytest.raises(ValueError, match="no ID numbers"):
        C.build([path], tmp_path / "cards.pdf")


def test_the_command_line(tmp_path):
    path = roster(tmp_path / "Period 5", ["5017", "5028"])
    out = subprocess.run([sys.executable, str(SCRIPTS / "paper_loop.py"), "cards", str(path), "--out",
                          str(tmp_path / "cards.pdf"), "--class-name", "Science 5"],
                         capture_output=True, text=True, check=True).stdout
    assert "Science 5: a class list, then 2 cards" in out
    assert (tmp_path / "cards.pdf").exists()
