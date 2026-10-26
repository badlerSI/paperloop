# Plom spike (Day 1)

**Decision: use Plom as a design reference only.** Don't adopt it as the backbone or wrap it with an adapter for v0.1.

**What I tried (about 30 minutes of the one-hour cap).** I installed plom 0.22.4 (AGPL-3.0-or-later) in a throwaway virtualenv. Using Plom's own `create_QR_codes` and `pdf_page_add_labels_QRs`, I generated a two-page QR-coded paper, rendered it at 200 dpi, and read it back with `plom.scan.qr_extract.QRextract_list`. All three corner codes decoded, with paper, page, version, and corner. I also read the `create`, `scan`, and `idreader` modules. I didn't stand up the server.

**Why not the backbone**

1. **The workflow doesn't match.** Plom prints a uniquely numbered paper for every student: the paper number is in every QR code, and IDs are matched to a class list afterward. A teacher prints one master and photocopies it 30 times. Paper Loop puts only the assignment and page in the QR code, and reads the student from ID bubbles.
2. **It's heavy.** `pip install plom` pulled in about 130 packages, including Django, PyQt6, transformers, onnxruntime, WeasyPrint, and PyMuPDF. The full workflow runs a Django server and a database built for teams of markers. That's a lot to put on a teacher's laptop to run one command-line tool.
3. **The license doesn't fit.** Plom is AGPL-3.0-or-later, and so is PyMuPDF. The spec keeps the core Apache 2.0.

**What we borrowed as ideas.** These were reimplemented; no code was copied.

- **Codes in several corners,** so a torn or stapled corner doesn't lose the page. Paper Loop uses four ArUco markers for orientation and deskew, plus one QR code for identity.
- **The highest QR error-correction level (H).**
- **The `pdfmucker` scan-damage tool** (fold, tear, rotate, lighten, jam). `paperloop simulate` already adds skew, shift, noise, a flipped sheet, and a blank page. Folds and torn corners are worth adding next.
- **Later: matching IDs against the class list** (`idreader/assign_prob.py`), if we ever read handwritten IDs instead of bubbles.

**When to revisit.** If a district wants team marking with a web interface, an exporter that sends our feedback into Plom could make sense. It would live outside the Apache core.
