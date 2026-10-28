# Try Paper Loop with a sample worksheet

Print one of these, fill it in yourself, and watch Claude mark it. It takes about ten minutes.

| Sample | What it shows |
| --- | --- |
| [Plants (grade 3)](sample-plants-gr3.pdf) | big print, labeling a diagram, circling a letter, a sentence |
| [Adding fractions (grade 5)](sample-fractions-gr5.pdf) | shading fraction strips, a word problem with units |
| [Smoothie ratios (grade 6)](sample-ratios-gr6.pdf) | a table, show-your-work math, plotting points, a choice |
| [La casa (grade 9 Spanish)](sample-spanish-gr9.pdf) | vocabulary where accents count, a short paragraph scored on a rubric |

## How to try it

1. **Print a sample.** Any printer works.
2. **Fill it in like a student would, in more than one way.** Get some answers right and some wrong, cross one
   out and write another beside it, leave one blank, and write a sentence with a spelling mistake. Then
   print it again and try another way. Write any number in the ID boxes: students write a class number,
   never their name.
3. **Take a photo or scan it.** Take a phone photo with the page flat and all four black corner squares in
   view, or scan it on any copier.
4. **Share it with Claude.** Paper Loop is a free plugin for [Claude for Teachers](https://www.anthropic.com/news/claude-for-teachers):
   - In Claude, open Cowork, then **Customize → Plugins**.
   - Add the marketplace `badlerSI/paperloop`, and install **Paper Loop**.
   - Share the photo and say "Mark this Paper Loop sample."

You get the page back marked: a comment beside each answer, a check or cross on each box, and a short
summary at the bottom. Claude also says what it wasn't sure of. Then ask it to make a worksheet for your own
class, in versions for students who need them.

## For Claude

Each sample names itself in its "Try Paper Loop" box and in its footer (`sample-ratios-gr6`). Its answer
key is rebuilt from `references/samples/<sample id>.json` in the Paper Loop skill. SKILL.md's "A Paper Loop
sample" section says how. Claude can't read a QR code from a photo reliably, so the box prints its
directions as text; the QR code is for the teacher's phone and opens the install page.

These PDFs come from `devtools/samples.py`. Rebuild them with `--url <your site>` to point the QR codes at
the site.
