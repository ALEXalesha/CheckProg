"""Entry point: sets up QApplication and opens the main window."""
import os
import sys
import traceback

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QStyleFactory

from checkprog import APP_NAME
from checkprog.settings import resolve_paths
from checkprog.window import MainWindow

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
UI_FONT_SIZE = 10
STYLE = "windows11"  # Qt falls back to windowsvista on Windows 10 by itself
_translators = []  # kept alive: Qt only holds a pointer


def _report_error(exc, value, tb):
    # A --windowed build has no console, so an uncaught error would vanish silently.
    details = "".join(traceback.format_exception(exc, value, tb))
    if sys.stderr:
        sys.stderr.write(details)
    if QApplication.instance() is not None:
        QMessageBox.critical(None, APP_NAME,
                             f"Непредвиденная ошибка: {value}\n\n{details[-1500:]}")


def create_app(argv=None):
    app = QApplication.instance() or QApplication(list(argv or sys.argv[:1]))
    app.setApplicationName(APP_NAME)
    if STYLE in [k.lower() for k in QStyleFactory.keys()]:
        app.setStyle(STYLE)
    font = QFont(app.font())
    font.setPointSize(UI_FONT_SIZE)
    app.setFont(font)
    if os.path.isfile(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    _install_russian(app)
    return app


def _install_russian(app):
    # Standard buttons and file dialogs ("Save", "Cancel") come from Qt's own
    # catalogue; the interface is Russian, so they must be too.
    if _translators:
        return
    translator = QTranslator(app)
    if translator.load(QLocale(QLocale.Russian), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
        _translators.append(translator)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    sys.excepthook = _report_error
    app = create_app()
    window = MainWindow(resolve_paths(), args[0] if args else None)
    window.show()
    return app.exec()
