import os
import tempfile
import tkinter as tk
import unittest
from unittest import mock

from checkprog import app as app_module
from checkprog.app import CHECK_COLUMN, App
from checkprog.settings import Paths


class RealEventTests(unittest.TestCase):
    """Drives real Tk events on a mapped window: a withdrawn window has no row geometry."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as e:
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

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


if __name__ == "__main__":
    unittest.main()
