"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/output_folder.py.
Run as a script, it has end-to-end tests in test_e2e_output.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

The config's CONFIG_PATH is patched to a file in a temporary folder, which each
test writes, and TEMP_ROOT to a folder inside it.
"""

import json
import os
from datetime import date, datetime, timedelta, timezone
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import config, output_folder  # noqa: E402


class OutputFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "config.json")
        self.temp_root = os.path.join(self.tmp.name, "temp")
        for target, attribute, value in ((config, "CONFIG_PATH", self.path),
                                         (output_folder, "TEMP_ROOT", self.temp_root)):
            patcher = mock.patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def test_output_root(self):
        # None: the config sets no usable root, so skills use the temp folder.
        cases = [({"output": {"root": " ~/reports "}}, os.path.join(os.path.expanduser("~"), "reports")),
                 ({}, None), ({"output": {}}, None), ({
                     "output": {"root": "<path>"}}, None),
                 ({"output": {"root": " "}}, None), ({
                     "output": {"root": " <path> "}}, None),
                 ({"output": {"root": 5}}, None), ({"output": []}, None)]
        for data, expected in cases:
            with self.subTest(data=data):
                self.write(data)
                self.assertEqual(output_folder.output_root(), expected)

    def test_unreadable_config(self):
        for call in (output_folder.output_root, lambda: output_folder.output_folder("reports")):
            with self.assertRaisesRegex(SystemExit, "could not read"):
                call()

    def test_output_folder(self):
        # The folder is absolute, even for a relative root, created if
        # missing, and keeps what is already in it.
        cases = [
            ("in the output root", {"output": {"root": os.path.join(self.tmp.name, "reports")}},
             (os.path.join(self.tmp.name, "reports", "jira-sprint-reports"), False)),
            ("in a relative output root", {"output": {"root": "relative"}},
             (os.path.join(os.path.realpath(self.tmp.name), "relative", "jira-sprint-reports"), False)),
            ("in the temp folder without an output root", {},
             (os.path.join(self.temp_root, "jira-sprint-reports"), True)),
        ]
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, cwd)
        for name, data, expected in cases:
            with self.subTest(name):
                self.write(data)
                self.assertEqual(output_folder.output_folder(
                    "jira-sprint-reports"), expected)
                with open(os.path.join(expected[0], "kept.md"), "w", encoding="utf-8") as f:
                    f.write("x")
                self.assertEqual(output_folder.output_folder(
                    "jira-sprint-reports"), expected)
                self.assertEqual(os.listdir(expected[0]), ["kept.md"])

    def test_name_must_be_one_folder(self):
        # The same rule on the command line and for a script that imports
        # output_folder(); a refused name creates nothing.
        self.write({})
        cases = [("tech-investigations", "tech-investigations"), (" reports ", "reports"),
                 ("", None), ("  ", None), (".",
                                            None), ("..", None), ("../outside", None),
                 (os.path.join("a", "b"), None), (os.path.join(self.tmp.name, "outside"), None)]
        for value, expected in cases:
            with self.subTest(value=value):
                if expected:
                    self.assertEqual(output_folder.parse_args(
                        ["--name", value]).name, expected)
                    self.assertEqual(os.path.basename(
                        output_folder.output_folder(value)[0]), expected)
                else:
                    with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                        output_folder.parse_args(["--name", value])
                    with self.assertRaisesRegex(SystemExit, "single folder name"):
                        output_folder.output_folder(value)
        self.assertEqual(sorted(os.listdir(self.temp_root)),
                         ["reports", "tech-investigations"])


class DayFolderTest(unittest.TestCase):
    def test_day_folder(self):
        # A datetime's own day is used, as its time zone gives it.
        cases = [("a date", date(2026, 3, 6), "PROJ_Sprint_3_26-03-06"),
                 ("a datetime", datetime(2026, 12, 31, 23, 59),
                  "PROJ_Sprint_3_26-12-31"),
                 ("a datetime in a time zone",
                  datetime(2026, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))), "PROJ_Sprint_3_26-01-01")]
        for name, day, expected in cases:
            with self.subTest(name):
                self.assertEqual(output_folder.day_folder(
                    "PROJ_Sprint_3", day), expected)
                # DAY_FOLDER reads the name back.
                match = output_folder.DAY_FOLDER.fullmatch(expected)
                assert match
                self.assertEqual((match["subject"], match["date"]),
                                 ("PROJ_Sprint_3", expected[-8:]))

    def test_clear_folder(self):
        # Only what is at the path goes: a link's target and the folder
        # around it stay.
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            os.makedirs(os.path.join(target, "kept"))

            def folder(path):
                os.makedirs(os.path.join(path, "sub"))
                with open(os.path.join(path, "sub", "file.md"), "w", encoding="utf-8") as f:
                    f.write("x")

            def file(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("x")
            cases = [("a folder with files", folder, True),
                     ("a file", file, True),
                     ("a link to a folder", lambda path: os.symlink(
                         target, path), True),
                     ("a broken link", lambda path: os.symlink(
                         os.path.join(tmp, "missing"), path), True),
                     ("nothing", lambda path: None, False)]
            for name, make, expected in cases:
                with self.subTest(name):
                    path = os.path.join(tmp, "PROJ_26-03-06")
                    make(path)
                    self.assertEqual(
                        output_folder.clear_folder(path), expected)
                    self.assertFalse(os.path.lexists(path))
                    self.assertEqual(sorted(os.listdir(tmp)), ["target"])
                    self.assertEqual(os.listdir(target), ["kept"])


class DescriptionTest(unittest.TestCase):
    def test_read_description(self):
        # (text, or None for no file, expected): the title, and every labelled
        # line, a label holding any character but * such as an apostrophe.
        cases = [(None, ("", {})),
                 ("No title.\n", ("", {})),
                 ("# A slide  \n\n**Use for:** a cover\n\n**Why it's good:** clear  \n",
                  ("A slide", {"Use for": "a cover", "Why it's good": "clear"})),
                 ("# Title\n\nSome **bold** text.\n", ("Title", {}))]
        for text, expected in cases:
            with self.subTest(text), tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, output_folder.EXAMPLE_DESCRIPTION)
                if text is not None:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                self.assertEqual(
                    output_folder.read_description(path), expected)


class TempRootTest(unittest.TestCase):
    def test_temp_root_is_in_the_system_temp_folder(self):
        self.assertTrue(output_folder.TEMP_ROOT.startswith(
            tempfile.gettempdir()))


if __name__ == "__main__":
    unittest.main()
