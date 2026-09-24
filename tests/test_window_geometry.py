"""Размер и место окна между запусками (2.1.0): window_geometry и MainWindow."""
import json

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QMainWindow

from checkprog import window_geometry
from tests.qtwin import close_quietly, make_window


def _main_area():
    return QApplication.primaryScreen().availableGeometry()


def test_a_window_comes_back_where_and_how_large_it_was(qtbot, tmp_path):
    win = make_window(qtbot, tmp_path)
    # Экран самого окна, а не основной: скрытое окно (WA_DontShowOnScreen) не узнаёт,
    # что его передвинули на другой монитор, и Qt при восстановлении вернул бы его на
    # «свой». С двумя мониторами итог зависел от того, где стояла мышь.
    area = win.screen().availableGeometry()
    want = QRect(area.x() + 40, area.y() + 60, 700, 480)
    win.setGeometry(want)
    close_quietly(win)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert isinstance(saved.get("window"), str)
    again = make_window(qtbot, tmp_path)
    try:
        assert (again.width(), again.height()) == (700, 480)
        assert (again.x(), again.y()) == (want.x(), want.y())
    finally:
        close_quietly(again)


def test_a_broken_line_in_the_settings_gives_the_default_size(qtbot, tmp_path):
    for bad in ["@@@", "", 42, None, "AAAA", "aGVsbG8="]:
        win = make_window(qtbot, tmp_path, settings={"window": bad})
        try:
            assert (win.width(), win.height()) == (560, 660), bad
        finally:
            win.model.checklist.dirty = False
            win.deleteLater()


def test_a_window_saved_far_off_screen_is_not_restored_there(qtbot):
    far = QMainWindow()
    far.resize(400, 300)
    far.move(-30000, -30000)
    text = window_geometry.encode(far)
    win = QMainWindow()
    win.resize(500, 350)
    window_geometry.restore(win, text)
    # Либо Qt сам перенёс окно на экран, либо проверка отказалась - заголовок виден.
    assert window_geometry.title_on_screen(win)
    far.deleteLater()
    win.deleteLater()


def test_the_title_bar_must_be_on_a_screen():
    win = QMainWindow()
    area = _main_area()
    win.setGeometry(area.x() + 10, area.y() + 10, 400, 300)
    assert window_geometry.title_on_screen(win)
    win.setGeometry(area.x() + 10, area.y() + area.height() + 500, 400, 300)
    assert not window_geometry.title_on_screen(win)
    win.deleteLater()
