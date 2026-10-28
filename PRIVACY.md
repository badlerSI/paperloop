# Paper Loop privacy policy

Effective October 28, 2026.

Paper Loop is free, open-source software that runs inside a teacher's own Claude account, as a plugin or a
skill. This policy covers Paper Loop itself. Claude is Anthropic's service, and the teacher's Claude
account terms cover what Claude does with the files it's given.

## What Paper Loop collects

Nothing. The project has no servers, no accounts, no analytics, and no tracking. Its author never receives
anything a teacher does with it.

## Where files go

- **Into Claude.** Scans, lists of class ID numbers, and the files Paper Loop makes (worksheets, marked
  pages, slides, dashboards) stay in the teacher's Claude workspace. Anthropic handles them under the
  teacher's account terms: for Claude for Teachers, see
  [Claude for Teachers: your data and our terms](https://support.claude.com/en/articles/15926041-claude-for-teachers-your-data-and-our-terms).
- **To Wikimedia, only when asked for a reading.** Paper Loop's scripts contact one service:
  the Wikimedia Foundation's public API at `en.wikipedia.org`, `simple.wikipedia.org`, and
  `en.wikisource.org`. A request carries the article title, and a user agent naming Paper Loop and its
  project page, as Wikimedia asks of scripts. It carries nothing else: no student work, no names, no email
  address.
- **Nowhere else.** The scripts make no other network requests.

## Sources Paper Loop draws on, and whose terms apply

Paper Loop isn't affiliated with, or endorsed by, any of these organizations. Readings are credited under
the passage, as each license asks.

- **Wikipedia, Simple English Wikipedia, and Wikisource,** run by the Wikimedia Foundation and written by
  their volunteer contributors. Wikipedia's text is shared under
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Paper Loop credits "Wikipedia
  contributors" with a link to the exact revision used, and says what it changed. Most Wikisource texts
  are in the public domain; Paper Loop asks Claude to check each page's license box. Requests follow
  Wikimedia's [Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) and
  [User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy).
  Wikimedia's own [privacy policy](https://foundation.wikimedia.org/wiki/Policy:Privacy_policy) covers
  the request.
- **Project Gutenberg,** a volunteer library of public-domain books. Its website is
  [for people, not scripts](https://www.gutenberg.org/policy/robot_access.html), so Paper Loop never
  downloads from it. The teacher downloads a book and gives Claude the file. Paper Loop removes Project
  Gutenberg's license header and footer, as [its license](https://www.gutenberg.org/policy/license.html)
  asks when a text is reused, and credits the book with a link to its page.
- **US government agencies** such as NASA, NOAA, USGS, and the Library of Congress. Claude reads their pages
  with its own web tool when the teacher asks. Works of the US government are generally in the public
  domain; Paper Loop credits the agency.
- **Anthropic's Claude** does the reading, marking, and writing, under the teacher's own Claude account.

## Student data

Paper Loop is built to work without knowing who a student is:
- students write a class ID number, never a name, and Paper Loop never asks for, accepts, or writes down
  names;
- Claude sees cropped answer boxes and the ID strip, not the whole page;
- no file records a student's race, disability, language background, or family income; the teacher hands
  out versions, and Paper Loop only knows which version a class ID turned in;
- the teacher keeps the list matching ID numbers to names, outside Claude.

On a teacher's own account, keep student work de-identified unless the school or district has authorized
Claude for student records.

## Keeping and deleting

Paper Loop keeps nothing. Files in the teacher's Claude workspace stay until the teacher deletes them.
How long Anthropic keeps conversations and files is set by the account's terms.

## Children

Paper Loop is for teachers. It isn't meant for students to use directly.

## Changes and questions

Changes to this policy are made in the public repository, where the history shows every version. Ask
questions or report a problem in the repository's issues: <https://github.com/Badlerz/paperloop/issues>.
