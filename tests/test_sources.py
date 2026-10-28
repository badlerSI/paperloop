"""Readings from free, human-written sources: licenses, credit lines, reading level, and fetching."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin" / "skills" / "paper-loop" / "scripts"))

from paper_loop_core import sheet as S  # noqa: E402
from paper_loop_core import sources as SR  # noqa: E402

ENRICH = ROOT / "examples" / "sci5-photosynthesis-enrich-01.json"


def test_an_adapted_wikipedia_passage_prints_its_credit_and_license(tmp_path):
    layout = S.make_worksheet(S.read_json(ENRICH), tmp_path / "e", base=ENRICH.parent)
    key = S.read_json(tmp_path / "e" / "key.json")
    source = key["passages"][0]["source"]
    assert source.startswith("Adapted from “Photosynthesis,” Simple English Wikipedia contributors, https://")
    assert "oldid=10903963" in source and "CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0)" in source
    assert "Changes: shortened and simplified for grade 5. Shared under the same license." in source
    assert layout["licenses"] == ["cc by-sa 4.0"] and layout["citation_problems"] == []


@pytest.mark.parametrize("cite, message", [
    ({"title": "A", "url": "https://www.commonlit.org/en/texts/x", "license": "CC BY-SA 4.0", "changes": "shortened"},
     "CommonLit's terms forbid"),
    ({"title": "A", "url": "https://openstax.org/books/biology", "license": "CC BY-NC-SA 4.0", "changes": "simplified"},
     "generative AI"),
    ({"title": "A", "license": "CC BY-ND 4.0", "changes": "shortened"}, "allows no changes"),
    ({"title": "A", "license": "All rights reserved"}, "isn't one Paper Loop knows"),
    ({"title": "A"}, "needs \"license\""),
])
def test_sources_that_forbid_adapting_are_refused(cite, message):
    with pytest.raises(S.WorksheetError, match=message):
        SR.check_cite(cite, "passage")


def test_public_domain_and_quoted_texts():
    line, _ = SR.check_cite({"title": "The Gettysburg Address", "author": "Abraham Lincoln", "license": "public domain"}, "p")
    assert line == "From “The Gettysburg Address,” by Abraham Lincoln. Public domain."
    line, _ = SR.check_cite({"title": "Clouds", "url": "https://www.noaa.gov/x", "license": "US government work",
                             "changes": "excerpted"}, "p")
    assert line.startswith("Excerpted from “Clouds,” https://www.noaa.gov/x. A US government work. Changes: excerpted.")
    assert SR.check_cite({"license": "written for this worksheet"}, "p")[0] == "Written for this worksheet."


def test_reading_level_flags_a_passage_far_above_the_grade(tmp_path):
    easy = "The cat sat on the mat. It was a warm day. The dog ran to the cat. They both sat in the sun. " * 3
    hard = ("Photosynthesis constitutes the biochemical mechanism whereby chlorophyll-containing organisms "
            "transform electromagnetic radiation into chemical potential energy, subsequently synthesizing "
            "carbohydrates from atmospheric carbon dioxide. ") * 3
    assert SR.reading_grade(easy) < 3 and SR.reading_grade(hard) > 14
    assert SR.reading_grade("Too short.") is None
    defn = {"assignment_id": "t", "title": "T", "grade": 4, "questions": [
        {"type": "passage", "title": "Light", "text": hard},
        {"type": "short", "q": 1, "prompt": "Why?", "key": "Because."}]}
    layout = S.make_worksheet(defn, tmp_path / "t")
    assert any("Light reads at about grade" in p and "well above grade 4" in p for p in layout["citation_problems"])


def test_wikipedia_text_comes_with_its_revision_and_without_formula_wreckage(monkeypatch):
    extract = ("Plants make food.\n\n== How ==\nIt needs light.\n\n  6\n  C\n\n  O\n  2\n  +\n  6\n"
               "  {\\displaystyle 6CO_{2}}\n\ncarbon dioxide + water → glucose + oxygen")
    reply = {"query": {"pages": [{"title": "Photosynthesis", "extract": extract,
                                  "revisions": [{"revid": 123, "timestamp": "2026-10-01T00:00:00Z"}]}]}}
    seen = []
    monkeypatch.setattr(SR, "_get", lambda url: seen.append(url) or json.dumps(reply).encode())
    got = SR.wikipedia("Photosynthesis", simple=True)
    assert seen[0].startswith("https://simple.wikipedia.org/w/api.php?") and "rvprop=ids" in seen[0]
    assert got["url"] == "https://simple.wikipedia.org/w/index.php?title=Photosynthesis&oldid=123"
    assert got["text"] == "Plants make food.\n\n# How\nIt needs light.\n\n[formula]\n\ncarbon dioxide + water → glucose + oxygen"
    assert got["license"] == "CC BY-SA 4.0" and got["author"] == "Simple English Wikipedia contributors"


def test_gutenberg_text_loses_its_license_header_and_is_never_fetched(monkeypatch, tmp_path):
    raw = ("The Project Gutenberg eBook of Tales\n\nTitle: Tales\nAuthor: A. Writer\n\nRelease date: May 1, 2004 "
           "[eBook #42]\n\n*** START OF THE PROJECT GUTENBERG EBOOK TALES ***\nOnce upon a time.\n"
           "*** END OF THE PROJECT GUTENBERG EBOOK TALES ***\nLicense text...")
    (tmp_path / "pg42.txt").write_text(raw)
    monkeypatch.setattr(SR, "_get", lambda url: pytest.fail("Gutenberg's site is for people, not scripts"))
    got = SR.gutenberg(tmp_path / "pg42.txt")
    assert got["text"] == "Once upon a time." and got["author"] == "A. Writer" and got["license"] == "public domain"
    assert got["url"] == "https://www.gutenberg.org/ebooks/42" and "check" not in got
    run = subprocess.run([sys.executable, str(ROOT / "plugin/skills/paper-loop/scripts/paper_loop.py"), "source", "gutenberg", "42", "--out",
                          str(tmp_path / "x.json")], capture_output=True, text=True)
    assert run.returncode == 1 and "https://www.gutenberg.org/ebooks/42" in run.stdout and "Plain Text" in run.stdout


def test_a_wikisource_page_with_no_scan_behind_it_says_so(monkeypatch):
    page = {"title": "Interview", "extract": "The text of an interview.",
            "revisions": [{"revid": 7, "timestamp": "2026-10-01T00:00:00Z"}],
            "categories": [{"title": "Category:Nonstandard texts"}]}
    monkeypatch.setattr(SR, "_get", lambda url: json.dumps({"query": {"pages": [page]}}).encode())
    got = SR.wikipedia("Interview", site="en.wikisource.org")
    assert "no scanned edition" in got["check"]
    page["categories"] = [{"title": "Category:PD-old"}]
    assert "mostly public domain" in SR.wikipedia("Interview", site="en.wikisource.org")["check"]


def test_a_rate_limited_fetch_tries_once_more(monkeypatch):
    import urllib.error
    calls = []

    def fake(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"ok"
        return Reply()
    monkeypatch.setattr(SR.urllib.request, "urlopen", fake)
    monkeypatch.setattr(SR.time, "sleep", lambda s: None)
    assert SR._get("https://en.wikipedia.org/w/api.php") == b"ok" and len(calls) == 2
    assert "@" not in SR.AGENT  # no one's email goes out with a request


def test_a_rate_limited_fetch_waits_as_long_as_the_site_asks(monkeypatch):
    import urllib.error
    calls, waits = [], []

    def fake(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "10"}, None)
    monkeypatch.setattr(SR.urllib.request, "urlopen", fake)
    monkeypatch.setattr(SR.time, "sleep", waits.append)
    try:
        SR._get("https://en.wikipedia.org/w/api.php")
    except urllib.error.HTTPError as e:
        assert e.code == 429
    assert len(calls) == 3 and waits == [10.0, 10.0]
    assert SR._wait("600", 0) == 30.0 and SR._wait(None, 1) == 10.0
