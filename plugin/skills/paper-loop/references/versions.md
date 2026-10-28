# Versions, home languages, and a copy for each student

One worksheet can print as several forms. Each form has its own page code, so the teacher scans every copy
in one stack and marking sorts them out:
- **versions**: the same questions with supports some students need (scaffolds, large print, more room to
  write, a home language). The teacher hands each version to whoever needs it.
- **variants**: a different copy for each student (other numbers, other items, shuffled choices), so
  copying a neighbor's answers doesn't work.
- **practice sheets** (`PL practice`, after marking): each student's own sheet of the questions they missed.

**Who decides.** For a student with an IEP or 504 plan, the plan decides: print what it lists, as it
lists it, so the student practices with what they'll get on tests. For anyone else, the teacher decides.

**Privacy.**
- Paper Loop doesn't ask who has an IEP, a 504 plan, or English learner services, and never records a name.
- It does record which form each class ID turned in. So the marking folders and progress files are as
  sensitive as a list of plans: they belong where the teacher keeps student records.
- Ask the teacher what supports the plans in the class list, and how many students need each set, never
  which student. Then make one version for each set of supports. A version for "everyone who needs help" is
  the opposite of individualized.

| Example | Shows |
| --- | --- |
| `math6-ratios-02.json` | five versions: support (every scaffold, three choices, graph paper, a multiplication chart), large print, Spanish and Arabic (bilingual), Bengali (a Word page) |
| `math6-ratios-02.es.json`, `.ar.json`, `.bn.json` | translation files |
| `math6-ratios-hw-01.json` | 30 different homework copies: variables, a pool of word problems, shuffled choices |

## Supports on each question

Write the supports into the worksheet once. Each version picks which ones it prints, so the base worksheet
stays as written.

```json
{"type": "math", "q": 2, "prompt": "Unit Price: 6 smoothies cost $15. How much does 1 smoothie cost?",
 "answer": "$2.50", "key": "...",
 "support": {
   "plain": "6 smoothies cost $15 in all. What does 1 smoothie cost?",
   "hint": "Share $15 equally among 6 smoothies.",
   "steps": ["Write 15 ÷ 6.", "Divide. Keep going past the decimal point.", "Write the answer in dollars and cents."],
   "example": "4 apples cost $2. One apple: 2 ÷ 4 = $0.50.",
   "frame": ["The cost of 1 smoothie is ___ because ___."],
   "word_bank": ["divide", "each", "total"],
   "glossary": [{"term": "unit price", "meaning": "the cost of one"}],
   "drop": ["D"]}}
```

| Field | Prints | Notes |
| --- | --- | --- |
| `plain` | instead of the prompt | Plain English: short sentences, common words, the question last. A small help, mostly on math items for students partway into English. Pair it with an English glossary of the item's key words. Keep every number and the task the same, and don't use it where reading or vocabulary is what's tested. |
| `hint` | "Hint: ..." under the prompt | Points toward the method without giving the answer. |
| `steps` | numbered steps under the prompt | The method broken down. |
| `example` | a worked example in a shaded box | A similar problem solved, not this one. |
| `frame` | sentence starters on the first writing lines | `short` questions only. One per line: "Claim: ___", "Evidence: ___". Each frame adds a writing line, so the student's room stays the same. |
| `word_bank` | a word bank | Joins the question's own word bank in `blanks` and `label`. There it turns recall into recognition, so those scores show as "with help on the page". |
| `glossary` | "Key words:" with meanings | English meanings, for any reader. |
| `drop` | | Options to remove first when a version keeps fewer choices. |

## Versions

```json
"versions": [
  {"id": "support", "name": "Support", "scaffolds": "all", "max_choices": 3, "grid": true,
   "reference": ["multiplication"], "copies": 5},
  {"id": "lp", "name": "Large print", "large_print": 1.5, "space": 1.2, "per_page": 2, "copies": 1},
  {"id": "es", "name": "Spanish", "language": "es", "scaffolds": ["frame", "word_bank"], "copies": 3}
]
```

| Field | What it does |
| --- | --- |
| `id` | Short name, used for the file: `versions/<id>.pdf`. Letters, digits, dashes. |
| `name`, `label` | What the version prints, in a few words ("Hints and steps", "Large print 18pt"), never "IEP", "SPED", "ELL", or a student's name: names appear in files. `label` (default B, C, D...) prints small in the footer as "form B", and the base copy says "form A". The version's name never prints. |
| `scaffolds` | Which supports print: any of `plain`, `hint`, `steps`, `example`, `frame`, `word_bank`, `glossary`, or `"all"`. |
| `large_print` | `true` prints the questions at 18pt, the usual large-print minimum. `"20pt"` (or 20) sets a size, and 1.5 a scale. The answer areas, the directions at the top, the ID boxes, and the comments on the marked page grow too. Match the size the IEP or the vision teacher names. |
| `space` | More room to write: taller writing lines, work areas, and boxes (1.2 to 2; `true` is 1.4). |
| `per_page` | At most this many questions on a page. Fewer things on a page makes it less crowded (chunking). |
| `max_choices` | Keep this many choice options, dropping `drop` ones first and never the answer. Letters stay as printed on the base copy (A, B, D), so marking and results line up. |
| `only` | The question numbers this version keeps (`[1, 2, 4]`): a shortened assignment, scored out of those. |
| `grid` | Graph paper in math work areas, for lining up digits. |
| `reference` | A page students keep beside the worksheet, not handed in: `multiplication` (12×12), `hundreds`, `number_line`, `fractions` (fraction strips), `glossary` (the key words from the questions' `support`, whether or not the version prints them on the sheet), `formulas` (with `"formulas": [...]`). |
| `language`, `language_mode`, `translation` | A home language: see below. |
| `comment_language` | The language marking comments are written in for these students (default: the translation's). |
| `notes` | For the teacher, not printed ("read the questions aloud on request"). `make` prints it back. |
| `copies` | How many to print, if the teacher said. |

**A record for case managers.** `PL progress` writes `progress/supports.csv`: each class ID that had a version,
with the date, the worksheet, the version, its supports (in plain words, with any `notes` such as
read-aloud), and the help that changes what's measured. It's the accommodation log a case manager keeps for
an IEP or 504 plan, by class ID; the teacher matches IDs to names. A version's `notes` go into it word for
word, so never write a name there.

**Fewer to a page means more room to write.** A version with `per_page` gives the space it frees to the
writing lines and work areas on each page, up to double their size.

**Students who read below grade level** (not English learners): plain wording (`plain`) where reading isn't
what's tested, a word bank, sentence starters, more room to write, and, in `notes`, read-aloud by an adult. On
a reading or vocabulary question, plain wording and read-aloud change what's measured, so Paper Loop marks
plain wording there as help.

**Same length as everyone else's.** A version with more pages than the base sheet stands out, so `make` says
so (unless it has large print, more space, or fewer per page) and prints that version's blocks page by page,
with its free space and about how much to cut. A one-page exit sheet leaves little room for supports: plan
for them when you write the base (fewer lines on the base, or glossary terms on a key-words page with
`reference: ["glossary"]` instead of on the sheet).

**Three kinds of support.**
- **Access.** Large print, space, per_page, graph paper, translated directions, and glossaries change how a
  student gets at the question, not what it measures.
- **Help that lowers the demand.** Hints, worked examples, laid-out steps, fewer choices, `only`, and a word
  bank on a fill-in question change what the question measures. They're right for practice.
  - `make` lists them for each version.
  - Progress reports mark those questions' scores "with help on the page", question by question.
  - Practice sheets carry the marking over.
- **It depends on the question.** Plain wording, sentence frames, and reference pages measure nothing extra
  on a math word problem, but they do on a reading, vocabulary, writing, or fact-recall question. A
  multiplication chart beside a ratio table may hold the answers.
  - Paper Loop marks plain wording on a reading or vocabulary question as help.
  - For the rest, use judgment, and tell the teacher.

In an IEP, a "modification" is the team's decision to change the standard. Paper Loop doesn't make that
call. What's allowed on state tests varies by state, and the state's accessibility manual says. For
test-like checks, print what each student's plan lists.

**Keep the same items for everyone when you can.** Three options per choice question, for every student,
lose nothing in what the test measures. That is better than reducing choices for some. Glossaries, word
banks on open questions, and sentence frames can go on everyone's sheet. Then only hints, steps, and
examples set the support version apart, and fewer students stand out.

What the evidence says, for advising a teacher who asks:
- Fonts sold for dyslexia (OpenDyslexic, Dyslexie) don't help reading. Plain sans type with normal spacing
  does as well. If a plan names a font or size, follow the plan.
- Wider letter spacing can cut errors a little. More room around text and fewer items on a page (chunking)
  are reasonable.
- Large print is for low vision.
- Extended time is set by the plan; note it in the version's `notes`.

## Home languages

```json
{"id": "es", "name": "Spanish", "language": "es", "language_mode": "bilingual"}
```

The translation is a file beside the worksheet, `<assignment_id>.<language>.json`. Name another file
with `"translation"`, or put it inline in the worksheet as `"translations": {"es": {...}}`.

```json
{"language": "es", "title": "Razones en el puesto de batidos",
 "instructions": "Muestra tu trabajo. Escribe tu número de identificación, no tu nombre. Puedes responder en español o en inglés.",
 "questions": {"1": "Razón de la receta: Un batido lleva 2 tazas de mango por cada 3 tazas de yogur. Completa la tabla (tandas, tazas de mango, tazas de yogur).",
               "4": {"prompt": "¿El mismo sabor? ¿Qué receta sabe igual que 2 tazas de mango por 3 de yogur?",
                     "options": {"A": "3 de mango : 4 de yogur", "B": "6 de mango : 9 de yogur",
                                 "C": "4 de mango : 5 de yogur", "D": "1 de mango : 2 de yogur"}}},
 "passages": {"story": "..."},
 "glossary": [{"term": "ratio", "translation": "razón"}],
 "comment_language": "Spanish",
 "reviewed_by": "bilingual aide"}
```

- **What to translate.** Everything a question prints for the student to read.
  - A question's translation is a string. For a choice question, use `{"prompt", "options": {letter:
    text}}`: the options print one a line, with their letters on the reading side, and a version with
    fewer choices drops the same ones.
  - When the version prints sentence starters or a word bank, translate them too: `{"prompt": ..., "frame":
    ["La razón es ___ porque ___."], "word_bank": ["dividir", "cada", "total"]}`. The starters print one a
    line, and the bank's words print in the same order as the English bank, under the question's
    translation, so a student sees both. They print only when the version prints the English ones.
  - Translate table headers and axis labels too.
  - Keep every number a numeral, in the same order as the English ("2 cups mango to 3 cups yogurt" keeps
    mango first). Keep the words that say which number goes where ("mango across, yogurt up"). Use the
    subject's own terms: *razón* is ratio, *proporción* is proportion.
  - Answers stay in the English boxes. Students may answer in either language, and marking reads both.
  - The translated `title` heads the box of directions and key words.
- **`language_mode`:**
  - `bilingual` (the default) prints each question's translation under the English, plus directions and
    the glossary at the top.
  - `glossary` prints only the key-word box.
  - `companion` keeps the worksheet in English and puts the translation on a Word page
    (`versions/<id>.docx`). Word and Google Docs print every script correctly.
  - Every version with a language also gets that Word page.
- **Which mode to suggest**, by English level (WIDA levels 1-6):

  | English level | What helps |
  | --- | --- |
  | 1-2 (Entering, Emerging) | `bilingual` if they went to school in that language; a home-language glossary; word bank; frames; pictures |
  | 3 (Developing) | `plain`, frames, an English glossary; the home-language glossary if they use one in class |
  | 4-5 (Expanding, Bridging) | an English glossary, or the base sheet |
  | Students who had little schooling and don't read their home language well | a printed translation won't help: pictures, and the Word page as a script for a bilingual adult to read aloud |

  A full translation only helps students who learned the subject in that language. A translation or
  frames don't count as "help on the page": they give access to what an English learner knows.
- **Scripts the worksheet PDF can't print.** Bengali, Nepali, Hindi, Punjabi, Gujarati, Telugu, Burmese,
  and Karen need a shaping engine this sandbox doesn't have, so they must use `companion`, and `make` says
  so.
  - Arabic, Dari, Farsi, Urdu, and Pashto print right to left in a plain Arabic style. A few Urdu and
    Pashto letters print unjoined, so their Word page reads better.
  - Chinese, Japanese, and Korean print when a font for them is found, or use the PDF viewer's own.
- **Translation quality.** It varies by language. `make` asks for a bilingual adult to check the
  translation for languages Claude translates less reliably: Haitian Creole, Hmong, Somali, Pashto, Dari,
  Swahili, Karen, Burmese, Marshallese, Chuukese, Kinyarwanda, Tigrinya, Oromo, and others.
  - Once someone has, add `"reviewed_by"` with their role, not their name.
  - For the least reliable languages, keep to key words and directions until then.
  - Write Modern Standard Arabic, and ask whether Chinese should be Simplified (`zh-Hans`) or Traditional
    (`zh-Hant`).
- **Comments in a home language.** Comments in Arabic script print right to left on the marked page.
  Scripts the page can't print (Bengali, Nepali, Burmese, and others) can't be used for comments: write
  those in English. An English-speaking teacher can't check a comment in another language, so for a
  student just starting English, set `comment_language` to "English, then Spanish": a short English
  comment, then the same in Spanish.
- **Reading a home-language answer.** A handwritten answer in a script other than the Latin alphabet is
  hard to read from a scan. Give it a confidence under 0.8, so the teacher sees it, and say who could read
  it (a bilingual aide).

The most common home languages of US English learners, by code:
- **Spanish and Asian languages:** `es` Spanish, `ar` Arabic, `zh-Hans` / `zh-Hant` Chinese, `vi`
  Vietnamese, `ko` Korean, `ja` Japanese, `tl` Tagalog, `hmn` Hmong, `my` Burmese, `kar` Karen.
- **European languages and Haitian Creole:** `pt` Portuguese, `ru` Russian, `uk` Ukrainian, `fr` French,
  `tr` Turkish, `ht` Haitian Creole.
- **Afghan and South Asian languages:** `ps` Pashto, `prs` Dari, `fa` Farsi, `ur` Urdu, `uz` Uzbek, `ne`
  Nepali, `te` Telugu, `bn` Bengali, `pa` Punjabi, `gu` Gujarati.
- **African languages:** `sw` Swahili, `so` Somali, `om` Oromo, `am` Amharic, `ti` Tigrinya, `rw`
  Kinyarwanda.
- **Pacific languages:** `mh` Marshallese, `chk` Chuukese.

Families sometimes read a different language than the one they speak: many Pashto speakers read Dari, and
some Somali Bantu families speak languages that are rarely written. Ask the teacher.

## A different copy for each student

```json
"variants": {"count": 30, "seed": 4, "shuffle_choices": true},
"questions": [
  {"type": "math", "q": 1,
   "vars": {"n": {"choose": [4, 5, 6, 8]}, "p": {"min": 1.5, "max": 3, "step": 0.25, "base": 2.5}},
   "prompt": "Unit Price: {{n}} smoothies cost {{money(n*p)}}. How much does 1 smoothie cost?",
   "answer": "{{money(p)}}", "accept": ["{{dec(p, 2)}}", "{{p}}"],
   "key": "Divides {{money(n*p)}} by {{n}} to get {{money(p)}} for one smoothie."},
  {"type": "short", "q": 4, "prompt": "Explain: Leo makes paint with 2 cups blue for every 5 cups white...",
   "key": "...", "pool": [{"prompt": "Explain: A trail mix has 3 scoops nuts...", "key": "..."}]}
]
```

`make` writes `copies.pdf`: every copy, one after another. The teacher prints it once and hands the copies
out in any order. `worksheet.pdf` is the base copy, made with each variable's `base` value (or its first
allowed value). The go-over deck shows it as "one version".

- **`vars`.** Each variable is `{"min", "max", "step"}`, `{"choose": [...]}`, or a list, with an optional
  `"base"`. `"where"` rules combinations in or out: `"a < b and gcd(a, b) == 1"`.
- **`{{ expression }}`.** Works in any text of the question: prompt, key, answer, accept, options and their
  `why`, table cells, blanks, and diagram fields. A diagram field that is only an expression becomes a
  number, so bar heights and points can vary.
  - Arithmetic is exact: `{{6/4}}` prints 1.5 and `{{1/3}}` prints 1/3.
  - Functions: `frac(a, b)` (keeps a fraction: 3/2), `mixed(x)` (1 1/2), `money(x)` ($2.50), `dec(x, 2)`
    (2.50), `pct(x)`, `round`, `abs`, `min`, `max`, `gcd`, `lcm`, `sqrt`, `floor`, `ceil`.
- **`pool`.** A list of alternatives, each holding just the fields that change. Copies cycle through the
  question as written and its alternatives. Use it for subjects without numbers: another sentence to
  correct, another primary source, another word.
- **`shuffle_choices`.** Puts options in a new order on each copy, with the answer relettered. Results
  still count picks by the base copy's letters. Set `"fixed_order": true` on a question whose options must
  stay in order ("all of the above", numbers in order).
- **Check the copies.** Every copy's key is computed from its own values, so marking judges each copy
  against itself. Check a few with `PL preview "<folder>/copies.pdf" --page N`.

**What this does and doesn't stop.** It stops copying a neighbor's answers. It doesn't stop a student who
photographs the sheet and asks an AI. The most cheat-proof work is work the student explains, so mix in
`short` questions that ask why. Practice also works best when it's low-stakes: put the grades on work done
in class.

## Practice sheets after marking

`PL practice "<work>"` makes a sheet for each student who missed something.
- **What's on each sheet:** up to three of the questions they did worst on (`--most N`), with new numbers
  or another item where the worksheet has them. The comment they got last time is printed above each one,
  as "Last time: ...". A student who had a version practices on that version.
- **Who gets none:** students with full credit on everything, or a blank worksheet. `practice` lists them.
- **The ID is printed:** each sheet carries the student's class ID, so marking a practice scan needs no ID
  reading. After `prepare`, go straight to `todo`.
- **Same numbering:** questions keep their worksheet numbers, so progress reports count practice toward
  the same skills.
