# Worksheet format

A worksheet is one JSON object. `references/example-density.json` uses every question type.

```json
{
  "assignment_id": "sci6-plants-02",
  "title": "Plant Power",
  "subject": "science",
  "grade_band": "6th grade",
  "instructions": "Write your ID in the boxes at the top right, not your name. For multiple choice, circle one letter.",
  "compact": true,
  "questions": [ ... ]
}
```

- `assignment_id`: short, unique for this teacher, no spaces (subject, grade, topic, number). It's printed
  in the footer and in the page code that tells the scanner which worksheet a page belongs to.
- `compact`: tighter spacing and a smaller summary box, to fit more on a page. One page of US Letter holds
  about 6 questions compact, or 4-5 otherwise.
- Every page gets four ID boxes at the top right for a 4-digit class ID number, and a feedback summary box
  at the bottom.

## Questions

Every question has `q` (its number, 1 up) and `prompt`. Start prompts with a short, catchy name and a real
situation ("Closet Bean: Two bean plants get the same water for a week. One sits in a sunny window, one in
a dark closet. Which one ends up taller and greener, and why?").

### short: writes in a ruled box

```json
{"type": "short", "q": 3, "prompt": "...", "key": "The window plant: it uses light to make its food (photosynthesis). Full credit needs the window plant and light for making food; 'because of the sun' alone is partial.", "points": 2, "lines": 2}
```

- `key`: what full credit needs, and what's partial or wrong if that's likely. This is what marking reads.
- `lines`: ruled lines in the box (default 4; 2 is enough for one sentence).

### choice: circles one letter

```json
{"type": "choice", "q": 1, "prompt": "...", "answer": "B", "columns": 2,
 "options": [
   {"letter": "A", "text": "From the soil", "why": "Roots take in water and minerals, but not most of the plant's mass."},
   {"letter": "B", "text": "From the air", "why": "Yes: leaves take in carbon dioxide and build sugar from it."}
 ]}
```

- `why`: printed beside the question when the student picks that option. Write one for every option: the
  right one says why it's right, and each wrong one names the misconception.
- `columns`: options side by side (1, 2, or 4), for short options on a packed page.

### label: writes in numbered boxes on a printed diagram

```json
{"type": "label", "q": 4, "prompt": "...", "word_bank": ["roots", "stem", "leaf", "flower"],
 "diagram": {"width": 300, "height": 150, "description": "A simple plant: roots below a ground line, a stem, two leaves, a flower on top. Box 1 points to the roots...", "shapes": [ ... ]},
 "labels": [
   {"n": 1, "box": [180, 10, 75, 22], "points_to": [120, 25], "answer": "roots", "accept": ["root"]}
 ]}
```

- `box`: x, y, width, height of the label box inside the diagram. `points_to` (optional) draws a leader line
  to that point.
- `description`: plain words for what's printed, before any student touches it. Marking reads it.

### draw: draws into a framed area

```json
{"type": "draw", "q": 5, "prompt": "Draw what goes into a leaf and what comes out. Use arrows and label each one.",
 "diagram": {"width": 344, "height": 140, "description": "A large leaf outline in the middle of the frame.", "shapes": [ ... ]},
 "checklist": [
   {"item": "An arrow goes into the leaf labeled carbon dioxide (or CO2, any spelling).", "short": "CO2 in"},
   {"item": "An arrow comes out of the leaf labeled oxygen (any spelling).", "short": "Oxygen out"}
 ]}
```

- `checklist`: one point per item. Write items as things you can see on the page ("an arrow goes up from the
  leaf, labeled oxygen"), not judgments ("shows understanding of photosynthesis"). `short` is the wording
  printed beside the drawing on the returned page.
- `shapes` can print a scaffold: empty boxes to fill, axes, a beaker outline.

## Diagram shapes

Coordinates are points (1/72 inch) inside the diagram, origin at its bottom-left. A diagram is at most 344
points wide.

| shape | fields |
| --- | --- |
| `rect` | `x`, `y`, `w`, `h` |
| `circle` | `x`, `y` (center), `r` |
| `line`, `arrow`, `polyline`, `polygon` | `points`: [[x, y], ...]. An arrow gets a head at its last point. |
| `text` | `x`, `y`, `text`, `size` (default 9), `bold`, `align` (left, center, right) |

All shapes also take `fill` and `stroke` (gray from 0 black to 1 white, or null for none; stroke defaults to
black, fill to none) and `width` (line width, default 1). Keep fills light (0.6 or lighter) so students'
pencil marks show on them.
