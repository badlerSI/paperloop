# Paper Loop

Paper Loop turns a school copier and Claude into the whole classroom loop on paper, for any subject from
grade 2 to grade 12. Claude plans the lesson and makes the worksheet, in versions for students who need
them. Students write on paper, and the teacher scans the stack. Claude reads every answer against the key
and writes a short comment beside it. The teacher checks anything Claude was unsure of and prints the
marked pages to hand back. Afterward Claude makes go-over slides, a practice sheet for each student, group
work, games, and a progress dashboard.

Students are known only by a class ID number. Paper Loop never asks for a name.

## Try it

- "Make me a one-page worksheet on the water cycle for 6th grade: two multiple choice, a short answer, a
  diagram to label, and one to draw. I need a large-print version and a Spanish version."
- "Here's the scan of the class set. Mark it."
- "Make slides to go over what they missed, and a practice sheet for everyone."
- "Plan a 50-minute lesson on equivalent ratios, with slides and a worksheet."
- "A lab on natural selection for groups of 4, with roles, and an exit sheet each student does alone."
- "How is my class doing?"

## What it runs and what it sends

- **Runs:** Python scripts in Claude's sandbox, using numpy, scipy, Pillow, pypdfium2, reportlab, and
  python-pptx. They line up scanned pages, crop the answers, and lay out PDFs, Word files, and slides. They
  install nothing and start no servers.
- **Sends:** nothing, except when the teacher asks for a reading from Wikipedia or Wikisource. Then the
  scripts fetch it from the Wikimedia Foundation's API at `en.wikipedia.org`, `simple.wikipedia.org`, or
  `en.wikisource.org`. The request carries only the article title, and a user agent naming Paper Loop and
  its project page, as Wikimedia asks. It never carries student work, names, or anything about the
  teacher. If the sandbox can't reach those sites, Claude uses its own web tool.
- **Never fetches from Project Gutenberg,** whose site is for people, not scripts: the teacher downloads a
  book and gives Claude the file.
- **Keeps:** nothing. Scans and the files Paper Loop makes stay in the teacher's Claude workspace.

The privacy policy, which also credits the sources Paper Loop draws on (Wikipedia, Wikisource, Project
Gutenberg, and US government agencies) and says whose terms apply, is at
<https://github.com/Badlerz/paperloop/blob/main/PRIVACY.md>. The skill's own
rules are in [`skills/paper-loop/SKILL.md`](skills/paper-loop/SKILL.md).

## Who can use it

Paper Loop is for teachers, not for students to use directly. Plugins work on Claude's paid plans and on
the free [Claude for Teachers](https://www.anthropic.com/news/claude-for-teachers) plan for US K-12
educators. On the Free plan, upload the skill instead: download `paper-loop.zip` from the
[releases page](https://github.com/Badlerz/paperloop/releases) and add it under **Customize → Skills**.

On a teacher's own account, keep student work de-identified (class ID numbers, no names) unless the school
or district has authorized Claude for student records.

## License

Apache 2.0. Paper Loop is an independent open-source project. Anthropic didn't make it and doesn't endorse
it.
