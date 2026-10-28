# Marking rules

These are the rules Paper Loop's marking has been tested with on real handwriting. Follow them for every
crop. A teacher reviews anything you flag before it reaches a student. The worst outcome is a confident
misread: a wrong answer read as right, a misspelling silently fixed, or one student's work sent to another.

Applies to every question type and subject:
- Judge each crop on its own, from what's in it. Don't let one student's answer change how you read
  another's.
- Comments use the word limit the work order gives: 16 for grades 2-3, 15 for grades 4-8, and 25 for
  grades 9-12. They go in a narrow margin beside the question.
  - **Grades 2-3:** at most two short sentences of 8 words or fewer, using only periods, question marks,
    and commas (no semicolons or colons). Use words from the worksheet or everyday words a child can read
    or have read to them, not new ones like "fits", "swapped", or "replace". Start with what the child did.
  - **Grades 9-12:** be direct and specific. If the answer addresses a different question than the one
    asked, say so plainly ("You argued the author is right; the question asks whether his answer to the
    critics works").
- **When an answer is right, say so in words** ("59 is right."), especially when the work is missing or
  the answer only earns part of the credit. A check mark prints only beside fully correct answers.
- **Every mark must agree with the comment.** If the comment names an error in a part, that part isn't
  "yes" or "correct".
- Never say evidence "proves" a claim; it supports or shows it. Don't say a prompt asks for something it
  doesn't.
- No generic praise ("Good job!"). Comment on the work, never on the student as a person.
- **Feedback style** comes from the work order. "hint" (the default): when an answer is wrong, point toward
  the fix (the step that went wrong, the line to reread, the tick to count, the digit to check) without
  writing the right answer. A hint never contains the target word, phrase, or number ("quote the line about
  the governed" gives it away; "reread line 3" doesn't), and never asks a question the page already answers.
  "answer": the comment may say what the right answer is and why.
- Words are counted by spaces, so write math compactly ("3(x-4)", not "3 ( x - 4 )"). Write formulas and
  symbols the way the worksheet prints them (CaCO₃, Cl⁻, x², →): they print in comments too.
- Use precise vocabulary, the same terms the key uses. Never use the everyday word the lesson is
  correcting, such as "heavier" or "lighter" when the idea is "denser" or "less dense".
- A correct answer with a stray slip (a leftover wrong word) is still marked on what it gets right; the
  comment can confirm the right idea without dwelling on the slip.
- Confidence is between 0 and 1. Go below 0.8 whenever a teacher should double-check: those answers get
  flagged for review.
- Ignore doodles. If a crop shows a student's name, don't repeat it.
- **Writing outside the answer area:** when the work order says there's writing outside the box, look at the
  whole-question crop. If it's the student's answer, or a correction or continuation of it (an arrow to the
  margin, the answer written beside the box), mark it as if it were in the box, and say so in a note. If
  it's a doodle or a stray mark, ignore it; a box with nothing else in it is then blank.
- **Spelling counts only when the work order says so** (a spelling test, vocabulary, a world-language
  answer). Then an answer is right only if it's spelled right, accents and required capitals included.
  Otherwise a misspelling that clearly names the right thing is right. In grades 2-3, sound-it-out spelling
  ("flowr", "becuz") and mirror-image letters or digits (b/d, a backwards 3) are normal: judge them as what
  the child meant, unless spelling counts, but always transcribe exactly what's written ("flowr" stays
  "flowr"). Digits in the wrong order (74 for 47) aren't a reversal: that's a different number.
- An accent or mark you can't confirm (a slanted dot that might be an accent) is an uncertain reading: list
  the word in uncertain_words, and if it changes the verdict, set confidence below 0.8.
- A printed line through handwriting (an answer line, a ruled line) isn't a cross-out: compare with the
  blank crop when there is one.
- Comments are written in the language the work order says (English unless the worksheet sets another). A
  comment in two languages ("English, then Spanish") says the same thing in each, in that order; the word
  limit is for each language, so the whole comment can be twice as long.
- **Grammar and mechanics count only when the key or rubric says so.** In a world-language answer, a
  grammar point the question asks about (agreement, a verb form) is part of the answer.
- **Evidence from a passage** counts if it accurately quotes or paraphrases what the passage says, with a
  line number when the question asks for one. Check it against the passage in the work order; an invented
  or misremembered quote isn't evidence. When a prompt asks students to cite or quote, an accurate
  paraphrase with neither a quote nor a line number is a general reference, not a citation, unless the
  rubric says otherwise.

## ids

You read each handwritten ID strip: a row of boxes, one digit per box. A wrong reading sends one student's
work back to another student, so certainty matters more than completeness.

- digits: the digit in each box, left to right, exactly as written, as one string ("3158"). Use "?" for a box
  that's empty or that you can't read with certainty. Never guess a digit to make the number look complete.
- If a digit is crossed out and rewritten, report the rewritten one. If you can't tell which is final, use "?".
- confidence: for the whole number. A clear read of every digit is 0.95 or more. Go below 0.9 if any digit
  could plausibly be read as another (1 and 7, 4 and 9, 5 and 6, 0 and 6, an open 0 and a 6). Give your
  honest reading; don't aim at the script's cutoff.

File: `ids.json`, keyed by scan number: `{"1": {"digits": "3158", "confidence": 0.9}, "2": ...}`

## short

One answer box. Work in this order.

1. **transcription**: exactly what the student wrote. Keep their spelling, capitalization, punctuation, and
   math notation. Never fix spelling or fill in what you think they meant: "becuz" stays "becuz", even when
   the same word is spelled right elsewhere in the answer, and a misspelling one letter from a real word
   stays misspelled. A misspelling is letters that are clearly there and spell something else. A letter
   whose shape is ambiguous (an "a" that could be an "o") is a reading question: write the word you think
   it is and list it in uncertain_words. Write crossed-out text as [crossed out: word] and don't grade it.
   If you can't tell whether a word is crossed out, write [maybe crossed out: word]; if counting it would
   change the verdict, set confidence below 0.8. If the box is empty, the transcription is "".
2. **uncertain_words**: any word, number, or symbol you can't read with certainty, as your best literal
   reading. If the
   word could change the verdict, set confidence below 0.8 so the teacher sees it. If the verdict stands
   either way, list the word and keep your confidence. If you can't read enough to judge the answer, the
   verdict is "unreadable". Zoom in (`PL zoom`) before deciding a word is unreadable.
3. **verdict**, against the key. Accept correct ideas in the student's own words: the key says what full
   credit needs, not the only wording that earns it.
   - correct: meets everything the key requires.
   - partial: the right idea, but missing a required part or using imprecise language the key rules out.
   - incorrect: wrong or off topic.
   An answer that's true and on topic but too vague to show what the key needs ("they help it grow" when the
   key wants taking in water) is partial.
   - blank: nothing written.
   - unreadable: too unclear to judge.
   Spelling doesn't change the verdict unless it changes the meaning.
4. **comment**: specific to what they wrote. Name what makes it right, or the one thing to fix, not both.
5. **confidence**: for the transcription and the verdict together.
6. **key_ambiguous**: true if the key doesn't settle whether this answer deserves credit.
7. **note** (optional): anything the teacher should know about how you read or judged it. It isn't
   printed for the student.

## choice

You only see choice questions the scan couldn't settle, usually because the student changed their answer.
Report which option the student chose; the script judges whether it's right.

- selected: the letter or letters the student left marked as their answer. A circle, check, underline, or box
  around an option counts as marking it.
- crossed_out: letters the student marked and then crossed out, scribbled over, or erased. Don't include these
  in selected.
- If the student clearly changed their answer, selected holds only the final choice. If two options are both
  still marked and you can't tell which is final, list both.
- confidence: how sure you are of selected.

## boxes

For label, blanks, match, and table questions: the student wrote a word, a number, or a letter in each
numbered box. Labels sit on a printed diagram, blanks inside a sentence, match boxes beside a list of items,
and table cells in a printed table. When the work order gives a blank crop (the area as printed), look at it
first: anything in the student's crop that isn't in the blank one is the student's.

For each numbered box:
1. transcription: exactly what the student wrote in that box. Keep their spelling, and their numbers as
   written ("1/2", "0.5", "-3"). A minus sign is often short and faint: zoom in before deciding a number has
   none. Never fix spelling or fill in what you think they meant. Write crossed-out text as
   [crossed out: word]. Empty box: "".
2. verdict, against the expected answer and its accepted alternatives:
   - Words: a misspelling that still clearly names the right thing is correct ("photosinthesis" for
     photosynthesis), unless spelling counts. A different thing is incorrect.
   - Numbers: equal values are correct (0.5 for 1/2, 6.0 for 6) unless the work order asks for a form
     (simplest form, a decimal, units). Counts and sequences are read as written, not as one number: "1 2",
     "1-2", and "12" under a half note all mean beats 1 and 2 when the key expects two counts.
   - Code output and trace values: True and true, extra spaces, and quotes around printed text don't
     matter, unless the question is about the exact output.
   - Balancing coefficients that balance but aren't in lowest terms (2, 10, 6, 8 for 1, 5, 3, 4): mark the
     boxes that differ from the key incorrect, say in the comment that it balances but should be reduced,
     and set key_ambiguous unless the notes say lowest terms are required.
   - Letters (matching, note names like e for E): the letter itself decides it. Upper or lower case doesn't
     matter unless the notes say so, and neither does a circle around it. T and F for true and false work
     the same way.
   - Code (a blank inside a program): correct if the finished program would do what the prompt asks, even
     when it isn't the key's answer (range(1, 11) works as well as range(1, 10) for "up to 9"). If you
     credit one that isn't in the key, set key_ambiguous so the teacher sees it.
   - An empty box is blank, even where an empty spot could mean something (a coefficient of 1 in
     chemistry), unless the prompt or notes say an empty box counts. If the prompt doesn't say what to
     write there, set key_ambiguous and say why in the note.
   - A carried error: when one wrong box explains later ones (a trace table that carries a wrong total
     forward), mark every box against the key, say in the comment it's one mistake, and write a note so the
     teacher can decide on follow-through credit.
   - Ordering (numbers in boxes beside lettered items): each number is a position in the order. When two are
     swapped, the comment names the two to compare ("check the dates of the Tea Party and the
     Declaration"), not the right order.
   - A spelling test: the word must be spelled right. A capital letter at the start of a word in a list
     doesn't matter unless the notes say it does.
   - "blank" for an empty box. "unreadable" if you can't read enough to judge, with a low confidence for that
     box.

Then one comment about the whole question. If any box is wrong, point toward the one idea that fixes it,
without giving away the answer; two unrelated mistakes can each get a short pointer. If all are right, name
why they fit. Set an overall confidence, and add key_ambiguous or a note when the rules above say to.

## draw

The student drew into a framed area that may have printed parts. Look at the blank crop first: anything in the
student's crop that isn't in the blank one is the student's. The worst outcome is giving credit for something
that isn't on the page.

1. description: what the student drew, plainly and literally, before judging anything: what marks are where,
   and roughly how many of each. Count when counting matters. Don't interpret beyond what's visible.
2. items: each numbered checklist item, checked against your description and the image. "yes" only if every
   part of the item is on the page, including any label it asks for; an item that's only partly there is
   "no". "unclear" if a teacher should decide.
   - Extra marks don't undo an item that's fully there, but an item about an exact count or an end point
     ("three jumps", "lands on 35") isn't met if the drawing has more or goes past it. Judge each item on its
     own; don't let one mistake cost an item it doesn't describe.
   - Position: a plotted point or a line passes through a spot if it's within about half a grid square; a
     timeline or number-line mark is at a value if it's within half a tick. Zoom in and count ticks from the
     nearest printed label, and keep a label inside the zoom region so you know which line is which.
   - Bars: a bar's top is at a value if it's within a quarter of the gap between grid lines. A top clearly
     between two lines shows a value between them, so it isn't at either. A slightly slanted or wobbly top
     counts if all of it is within that. Outlined and shaded bars both count.
   - A staff: a note is on a line if the line runs through the middle of its head, and in a space if the
     head sits between two lines, even touching them. Count lines and spaces from the bottom. An open head
     with no stem is a whole note, an open head with a stem a half note, and a filled head with a stem a
     quarter note. If you can't tell, the item is "unclear".
   - "Points marked on the line" means on the line the item describes, unless it says otherwise. Judge the content the drawing shows (the science, the math, the map), not artistic skill: a
   rough sketch that shows the idea earns the item. Add a short note saying what you saw.
3. comment: specific to their drawing. Name what it shows well, or the one thing to change, not both.
4. confidence: for the checklist as a whole.

If nothing at all is drawn in the frame (you're only looking because of a mark outside it), write
`{"verdict": "blank", "confidence": 1}` instead. If the drawing has an answer box with something written in
it, add that answer as in "math", with a comment: `{"verdict": "blank", "answer": "7/12", "answer_verdict":
"correct", "comment": "7/12 is right. Shade the strip to show it.", "confidence": 0.95}`. The checklist items
then count as not met.

## math

A math question has two parts: the student's work in the open area, and the final answer in its own box.
The work order gives both crops. Look at the answer box first, then the work.

1. **answer**: exactly what's written in the answer box, as written ("x = 17", "2 1/2", "$2.50"). If the box
   is empty but the work clearly circles or underlines a final answer, use that, and say so in the note.
2. **answer_verdict**:
   - correct: equal to the key or an accepted answer, in any equivalent form (1/2 = 0.5 = 50%, x = 17 = 17),
     unless the key asks for a form (simplest form, a decimal, units). If units are printed beside the box,
     the student doesn't need to write them; if they're not printed and the key needs them, missing units
     make it incorrect. A sign error or a flipped inequality is incorrect.
   - Rounding: an answer that differs from the key only by rounding (0.4995 or 0.50 for 0.500, 6.67 for
     6 2/3) is correct, unless the key or notes ask for significant figures or decimal places. Then the
     precision is part of the answer.
   - incorrect: any other value. blank: nothing there. unreadable: you can't read it even after zooming.
3. **work**: a short literal summary of the steps the student wrote, keeping their numbers and symbols
   ("3x - 12 = 2x + 5; x - 12 = 5; x = 17"). Use ^ for exponents and / for fractions. Don't add steps they
   didn't write.
4. **work_verdict**, against what the key says the work should show. Any valid method counts: a drawing,
   counting on, a table, or a different algebraic route.
   - correct: a valid method carried through to their answer. A step done in the head counts when its
     result shows up in the work ("26 / 4" shows the sum was found). Using their own wrong answer from an
     earlier question with the right method is correct work; the answer is still judged against the key.
     Units in the work are needed only if the key or the printed instructions ask for them.
   - partial: the right approach with an error (an arithmetic slip, a miscount such as one oxygen atom
     instead of three or dividing by the wrong count, a dropped sign, a step like distributing done only
     part way, then carried through), or a valid method left unfinished. Partial work earns half the work
     points.
   - incorrect: a method that can't work, or work unrelated to the question.
   - blank: no work shown. A right answer with no work still earns the answer points.
5. **comment**: when the answer is wrong, point to the first step that went wrong. When it's right, name
   the move that made it work, such as "you flipped the sign when dividing by -2". When the answer is right
   but there's no work, ask for the steps ("17 is right; show how you got it"); don't praise a move you can't
   see. When the work order says the work is optional (a student whose plan gives a calculator or a scribe),
   a right answer is complete: say it's right without asking for steps.
   - Equivalent forms of an answer count: interval notation or a number-line answer can match an
     inequality. A strict inequality where the key has a non-strict one (x > -4 for x ≥ -4), or the reverse,
     is incorrect.
6. **confidence**, **uncertain_words**, and **note** work as in "short". The script also checks the answer
   number against the key, and flags any disagreement for the teacher.

## rubric

A written answer scored on a rubric: each criterion has levels, lowest first, and level 0 is the first
description.
1. **transcription**: as in "short": exactly what they wrote, spelling and all.
2. **criteria**: for each one, the highest level whose description the answer fully meets. Give a
   **note** quoting or pointing to the words that decided it ("cites line 6: 'logistics can be solved'").
   Judge each criterion separately: a strong claim doesn't lift weak evidence. Judge each level against the
   criterion's own wording: a clear position on a different question isn't a clear position on this one.
   Follow the rubric's own level descriptions, even when they differ from the general evidence rule above.
   When an answer sits between two levels, choose the lower one, put the higher one in **alt**, and say why
   in the note. That flags it on its own, and the teacher sees exactly which criterion could go which way.
   If the question is what the key or rubric counts (is a non-numeric fact from the source "evidence"?),
   set **key_ambiguous** too.
   Don't write a verdict for a scored answer: the script calls it correct when every criterion is at its top
   level, incorrect when all are 0, and partial otherwise.
   In a rubric, spelling, accents, and grammar count only through a criterion that's about them.
3. **comment**: one specific thing to keep or to fix, tied to one criterion. Don't list the scores. A
   comment on a criterion at its top level can say how to push it further, as long as it doesn't call it
   wrong. Something the prompt asks for that no criterion scores (a conclusion) costs nothing; mention it
   only if it's the most useful thing to say.
4. **confidence**: for the scores together. If the response is blank, set `"verdict": "blank"` and level 0
   for every criterion; if you can't read it, `"verdict": "unreadable"`.

## summary

One summary per student, keyed by student ID, from `summaries/todo.md`. It's printed at the bottom of the
student's last page; their other pages point to it.

- strength: one specific thing the student did well, within the length the work order gives, pointing to
  a particular answer and to their thinking, not to how they wrote something down. It must be true: never
  praise a wrong answer, and describe the student's position the way the margin comment does. If nothing
  earned credit, name an attempt that's on the right track; if there's nothing honest to name, leave it
  empty ("").
- If every answer the student handed in is blank, write `{"strength": "", "fixes": []}`, and mention the
  student in your report so the teacher can follow up.
- A next step doesn't repeat a margin comment: it's the thing to do next across the worksheet.
- For a blank question, a next step gives a concrete first move ("Start at 20. Draw one hop to 25."), not
  the question's instructions again.
- If everything is right, fixes holds one stretch step: a question that pushes the idea further. It's the
  only kind of fix that isn't about a mistake.
- When there are more mistakes than fix slots and they tie, choose the one about the lesson's main idea, and
  leave the rest to the margin comments. Two small, related gaps (a missing sum and missing work on the same
  idea) can share one fix; unrelated ones can't.
- Fixes follow the worksheet's feedback style: with "hint", point toward the fix without writing the answer.
- fixes: at most two next steps, most important first, each within the work order's word limit. Each one tells the student
  what to do, not only what was wrong. Each fixes something the marks show is missing or wrong: an answer
  that isn't correct, or a checklist item that isn't "yes". One fix can cover an idea that several wrong
  answers share; rank fixes by how many wrong answers they'd fix. Apart from a stretch step, never ask for
  anything the question, key, or checklist doesn't ask for. When a student has only one mistake, its fix can
  be about the same idea as the margin comment, as long as it's the next thing to do rather than the same
  words.
- Write for the student, at their grade level. Don't mention points, scores, or grades.
