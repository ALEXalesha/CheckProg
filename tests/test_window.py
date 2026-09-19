"""MainWindow: list, mouse, keys, inline editing."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.qtwin import add, assert_in_sync, click, double_click, key, rows, win  # noqa: F401


def done(win):
    return [it.done for it in win.model.checklist.items]


def center(win, row):
    return win.view.visualRect(win.model.index(row)).center()


def test_starts_empty_and_clean(win):
    assert rows(win) == [] and win.selected_row() is None
    assert win.windowTitle() == "Без имени - CheckProg"
    assert_in_sync(win)


def test_add_by_enter_and_button(win):
    win.entry.setText("молоко")
    QTest.keyClick(win.entry, Qt.Key_Return)
    win.entry.setText("хлеб")
    QTest.mouseClick(win.add_button, Qt.LeftButton)
    assert rows(win) == ["молоко", "хлеб"]
    assert win.entry.text() == "" and win.selected_row() == 1
    assert win.windowTitle().startswith("*")
    assert_in_sync(win)


def test_empty_add_ignored(win):
    win.entry.setText("   ")
    win.add_item()
    assert rows(win) == [] and win.entry.text() == "   "


def test_click_box_toggles_and_selects(win):
    add(win, "a", "b")
    win.deselect()
    click(win, 1, "check")
    assert done(win) == [False, True] and win.selected_row() == 1
    click(win, 1, "check")
    assert done(win) == [False, False]
    assert_in_sync(win)


def test_double_click_on_box_toggles_twice(win):
    add(win, "a")
    double_click(win, 0, "check")
    assert done(win) == [False]


def test_click_arrow_expands_and_collapses(win):
    add(win, "a", "b")
    win.model.set_note(0, "заметка")
    h0 = win.view.visualRect(win.model.index(0)).height()
    click(win, 0, "arrow")
    assert win.model.checklist.items[0].expanded
    QApplication.processEvents()
    assert win.view.visualRect(win.model.index(0)).height() > h0
    click(win, 0, "arrow")
    assert not win.model.checklist.items[0].expanded
    QApplication.processEvents()
    assert win.view.visualRect(win.model.index(0)).height() == h0
    assert_in_sync(win)


def test_text_click_selects_second_click_deselects(win):
    add(win, "a", "b")
    win.deselect()
    click(win, 0)
    assert win.selected_row() == 0
    QTest.qWait(QApplication.doubleClickInterval() + 50)
    click(win, 0)
    assert win.selected_row() is None
    assert_in_sync(win)


def test_click_other_row_moves_selection(win):
    add(win, "a", "b")
    win.select(0)
    click(win, 1)
    assert win.selected_row() == 1


def test_click_below_rows_deselects(win):
    add(win, "a")
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(20, vp.height() - 5))
    assert win.selected_row() is None
    assert_in_sync(win)


def test_keys_space_delete_escape(win):
    add(win, "a", "b", "c")
    win.select(1)
    key(win, Qt.Key_Space)
    assert done(win) == [False, True, False]
    key(win, Qt.Key_Delete)
    assert rows(win) == ["a", "c"] and win.selected_row() == 1
    key(win, Qt.Key_Delete)
    assert rows(win) == ["a"] and win.selected_row() == 0
    key(win, Qt.Key_Escape)
    assert win.selected_row() is None
    key(win, Qt.Key_Delete)
    assert rows(win) == ["a"]
    assert_in_sync(win)


def test_delete_in_entry_does_not_delete_item(win):
    add(win, "a")
    win.select(0)
    win.entry.setText("xy")
    win.entry.setCursorPosition(0)
    QTest.keyClick(win.entry, Qt.Key_Delete)
    assert rows(win) == ["a"] and win.entry.text() == "y"


def test_delete_last_item_clears_selection(win):
    add(win, "a")
    win.select(0)
    win.delete_selected()
    assert win.selected_row() is None
    assert_in_sync(win)


def test_arrows_move_selection_over_expanded_notes(win):
    add(win, "a", "b", "c")
    win.model.set_note(0, "n")
    win.model.set_expanded(0, True)
    win.select(0)
    key(win, Qt.Key_Down)
    assert win.selected_row() == 1
    key(win, Qt.Key_Down)
    key(win, Qt.Key_Down)
    assert win.selected_row() == 2
    key(win, Qt.Key_Up)
    assert win.selected_row() == 1


def test_right_left_expand(win):
    add(win, "a", "b")
    win.model.set_note(1, "n")
    win.select(1)
    key(win, Qt.Key_Right)
    assert win.model.checklist.items[1].expanded
    key(win, Qt.Key_Left)
    assert not win.model.checklist.items[1].expanded
    win.select(0)
    key(win, Qt.Key_Right)  # no note: nothing to open
    assert not win.model.checklist.items[0].expanded


def test_expand_does_not_mark_dirty(win):
    add(win, "a")
    win.model.set_note(0, "n")
    win.model.checklist.dirty = False
    win._refresh_status()
    win.select(0)
    key(win, Qt.Key_Right)
    win.expand_all(False)
    win.expand_all(True)
    assert not win.model.checklist.dirty
    assert_in_sync(win)


def test_ctrl_up_down_move_with_selection(win):
    add(win, "a", "b", "c")
    win.select(0)
    key(win, Qt.Key_Down, Qt.ControlModifier)
    assert rows(win) == ["b", "a", "c"] and win.selected_row() == 1
    key(win, Qt.Key_Down, Qt.ControlModifier)
    key(win, Qt.Key_Down, Qt.ControlModifier)
    assert rows(win) == ["b", "c", "a"] and win.selected_row() == 2
    key(win, Qt.Key_Up, Qt.ControlModifier)
    assert rows(win) == ["b", "a", "c"] and win.selected_row() == 1
    assert_in_sync(win)


def test_move_actions_enabled_by_position(win):
    add(win, "a", "b")
    win.select(0)
    assert not win.act_up.isEnabled() and win.act_down.isEnabled()
    win.select(1)
    assert win.act_up.isEnabled() and not win.act_down.isEnabled()
    win.move_selected(-1)
    assert not win.act_up.isEnabled() and win.act_down.isEnabled()
    win.deselect()
    assert not any(a.isEnabled() for a in win.item_actions)


def test_f2_edit_enter_commits(win):
    add(win, "a", "b")
    win.select(0)
    key(win, Qt.Key_F2)
    editor = win.editor()
    assert editor is not None and editor.text() == "a"
    editor.setText("новое")
    QTest.keyClick(editor, Qt.Key_Return)
    QApplication.processEvents()  # the delegate commits/closes queued
    assert rows(win) == ["новое", "b"] and win.editor() is None
    assert_in_sync(win)


def test_edit_escape_cancels(win):
    add(win, "a")
    win.begin_edit(0)
    win.editor().setText("zzz")
    QTest.keyClick(win.editor(), Qt.Key_Escape)
    QApplication.processEvents()
    assert rows(win) == ["a"] and win.editor() is None


def test_edit_empty_keeps_old_text(win):
    add(win, "a")
    win.begin_edit(0)
    win.editor().setText("   ")
    QTest.keyClick(win.editor(), Qt.Key_Return)
    QApplication.processEvents()
    assert rows(win) == ["a"]


def test_double_click_text_edits(win):
    add(win, "a")
    double_click(win, 0, "text")
    assert win.editor() is not None
    win.end_edit(False)
    assert win.editor() is None and rows(win) == ["a"]


def test_other_action_commits_open_edit(win):
    add(win, "a", "b")
    win.begin_edit(0)
    win.editor().setText("a!")
    win.select(1)
    win.toggle_selected()
    assert rows(win) == ["a!", "b"] and done(win) == [False, True]
    assert win.editor() is None


def test_space_and_delete_in_editor_edit_text(win):
    add(win, "a")
    win.begin_edit(0)
    ed = win.editor()
    ed.setText("xy")
    ed.setCursorPosition(1)
    QTest.keyClick(ed, Qt.Key_Space)
    QTest.keyClick(ed, Qt.Key_Delete)
    assert ed.text() == "x " and done(win) == [False] and rows(win) == ["a"]
    win.end_edit(False)


def test_editor_sits_over_text_zone(win):
    add(win, "a")
    win.model.set_note(0, "n")
    win.begin_edit(0)
    QApplication.processEvents()
    ed_rect = win.editor().geometry()
    lay = win.delegate.layout(win.view.option_for(win.model.index(0)), win.model.index(0))
    assert ed_rect.left() == lay.text.left()
    assert not ed_rect.intersects(lay.check)
    win.end_edit(False)


def test_double_click_note_goes_to_panel(win):
    add(win, "a")
    win.model.set_note(0, "note")
    win.model.set_expanded(0, True)
    win.deselect()
    QApplication.processEvents()
    double_click(win, 0, "note")
    assert win.selected_row() == 0 and win.editor() is None
    assert win.focusWidget() is win.note_edit


def test_context_menu_mouse_and_keyboard(win):
    add(win, "a", "b")
    win.deselect()
    local = center(win, 1)
    gpos = win.view.viewport().mapToGlobal(local)
    QApplication.sendEvent(win.view.viewport(), QContextMenuEvent(QContextMenuEvent.Mouse, local, gpos))
    assert win.selected_row() == 1 and win.dialogs.infos[-1][0] == "menu"
    win.dialogs.infos.clear()
    win.deselect()
    QApplication.sendEvent(win.view.viewport(), QContextMenuEvent(QContextMenuEvent.Keyboard, QPoint(0, 0)))
    assert win.dialogs.infos == []  # nothing selected: no menu
    win.select(0)
    key(win, Qt.Key_F10, Qt.ShiftModifier)
    assert win.dialogs.infos[-1][0] == "menu"


def test_context_menu_below_rows_does_nothing(win):
    add(win, "a")
    vp = win.view.viewport()
    local = QPoint(10, vp.height() - 3)
    QApplication.sendEvent(win.view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, vp.mapToGlobal(local)))
    assert win.dialogs.infos == []


def test_item_menu_has_six_actions(win):
    names = [a.text().split("	")[0] for a in win.item_menu.actions() if not a.isSeparator()]
    assert names == ["Отметить / снять отметку", "Изменить", "Комментарий", "Удалить",
                     "Выше", "Ниже"]


def test_drop_moves_item_and_selection(win):
    add(win, "a", "b", "c")
    win.select(0)
    root = win.model.index(0).parent()
    assert win.model.moveRows(root, 0, 1, root, 3)
    assert rows(win) == ["b", "c", "a"] and win.selected_row() == 2
    assert_in_sync(win)


def test_press_on_selected_row_arms_deselect_only_without_move(win):
    add(win, "a", "b")
    win.select(0)
    view = win.view
    vp = view.viewport()
    p = center(win, 0)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p)
    assert view._toggle_off_on_release == 0
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p)
    assert win.selected_row() is None
