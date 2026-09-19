import itertools

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

from checkprog import theme
from checkprog.delegate import ItemDelegate
from checkprog.listmodel import ChecklistModel

LONG = " ".join(["комментарий"] * 30)
NOTES = ["", "коротко", LONG, "а" * 200, "первая\n\nтретья", "x " * 80]
WIDTHS = [120, 181, 260, 400, 640, 900]


@pytest.fixture
def setup(qapp):
    model = ChecklistModel()
    for i, note in enumerate(NOTES):
        model.add(f"пункт {i} с текстом подлиннее, чтобы он иногда не помещался")
        if note:
            model.set_note(i, note)
    return model, ItemDelegate()


def option(width, top=0, height=0, selected=False):
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, top, width, height)
    opt.font = QFont()
    opt.fontMetrics = QFontMetrics(opt.font)
    opt.state = QStyle.State_Enabled | (QStyle.State_Selected if selected else QStyle.StateFlag(0))
    return opt


def rects(lay):
    return {k: r for k, r in (("check", lay.check), ("text", lay.text),
                              ("arrow", lay.arrow), ("note", lay.note)) if r is not None}


def cases(model):
    for row, width, expanded in itertools.product(range(model.rowCount()), WIDTHS, (False, True)):
        model.set_expanded(row, expanded)
        yield row, width


def laid_out(delegate, model, row, width):
    ix = model.index(row)
    h = delegate.sizeHint(option(width), ix).height()
    opt = option(width, top=37, height=h)  # rows do not start at 0 in a real view
    return opt, ix, delegate.layout(opt, ix)


def test_zones_inside_row_and_disjoint(setup):
    model, d = setup
    for row, width in cases(model):
        opt, ix, lay = laid_out(d, model, row, width)
        rs = rects(lay)
        for name, r in rs.items():
            assert r.isValid(), (row, width, name)
            assert opt.rect.contains(r), (row, width, name, r, opt.rect)
        for (a, ra), (b, rb) in itertools.combinations(rs.items(), 2):
            assert not ra.intersects(rb), (row, width, a, b)


def test_arrow_only_with_note_and_note_only_when_expanded(setup):
    model, d = setup
    for row, width in cases(model):
        _, ix, lay = laid_out(d, model, row, width)
        item = model.checklist.items[row]
        assert (lay.arrow is not None) == bool(item.note)
        assert (lay.note is not None) == (bool(item.note) and item.expanded)
        assert bool(lay.note_lines) == (lay.note is not None)


def test_hit_matches_layout(setup):
    model, d = setup
    for row, width in cases(model):
        opt, ix, lay = laid_out(d, model, row, width)
        for name, r in rects(lay).items():
            for p in (r.center(), r.topLeft(), r.bottomRight()):
                assert d.hit(opt, ix, p) == name, (row, width, name, p)
        assert d.hit(opt, ix, QPoint(opt.rect.left() + 1, opt.rect.bottom() + 5)) is None


def test_check_zone_covers_left_strip(setup):
    # The box is small; the whole cell left of the text toggles, like in 1.x.
    model, d = setup
    opt, ix, lay = laid_out(d, model, 0, 400)
    assert d.hit(opt, ix, QPoint(opt.rect.left(), lay.text.center().y())) == "check"
    assert lay.check.right() + 1 == lay.text.left() or lay.check.right() < lay.text.left()


def test_height_grows_when_expanded_and_shrinks_with_width(setup):
    model, d = setup
    row = NOTES.index(LONG)
    collapsed = d.sizeHint(option(400), model.index(row)).height()
    model.set_expanded(row, True)
    heights = [d.sizeHint(option(w), model.index(row)).height() for w in WIDTHS]
    assert all(h > collapsed for h in heights)
    assert heights == sorted(heights, reverse=True)
    assert heights[0] > heights[-1]


def test_collapsed_rows_have_one_height(setup):
    model, d = setup
    hs = {d.sizeHint(option(w), model.index(r)).height()
          for r in range(model.rowCount()) for w in WIDTHS}
    assert len(hs) == 1


def test_note_lines_fit_and_keep_text(setup):
    model, d = setup
    for row, width in cases(model):
        _, ix, lay = laid_out(d, model, row, width)
        if lay.note is None:
            continue
        opt = option(width)
        fm = QFontMetrics(d.note_font(opt.font))
        for line in lay.note_lines:
            assert fm.horizontalAdvance(line) <= lay.note.width(), (row, width, line)
        note = model.checklist.items[row].note
        # nothing lost or added except the spaces at the wrap points
        assert "".join(lay.note_lines).replace(" ", "") == note.replace("\n", "").replace(" ", "")
        assert len(lay.note_lines) >= note.count("\n") + 1


def test_blank_lines_kept(setup):
    model, d = setup
    row = NOTES.index("первая\n\nтретья")
    model.set_expanded(row, True)
    _, ix, lay = laid_out(d, model, row, 640)
    assert lay.note_lines == ("первая", "", "третья")


def test_long_word_is_cut(setup):
    model, d = setup
    row = NOTES.index("а" * 200)
    model.set_expanded(row, True)
    _, ix, lay = laid_out(d, model, row, 181)
    assert len(lay.note_lines) > 1 and "".join(lay.note_lines) == "а" * 200


def test_wrap_cache_returns_same_result(setup):
    _, d = setup
    f = d.note_font(QFont())
    assert d.wrap_note(LONG, 200, f) is d.wrap_note(LONG, 200, f)
    assert d.wrap_note(LONG, 200, f) != d.wrap_note(LONG, 400, f)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_paint_every_case(setup, qapp, mode):
    model, d = setup
    theme.apply_mode(qapp, mode)
    qapp.processEvents()
    try:
        model.toggle(1)
        for row, width in cases(model):
            for selected in (False, True):
                ix = model.index(row)
                h = d.sizeHint(option(width), ix).height()
                img = QImage(width, h, QImage.Format_ARGB32)
                img.fill(0)
                p = QPainter(img)
                d.paint(p, option(width, height=h, selected=selected), ix)
                p.end()
                assert not img.isNull()
    finally:
        theme.apply_mode(qapp, "light")
        qapp.processEvents()


def test_paint_draws_something_in_text_zone(setup, qapp):
    model, d = setup
    ix = model.index(0)
    h = d.sizeHint(option(400), ix).height()
    img = QImage(400, h, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    opt = option(400, height=h)
    d.paint(p, opt, ix)
    p.end()
    lay = d.layout(opt, ix)
    colors = {img.pixel(x, y) for x in range(lay.text.left(), lay.text.right())
              for y in range(lay.text.top(), lay.text.bottom())}
    assert len(colors) > 2  # glyphs, not an empty cell
