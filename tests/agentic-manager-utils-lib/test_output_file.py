"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/output_file.py.
Run as a script, it has end-to-end tests in test_e2e_output.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

output_folder() is patched to return a folder inside a temporary folder, so no
config is read.
"""

import contextlib
import io
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
        # Each write replaces the file, creating missing folders on the way.
        cases = [("a file", "notes.md", "# Notes\n"),
                 ("the same file again", "notes.md", "second"),
                 ("missing folders on the way",
                  "Topic_26-03-29/ledger.md", "| a |\n"),
                 ("text that isn't ASCII", "_examples/README.md", "🟩 Existing, déjà vu\n")]
        for name, relative, content in cases:
            with self.subTest(name):
                path, temporary = output_file.write_output_file(
                    "reports", relative, content.encode("utf-8"))
                self.assertEqual(
                    (path, temporary), (os.path.join(self.folder, relative), True))
                self.assertEqual(self.read(path), content)
        self.output_folder.assert_called_with("reports")

    def test_refusals(self):
        # Nothing is written outside the folder, through a link out of it, or
        # from content that isn't UTF-8 text.
        os.symlink(self.root, os.path.join(self.folder, "out"))
        cases = [("", b"x", "must be a relative path"),
                 (os.path.join(self.root, "x.md"),
                  b"x", "must be a relative path"),
                 ("../x.md", b"x", "without .."), ("a/../../x.md", b"x", "without .."),
                 ("a\\..\\x.md", b"x", "without .."), (".", b"x", "must name a file"),
                 ("out/x.md", b"x", "leads outside"), ("x.md", b"\xff\xfe", "not UTF-8")]
        for relative, content, expected in cases:
            with self.subTest(relative=relative, content=content):
                with self.assertRaisesRegex(SystemExit, expected):
                    output_file.write_output_file("reports", relative, content)
        self.assertEqual(sorted(os.listdir(self.root)), ["reports"])
        self.assertEqual(os.listdir(self.folder), ["out"])

    def test_patch_updates_only_selected_text(self):
        path, _ = output_file.write_output_file(
            "reports", "doc.md", "unchanged\r\nold 🟩\r\nend".encode())
        result = output_file.patch_output_file("reports", "doc.md", json.dumps([
            {"old": "old 🟩", "new": "new 🟦"},
            {"old": "new 🟦", "new": "final"},
        ]).encode())
        self.assertEqual(result, (path, True))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"unchanged\r\nfinal\r\nend")

    def test_patch_refusals(self):
        # A bad patch, or a target that isn't an existing UTF-8 file inside
        # the folder, changes nothing: neither part of the patch applies.
        outside = os.path.join(self.root, "outside.md")
        with open(outside, "wb") as f:
            f.write(b"unique")
        os.symlink(outside, os.path.join(self.folder, "link.md"))
        with open(os.path.join(self.folder, "binary"), "wb") as f:
            f.write(b"\xff")
        valid = b'[{"old":"unique","new":"x"}]'
        bad_patches = [b"not json", b"\xff", b"{}", b"[]",
                       b'[{"old":"","new":"x"}]',
                       b'[{"old":"same","new":"x"}]',
                       b'[{"old":"unique","new":"aaa"},{"old":"aa","new":"x"}]',
                       b'[{"old":"missing","new":"x"}]',
                       b'[{"old":"unique","new":1}]',
                       b'[{"old":"unique","new":"x","extra":true}]',
                       json.dumps([{"old": "unique", "new": "changed"},
                                   {"old": "missing", "new": "x"}]).encode(),
                       json.dumps([{"old": "unique", "new": chr(0xd800)}]).encode()]
        bad_targets = ["../outside.md", outside,
                       "link.md", "missing.md", "binary", "."]
        cases = [("doc.md", patch) for patch in bad_patches] + \
            [(target, valid) for target in bad_targets]
        for relative, content in cases:
            with self.subTest(relative=relative, content=content):
                path, _ = output_file.write_output_file(
                    "reports", "doc.md", b"unique same same")
                with self.assertRaises(SystemExit):
                    output_file.patch_output_file("reports", relative, content)
                self.assertEqual(self.read(path), "unique same same")
        self.assertEqual(self.read(outside), "unique")
        self.assertFalse(os.path.exists(
            os.path.join(self.folder, "missing.md")))
        # A patch of the wrong shape shows a command to copy.
        for content in (b"not json", b"{}", b'[{"old":"unique"}]'):
            with self.subTest(shape=content), self.assertRaises(SystemExit) as raised:
                output_file.patch_output_file("reports", "doc.md", content)
            self.assertIn("--patch <<'EOF'", str(raised.exception))

    def test_set_changes_one_field(self):
        # A field is named by its path, list positions included; what isn't
        # named stays, and a refused --set writes nothing.
        relative = "Topic_26-03-29/content.json"
        output_file.write_output_file("reports", relative, json.dumps(
            {"title": "Old", "architecture": {"current": {"summary": ["One.", "Two."]}}}).encode())
        output_file.set_output_fields("reports", relative, [
            "architecture.current.summary.1=Two, \"quoted\".", "title=New", "skip=none"])
        with open(os.path.join(self.folder, relative), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"title": "New", "skip": "none",
                                            "architecture": {"current": {"summary": ["One.", 'Two, "quoted".']}}})
        before = self.read(os.path.join(self.folder, relative))
        cases = [("no equals sign", "title", "write --set as field=text"),
                 ("a list position not there",
                  "architecture.current.summary.5=x", "no such field"),
                 ("a key not there", "architecture.next.summary=x", "no such field"),
                 ("a text holds no fields", "title.part=x", "no such field")]
        for name, assignment, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                output_file.set_output_fields(
                    "reports", relative, ["title=Changed", assignment])
            self.assertEqual(
                self.read(os.path.join(self.folder, relative)), before)

    def test_read_json(self):
        # Any JSON value; a missing or unreadable file exits naming it, never a traceback.
        path = os.path.join(self.folder, "data.json")
        with self.assertRaisesRegex(SystemExit, "data.json is missing"):
            output_file.read_json(path)
        for text, expected in (('{"a": 1}', {"a": 1}), ("[1, 2]", [1, 2]), ("{", None)):
            with self.subTest(text=text):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                if expected is None:
                    with self.assertRaisesRegex(SystemExit, "data.json is not readable JSON"):
                        output_file.read_json(path)
                else:
                    self.assertEqual(output_file.read_json(path), expected)

    def test_command_line(self):
        for extra, patch, sets in (([], False, []), (["--patch"], True, []),
                                   (["--set", "a=1", "--set", "b=2"], False, ["a=1", "b=2"])):
            with self.subTest(extra=extra):
                args = output_file.parse_args(
                    ["--name", "reports", "--path", "a/b.md", *extra])
                self.assertEqual((args.name, args.path, args.patch, args.set),
                                 ("reports", "a/b.md", patch, sets))
        # --help shows a command to copy for writing a file and for patching one.
        out = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(out):
            output_file.parse_args(["--help"])
        self.assertEqual(out.getvalue().count("<<'EOF'"), 2)
        for argv in (["--name", "../x", "--path", "a.md"], ["--name", "reports"], ["--path", "a.md"],
                     ["--name", "reports", "--path", "a.md", "--patch", "--set", "a=1"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                output_file.parse_args(argv)


if __name__ == "__main__":
    unittest.main()
