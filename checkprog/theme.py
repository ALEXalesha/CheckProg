"""Theme mode: "system", "light" or "dark", applied through Qt's color scheme."""

MODES = ("system", "light", "dark")
MODE_LABELS = {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная"}


def normalize_mode(value):
    return value if isinstance(value, str) and value in MODES else "system"


# ---- Qt ----------------------------------------------------------------------
# Qt follows Windows by itself: "system" is ColorScheme.Unknown, and it recolors
# the palette and the title bar when the Windows setting changes.


def color_scheme(mode):
    from PySide6.QtCore import Qt
    return {"light": Qt.ColorScheme.Light,
            "dark": Qt.ColorScheme.Dark}.get(normalize_mode(mode), Qt.ColorScheme.Unknown)


def apply_mode(app, mode):
    app.styleHints().setColorScheme(color_scheme(mode))


def is_dark(palette):
    return palette.window().color().lightness() < 128


def muted_color(palette):
    """Grey between text and background, for note lines and done items.

    The style's PlaceholderText is not usable: windows11 makes it pure white in
    the dark scheme.
    """
    from PySide6.QtGui import QColor
    fg, bg = palette.text().color(), palette.base().color()
    t = 0.45
    return QColor(round(fg.red() * (1 - t) + bg.red() * t),
                  round(fg.green() * (1 - t) + bg.green() * t),
                  round(fg.blue() * (1 - t) + bg.blue() * t))
