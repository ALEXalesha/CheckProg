import subprocess
import sys

from PySide6.QtWidgets import QApplication, QStyleFactory

from checkprog import app as app_module


def test_create_app_style_and_font(qapp):
    old_font, old_style = QApplication.font(), QApplication.style().name()
    try:
        app = app_module.create_app()
        assert app is qapp
        if "windows11" in [k.lower() for k in QStyleFactory.keys()]:
            assert app.style().name().lower() == "windows11"
        assert app.font().pointSize() == app_module.UI_FONT_SIZE == 10
        assert app.applicationName() == "CheckProg"
    finally:
        QApplication.setFont(old_font)
        QApplication.setStyle(old_style)


def test_module_imports_without_tkinter():
    code = ("import sys; import checkprog.app, checkprog.window; "
            "print('tkinter' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_standard_buttons_are_russian(qapp):
    from PySide6.QtCore import QCoreApplication
    app_module.create_app()
    assert QCoreApplication.translate("QPlatformTheme", "Save") == "Сохранить"
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Отмена"


def test_translator_installed_once(qapp):
    app_module.create_app()
    app_module.create_app()
    assert len(app_module._translators) == 1
