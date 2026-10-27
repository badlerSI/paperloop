# Day 1 notes

Oct 26, 2026. The loop runs end to end on simulated scans with real marking (Sonnet 5.5): no misspellings lost, no wrong answer marked correct, about half a cent per page. Ben's hand-filled copies are still to come, and they're the test that matters: the simulated handwriting is a font, and every model read it perfectly.

## Day 1 checklist

| Task | Status |
| --- | --- |
| Repo, Apache 2.0 license, layout, SPEC.md | Done |
| Plom spike and note | Done: design reference only ([docs/plom-spike.md](docs/plom-spike.md)) |
| `make.py`: two-page density worksheet, layout.json, key.json | Done |
| Ben prints and fills four copies | Waiting on Ben: `paperloop fill-guide` says what to write |
| `ingest.py`: split, deskew, QR, ID, page map | Done; 9/9 pages routed on the simulated set |
| `mark.py`: Sonnet 5.5, marking rules, feedback.json, cost log | Done; run for real on the simulated set |
| `render.py`: comments beside boxes, summary, grade off by default, sorted by ID | Done |
| Ben reviews the output on paper | Waiting on a real run |
| NOTES.md | This file; fill in the real-run results below |

## What's verified (simulated scans, no model)

- **Page routing: 9/9.** Four students, eight pages, shuffled, skewed up to 1.8°, one sheet upside down, plus a blank page. Each page went to the right student and page, and the blank page was skipped.
- **Ambiguous IDs go to review:** two bubbles filled in one digit are flagged, never guessed.
- **Only answer boxes leave the laptop:** a test checks that every image sent to the marker is box-sized.
- **Empty boxes aren't sent:** all five of the blank copy's boxes were settled locally.
- **Review gate:** `render` refuses while flagged answers are unreviewed.
- **Separate scans work:** fronts and backs scanned as two PDFs route the same as one duplex PDF.
- 6 tests: `pytest`.

## What broke or surprised

- Plom's paper generator asserts its public code is numeric; trivial, but its API assumes its server's conventions throughout.
- The first real run failed on `.env`: the Console's sample `curl` command had been pasted in instead of a `KEY=value` line. Fixed by hand; worth a clearer message in `.env.example`.
- The simulated handwriting is a font. Every model read it perfectly (100% of words, all misspellings kept), so it can't tell the models apart on reading. Only real handwriting can.
- **Sonnet writes long comments.** At first, 45% ran over the 15-word rule. Telling it "one short sentence usually beats two, name what's right or the one fix, not both" brought that down to 13% with no change in verdicts.
- **Almost every flag is "the key doesn't settle this answer,"** not a misread. Q3 and Q5's keys describe a complete explanation without saying whether half of one earns full credit.

## Model and effort sweep (simulated set, 3 runs each)

15 answered boxes per run, scored against `scans/sim/sim-class.truth.json`. Cost per page includes the two blank pages. Second table is after the comment-length prompt change.

| Model | Effort | ¢/page | Verdicts right | Flag rate | Comments over 15 words | Sec/run |
| --- | --- | --- | --- | --- | --- | --- |
| Haiku 5.5 | low | 0.03 | 33/45 | 3% | 12/45 | 11 |
| Haiku 5.5 | medium | 0.05 | 33/45 | 25% | 9/45 | 18 |
| Haiku 5.5 | high | 0.09 | 38/45 | 15% | 8/45 | 25 |
| Sonnet 5.5 | low | 0.54 | 45/45 | 13% | 21/45 | 13 |
| Sonnet 5.5 | medium | 0.54 | 45/45 | 13% | 19/45 | 11 |
| Sonnet 5.5 | high | 0.57 | 45/45 | 13% | 21/45 | 11 |
| Opus 5.5 | low | 1.04 | 45/45 | 15% | 2/45 | 16 |
| Opus 5.5 | medium | 1.36 | 45/45 | 18% | 5/45 | 19 |
| Opus 5.5 | high | 1.91 | 45/45 | 20% | 2/45 | 27 |

After the prompt change:

| Model | Effort | ¢/page | Verdicts right | Flag rate | Comments over 15 words |
| --- | --- | --- | --- | --- | --- |
| Sonnet 5.5 | low | 0.54 | 45/45 | 8% | 10/45 |
| Sonnet 5.5 | medium | 0.57 | 45/45 | 10% | 6/45 |
| Opus 5.5 | low | 1.01 | 45/45 | 13% | 4/45 |
| Opus 5.5 | medium | 1.51 | 45/45 | 20% | 1/45 |

All 39 runs: 0 misspellings lost, 0 wrong answers marked correct, 100% of words transcribed.

- **Haiku is out.** It under-credits correct answers (Q3 and Q5 for two students, every run) and flags erratically. Cheap, but students would get "partial" for right answers.
- **Sonnet vs. Opus:** same verdicts. Opus keeps comments shorter and costs about twice as much (1 to 1.5¢ a page). Effort barely moves Sonnet's cost here, because these boxes are easy.
- **Default stays Sonnet 5.5 at `medium`.** Revisit after the handwriting sweep, where reading difficulty may separate the models and efforts.

## Cost per page (measured)

Sonnet 5.5 at medium effort: about 0.6¢ per page averaged over the set, about 0.75¢ per page with answers. A 30-student class on this two-page worksheet is about 40¢. Each box call is about 500 new input tokens (the image plus the question) plus about 1,000 cached tokens of marking rules, and about 100 to 130 output tokens. Prompt caching does kick in for the rules.

## Decisions made along the way (check these)

- **Corner squares plus one QR code.** Four ArUco markers handle deskew and orientation, so an upside-down sheet is fine. The QR code carries `assignment|page`.
- **The 4-digit ID is a bubble grid with one row per digit,** plus write-in boxes, on every page, so loose pages still route.
- **The key lives only in `key.json`,** not in `layout.json`, so the layout can be shared without answers.
- **The summary is a second, text-only call per page.** It sees transcriptions and verdicts, never the image.
- **Crossed-out words** are transcribed as `[crossed out: word]` and not graded.
- **Points:** correct is full credit, partial is half, everything else is zero. The teacher can change a verdict in review.
- **Defaults:** Sonnet 5.5, effort `medium`, flag threshold 0.8, grade off. All are flags on `mark` and `render`.
- **Small departures from the spec's repo layout:** `cli.py` lives inside the package (that's what makes the `paperloop` command install), and test fixtures are generated at test time by `simulate` instead of being committed.

## Test-plan results

| Metric | Target | Simulated (Sonnet 5.5, medium) | Ben's handwriting |
| --- | --- | --- | --- |
| Page routing | 100% or flagged | 9/9 | |
| Silent autocorrect | 0 | 0 of 6 lost | |
| False "correct" | 0 | 0 | |
| Transcription accuracy | track | 100% | |
| Flag rate | under 15% | 10% | |
| Cost per page | under 3¢ | 0.6¢ | |

Next: print four copies, fill them in per `paperloop fill-guide` (the key is already in `scans/day1/truth.json`), scan them, then `paperloop run` and `paperloop sweep` on `runs/day1`.

## Richer question types (built Oct 26)

Circle-the-answer, labeling, and drawing-with-checklist questions now work end to end. "Density Detectives" (`examples/sci7-density-02.json`) uses all of them: two circle-the-answer mysteries with a printed "why" for every option, one short answer, a density column to label, and a pine-vs-iron particle drawing.

How each is judged:
- **Circles are read from the scan, not by the model.** Ink that isn't on the blank page is counted per option row. One clear mark means no API call. Two marked rows, such as circling A, crossing it out, and circling B, go to the model, which reports the final choice and what was crossed out.
- **Labels and drawings are sent as a pair:** the blank printed region and the student's. The model can then tell the student's marks from the printing.
- **Drawings are described before they're judged** ("Pine wood box: 12 circles… Iron box: about 12"), then each checklist item gets yes, no, or unclear. Unclear goes to review.

Simulated results, Sonnet 5.5 at medium effort, 3 runs:

| Check | Result |
| --- | --- |
| Verdicts matching expected | 45/45 |
| Circled answers read right | 6/6 per run; 1 needed the model |
| Drawing checklist items matching expected | 9/9 per run |
| Misspellings kept, including in labels ("vegtable", "watter", "hunny") | all |
| Flags | 0% |
| Cost | 0.64¢ per page |
| Comments over 15 words | 8/45 |

**Two prompt fixes came out of this.** First, label and drawing comments ran long; the "one short sentence" wording helped. Second, the model was explaining layers with "the heaviest liquid sinks, the lightest floats," which is the misconception the lesson corrects. Every marking prompt now says to use the key's precise vocabulary, never the everyday word the lesson is correcting. That took it to zero.

**Rendering:** check and cross marks are drawn as strokes. The built-in symbol font rendered as solid squares in at least one PDF viewer.

## Ben's handwriting (Oct 26)

Four copies of Density Detectives, filled in by hand per `fill-guide`. They printed single-sided, giving 8 loose sheets, scanned in one pass on the HP 3301sdw's feeder with macOS Image Capture at 300 dpi. The 3301sdw can't scan both sides in one pass, despite its spec sheet. The real scan had things the fonts never did: an X across A that strays into the question text, "g/cm³" written as a stacked fraction, a "y" hanging below its label box, particles drawn as open loops, and "denisity" written as "density" with an extra i squeezed in.

Comparison: 3 runs per setting, on 15 answered questions.

| Model | Effort | ¢/page | Verdicts | "denisity" kept | Other misspellings kept | Drawing items | Flags | Comments over 15 words |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Haiku 5.5 | low–high | 0.04–0.08 | 45/45 | 0/9 | lost "vegtable" 9/9 | 78/81 | 5–10% | 2/135 |
| Sonnet 5.5 | low–high | 0.59–0.73 | 45/45 | 0/9 | all | 81/81 | 0% | 37/135 |
| Opus 5.5 | low | 1.36 | 45/45 | 3/3 | all | 27/27 | 0% | 7/45 |
| Opus 5.5 | medium | 1.51 | 45/45 | 3/3 | all | 27/27 | 0% | 3/45 |
| Opus 5.5 | high | 2.20 | 45/45 | 2/3 | all | 27/27 | 0% | 0/45 |

Every setting: pages routed 8/8, circled answers read right 6/6, no wrong answer marked correct.

- **Sonnet can't see a squeezed-in letter.** It read "density" with 0.93 confidence and no uncertainty in every run. Telling it to transcribe inserted letters as written didn't change that (0/6), and Opus at low effort did worse with it, so the rule was reverted.
- **Opus reads it and also says it's unsure.** It put "denisity" in `uncertain_words`, but at 0.85 confidence, just above the 0.80 flag line. Flagging any answer with uncertain words would send such cases to the teacher.
- **Opus at medium effort is the only setting that met the spec's silent-autocorrect target** on real handwriting (6/6 across two comparisons). It also writes the tightest comments, at about 1.5¢ a page: roughly 90¢ for a 30-student, two-page set, against about 36¢ on Sonnet.
- The squeezed-in letter is a borderline case: a squeezed letter usually means a self-correction, so reading "density" is what many teachers would do. The verdict was right either way.

## One-page worksheet with a handwritten ID (Oct 26)

"Water's Wild Ride" (`examples/sci6-water-01.json`) puts 6 questions on one sheet: two circle-the-answer questions with options in 2 and 4 columns, two 2-line short answers, a state-changes diagram to label, and the whole water cycle drawn from scratch with no printed scaffold, judged on a 5-item checklist. `compact: true` tightens spacing and shrinks the summary box. `id_style: "write"` replaces the bubble grid with four ID boxes.

**Handwritten IDs** are read by the model in a request that carries only the cropped ID strip, never any answers, so the provider never sees an ID next to a student's work. An ID goes to the review pile instead of being guessed when:
- a box is unclear, or the model's confidence is under 0.9 (stricter than marking, because a misread ID hands one student's feedback to another);
- the ID isn't on the class roster, if one is given with `--roster`.

This bends the spec's "IDs read locally, never by the model," so it's a per-worksheet setting and bubbles stay the default. A fully local route would be the Mac's built-in handwriting recognition, but that's Mac-only.

Simulated results, Sonnet 5.5 at medium effort, 3 runs:

| Check | Result |
| --- | --- |
| Handwritten IDs | 3 of 4 routed. "0006" was read correctly but at 0.85 confidence (the prompt warns about 0/6 lookalikes), so it went to review. |
| Verdicts | 54/54 |
| Drawing checklist items | 15/15 per run, after one fix |
| Misspellings kept | all |
| Cost | 1.8¢ per page (one sheet holds all 6 questions), plus about 0.13¢ per ID read |

**Fix:** on the messy copy's water cycle, the model wrote "no 'precipitation' label, so the item is only partly met" and still answered yes. The drawing prompt now says "yes" only if every part of the item, including any label it asks for, is on the page, and that partly met is "no". After the fix: 15/15 in every run.

**Other fixes from this round:**
- A long comment is shrunk to fit beside its question, so it can't run into the next one on a packed page.
- One-page worksheets no longer get a blank padding page after each student; they print single-sided.
- `sweep` now links the original scans too, so the review pile renders.

**Teaching call for Ben:** for wrong short answers, Sonnet's comment sometimes gives the answer away ("The drops come from water vapor in the air that condenses…") instead of hinting. The label comments hint. Decide which one the prompt should ask for.

## Water's Wild Ride on paper (Oct 26)

Four copies filled in by hand following `fill-guide.pdf`, then scanned on the HP into one 4-page PDF (`scans/day2/`). Copy 3158 also has margin doodles ("Hydro blast is SUPER effective", "Skool Sucks", a fish in the ocean).

**Handwritten IDs: every read was right, but the confidence number is useless as a gate.** Each of the four ID strips was read 3 times by each model at low and medium effort:

| Model | Reads right | Wrong digits | Confidence on right reads | Cost per read |
| --- | --- | --- | --- | --- |
| Haiku 5.5 | 17/24 | 0 (the rest were "?") | 0.60-0.88 | 0.01-0.02¢ |
| Sonnet 5.5 | 24/24 | 0 | 0.60-0.90 | 0.13¢ |
| Opus 5.5 | 24/24 | 0 | 0.60-0.92 | 0.26-0.61¢ |

No model ever guessed a wrong digit; when unsure they wrote "?". But confidence on correct reads of clear handwriting sat at 0.6-0.9, so the 0.9 cutoff sent 3 of 4 pages to review. "0006" always scored lowest, because its zeros are open like a C and the prompt warns about 0/6 lookalikes.

**Fix: the roster does the protecting.** With `--roster`, a read under 0.9 (down to 0.5) is accepted if it's on the roster and no other roster ID is one digit away. A misread usually changes one digit, so it can't have come from a classmate's ID. An ID one digit from a classmate's still needs 0.9. Without a roster nothing changed. In a class of 30 random 4-digit IDs, about 3 students will have a one-digit neighbour and still need the higher bar. After the fix: 4/4 routed.

**Marking: every model, 3 runs each** (`runs/day2-sweep`, about $2 for all 27 runs). Out of 18 answers with a key, 4 pages:

| Model | Verdicts right per run | Cost per page | Comments over 15 words | Errors beyond the arguable ones |
| --- | --- | --- | --- | --- |
| Opus 5.5, low effort | 17/18 every run | 3.2¢ (2.9¢ once the prompt cache is warm) | 7/54 | none |
| Opus 5.5, medium | 17/18 every run | 4.3¢ | 3/54 | none |
| Opus 5.5, high | 17/18 every run | 5.1¢ | 3/54 | none |
| Sonnet 5.5, low/medium/high | 16-17/18 | 1.4-1.5¢ | 11-17/54 | marked 3158's water cycle partial in 7 of 9 runs, though its runoff reaches the ocean |
| Haiku 5.5, low/medium/high | 15-16/18 | 0.1-0.2¢ | 0-7/52 | misread the crossed-out C as the answer, or as nothing; lost "vaper" |

- **No model ever called a wrong answer right.**
- **Effort barely matters.** Opus gave the same verdicts at every effort level, and so did Sonnet, give or take its wobble on 3158.
- **Opus's one miss isn't really a miss.** 0417's evaporation line has no arrowhead, and the checklist says "an arrow goes up". The key expected yes; Opus said no, every time.
- **Every model, in every run, read "undergrownd" as "underground".** It's one letter from a real word, and "ground" is written correctly on the line above. "vaper", "evaperation", "condensashun", "runof" and "precipatation" were kept by everything except Haiku.
- **Both real-handwriting tests now point the same way.** On Day 1, Opus kept "denisity" 6/6 and Sonnet 0/15. **Recommendation, accepted by Ben: Opus 5.5 at low effort is now the default.** It's about 3¢ a page, which is the spec's target, is exactly repeatable, and makes the fewest flags (4%).

The 2 checklist items every model "missed" are arguable, and the answer key is partly at fault:
- 0417's evaporation line has no arrowhead (above).
- 2093 drew a T-like mark before "evaporation" that may be a tiny arrow. The model said there was no arrow.

**What broke and got fixed:**
- **Pages bowed in the scanner.** Measuring printed-only patches showed 3 of 4 pages lined up at the corners but sat 3px across and 5-7px down in the middle of the page. That's paper curl or feeder stretch, which a 4-marker homography can't model. Day 1's scan had the same, smaller (about 2px). Printing that drifted more than the 4px slack showed up as "student ink", with three effects:
  - the blank copy's empty multiple-choice questions and drawing frame looked answered;
  - the messy copy's Q1 had "ink" on every option;
  - each of those cost a model call.
  
  `ingest` now flattens each page after the homography: it measures the shift of print-only patches across the page, fits a smooth quadratic warp, and resamples. Answer areas are now within 1px. 0417's header had a finer ripple, and a couple of pixels remain there. Results:
  - the blank copy reads 0 ink everywhere;
  - 5 of 6 circled answers are read on the laptop (only the circled-then-crossed-out one needs the model);
  - model calls went from 17 to 13.
- **Blank drawing frame marked wrong, with five ✗s.** On the blank copy, the drift put a sliver of the frame's own border inside the 2pt inset: 1,296 "ink" pixels. Flattening fixes the cause. The empty-answer check now also looks 4pt inside the border, as a second guard.
- **Next steps the key never asked for.** The summary said "Add arrows from the cloud to the rain" on two pages; no checklist item asks for that. The summary step only saw each drawing's description, so it reconstructed what was "missing". It now gets the checklist and label results, and the prompt says each next step must fix an answer that isn't correct or a checklist item that isn't "yes".
- **Doodles under the feedback.** Doodles never reach the model: margins aren't cropped. But feedback prints in the right margin, right where a 13-year-old doodles, and the comments became hard to read. Each line of feedback now has a white band behind it at 85% opacity, so the comment reads cleanly and the doodle still shows around it.

**Still open:**
- **Comment length.** Sonnet runs over the 15-word rule on about a third of comments (16-19 words); Opus on about 1 in 10. They still fit on the page, so this is style, not layout.
- **Strength length.** One Sonnet strength ran 26 words against "under 20".
- **Misspellings one letter from a real word** get normalized by every model ("undergrownd"). This only matters if spelling feedback is turned on.

## The Cowork plugin: Claude marks, no API key (Oct 26)

The rollout plan is Claude for Teachers: a free Claude Team plan for verified US K-12 teachers, with Cowork, which runs plugins in the desktop app or a web browser. So Paper Loop is now also a Cowork plugin (`plugin/`, with a marketplace file at `.claude-plugin/marketplace.json`). Claude reads the crops and writes the marks itself. The scripts do everything else.

**What's different from the CLI:**
- **Only what Claude's sandboxes ship with:** numpy, scipy, Pillow, pypdfium2, reportlab. The documented code-execution sandbox has no OpenCV, and Team plans may block package installs. Corner-marker finding, the homography, warping, and flattening are rewritten with numpy and scipy. The corner markers are the same ArUco patterns, read from hard-coded bits. On the four real day-2 pages the corners land within about 1px of OpenCV's, and choice reads and blank checks match the CLI exactly. A test runs the scripts with OpenCV, pydantic, qrcode, typer, and the anthropic SDK blocked.
- **A bit strip instead of the QR code.** 32 squares where the QR code was: 18 bits of assignment hash, 6 of page number, 8 of CRC, so one misread square fails the check instead of naming the wrong page. Pages printed with the old QR code are recognized by matching the question area against the blank template: 0.98 or more for the right page, 0.30 or less for other worksheets.
- **Handwritten ID boxes only:** no bubbles. Claude reads the ID strips in the same conversation as the answers, so the IDs must be class numbers, not names or district IDs.
- **Same files as the CLI.** `layout.json` and `key.json` are identical for the same worksheet, and `render` writes `feedback.json` and `ingest.json`, so `paperloop score` measures the plugin's marking.
- **The flow:** `prepare` (line up, crop) → Claude reads ID strips into `ids.json` → `ids` (the roster rule) → `todo` (one work order per question) → Claude writes `marks/qN.json`, one question across the whole class at a time → `check` (validates, lists flags, asks for shorter comments) → Claude writes `summaries.json` → teacher reviews flags → `render`. `render` refuses while flags are unreviewed, unless the teacher says to print as marked.

**Two trials on the day-2 scan.** In each, a fresh agent with none of this conversation followed SKILL.md in a folder set up like a teacher's: the skill, the assignment, the scan, and the class ID list. The second trial ran on the skill as fixed after the first, with the roster saved the way a spreadsheet saves it (`417`, `6`). I removed every day-2 example from the skill first, since the rules had quoted "denisity" and "undergrownd" and the format guide had used the water-cycle questions.

| | Skill, trial 1 | Skill, trial 2 | API, Opus 5.5 low (3 runs) | API, Sonnet 5.5 medium (3 runs) |
| --- | --- | --- | --- | --- |
| Verdicts | **18/18** | **18/18** | 17/18 each | 16-17/18 |
| Drawing checklist items | 14/15 | **15/15** | 13/15 each | 11-13/15 |
| Words transcribed right | 97% | **99%** | 96% | 97% |
| Comments over 15 words | **0/18** | **0/18** | 3/54 | 16/54 |
| Flags | 1/24 | 0/24 | 1/24 | 2/24 |
| Misspellings kept | 3/4 | 3/4 | 3/4 | 3/4 |
| What it cost | 118k tokens, 43 tool calls, 7 min | 122k tokens, 52 tool calls, 8 min | 3.2¢/page | 1.5¢/page |

- **Every reader, in every run, turned "undergrownd" into "underground".**
- **Trial 1's one flag was 2093's mark before "evaporation"** ("a T or an up-arrow"). Zoomed in, it's an up-arrow, so the key's "yes" was right.
- **Trial 2 had `zoom` and used it 9 times.** It got that item, and 0417's faint arrowhead, right.
- **Why the skill beats the API pipeline here:** probably because it marks one question across the whole class with the rules in hand, can zoom, and is told when a comment runs long. The API pipeline marks each crop alone in one shot.
- **Caveat:** two runs on four pages. That shows the approach works, not how much it varies.

**Fixes from the first trial's feedback:**
- `todo` and `check` now name pages where every answer is blank (an absent student, or work on another sheet), and the summary for those pages is left empty for the teacher.
- `check` now validates summaries too and gives the right next step; before, it always said "write summaries.json".
- `check` shows how each flag is scored for now, for example 1/5 with an "unclear" item counting as not earned. SKILL.md says what to tell a teacher who has stepped away.
- `PL zoom` makes an enlarged, darkened copy of part of a crop, for faint arrowheads and crossed-out letters.
- The rules now say an uncertain word goes below 0.8 only if it could change the verdict, so flagging is less arbitrary.
- `ids` says when a read got through because of the roster. SKILL.md explains the ID rule and the roster format, and dropped leading zeros (`6` for `0006`) are handled.
- Every path in SKILL.md is quoted (the assignment folder was "Water's Wild Ride"), and it says what's printed for the student: comments, check marks, and summary, never transcriptions.

**Fixes from the second trial's feedback:**
- **Marking rules:**
  - when you can't tell if a word is crossed out, write [maybe crossed out: word];
  - an ambiguous letter shape is a reading question, not a misspelling;
  - short answers get an optional note for the teacher;
  - a clear ID read is 0.95 or more, and don't aim at the cutoff;
  - one next step can cover an idea several wrong answers share.
- **Script output:**
  - `check` says "0 flagged" when nothing is flagged;
  - `ids` and `todo` say what's next, and `todo` names questions settled for every student;
  - `render` says whether scores were printed.
- **Work orders:**
  - every path is absolute, crops and output file alike;
  - example values are placeholders (`"<letter>"`, `<0 to 1>`) that fail the check if copied as they are.

**Still open:**
- **Usage limits.** About 120k tokens for 4 pages includes reading the skill and rules once. A class of 30 needs measuring on a real teacher account: it may need subagents (one per question) to keep each context small, and it may not fit one usage window.
- **The CLI can't read sheets made by the plugin**, because they have the bit strip instead of a QR code; the plugin reads both. The two should share one core: the plugin's, since it has no OpenCV.
- **Not yet tried in real Cowork:** plugin install, the cloud sandbox's Python packages, and uploads from Google Drive.

## Next iteration: worksheets kids want to do (Ben, Oct 26)

Day 1's worksheet tests function, and it's blank and boring: five short-answer boxes. The next iteration needs more than short answer. Directions to explore:

- **Question types.** Circle-the-answer, labeling, and drawing with checklist keys are built (above). Still to do: matching (draw a line), fill-in tables, numbers with units, ordering and sorting, claim-evidence-reasoning in three labeled boxes, and plotting on printed axes (points on a printed grid can be checked by image processing alone).
- **More diagram scaffolds.** Axes, a food web's organisms, a circuit. Keys stay checklists of things you can see; open-ended drawings get higher flag rates by design.
- **Engagement.** Phenomenon-first prompts ("Why does the can of diet soda float and the regular one sink?"), illustrations, and a scenario that runs through the page. The Make step drafts this from a lesson description.
- **IDs printed into the QR code instead of bubbles.** Print one copy per student from the roster. The QR carries an opaque per-class student code (never a name or district ID), and the header shows the student's first name for handing out. Spares get a "spare" code, and the teacher assigns them in review. This drops bubbles entirely (hard for young kids and for kids with motor issues) and makes per-student accommodations possible.
- **Accommodations applied automatically, from a local profile per student** (the v0.2 plan). At print time: larger print, fewer items, word bank, sentence starters, extra space. At marking time: "spelling isn't assessed", "accept a drawn or dictated answer". The model sees only a generic instruction, never the IEP, a diagnosis, or who the student is. Variants should look like the regular sheet. The teacher confirms a print summary ("5 students get the word bank version"), and a delivery log records what each student got. Profiles come only from the teacher or case manager; the tool never infers who needs one.

## Every subject, grades 2-12 (overnight, Oct 26-27)

The plugin now makes and marks worksheets for any subject from grade 2 to 12: reading passages, rubric-scored writing, essays that run onto more pages, fill-in-the-blank, matching and ordering, tables, show-your-work math, maps, coordinate grids, number lines, fraction models, clocks, timelines, bar charts, code listings, chemical equations, and music on a staff or rhythm line, with primary-style sheets for grades 2-3. Phone photos work as well as copier scans. Simulated class sets in thirteen subjects and grades were marked by fresh agents following the skill, and scored; a 16-student class took about 160k tokens. The full log, with results and what was fixed after each round, is [docs/all-subjects.md](docs/all-subjects.md).

**For the morning:** test kits for the new subjects are in `scans/day3/` (code tracing, chemistry, music, bar charts). Print `worksheet.pdf`, copy each page of `guide.pdf` by hand, scan, and mark with the skill using the kit's `assignment/` folder; then `devtools/score.py <work> scans/day3/<kit>/truth.json` scores it. Music and bar charts are the ones simulated fonts can't really test: hand-drawn noteheads and bar tops.

## Lesson plans and slides (Oct 27)

The plugin now plans the lesson around a worksheet and goes over it afterward, on the same free Claude for Teachers account. From one lesson file Claude writes, `lesson` makes a Word lesson plan, a PowerPoint deck to teach from (with speaker notes), a go-over deck that shows each worksheet question as printed and then answered and explained, and an answer key. After marking, `goover` makes a go-over deck from the class's results, most-missed questions first, with no student identifiable. Five example lessons (grades 3, 5, 6, 10, 11) build clean; the files pass the validator from Anthropic's own pptx and docx skills. Four fresh-agent trials (grade 4 math, grade 8 history, grade 9 biology, and a go-over from a marked class), an instructional coach's review, and a code review (17 bugs, all fixed) shaped the result. The log is [docs/lessons.md](docs/lessons.md).

## Top three for Day 2

0. **Try the plugin in real Cowork, on a Claude for Teachers account.** Check that it installs from the marketplace, that the cloud sandbox has numpy, scipy, Pillow, pypdfium2, reportlab, and python-pptx (0.6.22 or later), and that a scan can come in from Google Drive. Open a generated slides.pptx in PowerPoint and in Google Slides. Then mark a full class set (print 25-30 copies) and measure how much of the plan's usage it takes, with and without a subagent per question.
1. ~~**Pick the default model.**~~ Done Oct 26: Ben chose Opus 5.5 at low effort, about 3¢ a page. That's double Sonnet, and it departs from SPEC.md's "Default Sonnet 5.5". `--model claude-sonnet-5-5 --effort medium` still works for a cheaper run.
2. **Rubric-style keys.** Have each key say what full and partial credit need, as Q2's does. That should remove most "the key doesn't settle this" flags. The Make step (spec pipeline step 1, drafting from a lesson description) should write keys this way.
3. **Fix routing in review instead of reprinting.** Let the teacher type the ID for review-pile pages, so a smudged bubble doesn't send a page back. Then the Batch API for overnight runs at half price.
