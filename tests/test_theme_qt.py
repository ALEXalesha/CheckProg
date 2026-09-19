import pytest
from PySide6.QtCore import Qt

from checkprog import theme


@pytest.mark.parametrize("mode, scheme", [
    ("system", Qt.ColorScheme.Unknown), ("light", Qt.ColorScheme.Light),
    ("dark", Qt.ColorScheme.Dark), ("bogus", Qt.ColorScheme.Unknown),
    (None, Qt.ColorScheme.Unknown), (5, Qt.ColorScheme.Unknown)])
def test_color_scheme(mode, scheme):
    assert theme.color_scheme(mode) == scheme


def test_apply_mode_switches_palette(qapp):
    try:
        for mode, dark in (("dark", True), ("light", False), ("dark", True)):
            theme.apply_mode(qapp, mode)
            qapp.processEvents()
            assert theme.is_dark(qapp.palette()) is dark
    finally:
        theme.apply_mode(qapp, "light")
        qapp.processEvents()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_muted_is_between_text_and_base(qapp, mode):
    theme.apply_mode(qapp, mode)
    qapp.processEvents()
    try:
        p = qapp.palette()
        muted = theme.muted_color(p).lightness()
        lo, hi = sorted((p.text().color().lightness(), p.base().color().lightness()))
        assert lo < muted < hi
        # readable on the base colour, but clearly not the text colour
        assert abs(muted - p.base().color().lightness()) >= 60
        assert abs(muted - p.text().color().lightness()) >= 60
    finally:
        theme.apply_mode(qapp, "light")
        qapp.processEvents()


@pytest.mark.parametrize("value, expected", [
    ("system", "system"), ("light", "light"), ("dark", "dark"), ("Dark", "system"),
    ("", "system"), (None, "system"), (1, "system"), (["dark"], "system")])
def test_normalize_mode(value, expected):
    assert theme.normalize_mode(value) == expected


def test_every_mode_has_a_label():
    assert set(theme.MODE_LABELS) == set(theme.MODES)
