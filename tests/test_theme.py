import unittest
from unittest import mock

from checkprog import theme


class ResolveTests(unittest.TestCase):
    def test_explicit_modes_ignore_system(self):
        for system_dark in (True, False):
            self.assertEqual(theme.resolve("light", system_dark), "light")
            self.assertEqual(theme.resolve("dark", system_dark), "dark")

    def test_system_mode_follows_system(self):
        self.assertEqual(theme.resolve("system", True), "dark")
        self.assertEqual(theme.resolve("system", False), "light")

    def test_normalize_mode(self):
        for good in theme.MODES:
            self.assertEqual(theme.normalize_mode(good), good)
        for bad in (None, "", "blue", "Dark", 5, ["dark"], True):
            with self.subTest(bad=bad):
                self.assertEqual(theme.normalize_mode(bad), "system")

    def test_every_mode_has_a_label(self):
        self.assertEqual(set(theme.MODE_LABELS), set(theme.MODES))


class PaletteTests(unittest.TestCase):
    def test_palettes_define_the_same_colors(self):
        self.assertEqual(theme.LIGHT._fields, theme.DARK._fields)
        for palette in (theme.LIGHT, theme.DARK):
            for name, value in palette._asdict().items():
                with self.subTest(palette=palette, name=name):
                    self.assertTrue(isinstance(value, str) and value)

    def test_palette_for(self):
        self.assertIs(theme.palette_for("dark"), theme.DARK)
        self.assertIs(theme.palette_for("light"), theme.LIGHT)


class SystemPrefersDarkTests(unittest.TestCase):
    def fake_winreg(self, value=None, error=None):
        fake = mock.MagicMock()
        key = mock.MagicMock()
        fake.OpenKey.return_value.__enter__.return_value = key
        if error is not None:
            fake.OpenKey.side_effect = error
        else:
            fake.QueryValueEx.return_value = (value, 4)
        return fake

    def test_zero_means_dark(self):
        with mock.patch.object(theme, "winreg", self.fake_winreg(0)):
            self.assertTrue(theme.system_prefers_dark())

    def test_one_means_light(self):
        with mock.patch.object(theme, "winreg", self.fake_winreg(1)):
            self.assertFalse(theme.system_prefers_dark())

    def test_missing_key_means_light(self):
        with mock.patch.object(theme, "winreg", self.fake_winreg(error=FileNotFoundError())):
            self.assertFalse(theme.system_prefers_dark())

    def test_unexpected_value_type_means_light(self):
        with mock.patch.object(theme, "winreg", self.fake_winreg("0")):
            self.assertFalse(theme.system_prefers_dark())

    def test_no_winreg_means_light(self):
        with mock.patch.object(theme, "winreg", None):
            self.assertFalse(theme.system_prefers_dark())


class TitleBarTests(unittest.TestCase):
    def test_unmapped_or_foreign_window_is_harmless(self):
        window = mock.MagicMock()
        window.winfo_id.side_effect = RuntimeError("not a real window")
        self.assertFalse(theme.set_title_bar_dark(window, True))


if __name__ == "__main__":
    unittest.main()
