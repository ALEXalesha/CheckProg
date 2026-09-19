"""Helpers for driving MainWindow in tests without showing it on screen."""
import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from checkprog import window as window_module
from checkprog.model import clean_note
from checkprog.settings import Paths
from checkprog.window import MainWindow


class Dialogs:
    """Scripted answers for the window's dialog methods; unexpected calls fail."""

    def __init__(self):
        self.save_answers = []
        self.open_paths = []
        self.save_paths = []
        self.errors = []
        self.infos = []
        self.asked = []

    def install(self, win):
        def ask_save(name):
            self.asked.append(name)
            assert self.save_answers, f"unexpected «Сохранить изменения в {name}?»"
            return self.save_answers.pop(0)

        def ask_open():
            assert self.open_paths, "unexpected open dialog"
            return self.open_paths.pop(0)

        def ask_save_path(suggested):
            assert self.save_paths, f"unexpected save dialog ({suggested})"
            return self.save_paths.pop(0)

        win._ask_save = ask_save
        win._ask_open_path = ask_open
        win._ask_save_path = ask_save_path
        win._error = self.errors.append
        win._info = lambda title, text: self.infos.append((title, text))
        win.popup_item_menu = lambda pos: self.infos.append(("menu", pos))


def make_window(qtbot, tmp_path, initial_path=None, settings=None, dialogs=None):
    paths = Paths(str(tmp_path / "settings.json"), str(tmp_path / "lists"), True)
    if settings is not None:
        import json
        (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    dialogs = dialogs or Dialogs()
    orig = (MainWindow._error, MainWindow._ask_save)
    # Dialogs may be needed during __init__ (a bad initial file): patch the class first.
    MainWindow._error = lambda self, text: dialogs.errors.append(text)
    try:
        win = MainWindow(paths, initial_path)
    finally:
        MainWindow._error, MainWindow._ask_save = orig
    dialogs.install(win)
    win.setAttribute(Qt.WA_DontShowOnScreen)
    win.show()
    # Not qtbot.addWidget: it closes the window before our teardown clears dirty.
    QTest.qWait(1)
    win.dialogs = dialogs
    return win


def close_quietly(win):
    win.model.checklist.dirty = False
    win.close()
    win.deleteLater()


def rows(win):
    m = win.model
    return [m.data(m.index(r)) for r in range(m.rowCount())]


def zone_point(win, row, zone):
    view = win.view
    index = win.model.index(row)
    opt = view.option_for(index)
    lay = win.delegate.layout(opt, index)
    rect = {"check": lay.check, "text": lay.text, "arrow": lay.arrow, "note": lay.note}[zone]
    assert rect is not None, (row, zone)
    return rect.center()


def click(win, row, zone="text", button=Qt.LeftButton):
    QTest.mouseClick(win.view.viewport(), button, Qt.NoModifier, zone_point(win, row, zone))


def double_click(win, row, zone="text"):
    pos = zone_point(win, row, zone)
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, pos)


def key(win, k, mods=Qt.NoModifier, widget=None):
    QTest.keyClick(widget or win.view, k, mods)


def assert_in_sync(win):
    cl = win.model.checklist
    assert rows(win) == [it.text for it in cl.items]
    assert win.model.rowCount() == len(cl)
    title = win.windowTitle()
    assert title.startswith("*") == cl.dirty, title
    name = os.path.basename(cl.path) if cl.path else window_module.UNTITLED
    assert title.lstrip("*") == f"{name} - CheckProg"
    assert win.progress_label.text() == f"Выполнено: {cl.done_count} из {cl.total}"
    assert win.progress_bar.value() == cl.done_count
    sel = win.selected_row()
    if sel is None:
        assert not win.note_edit.isEnabled()
        assert win.note_edit.toPlainText() == ""
        assert not win.act_delete.isEnabled()
    else:
        assert 0 <= sel < len(cl)
        assert win.note_edit.isEnabled()
        assert clean_note(win.note_edit.toPlainText()) == cl.items[sel].note
        assert win.act_delete.isEnabled()
    for r in range(win.model.rowCount()):
        item = cl.items[r]
        assert not (item.expanded and not item.note)


@pytest.fixture
def win(qtbot, tmp_path):
    w = make_window(qtbot, tmp_path)
    yield w
    close_quietly(w)


def add(win, *texts):
    for t in texts:
        win.entry.setText(t)
        win.add_item()
    assert_in_sync(win)
