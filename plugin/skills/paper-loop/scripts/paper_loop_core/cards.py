"""ID cards: a card for each class ID, to cut out and keep, so no student has to remember a 4-digit number.

For each class there's a class list for the teacher first: every ID in order, with a blank line beside it
for a name, written by hand. Numbered in the order of the teacher's own class list (their gradebook's),
the nth ID is the nth name, so the list they already have is the key. Then ten cards to a page. Each shows
the class, the number in big print, the number written into the worksheet's ID boxes, and a line for the
student's name. Names are written on paper only: no file here ever holds one.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas

from .fonts import choose
from .prepare import load_roster
from .sheet import INK, OUTLINE, PAGE_H, PAGE_W, STYLES

CARD_W, CARD_H = 252.0, 144.0  # 3.5 x 2 inches: a business card, to fit a wallet or a notebook cover
COLS, ROWS = 2, 5
LEFT = (PAGE_W - COLS * CARD_W) / 2
TOP = PAGE_H - (PAGE_H - ROWS * CARD_H) / 2
LIST_ROWS = 34  # IDs per column on the class list; two columns hold 68


def read_ids(path: Path) -> list[str]:
    """The roster's IDs in order: 2 digits if every one has 2 or fewer (grades 2-3), else 4."""
    ids = load_roster(path, 0) or set()
    width = 2 if ids and max(len(i) for i in ids) <= 2 else 4
    return sorted(i.zfill(width) for i in ids)


def _class_list(c: canvas.Canvas, f, name: str, ids: list[str]) -> int:
    """The teacher's list, two columns of IDs to a page. Returns the pages it took."""
    per_page = 2 * LIST_ROWS
    for start in range(0, len(ids), per_page):
        chunk = ids[start:start + per_page]
        col_w = (PAGE_W - 108) / (1 if len(chunk) <= LIST_ROWS else 2)
        c.setFillGray(INK)
        c.setFont(f.bold, 18)
        c.drawString(54, PAGE_H - 64, f.text(f"{name}: class numbers"))
        c.setFont(f.regular, 10)
        lines = [
            "For you, not for scanning. Write each student's name beside their number, in the order of your own",
            "class list, so the 1st name is the 1st number. Marked pages then come back in the order of your list.",
        ]
        for k, line in enumerate(lines):
            c.drawString(54, PAGE_H - 84 - 13 * k, line)
        for k, sid in enumerate(chunk):
            col, row = divmod(k, LIST_ROWS)
            x, y = 54 + col * col_w, PAGE_H - 130 - row * 18.5
            c.setFillGray(INK)
            c.setFont(f.bold, 11)
            c.drawString(x, y, sid)
            c.setStrokeGray(OUTLINE)
            c.setLineWidth(0.5)
            c.line(x + 44, y - 2, x + col_w - 18, y - 2)
        c.showPage()
    return -(-len(ids) // per_page)


def _card(c: canvas.Canvas, f, name: str, sid: str, x: float, y: float) -> None:
    """One card, its top-left corner at (x, y)."""
    pad = 14.0
    c.setFillGray(INK)
    c.setFont(f.bold, 10)
    c.drawString(x + pad, y - 22, f.text(name)[:44])
    c.setFont(f.regular, 7.5)
    c.setFillGray(0.35)
    c.drawString(x + pad, y - 34, "My class number")
    c.setFillGray(INK)
    c.setFont(f.bold, 34)
    c.drawString(x + pad, y - 72, sid)

    # The number written into boxes the size of the worksheet's, so students see what goes where.
    bw, bh = STYLES["primary" if len(sid) == 2 else "standard"]["id_box"]
    bx = x + CARD_W - pad - len(sid) * bw
    by = y - 76
    c.setFont(f.regular, 7.5)
    c.setFillGray(0.35)
    c.drawString(bx, by + bh + 5, "On a worksheet, write:")
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(0.8)
    for d, digit in enumerate(sid):
        c.rect(bx + d * bw, by, bw, bh, stroke=1, fill=0)
        c.setFillGray(0.3)
        c.setFont(f.regular, 16)
        c.drawCentredString(bx + d * bw + bw / 2, by + bh / 2 - 5.5, digit)

    c.setFillGray(INK)
    c.setFont(f.regular, 9)
    c.drawString(x + pad, y - CARD_H + 30, "Name")
    c.setStrokeGray(OUTLINE)
    c.setLineWidth(0.5)
    c.line(x + pad + 30, y - CARD_H + 28, x + CARD_W - pad, y - CARD_H + 28)
    c.setFont(f.regular, 7)
    c.setFillGray(0.35)
    c.drawString(x + pad, y - CARD_H + 13, "Put this number on every worksheet, never your name.")


def _cut_lines(c: canvas.Canvas) -> None:
    c.setStrokeGray(0.6)
    c.setLineWidth(0.4)
    c.setDash(3, 3)
    for col in range(COLS + 1):
        c.line(LEFT + col * CARD_W, TOP + 12, LEFT + col * CARD_W, TOP - ROWS * CARD_H - 12)
    for row in range(ROWS + 1):
        c.line(LEFT - 12, TOP - row * CARD_H, LEFT + COLS * CARD_W + 12, TOP - row * CARD_H)
    c.setDash()


def build(rosters: list[Path], out: Path, class_name: str = "") -> dict:
    """Write out (a PDF): for each roster, its class list and then its cards.

    The class is named by class_name (with one roster), else by the roster's folder: a class's folder,
    named by the teacher, holds its roster.csv."""
    if class_name and len(rosters) > 1:
        raise ValueError("--class-name names one class; with several rosters, each is named by its folder")
    classes = []
    for path in rosters:
        ids = read_ids(path)
        if not ids:
            raise ValueError(f"{path} has no ID numbers (it needs a column named id, one number per row)")
        name = class_name or (path.parent.name if path.parent.name else path.stem)
        classes.append((name, ids))
    f, _ = choose([name for name, _ in classes])
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Class ID cards")
    pages = 0
    report = []
    for name, ids in classes:
        pages += _class_list(c, f, name, ids)
        for start in range(0, len(ids), COLS * ROWS):
            _cut_lines(c)
            for k, sid in enumerate(ids[start:start + COLS * ROWS]):
                row, col = divmod(k, COLS)
                _card(c, f, name, sid, LEFT + col * CARD_W, TOP - row * CARD_H)
            c.showPage()
            pages += 1
        report.append({"class": name, "ids": len(ids)})
    c.save()
    return {"out": out, "pages": pages, "classes": report}
