# Research notes: languages, accommodations, evidence, ed tech, open content

Gathered Oct 27, 2026 by two research agents working from primary sources where they could. Items marked
(nv) are well-known figures the agents didn't re-verify. These notes back the design of versions, the
SaaS Reaper map, and the walkthrough.

## Home languages of US English learners

**Source.** OELA fact sheet, SY 2022–23, Jan 2026 (EDFacts): https://ncela.ed.gov/resources/fact-sheet-top-ten-languages-of-english-learners-january-2026
- 5,558,716 English learners in total.
- Each count only includes states where that language was in the state's top five, so smaller languages are undercounted.
- Cross-check: NCES Digest 204.27, fall 2021, which counts every speaker but lists only 15 languages: https://nces.ed.gov/programs/digest/d23/tables/dt23_204.27.asp

**Top 20 languages**

| # | Language | Count | Share of English learners | Trend |
|---|---|---|---|---|
| 1 | Spanish | 4,229,448 | 76.1% | |
| 2 | Arabic | 133,288 | | |
| 3 | Chinese | 94,016 | | |
| 4 | Vietnamese | 71,308 | | declining |
| 5 | Portuguese | 62,171 | | doubled since 2017–18 |
| 6 | Russian | 49,047 | | |
| 7 | Haitian Creole | 31,184 | | |
| 8 | Hmong | 28,404 | | declining |
| 9 | Urdu | 24,428 | | |
| 10 | Pashto | 23,537 | | new: 1,670 in 2020–21 |
| 11 | French | 23,308 | | |
| 12 | Korean | 23,088 | | |
| 13 | Persian (Dari/Farsi) | 22,461 | | new |
| 14 | Ukrainian | 20,396 | | new |
| 15 | Swahili | 19,811 | | |
| 16 | "Cushitic (Other)" | 16,112 | | likely Somali/Oromo under a generic code |
| 17 | Nepali | 15,311 | | |
| 18 | Tagalog | 15,063 | | |
| 19 | Somali | 15,003 | | |
| 20 | Telugu | 14,589 | | |

**Next most common:** Bengali, Navajo, Karen, Marshallese, Cape Verdean Kriolu, Mayan languages, Amharic, Burmese and Chuukese. Chuukese is the top English-learner language in Hawaii (18%).

**Translation quality**
- **Machine translation:** GPT-class models match traditional machine translation for high-resource languages and trail it for low-resource ones (Robinson et al. 2023, arXiv 2309.07423).
- **Haitian Creole:** GPT-4 discharge instructions had potentially significant errors 33% of the time, against 8% for professionals (Brewster et al., Pediatrics 2024).
- **Not benchmarked:** Hmong, Karen, Marshallese, Chuukese and Mayan languages aren't in FLORES-200.
- **Human post-editing** matched or beat professional translation (npj Digital Medicine 2025).
- **Paper Loop's policy:** "high" quality languages print with a spot-check. "Medium" and "low" need a bilingual adult's review (`reviewed_by`). "Low" stays at key words and directions until reviewed.

**Scripts that need a shaping engine to print** (Paper Loop puts these on the Word page): Nepali, Telugu, Bengali, Punjabi, Gujarati (Devanagari and other Indic scripts), and Burmese and Karen (Myanmar script). Arabic-script languages (Arabic, Urdu, Pashto, Dari/Farsi) are shaped by `script.py`. Urdu and Pashto print in a plain style, and a few Pashto and Urdu letters print unjoined.

**Literacy and family-language notes**
- **Hmong:** many families weren't literate in any script.
- **Pashto:** speakers often read Dari better.
- **Somali Bantu:** families speak Maay Maay or Kizigua, which are largely unwritten.
- **Swahili:** many Congolese families prefer Kinyarwanda, Kirundi, Lingala or French.
- **Chinese:** ask Simplified or Traditional.
- **Ukrainian:** never default to Russian.

## English-learner accommodations: what works

**Effect sizes** (Kieffer et al. 2009, doi:10.3102/0034654309332490; 2012 update ED537635; Pennock-Roman & Rivera 2011; Li & Suen 2012; Rios et al. 2020):

| Accommodation | Effect size | Notes |
|---|---|---|
| English dictionary or glossary | g = .15–.18 | The only significant one in 2009 |
| Bilingual word-to-word glossary | g = −.03 | Not significant |
| Native-language test version | .46 | Not significant. It helps only students taught in that language; English-taught students did worse (Hofstetter 2003) |
| Side-by-side bilingual booklet | −.01 | |
| Simplified English (Abedi) | .14 | Significant. Biggest for intermediate English learners and low-level math. Universal design |
| Extra time | .23 | |
| Read-aloud | .09 | Not significant |
| Overall | .16 | Low-proficiency learners gain more; non-English-learners gain .01 |

**Translated directions:** no effect studies; a designated support at CCSSO and Smarter Balanced, and low-risk.

**WIDA levels:** 1 Entering, 2 Emerging, 3 Developing, 4 Expanding, 5 Bridging, 6 Reaching. Scaffolds run at least through level 4: sensory, graphic, interactive, and home language.

**Other evidence**
- **Cognates** help Spanish, Portuguese, French and Haitian speakers (Carlo et al. 2004).
- **Visuals and organizers** have "strong" evidence (IES practice guide, Baker et al. 2014).

## IEP/504: accommodation or modification

**CCSSO Accessibility Manual 2016, p. 20.** Modifications "change, lower, or reduce" expectations. Its examples: fewer objectives, only the easiest items, **removing answer options**, and **hints or clues**. Modifications aren't allowed on state tests, and families must be told.

**What Paper Loop treats as modifications:** hints, worked examples, laid-out steps, and fewer choices.

**Accommodations:**
- large print;
- spacing;
- chunking (per_page);
- graph paper;
- translated directions or glossary;
- plain-language text when language isn't what's being tested;
- sentence frames and blank organizers;
- reference sheets when fluency isn't the standard.

**Better than fewer choices:** write 3-option items for everyone. There is no psychometric loss (Rodriguez 2005).

**Evidence notes**
- **Dyslexia fonts don't help.** OpenDyslexic (Wery & Diliberto 2017) and Dyslexie (Kuster 2018) showed no gain; Marinus 2016 traced Dyslexie's edge to spacing.
- **Letter and word spacing:** fewer errors, no speed gain (Zorzi 2012; Hakvoort 2017). Wider letters without wider words slows reading (Galliussi 2020).
- **Large print:** strong for low vision, mixed otherwise (Hughes & Wilkins 2000; Katzir 2013).
- **Extended time** helps everyone; students with disabilities somewhat more (Sireci 2005).
- **Read-aloud** helps students with disabilities more, especially in reading, but it changes what reading tests measure (Li 2014; Buzick & Stone 2014).

## Ed tech: what the subscriptions are, and what the evidence says

**Usage**
- **EdTech Top 40.** Instructure/LearnPlatform tracks engagement, not effectiveness, from an opt-in sample (https://www.instructure.com/sites/default/files/pdf/2025_edtech-top-40-ebook.pdf). A district accessed about 2,982 distinct tools in 2024–25, and each student used 48.
- **Courseware leaders:** i-Ready, IXL, McGraw Hill, Amplify, Lexia, CommonLit, HMH, DeltaMath, ReadWorks, CK-12.
- **Supplemental leaders:** Epic, Nearpod, Khan, Prodigy, Code.org, BrainPOP.
- **Assessment and game leaders:** Kahoot, Blooket, Quizizz, Gimkit, Pear Deck, Quizlet.

**Unused licenses**
- Glimpse K12 (2019): 67% of licenses unused on average (vendor analysis, not peer reviewed).
- LearnPlatform (2017): 65% effectively unused.
- BrightBytes/Baker (2018): a median 70% of over-bought licenses never used, and 97.6% never used intensively.

**Effects of the leading products**

| Product | Evidence | Effect |
|---|---|---|
| i-Ready | Vendor quasi-experimental study | Math +0.23, reading +0.12 |
| IXL | RCT, one semester | Star +0.13; state test +0.03 (not significant) |
| Lexia | Vendor-sponsored RAND study | +0.11 |
| Lexia | Independent EEF RCT | ≈ +0.08 |
| Zearn | Independent RAND RCT, 64 schools | STAAR +0.07 (not significant) |
| DreamBox | | Grades 4–5 +0.03 |
| MAP Growth | Independent RCT | No reading impact |
| Achieve3000 secondary | | +0.29 (one study) |
| Raz-Plus | Vendor RCT | +0.14 |
| Prodigy | Vendor correlational | About 888 questions per STAAR scale point |

**No rigorous evidence found:** Kahoot, Blooket and Gimkit (meta-analyses of small studies show novelty effects); Nearpod, Pear Deck, Epic, Newsela, CommonLit, ReadWorks, BrainPOP, Flocabulary, Reflex, XtraMath, Gizmos, Mystery Science, Generation Genius, Seesaw and Duolingo K-12. They have none, or only vendor correlational studies or logic models.

**ASSISTments**
- Online homework with immediate feedback and a teacher report of common errors.
- Independent RCT, 43 Maine schools, 2,850 seventh graders: +0.18. Low achievers gained most (Roschelle et al. 2016, doi:10.1177/2332858416673968).
- Replication, 63 North Carolina schools: +0.10 on the next year's state test (Feng et al. 2024).
- **This is the mechanism Paper Loop copies on paper:** marked homework, a report of common wrong answers, and a go-over.

**J-PAL (Escueta et al. 2020, JEL):** computer access alone doesn't raise scores. Self-paced skill software is promising in math (Mindspark +0.37 in India). The US IES study of 16 products found no effects (Dynarski 2007).

## Learning techniques with the strongest evidence

**Dunlosky et al. 2013** rates high utility for practice testing and distributed practice; moderate for elaborative interrogation, self-explanation and interleaving; low for highlighting and rereading.

| Technique | Evidence |
|---|---|
| Retrieval practice | Classroom quizzing g = 0.50 (Yang et al. 2021, 222 studies) |
| Spacing | d ≈ 0.46. Best gap: about 20–40% of the time until the test, for a one-week horizon |
| Interleaving | Rohrer 2015: d = 0.79 at 30 days. Rohrer 2020, cluster RCT of 54 classes: 61% vs 38%, d = 0.83. Both on **paper worksheets** |
| Worked and faded examples | Moderate evidence (Pashler IES guide). Examples help novices, not experts (expertise reversal) |
| Feedback | Wisniewski et al. 2020: d = 0.48; high-information feedback d = 0.99. Kluger & DeNisi 1996: over a third of feedback interventions **lowered** performance; self-level praise is weakest |
| Comments vs grades | Butler 1988: comments alone beat grades and grades plus comments. A grade beside a comment cancels the comment |
| Mastery learning | Kulik 1990 ≈ 0.52 on experimenter tests; Slavin 1987 found little on standardized tests |
| Peer tutoring | PALS Reading (whole class, grade 1): E4E Strong, +0.23, no technology |
| High-dosage tutoring | 0.29 SD (Nickow et al. 2024); a third to half that at scale |
| Student-generated questions | 0.36 on standardized tests, 0.86 on experimenter tests (Rosenshine et al. 1996) |
| Paper vs screens | Paper wins for informational text: g = −0.21 (Delgado 2018), g = −0.25 (Clinton 2019). The gap is growing; readers also judge their own comprehension better on paper |
| Math fact fluency | Timed activities: Strong (WWC practice guide 2021); drill with modeling works on paper |
| Games | Designed learning games d = 0.29 (Wouters 2013), g = 0.33 (Clark 2016). Combining them with instruction, repeated play and groups helps. Quiz games are not the same thing |
| Handwriting vs laptops | Small or uncertain longhand advantage (Urry 2021 replication null; Flanigan 2024 g ≈ 0.25) |

## Free human-written content: licenses

**Wikipedia and Simple English Wikipedia (CC BY-SA 4.0)**
- An adapted passage needs:
  - credit to "Wikipedia contributors" with an oldid permalink;
  - the license and its URL;
  - a statement of what changed.
- The adapted passage stays CC BY-SA. The teacher's own questions beside it don't need to be.
- **API:** `api.php?action=query&prop=extracts|revisions&explaintext=1&titles=X&rvprop=ids|timestamp&redirects=1&format=json&formatversion=2`. It needs a descriptive User-Agent. Anonymous use is limited to 10 requests a minute.

**Free to adapt**
- US federal works: NASA, NOAA, USGS, Library of Congress (check each item).
- Wikisource.
- Project Gutenberg, with its license header and references stripped.
- Smithsonian items marked CC0.
- Wikimedia Commons files, per their own licenses.
- IM K–12 Math first edition (CC BY).
- OpenStax titles obtained under CC BY.

**Noncommercial only:** OpenStax (CC BY-NC-SA since 2026-04-22), IM v.360, EngageNY/Eureka, Core Knowledge and MIT OCW, all NC-SA or NC.

**Don't adapt:** CommonLit, ReadWorks and CK-12 forbid rewriting, and CK-12 and CommonLit also forbid generative-AI use. OpenStax also bars AI ingestion without written permission. For public-domain texts, use Gutenberg or Wikisource rather than these.

## Open labs and group work (Oct 27)

Checked Oct 27, 2026; the details and what they changed are in [teamwork.md](teamwork.md).

**Licenses** (read on each site; not legal advice)
- PhET: simulations released since March 29, 2026 are CC BY-NC 4.0; earlier ones stay CC BY 4.0; teacher
  activities in the database are CC BY 4.0; Teacher Tips are all rights reserved
  (phet.colorado.edu/en/licensing).
- Concord Consortium: CC BY-NC 4.0 (concord.org/licensing; CC BY 4.0 until at least March 2026).
- OpenSciEd: middle school CC BY 4.0; elementary and high school CC BY-NC 4.0 since October 2023.
- NetLogo models: CC BY-NC-SA 3.0. HHMI BioInteractive: set per resource, some CC BY-NC-SA 4.0. The Wonder of
  Science: CC BY-NC-SA 4.0. NOVA Labs (WGBH), Gizmos, NAAP, Zooniverse: no open license.
- NASA, USGS, NOAA: free to use, with credit and no implied endorsement; logos and third-party items excluded.
- Ideas, procedures, and facts aren't copyrightable (17 U.S.C. §102(b)); federal works have no copyright
  (§105).

**Data used**
- HAT-P-7 (Kepler-2): Kepler quarter 1 long-cadence light curve from MAST; NASA Exoplanet Archive values
  (Stassun et al. 2017: depth 0.60%, star 2.00 solar radii, planet 16.93 Earth radii, period 2.2047 days).
- Lynx and snowshoe hare: Hudson's Bay Company fur records, 1900-1920, thousands of pelts (the classic
  dataset; trapping records, not a census).
- Carbon-14 half-life: 5,700 ± 30 years (Kutschera 2019, Radiocarbon); textbooks often use 5,730.

**Evidence**
- Slavin 1996 (Contemporary Educational Psychology 21:43): group goals plus individual accountability, median
  +0.32 across 99 studies; one or neither, +0.07.
- Stanczak et al. 2022 (Journal of Educational Psychology 114:1461): jigsaw, five randomized trials in grade
  6, about 850 students, pooled effect 0.00.
- Cohen and Lotan 1995 (AERJ 32:99): status treatments raised low-status students' participation with no
  loss for others.
- Rosenshine and Meister 1994 (RER 64:479): reciprocal teaching, median 0.32 on standardized tests, 0.88 on
  experimenter-made tests.
- PALS: Evidence for ESSA "Strong" for whole-class elementary reading (+0.23); math showed no significant
  positive outcomes. Fuchs et al. 1997 (AERJ 34:174).
- Lou et al. 1996 (RER 66:423): within-class grouping +0.17; students who were behind did better in mixed
  groups, middle students in similar ones, high achievers no difference.
- Webb 1991 (JRME 22:366): giving and receiving elaborated explanations predicts learning; bare answers
  don't.
- Numbered Heads Together: only small single-case studies; no rigorous evaluation of Kagan Structures found.
