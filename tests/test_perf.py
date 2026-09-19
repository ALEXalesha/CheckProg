"""Resizing must stay smooth: the reason CheckProg moved from Tk to Qt."""
import time

from PySide6.QtWidgets import QApplication

from tests.qtwin import close_quietly, make_window

LONG = " ".join(["комментарий"] * 30) + "\nвторая строка"


def fill(win, n):
    for i in range(n):
        win.model.add(f"пункт номер {i} с довольно длинным текстом")
        win.model.set_note(i, LONG)
    win.model.expand_all(True)
    QApplication.processEvents()


def test_resize_step_under_16_ms(qtbot, tmp_path):
    win = make_window(qtbot, tmp_path)
    try:
        fill(win, 200)
        win.resize(520, 640)
        QApplication.processEvents()
        steps = 100
        start = time.perf_counter()
        for k in range(steps):
            win.resize(420 + k * 5, 640)  # every width is new: no cached wrapping
            QApplication.processEvents()
            win.view.viewport().repaint()
        mean_ms = (time.perf_counter() - start) / steps * 1000
        assert mean_ms < 16, f"{mean_ms:.1f} ms per resize step"
    finally:
        close_quietly(win)


def test_relayout_of_200_expanded_rows_is_fast(qtbot, tmp_path):
    win = make_window(qtbot, tmp_path)
    try:
        fill(win, 200)
        view, delegate = win.view, win.delegate
        start = time.perf_counter()
        for width in (300, 301, 302):
            opt = view.option_for(win.model.index(0))
            opt.rect.setWidth(width)
            for r in range(200):
                delegate.sizeHint(opt, win.model.index(r))
        per_pass = (time.perf_counter() - start) / 3 * 1000
        assert per_pass < 50, f"{per_pass:.1f} ms for 200 rows"
    finally:
        close_quietly(win)
