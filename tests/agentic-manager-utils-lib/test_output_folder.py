# Unit tests for skills/agentic-manager-utils-lib/agentic_manager/output_folder.py.
# Run as a script, it has end-to-end tests in test_e2e_output.py.
# Run with: python3 tests/run.py agentic-manager-utils-lib
#
# The config's CONFIG_PATH is patched to a file in a temporary folder, which each
# test writes, and TEMP_ROOT to a folder inside it.
import json
import os
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

    # --- output_root

    def test_output_root(self):
        self.write({"output": {"root": " ~/reports "}})
        self.assertEqual(output_folder.output_root(),
                         os.path.join(os.path.expanduser("~"), "reports"))

    def test_output_root_not_set(self):
        for data in ({}, {"output": {}}, {"output": {"root": "<path>"}}, {"output": {"root": " "}},
                     {"output": {"root": " <path> "}},
                     {"output": {"root": 5}}, {"output": []}):
            with self.subTest(data=data):
                self.write(data)
                self.assertIsNone(output_folder.output_root())

    def test_unreadable_config(self):
        for call in (output_folder.output_root, lambda: output_folder.output_folder("reports")):
            with self.assertRaisesRegex(SystemExit, "could not read"):
                call()

    # --- output_folder

    def test_output_folder(self):
        reports = os.path.join(self.tmp.name, "reports")
        cases = [
            ("in the output root", {"output": {"root": reports}},
             (os.path.join(reports, "jira-sprint-reports"), False)),
            ("in the temp folder without an output root", {},
             (os.path.join(self.temp_root, "jira-sprint-reports"), True)),
        ]
        for name, data, expected in cases:
            with self.subTest(name):
                self.write(data)
                self.assertEqual(output_folder.output_folder(
                    "jira-sprint-reports"), expected)
                self.assertTrue(os.path.isdir(expected[0]))

    def test_imported_api_rejects_paths_as_names(self):
        self.write({})
        for name in ("", "..", "../outside", os.path.join(self.tmp.name, "outside")):
            with self.subTest(name=name), self.assertRaisesRegex(SystemExit, "single folder name"):
                output_folder.output_folder(name)
        self.assertFalse(os.path.exists(self.temp_root))

    def test_output_folder_keeps_its_files(self):
        self.write({})
        folder, _ = output_folder.output_folder("reports")
        with open(os.path.join(folder, "kept.md"), "w", encoding="utf-8") as f:
            f.write("x")
        self.assertEqual(output_folder.output_folder("reports")[0], folder)
        self.assertEqual(os.listdir(folder), ["kept.md"])

    def test_output_folder_is_absolute(self):
        self.write({"output": {"root": "reports"}})
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            folder, _ = output_folder.output_folder("x")
        finally:
            os.chdir(cwd)
        self.assertEqual(folder, os.path.join(
            os.path.realpath(self.tmp.name), "reports", "x"))

    # --- the command line

    def test_name_must_be_one_folder(self):
        cases = [("tech-investigations", "tech-investigations"), (" reports ", "reports"),
                 ("", None), ("  ", None), (".", None), ("..", None),
                 (os.path.join("a", "b"), None)]
        for value, expected in cases:
            with self.subTest(value=value):
                if expected:
                    self.assertEqual(output_folder.parse_args(
                        ["--name", value]).name, expected)
                else:
                    with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                        output_folder.parse_args(["--name", value])


class TempRootTest(unittest.TestCase):
    def test_temp_root_is_in_the_system_temp_folder(self):
        self.assertTrue(output_folder.TEMP_ROOT.startswith(
            tempfile.gettempdir()))


if __name__ == "__main__":
    unittest.main()
