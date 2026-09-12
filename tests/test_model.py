import json
import os
import random
import tempfile
import unittest
from unittest import mock

from checkprog.model import Checklist, ChecklistFormatError, Item


def make(*texts, done=()):
    cl = Checklist()
    for t in texts:
        cl.add(t)
    for i in done:
        cl.toggle(i)
    cl.dirty = False
    return cl


def texts(cl):
    return [it.text for it in cl.items]


class TmpDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name="list.json"):
        return os.path.join(self.tmp, name)

    def write(self, content, name="list.json"):
        p = self.path(name)
        mode = "wb" if isinstance(content, bytes) else "w"
        kwargs = {} if isinstance(content, bytes) else {"encoding": "utf-8", "newline": ""}
        with open(p, mode, **kwargs) as f:
            f.write(content)
        return p


class EmptyListTests(unittest.TestCase):
    def test_new_list_is_empty_and_clean(self):
        cl = Checklist()
        self.assertEqual(len(cl), 0)
        self.assertEqual(cl.total, 0)
        self.assertEqual(cl.done_count, 0)
        self.assertEqual(cl.progress, 0.0)
        self.assertFalse(cl.dirty)
        self.assertIsNone(cl.path)

    def test_items_view_is_read_only(self):
        cl = make("a")
        with self.assertRaises((TypeError, AttributeError)):
            cl.items.append(Item("b"))
        self.assertEqual(len(cl), 1)


class AddTests(unittest.TestCase):
    def test_add_returns_index_and_strips(self):
        cl = Checklist()
        self.assertEqual(cl.add("  молоко  "), 0)
        self.assertEqual(cl.add("хлеб"), 1)
        self.assertEqual(texts(cl), ["молоко", "хлеб"])
        self.assertFalse(cl.items[0].done)

    def test_add_rejects_blank(self):
        cl = Checklist()
        for blank in ("", "   ", "\n\t ", "\r\n"):
            with self.subTest(blank=blank):
                self.assertIsNone(cl.add(blank))
        self.assertEqual(len(cl), 0)
        self.assertFalse(cl.dirty)

    def test_add_flattens_line_breaks_and_tabs(self):
        cl = Checklist()
        cl.add("a\nb\r\nc\td e")
        self.assertEqual(texts(cl), ["a b c d e"])

    def test_add_marks_dirty(self):
        cl = Checklist()
        cl.add("x")
        self.assertTrue(cl.dirty)

    def test_add_non_str_raises(self):
        with self.assertRaises(TypeError):
            Checklist().add(None)


class ItemOperationTests(unittest.TestCase):
    def test_toggle_flips_and_counts(self):
        cl = make("a", "b", "c")
        cl.toggle(1)
        self.assertEqual([it.done for it in cl.items], [False, True, False])
        self.assertEqual(cl.done_count, 1)
        self.assertTrue(cl.dirty)
        cl.toggle(1)
        self.assertEqual(cl.done_count, 0)

    def test_set_done_same_value_is_not_a_change(self):
        cl = make("a", done=(0,))
        cl.set_done(0, True)
        self.assertFalse(cl.dirty)
        cl.set_done(0, False)
        self.assertTrue(cl.dirty)

    def test_rename(self):
        cl = make("a", "b")
        self.assertTrue(cl.rename(0, "  новое  "))
        self.assertEqual(texts(cl), ["новое", "b"])
        self.assertTrue(cl.dirty)

    def test_rename_to_blank_keeps_old_text(self):
        cl = make("a")
        self.assertFalse(cl.rename(0, "   "))
        self.assertEqual(texts(cl), ["a"])
        self.assertFalse(cl.dirty)

    def test_rename_to_same_text_is_not_a_change(self):
        cl = make("a")
        self.assertFalse(cl.rename(0, " a "))
        self.assertFalse(cl.dirty)

    def test_rename_keeps_done_flag(self):
        cl = make("a", done=(0,))
        cl.rename(0, "b")
        self.assertTrue(cl.items[0].done)

    def test_remove_returns_item(self):
        cl = make("a", "b", "c", done=(1,))
        removed = cl.remove(1)
        self.assertEqual(removed, Item("b", True))
        self.assertEqual(texts(cl), ["a", "c"])
        self.assertEqual(cl.done_count, 0)
        self.assertTrue(cl.dirty)

    def test_bad_indexes_raise_and_change_nothing(self):
        ops = [
            lambda cl, i: cl.toggle(i),
            lambda cl, i: cl.set_done(i, True),
            lambda cl, i: cl.rename(i, "x"),
            lambda cl, i: cl.remove(i),
            lambda cl, i: cl.move(i, 0),
        ]
        for op in ops:
            for bad in (-1, 3, 100, True, 1.0, "0"):
                with self.subTest(op=op, bad=bad):
                    cl = make("a", "b", "c")
                    with self.assertRaises((IndexError, TypeError)):
                        op(cl, bad)
                    self.assertEqual(texts(cl), ["a", "b", "c"])
                    self.assertFalse(cl.dirty)


class MoveTests(unittest.TestCase):
    def test_move_every_pair_is_a_permutation(self):
        orig = ["a", "b", "c", "d"]
        for src in range(4):
            for dst in range(4):
                with self.subTest(src=src, dst=dst):
                    cl = make(*orig)
                    new = cl.move(src, dst)
                    got = texts(cl)
                    self.assertEqual(new, dst)
                    self.assertEqual(sorted(got), sorted(orig))
                    self.assertEqual(got[new], orig[src])
                    others = [t for t in orig if t != orig[src]]
                    self.assertEqual([t for t in got if t != orig[src]], others)
                    self.assertEqual(cl.dirty, src != dst)

    def test_move_clamps_destination(self):
        cl = make("a", "b", "c", "d")
        self.assertEqual(cl.move(0, 99), 3)
        self.assertEqual(texts(cl), ["b", "c", "d", "a"])
        self.assertEqual(cl.move(3, -5), 0)
        self.assertEqual(texts(cl), ["a", "b", "c", "d"])

    def test_move_keeps_done_flag_with_item(self):
        cl = make("a", "b", "c", done=(0,))
        cl.move(0, 2)
        self.assertEqual([(it.text, it.done) for it in cl.items],
                         [("b", False), ("c", False), ("a", True)])


class ProgressTests(unittest.TestCase):
    def test_progress_values(self):
        self.assertEqual(make("a", "b").progress, 0.0)
        self.assertEqual(make("a", "b", done=(0,)).progress, 0.5)
        self.assertEqual(make("a", "b", done=(0, 1)).progress, 1.0)


class RandomInvariantTests(unittest.TestCase):
    TEXTS = ["", "  ", "молоко", "a\nb", "\t x \t", "😀 эмодзи", '"кавычки"', "x" * 300]

    def check_invariants(self, cl):
        self.assertEqual(cl.total, len(cl.items))
        self.assertEqual(cl.done_count, sum(1 for it in cl.items if it.done))
        self.assertLessEqual(cl.done_count, cl.total)
        self.assertTrue(0.0 <= cl.progress <= 1.0)
        for it in cl.items:
            self.assertIsInstance(it.text, str)
            self.assertIsInstance(it.done, bool)
            self.assertTrue(it.text)
            self.assertEqual(it.text, it.text.strip())
            self.assertFalse(set(it.text) & set("\r\n\t"))

    def test_random_operation_sequences(self):
        for seed in range(25):
            rng = random.Random(seed)
            cl = Checklist()
            for _ in range(200):
                n = len(cl)
                op = rng.choice(["add", "add", "toggle", "rename", "remove", "move"])
                before = sorted(texts(cl))
                if op == "add":
                    t = rng.choice(self.TEXTS)
                    idx = cl.add(t)
                    self.assertEqual(len(cl), n + (idx is not None))
                elif n == 0:
                    continue
                elif op == "toggle":
                    cl.toggle(rng.randrange(n))
                    self.assertEqual(sorted(texts(cl)), before)
                elif op == "rename":
                    cl.rename(rng.randrange(n), rng.choice(self.TEXTS))
                    self.assertEqual(len(cl), n)
                elif op == "remove":
                    cl.remove(rng.randrange(n))
                    self.assertEqual(len(cl), n - 1)
                else:
                    new = cl.move(rng.randrange(n), rng.randint(-3, n + 3))
                    self.assertTrue(0 <= new < n)
                    self.assertEqual(sorted(texts(cl)), before)
                self.check_invariants(cl)


class SaveLoadTests(TmpDirTestCase):
    SAMPLE = ["Привет, мир", 'кавычки "x" и \\ слеш', "эмодзи 😀", "ё Ё й"]

    def test_roundtrip_preserves_items(self):
        cl = make(*self.SAMPLE, done=(1, 3))
        cl.save(self.path())
        loaded = Checklist.load(self.path())
        self.assertEqual(loaded.items, cl.items)

    def test_file_is_readable_utf8_json(self):
        cl = make("Молоко", done=(0,))
        cl.save(self.path())
        with open(self.path(), encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("Молоко", raw)
        self.assertEqual(json.loads(raw),
                         {"version": 1, "items": [{"text": "Молоко", "done": True}]})

    def test_save_clears_dirty_and_sets_absolute_path(self):
        cl = make("a")
        cl.add("b")
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            cl.save("rel.json")
        finally:
            os.chdir(cwd)
        self.assertFalse(cl.dirty)
        self.assertTrue(os.path.isabs(cl.path))
        self.assertEqual(os.path.normcase(cl.path), os.path.normcase(self.path("rel.json")))

    def test_save_without_path_raises(self):
        with self.assertRaises(ValueError):
            make("a").save()

    def test_save_as_switches_path_and_leaves_old_file(self):
        cl = make("a")
        cl.save(self.path("one.json"))
        cl.add("b")
        cl.save(self.path("two.json"))
        self.assertEqual(os.path.basename(cl.path), "two.json")
        self.assertEqual(texts(Checklist.load(self.path("one.json"))), ["a"])
        self.assertEqual(texts(Checklist.load(self.path("two.json"))), ["a", "b"])

    def test_save_leaves_no_temp_files(self):
        cl = make("a")
        cl.save(self.path())
        cl.add("b")
        cl.save()
        self.assertEqual(os.listdir(self.tmp), ["list.json"])

    def test_load_sets_path_and_is_clean(self):
        make("a").save(self.path())
        cl = Checklist.load(self.path())
        self.assertFalse(cl.dirty)
        self.assertEqual(os.path.normcase(cl.path), os.path.normcase(self.path()))

    def test_load_accepts_bom(self):
        p = self.write('﻿{"version": 1, "items": [{"text": "да", "done": true}]}')
        self.assertEqual(Checklist.load(p).items, (Item("да", True),))

    def test_load_defaults_and_cleanup(self):
        p = self.write(json.dumps({"items": [
            {"text": "без done"},
            {"text": "   ", "done": True},
            {"text": "перенос\nстроки", "done": False},
        ]}))
        cl = Checklist.load(p)
        self.assertEqual(cl.items, (Item("без done", False), Item("перенос строки", False)))

    def test_load_rejects_bad_structure(self):
        bad = [
            "",
            "not json",
            "[]",
            '"str"',
            "{}",
            '{"items": {}}',
            '{"items": [1]}',
            '{"items": [{"done": true}]}',
            '{"items": [{"text": 5}]}',
            '{"items": [{"text": "a", "done": "false"}]}',
            '{"items": [{"text": "a", "done": 1}]}',
            '{"version": 2, "items": []}',
            '{"version": "1", "items": []}',
            '{"version": true, "items": []}',
        ]
        for content in bad:
            with self.subTest(content=content):
                p = self.write(content)
                with self.assertRaises(ChecklistFormatError):
                    Checklist.load(p)

    def test_load_rejects_non_utf8(self):
        p = self.write(b'{"items": [{"text": "\xcf\xf0\xe8\xe2\xe5\xf2"}]}')
        with self.assertRaises(ChecklistFormatError):
            Checklist.load(p)

    def test_load_missing_file_raises_oserror(self):
        with self.assertRaises(FileNotFoundError):
            Checklist.load(self.path("nope.json"))

    def test_failed_replace_keeps_original_file(self):
        cl = make("старое")
        cl.save(self.path())
        cl.add("новое")
        with mock.patch("checkprog.model.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cl.save()
        self.assertEqual(texts(Checklist.load(self.path())), ["старое"])
        self.assertEqual(os.listdir(self.tmp), ["list.json"])
        self.assertTrue(cl.dirty)

    def test_failed_write_keeps_original_file(self):
        cl = make("старое")
        cl.save(self.path())
        cl.add("новое")
        with mock.patch("checkprog.model.json.dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                cl.save()
        self.assertEqual(texts(Checklist.load(self.path())), ["старое"])
        self.assertEqual(os.listdir(self.tmp), ["list.json"])

    def test_failed_save_as_keeps_old_path(self):
        cl = make("a")
        cl.save(self.path("one.json"))
        missing_dir = os.path.join(self.tmp, "нет такой папки", "two.json")
        with self.assertRaises(OSError):
            cl.save(missing_dir)
        self.assertEqual(os.path.basename(cl.path), "one.json")


if __name__ == "__main__":
    unittest.main()
