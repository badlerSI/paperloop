# Paper Loop: Build Spec for Claude Code

Oct 25, 2026 · @Benjamin Adler

Exported from the Claude Doc at https://claude.ai/artifact/B4BYLQ9Z6z4gd1SX76Xz1S. That doc is the source of truth; refresh this copy when it changes.

Hand this to Claude Code: export this tab as Markdown, save it as SPEC.md in a new repo, and say "Read SPEC.md and start Day 1."

## Goal and v0.1 acceptance criteria

Build a free, open-source loop that turns a school copier into a feedback machine: print worksheets, scan the class stack, get marked-up paper back the next morning.

v0.1 is done when:

- [ ] One command generates a printable worksheet PDF (QR code per page, student ID box, numbered answer boxes), plus an answer key and a layout file.
- [ ] One command takes a scanned class-set PDF (any page order, duplex) and outputs one print-ready PDF in student-ID order, with comments stamped beside each answer box.
- [ ] Each page gets one strength and at most two fixes. The grade is off, on the back page, or exported to CSV only, per a setting.
- [ ] Low-confidence answers are listed for teacher review before anything prints.
- [ ] No student names leave the machine; only ID numbers appear on paper.
- [ ] It runs on a teacher's laptop with a district-owned Anthropic API key.

Scope limits for v0.1: one subject (middle school science short answer), answers in boxes, no essays, English only.

## The pipeline

Eight steps, in order. The copier only scans and prints; everything else runs on the laptop.

1. **Make.** The teacher describes the lesson; the model drafts questions and an answer key. A script lays out the PDF and writes `layout.json` with every box's position.
2. **Print.** Normal print queue. Students write an ID number, not a name.
3. **Scan.** The stack goes through the copier's duplex feeder at about 300 dpi grayscale, to a Drive folder or email ([PaperCut scan-to-cloud](https://www.papercut.com/support/resources/manuals/ng-mf/applicationserver/topics/device-mf-scanning-integration-introduction.html)).
4. **Ingest.** Split pages, deskew, read the QR code (assignment, page) and the ID box. Unreadable pages go to a review pile; never guess.
5. **Mark.** Crop each answer box and send it to the model one region at a time, with the key. Region-level grading reduces cross-problem interference and hallucination ([paper](https://arxiv.org/pdf/2603.00895v1)).
6. **Review.** Show the teacher only flagged items: low confidence, unreadable, or an ambiguous key.
7. **Render.** Stamp comments beside each box on the original scan, add a strength and next-step box, and place the grade per the setting.
8. **Print.** One PDF, sorted by student ID, ready to hand back.

## Build on what exists

Don't start from zero: four existing pieces cover most of the loop.

| Component | What we use it for | License |
| --- | --- | --- |
| [Plom](https://pypi.org/project/plom/) | QR-coded papers, scan sorting, ID handling, marking workflow. Built for university multi-marker exams; evaluate as backbone vs. design reference on Day 1 | AGPL-v3 |
| [Anthropic k12-teacher-skills](https://github.com/anthropics/k12-teacher-skills) | Skill structure and evaluation rubrics; lesson planning and differentiation for the Make step | Apache 2.0 |
| [Learning Commons Knowledge Graph](https://learningcommons.org/news/scaling-proven-learning-practices/) | Machine-readable standards for all 50 states, math learning components, open Evaluators code | Open; check each dataset |
| [PaperCut MF Integrated Scanning](https://www.papercut.com/support/resources/manuals/ng-mf/applicationserver/topics/device-mf-scanning-integration-introduction.html) | Scan to Google Drive or OneDrive with zero copier integration | Commercial; already in many districts |

## Stack, repo layout, and licenses

Python 3.11+, a command-line tool first, a small local web page later.

- **Layout and stamping:** reportlab to draw worksheets and comment overlays; pypdf to merge overlays onto scans.
- **Scans to images:** pypdfium2.
- **QR, deskew, crops:** OpenCV (QR detector plus perspective transform); `qrcode` to generate codes.
- **Model calls:** Anthropic Python SDK. Default Sonnet 5.5; test Haiku 5.5 for cost; use batch processing for overnight runs at 50% off ([pricing](https://claude.com/pricing)).
- **Schemas:** pydantic models for layout, results, and feedback. **CLI:** typer.

```
paperloop/
  SPEC.md
  paperloop/
    make.py      # worksheet PDF + layout.json + key.json
    ingest.py    # split, deskew, QR, ID box
    mark.py      # crops -> model -> feedback.json
    review.py    # flagged items for the teacher
    render.py    # stamp comments, grade setting, sort by ID
    schemas.py
  prompts/mark_region.md
  tests/fixtures/   # synthetic scans + hand-labeled truth
  cli.py
```

License: Apache 2.0 for the core, matching Anthropic's teacher skills. Keep AGPL code (including anything borrowed from Plom) out of the core, in a separate adapter, and check every dependency's license before adding it.

## Data formats and marking rules

The template decides where everything goes, so the model never has to guess coordinates. Box rects are PDF points, [x0, y0, x1, y1].

```json
{
  "assignment_id": "sci7-density-01",
  "pages": [
    {"page": 1, "qr": "sci7-density-01|p1",
     "id_box": [72, 700, 220, 740],
     "boxes": [
       {"q": 1, "rect": [72, 560, 540, 640],
        "prompt": "Why does ice float on water?",
        "key": "Ice is less dense than liquid water.",
        "points": 2}
     ]}
  ]
}
```

The model returns one record per box, plus a page summary:

```json
{"q": 1,
 "transcription": "ice is lighter then water",
 "uncertain_words": ["then"],
 "verdict": "partial",
 "comment": "Right idea. Say less dense, not lighter.",
 "confidence": 0.82}
```

Marking rules for `prompts/mark_region.md`:

1. Transcribe literally first. Never fix spelling or fill in what the student meant.
2. Mark unreadable words as uncertain; never guess.
3. Judge against the key, accepting correct answers in the student's own words.
4. Comments under 15 words, at the student's grade level, specific, no generic praise.
5. Per page: one strength, then at most two specific fixes ([Guskey](https://www.edweek.org/education/opinion-grades-versus-comments-what-does-the-research-really-tell-us/2019/06)).
6. Flag anything under 0.8 confidence for teacher review (a starting threshold; tune it in testing).
7. Comment on the work, never on the student as a person.

## Day 1 tasks for Claude Code

Goal for the day: one worksheet printed, filled in by hand, scanned, and returned marked up, end to end, even if it's ugly.

- [ ] Create the repo with an Apache 2.0 license and the layout above; commit SPEC.md.
- [ ] Spike Plom, capped at one hour: install it, generate a QR-coded paper, read the scan and marking docs. Write a half-page note: adopt as backbone, wrap with an adapter, or use as design reference only.
- [ ] `make.py`: render a two-page sample worksheet (five short-answer questions on density) with QR codes, an ID box, and numbered answer boxes; write layout.json and key.json.
- [ ] Ben prints four copies and fills them in by hand: one clean, one messy, one with crossed-out answers and misspellings, one blank. Scan them as one duplex PDF.
- [ ] `ingest.py`: split, deskew, read each QR code and ID box; print a page map.
- [ ] `mark.py`: send each crop to Sonnet 5.5 with the marking rules; save feedback.json; log tokens and cost per page.
- [ ] `render.py`: stamp comments beside each box, add the summary box, grade off by default; output one PDF sorted by ID.
- [ ] Ben prints the output and reviews it on paper, noting every misread and every wrong or unhelpful comment.
- [ ] Write NOTES.md: what broke, cost per page, and the top three fixes for Day 2.

## Test plan and metrics

The failure that matters most is silent autocorrect: a wrong answer read as right. Measure it first. Targets below are starting points to revise after Day 1.

| Metric | How measured | Starting target |
| --- | --- | --- |
| Page routing | Pages matched to the right student and page by QR and ID | 100%, or flagged |
| Silent autocorrect | Misspelled words transcribed as correctly spelled | 0 on the test set |
| False "correct" | Wrong answers marked correct | 0 on the test set |
| Transcription accuracy | Words matching hand-labeled truth | Track; no target yet |
| Flag rate | Share of boxes sent to teacher review | Under 15% |
| Comment placement | Comments beside the right box | 100% |
| Cost per page | Logged tokens times list price | Under 3 cents on Sonnet 5.5 |
| Turnaround | Scan in to print-ready PDF, 30 students | Under 10 minutes |

Test sets, in order: Ben's own handwriting (synthetic), then anonymized real samples with teacher consent, then a blind comparison of AI comments against a teacher's comments on the same pages.

## Privacy and guardrails

Only cropped answer boxes ever leave the laptop. Everything that identifies a student stays local.

- **IDs, not names.** Use a bubble grid for the student ID so it's read locally with OpenCV, never by the model. The ID-to-name roster lives only on the teacher's laptop.
- **Crop before sending.** The model sees answer boxes only, never the header, margins, or ID area.
- **District-owned key** under Anthropic's [US K-12 terms](https://anthropic.com/legal/k12-terms) and [K-12 data processing agreement](https://anthropic.com/legal/k12-dpa). Confirm they cover API use before any real student work.
- **Teacher prints everything.** Flagged items get reviewed first; nothing reaches a student without the teacher handling it.
- **Delete by default.** Scans and crops are deleted after printing; keep only de-identified feedback for evaluation, if anything.
- **Out of scope:** drafting IEPs, behavior plans, or discipline decisions (delivering accommodations already in a plan is in scope; see v0.2). AI tools for those were flagged as high risk ([source](https://stacker.com/stories/technology/ai-teacher-tools-display-racial-bias-when-generating-student-behavior-plans)).
- **Day 1 uses Ben's handwriting only.**

## Request to district IT

Copy, fill the brackets, and send. It asks for one scan action and one folder permission, nothing else.

**Subject:** Request: copier scan action for a paper feedback pilot

> Hi [IT contact], I'd like to pilot a paper-based feedback workflow in my [subject] classes this [semester]. Students do worksheets on paper; I scan the class stack on the copier, and a tool on my laptop uses AI to write short comments beside each answer, which I review and print. Could you add a one-touch scan action on our copier (through PaperCut, if we use it) that sends duplex, 300 dpi grayscale PDFs to a shared Google Drive folder called "Feedback In," and approve the app's access to that folder? Students write ID numbers, not names; only cropped answer boxes go to the AI, and I'd use a district-owned Anthropic account under its K-12 terms and data processing agreement, once you or legal confirm that's acceptable. No new devices or student accounts are needed, and I'm happy to show you a demo. Thanks, [Name]

## v0.2: early reading, parents, and accommodations

Three additions close the biggest gaps: kids who can't read the worksheet yet, parents who don't know where their kid stands, and accommodations that rarely happen in practice.

### K-1 reading track

- **Humans lead.** Reading Corps-style tutors, AmeriCorps members without teaching backgrounds, produced effects of 0.85 SD in kindergarten and 0.81 in first grade ([source](https://nssa.stanford.edu/studies/evaluating-effectiveness-volunteer-one-one-tutoring-model-early-elementary-reading)).
- **The loop supports them.** It prints decodable passages matched to each student's phonics skill (stored in the QR code), plus a one-line check sheet the tutor marks: words read correctly, errors by sound. Scanned check sheets set the next passage.
- **No AI listening yet.** Speech models are weakest on ages 4 to 6, around 34% word error rate versus about 5% for adults, and worse in noisy rooms ([source](https://the-learning-agency.com/guides-resources/closing-the-child-speech-recognition-gap-evidence-limitations-and-paths-forward/)). Revisit with a kid-tuned model later.

### Monthly parent summary

- One page per student, in plain language and the family's home language: what they can do, what they can't do yet, and one specific thing to do at home.
- Why it matters: 88% of parents believe their child is at or above grade level in reading, and parents who know their child is behind act on it ([Gallup and Learning Heroes](https://gallup.com/file/analytics/514025/B-flation_Gallup_Learning%20Heroes_Report.pdf)).
- Built from feedback.json, reviewed by the teacher before printing, and never compares a child to classmates.

### QR-based accommodations

- Each student's code maps to an accommodation profile stored only on the teacher's laptop: larger print, fewer items, a word bank, chunked steps, extra writing space.
- make.py prints a variant per student. The model sees only a generic variant code (for example, reduced items plus word bank), never the IEP.
- A delivery log records which variant each student got on each assignment, so accommodations are documented, not just promised.
- The teacher or case manager sets profiles; the tool never drafts or changes an IEP.

v0.2 is done when:

- [ ] A decodable passage and tutor check sheet generator works end to end.
- [ ] A monthly parent summary PDF prints in English and one other language.
- [ ] Per-student variants print from local profiles, with a delivery log.

## Open decisions for Ben

None of these block Day 1; decide them as results come in.

- [ ] Project name ("Paper Loop" is a placeholder).
- [ ] Plom as backbone, adapter, or design reference only, after the Day 1 spike.
- [ ] Apache 2.0 for the core: confirm.
- [ ] Default grade setting: off, back page, or CSV only.
- [ ] First subject and grade band (this spec assumes middle school science).
- [ ] Ship as a CLI only, or also as a Claude Skill teachers can run inside Claude for Teachers.
- [ ] Pilot API key: yours for synthetic tests; a district's for real student work.
