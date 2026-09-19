"""MainWindow: note panel, files, theme, layout-independent keys, random sequences."""
import json
import random

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from checkprog import theme
from checkprog.model import Checklist, Item, clean_note
from tests.qtwin import add, assert_in_sync, close_quietly, make_window, rows, win  # noqa: F401


def type_note(win, text):
    win.note_edit.moveCursor(win.note_edit.textCursor().MoveOperation.End)
    win.note_edit.insertPlainText(text)


# ---- note panel -----------------------------------------------------------------

def test_panel_disabled_without_selection(win):
    assert not win.note_edit.isEnabled()
    assert "выделите пункт" in win.note_label.text()


def test_selecting_shows_note_and_typing_saves(win):
    add(win, "a", "b")
    win.model.checklist.dirty = False
    win.select(0)
    assert win.note_edit.isEnabled() and "«a»" in win.note_label.text()
    type_note(win, "купить\nфартук")
    assert win.model.checklist.items[0].note == "купить\nфартук"
    assert win.model.checklist.dirty and win.windowTitle().startswith("*")
    win.select(1)
    assert win.note_edit.toPlainText() == ""
    win.select(0)
    assert win.note_edit.toPlainText() == "купить\nфартук"
    assert_in_sync(win)


def test_note_follows_item_when_moved(win):
    add(win, "a", "b", "c")
    win.select(0)
    type_note(win, "A")
    win.move_selected(1)
    win.move_selected(1)
    type_note(win, "!")
    assert [it.note for it in win.model.checklist.items] == ["", "", "A!"]
    assert win.selected_row() == 2
    assert_in_sync(win)


def test_note_never_goes_to_neighbour_after_delete(win):
    add(win, "a", "b")
    win.select(0)
    type_note(win, "A")
    win.delete_selected()
    assert win.selected_row() == 0 and win.model.checklist.items[0].text == "b"
    assert win.note_edit.toPlainText() == ""
    type_note(win, "B")
    assert [it.note for it in win.model.checklist.items] == ["B"]


def test_undo_does_not_cross_items(win):
    add(win, "a", "b")
    win.select(0)
    type_note(win, "A")
    win.select(1)
    win.note_edit.undo()
    assert win.note_edit.toPlainText() == ""
    assert win.model.checklist.items[0].note == "A"


def test_undo_in_panel_updates_item(win):
    add(win, "a")
    win.select(0)
    type_note(win, "x")
    win.note_edit.undo()
    assert win.model.checklist.items[0].note == ""


def test_open_note_lines_follow_typing(win):
    add(win, "a")
    win.select(0)
    type_note(win, "раз")
    win.set_expanded(0, True)
    h1 = win.view.visualRect(win.model.index(0)).height()
    type_note(win, "\nдва\nтри")
    QApplication.processEvents()
    assert win.view.visualRect(win.model.index(0)).height() > h1


def test_clearing_note_collapses_and_hides_arrow(win):
    add(win, "a")
    win.select(0)
    type_note(win, "x")
    win.set_expanded(0, True)
    win.note_edit.clear()
    item = win.model.checklist.items[0]
    assert item.note == "" and not item.expanded
    lay = win.delegate.layout(win.view.option_for(win.model.index(0)), win.model.index(0))
    assert lay.arrow is None


def test_whitespace_note_is_empty(win):
    add(win, "a")
    win.select(0)
    type_note(win, "  \n ")
    assert win.model.checklist.items[0].note == ""
    assert_in_sync(win)


def test_rename_toggle_keep_panel_text_and_cursor(win):
    add(win, "a")
    win.select(0)
    type_note(win, "abc ")  # trailing space is not saved but stays in the editor
    win.toggle_selected()
    win.begin_edit(0)
    win.editor().setText("b")
    win.end_edit()
    assert win.note_edit.toPlainText() == "abc "
    assert win.model.checklist.items[0].note == "abc"
    assert "«b»" in win.note_label.text()  # the label follows a rename


def test_edit_note_action_focuses_panel(win):
    add(win, "a")
    win.select(0)
    win.edit_note()
    assert win.focusWidget() is win.note_edit
    win.deselect()
    win.edit_note()  # harmless without a selection


# ---- files -------------------------------------------------------------------------

def test_save_as_and_title(win, tmp_path):
    add(win, "a")
    win.select(0)
    type_note(win, "n")
    target = tmp_path / "list.json"
    win.dialogs.save_paths.append(str(target))
    assert win.save()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["items"] == [{"text": "a", "done": False, "note": "n"}]
    assert win.windowTitle() == "list.json - CheckProg"
    assert win.settings["last_file"] == str(target)
    assert_in_sync(win)


def test_save_path_without_extension_gets_json(win, tmp_path):
    win.dialogs.save_paths.append(str(tmp_path / "plain"))
    win._ask_save_path = type(win)._ask_save_path.__get__(win)  # real method, fake dialog
    from PySide6.QtWidgets import QFileDialog
    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(tmp_path / "plain"), ""))
    try:
        assert win.save_as()
    finally:
        QFileDialog.getSaveFileName = orig
    assert (tmp_path / "plain.json").exists()


def test_open_and_last_file_on_next_start(qtbot, tmp_path):
    path = tmp_path / "l.json"
    Checklist([Item("x"), Item("y", True, "note")]).save(str(path))
    w = make_window(qtbot, tmp_path)
    w.dialogs.open_paths.append(str(path))
    w.open_file()
    assert rows(w) == ["x", "y"] and w.selected_row() == 0
    assert_in_sync(w)
    close_quietly(w)
    w2 = make_window(qtbot, tmp_path)
    assert rows(w2) == ["x", "y"] and not w2.model.checklist.dirty
    close_quietly(w2)


def test_initial_path_beats_last_file(qtbot, tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    Checklist([Item("A")]).save(str(a))
    Checklist([Item("B")]).save(str(b))
    w = make_window(qtbot, tmp_path, settings={"last_file": str(a)}, initial_path=str(b))
    assert rows(w) == ["B"]
    close_quietly(w)


def test_missing_last_file_is_forgotten_quietly(qtbot, tmp_path):
    w = make_window(qtbot, tmp_path, settings={"last_file": str(tmp_path / "gone.json")})
    assert rows(w) == [] and w.dialogs.errors == []
    assert "last_file" not in w.settings
    close_quietly(w)


def test_bad_file_keeps_current_list(win, tmp_path):
    add(win, "keep")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert not win.open_path(str(bad))
    assert rows(win) == ["keep"] and "JSON" in win.dialogs.errors[-1]


def test_missing_file_explicit_open_reports(win, tmp_path):
    assert not win.open_path(str(tmp_path / "nope.json"))
    assert "не найден" in win.dialogs.errors[-1]


def test_new_asks_and_cancel_keeps(win):
    add(win, "a")
    win.dialogs.save_answers.append("cancel")
    win.new_file()
    assert rows(win) == ["a"] and win.dialogs.asked == ["Без имени"]
    win.dialogs.save_answers.append("discard")
    win.new_file()
    assert rows(win) == [] and not win.model.checklist.dirty
    assert_in_sync(win)


def test_new_with_save_that_is_cancelled_keeps(win):
    add(win, "a")
    win.dialogs.save_answers.append("save")
    win.dialogs.save_paths.append("")  # user closes the save dialog
    win.new_file()
    assert rows(win) == ["a"]


def test_close_asks_and_can_cancel(win):
    add(win, "a")
    win.dialogs.save_answers.append("cancel")
    assert not win.close()
    assert win.isVisible()


def test_clean_list_closes_without_asking(qtbot, tmp_path):
    w = make_window(qtbot, tmp_path)
    assert w.close() and w.dialogs.asked == []


def test_save_error_is_reported(win, tmp_path):
    add(win, "a")
    win.dialogs.save_paths.append(str(tmp_path / "missing_dir" / "x.json"))
    assert not win.save()
    assert win.dialogs.errors and win.model.checklist.dirty


def test_open_commits_pending_edit_nowhere(win, tmp_path):
    path = tmp_path / "o.json"
    Checklist([Item("new")]).save(str(path))
    add(win, "old")
    win.model.checklist.dirty = False
    win.begin_edit(0)
    win.editor().setText("changed")
    assert win.open_path(str(path))
    assert rows(win) == ["new"] and win.editor() is None


def test_about_and_help(win):
    win.show_about()
    win.show_help()
    (t1, about), (t2, help_text) = win.dialogs.infos
    assert "2.0.0" in about or "CheckProg" in about
    assert "portable" in about and "Ctrl+N" in help_text


# ---- theme -------------------------------------------------------------------------

def test_theme_actions_switch_and_persist(qtbot, tmp_path):
    w = make_window(qtbot, tmp_path)
    try:
        w.theme_actions["dark"].trigger()
        QApplication.processEvents()
        assert theme.is_dark(QApplication.palette())
        assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["theme"] == "dark"
        w.theme_actions["light"].trigger()
        QApplication.processEvents()
        assert not theme.is_dark(QApplication.palette())
        assert [m for m, a in w.theme_actions.items() if a.isChecked()] == ["light"]
    finally:
        close_quietly(w)
    w2 = make_window(qtbot, tmp_path)
    assert w2.theme_mode == "light" and w2.theme_actions["light"].isChecked()
    close_quietly(w2)
    theme.apply_mode(QApplication.instance(), "light")


def test_bad_theme_setting_falls_back(qtbot, tmp_path):
    w = make_window(qtbot, tmp_path, settings={"theme": "purple"})
    assert w.theme_mode == "system" and w.theme_actions["system"].isChecked()
    close_quietly(w)
    theme.apply_mode(QApplication.instance(), "light")


# ---- keys in any layout ------------------------------------------------------------

def native_key(widget, qt_key, vk, mods, text=""):
    ev = QKeyEvent(QEvent.KeyPress, qt_key, mods, 0, vk, 0, text)
    QApplication.sendEvent(widget, ev)
    return ev


def test_ctrl_s_in_russian_layout_saves(win, tmp_path):
    add(win, "a")
    win.dialogs.save_paths.append(str(tmp_path / "r.json"))
    native_key(win.view, ord("Ы"), 0x53, Qt.ControlModifier, "ы")
    assert (tmp_path / "r.json").exists()


def test_ctrl_shift_s_in_russian_layout_saves_as(win, tmp_path):
    win.dialogs.save_paths.append(str(tmp_path / "r2.json"))
    native_key(win.entry, ord("Ы"), 0x53, Qt.ControlModifier | Qt.ShiftModifier, "Ы")
    assert (tmp_path / "r2.json").exists()


def test_ctrl_c_v_in_russian_layout_in_entry(win):
    win.entry.setText("копия")
    win.entry.selectAll()
    native_key(win.entry, ord("С"), 0x43, Qt.ControlModifier, "с")
    assert QApplication.clipboard().text() == "копия"
    win.entry.clear()
    native_key(win.entry, ord("М"), 0x56, Qt.ControlModifier, "м")
    assert win.entry.text() == "копия"


def test_ctrl_a_z_in_russian_layout_in_panel(win):
    add(win, "a")
    win.select(0)
    type_note(win, "текст")
    native_key(win.note_edit, ord("Ф"), 0x41, Qt.ControlModifier, "ф")
    assert win.note_edit.textCursor().selectedText() == "текст"
    native_key(win.note_edit, ord("Я"), 0x5A, Qt.ControlModifier, "я")
    assert win.note_edit.toPlainText() == ""
    assert win.model.checklist.items[0].note == ""


def test_altgr_is_left_alone(win):
    win.entry.setText("")
    ev = native_key(win.entry, ord("С"), 0x43, Qt.ControlModifier | Qt.AltModifier, "")
    assert QApplication.clipboard() is not None and win.entry.text() == ""


def test_alt_letters_open_menus_in_english_layout(win):
    opened = []
    win.open_menu = opened.append
    for vk, qt_key, name in ((0x41, Qt.Key_A, "file"), (0x47, Qt.Key_G, "item"),
                             (0x44, Qt.Key_D, "view"), (0x43, Qt.Key_C, "help")):
        native_key(win.view, qt_key, vk, Qt.AltModifier, qt_key and chr(vk).lower())
    assert opened == ["file", "item", "view", "help"]


def test_menu_titles_have_russian_mnemonics(win):
    assert [m.title() for m in win.bar_menus.values()] == ["&Файл", "&Пункт", "&Вид", "&Справка"]


def test_ctrl_letter_latin_is_not_duplicated(win, tmp_path):
    # A Latin key event that reaches the filter is Qt's job, not ours.
    add(win, "a")
    native_key(win.view, Qt.Key_S, 0x53, Qt.ControlModifier, "s")
    assert win.dialogs.save_paths == [] and not (tmp_path / "x.json").exists()


# ---- random sequences ----------------------------------------------------------------

def check(win, step):
    assert_in_sync(win)
    sel = win.selected_row()
    if sel is not None:
        assert clean_note(win.note_edit.toPlainText()) == win.model.checklist.items[sel].note, step


def test_random_sequences(win):
    for seed in range(25):
        rng = random.Random(seed)
        win.model.set_checklist(Checklist())
        log = []
        for n in range(60):
            op = rng.choice(["add", "select", "type", "delete", "move", "drop", "toggle",
                             "deselect", "rename", "expand", "expand", "expand_all", "click"])
            size = win.model.rowCount()
            log.append(op)
            if op == "add":
                add(win, f"п{n}")
            elif op == "select" and size:
                win.select(rng.randrange(size))
            elif op == "type" and win.note_edit.isEnabled():  # a disabled panel takes no typing
                type_note(win, rng.choice(["x", "\n", " ", "да"]))
            elif op == "delete":
                win.delete_selected()
            elif op == "move":
                win.move_selected(rng.choice([-1, 1]))
            elif op == "drop" and size:
                root = win.model.index(0).parent()
                win.model.moveRows(root, rng.randrange(size), 1, root, rng.randrange(size + 1))
            elif op == "toggle":
                win.toggle_selected()
            elif op == "deselect":
                win.deselect()
            elif op == "rename" and win.selected_row() is not None:
                win.begin_edit(win.selected_row())
                win.editor().setText(win.editor().text() + "!")
                win.end_edit()
            elif op == "expand" and size:
                win.toggle_expanded(rng.randrange(size))
            elif op == "expand_all":
                win.expand_all(rng.random() < 0.5)
            elif op == "click" and size:
                from tests.qtwin import click
                click(win, rng.randrange(size), rng.choice(["check", "text"]))
                QTest.qWait(QApplication.doubleClickInterval() + 10) if rng.random() < 0.1 else None
            check(win, f"seed {seed}: {log}")


# ---- geometry ------------------------------------------------------------------

def test_long_item_name_does_not_widen_minimum(win):
    base = win.minimumSizeHint().width()
    add(win, "очень длинное название пункта " * 3)
    win.select(0)
    QApplication.processEvents()
    assert win.minimumSizeHint().width() <= max(base, 360)
    win.resize(360, 420)
    QApplication.processEvents()
    assert win.width() <= 380


def test_minimum_size_is_usable(win):
    m = win.minimumSize()
    assert 300 <= m.width() <= 400 and 300 <= m.height() <= 420
