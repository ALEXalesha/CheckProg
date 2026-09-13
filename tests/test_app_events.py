import os
import tempfile
import tkinter as tk
import unittest
from unittest import mock

from checkprog import app as app_module
from checkprog.app import CHECK_COLUMN, App
from checkprog.settings import Paths
from tests.tkroot import shared_root


class RealEventTests(unittest.TestCase):
    """Drives real Tk events on a mapped window: a withdrawn window has no row geometry."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = shared_root()
        except tk.TclError as e:
            raise unittest.SkipTest(f"no display: {e}")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dialogs = mock.patch.multiple(
            app_module.messagebox, showerror=mock.DEFAULT, askyesnocancel=mock.DEFAULT)
        self.dialogs.start()
        # A fresh Toplevel per test keeps Tk from merging clicks of two tests into a double click.
        self.top = tk.Toplevel(self.root)
        self.top.geometry("+-4000+-4000")
        tmp = self._tmp.name
        self.app = App(self.top, Paths(os.path.join(tmp, "s.json"), tmp, True))
        for text in "abcde":
            self.app.entry.insert(0, text)
            self.app.add_item()
        self.top.update()
        self.tree = self.app.tree

    def tearDown(self):
        if self.top.winfo_exists():
            self.top.destroy()
        self.dialogs.stop()
        self._tmp.cleanup()

    def center(self, row, column):
        x, y, w, h = self.tree.bbox(str(row), column)
        return x + w // 2, y + h // 2

    def send(self, sequence, xy, widget=None):
        (widget or self.tree).event_generate(sequence, x=xy[0], y=xy[1])
        self.top.update()

    def click(self, xy, times=1):
        for _ in range(times):
            self.send("<ButtonPress-1>", xy)
            self.send("<ButtonRelease-1>", xy)

    def texts(self):
        return "".join(it.text for it in self.app.checklist.items)

    def dones(self):
        return "".join("x" if it.done else "." for it in self.app.checklist.items)

    def test_click_on_checkbox_toggles(self):
        self.click(self.center(1, CHECK_COLUMN))
        self.assertEqual(self.dones(), ".x...")
        self.assertEqual(self.app.selected_index(), 1)

    def test_click_on_text_does_not_toggle(self):
        self.click(self.center(1, "text"))
        self.assertEqual(self.dones(), ".....")
        self.assertEqual(self.app.selected_index(), 1)

    def test_double_click_on_checkbox_toggles_twice(self):
        self.click(self.center(2, CHECK_COLUMN), times=2)
        self.assertEqual(self.dones(), ".....")

    def test_double_click_on_text_edits_and_enter_commits(self):
        self.click(self.center(1, "text"), times=2)
        self.assertIsNotNone(self.app.editor)
        self.assertEqual(self.app.editor.index, 1)
        entry = self.app.editor.entry
        entry.focus_force()
        self.top.update()
        entry.delete(0, "end")
        entry.insert(0, "НОВОЕ")
        entry.event_generate("<Return>")
        self.top.update()
        self.assertIsNone(self.app.editor)
        self.assertEqual([it.text for it in self.app.checklist.items][1], "НОВОЕ")

    def test_escape_cancels_edit(self):
        self.app.begin_edit(0)
        entry = self.app.editor.entry
        entry.focus_force()
        self.top.update()
        entry.insert("end", "zzz")
        entry.event_generate("<Escape>")
        self.top.update()
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.texts(), "abcde")

    def test_focus_out_commits_edit(self):
        self.app.begin_edit(0)
        self.app.editor.entry.focus_force()
        self.top.update()
        self.app.editor.entry.insert("end", "!")
        self.app.entry.focus_force()
        self.top.update()
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.app.checklist.items[0].text, "a!")

    def test_drag_moves_item_and_selection(self):
        self.send("<ButtonPress-1>", self.center(0, "text"))
        for row in (1, 2, 3):
            self.send("<B1-Motion>", self.center(row, "text"))
        self.send("<ButtonRelease-1>", self.center(3, "text"))
        self.assertEqual(self.texts(), "bcdae")
        self.assertEqual(self.app.selected_index(), 3)

    def test_drag_past_the_edges(self):
        x = self.center(0, "text")[0]
        self.send("<ButtonPress-1>", self.center(0, "text"))
        self.send("<B1-Motion>", (x, -40))
        self.assertEqual(self.texts(), "abcde")
        self.send("<B1-Motion>", (x, self.tree.winfo_height() + 40))
        self.send("<ButtonRelease-1>", (x, self.tree.winfo_height() + 40))
        self.assertEqual(self.texts(), "bcdea")

    def test_keyboard_on_tree(self):
        self.app.select(2)
        self.tree.focus_force()
        self.top.update()
        for key in ("<space>", "<Control-Up>", "<Delete>"):
            self.tree.event_generate(key)
            self.top.update()
        self.assertEqual(self.texts(), "abde")
        self.assertEqual(self.dones(), "....")

    def test_delete_key_in_add_entry_does_not_delete_items(self):
        self.app.select(0)
        self.app.entry.focus_force()
        self.app.entry.insert(0, "xy")
        self.app.entry.icursor(0)
        self.top.update()
        self.app.entry.event_generate("<Delete>")
        self.top.update()
        self.assertEqual(self.texts(), "abcde")
        self.assertEqual(self.app.entry.get(), "y")

    def generate_key(self, sequence, keycode):
        self.app.entry.focus_force()
        self.top.update()
        with mock.patch.object(self.app, "open_menu") as open_menu:
            self.app.entry.event_generate(sequence, keycode=keycode)
            self.top.update()
        return open_menu

    @unittest.skipUnless(os.name == "nt", "keycodes are Windows virtual-key codes")
    def test_alt_key_event_reaches_menu_handler(self):
        open_menu = self.generate_key("<Alt-KeyPress-d>", 68)
        open_menu.assert_called_once_with("view")

    @unittest.skipUnless(os.name == "nt", "keycodes are Windows virtual-key codes")
    def test_alt_key_does_not_type_into_entry(self):
        self.generate_key("<Alt-KeyPress-d>", 68)
        self.assertEqual(self.app.entry.get(), "")

    def test_f10_event_reaches_menu_handler(self):
        open_menu = self.generate_key("<KeyPress-F10>", 121)
        open_menu.assert_called_once_with("file")

    # Explicit timestamps: two clicks within 500 ms would be merged into a double click.
    def click_at(self, xy, time):
        self.tree.event_generate("<ButtonPress-1>", x=xy[0], y=xy[1], time=time)
        self.top.update()
        self.tree.event_generate("<ButtonRelease-1>", x=xy[0], y=xy[1], time=time + 30)
        self.top.update()

    def test_second_click_on_selected_row_deselects(self):
        xy = self.center(1, "text")
        self.click_at(xy, 10_000)
        self.assertEqual(self.app.selected_index(), 1)
        self.click_at(xy, 20_000)
        self.assertIsNone(self.app.selected_index())
        self.assertIsNone(self.app.note_index)
        self.click_at(xy, 30_000)
        self.assertEqual(self.app.selected_index(), 1)

    def test_drag_from_selected_row_keeps_selection(self):
        self.click_at(self.center(0, "text"), 10_000)
        start = self.center(0, "text")
        self.tree.event_generate("<ButtonPress-1>", x=start[0], y=start[1], time=20_000)
        self.top.update()
        for n, row in enumerate((1, 2), 1):
            xy = self.center(row, "text")
            self.tree.event_generate("<B1-Motion>", x=xy[0], y=xy[1], time=20_000 + n * 50)
            self.top.update()
        end = self.center(2, "text")
        self.tree.event_generate("<ButtonRelease-1>", x=end[0], y=end[1], time=20_200)
        self.top.update()
        self.assertEqual(self.texts(), "bcade")
        self.assertEqual(self.app.selected_index(), 2)

    def test_click_on_empty_area_deselects(self):
        self.assertIsNotNone(self.app.selected_index())
        x = self.center(0, "text")[0]
        self.click_at((x, self.tree.winfo_height() - 5), 10_000)
        self.assertIsNone(self.app.selected_index())

    def test_escape_on_tree_deselects(self):
        self.tree.focus_force()
        self.top.update()
        self.tree.event_generate("<Escape>")
        self.top.update()
        self.assertIsNone(self.app.selected_index())

    def test_double_click_on_selected_row_still_edits(self):
        xy = self.center(1, "text")
        self.click_at(xy, 10_000)
        self.click_at(xy, 20_000 - 30)  # deselects...
        self.click_at(xy, 20_100)       # ...and this press is a double click: edit
        self.assertIsNotNone(self.app.editor)
        self.assertEqual(self.app.editor.index, 1)
        self.assertEqual(self.app.selected_index(), 1)

    def test_ctrl_o_in_note_does_not_insert_newline(self):
        self.app.select(0)
        self.app.note_text.focus_force()
        self.top.update()
        with mock.patch.object(self.app, "open_file") as open_file:
            self.app.note_text.event_generate("<Control-KeyPress-o>", keycode=79)
            self.top.update()
        open_file.assert_called_once()
        self.assertEqual(self.app.note_text.get("1.0", "end-1c"), "")

    def with_note(self, index, note):
        self.app.checklist.set_note(index, note)
        self.app.refresh()
        self.top.update()

    def test_click_on_arrow_expands_and_collapses(self):
        self.with_note(1, "первая\nвторая")
        self.click_at(self.center(1, "note"), 10_000)
        self.assertTrue(self.app.checklist.items[1].expanded)
        self.assertEqual(len(self.tree.get_children("1")), 2)
        self.click_at(self.center(1, "note"), 20_000)
        self.assertFalse(self.app.checklist.items[1].expanded)
        self.assertEqual(self.tree.get_children("1"), ())

    def test_click_on_empty_arrow_cell_selects_row(self):
        self.click_at(self.center(2, "note"), 10_000)
        self.assertEqual(self.app.selected_index(), 2)
        self.assertEqual(self.texts(), "abcde")

    def test_click_on_note_line_selects_its_item(self):
        self.with_note(0, "заметка")
        self.app.set_expanded(0, True)
        self.app.select(3)
        self.top.update()
        self.click_at(self.center("0.0", "text"), 10_000)
        self.assertEqual(self.app.selected_index(), 0)
        self.assertEqual(self.tree.selection(), ("0",))

    def test_double_click_on_note_line_focuses_panel(self):
        self.with_note(0, "заметка")
        self.app.set_expanded(0, True)
        self.top.update()
        xy = self.center("0.0", "text")
        self.click_at(xy, 10_000)
        self.click_at(xy, 10_100)
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.top.focus_get(), self.app.note_text)
        self.assertEqual(self.app.note_index, 0)

    def test_arrow_keys_skip_note_lines_and_expand(self):
        self.with_note(0, "заметка")
        self.app.select(0)
        self.tree.focus_force()
        self.top.update()
        for key, expected in (("<Right>", True), ("<Down>", None), ("<Up>", None),
                              ("<Left>", False)):
            self.tree.event_generate(key)
            self.top.update()
            if expected is not None:
                self.assertEqual(self.app.checklist.items[0].expanded, expected)
        self.assertEqual(self.app.selected_index(), 0)
        self.app.set_expanded(0, True)
        self.tree.event_generate("<Down>")
        self.top.update()
        self.assertEqual(self.app.selected_index(), 1)

    def test_drag_over_note_lines_moves_item(self):
        self.with_note(1, "заметка")
        self.app.set_expanded(1, True)
        self.top.update()
        target = self.center("1.0", "text")  # row "1.0" is renamed "0.0" by the move
        self.send("<ButtonPress-1>", self.center(0, "text"))
        self.send("<B1-Motion>", target)
        self.send("<ButtonRelease-1>", target)
        self.assertEqual(self.texts(), "bacde")
        self.assertEqual(self.tree.get_children("0"), ("0.0",))  # the note moved with b

    def paste_with(self, widget, keysym):
        self.root.clipboard_clear()
        self.root.clipboard_append("буфер")
        widget.focus_force()
        self.top.update()
        widget.event_generate(f"<Control-KeyPress-{keysym}>", keycode=86)
        self.top.update()

    @unittest.skipUnless(os.name == "nt", "keycodes are Windows virtual-key codes")
    def test_ctrl_v_in_russian_layout_pastes_into_note(self):
        self.app.select(0)
        self.paste_with(self.app.note_text, "Cyrillic_em")
        self.assertEqual(self.app.note_text.get("1.0", "end-1c"), "буфер")
        self.assertEqual(self.app.checklist.items[0].note, "буфер")

    @unittest.skipUnless(os.name == "nt", "keycodes are Windows virtual-key codes")
    def test_ctrl_v_in_russian_layout_pastes_into_entry(self):
        self.paste_with(self.app.entry, "Cyrillic_em")
        self.assertEqual(self.app.entry.get(), "буфер")

    @unittest.skipUnless(os.name == "nt", "keycodes are Windows virtual-key codes")
    def test_ctrl_v_in_latin_layout_pastes_once(self):
        self.app.select(0)
        self.paste_with(self.app.note_text, "v")
        self.assertEqual(self.app.note_text.get("1.0", "end-1c"), "буфер")
        self.paste_with(self.app.entry, "v")
        self.assertEqual(self.app.entry.get(), "буфер")

    @unittest.skipUnless(os.name == "nt", "keycodes are Windows virtual-key codes")
    def test_ctrl_v_on_tree_does_nothing(self):
        self.paste_with(self.tree, "Cyrillic_em")
        self.assertEqual(self.texts(), "abcde")


if __name__ == "__main__":
    unittest.main()
