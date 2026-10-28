# Pieces format

Pieces are paper versions of screen review games (Quizlet, Kahoot, Blooket): fold-over question cards,
games for any checker or chess board, and foldables. One JSON file holds a deck of cards and the list of
pieces to make from it. `PL pieces FILE.json --out DIR` writes `DIR/pieces.pdf`: a page for the teacher
(what's in the file, page numbers, what to print it on, prep, materials), then each piece on its own pages.

Everything prints one-sided, in black and white, on US Letter, with any printer. Students need only
scissors; a glue stick helps the die and pawns but is optional.

| Example | Grade | Shows |
| --- | --- | --- |
| `sci3-plants-pieces.json` | 3 | big type, question and term cards, Snake Race and the printed board, a vocabulary die, a fortune teller, a mini-book with its own pages plus a blank one, bingo |
| `math6-ratios-pieces.json` | 6 | difficulty levels on every card, all four board games, a level spinner, lettered pawns, a blank mini-book, 30 bingo boards |

```json
{
  "title": "Plant Parts and What Plants Need",
  "short_title": "Plants",
  "subject": "science",
  "grade": 3,
  "cards": [
    {"q": "What part of a plant soaks up water from the soil?", "a": "roots", "level": 1},
    {"q": "A bean plant lived in a dark closet for a week. What color did its leaves turn, and why?",
     "a": "pale yellow: no light to make food", "level": 3},
    {"q": "seedling", "a": "a young plant that just grew from a seed", "kind": "term", "level": 2}
  ],
  "pieces": ["cards", "blank_cards", "snake_race", "board", {"type": "bingo", "boards": 24}]
}
```

## The file

| Field | Required | What it is |
| --- | --- | --- |
| `title` | yes | Printed on the teacher's page and every page heading. |
| `grade` | yes (or `grade_band`) | 2-12. Sets the type sizes: card text starts at 18pt and never goes below 12pt in grades 2-3; it starts at 16pt (grades 4-5) or 14pt (6-12) and never goes below 9pt. Grades 2-5 get 8 cards a page, grades 6-12 get 10. |
| `short_title` | no | Up to 24 characters, printed small on every card ("Plants 7") so a dropped card finds its deck. Defaults to the first words of `title`. |
| `subject` | no | Shown on the teacher's page. |
| `seed` | no | A whole number (default 1). Bingo boards are the same every build; change `seed` for a new set. |
| `cards` | yes | The deck (below). |
| `pieces` | yes | What to make, in order (below). |

## Cards

| Field | What it is |
| --- | --- |
| `q` | The front: a question, or for a term card the word itself. |
| `a` | The back: the answer, or the term's meaning. |
| `level` | Optional: 1, 2, or 3, printed as 1-3 dots. 1 is a warm-up, 3 a stretch. The games use levels (below). |
| `kind` | `"question"` (the default) or `"term"`: a vocabulary card, the term printed bold on the front and its meaning on the back. On a bingo board the term is the square and the meaning is the clue. |

Card numbers are their order in the deck, from 1. Pieces that pick cards (`fortune_teller`, `minibook`)
use these numbers.

## Pieces

Each entry is a type (`"cards"`), or an object with `"type"` and that piece's options. A type can appear
twice, such as two spinners with different sectors.

| Type | What it makes | Options |
| --- | --- | --- |
| `cards` | Fold-over cards: the question on the top half, the answer upside down on the bottom half, a dashed fold between. Fold, printing out, and turn the card over side to side to read the answer. Empty slots on the last page become blank cards. | none |
| `blank_cards` | The same cards, empty ("Question", "Answer", writing lines, three dots to fill in for a hard card), and a "Make a good card" checklist. | `pages` (1-10, default 1) |
| `snake_race` | Rules for a race along all 64 squares, row by row. Roll, answer, move the roll. A corner square (the end of a row) earns a 3-dot card for 3 more squares. | none |
| `question_checkers` | Checkers where a jump needs a right answer and becoming a king needs a 3-dot card. | none |
| `four_in_a_row` | Each right answer drops a checker to the lowest empty square of a column; four in a row wins. | none |
| `chess_quiz` | Chess where a capture needs a right answer, the card's dots matching the piece: pawn 1, knight or bishop 2, rook or queen 3. | none |
| `board` | A printable 8x8 board with the Snake Race path numbered, for a class with no boards. | none |
| `die` | A cube net with glue tabs and folding steps. | `faces`: `"pips"` (the default, opposite sides add up to 7), `"vocab"` (Define it, Draw it, Use it in a sentence, Opposite, Example, Act it out), or a list of 6 short texts |
| `spinner` | A circle with 2-8 labeled sectors, spun with a paper clip and a pencil. | `sectors`: 2-8 short texts (default: 1, 2, and 3 dots, twice, to pick a card's level) |
| `pawns` | Stand-up tent pawns, 6 sets a sheet, each player's pawn with its own pattern (plain, gray, stripes, dots, checks, rings) so black-and-white copies stay easy to tell apart. | `labels`: 2-6 short labels (default 1-6) |
| `fortune_teller` | A cootie catcher: 4 corner words, 8 numbered flaps, a question under each flap and its answer beneath that. | `outer`: 4 words (default Red, Blue, Green, Gold, which students can color); `cards`: 8 card numbers (default: the 8 shortest cards) |
| `minibook` | An 8-page book folded from one sheet (a zine fold), with a page of folding steps. The cover, 6 inside pages each with a heading, text, and a picture box, and a back cover. | `title` (default: the file's), `pages`: 6 of `{"heading": "...", "text": "..."}`, or `cards`: 6 card numbers (default cards 1-6), `back`: the back cover's text, `blank: true` for a blank book to write, `also_blank: true` to add a blank one |
| `abcd` | Answer cards: A, B, C, D in big letters, a fold-over card each, one sheet per student, so the whole class holds up an answer at once. | `letters`: 2-4 (`["T", "F"]`, `["Yes", "No"]`) |
| `bingo` | Unique boards (one per student) of the deck's answers, a free middle square, and the caller's list: every clue in a shuffled order, with its answer. | `boards` (1-60, default 30); `size`: 5 (the default; needs 24 different answers), 4 (16), or 3 (8) |

Every game's rules page says how to check an answer (the reader looks at the back of the folded card),
what happens on a wrong answer (the reader says the right one, and the card goes to the bottom of the
pile), and the "explain it" rule: a 3-dot card also needs a reason ("I know because...").

## What `pieces` reports

`Wrote DIR/pieces.pdf: 28 pages, 26 cards`, then each piece's pages, then any `Check:` lines. Fix every
`Check:` before handing the file over:

- **Text shrunk below the grade's minimum** ("card 7's question was shrunk to 10pt..."): shorten that card,
  or for a fortune teller, choose shorter cards with `cards`.
- **A game uses levels the deck doesn't have** (Snake Race and checkers need 3-dot cards; Chess Quiz needs
  all three levels): add `level` to the cards.
- **Characters that will print as "?"**: no Unicode font was found; write them in words.

## Writing good pieces

- **Short cards.** One idea per card, a question with one checkable answer. Answers that are a word or a
  short phrase work everywhere: on bingo squares, in fortune teller flaps, and read aloud in a game. For a
  question that needs a reason, put the key reason in the answer ("pale yellow: no light to make food").
- **Level the deck when there are games.** About a third each: level 1 recalls a fact, level 2 applies it,
  level 3 explains or works a multi-step problem. Give levels to every card, or to none.
- **Mix in term cards** for vocabulary (`"kind": "term"`), so bingo has terms to call by their meanings.
- **Bingo needs enough different answers**: 24 for a 5x5 board. Two cards with the same answer make one
  square. With fewer, use `"size": 4` or `3`, or skip bingo.
- **Grades 2-3:** about 16-26 cards, short words, levels 1-2 for most. Pieces that fold (fortune teller,
  mini-book) go best after the teacher models the folds once.
- **Check every fact**, and choose simplifications that stay true at the next grade.
- **Don't give away a worksheet's answers.** If the class hasn't done the worksheet yet, use different
  numbers or examples on the cards.
- **Choose pieces for the time there is:** cards and a board game for a 20-minute review; a fortune teller
  or mini-book when there's time to fold; ABCD cards for whole-class checks any day; bingo for the whole
  class at once.
- **Where files go:** save the JSON beside the unit's worksheets (`<folder>/<topic>-pieces.json`) and build it
  with `--out "<folder>/<topic>-pieces"`.
