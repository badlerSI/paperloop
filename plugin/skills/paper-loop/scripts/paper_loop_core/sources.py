"""Readings from free, human-written sources: what a license allows, the credit line it requires, and how
hard the text is to read.

A passage can name its source with "cite" ({"title", "author", "url", "license", "changes"}); the worksheet
then prints the credit line the license asks for. Openly licensed and public-domain texts may be abridged
and adapted. Some free sites forbid rewriting their texts, or using them with AI tools, and an "ND" license
forbids changes: a passage adapted from one of those is refused, with what to use instead.

`fetch` gets an article's plain text from Wikipedia or Simple English Wikipedia (with the revision, so the
credit points at the exact text used) or a book from Project Gutenberg, when the sandbox can reach them.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from .sheet import WorksheetError

# license name (lowercase, as written in "cite") -> (may be adapted, URL, share-alike)
LICENSES = {
    "public domain": (True, "", False), "cc0": (True, "https://creativecommons.org/publicdomain/zero/1.0/", False),
    "us government work": (True, "", False),
    "cc by 4.0": (True, "https://creativecommons.org/licenses/by/4.0/", False),
    "cc by-sa 4.0": (True, "https://creativecommons.org/licenses/by-sa/4.0/", True),
    "cc by 3.0": (True, "https://creativecommons.org/licenses/by/3.0/", False),
    "cc by-sa 3.0": (True, "https://creativecommons.org/licenses/by-sa/3.0/", True),
    "cc by-nc 4.0": (True, "https://creativecommons.org/licenses/by-nc/4.0/", False),
    "cc by-nc-sa 4.0": (True, "https://creativecommons.org/licenses/by-nc-sa/4.0/", True),
    "cc by-nc-sa 3.0": (True, "https://creativecommons.org/licenses/by-nc-sa/3.0/", True),
    "cc by-nd 4.0": (False, "https://creativecommons.org/licenses/by-nd/4.0/", False),
    "cc by-nc-nd 4.0": (False, "https://creativecommons.org/licenses/by-nc-nd/4.0/", False),
    "written for this worksheet": (True, "", False),
}
# Free to read, not free to rewrite (or to use with AI tools): their terms, as of October 2026.
NO_ADAPT = {
    "commonlit.org": "CommonLit's terms forbid modifying its texts and any use with generative AI",
    "readworks.org": "ReadWorks' terms forbid rewriting its passages or question sets",
    "ck12.org": "CK-12's license forbids making derivatives by automated means, including AI",
    "openstax.org": "OpenStax's newer books are noncommercial and its terms forbid use with generative AI without "
                    "written permission",
    "newsela.com": "Newsela's articles are licensed, not open",
    "khanacademy.org": "Khan Academy's terms don't clearly allow adapting its content",
}
INSTEAD = ("Use Wikipedia or Simple English Wikipedia (CC BY-SA), Project Gutenberg or Wikisource (public domain), "
           "or a US government source (NASA, NOAA, USGS, the Library of Congress), or write the passage yourself")


def check_cite(cite: dict, where: str) -> tuple[str, str]:
    """(the credit line to print, the license's name) for a passage's "cite", or an error saying what to fix."""
    if not isinstance(cite, dict) or not cite.get("license"):
        raise WorksheetError(f"{where}: \"cite\" needs \"license\" (such as \"CC BY-SA 4.0\" or \"public domain\"), "
                             "and \"title\" and \"url\" when there is one")
    name = " ".join(str(cite["license"]).lower().replace("creative commons", "cc").split())
    url = str(cite.get("url", ""))
    site = next((s for s in NO_ADAPT if s in url.lower()), None)
    changes = str(cite.get("changes", "")).strip()
    if site and changes:
        raise WorksheetError(f"{where}: {NO_ADAPT[site]}, so the passage can't be adapted from it. {INSTEAD}.")
    if name not in LICENSES:
        raise WorksheetError(f"{where}: license {cite['license']!r} isn't one Paper Loop knows. Use one of: "
                             f"{', '.join(sorted(LICENSES))}. If the text is copyrighted and not openly licensed, "
                             f"don't print it: {INSTEAD}.")
    adapt, license_url, share_alike = LICENSES[name]
    license_url = license_url.removeprefix("https://").rstrip("/")  # shorter in print, and still the license's address
    if changes and not adapt:
        raise WorksheetError(f"{where}: {cite['license']} allows no changes, but \"changes\" says {changes!r}. Quote "
                             "it exactly, or choose another source.")
    if name == "written for this worksheet":
        return "Written for this worksheet.", name
    title = str(cite.get("title", "")).strip()
    author = str(cite.get("author", "")).strip()
    if not author and "wikipedia.org" in url:
        author = "Wikipedia contributors"
    # "Adapted" when the words were changed; "Excerpted" when the text is the author's own, only cut.
    lead = ("Adapted from" if re.search(r"adapt|simplif|rewr|reword|translat|paraphras|modern", changes, re.I)
            else "Excerpted from") if changes else "From"
    parts = [f"{lead} “{title}”" if title else lead + " the source below"]
    if author:
        parts.append(f"by {author}" if name in ("public domain", "us government work") else author)
    if url:
        parts.append(url)
    line = ", ".join(parts).replace("\u201d, ", ",\u201d ") + "."
    label = "Public domain" if name == "public domain" else "A US government work" if name == "us government work" \
        else str(cite["license"]).replace("cc ", "CC ").replace("Cc ", "CC ")
    line += f" {label}" + (f" ({license_url})" if license_url else "") + "."
    if changes:
        line += f" Changes: {changes}."
    if changes and share_alike:
        line += " Shared under the same license."
    return line, name


# --- How hard a text is to read ----------------------------------------------------------------------

def _syllables(word: str) -> int:
    word = word.lower().strip(".,;:!?\"'()")
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", word)
    word = re.sub(r"^y", "", word)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", word)))


def reading_grade(text: str) -> float | None:
    """The Flesch-Kincaid grade of English text: a rough guide to its difficulty, best between grades 3 and 12.
    None when there's too little text to judge."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    sentences = max(1, len(re.findall(r"[.!?]+(?:\s|$)", text)))
    if len(words) < 30:
        return None
    syllables = sum(_syllables(w) for w in words)
    return round(0.39 * len(words) / sentences + 11.8 * syllables / len(words) - 15.59, 1)


def level_problems(defn: dict) -> list[str]:
    """Passages much harder to read than the worksheet's grade, or than the level they were adapted for."""
    problems = []
    for b in defn["questions"]:
        if b.get("type") != "passage" or b.get("note") or b.get("mono") or b.get("lang"):
            continue
        grade = reading_grade(b["text"])
        if grade is None:
            continue
        target = b.get("reading_level")
        aim = float(target) if target is not None else float(defn["grade"])
        if grade > aim + (1.0 if target is not None else 3.0) and aim >= 2:
            problems.append(f"{b['title'] or b['id']} reads at about grade {grade:g} (Flesch-Kincaid), "
                            + (f"above the grade {target} it was adapted for" if target is not None
                               else f"well above grade {defn['grade']}")
                            + ": shorter sentences and everyday words bring it down, or set \"reading_level\" if "
                              "that's intended")
    return problems


# --- Getting a text ----------------------------------------------------------------------------------

AGENT = "PaperLoop/0.4 (classroom worksheets; https://github.com/) python-urllib"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt:
                raise
            time.sleep(5)  # rate-limited: once more, after a pause
    raise AssertionError("unreachable")


def wikipedia(title: str, simple: bool = False, site: str | None = None) -> dict:
    """An article's plain text and its revision: {"title", "text", "url", "license", "site", "retrieved"}.
    site: another Wikimedia wiki, such as en.wikisource.org (primary sources, mostly public domain)."""
    site = site or ("simple.wikipedia.org" if simple else "en.wikipedia.org")
    query = urllib.parse.urlencode({"action": "query", "prop": "extracts|revisions|categories", "explaintext": 1,
                                    "titles": title, "rvprop": "ids|timestamp", "cllimit": "max", "redirects": 1,
                                    "format": "json", "formatversion": 2})
    data = json.loads(_get(f"https://{site}/w/api.php?{query}"))
    page = (data.get("query", {}).get("pages") or [{}])[0]
    if page.get("missing") or not page.get("extract"):
        raise WorksheetError(f"{site} has no article called {title!r}; check the title (as in the article's URL)")
    revision = page["revisions"][0]["revid"]
    name = page["title"]
    url = f"https://{site}/w/index.php?title={urllib.parse.quote(name.replace(' ', '_'))}&oldid={revision}"
    text = _clean(page["extract"])
    if "wikisource" in site:  # the source text is usually public domain; its page says which
        categories = " ".join(c.get("title", "") for c in page.get("categories", [])).lower()
        unbacked = any(w in categories for w in ("nonstandard texts", "without a source", "unsourced"))
        return {"title": name, "text": text, "url": url, "license": "public domain", "author": "", "site": site,
                "retrieved": date.today().isoformat(),
                "check": ("Wikisource files this page under nonstandard or unsourced texts: no scanned edition stands "
                          "behind it, and its license isn't confirmed. Find the text in a scanned edition (the "
                          "Internet Archive, HathiTrust, Chronicling America) and quote that instead" if unbacked else
                          "Wikisource texts are mostly public domain, but translations and some pages aren't: check "
                          "the license box at the bottom of the page, and the edition it reproduces")}
    return {"title": name, "text": text, "url": url, "license": "CC BY-SA 4.0",
            "author": f"{'Simple English ' if simple else ''}Wikipedia contributors", "site": site,
            "retrieved": date.today().isoformat()}


def _clean(extract: str) -> str:
    """Wikipedia's plain text, minus the wreckage of its math markup: formulas come through as runs of one or
    two characters a line, then a {\\displaystyle ...} line. Headings become "# Heading"."""
    lines, out, run = extract.split("\n"), [], []
    for line in lines:
        bare = line.strip()
        if "\\displaystyle" in bare:
            run = []
            out.append("[formula]")
            continue
        if (bare and len(bare) <= 3) or (not bare and run):  # blank lines inside a formula belong to it
            run.append(line)
            continue
        if len(run) < 4:
            out += run
        run = []
        heading = re.fullmatch(r"(=+)\s*(.+?)\s*\1", bare)
        out.append(f"# {heading.group(2)}" if heading else line.rstrip())
    if len(run) < 4:
        out += run
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def gutenberg(book: int) -> dict:
    """A Project Gutenberg book's text, its license header and footer removed (as Gutenberg asks when the
    text is reused without its name). Public domain in the US."""
    raw = _get(f"https://www.gutenberg.org/cache/epub/{int(book)}/pg{int(book)}.txt").decode("utf-8", "replace")
    title = re.search(r"^Title:\s*(.+)$", raw, re.M)
    author = re.search(r"^Author:\s*(.+)$", raw, re.M)
    start = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", raw)
    end = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG EBOOK", raw)
    body = raw[start.end() if start else 0:end.start() if end else len(raw)].strip()
    body = re.sub(r"(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])", r"\1", body)  # _italics_ marks: the words alone
    return {"title": title.group(1).strip() if title else f"Book {book}", "text": body.replace("\r\n", "\n"),
            "author": author.group(1).strip() if author else "", "url": f"https://www.gutenberg.org/ebooks/{int(book)}",
            "license": "public domain", "site": "gutenberg.org", "retrieved": date.today().isoformat()}
