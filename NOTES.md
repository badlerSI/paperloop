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

## Top three for Day 2 (provisional until the handwriting run)

1. **Run the sweep on Ben's handwriting** and pick the default model and effort from it, plus the confidence threshold from its flag rate.
2. **Rubric-style keys.** Have each key say what full and partial credit need, as Q2's does. That should remove most "the key doesn't settle this" flags. The Make step (spec pipeline step 1, drafting from a lesson description) should write keys this way.
3. **Fix routing in review instead of reprinting.** Let the teacher type the ID for review-pile pages, so a smudged bubble doesn't send a page back. Then the Batch API for overnight runs at half price.
