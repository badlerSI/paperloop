# The next level: every student, the same high bar (Oct 27)

Ben asked for these:
- scaffolding, granular IEP accommodations, and support in the top 20 languages of US English learners;
- unlimited enrichment from free, human-written sources;
- a paper version of every ed tech subscription, including cards and games for any checker or chess board;
- feedback at scale;
- progress tracking for teachers and families;
- a different homework copy for each student;
- the next day's slides opening with what the class missed;
- sample worksheets for the website, with a QR code.

All of it runs in the Cowork plugin on a free Claude for Teachers account, with no new packages. The research
behind it is in [research-notes.md](research-notes.md).

## What was built

**Versions** (`forms.py`, `references/versions.md`). One worksheet prints as several forms, each with its
own page code, and a scan of every copy marks as one stack.
- **Supports.** Each question carries supports (`plain`, `hint`, `steps`, `example`, `frame`, `word_bank`,
  `glossary`), and each version picks which ones print.
- **Print options per version.** Large print (true is 18pt; the header, ID boxes, comments, and practice
  sheets grow too), more room to write, at most N questions a page, graph paper, fewer choices (letters
  kept), `only` (a shortened assignment), and reference pages to keep.
- **Help that changes what's measured** is flagged question by question: hints, steps, worked examples, fewer
  choices, a word bank on a fill-in question, plain wording on a reading question. Progress reports mark
  those scores "with help on the page".
- **Footers.** Every copy's footer says "form A/B/C", so versions don't stand out.

**Home languages** (`script.py`, `fonts.font_for`, the Word companion page).
- About 35 languages cover the top 20 of US English learners and the next most common. Each has a quality
  rating, and `make` asks for a bilingual adult's check (`reviewed_by`) where Claude's translation is less
  reliable.
- Arabic, Dari, Farsi, Urdu, and Pashto are shaped and set right to left in pure Python, with brackets,
  numbers, and currency signs in the right places. Chinese, Japanese, and Korean use a found font or the
  viewer's.
- Bengali, Nepali, Burmese, and the others that need a shaping engine go on a Word page, which Word and
  Google Docs print correctly.
- Comments and summaries on the marked pages print in Arabic script too. Comments in scripts the page can't
  print are refused at `check`.

**A different copy for each student** (`variants`).
- `vars` with `{{ expressions }}` (exact arithmetic, rounding half up, `money`, `frac`, `mixed`), a `pool` of
  alternatives, and shuffled choices whose class results line up by the base letter.
- `copies-key.pdf` gives every copy's answers, and `make` warns when an answer repeats on most copies.

**Practice sheets** (`PL practice`).
- Each student who missed something gets up to three of those questions. They come with new numbers or
  another pool item where the worksheet has them, on the student's own version, with the comment they got
  last time.
- The ID is printed, so the scan routes itself.
- Retries of the very same question don't move progress statuses.

**Progress** (`PL progress`).
- `dashboard.html`: one file that works offline. It shows skills student by student, groups for the next
  lesson, how each worksheet went, and what marking noticed, and can print one student only.
- `parents.docx` and `parents-<code>.docx`: plain words, a line for the name, the evidence count, something
  to try at home, an interpreter notice, and a footer that says AI helped mark.
- `progress.csv`: numbers, with help on the page as its own column.

**The next day's slides.** A lesson phase with `"review"` opens with the earlier worksheet's go-over: how it
went, the most-missed questions with how the class answered, and a "Fix it" slide for the marked copies.

**Enrichment from free sources** (`sources.py`, `PL source`).
- Wikipedia, Simple English Wikipedia, Wikisource, and Gutenberg, with revision links.
- Credit lines that meet the license.
- Refuses to adapt CommonLit, ReadWorks, CK-12, newer OpenStax, and ND texts.
- A Flesch-Kincaid check against the grade.
- `note` blocks ("Done early?").

**Cards, games, and foldables** (`pieces.py`, `PL pieces`, built by a subagent).
- Fold-over cards and blank cards for students.
- Snake Race, Question Checkers, Four in a Row, and Chess Quiz for any 8×8 board and a die.
- A board, a paper die, a spinner, tent pawns, a fortune teller, an eight-page mini-book, ABCD answer cards,
  and bingo.
- The fold geometry is checked with geometric models in its tests.

**Samples for the website** (`samples/`, `devtools/samples.py`, `references/samples/`). There are four
one-page samples. Each has a "Try Paper Loop" box with the directions as print (Claude reads print; it can't
reliably read a QR code from a photo) and a QR code for the teacher's phone. The skill rebuilds each one
pixel for pixel from the bundled copy, so any way a teacher fills one in marks.

**Walkthrough** for teachers and the podcast:
[Paper Loop: One Worksheet, Every Student](https://claude.ai/artifact/8bB8CAgaNFiG82pyRR4miV). It covers the
loop, "Every student, the same high bar", blind marking, the research, the SaaS Reaper map, and what it
doesn't do yet.

## How it was tested

**Trials.** Three agents played Claude in sandbox-like folders, from a teacher's message alone:
1. A 5th grade water-cycle sheet in six versions (large print, chunked, word bank and starters, Dari,
   Spanish).
2. Seventh grade homework with 8 different copies, marked by hand, then practice sheets, then progress with
   Spanish family pages.
3. An 8th grade Underground Railroad enrichment sheet from Wikipedia and primary sources, marked, then a
   45-minute lesson on the Fugitive Slave Act opening with its go-over.

**Specialist review.** An agent playing a special education case manager and an ESL specialist reviewed the
guide and every printed page.

**Code review.** It found 16 confirmed bugs with reproductions, and 5 risks.

What changed because of them:
- **Marking.**
  - `todo` crashed when one version split an essay and another didn't.
  - A smudged page code marked a copy against the base key: it now goes to the review pile.
  - A student's pages from two different copies were summed: now they go to review.
  - A practice sheet fed twice counted twice.
  - Crops cut off writing just below the box: they now reach 14pt below it.
- **Answer keys.** Rounding was half to even ($0.62 for 5/8 of a dollar), and keyword arguments were
  silently ignored. Exponents and string repeats could hang the sandbox. Partial `base` values failed, and
  `drop` was ignored.
- **Large print.** It stopped at the worksheet: practice sheets and comments were normal size, the header
  and ID boxes small, and the choice letters touched their text. True meant 1.4x, not 18pt.
- **Home languages.**
  - Arabic comments printed as boxes.
  - Dari's combining hamza was refused.
  - Brackets and `$`/`%` came out on the wrong side.
  - Translated option lines read left to right, and the translation printed smaller and grayer than the
    English.
  - Translated options ignored fewer choices.
- **Honesty.**
  - "With support" was per form, not per question, and called scaffolds "modifications" in a way a report
    card could misuse.
  - Practice retries of the same item made family pages say "Got it".
  - The family footer said the teacher marked the work.
  - Translated family pages kept English feedback.
  - There was no interpreter notice and no review of translated family pages.
  - The CSV put "(with support)" inside a grade cell, a pattern transcripts must avoid.
- **Standing out.** Only versions had a form letter, and version names like "Support" sat in folder and
  file names. A version a page longer than the base gets a `Check:` now.
- **Guide.**
  - The plan decides, not the teacher.
  - What state tests allow varies by state.
  - Dropped "extra time helps nearly everyone" and the overstatement of plain wording's evidence.
  - Added a WIDA-level table, students with little schooling, and the families.json guidance.
  - Primary sources come from a scan-backed edition, never a quote inside Wikipedia (the trial caught
    Wikipedia misquoting William Still's telegram).
  - Two passages per question.
  - "Excerpted from" for cut texts, and shorter credit lines.
- **Smaller.** Practice notes quoting the old numbers, stale preview pages, "1 points", dates "from Oct 27
  to Oct 27", the dashboard breaking on a skill named `constructor` or containing `<!--`, Word elements out
  of schema order, double periods in plans, `--help`, and `make` now writes an answer key without a lesson.

151 tests pass. The Word files pass the docx skill's validator.

## Still open

- Practice for every student (a stretch item for full credit), so a practice sheet isn't a public signal.
- An accommodation log for case managers, a view of supports fading, and `work_optional` for a calculator or
  scribe.
- Writing areas that grow into the space `per_page` leaves.
- Bilingual word banks and frames.
- A review phase option to skip passage slides and the "Fix it" slide.
- Hiding match-item numbers.
- Practice of a practice sheet gets no new numbers.
- Go-over picks for a `pool` question whose alternatives change the options.
- Not yet tried in real Cowork on a Claude for Teachers account, or opened in Word, PowerPoint, or Google
  Docs. Not yet tried with real handwriting in a home language.
