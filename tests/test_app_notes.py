import tkinter as tk
import unittest
import unittest.mock

from checkprog import app as app_module
from checkprog import theme
from checkprog.model import Checklist
from tests.test_app import AppTestCase


class NoteTestCase(AppTestCase):
    def note(self):
        return self.app.note_text.get("1.0", "end-1c")

    def type_note(self, text):
        self.app.note_text.insert("end", text)
        self.top.update()  # delivers <<Modified>> like real typing

    def panel_enabled(self):
        return str(self.app.note_text.cget("state")) == "normal"


class NotePanelTests(NoteTestCase):
    def test_disabled_without_selection(self):
        self.assertIsNone(self.app.note_index)
        self.assertFalse(self.panel_enabled())
        self.assertEqual(self.note(), "")

    def test_selecting_item_shows_its_note(self):
        self.add("a", "b")
        self.app.checklist.set_note(0, "заметка a")
        self.app.select(0)
        self.assertTrue(self.panel_enabled())
        self.assertEqual(self.note(), "заметка a")
        self.assertIn("«a»", self.app.note_label.cget("text"))
        self.app.select(1)
        self.assertEqual(self.note(), "")
        self.assertIn("«b»", self.app.note_label.cget("text"))

    def test_typing_commits_note_and_marks_row(self):
        self.add("a")
        self.app.checklist.dirty = False
        self.app.refresh()
        self.app.select(0)
        self.type_note("купить\nфартук")
        self.assertEqual(self.app.checklist.items[0].note, "купить\nфартук")
        self.assertTrue(self.app.checklist.dirty)
        self.assert_in_sync()
        self.assertEqual(self.rows()[0][1], app_module.NOTE_MARK)

    def test_clearing_note_removes_marker(self):
        self.add("a")
        self.app.select(0)
        self.type_note("x")
        self.app.note_text.delete("1.0", "end")
        self.top.update()
        self.assertEqual(self.app.checklist.items[0].note, "")
        self.assertEqual(self.rows()[0][1], "")

    def test_save_includes_uncommitted_note(self):
        self.add("a")
        self.app.select(0)
        self.app.note_text.insert("end", "без update")
        self.fdm["asksaveasfilename"].return_value = self.p("n.json")
        self.assertTrue(self.app.save())
        self.assertEqual(Checklist.load(self.p("n.json")).items[0].note, "без update")

    def test_note_follows_item_when_moved(self):
        self.add("a", "b", "c")
        self.app.checklist.set_note(0, "A")
        self.app.select(0)
        self.app.move_selected(1)
        self.assertEqual(self.app.note_index, 1)
        self.assertEqual(self.note(), "A")

    def test_delete_moves_panel_to_neighbour(self):
        self.add("a", "b")
        self.app.checklist.set_note(0, "A")
        self.app.checklist.set_note(1, "B")
        self.app.select(0)
        self.app.delete_selected()
        self.assertEqual(self.app.selected_index(), 0)
        self.assertEqual(self.note(), "B")
        self.type_note("!")
        self.assertEqual([it.note for it in self.app.checklist.items], ["B!"])

    def test_panel_never_writes_into_another_item(self):
        self.add("a", "b")
        self.app.select(0)
        self.app.note_text.insert("end", "для a")
        self.app.checklist.remove(0)  # bypasses the UI flush on purpose
        self.app.refresh(select=0)
        self.assertEqual(self.app.checklist.items[0].note, "")
        self.assertEqual(self.note(), "")

    def test_undo_does_not_cross_items(self):
        self.add("a", "b")
        self.app.select(0)
        self.type_note("AAA")
        self.app.select(1)
        try:
            self.app.note_text.edit_undo()
        except tk.TclError:
            pass  # "nothing to undo" is the expected outcome
        self.top.update()
        self.assertEqual(self.note(), "")
        self.assertEqual([it.note for it in self.app.checklist.items], ["AAA", ""])

    def test_deselect_disables_panel(self):
        self.add("a")
        self.app.select(0)
        self.app.deselect()
        self.assertIsNone(self.app.selected_index())
        self.assertIsNone(self.app.note_index)
        self.assertFalse(self.panel_enabled())
        self.assertEqual(self.note(), "")
        self.assert_in_sync()

    def test_deselect_commits_pending_note(self):
        self.add("a")
        self.app.select(0)
        self.app.note_text.insert("end", "x")
        self.app.deselect()
        self.assertEqual(self.app.checklist.items[0].note, "x")

    def test_open_file_shows_notes_and_marker(self):
        cl = Checklist()
        cl.add("с заметкой")
        cl.set_note(0, "текст")
        cl.save(self.p("f.json"))
        self.fdm["askopenfilename"].return_value = self.p("f.json")
        self.app.open_file()
        self.assert_in_sync()
        self.assertEqual(self.app.selected_index(), 0)
        self.assertEqual(self.note(), "текст")

    def test_new_file_clears_panel(self):
        self.add("a")
        self.app.select(0)
        self.type_note("x")
        self.mb["askyesnocancel"].return_value = False
        self.app.new_file()
        self.assertIsNone(self.app.note_index)
        self.assertEqual(self.note(), "")

    def test_theme_switch_keeps_uncommitted_text_and_recolors(self):
        self.add("a")
        self.app.select(0)
        self.app.note_text.insert("end", "черновик")
        self.app.set_theme_mode("dark")
        try:
            self.assertEqual(self.note(), "черновик")
            self.assertEqual(str(self.app.note_text.cget("background")), theme.DARK.field)
        finally:
            self.app.set_theme_mode("light")

    def test_comment_menu_entry_exists_and_enables_panel(self):
        menu = self.app.item_menu
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
                  if menu.type(i) != "separator"]
        self.assertIn("Комментарий", labels)
        self.add("a")
        self.app.select(0)
        self.app.edit_note()
        self.assertTrue(self.panel_enabled())

    def test_edit_note_without_selection_is_harmless(self):
        self.app.edit_note()
        self.assertFalse(self.panel_enabled())

    def test_rename_keeps_pending_note(self):
        self.add("a")
        self.app.select(0)
        self.app.note_text.insert("end", "N")
        self.app.begin_edit(0)
        self.app.editor.entry.delete(0, "end")
        self.app.editor.entry.insert(0, "b")
        self.app.end_edit(True)
        self.assertEqual((self.app.checklist.items[0].text, self.app.checklist.items[0].note),
                         ("b", "N"))
        self.assertEqual(self.note(), "N")
        self.assertIn("«b»", self.app.note_label.cget("text"))

    def test_toggle_keeps_pending_note(self):
        self.add("a")
        self.app.select(0)
        self.app.note_text.insert("end", "N")
        self.app.toggle_index(0)
        self.assertEqual(self.app.checklist.items[0].note, "N")
        self.assertTrue(self.app.checklist.items[0].done)
        self.assertEqual(self.note(), "N")

    def test_drag_keeps_note_on_moved_item(self):
        self.add("a", "b", "c")
        self.app.select(0)
        self.type_note("A")
        self.app.drag_start(0)
        self.app.drag_to(2)
        self.app.drag_end()
        self.assertEqual([it.note for it in self.app.checklist.items], ["", "", "A"])
        self.assertEqual((self.app.note_index, self.note()), (2, "A"))

    def test_undo_commits(self):
        self.add("a")
        self.app.select(0)
        self.type_note("x")
        self.app.note_text.edit_separator()
        self.type_note("y")
        self.app.note_text.edit_undo()
        self.top.update()
        self.assertEqual(self.app.checklist.items[0].note, "x")

    def test_exit_asks_about_uncommitted_note(self):
        self.add("a")
        self.app.checklist.dirty = False
        self.app.select(0)
        self.app.note_text.insert("end", "x")
        self.mb["askyesnocancel"].return_value = None
        self.app.on_exit()
        self.mb["askyesnocancel"].assert_called_once()
        self.assertTrue(self.top.winfo_exists())

    def test_whitespace_only_note_is_empty(self):
        self.add("a")
        self.app.select(0)
        self.type_note("  \n\t ")
        self.assertEqual(self.app.checklist.items[0].note, "")
        self.assertEqual(self.rows()[0][1], "")


class ExpandTests(NoteTestCase):
    def kids(self, index):
        tree = self.app.tree
        return [str(tree.item(k, "values")[0]) for k in tree.get_children(str(index))]

    def with_notes(self, *notes):
        self.add(*(f"п{i}" for i in range(len(notes))))
        for i, note in enumerate(notes):
            self.app.checklist.set_note(i, note)
        self.app.refresh()

    def test_arrow_only_for_items_with_notes(self):
        self.with_notes("есть", "")
        self.assertEqual([r[1] for r in self.rows()], [app_module.NOTE_MARK, ""])
        self.assertFalse(self.app.set_expanded(1, True))
        self.assertEqual(self.kids(1), [])

    def test_expand_shows_lines_and_collapse_hides(self):
        self.with_notes("раз\nдва", "")
        self.app.checklist.dirty = False
        self.app.refresh()
        self.assertTrue(self.app.set_expanded(0, True))
        self.assertEqual(self.kids(0), ["раз", "два"])
        self.assertEqual(self.rows()[0][1], app_module.NOTE_OPEN_MARK)
        self.assertFalse(self.app.checklist.dirty)  # view state only
        self.assert_in_sync()  # top-level rows are still exactly the items
        self.app.set_expanded(0, False)
        self.assertEqual(self.kids(0), [])
        self.assertEqual(self.rows()[0][1], app_module.NOTE_MARK)

    def test_typing_in_panel_updates_open_lines(self):
        self.with_notes("старое")
        self.app.set_expanded(0, True)
        self.app.select(0)
        self.app.note_text.delete("1.0", "end")
        self.type_note("новое\nвторая")
        self.assertEqual(self.kids(0), ["новое", "вторая"])

    def test_clearing_note_hides_lines_and_arrow(self):
        self.with_notes("x")
        self.app.set_expanded(0, True)
        self.app.select(0)
        self.app.note_text.delete("1.0", "end")
        self.top.update()
        self.assertEqual(self.kids(0), [])
        self.assertEqual(self.rows()[0][1], "")

    def test_lines_follow_item_on_move_and_delete(self):
        self.with_notes("A", "B", "")
        self.app.set_expanded(0, True)
        self.app.select(0)
        self.app.move_selected(1)
        self.assertEqual((self.kids(0), self.kids(1)), ([], ["A"]))
        self.app.select(0)
        self.app.delete_selected()
        self.assertEqual((self.kids(0), self.kids(1)), (["A"], []))
        self.assert_in_sync()

    def test_expand_keeps_uncommitted_panel_text(self):
        self.with_notes("x")
        self.app.select(0)
        self.app.note_text.insert("end", "y")
        self.app.set_expanded(0, True)
        self.assertEqual(self.app.checklist.items[0].note, "xy")
        self.assertEqual(self.note(), "xy")
        self.assertEqual(self.kids(0), ["xy"])
        self.assertIs(self.app._note_item, self.app.checklist.items[0])

    def test_long_note_wraps_within_column(self):
        words = ["слово"] * 60
        self.with_notes(" ".join(words))
        self.app.set_expanded(0, True)
        width = self.app._note_width()
        lines = self.kids(0)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(self.app._note_font.measure(line), width)
        self.assertEqual(" ".join(lines).split(), words)

    def test_long_word_is_cut(self):
        word = "ж" * 400
        self.with_notes(word)
        self.app.set_expanded(0, True)
        lines = self.kids(0)
        self.assertGreater(len(lines), 1)
        self.assertEqual("".join(lines), word)
        width = self.app._note_width()
        self.assertTrue(all(self.app._note_font.measure(s) <= width for s in lines))

    def test_blank_lines_are_kept(self):
        self.with_notes("a\n\nb")
        self.app.set_expanded(0, True)
        self.assertEqual(self.kids(0), ["a", "", "b"])

    def test_note_line_is_never_selected(self):
        self.with_notes("a", "")
        self.app.set_expanded(0, True)
        self.app.tree.selection_set("0.0")
        self.top.update()
        self.assertEqual(self.app.tree.selection(), ("0",))
        self.assertEqual(self.app.selected_index(), 0)

    def test_expand_all_and_collapse_all_from_view_menu(self):
        self.with_notes("A", "", "C")
        view = self.app.bar_menus["view"]
        labels = [view.entrycget(i, "label") for i in range(view.index("end") + 1)]
        view.invoke(labels.index("Развернуть все комментарии"))
        self.assertEqual([it.expanded for it in self.app.checklist.items], [True, False, True])
        self.assertEqual((self.kids(0), self.kids(2)), (["A"], ["C"]))
        view.invoke(labels.index("Свернуть все комментарии"))
        self.assertEqual((self.kids(0), self.kids(2)), ([], []))

    def test_expanded_state_is_not_saved(self):
        self.with_notes("A")
        self.app.set_expanded(0, True)
        self.fdm["asksaveasfilename"].return_value = self.p("e.json")
        self.app.save()
        self.app.open_path(self.p("e.json"))
        self.assertEqual(self.kids(0), [])

    def test_resize_rewraps(self):
        self.with_notes(" ".join(["слово"] * 30))
        self.app.set_expanded(0, True)
        before = self.kids(0)
        with unittest.mock.patch.object(self.app, "_note_width", return_value=2000):
            self.app.refresh()
        self.assertEqual(len(self.kids(0)), 1)
        self.app.refresh()
        self.assertEqual(self.kids(0), before)


class NoteRandomOpsTests(NoteTestCase):
    """Random UI sequences; after each step the panel, tree and model must agree."""

    def check(self, step):
        app = self.app
        self.assert_in_sync()
        sel = app.selected_index()
        self.assertEqual(app.note_index, sel, step)
        if sel is None:
            self.assertFalse(self.panel_enabled(), step)
            self.assertEqual(self.note(), "", step)
        else:
            self.assertTrue(self.panel_enabled(), step)
            self.assertIs(app._note_item, app.checklist.items[sel], step)
            from checkprog.model import clean_note
            self.assertEqual(clean_note(self.note()), app.checklist.items[sel].note, step)
        width = app._note_width()
        for i, item in enumerate(app.checklist.items):
            shown = app.tree.get_children(str(i))
            expected = app._wrap_note(item.note, width) if item.expanded and item.note else ()
            self.assertEqual(tuple(str(app.tree.item(k, "values")[0]) for k in shown),
                             expected, step)
            self.assertEqual(list(shown), [f"{i}.{k}" for k in range(len(expected))], step)

    def test_random_sequences(self):
        import random
        for seed in range(25):
            rng = random.Random(seed)
            self.app.checklist = Checklist()
            self.app.refresh()
            log = []
            for n in range(60):
                op = rng.choice(["add", "select", "type", "type_raw", "delete", "move",
                                 "drag", "toggle", "deselect", "rename", "theme",
                                 "expand", "expand", "expand_all"])
                size = len(self.app.checklist)
                log.append(op)
                if op == "add":
                    self.add(f"п{n}")
                elif op == "select" and size:
                    self.app.select(rng.randrange(size))
                elif op == "type":
                    self.type_note(rng.choice(["x", "\n", " ", "да"]))
                elif op == "type_raw":
                    self.app.note_text.insert("end", "r")  # no update: not yet committed
                elif op == "delete":
                    self.app.delete_selected()
                elif op == "move":
                    self.app.move_selected(rng.choice([-1, 1]))
                elif op == "drag" and size:
                    self.app.drag_start(rng.randrange(size))
                    self.app.drag_to(rng.randrange(size))
                    self.app.drag_end()
                elif op == "toggle":
                    self.app.toggle_selected()
                elif op == "deselect":
                    self.app.deselect()
                elif op == "rename" and self.app.selected_index() is not None:
                    self.app.begin_edit(self.app.selected_index())
                    self.app.editor.entry.insert("end", "!")
                    self.app.end_edit(True)
                elif op == "theme":
                    self.app.set_theme_mode(rng.choice(["light", "dark"]))
                elif op == "expand" and size:
                    self.app.toggle_expanded(rng.randrange(size))
                elif op == "expand_all":
                    self.app.expand_all(rng.choice([True, False]))
                self.top.update()
                self.check(f"seed {seed}: {log}")
        self.app.set_theme_mode("light")


if __name__ == "__main__":
    unittest.main()
