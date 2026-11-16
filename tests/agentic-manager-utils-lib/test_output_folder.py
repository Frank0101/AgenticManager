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

    def test_new_run(self):
        # A run starts empty: the same subject's folder of that day is
        # replaced, another day's stays.
        self.write({})
        folder = os.path.join(self.temp_root, "slides-decks")
        os.makedirs(os.path.join(folder, "Acme_26-03-05"))
        for name, expected_replaced in (("first run", False), ("rerun the same day", True)):
            with self.subTest(name):
                result = output_folder.new_run(
                    "slides-decks", "Acme", date(2026, 3, 6))
                self.assertEqual(
                    result, (folder, True, "Acme_26-03-06", expected_replaced))
                path = os.path.join(folder, "Acme_26-03-06")
                self.assertEqual(os.listdir(path), [])
                with open(os.path.join(path, "slides.json"), "w", encoding="utf-8") as f:
                    f.write("{}")
        self.assertEqual(sorted(os.listdir(folder)), [
                         "Acme_26-03-05", "Acme_26-03-06"])

    def test_run_folder(self):
        # name: (run, the path expected, or the message an exit gives)
        self.write({})
        folder = os.path.join(self.temp_root, "slides-decks")
        os.makedirs(os.path.join(folder, "Acme_26-03-06"))
        cases = [("an existing run", "Acme_26-03-06", os.path.join(folder, "Acme_26-03-06")),
                 ("not a run's name", "Acme",
                  "'Acme' is not a deck folder, <Name>_<YY-MM-DD>"),
                 ("leading outside", "../Acme_26-03-06",
                  "leads outside|without \\.\\."),
                 ("missing", "Acme_26-03-07",
                  f"Acme_26-03-07 doesn't exist in {folder}: run init_deck.py first")]
        for name, run, expected in cases:
            with self.subTest(name):
                def call(): return output_folder.run_folder(
                    "slides-decks", run, "deck", "Name", "init_deck.py")
                if os.path.isabs(expected):
                    self.assertEqual(call(), expected)
                else:
                    with self.assertRaisesRegex(SystemExit, expected):
                        call()

    def test_run_document(self):
        # The document is named after the run folder's subject; a name of
        # another form exits as run_folder() does, naming the folder's form.
        self.assertEqual(output_folder.run_document("Acme-Q3_26-10-05", "Slides.html", "deck", "Name"),
                         "Acme-Q3_Slides.html")
        for run in ("Acme-Q3", "Acme_26-10", "_26-10-05x"):
            with self.subTest(run), self.assertRaisesRegex(
                    SystemExit, f"'{run}' is not a deck folder, <Name>_<YY-MM-DD>"):
                output_folder.run_document(run, "Slides.html", "deck", "Name")


class DayFolderTest(unittest.TestCase):
    def test_day_folder(self):
        # A datetime's own day is used, as its time zone gives it.
        cases = [("a date", date(2026, 3, 6), "PROJ-Sprint-3_26-03-06"),
                 ("a datetime", datetime(2026, 12, 31, 23, 59),
                  "PROJ-Sprint-3_26-12-31"),
                 ("a datetime in a time zone",
                  datetime(2026, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))), "PROJ-Sprint-3_26-01-01")]
        for name, day, expected in cases:
            with self.subTest(name):
                self.assertEqual(output_folder.day_folder(
                    "PROJ-Sprint-3", day), expected)
                # folder_day() and DAY_FOLDER read the name back.
                self.assertEqual(output_folder.folder_day(expected), datetime.strptime(
                    expected[-8:], "%y-%m-%d").date())
                match = output_folder.DAY_FOLDER.fullmatch(expected)
                assert match
                self.assertEqual((match["subject"], match["date"]),
                                 ("PROJ-Sprint-3", expected[-8:]))
                self.assertEqual(output_folder.folder_subject(
                    expected), "PROJ-Sprint-3")
        self.assertIsNone(output_folder.folder_day("_examples"))
        self.assertIsNone(output_folder.folder_subject("_examples"))

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


class FolderProblemTest(unittest.TestCase):
    def test_folder_problem(self):
        # name: (the files in the folder, the problem expected, or None)
        wanted = {"data.json", "Report.md"}
        cases = [("as wanted", ["data.json", "Report.md", ".DS_Store"], None),
                 ("extra and missing", ["data.json", "notes.txt"],
                  "the folder must hold only Report.md, data.json; move notes.txt to your own scratch folder; "
                  "missing Report.md")]
        for name, files, expected in cases:
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                for file in files:
                    open(os.path.join(folder, file), "w").close()
                self.assertEqual(output_folder.folder_problem(
                    folder, wanted), expected)


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
                path = os.path.join(folder, output_folder.DESCRIPTION)
                if text is not None:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                self.assertEqual(
                    output_folder.read_description(path), expected)

    def test_a_written_description_reads_back(self):
        text = output_folder.description("A slide", {"Use for": "a cover", "Why it's good": "clear"},
                                         "The slide: [slides.json](slides.json).")
        self.assertEqual(text, "# A slide\n\n**Use for:** a cover\n\n**Why it's good:** clear\n\n"
                               "The slide: [slides.json](slides.json).\n")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, output_folder.DESCRIPTION)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.assertEqual(output_folder.read_description(path),
                             ("A slide", {"Use for": "a cover", "Why it's good": "clear"}))


class TempRootTest(unittest.TestCase):
    def test_temp_root_is_in_the_system_temp_folder(self):
        self.assertTrue(output_folder.TEMP_ROOT.startswith(
            tempfile.gettempdir()))


if __name__ == "__main__":
    unittest.main()
