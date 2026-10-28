# Students teaching each other: group work and paper labs (Oct 27)

Ben asked for two things:
- a look at PhET, NOVA Labs (evolution, exoplanets), and other openly licensed labs, to borrow their best
  ideas and questions for more games and interactive worksheets;
- pedagogically sound activities for mixed-skill groups, where each student has a role, so students help
  the teacher by teaching their peers.

It all runs in the Cowork plugin on a free Claude for Teachers account, with no new packages.

## What was built

**`PL teamwork`** (`teamwork.py`, `references/teamwork-format.md`). One JSON file makes a PDF: a teacher's
page, role cards, and what each group or student needs. Every activity pairs a group goal with a one-page
exit sheet each student does alone, which Paper Loop scans and marks like any worksheet. Slavin's reviews
found that pairing, group goals plus individual accountability, is what makes cooperative learning raise
achievement. Five structures:
- **lab**: an investigation in rounds with rotating jobs (Facilitator, Recorder, Skeptic, Reporter,
  Materials), a task card with a dice table and a blank data table, and tokens to cut out (patterns that
  survive a black-and-white copy, in sizes, with blank backs that work like coins);
- **jigsaw**: an expert card per letter, an expert sheet per part (what to teach, a check question, a
  sketch box), and home-group notes;
- **reciprocal**: reading in chunks with a "stop and talk" bar after each, for Predictor, Questioner,
  Clarifier, and Summarizer;
- **pairs**: PALS-style coach and player, with the coach's correction words and a fold-over sheet with a
  "switch jobs here" line;
- **heads**: Numbered Heads Together, with number tents and the teacher's question page.

Role cards fold into tents: the job's name faces the group (upside down on the sheet, so it reads right
once folded), and what to do and say faces the student. Sentence starters on every card give everyone,
English learners especially, the words for the job. Abilities on the task card ("counting carefully",
"spotting a pattern") follow Cohen and Lotan's Complex Instruction: no one is good at all of them, everyone
is good at some, and the teacher names a student's contribution out loud.

**`PL groups`** deals mixed-skill groups from a class's marked work, by class ID only: sorted by recent
scores on one skill or all, then dealt back and forth (snake order) so every group has a range. Extras join
a group rather than working alone. First jobs are dealt at random, not by score. With only a roster, groups
are random. `progress/groups.md` is for the teacher and says so.

**Paper labs and examples**, each with its own one-page exit sheet:

| Example | Grade | Structure | The idea it borrows |
| --- | --- | --- | --- |
| Beetles and Birds | 7 | lab | natural selection by predation (NOVA Evolution Lab, PhET Natural Selection): dice birds hunt paper beetles over three generations |
| Shake and Spill: Half-Life | 9 | lab | radioactive decay as chance (PhET's Radioactive Dating Game, the coin-flip classic): paper atoms spilled from a cup |
| Lynx and Hares | 7 | lab | predator-prey cycles (NetLogo Wolf Sheep Predation): a card toss over ten generations; the exit sheet graphs the real Hudson's Bay fur records |
| Atom Builders | 8 | lab | PhET's Build an Atom: a die picks the atom, paper particles build it, a second roll makes an ion or isotope |
| How Do We Find Planets? | 9 | jigsaw | NASA's four detection methods; the exit sheet reads a real Kepler light curve and finds the planet's size from the dip |
| The Rooftop Garden | 4 | reciprocal | reciprocal teaching on the existing story |
| Ratio Coach | 6 | pairs | PALS-style coaching on ratios |
| Moles: Heads Together | 10 | heads | review before the moles worksheet |

The activities and questions are Paper Loop's own; the sources lines credit where ideas and facts came
from.

## The research behind it

A research agent read the license pages of the open labs directly (checked Oct 27, 2026) and the
cooperative-learning evidence. What changed because of it:
- **Licenses.** PhET's simulations moved to CC BY-NC 4.0 for anything released since March 29, 2026; its
  teacher-written activities stay CC BY 4.0. Concord Consortium moved to CC BY-NC; OpenSciEd is CC BY only for
  middle school; NetLogo, HHMI, and The Wonder of Science are NonCommercial (some ShareAlike); NOVA Labs,
  Gizmos, NAAP, and Zooniverse have no open license. NASA, USGS, and NOAA are free to use. So every lab takes
  the *idea* (ideas and facts aren't copyrightable) in Paper Loop's own words, credits what inspired it, and
  uses real government data where it can. The half-life lab's old "CC BY 4.0" line for PhET was wrong and is
  gone; the format doc has a table of what each source allows.
- **Real data.** The exoplanet exit sheet reads a real Kepler light curve for HAT-P-7 (2-hour means from
  Kepler's first quarter, processed by the agent; period 2.2 days, a 0.6% dip, a planet 16.9 Earths wide per
  the NASA Exoplanet Archive). The lynx-and-hare sheet graphs the Hudson's Bay Company fur records,
  1900-1920.
- **Honest evidence on the teacher's page.**
  - Labs: Slavin's +0.32 with group goals and individual accountability, against +0.07 without.
  - Jigsaw: learning results are mixed (five 2022 classroom trials found no gain), so it now prints the
    Jigsaw II safeguards: a teacher check on each expert's box, notes on every part, and an exit sheet on all
    parts.
  - PALS: strong in elementary reading, weaker in math.
  - Numbered Heads: little rigorous research; kept for quick review.
- **Pairing and grouping.** Pairs now follow PALS: the ranked class split in half, the halves paired in order.
  `--similar` makes like-skill groups for targeted practice. Lou et al. (1996) found students who are behind
  do better in mixed groups and middle students in similar ones.
- **Coaching words** follow PALS's correction pattern ("Check it", then a hint, then show how), in Paper
  Loop's wording.

## How it was tested

Three agents played Claude in sandbox-like folders, from a teacher's message alone:
1. A 6th grade "paper version of PhET" lab, plus grouping Period 2 from a marked water-cycle worksheet. It
   built a water-drop journey lab with a simulation of its dice rules (20,000 runs).
2. A 10th grade jigsaw on the long-term causes of World War I, with sources, for sections of 28 and 31 and
   some English learners. It checked two primary sources against scans.
3. A 3rd grade reading group on bats (reciprocal teaching) and partner practice on 6s, 7s, and 8s.

What changed because of them:
- **Layout.**
  - The rounds line ran off the page at 7 or more rounds (the predator lab's own 10). It now wraps as boxes
    to check.
  - The dice table's label column now fits its labels, and data-table columns are sized by heading.
  - Reading lines for young readers are about 70 letters.
  - Coach-sheet questions print at 16pt and shrink only to fit, clear of the page label.
  - The home-group notes kept a line on the box border; the page now asks for the student's own words and
    has a box for how the parts connect.
  - Student-facing type is 25% bigger in grades 2-3 and 12% in 4-5. Role card text fills the card and
    shrinks only to fit.
- **Teacher's page.**
  - It gives page numbers for what to print, and says it's printed once.
  - It lists `materials`, and with `class_size`, how many groups.
  - Grouping is offered either way: from marked work, or at random.
  - Jigsaw timings now add up to `minutes`, and expert groups are 3-4 students.
  - The worksheet note covers its versions.
- **Reading groups.** The order was backwards (predict, then summarize); after each part it's now
  summarize, question, clarify, then predict the next part, with no prediction after the last. The sheet says
  who reads.
- **Coach card.** "What's the first step?" didn't fit fact practice; the coach now gives a hint, and the
  format doc shows hints written into the answers.
- **Authors can word the cards** (`roles`): plainer names and jobs for young students, or content sentence
  starters ("__ led to __ because __").
- **Jigsaw parts.**
  - `cite` is checked like a passage's, and parts from CommonLit, ReadWorks, and other no-adapt sources are
    refused.
  - New fields: `quote` and `quote_source` for a primary source set apart, and `words` for a key-words line.
  - Tents show the expert's topic.
  - Long parts are flagged before the teach and sketch boxes disappear.
- **Checks.** `teamwork` flags a missing exit sheet, a reading more than two grades above the class, and a
  data table that won't fit.
- **Files and commands.**
  - Every `groups` run wrote the same file. Each kind now has its own (`groups-pairs.md`,
    `groups-lab-similar.md`).
  - `preview --page` or `--sheet` deleted the other previews; now each replaces only itself.
  - `--help` lists every command.
  - A rate-limited `source` retries once and says to wait, instead of "can't reach".
- **Fonts.** Arrows printed as "->" on group pages because the font choice skipped dice rows and tables; it
  now reads every string. The worksheet guide's claim that → always prints as written is corrected.
- **Worksheets, found along the way.**
  - In grades 2-3, two- and four-column choices printed the letter touching its text. Fixed; the grade 3
    website sample is rebuilt, and printed copies still mark, since the letters didn't move.
  - A fourth line of instructions crowded the header rule.
  - Answer keys printed a long key over the ruled lines, like strikethrough, and doubled a key's own "Full
    credit:" label.
- **Privacy.** One trial agent, debugging a rate limit, put the user's email in a request header to Wikipedia
  by hand. Paper Loop's code never does this. SKILL.md now says never to send a teacher's or student's name
  or email to a website.

## Day 2 (overnight, Oct 27-28)

Ben asked for four things, in order: review and harden; more labs and games (with a measurements-only
greenhouse lab); every student in group work; then the Day 1 backlog. Commits on the `day-2` branch.

**Review and harden.** An independent code review of the group-work code found 14 confirmed bugs, each
reproduced. All fixed, with regression tests:
- **Groups.**
  - `--similar` put every leftover student in the lowest group.
  - Groups grew past a structure's limit, and handed out jobs that had no printed card.
  - `--size 0` crashed.
  - Groups now come out as even as the structure allows: labs 3-5, pairs 2 or one trio, a jigsaw home
    group with every letter.
- **Input.**
  - Wrong types crashed with a traceback or printed one letter per line.
  - A number answer on a coach card crashed.
- **Silent loss.**
  - Reading parts dropped their key words and quotes.
  - Long titles, names, task cards, readings and teacher pages ran off the page without a warning.
  - Unshaped scripts printed reversed or as boxes.
- **Smaller.** The teacher's group count was wrong for small classes, preview deleted files it shouldn't,
  and a "Full credit for any two of:" key lost its condition.

The trials' worksheet bugs are fixed too:
- per-version page fit in `make`;
- a key-words page without the inline glossary;
- matching items without numbers, with columns sized to their text;
- bigger directions in grades 2-3;
- sentence starters that fit;
- Wikisource pages without a scan flagged;
- a rate-limit retry.

**More labs and games.**
- **New features.** `data` tables (blank cells welcome) and printed boards: `grid`, `number_line`, `rows`,
  `ring`, `graph`, and `diagram` for a picture.
- **Eight new labs, each with an exit sheet.**
  - circuits;
  - density;
  - the greenhouse effect, a dice model of infrared plus NOAA's Mauna Loa CO2 measurements, physics only;
  - forces;
  - plate tectonics, with real USGS earthquake depths and Hawaii's island ages;
  - genetic drift;
  - fractions (grade 4);
  - area (grade 3).
- **Testing.** Two more teacher trials (an 8th grade energy lab, 4th grade fraction centers), and a science
  reviewer who simulated every dice game.
- **The simulations found three labs that couldn't work as printed:**
  - lynx and hares never cycled with the cards given;
  - the beetle game ran out of brown tokens, and its worksheet data couldn't come from the game;
  - most circuits groups never met both series and parallel.
- **The review's other fixes:** several science points (friction and weight, unstable isotopes, the
  fingernail comparison, Hawaii's ages), unfair keys, and corner labels on graphs that don't start at zero.

**Every student in group work.**
- **Versions.** Activities take `versions`, like worksheets: plain English, or a home language, swapping the
  words and keeping the work.
  - Latin, Greek, and Cyrillic versions print as extra pages, with the pages' own words in the language
    (Spanish built in, `labels` for any other).
  - Arabic, Chinese, Indic and other scripts go to a Word file.
  - The exoplanet jigsaw has plain-English and Spanish versions.
- **Team points.** `PL teampoints` scores teams the STAD way, by each member's improvement on their own
  earlier work. It writes a page to post, with no names or IDs.
- **Game groups.** `--structure game`: groups with no jobs, never above the game's player count.

**Day 1 backlog.**
- **Practice for every student.** A worksheet's `stretch` questions go to students with full credit, so a
  practice sheet no longer signals who struggled.
- **An accommodation log.** `progress/supports.csv`, for case managers.
- **Writing room.** Versions printed a few questions to a page give the free space to writing (up to double).
- **Review slides** can skip readings or the "Fix it" slide.
- **Practice of a practice** draws new numbers from the original worksheet. Its test passes either way: the
  old code fell back to the base numbers, which differ in the test.

243 tests pass.

## Still open

- Bilingual word banks and sentence frames on worksheets.
- A view of supports fading over time, and `work_optional` for a calculator or scribe.
- Go-over picks for a `pool` question whose alternatives change the options.
- Answer keys for draw questions show the checklist, not the drawn answer (bars, plotted points).
- Cards-and-games: levels for similar groups (a 1-2 dot pile), a printed Snake Race path, and plainer
  rules for young readers.
- Copies of the website's grade 3 and Spanish samples printed before today still mark (their answer areas
  didn't move), but the website PDFs should be replaced with the rebuilt ones in `samples/`.
- Not yet run in a real classroom, or in real Cowork on a Claude for Teachers account.
