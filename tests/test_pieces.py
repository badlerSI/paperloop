"""Classroom pieces: fold-over cards, games, and foldables from one pieces file (the plugin's `pieces`)."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugin" / "skills" / "paper-loop" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_loop_core import pieces as PC  # noqa: E402

EXAMPLES = sorted((ROOT / "examples").glob("*-pieces.json"))
REFERENCE = ROOT / "plugin" / "skills" / "paper-loop" / "references" / "examples"
BLOCKER = (Path(__file__).parent / "test_plugin.py").read_text().split('BLOCKER = """')[1].split('"""')[0]
PLANTS = ROOT / "examples" / "sci3-plants-pieces.json"


def close(a, b, eps=1e-9) -> bool:
    return all(abs(x - y) < eps for x, y in zip(a, b))


# --- The examples -----------------------------------------------------------------------------

@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_builds_clean(path, tmp_path):
    report = PC.build(path, tmp_path)
    assert report["warnings"] == []
    assert report["files"] == ["pieces.pdf"]
    doc = pdfium.PdfDocument(str(tmp_path / "pieces.pdf"))
    assert len(doc) == report["pages"]
    assert all(close(doc[i].get_size(), (612, 792), 0.01) for i in range(len(doc)))
    start = 2  # page 1 is the teacher's
    for piece in report["pieces"]:
        a, b = piece["pages"]
        assert a == start and b >= a
        start = b + 1
    assert start - 1 == report["pages"]
    assert (REFERENCE / path.name).read_text() == path.read_text()  # the plugin's copy is the same file


def test_the_examples_show_every_piece():
    kinds = set()
    for path in EXAMPLES:
        kinds |= {p["type"] for p in PC.normalize(json.loads(path.read_text()))["pieces"]}
    assert kinds == set(PC.TYPES)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_nothing_prints_within_the_margin(path, tmp_path):
    """Any printer reaches to 0.4in from the edge: every page is blank outside that."""
    PC.build(path, tmp_path)
    doc = pdfium.PdfDocument(str(tmp_path / "pieces.pdf"))
    edge = 28  # pixels at 72 dpi: just inside 0.4in (28.8pt)
    for i in range(len(doc)):
        img = np.asarray(doc[i].render(scale=1).to_pil().convert("L"))
        band = np.concatenate([img[:edge].ravel(), img[-edge:].ravel(), img[:, :edge].ravel(), img[:, -edge:].ravel()])
        assert band.min() > 245, f"page {i + 1} prints within 0.4in of the edge"


def test_gray_fills_are_light_enough_to_write_on():
    assert PC.FILL >= 0.85 and PC.LINES >= 0.7


# --- Fold geometry ----------------------------------------------------------------------------

def test_fold_over_card_answer_reads_upright_after_a_side_to_side_turn():
    # the question, on the top half, faces the reader the right way up before any turn
    where, up, right, facing = PC.card_fold((40, 30), (0, 1), "none")
    assert facing and close(up, (0, 1)) and close(right, (1, 0))
    # the answer prints upside down on the bottom half
    printed_up = (0, -1)
    where, up, right, facing = PC.card_fold((40, -30), printed_up, "none")
    assert not facing  # folded behind
    where, up, right, facing = PC.card_fold((40, -30), printed_up, "side")
    assert facing and close(up, (0, 1)) and close(right, (1, 0))  # upright, reading left to right
    assert where[1] > 0  # right behind the question
    where, up, right, facing = PC.card_fold((40, -30), printed_up, "top")
    assert facing and close(up, (0, -1))  # turned top to bottom it would be upside down: hence the direction


def test_fortune_teller_regions_fold_into_four_layers():
    ft = PC.FortuneTeller()
    roles = [ft.role(r) for r in ft.regions]
    assert sorted(roles.count(k) for k in ("number", "question", "answer", "outer")) == [8, 8, 8, 8]
    for r in ft.regions:
        for verts, A, b, parity, z, moved in r["states"]:
            assert np.allclose(A @ A.T, np.eye(2)) and round(np.linalg.det(A)) == parity  # rigid, flips counted
        final = r["states"][-1][0]
        assert all(abs(x) <= 0.5 + 1e-9 and abs(y) <= 0.5 + 1e-9 for x, y in final)  # the folded square
    # the same as the well-known template: outer labels in the corner squares, numbers on the edges
    plan = ft.layout()
    for k in range(1, 9):
        tri, _ = plan["number"][k]
        cx, cy = np.mean(tri, axis=0)
        assert abs(cx) + abs(cy) > 1 and max(abs(cx), abs(cy)) > 0.5


def test_fortune_teller_labels_land_where_kids_look():
    ft = PC.FortuneTeller()
    plan = ft.layout()
    for k in range(1, 9):
        stack = {}
        for role in ("number", "question", "answer"):
            tri, up = plan[role][k]
            centroid = tuple(np.mean(tri, axis=0))
            where, up_after, parity, z, moved = ft.forward(centroid, up)
            assert ft.sector(where) == k, (role, k)
            stack[role] = z
            if role == "number":  # on top of the flap, printing up, reading outward
                assert parity == 1 and moved == (2, 4)
                assert close(up_after, ft.outward(where))
            else:  # with the flap lifted (before the last fold): printing up, reading outward
                lifted, up_lifted, parity_lifted, _, _ = ft.forward(centroid, up, state=PC.LIFTED)
                assert parity_lifted == 1 and close(up_lifted, ft.outward(lifted))
                if role == "question":  # the flap's underside: beyond the hinge when lifted
                    assert parity == -1 and moved == (4,) and max(abs(lifted[0]), abs(lifted[1])) > 0.5
                else:  # the base under the flap: never moves
                    assert parity == 1 and moved == () and close(lifted, where)
        assert stack["number"] > stack["question"] > stack["answer"]  # number on top, the answer beneath
    lowest = min(s[4] for r in ft.regions for s in r["states"][-1:])
    for i in range(1, 5):
        square, up = plan["outer"][i]
        where, up_after, parity, z, moved = ft.forward(tuple(np.mean(square, axis=0)), up)
        assert parity == -1 and moved == (2,) and z == lowest  # the outside, seen from below
        tip = (math.copysign(1, where[0]) / math.sqrt(2), math.copysign(1, where[1]) / math.sqrt(2))
        assert close(up_after, tip)  # reads toward its point of the finished fortune teller


def test_zine_page_order_and_orientation():
    order = PC.zine_book()
    assert sorted(order) == [(r, c) for r in (0, 1) for c in range(4)]
    # the usual template: top row upside down 5 4 3 2, bottom row 6 7 back cover
    assert order == [(0, 3), (1, 3), (1, 2), (1, 1), (1, 0), (0, 0), (0, 1), (0, 2)]
    for page, panel in enumerate(order, start=1):
        # right-hand pages (and the cover) have the spine on the left; left-hand pages (and the back) on the right
        assert PC.zine_spine_side(panel) == ("left" if page % 2 else "right"), page
    for a, b in ((1, 2), (3, 4), (5, 6), (7, 8)):  # back to back on one leaf
        (ra, ca), (rb, cb) = order[a - 1], order[b - 1]
        assert (ca == cb and ca in (0, 3) and ra != rb) or (ra == rb and {ca, cb} == {1, 2})
    for a, b in ((2, 3), (4, 5), (6, 7), (8, 1)):  # facing across the spine: one row, joined at column 1 or 3
        (ra, ca), (rb, cb) = order[a - 1], order[b - 1]
        assert ra == rb and abs(ca - cb) == 1 and max(ca, cb) in (1, 3)
    assert PC.zine_panels()[1] == (0, 3) and PC.zine_panels()[8] == (0, 2)


def test_snake_path_visits_every_square_once():
    squares = [PC.snake_square(n) for n in range(1, 65)]
    assert len(set(squares)) == 64 and squares[0] == (0, 0)
    for (c0, r0), (c1, r1) in zip(squares, squares[1:]):
        assert abs(c0 - c1) + abs(r0 - r1) == 1
    corners = PC.snake_corners()
    assert len(corners) == 14 and all(PC.snake_square(n)[0] in (0, 7) for n in corners)


def test_printed_board_draws_the_path_through_every_square(tmp_path):
    from reportlab.pdfgen import canvas
    pdf = tmp_path / "path.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(612, 792))
    PC.snake_path(c, 36, 100, 67.5, 1.8, 0.5, 10)
    c.save()
    img = np.asarray(pdfium.PdfDocument(str(pdf))[0].render(scale=1).to_pil().convert("L"))
    for n in range(1, 65):
        col, row = PC.snake_square(n)
        x, y = 36 + (col + 0.5) * 67.5, 792 - (100 + (row + 0.5) * 67.5)
        assert img[int(y) - 1:int(y) + 2, int(x) - 1:int(x) + 2].min() < 200, f"no path at square {n}"
    x, top, bottom = int(36 + 1.5 * 67.5), int(792 - 100 - 1.5 * 67.5), int(792 - 100 - 0.5 * 67.5)
    assert img[top + 5:bottom - 5, x].min() > 245  # rows join only at the ends


def test_die_net_folds_into_a_cube():
    folds, cuts, tabs = PC.net_lines(100, 20, 0, 0)
    assert len(folds) == 5 + 7 and len(tabs) == 7 and len(cuts) == 7  # 12 cube edges: 5 folds, 7 glued
    opposite = {("A", "C"), ("B", "D"), ("L", "R")}
    assert all(PC.PIP_FACES[a] + PC.PIP_FACES[b] == 7 for a, b in opposite)


# --- Bingo ------------------------------------------------------------------------------------

def test_bingo_boards_are_unique_and_from_the_deck():
    P = PC.normalize(json.loads(PLANTS.read_text()))
    piece = next(p for p in P["pieces"] if p["type"] == "bingo")
    items, boards, order = PC.bingo_boards(P, piece)
    deck = {c["a"] if c["kind"] == "question" else c["q"] for c in P["cards"]}
    assert len(boards) == piece["boards"] and len({tuple(b) for b in boards}) == len(boards)
    for board in boards:
        assert len(board) == 25 and board[12] is None
        squares = [items[i]["square"] for i in board if i is not None]
        assert len(set(squares)) == 24 and set(squares) <= deck
    assert sorted(order) == list(range(len(items)))
    assert PC.bingo_boards(P, piece) == (items, boards, order)  # the same every build
    assert PC.bingo_boards({**P, "seed": 2}, piece)[1] != boards


def test_small_bingo_boards_from_a_short_deck(tmp_path):
    cards = [{"q": f"What is {n} + {n}?", "a": str(2 * n)} for n in range(1, 10)]
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"title": "Doubles", "grade": 2, "cards": cards,
                                "pieces": [{"type": "bingo", "size": 3, "boards": 6}]}))
    report = PC.build(path, tmp_path / "out")
    assert report["warnings"] == []
    P = PC.normalize(json.loads(path.read_text()))
    _, boards, _ = PC.bingo_boards(P, P["pieces"][0])
    assert all(len(b) == 9 and b[4] is None for b in boards)


# --- Text that fits, and errors that say what to fix ----------------------------------------------

def test_text_shrunk_below_the_grade_minimum_is_reported(tmp_path):
    long = "Which of these is a part of a plant that " + "really " * 40 + "matters?"
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"title": "T", "grade": 3, "cards": [{"q": long, "a": "roots"}],
                                "pieces": ["cards"]}))
    report = PC.build(path, tmp_path / "out")
    assert any(w.startswith("card 1's question") and ("12pt minimum for grade 3" in w or "cut short" in w)
               for w in report["warnings"])
    path.write_text(json.dumps({"title": "T", "grade": 3, "cards": [{"q": "What soaks up water?", "a": "roots"}],
                                "pieces": ["cards"]}))
    assert PC.build(path, tmp_path / "out")["warnings"] == []


def test_fit_never_spills():
    from reportlab.pdfgen import canvas
    pen = PC.Pen(canvas.Canvas(str(Path("/dev/null"))), PC.F.HELVETICA, 8, [])
    for text in ("ratio", "A recipe uses 3 eggs for 12 muffins. How many eggs for 36 muffins?",
                 "photosynthesis " * 3, "x" * 60):
        for w, h in ((250, 60), (100, 50), (60, 30)):
            size, lines = pen.fit(text, "Helvetica", w, h, 14, "t")
            assert all(pen.width(s, "Helvetica", size) <= w + 0.01 for s in lines)
            assert len(lines) * size * 1.2 <= h + 0.01


def test_games_without_hard_cards_say_so(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"title": "T", "grade": 5, "cards": [{"q": "2 + 2?", "a": "4", "level": 1}],
                                "pieces": ["snake_race", "chess_quiz"]}))
    warnings = PC.build(path, tmp_path / "out")["warnings"]
    assert any("Snake Race" in w and '"level": 3' in w for w in warnings)
    assert any("Chess Quiz" in w and '"level": 2 or 3' in w for w in warnings)


BAD = [
    ({"grade": None}, 'missing "grade"'),
    ({"cards": [{"q": "a"}, {"q": "b"}]}, 'card 1: missing "a"'),
    ({"cards": [{"q": "What is a seed?", "answer": "a baby plant"}]}, 'card 1: write "answer" as "a"'),
    ({"cards": [{"q": "q", "a": "a", "level": 4}]}, 'card 1: "level" is 1, 2, or 3'),
    ({"cards": [{"q": "q", "a": "a", "kind": "word"}]}, '"kind" is "question" or "term"'),
    ({"pieces": ["bingos"]}, 'pieces 1: unknown type "bingos" (did you mean "bingo"?)'),
    ({"pieces": [{"type": "spinner", "sectors": list("abcdefghi")}]}, '"sectors" needs 2 to 8 entries; it has 9'),
    ({"pieces": [{"type": "die", "faces": ["1", "2", "3"]}]}, '"faces" needs 6 entries; it has 3'),
    ({"pieces": [{"type": "die", "color": "red"}]}, 'pieces 1 (die): unknown field "color"'),
    ({"pieces": ["fortune_teller"]}, "needs 8 cards for its 8 flaps; the deck has 2"),
    ({"pieces": [{"type": "fortune_teller", "cards": [1, 2, 3, 4, 5, 6, 7, 9]}]},
     "card 3 isn't in the deck, which has cards 1-2"),
    ({"pieces": ["bingo"]}, "a 5x5 board needs 24 different answers, and the deck has 2"),
    ({"pieces": [{"type": "minibook", "pages": [{"text": "x"}]}]}, '"pages" is a list of the 6 inside pages'),
    ({"deck": []}, 'pieces file: unknown field "deck"'),
]


@pytest.mark.parametrize("change, message", BAD, ids=[m[:30] for _, m in BAD])
def test_bad_input_says_what_to_fix(change, message, tmp_path):
    data = {"title": "Seeds", "grade": 3, "cards": [{"q": "What grows from a seed?", "a": "a plant"},
                                                    {"q": "What do roots take in?", "a": "water"}],
            "pieces": ["cards"], **change}
    data = {k: v for k, v in data.items() if v is not None}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(PC.PiecesError) as err:
        PC.build(path, tmp_path / "out")
    assert message in str(err.value)


def test_main_reports_and_fails_cleanly(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    assert PC.main([str(path), "--out", str(tmp_path / "out")]) == 1
    assert "Can't make the pieces: bad.json isn't valid JSON" in capsys.readouterr().out
    assert PC.main(["pieces", str(PLANTS), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "pieces.pdf: 28 pages" in out and "pages 2-5: Fold-over cards" in out and "Check:" not in out


def test_pieces_run_in_the_sandbox_without_the_cli_packages(tmp_path):
    driver = tmp_path / "pieces_cli.py"
    driver.write_text(f"import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\nfrom paper_loop_core import pieces\n"
                      "sys.exit(pieces.main(sys.argv[1:]))\n")
    script = tmp_path / "blocked.py"
    script.write_text(BLOCKER)
    run = subprocess.run([sys.executable, str(script), str(driver), str(ROOT / "examples" / "math6-ratios-pieces.json"),
                          "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr + run.stdout
    assert "Wrote" in run.stdout and "Check:" not in run.stdout
    assert (tmp_path / "out" / "pieces.pdf").exists()
