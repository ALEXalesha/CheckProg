import os
import tempfile
import unittest

from checkprog.settings import PORTABLE_MARKER, load_settings, resolve_paths, save_settings


class TmpDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


class ResolvePathsTests(TmpDirTestCase):
    def test_portable_when_marker_present(self):
        open(self.p(PORTABLE_MARKER), "w").close()
        paths = resolve_paths(self.tmp, appdata=self.p("A"), documents=self.p("D"))
        self.assertTrue(paths.portable)
        self.assertEqual(paths.settings_file, self.p("settings.json"))
        self.assertEqual(paths.lists_dir, self.p("lists"))

    def test_installed_without_marker(self):
        paths = resolve_paths(self.tmp, appdata=self.p("A"), documents=self.p("D"))
        self.assertFalse(paths.portable)
        self.assertEqual(paths.settings_file, self.p("A", "CheckProg", "settings.json"))
        self.assertEqual(paths.lists_dir, self.p("D", "CheckProg"))

    def test_marker_must_be_a_file(self):
        os.mkdir(self.p(PORTABLE_MARKER))
        paths = resolve_paths(self.tmp, appdata=self.p("A"), documents=self.p("D"))
        self.assertFalse(paths.portable)

    def test_defaults_work_without_arguments(self):
        paths = resolve_paths(self.tmp)
        self.assertTrue(os.path.isabs(paths.settings_file))
        self.assertTrue(os.path.isabs(paths.lists_dir))


class SettingsIOTests(TmpDirTestCase):
    def write(self, name, data):
        with open(self.p(name), "wb") as f:
            f.write(data)
        return self.p(name)

    def test_missing_file_gives_empty_dict(self):
        self.assertEqual(load_settings(self.p("nope.json")), {})

    def test_broken_files_give_empty_dict(self):
        for data in (b"", b"not json", b"[1, 2]", b'"x"', b"\xff\xfe\x00garbage"):
            with self.subTest(data=data):
                self.assertEqual(load_settings(self.write("s.json", data)), {})

    def test_directory_instead_of_file_gives_empty_dict(self):
        os.mkdir(self.p("dir.json"))
        self.assertEqual(load_settings(self.p("dir.json")), {})

    def test_roundtrip_creates_parent_dirs(self):
        target = self.p("a", "b", "settings.json")
        data = {"last_file": "C:\\Списки\\покупки.json"}
        self.assertTrue(save_settings(target, data))
        self.assertEqual(load_settings(target), data)
        self.assertEqual(os.listdir(self.p("a", "b")), ["settings.json"])

    def test_unwritable_location_returns_false(self):
        open(self.p("file"), "w").close()
        self.assertFalse(save_settings(self.p("file", "settings.json"), {"a": 1}))


if __name__ == "__main__":
    unittest.main()
