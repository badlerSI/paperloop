# Teamwork format

Group work where students teach each other. One JSON file describes the activity; `PL teamwork FILE.json
--out DIR` writes `DIR/teamwork.pdf`: a page for the teacher (printed once, with the page numbers of
everything else), role cards, and what each group or student needs. Everything prints one-sided, in black
and white, on US Letter.

Group work raises achievement when two things are both true: the group shares a goal, and each student is
accountable alone. In Slavin's review of cooperative learning, methods with both averaged about +0.32 SD;
methods with one or neither averaged about +0.07. So every activity has:

- **A job for each student**, on a tent card: the job's name faces the group, and what to do and say faces
  the student. Jobs rotate, so no one is always the helper or the helped.
- **A task that needs more than one kind of ability** (`abilities`), so every student has something to
  give. When a student shows one, the teacher says so to the group, specifically. Cohen and Lotan found that
  this "assigning competence" raised participation of students who usually hang back, at no cost to
  anyone else.
- **A worksheet each student does alone at the end** (`worksheet`), scanned and marked like any other. It's
  what shows each student learned it, and it feeds progress. `teamwork` warns when there isn't one, or when
  it isn't beside the activity file.

| Example | Grade | Structure | Shows |
| --- | --- | --- | --- |
| `sci7-selection-teamwork.json` | 7 | lab | natural selection with dice and paper beetles, a dice table, a data table, tokens; exit sheet `sci7-selection-01` |
| `sci9-halflife-teamwork.json` | 9 | lab | radioactive decay with spilled paper "atoms" (blank backs work like coins); exit sheet `sci9-halflife-01` |
| `sci7-predators-teamwork.json` | 7 | lab | lynx and hares: a card toss over ten generations, tokens in two sizes, cards passed every 2 rounds; exit sheet `sci7-predators-01` graphs real fur-trade records |
| `sci8-atoms-teamwork.json` | 8 | lab | build atoms and ions from paper protons, neutrons, and electrons, a die picks the atom; exit sheet `sci8-atoms-01` (a table, misconceptions, a drawing) |
| `sci6-circuits-teamwork.json` | 6 | lab | series and parallel circuits from paper cards, a dice table of challenges; exit sheet `sci6-circuits-01` labels bulbs on two circuit diagrams |
| `sci7-density-teamwork.json` | 7 | lab | mystery blocks: density from mass and volume, then cut in half; exit sheet `sci7-density-03` |
| `sci7-greenhouse-teamwork.json` | 7 | lab | infrared tokens bounce through air layers on a printed `rows` board, low then high CO₂; exit sheet `sci7-greenhouse-01` graphs NOAA's Mauna Loa CO₂ measurements |
| `sci8-forces-teamwork.json` | 8 | lab | net force, mass, and acceleration with dice and controlled variables; exit sheet `sci8-forces-01` |
| `sci9-plates-teamwork.json` | 9 | lab | real USGS earthquake depths (`data`) plotted on a printed `graph` board, and Hawaii's island ages; exit sheet `sci9-plates-01` |
| `bio10-drift-teamwork.json` | 10 | lab | genetic drift and selection by drawing gene tokens from a cup, in two pairs; exit sheet `bio10-drift-01` |
| `math4-fractions-teamwork.json` | 4 | lab | a fraction race on a printed `number_line` board; exit sheet `math4-fractions-01` |
| `math3-area-teamwork.json` | 3 | lab | claiming rectangles on a printed `grid` board, with plain-word `roles`; exit sheet `math3-area-01` |
| `sci9-exoplanets-teamwork.json` | 9 | jigsaw | four ways to find planets, one expert sheet each, with what to teach and a check question; exit sheet `sci9-exoplanets-01` reads a real Kepler light curve |
| `ela4-garden-teamwork.json` | 4 | reciprocal | a story in four parts, with a stop to talk after each; exit sheet `ela4-garden-01` |
| `math6-ratios-teamwork.json` | 6 | pairs | twelve ratio questions, coach and player, a switch halfway; exit sheet `math6-ratios-02` |
| `chem10-moles-teamwork.json` | 10 | heads | eight mole questions for numbered heads; exit sheet `chem10-moles-01` |

## Structures, and what the evidence says

| `structure` | Group size | What students do | What prints | Evidence |
| --- | --- | --- | --- | --- |
| `lab` | 3-5 | An investigation in rounds: dice, tokens, measuring, a data table. Facilitator, Recorder, Skeptic, Reporter, and (in fives) Materials. | role cards, the task card (goal, steps, round boxes, dice table, data table), tokens | Slavin's conditions above; Complex Instruction for the roles and abilities. |
| `jigsaw` | 3-5 (one per part) | Each student learns one part with the other experts on it, then teaches it to their home group. | an expert card per letter; an expert sheet per part (teach box, teacher check, sketch box); home-group notes | Mixed: five recent classroom trials found no gain on learning. Use it with Slavin's Jigsaw II safeguards, which this version prints: the teacher checks each expert's box, everyone writes notes on every part, and the exit sheet covers all parts. Prefer a lab or pairs when learning the content is what matters most. |
| `reciprocal` | 4 | Reading in parts. After each part: the Summarizer, Questioner, and Clarifier lead, then the Predictor guesses the next part. | role cards; the reading in parts with a "stop and talk" bar after each | Gains in reading comprehension across studies (Rosenshine and Meister 1994: about +0.32 on standardized tests). |
| `pairs` | 2 | Peer tutoring in the PALS pattern: the coach asks, says what was right, and on a mistake says "Check it," then gives a hint, then shows how. Partners switch halfway. | coach and player cards; a sheet that folds so the player sees questions and the coach sees answers | Strong in elementary reading (Evidence for ESSA); weaker in math. Short, regular sessions. |
| `heads` | 3-5 | Numbered Heads Together: the group makes sure everyone can answer, then a die picks the number that answers. | number cards (tents); the questions page for the teacher | Little rigorous research on its own. Use it for quick review; the random pick makes every student get ready. |

## The file

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | Printed on every page. |
| `structure` | yes | One of the structures above. |
| `grade` | yes (or `grade_band`) | 2-12. Everything students read prints bigger in grades 2-3 (25%) and 4-5 (12%), and a reading's lines are kept to about 70 letters. |
| `subject` | no | Shown on the teacher's page. |
| `group_size` | no | Default 4 (2 for pairs). A jigsaw's group size is its number of parts. |
| `minutes` | no | Default 30: the group work. The teacher's page adds about 10 for the exit sheet. |
| `goal` | no | One sentence, what the whole group must be able to do. Write it so the group succeeds only if everyone can: "anyone in your group could explain...". |
| `abilities` | no | The kinds of ability the task needs ("counting carefully", "spotting a pattern", "explaining with evidence"). Name three or four, so no student is good at all of them and every student is good at some. |
| `materials` | no | What each group needs besides the printout: `["one die", "a cup", "scissors"]`. Listed on the teacher's page. |
| `launch` | no | What the teacher does with the whole class before groups start ("sketch the track and model the first move"), on the teacher's page. |
| `steps` | lab: yes | Lab: what the group does, in order, on the task card. Name which job does what where it matters. Other structures: extra directions for the teacher's "During" list ("finished? start again from card 1"). |
| `rounds` | no | Lab rounds (default 1): a box to check off for each; say "round" in the steps so they match. `rounds`, `rotate_every`, `dice`, `table`, `data`, `board`, and `tokens` print only in a lab; other structures refuse them. |
| `rotate_every` | no | Pass the role cards every this many rounds (default 1). Use 2 or 3 when a round takes a minute or two. |
| `dice` | no | `{"title": "...", "rows": [["1-4", "what happens"], ["5-6", "..."]]}`: a table on the task card. The first column widens to fit short labels ("Ocean", "1-4"); keep them under about 12 letters. |
| `table` | no | `{"title": "Our data", "columns": ["Spill", "Atoms left"], "rows": 8}`: a blank table on the task card for the Recorder (up to 6 columns, widths by heading). `teamwork` says if fewer rows fit. |
| `data` | no | Tables on their own pages, running onto more pages as needed: `[{"title": "...", "columns": [...], "rows": [[...], ...]}]`. Real data belongs here (with its source in the title or `sources`). Leave cells empty (`""`) for students to fill in: a long record sheet (rounds × points) works better here than in `table`, and rows with blanks are tall enough to write in. |
| `board` | no | A printed board, one page per group (or a list of boards): `{"kind": "grid", "cols": 18, "rows": 22}`; `{"kind": "number_line", "min": 0, "max": 2, "parts": 24}` (simpler fractions get taller marks; only whole numbers are labeled); `{"kind": "rows", "rows": ["Space", "Air", "Ground"]}` (labeled layers, splitting the page equally, each label at its top left); `{"kind": "ring", "stations": ["Ocean", "Cloud", "Land"]}` (a journey's stops); `{"kind": "graph", "xmin": 0, "xmax": 900, "xstep": 100, "ymin": 0, "ymax": 600, "ystep": 100, "xlabel": "...", "ylabel": "...", "y_down": true}` (axes to plot on; `y_down` counts down, for depth); `{"kind": "diagram", "width": 344, "height": 160, "shapes": [...]}` (a picture drawn with the worksheet's diagram shapes, scaled to fill the page: a skate track, a map, a food web). Any board takes a `title`. |
| `tokens` | no | `[{"label": "green beetle", "count": 40, "pattern": "plain", "size": 0.75}]`, per group. Each kind starts a new row. Patterns (`solid`, `dots`, `stripes`, `plain`, `checks`, `rings`) tell tokens apart on a black-and-white copy. `size` is the side in inches (0.5 to 4, default 0.75): a predator card can be bigger than its prey. A token has a blank back, so "lands blank side up" works like a coin. For a few pieces each student moves, use coins or erasers instead. |
| `roles` | no | Your own wording for the cards, replacing the built-in jobs: one entry per card, in order, each `{"name": "Sum It Up", "jobs": ["Tell the big idea."], "say": ["It's mostly about __."]}`. Use it for young students ("Sum It Up", "Ask", "Fix It", "Guess" for reciprocal in grade 2-3) or a subject's own jobs. Reciprocal roles are listed in the order they speak after each part, the last one guessing what comes next. |
| `parts` | jigsaw, reciprocal: yes | Jigsaw: 3-5 parts, each `{"title", "text", "teach": ["2-3 things to teach"], "check": "a question for the home group"}`; about 150-200 words a part (quote included) fits beside the teach box, and `teamwork` warns past that. Reciprocal: 2-8 chunks of the reading, each `{"text"}` with an optional `title`. Either kind of part can also have: `cite` (the same as a passage's: `teamwork` checks the license and prints the credit line), or `source` (a credit line as written, for text written for the activity); `quote` and `quote_source` (a primary source, set apart under the text); and `words` (`[{"word": "alliance", "means": "an agreement to help each other"}]`, a key-words line under the text, for everyone and especially students still learning English). Parts adapted from CommonLit, ReadWorks, CK-12, OpenStax, Newsela, or Khan Academy are refused, as passages are. `teamwork` flags a reading more than two grades above the class. |
| `cards` | pairs, heads: yes | `[{"q": "...", "a": "..."}]`. Pairs: 12 a page, so 12 or 24 work well; the switch line falls halfway. Heads: as many as the time allows. |
| `worksheet` | no, but expected | The `assignment_id` of the exit sheet each student does alone, made in the same folder. Its versions (plain wording, sentence starters, a home language) are handed out as usual and scanned together. |
| `class_size` | no | The number of students: the teacher's page then says how many groups, and of what sizes. |
| `versions` | no | The same activity in other words, for the students who need them: `[{"id": "plain", "name": "Plain English", "parts": [...]}, {"id": "es", "language": "es", "parts": [...], "roles": [...]}]`. A version replaces any of `parts` (one entry per part, each with just the fields it changes: `title`, `text`, `teach`, `check`, `words`), `roles` (one per card: `name`, `jobs`, `say`), `steps`, and `goal`. Plain English, and languages in the Latin, Greek, or Cyrillic alphabets (Spanish, Vietnamese, Haitian Creole, Russian...), print as extra pages after everyone's, with the pages' own words ("Teach box", "Group task", "Rounds:") in the version's language: built in for Spanish, and for any other language give `labels`, the same keys as the English (`intro`, `teach_box`, `your_job`, `task`, `rounds`, `close`, and the rest; `teamwork` lists them if one is wrong), keeping each `{placeholder}`. Arabic, Chinese, Bengali, Burmese and other scripts these pages can't shape go in a Word file, `versions/<id>.docx`, which Word and Google Docs print correctly. As with worksheets, a language Claude translates less reliably asks for a bilingual adult's check (`reviewed_by`), and a plain version is checked to read easier than the original. |
| `listen_for` | no | What the teacher listens for while walking around: the talk that shows understanding and the misconception to catch. |
| `debrief` | no | How to wrap up with the whole class. |
| `sources` | no | Where the activity's idea, facts, and data came from, with credit (see below). |

## Versions: the same work, in words each student can read

A version changes the words, never the work: the same parts, the same jobs, the same exit sheet. A student
with the Spanish expert sheet still teaches the home group (in English or Spanish), and a student with the
plain-English reading still takes their turn as Summarizer. That keeps groups mixed and keeps every student
inside the group's talk, where most of the learning happens. Write a plain version in short sentences and
everyday words, keeping every number and idea; translate key words into `words` so they print on the sheet.

## Team points

STAD (Student Teams-Achievement Divisions, Slavin) scores a team by how much each member improves on their
own past work, so every student can add as much to the team as anyone. After the exit sheet is marked, run
`PL teampoints "<class folder>" --worksheet <exit sheet id>`. It reads the newest `progress/groups-*.json`
(or `--groups`), and gives each student improvement points from their exit sheet against their average on
earlier marked worksheets:
- 30 for a perfect paper, or more than 10 points above their own usual;
- 20 for their usual to 10 above, or no earlier work;
- 10 for up to 10 below;
- 5 for further below.

A team's score is its members' average; absent students (or a page with nothing on it) don't count against
it, and a team with only one exit sheet posts "-", since one student's score alone would show. Every marking of
the exit sheet counts: two periods, or a make-up marked later. It writes
`progress/team-points.pdf` to post (teams and points, no names or IDs) and `progress/team-points.md` for the
teacher (each class ID's points). Celebrate every team that improves; don't rank students.

## Writing a good activity

- **The exit sheet comes first.** Decide what each student must show alone, write that worksheet, then
  design the group work that gets everyone there. One page in grades 4-12. In grades 2-3, big print fits
  about three questions a page: use two pages, or fewer questions, rather than squeezing writing space.
- **A reading's exit sheet needn't reprint it.** Students keep the reading from the group work; say so in
  the worksheet's instructions ("Use your reading"), and ask questions it answers.
- **Make the task need the group.** A task one strong student can do alone becomes one student's task.
  Labs need hands (rolling, counting, recording at once); jigsaws need every expert; heads needs everyone
  ready.
- **Give the words, not just the job.** Each role card has sentence starters ("How do you know?", "Let me
  read that back"). They help everyone, and they're how students still learning English join the talk. Ask
  for elaborated answers, not bare ones: explaining helps the explainer and the listener; being handed an
  answer doesn't (Webb).
- **Correct like a coach.** In pairs, the coach says exactly what was right, and on a mistake says "Check
  it" and waits, then gives a hint, then shows how and has the player say it back. For fact practice, write
  the hint in the answer: "56 (7 × 7 = 49, plus 7)".
- **Check questions check understanding.** A jigsaw `check` should need the idea, not repeat a sentence:
  "If one dip is four times deeper than another, how do the planets' sizes compare?"
- **Keep the jigsaw parts even.** Each expert reads about the same amount and teaches for about 3 minutes.
- **Young students learn one job at a time.** In grades 2-5, teach one reciprocal job a day with the whole
  class before groups use all four, and use `roles` for plainer names.
- **Real data beats made-up data** when it's free to use: NASA light curves, USGS earthquakes, NOAA
  measurements. Say on the sheet that it's real, and credit it in small print.
- **Check facts against a second source.** Wikipedia, and Simple English Wikipedia especially, can be wrong
  or vandalized in the revision you fetch. Check dates, names, and numbers before they go on an expert sheet,
  and present a textbook framework (such as "four causes") as a way historians organize causes, not settled
  fact.
- **Students still learning English** get the same activity: sentence starters on every card, `words` in
  each part, a sketch box on each expert sheet, and the exit sheet's versions. A shared jigsaw letter (two
  students on one part) is a good spot for a student new to English.

## Ideas from simulations and online labs

Many good labs live on screens: PhET, NOVA Labs, HHMI BioInteractive, NASA, Concord Consortium, NetLogo.
Their ideas (a model to play with, a question to investigate) and the facts and data they use aren't
anyone's property, and paper often does them well: dice for chance, tokens for populations, a printed graph
for real data. Write the activity, its text, and its questions in your own words, and say in `sources` what
inspired it. Copy or adapt someone's text, questions, or images only when the license allows it:

| Source | Use |
| --- | --- |
| NASA, USGS, NOAA (US government) | Text, images, and data are free to use. Credit the agency ("Credit: NASA"); don't imply it endorses the activity, and leave out logos and anything credited to someone else. JPL images: "Courtesy NASA/JPL-Caltech". |
| Kepler and TESS data (MAST), NASA Exoplanet Archive | Data are free to use. Credit "NASA Kepler mission, via MAST" and the archive. |
| PhET (University of Colorado Boulder) | Ideas only for the simulations: since March 2026 new ones are CC BY-NC, and a NonCommercial license doesn't fit every school's use. Teacher-written activities in PhET's activity database are CC BY 4.0 and may be adapted with the author's credit and "Adapted". Don't use the PhET name or logo to promote anything. |
| OpenSciEd | Middle school units are CC BY 4.0 (adapt with credit); elementary and high school are NonCommercial: ideas only. |
| Concord Consortium, NetLogo models, HHMI BioInteractive, The Wonder of Science | NonCommercial (some ShareAlike): ideas only. |
| NOVA Labs (WGBH/PBS), Gizmos, NAAP, Zooniverse | No open license: ideas only, in your own words. |

## Groups

`PL groups "<class folder>" --size 4 --structure <structure>` makes groups from the class's marked work, by
class ID only, and writes `progress/groups-<structure>.md` (and `.json`) for the teacher, with `-similar`
added for similar groups (one file per kind, so pairs don't replace lab groups). Add `--skill "..."` to sort
by one skill, and `--roster ids.csv` to include students with nothing marked yet (or to make random groups
before anything is marked). `--structure game` makes groups with no jobs, never above `--size`, for a card or
board game. The one exception is a two-player game (`--size 2`) with an odd number of students: one pair becomes
three who take turns, so no one plays alone. Students are ranked by all their marked work (every point counts the same) or by the one skill,
then:

- **Mixed** (the default, for labs, jigsaws, reading, and review): dealt out back and forth, so every group
  gets some from each part of the range. Students who are behind learn more in mixed groups; students who
  are ahead do as well in either when the group works well (Lou et al. 1996; Webb).
- **Pairs** (`--structure pairs`): the PALS way. The ranked class is split in half and the halves pair up in
  order, so partners are apart but close enough that the coach can help.
- **Similar** (`--similar`, for practicing one skill): neighbors in the ranking together, so the teacher can
  give each group what it needs next. The file lists them from the highest recent scores to the lowest, so
  the teacher knows which group to pull to their table. Students in the middle gain most from these.
  Regroup often.

Groups come out as even as the structure allows, never above its limit: labs and numbered heads 3-5, a
reading group 3-5 (with three, one student takes two jobs), pairs 2 or one trio, a jigsaw home group with every
letter and at most one shared. Extra students double up on a job that has a printed card. First-round jobs are
dealt at random, not by score; `--seed 2` (any other number) deals them again. Students with no marked work
(on `--skill`, if given) are placed in the middle of the ranking, and the groups file lists them.

The groups file is for the teacher. Don't say why a group is mixed or similar, and don't post it.
