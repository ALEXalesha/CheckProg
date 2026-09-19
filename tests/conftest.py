"""Safety net: a test must never show a real dialog on the user's screen.

A real "Сохранить список" window blocks the test run until someone closes it.
Tests script the window's own dialog methods (tests/qtwin.py); any real Qt
dialog call fails at once instead of popping up.
"""
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

_QT_DIALOGS = {QMessageBox: ("question", "critical", "information", "warning"),
               QFileDialog: ("getOpenFileName", "getSaveFileName")}


def _refuse(name):
    def call(*args, **kwargs):
        raise AssertionError(f"real dialog {name}() opened during a test")
    return call


@pytest.fixture(autouse=True)
def no_real_qt_dialogs(monkeypatch):
    for cls, names in _QT_DIALOGS.items():
        for name in names:
            monkeypatch.setattr(cls, name, staticmethod(_refuse(name)))
