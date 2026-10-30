# Publishing Paper Loop

Where things stand on October 28, 2026, from Anthropic's docs and Help Center as read that day.

## Who each path reaches

No single path reaches every Claude user. Three together come close.

| Path | Who gets it | How they install it | Notes |
| - | - | - | - |
| **Skill zip** | Everyone, the Free plan included | Download `paper-loop.zip` from the GitHub releases page, then **Customize → Skills → + → Upload**, with code execution on (**Settings → Capabilities**) | The only path for Free accounts, which can't install plugins or use Cowork. No automatic updates. The upload caps the description at 200 characters, so `devtools/release.py` builds the zip with a short one. |
| **GitHub marketplace** | Pro, Max, Team, Enterprise, and Claude for Teachers | **Customize → Plugins → Add marketplace** → `badlerSI/paperloop`, in chat, the desktop app, or Cowork; in Claude Code, `/plugin marketplace add badlerSI/paperloop` | Works the day the repo is public. Users see a warning that the plugin isn't reviewed. Not confirmed: whether a teacher's individual Claude for Teachers account shows **Add marketplace**. |
| **Anthropic's plugin directory** | Pro, Max, Team, and Enterprise users browsing for plugins | One click from the directory | Reviewed by Anthropic (automated checks, a security scan, and a person for a new listing). The submitter needs a Pro plan or above and GitHub connected on claude.ai. |

Districts on Claude for Teachers' Enterprise offering can push it to every teacher: an owner syncs the repo
under **Organization settings → Plugins & skills** and sets it to install by default.

## Done

- `plugin/README.md`: what it does, six example prompts, everything it runs and every site it contacts.
  The directory blocks a plugin without a README of at least 40 words in the plugin folder.
- `PRIVACY.md`: the privacy policy the directory requires. Paper Loop collects nothing.
- `SECURITY.md`: how to report a vulnerability privately, which the directory terms require.
- `plugin.json`: version 0.6.0, with `homepage` and `repository`.
- `devtools/release.py` builds `dist/paper-loop.zip` for the releases page.
- `tests/test_release.py` checks the zip, the README rules, file sizes, and that every site the scripts
  reach is named in the README and the privacy policy.
- October 30, 2026: the repository was made public, private vulnerability reporting was turned on, and
  release `v0.6.0` was published with `paper-loop.zip` attached. The website, saaspocalypsenow.ai, deploys
  from `site/` on every push to `day-3`.

## Steps only the owner can take

1. **Try both installs** before telling anyone:
   - the marketplace in Cowork on your Claude for Teachers account (**Customize → Plugins → Add
     marketplace** → `badlerSI/paperloop`);
   - the zip on a Free account (**Customize → Skills** → upload `paper-loop.zip`, with code execution on).

   On each, print a sample from the website, fill it in, show Claude a phone photo, and say "Set up Paper
   Loop for my class." Then make a worksheet, mark a scan, and run `PL source` to see whether the sandbox
   reaches Wikipedia.
2. **Submit to the directory** at claude.ai/directory/manage: **Submit new → Plugin bundle**, plugin path
   `plugin`, then **Validate**. The data-handling answers and the four compliance acknowledgements are a
   legal attestation in your name, and the form asks for a contact email of your choosing. Answers to
   paste are below.
3. **Optional:** open an issue on `anthropics/k12-teacher-skills`, the skills built into Claude for
   Teachers, to ask whether it takes contributions. Contributions there need a CLA.

## Directory submission, ready to paste

Check each answer against the form as it is on the day; these follow the requirements as read on October
28, 2026.

- **Repository:** `https://github.com/badlerSI/paperloop`, plugin path `plugin`.
- **Name:** Paper Loop.
- **Description:** the `description` in `plugin/.claude-plugin/plugin.json`.
- **Example prompts:**
  1. "Make me a one-page worksheet on the water cycle for 6th grade: two multiple choice, a short answer, a
     diagram to label, and one to draw. I need a large-print version and a Spanish version."
  2. "Here's the scan of the class set. Mark it."
  3. "Make slides to go over what they missed, and a practice sheet for everyone."
- **Privacy policy:** `https://github.com/badlerSI/paperloop/blob/HEAD/PRIVACY.md`.
- **Security contact:** private vulnerability reporting on the repository's Security tab.
- **What data it collects:** none. Scans, worksheets, and everything Paper Loop makes stay in the
  teacher's Claude workspace. Students are known only by class ID numbers; Paper Loop never asks for a
  name.
- **What it connects to:** only the Wikimedia Foundation's API (`en.wikipedia.org`,
  `simple.wikipedia.org`, `en.wikisource.org`), and only when the teacher asks for a reading; the request
  carries an article title and a user agent naming Paper Loop. See "Readings from sites you don't control"
  below before you answer the domains question.
- **What it runs:** Python scripts in Claude's sandbox (numpy, scipy, Pillow, pypdfium2, reportlab,
  python-pptx). It installs nothing and starts no servers.

## Decisions before submitting

- **Readings from sites you don't control.** The directory policy (section 3F) asks developers to own or
  control every domain their software connects to. `PL source` fetches from Wikimedia's API (Wikipedia and
  Wikisource), which welcomes scripts that identify themselves. It no longer fetches from Project Gutenberg,
  whose site is for people only: the teacher downloads the book. There are two ways forward:
  - keep it and let the reviewer decide (the requests carry only an article title);
  - drop the scripts' fetching and have Claude always use its own web tool, which the skill already falls
    back to when the sandbox is offline. That loses the exact-revision link and Wikisource's check for
    unsourced pages.

  This doesn't affect the marketplace or the zip.
- **Saying that AI helped mark.** Anthropic's Usage Policy (effective November 12, 2026) treats grading an
  exam that decides graduation or certification as high-risk: a qualified person reviews the result, and
  the student is told AI was used. Classroom worksheets aren't that. A line on each marked page, such as
  "Comments drafted with Claude", would cover a teacher who uses Paper Loop on a test that counts, and it
  is honest with students and families.

## Not settled by the docs

- One Help Center page caps a skill's description at 200 characters; the Agent Skills spec and the other
  docs say 1,024. The plugin keeps its 1,005-character description and the zip gets the short one.
- Two docs say custom skills need Pro or above; the Help Center says the Free plan has them. Step 3
  settles it.
- Which Python packages claude.ai's sandbox has isn't published; the API's code execution container has
  all six Paper Loop needs.
- Network access from the sandbox depends on the plan: Free, Pro, and Max users can turn it on; Team
  defaults to package managers only; Enterprise is off unless an owner allows it.
