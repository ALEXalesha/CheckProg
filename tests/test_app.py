import os
import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

from checkprog import app as app_module
from checkprog.app import App
from checkprog.model import Checklist
from checkprog.settings import Paths, load_settings


class AppTestCase(unittest.TestCase):
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
        self.tmp = self._tmp.name
        self.paths = Paths(self.p("settings.json"), self.p("lists"), True)
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()
        self.dialogs = mock.patch.multiple(
            app_module.messagebox,
            showerror=mock.DEFAULT, showinfo=mock.DEFAULT, askyesnocancel=mock.DEFAULT)
        self.mb = self.dialogs.start()
        self.fd = mock.patch.multiple(
            app_module.filedialog,
            askopenfilename=mock.DEFAULT, asksaveasfilename=mock.DEFAULT)
        self.fdm = self.fd.start()
        self.app = App(self.top, self.paths)

    def tearDown(self):
        self.fd.stop()
        self.dialogs.stop()
        if self.top.winfo_exists():
            self.top.destroy()
        self._tmp.cleanup()

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)

    def rows(self):
        tree = self.app.tree
        return [tuple(str(v) for v in tree.item(iid, "values")) for iid in tree.get_children()]

    def texts(self):
        return [r[0] for r in self.rows()]

    def checked(self, index):
        image = self.app.tree.item(str(index), "image")
        name = str(image[0]) if image else ""
        self.assertIn(name, (str(self.app.img_on), str(self.app.img_off)))
        return name == str(self.app.img_on)

    def assert_in_sync(self):
        cl = self.app.checklist
        self.assertEqual(self.rows(), [(it.text,) for it in cl.items])
        self.assertEqual(list(self.app.tree.get_children()),
                         [str(i) for i in range(len(cl))])
        self.assertEqual([self.checked(i) for i in range(len(cl))],
                         [it.done for it in cl.items])
        self.assertIn(f"{cl.done_count} из {cl.total}", self.app.progress_label.cget("text"))
        self.assertEqual(self.top.title().startswith("*"), cl.dirty)
        selected = self.app.selected_index()
        self.assertTrue(selected is None or 0 <= selected < len(cl))

    def add(self, *texts):
        for t in texts:
            self.app.entry.delete(0, "end")
            self.app.entry.insert(0, t)
            self.app.add_item()
        self.assert_in_sync()

    def selected(self):
        return self.app.selected_index()


class BasicOperationTests(AppTestCase):
    def test_starts_empty_and_clean(self):
        self.assertEqual(self.rows(), [])
        self.assertIn("Без имени", self.top.title())
        self.assert_in_sync()

    def test_add_via_entry_clears_it_and_selects_new_item(self):
        self.add("молоко", "хлеб")
        self.assertEqual(self.app.entry.get(), "")
        self.assertEqual(self.selected(), 1)
        self.assertTrue(self.top.title().startswith("*"))

    def test_blank_entry_adds_nothing(self):
        self.add("   ")
        self.assertEqual(self.rows(), [])
        self.assertFalse(self.app.checklist.dirty)

    def test_toggle_updates_row_and_progress(self):
        self.add("a", "b")
        self.app.toggle_index(0)
        self.assert_in_sync()
        self.assertTrue(self.checked(0))
        self.assertFalse(self.checked(1))
        self.assertIn("1 из 2", self.app.progress_label.cget("text"))
        self.assertEqual(float(self.app.progress_bar.cget("value")), 1.0)
        self.assertEqual(float(self.app.progress_bar.cget("maximum")), 2.0)

    def test_done_row_gets_done_tag(self):
        self.add("a")
        self.app.toggle_index(0)
        self.assertIn("done", self.app.tree.item("0", "tags"))
        self.app.toggle_index(0)
        self.assertNotIn("done", self.app.tree.item("0", "tags") or ())

    def test_numeric_looking_and_tcl_special_texts_survive(self):
        weird = ["007", "1e3", "{", "}", "[x]", "a\\b", "$var", '"q"', "-flag", "{a b}"]
        self.add(*weird)
        self.assertEqual(self.texts(), weird)

    def test_delete_selects_neighbour(self):
        self.add("a", "b", "c")
        self.app.select(2)
        self.app.delete_selected()
        self.assert_in_sync()
        self.assertEqual(self.selected(), 1)
        self.app.select(0)
        self.app.delete_selected()
        self.assertEqual(self.selected(), 0)
        self.app.delete_selected()
        self.assert_in_sync()
        self.assertIsNone(self.selected())
        self.app.delete_selected()
        self.assert_in_sync()

    def test_move_selected_up_and_down(self):
        self.add("a", "b", "c")
        self.app.select(0)
        self.app.move_selected(-1)
        self.assertEqual(self.texts(), ["a", "b", "c"])
        self.app.move_selected(1)
        self.assert_in_sync()
        self.assertEqual(self.texts(), ["b", "a", "c"])
        self.assertEqual(self.selected(), 1)
        self.app.select(2)
        self.app.move_selected(1)
        self.assertEqual(self.texts(), ["b", "a", "c"])

    def test_drag_reorders(self):
        self.add("a", "b", "c", "d")
        self.app.drag_start(0)
        self.app.drag_to(2)
        self.app.drag_to(3)
        self.app.drag_end()
        self.assert_in_sync()
        self.assertEqual(self.texts(), ["b", "c", "d", "a"])
        self.assertEqual(self.selected(), 3)

    def test_drag_after_list_shrinks_is_ignored(self):
        self.add("a", "b")
        self.app.drag_start(1)
        self.app.checklist.remove(1)
        self.app.refresh()
        self.app.drag_to(0)
        self.app.drag_end()
        self.assert_in_sync()

    def test_window_fits_on_small_screen(self):
        self.top.update_idletasks()
        geometry = self.top.geometry().split("+")[0]
        width, height = (int(v) for v in geometry.split("x"))
        self.assertLessEqual(width, self.top.winfo_screenwidth())
        self.assertLessEqual(height, self.top.winfo_screenheight())


class EditTests(AppTestCase):
    def test_edit_commit(self):
        self.add("a", "b")
        self.app.begin_edit(1)
        self.assertIsNotNone(self.app.editor)
        self.app.editor.entry.delete(0, "end")
        self.app.editor.entry.insert(0, "  новое  ")
        self.app.end_edit(commit=True)
        self.assertIsNone(self.app.editor)
        self.assert_in_sync()
        self.assertEqual(self.texts()[1], "новое")

    def test_edit_cancel(self):
        self.add("a")
        self.app.checklist.dirty = False
        self.app.refresh()
        self.app.begin_edit(0)
        self.app.editor.entry.insert(0, "zzz")
        self.app.end_edit(commit=False)
        self.assertEqual(self.texts()[0], "a")
        self.assertFalse(self.app.checklist.dirty)

    def test_edit_to_blank_keeps_text(self):
        self.add("a")
        self.app.begin_edit(0)
        self.app.editor.entry.delete(0, "end")
        self.app.end_edit(commit=True)
        self.assertEqual(self.texts()[0], "a")

    def test_end_edit_is_reentrant_safe(self):
        self.add("a")
        self.app.begin_edit(0)
        self.app.end_edit(commit=True)
        self.app.end_edit(commit=True)
        self.assertIsNone(self.app.editor)

    def test_other_actions_commit_pending_edit_first(self):
        self.add("a", "b")
        self.app.begin_edit(0)
        self.app.editor.entry.delete(0, "end")
        self.app.editor.entry.insert(0, "x")
        self.app.select(1)
        self.app.delete_selected()
        self.assert_in_sync()
        self.assertEqual(self.texts(), ["x"])

    def test_begin_edit_twice_replaces_editor(self):
        self.add("a", "b")
        self.app.begin_edit(0)
        first = self.app.editor.entry
        self.app.begin_edit(1)
        self.assertFalse(first.winfo_exists())
        self.assertEqual(self.app.editor.index, 1)
        self.app.end_edit(commit=False)

    def test_half_deleted_emoji_does_not_break_save(self):
        self.add("a")
        self.app.begin_edit(0)
        entry = self.app.editor.entry
        entry.delete(0, "end")
        entry.insert(0, "b😀")
        entry.delete(2, "end")  # Tk 8.6 counts the emoji as two chars; cut the pair in half
        self.app.end_edit(commit=True)
        self.fdm["asksaveasfilename"].return_value = self.p("emoji.json")
        self.assertTrue(self.app.save())
        self.assertEqual([it.text for it in Checklist.load(self.p("emoji.json")).items], ["b"])

    def test_save_commits_pending_edit(self):
        self.add("a")
        self.fdm["asksaveasfilename"].return_value = self.p("e.json")
        self.app.begin_edit(0)
        self.app.editor.entry.delete(0, "end")
        self.app.editor.entry.insert(0, "b")
        self.assertTrue(self.app.save())
        self.assertEqual([it.text for it in Checklist.load(self.p("e.json")).items], ["b"])
        self.assertFalse(self.app.checklist.dirty)


class FileTests(AppTestCase):
    def test_save_as_then_save(self):
        self.add("a")
        target = self.p("list.json")
        self.fdm["asksaveasfilename"].return_value = target
        self.assertTrue(self.app.save())
        self.assert_in_sync()
        self.assertIn("list.json", self.top.title())
        self.assertFalse(self.top.title().startswith("*"))
        self.add("b")
        self.fdm["asksaveasfilename"].reset_mock()
        self.assertTrue(self.app.save())
        self.fdm["asksaveasfilename"].assert_not_called()
        self.assertEqual([it.text for it in Checklist.load(target).items], ["a", "b"])
        self.assertEqual(os.path.normcase(load_settings(self.paths.settings_file)["last_file"]),
                         os.path.normcase(target))

    def test_save_as_cancel_returns_false(self):
        self.add("a")
        self.fdm["asksaveasfilename"].return_value = ""
        self.assertFalse(self.app.save())
        self.assertTrue(self.app.checklist.dirty)

    def test_save_error_is_reported_and_state_kept(self):
        self.add("a")
        self.fdm["asksaveasfilename"].return_value = self.p("нет", "list.json")
        self.assertFalse(self.app.save())
        self.mb["showerror"].assert_called_once()
        self.assertTrue(self.app.checklist.dirty)
        self.assertIsNone(self.app.checklist.path)

    def test_open_replaces_list(self):
        other = Checklist()
        other.add("из файла")
        other.save(self.p("other.json"))
        self.fdm["askopenfilename"].return_value = self.p("other.json")
        self.app.open_file()
        self.assert_in_sync()
        self.assertEqual(self.texts(), ["из файла"])
        self.assertIn("other.json", self.top.title())

    def test_open_shorter_list_leaves_no_stale_rows(self):
        self.add("1", "2", "3", "4")
        self.app.toggle_index(3)
        other = Checklist()
        other.add("x")
        other.save(self.p("short.json"))
        self.mb["askyesnocancel"].return_value = False
        self.fdm["askopenfilename"].return_value = self.p("short.json")
        self.app.open_file()
        self.assert_in_sync()
        self.assertEqual(self.texts(), ["x"])

    def test_open_corrupt_file_keeps_current_list(self):
        self.add("мой")
        with open(self.p("bad.json"), "w", encoding="utf-8") as f:
            f.write("{oops")
        self.mb["askyesnocancel"].return_value = False
        self.fdm["askopenfilename"].return_value = self.p("bad.json")
        self.app.open_file()
        self.mb["showerror"].assert_called_once()
        self.assertEqual(self.texts(), ["мой"])
        self.assert_in_sync()

    def test_open_cancel_in_save_prompt_does_nothing(self):
        self.add("мой")
        self.mb["askyesnocancel"].return_value = None
        self.app.open_file()
        self.fdm["askopenfilename"].assert_not_called()
        self.assertEqual(self.texts(), ["мой"])

    def test_open_prompt_yes_saves_first(self):
        self.add("мой")
        self.mb["askyesnocancel"].return_value = True
        self.fdm["asksaveasfilename"].return_value = self.p("mine.json")
        self.fdm["askopenfilename"].return_value = ""
        self.app.open_file()
        self.assertEqual([it.text for it in Checklist.load(self.p("mine.json")).items], ["мой"])

    def test_open_prompt_yes_but_save_cancelled_stops(self):
        self.add("мой")
        self.mb["askyesnocancel"].return_value = True
        self.fdm["asksaveasfilename"].return_value = ""
        self.app.open_file()
        self.fdm["askopenfilename"].assert_not_called()
        self.assertTrue(self.app.checklist.dirty)

    def test_new_asks_and_clears(self):
        self.add("a")
        self.mb["askyesnocancel"].return_value = False
        self.app.new_file()
        self.assert_in_sync()
        self.assertEqual(self.rows(), [])
        self.assertIsNone(self.app.checklist.path)

    def test_clean_list_is_not_prompted(self):
        self.app.new_file()
        self.mb["askyesnocancel"].assert_not_called()

    def test_exit_cancel_keeps_window(self):
        self.add("a")
        self.mb["askyesnocancel"].return_value = None
        self.app.on_exit()
        self.assertTrue(self.top.winfo_exists())

    def test_exit_without_saving_closes_window(self):
        self.add("a")
        self.mb["askyesnocancel"].return_value = False
        self.app.on_exit()
        self.assertFalse(self.top.winfo_exists())

    def test_exit_commits_edit_before_prompt(self):
        self.add("a")
        self.app.checklist.dirty = False
        self.app.refresh()
        self.app.begin_edit(0)
        self.app.editor.entry.insert("end", "b")
        self.mb["askyesnocancel"].return_value = None
        self.app.on_exit()
        self.mb["askyesnocancel"].assert_called_once()
        self.assertEqual(self.texts()[0], "ab")


class StartupTests(AppTestCase):
    def make_app(self, initial=None):
        self.top.destroy()
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()
        self.app = App(self.top, self.paths, initial)

    def test_opens_initial_path(self):
        cl = Checklist()
        cl.add("аргумент")
        cl.save(self.p("arg.json"))
        self.make_app(self.p("arg.json"))
        self.assertEqual(self.texts(), ["аргумент"])
        self.assert_in_sync()

    def test_reopens_last_file(self):
        cl = Checklist()
        cl.add("прошлый")
        cl.save(self.p("last.json"))
        self.app.open_path(self.p("last.json"))
        self.make_app()
        self.assertEqual(self.texts(), ["прошлый"])

    def test_missing_last_file_is_silent_and_forgotten(self):
        cl = Checklist()
        cl.add("x")
        cl.save(self.p("gone.json"))
        self.app.open_path(self.p("gone.json"))
        os.remove(self.p("gone.json"))
        self.make_app()
        self.mb["showerror"].assert_not_called()
        self.assertEqual(self.rows(), [])
        self.assertNotIn("last_file", load_settings(self.paths.settings_file))

    def test_missing_initial_path_is_reported(self):
        self.make_app(self.p("nope.json"))
        self.mb["showerror"].assert_called_once()

    def test_garbage_settings_do_not_break_startup(self):
        with open(self.paths.settings_file, "w", encoding="utf-8") as f:
            f.write('{"last_file": 5}')
        self.make_app()
        self.assertEqual(self.rows(), [])
        with open(self.paths.settings_file, "w", encoding="utf-8") as f:
            f.write("][")
        self.make_app()
        self.assertEqual(self.rows(), [])


class KeyboardTests(AppTestCase):
    def ctrl(self, keycode, keysym, extra_state=0):
        event = SimpleNamespace(keycode=keycode, keysym=keysym, state=0x4 | extra_state)
        with mock.patch.object(app_module.sys, "platform", "win32"):
            return self.app.on_ctrl_key(event)

    def test_ctrl_s_works_in_russian_layout(self):
        with mock.patch.object(self.app, "save") as save:
            self.assertEqual(self.ctrl(83, "Cyrillic_yeru"), "break")
        save.assert_called_once()

    def test_ctrl_s_works_with_numlock_and_capslock(self):
        with mock.patch.object(self.app, "save") as save:
            self.ctrl(83, "S", extra_state=0x8 | 0x2)
        save.assert_called_once()

    def test_ctrl_shift_s_is_save_as(self):
        with mock.patch.object(self.app, "save_as") as save_as, \
                mock.patch.object(self.app, "save") as save:
            self.ctrl(83, "Cyrillic_YERU", extra_state=0x1)
        save_as.assert_called_once()
        save.assert_not_called()

    def test_altgr_is_not_a_shortcut(self):
        with mock.patch.object(self.app, "save") as save:
            self.assertIsNone(self.ctrl(83, "sacute", extra_state=app_module.ALT_MASK))
        save.assert_not_called()

    def test_ctrl_o_and_n(self):
        with mock.patch.object(self.app, "open_file") as op, \
                mock.patch.object(self.app, "new_file") as nw:
            self.ctrl(79, "Cyrillic_shcha")
            self.ctrl(78, "Cyrillic_te")
        op.assert_called_once()
        nw.assert_called_once()

    def test_unrelated_ctrl_key_passes_through(self):
        self.assertIsNone(self.ctrl(65, "a"))


if __name__ == "__main__":
    unittest.main()
