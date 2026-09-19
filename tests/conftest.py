"""Safety net: a test must never show a real dialog on the user's screen.

A real "Сохранить список" window blocks the test run until someone closes it.
Tests that expect a dialog patch it themselves (their patch wins, being applied
later); any other call fails at once instead of popping up.
"""
from unittest import mock

import pytest

from checkprog import app as app_module

_DIALOGS = {
    app_module.filedialog: ("askopenfilename", "asksaveasfilename"),
    app_module.messagebox: ("askyesnocancel", "showerror", "showinfo"),
}


def _refuse(name):
    def call(*args, **kwargs):
        raise AssertionError(f"real dialog {name}() opened during a test")
    return call


@pytest.fixture(autouse=True)
def no_real_dialogs():
    patches = [mock.patch.object(module, name, side_effect=_refuse(name))
               for module, names in _DIALOGS.items() for name in names]
    for p in patches:
        p.start()
    yield
    for p in reversed(patches):
        p.stop()


# ---- Qt ---------------------------------------------------------------------
from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

_QT_DIALOGS = {QMessageBox: ("question", "critical", "information", "warning"),
               QFileDialog: ("getOpenFileName", "getSaveFileName")}


@pytest.fixture(autouse=True)
def no_real_qt_dialogs(monkeypatch):
    for cls, names in _QT_DIALOGS.items():
        for name in names:
            monkeypatch.setattr(cls, name, staticmethod(_refuse(f"Qt {name}")))
