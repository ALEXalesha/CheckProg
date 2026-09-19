import random

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtTest import QAbstractItemModelTester

from checkprog.listmodel import ChecklistModel, ExpandedRole, ItemRole, NoteRole
from checkprog.model import Checklist, Item


@pytest.fixture
def model(qapp):
    m = ChecklistModel()
    m._tester = QAbstractItemModelTester(
        m, QAbstractItemModelTester.FailureReportingMode.Fatal)
    return m


def texts(m):
    return [m.data(m.index(r), Qt.DisplayRole) for r in range(m.rowCount())]


def fill(m, *names):
    for n in names:
        m.add(n)
    m.checklist.dirty = False


def signals(m, *names):
    log = []
    for name in names:
        getattr(m, name).connect(lambda *a, name=name: log.append((name, a)))
    return log


def test_empty():
    m = ChecklistModel()
    assert m.rowCount() == 0
    assert m.checklist.items == ()


def test_add_inserts_row_and_marks_dirty(model):
    log = signals(model, "rowsAboutToBeInserted", "rowsInserted", "changed")
    assert model.add("  молоко  ") == 0
    assert texts(model) == ["молоко"]
    assert model.checklist.dirty
    assert [n for n, _ in log] == ["rowsAboutToBeInserted", "rowsInserted", "changed"]


def test_add_empty_is_ignored(model):
    log = signals(model, "rowsInserted", "changed")
    assert model.add(" \t\n ") is None
    assert model.rowCount() == 0 and log == []


def test_roles(model):
    fill(model, "a")
    model.set_note(0, "n")
    ix = model.index(0)
    assert model.data(ix, Qt.DisplayRole) == "a"
    assert model.data(ix, Qt.EditRole) == "a"
    assert model.data(ix, Qt.CheckStateRole) == Qt.Unchecked
    assert model.data(ix, NoteRole) == "n"
    assert model.data(ix, ExpandedRole) is False
    assert model.data(ix, ItemRole) is model.checklist.items[0]
    assert "n" in model.data(ix, Qt.ToolTipRole)
    assert model.data(model.index(5), Qt.DisplayRole) is None


def test_tooltip_wraps_and_hides_when_expanded(model):
    fill(model, "a", "b")
    model.set_note(0, "длинный <текст> " * 40 + "\nвторая")
    tip = model.data(model.index(0), Qt.ToolTipRole)
    assert tip.startswith("<p") and "&lt;текст&gt;" in tip and "<br>" in tip  # rich text wraps
    model.set_expanded(0, True)
    assert model.data(model.index(0), Qt.ToolTipRole) is None  # already on screen
    assert model.data(model.index(1), Qt.ToolTipRole) is None  # no note, no tooltip


def test_toggle_emits_data_changed_for_one_row(model):
    fill(model, "a", "b")
    log = signals(model, "dataChanged", "changed")
    model.toggle(1)
    assert model.data(model.index(1), Qt.CheckStateRole) == Qt.Checked
    (name, (top, bottom, roles)), changed = log
    assert (top.row(), bottom.row()) == (1, 1) and changed[0] == "changed"
    assert model.checklist.dirty


def test_set_data_check_state_and_edit(model):
    fill(model, "a")
    assert model.setData(model.index(0), Qt.Checked, Qt.CheckStateRole)
    assert model.checklist.items[0].done
    assert model.setData(model.index(0), Qt.Unchecked.value, Qt.CheckStateRole)
    assert not model.checklist.items[0].done
    assert model.setData(model.index(0), "b", Qt.EditRole)
    assert texts(model) == ["b"]
    assert not model.setData(model.index(0), "   ", Qt.EditRole)
    assert texts(model) == ["b"]
    assert not model.setData(model.index(3), "x", Qt.EditRole)


def test_rename_noop_emits_nothing(model):
    fill(model, "a")
    log = signals(model, "dataChanged", "changed")
    assert not model.rename(0, "a")
    assert not model.rename(0, "")
    assert log == [] and not model.checklist.dirty


def test_note_and_expand(model):
    fill(model, "a", "b")
    assert not model.set_expanded(0, True)  # no note: nothing to show
    assert model.set_note(0, " текст ")
    model.checklist.dirty = False
    log = signals(model, "dataChanged")
    assert model.set_expanded(0, True)
    assert model.data(model.index(0), ExpandedRole) is True
    assert not model.checklist.dirty  # view state only
    (_, (top, bottom, roles)), = log
    assert Qt.SizeHintRole in roles and top.row() == 0
    assert not model.set_expanded(0, True)


def test_clearing_note_collapses(model):
    fill(model, "a")
    model.set_note(0, "x")
    model.set_expanded(0, True)
    model.set_note(0, "")
    item = model.checklist.items[0]
    assert item.note == "" and not item.expanded


def test_expand_all(model):
    fill(model, "a", "b", "c")
    model.set_note(0, "x")
    model.set_note(2, "y")
    model.checklist.dirty = False
    assert model.expand_all(True)
    assert [i.expanded for i in model.checklist.items] == [True, False, True]
    assert not model.expand_all(True)
    assert model.expand_all(False)
    assert not any(i.expanded for i in model.checklist.items)
    assert not model.checklist.dirty


def test_remove(model):
    fill(model, "a", "b", "c")
    log = signals(model, "rowsAboutToBeRemoved", "rowsRemoved", "changed")
    removed = model.remove(1)
    assert removed.text == "b" and texts(model) == ["a", "c"]
    assert [n for n, _ in log] == ["rowsAboutToBeRemoved", "rowsRemoved", "changed"]


@pytest.mark.parametrize("src, dst, expected", [
    (0, 2, ["b", "c", "a", "d"]), (3, 0, ["d", "a", "b", "c"]),
    (1, 2, ["a", "c", "b", "d"]), (2, 1, ["a", "c", "b", "d"]),
    (1, 99, ["a", "c", "d", "b"]), (2, -5, ["c", "a", "b", "d"])])
def test_move(model, src, dst, expected):
    fill(model, "a", "b", "c", "d")
    log = signals(model, "rowsMoved")
    final = model.move(src, dst)
    assert texts(model) == expected
    assert texts(model)[final] == ["a", "b", "c", "d"][src]
    assert len(log) == 1


def test_move_to_same_place_is_noop(model):
    fill(model, "a", "b")
    log = signals(model, "rowsMoved", "changed")
    assert model.move(1, 1) == 1
    assert log == [] and not model.checklist.dirty


@pytest.mark.parametrize("src, dest_child, expected", [
    (0, 2, ["b", "a", "c"]), (0, 3, ["b", "c", "a"]), (2, 0, ["c", "a", "b"]),
    (1, 0, ["b", "a", "c"])])
def test_move_rows_uses_qt_destination(model, src, dest_child, expected):
    # QListView drops call moveRows with Qt's "insert before destChild" rule.
    fill(model, "a", "b", "c")
    assert model.moveRows(QModelIndex(), src, 1, QModelIndex(), dest_child)
    assert texts(model) == expected


@pytest.mark.parametrize("src, dest_child", [(0, 0), (0, 1), (1, 1), (1, 2)])
def test_move_rows_onto_itself_refused(model, src, dest_child):
    fill(model, "a", "b", "c")
    assert not model.moveRows(QModelIndex(), src, 1, QModelIndex(), dest_child)
    assert texts(model) == ["a", "b", "c"]


def test_move_rows_refuses_many_or_nested(model):
    fill(model, "a", "b", "c")
    assert not model.moveRows(QModelIndex(), 0, 2, QModelIndex(), 3)
    assert not model.moveRows(model.index(0), 0, 1, QModelIndex(), 3)


def test_flags(model):
    fill(model, "a")
    f = model.flags(model.index(0))
    for flag in (Qt.ItemIsEnabled, Qt.ItemIsSelectable, Qt.ItemIsEditable,
                 Qt.ItemIsDragEnabled, Qt.ItemNeverHasChildren):
        assert f & flag
    assert not f & Qt.ItemIsDropEnabled  # drops go between rows, never onto one
    assert model.flags(QModelIndex()) & Qt.ItemIsDropEnabled
    assert model.supportedDropActions() == Qt.MoveAction


def test_set_checklist_resets(model):
    fill(model, "a")
    log = signals(model, "modelReset", "changed")
    cl = Checklist([Item("x"), Item("y", True)])
    model.set_checklist(cl)
    assert model.checklist is cl and texts(model) == ["x", "y"]
    assert [n for n, _ in log] == ["modelReset", "changed"]


def test_random_operations_match_shadow(model):
    rng = random.Random(7)
    shadow = []
    for step in range(400):
        op = rng.choice(["add", "toggle", "rename", "note", "expand", "remove", "move",
                         "moveRows", "all"])
        n = len(shadow)
        if op == "add":
            t = rng.choice(["a", "b", " ", "в г"])
            if model.add(t) is not None:
                shadow.append([t.strip(), False, "", False])
        elif op == "toggle" and n:
            i = rng.randrange(n)
            model.toggle(i)
            shadow[i][1] = not shadow[i][1]
        elif op == "rename" and n:
            i = rng.randrange(n)
            t = rng.choice(["x", "", "y z"])
            if model.rename(i, t):
                shadow[i][0] = t
        elif op == "note" and n:
            i = rng.randrange(n)
            t = rng.choice(["", "note", "a\nb"])
            model.set_note(i, t)
            shadow[i][2] = t
            if not t:
                shadow[i][3] = False
        elif op == "expand" and n:
            i = rng.randrange(n)
            want = rng.random() < 0.5
            model.set_expanded(i, want)
            if shadow[i][2]:
                shadow[i][3] = want
        elif op == "all":
            want = rng.random() < 0.5
            model.expand_all(want)
            for s in shadow:
                if s[2]:
                    s[3] = want
        elif op == "remove" and n:
            i = rng.randrange(n)
            model.remove(i)
            shadow.pop(i)
        elif op == "move" and n:
            i, j = rng.randrange(n), rng.randrange(-1, n + 1)
            final = model.move(i, j)
            shadow.insert(final, shadow.pop(i))
        elif op == "moveRows" and n:
            i, d = rng.randrange(n), rng.randrange(n + 1)
            if model.moveRows(QModelIndex(), i, 1, QModelIndex(), d):
                shadow.insert(d - 1 if d > i else d, shadow.pop(i))
        got = [[it.text, it.done, it.note, it.expanded] for it in model.checklist.items]
        assert got == shadow, (step, op)
        assert model.rowCount() == len(shadow)
