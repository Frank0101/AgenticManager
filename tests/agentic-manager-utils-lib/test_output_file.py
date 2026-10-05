# Unit tests for skills/agentic-manager-utils-lib/agentic_manager/output_file.py.
# Run as a script, it has end-to-end tests in test_e2e_output.py.
# Run with: python3 tests/run.py agentic-manager-utils-lib
#
# output_folder() is patched to return a folder inside a temporary folder, so no
# config is read.
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
from agentic_manager import output_file  # noqa: E402


class OutputFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        self.folder = os.path.join(self.root, "reports")
        os.makedirs(self.folder)
        patcher = mock.patch.object(output_file, "output_folder",
                                    return_value=(self.folder, True))
        self.output_folder = patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_writes_inside_the_folder(self):
        cases = [("a file", "notes.md", "# Notes\n"),
                 ("missing folders on the way",
                  "2026-03-29--topic/ledgers.md", "| a |\n"),
                 ("text that isn't ASCII", "_examples/README.md", "🟩 Existing, déjà vu\n")]
        for name, relative, content in cases:
            with self.subTest(name):
                path, temporary = output_file.write_output_file(
                    "reports", relative, content.encode("utf-8"))
                self.assertEqual(
                    (path, temporary), (os.path.join(self.folder, relative), True))
                self.assertEqual(self.read(path), content)
        self.output_folder.assert_called_with("reports")

    def test_replaces_an_existing_file(self):
        for content in (b"first draft", b"second"):
            path, _ = output_file.write_output_file(
                "reports", "doc.md", content)
        self.assertEqual(self.read(path), "second")

    def test_refuses_paths_outside_the_folder(self):
        os.symlink(self.root, os.path.join(self.folder, "out"))
        cases = [("", "must be a relative path"),
                 (os.path.join(self.root, "x.md"), "must be a relative path"),
                 ("../x.md", "without .."), ("a/../../x.md", "without .."),
                 ("a\\..\\x.md", "without .."), (".", "leads outside"),
                 ("out/x.md", "leads outside")]
        for relative, expected in cases:
            with self.subTest(relative=relative):
                with self.assertRaisesRegex(SystemExit, expected):
                    output_file.write_output_file("reports", relative, b"x")
        self.assertEqual(sorted(os.listdir(self.root)), ["reports"])

    def test_refuses_content_that_is_not_utf8(self):
        with self.assertRaisesRegex(SystemExit, "not UTF-8"):
            output_file.write_output_file("reports", "x.md", b"\xff\xfe")
        self.assertEqual(os.listdir(self.folder), [])

    def test_command_line(self):
        args = output_file.parse_args(
            ["--name", "reports", "--path", "a/b.md"])
        self.assertEqual((args.name, args.path), ("reports", "a/b.md"))
        for argv in (["--name", "../x", "--path", "a.md"], ["--name", "reports"], ["--path", "a.md"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                output_file.parse_args(argv)


if __name__ == "__main__":
    unittest.main()
