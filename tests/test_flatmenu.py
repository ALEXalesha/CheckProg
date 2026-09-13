import os
import tempfile
import tkinter as tk
import unittest
from tkinter import font as tkfont
from unittest import mock

from checkprog import app as app_module
from checkprog import theme
from checkprog.app import CHECK_COLUMN, App
from checkprog.settings import Paths
from tests.tkroot import shared_root


class FlatMenuTestCase(unittest.TestCase):
    """A mapped (off-screen) window: placed menus need real geometry."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = shared_root()
        except tk.TclError as e:
            raise unittest.SkipTest(f"no display: {e}")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # askyesnocancel returns None (Cancel) and the file dialogs "" (closed):
        # a stray command then does nothing instead of opening a real window.
        self.dialogs = mock.patch.multiple(
            app_module.messagebox, showerror=mock.DEFAULT, showinfo=mock.DEFAULT,
            askyesnocancel=mock.Mock(return_value=None))
        self.dialogs.start()
        self.files = mock.patch.multiple(
            app_module.filedialog, askopenfilename=mock.Mock(return_value=""),
            asksaveasfilename=mock.Mock(return_value=""))
        self.files.start()
        self.sysdark = mock.patch("checkprog.theme.system_prefers_dark", return_value=False)
        self.sysdark.start()
        self.top = tk.Toplevel(self.root)
        self.top.geometry("520x620+-4000+-4000")
        tmp = self._tmp.name
        self.app = App(self.top, Paths(os.path.join(tmp, "s.json"), tmp, True))
        for text in "abc":
            self.app.entry.insert(0, text)
            self.app.add_item()
        self.top.update()
        self.ms = self.app.menu_system

    def tearDown(self):
        if self.top.winfo_exists():
            self.top.destroy()
        self.sysdark.stop()
        self.files.stop()
        self.dialogs.stop()
        self._tmp.cleanup()

    def key(self, keysym, **kw):
        frame = self.ms.chain[0].frame
        frame.focus_force()
        self.top.update()
        frame.event_generate(f"<KeyPress-{keysym}>", **kw)
        self.top.update()

    def center_root(self, widget):
        return (widget.winfo_rootx() + widget.winfo_width() // 2,
                widget.winfo_rooty() + widget.winfo_height() // 2)

    def pointer(self, sequence, xy):
        # With a grab, Tk reports pointer events from anywhere in the window to the
        # grab window; generating them there with root coordinates does the same.
        target = self.ms.chain[0].frame if self.ms.chain else self.app.tree
        target.event_generate(sequence, rootx=xy[0], rooty=xy[1],
                              x=xy[0] - target.winfo_rootx(), y=xy[1] - target.winfo_rooty())
        self.top.update()

    def row_xy(self, menu, index):
        return self.center_root(menu.rows[index][1])

    def labels(self, menu):
        return [e.get("label") for e in menu.entries]


class OpenCloseTests(FlatMenuTestCase):
    def test_keyboard_open_shows_menu_with_first_entry_active(self):
        self.app.open_menu("file")
        menu = self.app.bar_menus["file"]
        self.assertTrue(menu.frame.winfo_viewable())
        self.assertEqual(menu.active, 0)
        self.assertEqual(str(self.app.menu_buttons["file"].cget("state")), "active")

    def test_border_is_one_pixel_in_theme_color(self):
        for mode, palette in (("light", theme.LIGHT), ("dark", theme.DARK)):
            self.app.set_theme_mode(mode)
            self.app.open_menu("file")
            menu = self.app.bar_menus["file"]
            self.assertEqual(str(menu.frame.cget("background")), palette.border)
            self.assertEqual(str(menu.frame.cget("borderwidth")), "0")
            info = menu._inner.pack_info()
            self.assertEqual((str(info["padx"]), str(info["pady"])), ("1", "1"))
            self.assertEqual(menu.frame.winfo_width() - menu._inner.winfo_width(), 2)
            self.ms.close()

    def test_menu_opens_under_its_bar_label(self):
        self.app.open_menu("view")
        label, frame = self.app.menu_buttons["view"], self.app.bar_menus["view"].frame
        self.assertEqual(frame.winfo_rootx(), label.winfo_rootx())
        self.assertEqual(frame.winfo_rooty(), label.winfo_rooty() + label.winfo_height())

    def test_escape_closes_and_restores_focus(self):
        self.app.entry.focus_force()
        self.top.update()
        self.app.open_menu("file")
        self.key("Escape")
        self.assertFalse(self.ms.is_open)
        self.assertIsNone(self.app.bar_menus["file"].frame)
        self.assertEqual(self.top.focus_get(), self.app.entry)
        self.assertEqual(str(self.app.menu_buttons["file"].cget("state")), "normal")

    def test_grab_is_released_after_close(self):
        self.app.open_menu("file")
        self.assertTrue(self.top.grab_current())
        self.ms.close()
        self.assertIsNone(self.top.grab_current())

    def test_opening_twice_leaves_one_menu(self):
        self.app.open_menu("file")
        self.app.open_menu("item")
        self.assertEqual(self.ms.chain, [self.app.bar_menus["item"]])
        self.assertIsNone(self.app.bar_menus["file"].frame)
        placed = [w for w in self.top.place_slaves()]
        self.assertEqual(len(placed), 1)

    def test_alt_key_closes(self):
        self.app.open_menu("file")
        self.key("Alt_L")
        self.assertFalse(self.ms.is_open)

    def test_losing_focus_closes(self):
        self.app.open_menu("file")
        with mock.patch.object(self.ms, "_focus", return_value=None):
            self.ms._check_focus()
        self.assertFalse(self.ms.is_open)

    def test_focus_check_keeps_menu_while_it_has_focus(self):
        self.app.open_menu("file")
        self.ms.chain[0].frame.focus_force()
        self.top.update()
        self.ms._check_focus()
        self.assertTrue(self.ms.is_open)


class KeyboardTests(FlatMenuTestCase):
    def test_arrows_wrap_and_skip_separators(self):
        self.app.open_menu("file")
        menu = self.app.bar_menus["file"]
        seen = []
        for _ in range(len(menu.selectable()) + 1):
            seen.append(menu.active)
            self.key("Down")
        self.assertNotIn(menu.entries.index({"type": "separator"}), seen)
        self.assertEqual(menu.active, seen[1])  # wrapped around past the end
        self.key("Up")
        self.key("Up")
        self.assertEqual(menu.active, menu.selectable()[-1])  # wrapped past the start

    def test_right_and_left_switch_bar_menus(self):
        self.app.open_menu("file")
        self.key("Right")
        self.assertEqual(self.ms.bar_key, "item")
        self.key("Left")
        self.key("Left")
        self.assertEqual(self.ms.bar_key, "help")  # wraps like Windows

    def test_theme_submenu_by_keyboard(self):
        self.app.open_menu("view")
        self.key("Right")  # "Тема" is a cascade: opens it
        self.assertEqual(len(self.ms.chain), 2)
        sub = self.ms.chain[1]
        self.assertEqual(sub.active, 0)
        self.key("Down")
        self.key("Down")
        self.key("Return")
        self.assertEqual(self.app.theme_mode, "dark")
        self.assertFalse(self.ms.is_open)
        self.app.set_theme_mode("light")

    def test_left_closes_submenu_only(self):
        self.app.open_menu("view")
        self.key("Return")
        self.assertEqual(len(self.ms.chain), 2)
        self.key("Left")
        self.assertEqual(len(self.ms.chain), 1)
        self.assertIsNone(self.app.bar_menus["view"].entries[0]["menu"].frame)
        self.key("Escape")
        self.assertFalse(self.ms.is_open)

    def test_radio_mark_shows_current_theme(self):
        self.app.set_theme_mode("dark")
        self.app.open_menu("view")
        self.key("Right")
        sub = self.ms.chain[1]
        marks = [sub.rows[i][0].cget("text") for i in sorted(sub.rows)]
        self.assertEqual(marks, ["", "", "●"])
        self.ms.close()
        self.app.set_theme_mode("light")

    def test_enter_runs_command_after_closing(self):
        seen = {}

        def about():
            seen["open"] = self.ms.is_open
            seen["grab"] = self.top.grab_current()

        self.app.bar_menus["help"].entries[0]["command"] = about
        self.app.open_menu("help")
        self.key("Return")
        self.assertEqual(seen, {"open": False, "grab": None})

    def test_letter_jumps_to_entry(self):
        self.app.open_menu("file")
        menu = self.app.bar_menus["file"]
        self.key("Cyrillic_VE", )  # no char: ignored
        menu.jump("с")
        first = menu.active
        self.assertTrue(menu.entries[first]["label"].startswith("С"))
        menu.jump("с")
        self.assertNotEqual(menu.active, first)

    def test_alt_letter_while_open_reaches_app(self):
        self.app.open_menu("file")
        with mock.patch.object(self.app, "open_menu") as open_menu, \
                mock.patch.object(app_module.sys, "platform", "win32"):
            frame = self.ms.chain[0].frame
            frame.focus_force()
            self.top.update()
            frame.event_generate("<Alt-KeyPress-d>", keycode=68)
            self.top.update()
        open_menu.assert_called_once_with("view")


class PointerTests(FlatMenuTestCase):
    def test_click_on_bar_label_opens_and_closes(self):
        label = self.app.menu_buttons["file"]
        label.event_generate("<ButtonPress-1>", x=3, y=3)
        self.top.update()
        self.assertEqual(self.ms.bar_key, "file")
        self.assertIsNone(self.app.bar_menus["file"].active)  # mouse: nothing preselected
        self.pointer("<ButtonPress-1>", self.center_root(label))
        self.assertFalse(self.ms.is_open)

    def test_hover_activates_and_release_invokes(self):
        self.app.open_menu("item")
        menu = self.app.bar_menus["item"]
        index = self.labels(menu).index("Удалить")
        self.app.select(0)
        self.pointer("<Motion>", self.row_xy(menu, index))
        self.assertEqual(menu.active, index)
        self.pointer("<ButtonPress-1>", self.row_xy(menu, index))
        self.pointer("<ButtonRelease-1>", self.row_xy(menu, index))
        self.assertFalse(self.ms.is_open)
        self.assertEqual(len(self.app.checklist), 2)

    def test_hover_on_other_bar_label_switches_menu(self):
        self.app.open_menu("file")
        self.pointer("<Motion>", self.center_root(self.app.menu_buttons["help"]))
        self.assertEqual(self.ms.bar_key, "help")

    def test_hover_on_cascade_opens_submenu_and_elsewhere_closes_it(self):
        self.app.open_menu("view")
        menu = self.app.bar_menus["view"]
        self.pointer("<Motion>", self.row_xy(menu, 0))
        self.assertEqual(len(self.ms.chain), 2)
        sub = self.ms.chain[1]
        self.assertGreaterEqual(sub.frame.winfo_rootx() + 4,
                                menu.frame.winfo_rootx() + menu.frame.winfo_width())
        self.pointer("<Motion>", self.row_xy(sub, 1))
        self.assertEqual(sub.active, 1)
        self.pointer("<ButtonRelease-1>", self.row_xy(sub, 1))
        self.assertEqual(self.app.theme_mode, "light")
        self.assertFalse(self.ms.is_open)

    def test_click_outside_only_closes(self):
        # "Справка" opens far to the right, so the checkbox column stays uncovered.
        # (Under "Файл" the same point would hit "Сохранить" and open a dialog.)
        self.app.open_menu("help")
        x, y, w, h = self.app.tree.bbox("1", CHECK_COLUMN)
        xy = (self.app.tree.winfo_rootx() + x + w // 2, self.app.tree.winfo_rooty() + y + h // 2)
        self.assertEqual(self.ms._hit(*xy), (None, None, None))
        self.pointer("<ButtonPress-1>", xy)
        self.pointer("<ButtonRelease-1>", xy)
        self.assertFalse(self.ms.is_open)
        self.assertEqual([it.done for it in self.app.checklist.items], [False] * 3)

    def test_click_on_separator_keeps_menu(self):
        self.app.open_menu("file")
        menu = self.app.bar_menus["file"]
        self.pointer("<ButtonPress-1>", self.center_root(menu._separators[0]))
        self.pointer("<ButtonRelease-1>", self.center_root(menu._separators[0]))
        self.assertTrue(self.ms.is_open)

    def test_wheel_is_swallowed(self):
        self.app.open_menu("file")
        frame = self.ms.chain[0].frame
        self.assertEqual(frame.bind("<MouseWheel>") != "", True)


class PopupTests(FlatMenuTestCase):
    def test_right_click_opens_item_menu_at_pointer(self):
        x, y, w, h = self.app.tree.bbox("1", "text")
        self.app.tree.event_generate("<Button-3>", x=x + 5, y=y + 5)
        self.top.update()
        self.assertEqual(self.ms.chain, [self.app.item_menu])
        self.assertIsNone(self.ms.bar_key)
        self.assertEqual(self.app.selected_index(), 1)
        self.assertIn("Комментарий", self.labels(self.app.item_menu))

    def test_popup_is_kept_inside_the_window(self):
        corner = (self.top.winfo_rootx() + self.top.winfo_width() - 2,
                  self.top.winfo_rooty() + self.top.winfo_height() - 2)
        self.ms.popup(self.app.item_menu, *corner)
        frame = self.app.item_menu.frame
        self.assertLessEqual(frame.winfo_rootx() + frame.winfo_width(),
                             self.top.winfo_rootx() + self.top.winfo_width())
        self.assertLessEqual(frame.winfo_rooty() + frame.winfo_height(),
                             self.top.winfo_rooty() + self.top.winfo_height())
        self.assertGreaterEqual(frame.winfo_rootx(), self.top.winfo_rootx())

    def test_submenu_flips_left_near_right_edge(self):
        self.top.geometry("360x620")
        self.top.update()
        view = self.app.bar_menus["view"]
        self.ms.popup(view, self.top.winfo_rootx() + 300, self.top.winfo_rooty() + 100)
        view.activate(0)
        self.ms._open_sub(0, keyboard=True)
        sub = self.ms.chain[1]
        self.assertLess(sub.frame.winfo_rootx(), view.frame.winfo_rootx())

    def test_shift_f10_opens_item_menu_with_keyboard(self):
        self.app.select(0)
        self.app.tree.focus_force()
        self.top.update()
        self.app.tree.event_generate("<Shift-F10>")
        self.top.update()
        self.assertEqual(self.ms.chain, [self.app.item_menu])
        self.assertEqual(self.app.item_menu.active, 0)

    def test_theme_switch_recolors_open_menu(self):
        self.app.open_menu("file")
        self.app.set_theme_mode("dark")
        menu = self.app.bar_menus["file"]
        self.assertEqual(str(menu._inner.cget("background")), theme.DARK.menu_bg)
        self.ms.close()
        self.app.set_theme_mode("light")


class FontTests(FlatMenuTestCase):
    def test_fonts_are_larger_and_stable(self):
        size = tkfont.nametofont("TkDefaultFont", root=self.top).actual("size")
        self.assertEqual(size, app_module.UI_FONT_SIZE)
        App(tk.Toplevel(self.root), self.app.paths).root.destroy()
        self.assertEqual(tkfont.nametofont("TkDefaultFont", root=self.top).actual("size"), size)
        self.assertEqual(self.app._menu_font.actual("size"), app_module.UI_FONT_SIZE)

    def test_row_height_fits_the_font(self):
        linespace = tkfont.nametofont("TkDefaultFont", root=self.top).metrics("linespace")
        self.assertGreater(self.app._row_height, linespace)


if __name__ == "__main__":
    unittest.main()
