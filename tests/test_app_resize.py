"""Resizing: note lines are rewrapped once the width settles, not on every step."""
import random
import time
import tkinter as tk
import tkinter.font as tkfont
import unittest
import unittest.mock

from checkprog import app as app_module
from checkprog import theme
from checkprog.model import Checklist
from tests.test_app_notes import NoteTestCase

LONG = " ".join(["слово"] * 40)


class ResizeTestCase(NoteTestCase):
    def setUp(self):
        super().setUp()
        self.width = 300
        patcher = unittest.mock.patch.object(self.app, "_note_width",
                                             side_effect=lambda: self.width)
        patcher.start()
        self.addCleanup(patcher.stop)

    def kids(self, index):
        tree = self.app.tree
        return [str(tree.item(k, "values")[0]) for k in tree.get_children(str(index))]

    def with_expanded(self, *notes):
        self.add(*[f"п{i}" for i in range(len(notes))])
        for i, note in enumerate(notes):
            self.app.checklist.set_note(i, note)
            if note:
                self.app.checklist.set_expanded(i, True)
        self.app.refresh()
        self.settle()

    def resize(self, width):
        self.width = width
        self.app._on_tree_configure(None)

    def settle(self, timeout=3.0):
        deadline = time.monotonic() + timeout
        while self.app._rewrap_job is not None:
            self.assertLess(time.monotonic(), deadline, "rewrap never ran")
            self.top.update()
            time.sleep(0.005)
        self.top.update()

    def expected(self, index):
        item = self.app.checklist.items[index]
        if not (item.note and item.expanded):
            return []
        return list(self.app._wrap_note(item.note, self.width))

    def assert_wrapped(self):
        for i in range(len(self.app.checklist)):
            self.assertEqual(self.kids(i), self.expected(i), f"row {i} at {self.width}px")


class DeferredRewrapTests(ResizeTestCase):
    def test_burst_of_resizes_rebuilds_once(self):
        self.with_expanded(LONG, LONG)
        with unittest.mock.patch.object(self.app, "refresh",
                                        wraps=self.app.refresh) as refresh:
            for w in range(300, 600, 5):
                self.resize(w)
                self.top.update()  # a real drag runs the event loop between steps
            self.assertEqual(refresh.call_count, 0, "no rebuild while the width moves")
            self.settle()
            self.assertEqual(refresh.call_count, 1)
        self.assert_wrapped()

    def test_lines_are_stale_during_drag_and_fresh_after(self):
        self.with_expanded(LONG)
        before = self.kids(0)
        self.resize(900)
        self.assertEqual(self.kids(0), before)
        self.settle()
        self.assertLess(len(self.kids(0)), len(before))
        self.assert_wrapped()

    def test_timer_restarts_on_every_step(self):
        self.with_expanded(LONG)
        self.resize(400)
        first = self.app._rewrap_job
        self.resize(410)
        self.assertNotEqual(self.app._rewrap_job, first)
        pending = self.top.tk.call("after", "info")
        self.assertNotIn(first, pending, "the old timer must be cancelled")
        self.assertIn(self.app._rewrap_job, pending)
        self.settle()

    def test_same_width_schedules_nothing(self):
        self.with_expanded(LONG)
        self.resize(self.width)
        self.assertIsNone(self.app._rewrap_job)

    def test_no_expanded_notes_schedules_nothing(self):
        self.with_expanded("", "")
        self.app.checklist.set_note(0, LONG)  # collapsed: nothing to rewrap
        self.app.refresh()
        self.resize(777)
        self.assertIsNone(self.app._rewrap_job)
        self.app.set_expanded(0, True)  # expanding later uses the new width
        self.assert_wrapped()

    def test_job_is_cleared_after_running(self):
        self.with_expanded(LONG)
        self.resize(500)
        job = self.app._rewrap_job
        self.assertIsNotNone(job)
        self.settle()
        self.assertIsNone(self.app._rewrap_job)
        self.assertNotIn(job, self.top.tk.call("after", "info"))

    def test_other_operation_during_pending_rewrap_uses_new_width(self):
        self.with_expanded(LONG, LONG)
        self.resize(800)
        self.app.toggle_index(0)  # refresh() right away, before the timer
        self.assert_wrapped()
        self.settle()
        self.assert_wrapped()
        self.assert_in_sync()

    def test_delete_and_collapse_before_timer(self):
        self.with_expanded(LONG, LONG, LONG)
        self.resize(250)
        self.app.select(1)
        self.app.delete_selected()
        self.app.set_expanded(0, False)
        self.settle()
        self.assert_in_sync()
        self.assert_wrapped()

    def test_open_new_list_before_timer(self):
        self.with_expanded(LONG)
        self.resize(640)
        self.app.checklist = Checklist()
        self.app.refresh()
        self.settle()
        self.assert_in_sync()
        self.assertEqual(self.app.tree.get_children(), ())

    def test_destroyed_window_with_pending_rewrap(self):
        self.with_expanded(LONG)
        self.resize(520)
        self.assertIsNotNone(self.app._rewrap_job)
        errors = []
        self.root.report_callback_exception = lambda *a: errors.append(a)
        try:
            self.top.destroy()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
        finally:
            del self.root.report_callback_exception
        self.assertEqual(errors, [])

    def test_resize_ends_inline_edit(self):
        self.with_expanded(LONG)
        self.app.begin_edit(0)
        self.app.editor.entry.insert("end", "!")
        self.resize(450)
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.app.checklist.items[0].text, "п0!")
        self.settle()
        self.assert_wrapped()

    def test_resize_commits_typed_note(self):
        self.with_expanded(LONG)
        self.app.select(0)
        self.app.note_text.insert("end", " хвост")  # not yet committed
        self.resize(480)
        self.assertTrue(self.app.checklist.items[0].note.endswith("хвост"))
        self.settle()
        self.assert_wrapped()

    def test_real_configure_event_reaches_handler(self):
        self.with_expanded(LONG)
        self.top.deiconify()  # Tk delivers <Configure> only to mapped windows
        self.top.update()
        self.settle()
        self.width = 555
        self.app.tree.event_generate("<Configure>", width=555, height=300)
        self.assertIsNotNone(self.app._rewrap_job)
        self.settle()
        self.assert_wrapped()

    def test_every_line_fits_after_settle(self):
        self.with_expanded(LONG, "а" * 200, "короткая\n\nс пустой строкой")
        for w in (60, 120, 333, 1000):
            self.resize(w)
            self.settle()
            self.assert_wrapped()
            font = self.app._note_font
            for i in range(3):
                for line in self.kids(i):
                    self.assertLessEqual(font.measure(line), w, (w, line))

    def test_random_resizes_and_operations(self):
        for seed in range(15):
            rng = random.Random(seed)
            self.app.checklist = Checklist()
            self.app.refresh()
            log = []
            for n in range(40):
                op = rng.choice(["resize", "resize", "resize", "settle", "add", "note",
                                 "expand", "delete", "toggle", "move"])
                size = len(self.app.checklist)
                log.append(op)
                if op == "resize":
                    self.resize(rng.randrange(40, 1200))
                elif op == "settle":
                    self.settle()
                    self.assert_wrapped()
                elif op == "add":
                    self.add(f"п{n}")
                elif op == "note" and size:
                    i = rng.randrange(size)
                    self.app.checklist.set_note(i, rng.choice(["", LONG, "x y z"]))
                    self.app.refresh()
                elif op == "expand" and size:
                    self.app.toggle_expanded(rng.randrange(size))
                elif op == "delete" and size:
                    self.app.select(rng.randrange(size))
                    self.app.delete_selected()
                elif op == "toggle" and size:
                    self.app.toggle_index(rng.randrange(size))
                elif op == "move" and size:
                    self.app.select(rng.randrange(size))
                    self.app.move_selected(rng.choice([-1, 1]))
                self.assert_in_sync()
            self.settle()
            self.assert_wrapped()
            self.assertIsNone(self.app._rewrap_job, f"seed {seed}: {log}")


class HintLabelTests(ResizeTestCase):
    def configure_hint(self, width):
        self.app._on_hint_configure(unittest.mock.Mock(width=width))

    def test_hint_is_bound_to_configure(self):
        self.assertIn("_on_hint_configure", self.app.hint.bind("<Configure>"))

    def test_hint_is_plain_tk_label(self):
        # A wrapped ttk.Label re-lays out its text on every redraw: slow while resizing.
        self.assertEqual(self.app.hint.winfo_class(), "Label")

    def test_wraplength_follows_width(self):
        self.configure_hint(321)
        self.assertEqual(int(self.app.hint.cget("wraplength")), 321)

    def test_narrow_width_is_clamped(self):
        self.configure_hint(3)
        self.assertEqual(int(self.app.hint.cget("wraplength")), 50)

    def test_unchanged_width_does_not_reconfigure(self):
        self.configure_hint(400)
        with unittest.mock.patch.object(self.app.hint, "configure",
                                        wraps=self.app.hint.configure) as configure:
            self.configure_hint(400)
            self.configure_hint(400)
            configure.assert_not_called()
            self.configure_hint(401)
            configure.assert_called_once_with(wraplength=401)

    def test_hint_colors_follow_theme(self):
        for mode in ("dark", "light", "dark"):
            self.app.set_theme_mode(mode)
            palette = theme.palette_for(self.app.theme)
            self.assertEqual(str(self.app.hint.cget("foreground")), palette.muted)
            self.assertEqual(str(self.app.hint.cget("background")), palette.bg)
        self.app.set_theme_mode("light")

    def test_hint_uses_ui_font_and_left_alignment(self):
        self.assertEqual(str(self.app.hint.cget("justify")), "left")
        self.assertEqual(str(self.app.hint.cget("anchor")), "w")
        font = tkfont.Font(root=self.top, font=self.app.hint.cget("font"))
        self.assertEqual(font.actual("size"), app_module.UI_FONT_SIZE)


class FontSizeTests(ResizeTestCase):
    def test_ui_font_is_ten_points(self):
        self.assertEqual(app_module.UI_FONT_SIZE, 10)
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            size = tkfont.nametofont(name, root=self.top).actual("size")
            self.assertEqual(size, app_module.UI_FONT_SIZE, name)

    def test_note_font_is_one_point_smaller(self):
        self.assertEqual(self.app._note_font.actual("size"), app_module.UI_FONT_SIZE - 1)
        self.assertTrue(self.app._note_font.actual("slant") == "italic")

    def test_rows_fit_the_font(self):
        linespace = tkfont.nametofont("TkDefaultFont", root=self.top).metrics("linespace")
        self.assertGreaterEqual(self.app._row_height, linespace)
        self.assertGreaterEqual(self.app._row_height, self.app._box)


if __name__ == "__main__":
    unittest.main()
