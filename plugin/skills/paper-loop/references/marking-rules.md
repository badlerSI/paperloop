# Marking rules

These are the rules Paper Loop's marking has been tested with on real handwriting. Follow them for every
crop. A teacher reviews anything you flag before it reaches a student. The worst outcome is a confident
misread: a wrong answer read as right, a misspelling silently fixed, or one student's work sent to another.

Applies to every question type:
- Judge each crop on its own, from what's in it. Don't let one student's answer change how you read
  another's.
- Comments are 15 words at most, at the students' grade level. They go in a narrow margin, so one short
  sentence usually beats two.
- No generic praise ("Good job!"). Comment on the work, never on the student as a person.
- Use precise vocabulary, the same terms the key uses. Never use the everyday word the lesson is
  correcting, such as "heavier" or "lighter" when the idea is "denser" or "less dense".
- A correct answer with a stray slip (a leftover wrong word) is still marked on what it gets right; the
  comment can confirm the right idea without dwelling on the slip.
- Confidence is between 0 and 1. Go below 0.8 whenever a teacher should double-check: those answers get
  flagged for review.
- Ignore doodles and anything outside the answer. If a crop shows a student's name, don't repeat it.

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
2. **uncertain_words**: any word you can't read with certainty, as your best literal reading. If the
   word could change the verdict, set confidence below 0.8 so the teacher sees it. If the verdict stands
   either way, list the word and keep your confidence. If you can't read enough to judge the answer, the
   verdict is "unreadable". Zoom in (`PL zoom`) before deciding a word is unreadable.
3. **verdict**, against the key. Accept correct ideas in the student's own words: the key says what full
   credit needs, not the only wording that earns it.
   - correct: meets everything the key requires.
   - partial: the right idea, but missing a required part or using imprecise language the key rules out.
   - incorrect: wrong or off topic.
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

## label

The student wrote a word or two in each numbered box on a printed diagram. Look at the blank crop first (the
diagram as printed): anything in the student's crop that isn't in the blank one is the student's.

For each numbered box:
1. transcription: exactly what the student wrote in that box. Keep their spelling. Never fix spelling or fill
   in what you think they meant. Write crossed-out text as [crossed out: word]. Empty box: "".
2. verdict, against the expected label and its accepted alternatives: a misspelling that still clearly names
   the right thing is correct ("photosinthesis" for photosynthesis); a different thing is incorrect. "blank" for an
   empty box; "unreadable" if you can't read enough to judge, with a low confidence for that box.

Then one comment about the whole diagram. If any label is wrong, point toward the one idea that fixes it
without giving away the answer; if all are right, name why the order makes sense. Set an overall confidence.

## draw

The student drew into a framed area that may have printed parts. Look at the blank crop first: anything in the
student's crop that isn't in the blank one is the student's. The worst outcome is giving credit for something
that isn't on the page.

1. description: what the student drew, plainly and literally, before judging anything: what marks are where,
   and roughly how many of each. Count when counting matters. Don't interpret beyond what's visible.
2. items: each numbered checklist item, checked against your description and the image. "yes" only if every
   part of the item is on the page, including any label it asks for; an item that's only partly there is
   "no". "unclear" if a teacher should decide. Judge the science the drawing shows, not artistic skill: a
   rough sketch that shows the idea earns the item. Add a short note saying what you saw.
3. comment: specific to their drawing. Name what it shows well, or the one thing to change, not both.
4. confidence: for the checklist as a whole.

## summary

For each page, from its marked answers in `summaries/todo.md`. The student reads it at the bottom of the page.

- strength: one specific thing the student did well on this page, under 20 words, pointing to a particular
  answer. If nothing earned credit, name an attempt that's on the right track.
- If every answer on the page is blank, write `{"strength": "", "fixes": []}`: the summary box stays empty,
  and the teacher decides what to say. Mention the page in your report.
- fixes: at most two next steps, most important first, each 15 words or fewer. Each one tells the student
  what to do, not only what was wrong. Each fixes something the marks show is missing or wrong: an answer
  that isn't correct, or a checklist item that isn't "yes". One fix can cover an idea that several wrong
  answers share; rank fixes by how many wrong answers they'd fix. Never ask for anything the question, key, or
  checklist doesn't ask for. Empty list if every answer is correct.
- Write for the student, at their grade level. Don't mention points, scores, or grades.
