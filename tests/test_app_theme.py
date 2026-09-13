import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from unittest import mock

from checkprog import app as app_module
from checkprog import theme
from checkprog.app import App
from checkprog.settings import load_settings, save_settings
from tests.test_app import AppTestCase


class ThemeTestCase(AppTestCase):
    system_dark = False

    def setUp(self):
        self.sysdark = mock.patch("checkprog.theme.system_prefers_dark",
                                  return_value=self.system_dark)
        self.sysdark_mock = self.sysdark.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.sysdark.stop()

    def restart(self):
        self.top.destroy()
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()
        self.app = App(self.top, self.paths)

    def assert_palette_applied(self, palette):
        app = self.app
        self.assertEqual(str(app.tree.tag_configure("done", "foreground")), palette.done_fg)
        for button in app.menu_buttons.values():
            self.assertEqual(str(button.cget("background")), palette.menu_bar_bg)
            self.assertEqual(str(button.cget("foreground")), palette.fg)
        for menu in app.menus:
            self.assertEqual(str(menu.cget("background")), palette.menu_bg)
            self.assertEqual(str(menu.cget("foreground")), palette.menu_fg)
        self.assertEqual(str(app.menu_bar.cget("background")), palette.menu_bar_bg)
        self.assertEqual(str(app.hint.cget("foreground")), palette.muted)


class ThemeTests(ThemeTestCase):
    def test_default_mode_is_system_and_light_here(self):
        self.assertEqual(self.app.theme_mode, "system")
        self.assertEqual(self.app.theme, "light")
        self.assertEqual(self.app.theme_var.get(), "system")
        self.assert_palette_applied(theme.LIGHT)

    def test_set_dark_applies_everywhere_and_persists(self):
        self.add("a", "b")
        self.app.toggle_index(1)
        self.app.set_theme_mode("dark")
        self.assertEqual(self.app.theme, "dark")
        self.assertEqual(ttk.Style(self.top).theme_use(), "clam")
        self.assert_palette_applied(theme.DARK)
        self.assert_in_sync()
        self.assertEqual(load_settings(self.paths.settings_file)["theme"], "dark")
        self.assertEqual(self.app.theme_var.get(), "dark")

    def test_back_to_light_restores_native_theme(self):
        self.app.set_theme_mode("dark")
        self.app.set_theme_mode("light")
        style = ttk.Style(self.top)
        if "vista" in style.theme_names():
            self.assertEqual(style.theme_use(), "vista")
        self.assert_palette_applied(theme.LIGHT)

    def test_row_height_and_layout_survive_theme_switches(self):
        style = ttk.Style(self.top)
        expected = int(style.lookup("Treeview", "rowheight"))
        layout = style.layout("Treeview.Item")
        for mode in ("dark", "light", "dark"):
            self.app.set_theme_mode(mode)
            self.assertEqual(int(style.lookup("Treeview", "rowheight")), expected)
            self.assertEqual(style.layout("Treeview.Item"), layout)

    def test_switch_keeps_selection_dirty_flag_and_rows(self):
        self.add("a", "b", "c")
        self.app.select(1)
        self.app.set_theme_mode("dark")
        self.assertEqual(self.selected(), 1)
        self.assertTrue(self.app.checklist.dirty)
        self.assert_in_sync()

    def test_switch_while_editing_keeps_editor_usable(self):
        self.add("a")
        self.app.begin_edit(0)
        self.app.set_theme_mode("dark")
        self.assertIsNotNone(self.app.editor)
        self.app.editor.entry.delete(0, "end")
        self.app.editor.entry.insert(0, "b")
        self.app.end_edit(True)
        self.assertEqual(self.texts(), ["b"])
        self.assert_in_sync()

    def test_switching_does_not_leak_images(self):
        self.add("a")
        self.app.set_theme_mode("dark")
        self.app.set_theme_mode("light")
        before = len(self.root.image_names())
        for _ in range(10):
            self.app.set_theme_mode("dark")
            self.app.set_theme_mode("light")
        self.assertEqual(len(self.root.image_names()), before)
        self.assert_in_sync()

    def test_mode_survives_restart(self):
        self.app.set_theme_mode("dark")
        self.restart()
        self.assertEqual(self.app.theme_mode, "dark")
        self.assertEqual(self.app.theme, "dark")
        self.assertEqual(self.app.theme_var.get(), "dark")

    def test_garbage_mode_in_settings_falls_back_to_system(self):
        for bad in ("blue", 5, None, ["dark"]):
            with self.subTest(bad=bad):
                save_settings(self.paths.settings_file, {"theme": bad})
                self.restart()
                self.assertEqual(self.app.theme_mode, "system")

    def test_theme_setting_does_not_disturb_last_file(self):
        self.add("a")
        self.fdm["asksaveasfilename"].return_value = self.p("x.json")
        self.app.save()
        self.app.set_theme_mode("dark")
        settings = load_settings(self.paths.settings_file)
        self.assertEqual(settings["theme"], "dark")
        self.assertIn("last_file", settings)


class SystemFollowTests(ThemeTestCase):
    def test_system_mode_follows_registry_on_focus(self):
        self.sysdark_mock.return_value = True
        self.app.on_focus_in(None)
        self.assertEqual(self.app.theme, "dark")
        self.sysdark_mock.return_value = False
        self.app.on_focus_in(None)
        self.assertEqual(self.app.theme, "light")

    def test_explicit_mode_ignores_registry(self):
        self.app.set_theme_mode("light")
        self.sysdark_mock.return_value = True
        self.app.on_focus_in(None)
        self.assertEqual(self.app.theme, "light")

    def test_focus_without_change_does_not_reapply(self):
        with mock.patch.object(self.app, "apply_theme") as apply:
            self.app.on_focus_in(None)
        apply.assert_not_called()


class DarkSystemStartupTests(ThemeTestCase):
    system_dark = True

    def test_starts_dark_when_windows_is_dark(self):
        self.assertEqual(self.app.theme_mode, "system")
        self.assertEqual(self.app.theme, "dark")
        self.assert_palette_applied(theme.DARK)


class MenuKeyboardTests(ThemeTestCase):
    def alt(self, keycode):
        event = SimpleNamespace(keycode=keycode, keysym="x", state=app_module.ALT_MASK)
        with mock.patch.object(app_module.sys, "platform", "win32"):
            return self.app.on_alt_key(event)

    def test_menu_bar_has_four_menus_in_order(self):
        texts = [b.cget("text") for b in self.app.menu_buttons.values()]
        self.assertEqual(texts, ["Файл", "Пункт", "Вид", "Справка"])

    def test_alt_letters_open_menus_by_keycode(self):
        expected = {65: "file", 71: "item", 68: "view", 67: "help"}
        with mock.patch.object(self.app, "open_menu") as open_menu:
            for keycode, key in expected.items():
                self.assertEqual(self.alt(keycode), "break")
                open_menu.assert_called_with(key)
        self.assertEqual(open_menu.call_count, 4)

    def test_altgr_letter_does_not_open_menu(self):
        event = SimpleNamespace(keycode=65, keysym="aogonek",
                                state=app_module.ALT_MASK | app_module.CONTROL_MASK)
        with mock.patch.object(self.app, "open_menu") as open_menu, \
                mock.patch.object(app_module.sys, "platform", "win32"):
            self.assertIsNone(self.app.on_alt_key(event))
        open_menu.assert_not_called()

    def test_alt_f4_is_not_swallowed(self):
        with mock.patch.object(self.app, "open_menu") as open_menu:
            self.assertIsNone(self.alt(115))
        open_menu.assert_not_called()

    def test_f10_opens_file_menu(self):
        with mock.patch.object(self.app, "open_menu") as open_menu:
            self.assertEqual(self.app.on_f10(None), "break")
        open_menu.assert_called_once_with("file")

    def test_open_menu_commits_edit_first(self):
        self.add("a")
        self.app.begin_edit(0)
        self.app.editor.entry.insert("end", "b")
        with mock.patch.object(self.app.menu_system, "open_bar"):
            self.app.open_menu("file")
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.texts(), ["ab"])

    def test_theme_menu_items_switch_mode(self):
        submenu = self.app.bar_menus["view"].entrycget(0, "menu")
        labels = [submenu.entrycget(i, "label") for i in range(submenu.index("end") + 1)]
        self.assertEqual(labels, [theme.MODE_LABELS[m] for m in theme.MODES])
        submenu.invoke(2)
        self.assertEqual(self.app.theme_mode, "dark")
        submenu.invoke(1)
        self.assertEqual(self.app.theme_mode, "light")


if __name__ == "__main__":
    unittest.main()
