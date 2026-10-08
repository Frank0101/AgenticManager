# Unit tests for skills/agentic-manager-utils-refactoring/scripts/precheck.py.
# Run with: python3 tests/run.py agentic-manager-utils-refactoring
#
# Each check runs on small made-up files; test_e2e_precheck.py runs the whole
# script on a made-up repository.
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import precheck  # noqa: E402


def trees(texts):
    return {path: precheck.parse(text) for path, text in texts.items() if path.endswith(".py")}


def found(leads):
    """The leads as (file, line, message)."""
    return [(lead["file"], lead["line"], lead["message"]) for lead in leads]


class TestsCheckTest(unittest.TestCase):
    def test_similar(self):
        cases = [("test_parse", "test_parse_errors", True), ("test_valid", "test_invalid", True),
                 ("test_find_sprint", "test_find_sprint_failures", True),
                 ("test_output_valid", "test_output_invalid", True),
                 ("test_parse", "test_format", False), ("test_header_table", "test_epic_table", False)]
        for a, b, expected in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(precheck.similar(a, b), expected)

    def test_check_tests(self):
        # Pairs are only looked for within a class, or among a module's own
        # functions, and every test is listed with its class.
        text = ("class ATest:\n    def test_parse(self): pass\n    def test_parse_errors(self): pass\n"
                "    def helper(self): pass\n"
                "class BTest:\n    def test_parse_dates(self): pass\n"
                "def test_valid(): pass\ndef test_invalid(): pass\n")
        leads, listing = precheck.check_tests(
            trees({"tests/test_x.py": text, "lib.py": "def test_y(): pass\n"}))
        self.assertEqual(found(leads), [
            ("tests/test_x.py", 3,
             "test_parse_errors may check the same thing as test_parse (line 2)"),
            ("tests/test_x.py", 8, "test_invalid may check the same thing as test_valid (line 7)")])
        self.assertEqual(listing, {"tests/test_x.py": [[2, "ATest.test_parse"], [3, "ATest.test_parse_errors"],
                                                       [6, "BTest.test_parse_dates"], [
                                                           7, "test_valid"],
                                                       [8, "test_invalid"]]})


class ReferencesCheckTest(unittest.TestCase):
    def test_prose(self):
        # References are read in every line of a document, but only in a
        # Python file's comments and docstrings: its strings are data.
        code = ('"""Module, see test_a."""\nNAME = "test_b"  # see test_c\n\n\n'
                'def f():\n    """Two lines,\n    see test_d."""\n    return "test_e"\n')
        cases = [("a.md", "one\ntwo\n", [(1, "one"), (2, "two")]),
                 ("a.py", code, [(1, '"""Module, see test_a."""'), (2, "# see test_c"),
                                 (6, '    """Two lines,'), (7, '    see test_d."""')])]
        for path, text, expected in cases:
            with self.subTest(path):
                self.assertEqual(precheck.prose(path, text), expected)

    def test_check_test_names(self):
        # Known: tests, modules and any other Python name; a file name or a
        # pattern is no test name.
        texts = {"tests/test_a.py": "def test_one(): pass\ntest_value = 1\n",
                 "README.md": ("test_one, test_a, test_value, test_a.py, test_<module>, test_*.py.\n"
                               "test_gone was merged.\n")}
        self.assertEqual(found(precheck.check_test_names(texts, trees(texts))),
                         [("README.md", 2, "test_gone is defined nowhere")])

    def test_check_files(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "docs"))
            for path in ("docs/a.md", "b.md"):
                open(os.path.join(root, path), "w").close()
            texts = {"docs/a.md": ("[ok](../b.md#part) [web](https://acme.test) [here](#top) "
                                   "[var](${CLAUDE_SKILL_DIR}/x.md) [gone](missing.md)\n"
                                   "Run `run.py` and `old.py`, not `<script>.py`.\n"),
                     "run.py": "# See [gone](missing.md), `old.py`.\n"}
            self.assertEqual(found(precheck.check_files(root, texts)), [
                ("docs/a.md", 1, "the link to missing.md leads nowhere"),
                ("docs/a.md", 2, "old.py is no file in the repo"),
                ("run.py", 1, "old.py is no file in the repo")])

    def test_check_flags(self):
        # A flag counts once the script's source mentions it, in either
        # quotes; only flags on the script's own command are checked.
        texts = {"scripts/run.py": 'parser.add_argument("--name")\nif "--png" in argv: pass\n',
                 "check.py": "flags = ['--strict']\n",
                 "SKILL.md": ("`python3 run.py --name x [--png] --check`\n"
                              "`run.py --name` then `check.py --strict --fast`\n"
                              "`other.py --anything`\n")}
        self.assertEqual(found(precheck.check_flags(texts)), [
            ("SKILL.md", 1, "run.py has no --check"), ("SKILL.md", 2, "check.py has no --fast")])


class CodeCheckTest(unittest.TestCase):
    def test_check_imports(self):
        texts = {"a.py": "import os\nimport sys\nimport json  # noqa: F401\nfrom x import (y,\n    z)\nprint(sys, y)\n",
                 "pkg/__init__.py": "from .a import b\n"}
        self.assertEqual(found(precheck.check_imports(texts, trees(texts))), [
            ("a.py", 1, "os is imported but never used"), ("a.py", 4, "z is imported but never used")])

    def test_check_definitions(self):
        # Only the code, not its tests; main and dunder names are entry
        # points; a name used anywhere in Python counts.
        texts = {"lib.py": ("LIMIT = 3\nUNUSED = 4\n__all__ = []\ndef used(): pass\ndef dead(): pass\n"
                            "class Dead: pass\ndef main(): used()\n"),
                 "other.py": "from lib import LIMIT\n",
                 "tests/test_lib.py": "def helper(): pass\n"}
        self.assertEqual(found(precheck.check_definitions(texts, trees(texts))), [
            ("lib.py", 2, "nothing refers to UNUSED"), ("lib.py",
                                                        5, "nothing refers to dead"),
            ("lib.py", 6, "nothing refers to Dead")])

    def test_check_comments(self):
        long_comment = "    # " + "x" * (precheck.COMMENT_WIDTH - 5)
        texts = {"a.py": "#!/usr/bin/env python3 " + "x" * 90 + "\n# short\n" + long_comment + "\n" + "y = '" + "x" * 99 + "'\n",
                 "a.md": "# " + "x" * 99 + "\n"}
        self.assertEqual(found(precheck.check_comments(texts)), [
            ("a.py", 3, f"a {precheck.COMMENT_WIDTH + 1}-character comment line, over {precheck.COMMENT_WIDTH}")])


class TypesCheckTest(unittest.TestCase):
    def test_check_types(self):
        # pyright's errors and warnings, not its information; why it didn't
        # run otherwise; nothing to check without Python.
        root = "/repo"
        output = json.dumps({"generalDiagnostics": [
            {"file": "/repo/a.py", "severity": "error", "message": "\"x\" is possibly unbound\n  more",
             "range": {"start": {"line": 4}}, "rule": "reportPossiblyUnbound"},
            {"file": "/repo/b.py", "severity": "warning",
                "message": "unused", "range": {"start": {"line": 0}}},
            {"file": "/repo/c.py", "severity": "information", "message": "fyi", "range": {"start": {"line": 0}}}]})
        cases = [
            ("diagnostics", "/bin/npx", subprocess.CompletedProcess([], 1, output, ""), {"a.py": ""},
             [("a.py", 5, "error: \"x\" is possibly unbound (reportPossiblyUnbound)"),
              ("b.py", 1, "warning: unused")],
             []),
            ("no npx", None, None, {"a.py": ""}, [], [
             "type: npx (Node.js) is not available, so pyright didn't run"]),
            ("no output", "/bin/npx", subprocess.CompletedProcess([], 1, "", "npm error network\nmore"), {"a.py": ""},
             [], ["type: pyright didn't run: npm error network"]),
            ("a timeout", "/bin/npx", subprocess.TimeoutExpired("npx", 600), {"a.py": ""},
             [], ["type: pyright took more than 10 minutes"]),
            ("no Python", "/bin/npx", None, {"a.md": ""}, [], []),
        ]
        for name, npx, result, texts, leads, skipped in cases:
            with self.subTest(name), mock.patch.object(precheck.shutil, "which", return_value=npx), \
                    mock.patch.object(precheck.subprocess, "run",
                                      side_effect=result if isinstance(
                                          result, Exception) else None,
                                      return_value=result) as run:
                found_leads, found_skipped = precheck.check_types(root, texts)
                self.assertEqual(
                    (found(found_leads), found_skipped), (leads, skipped))
                if result is not None:
                    self.assertEqual(run.call_args.args[0],
                                     [npx, "-y", f"pyright@{precheck.PYRIGHT}", "--outputjson"])
                    self.assertEqual(run.call_args.kwargs["cwd"], root)


class FilesTest(unittest.TestCase):
    def test_repo_files(self):
        # Tracked text files and new ones git doesn't ignore: not ignored,
        # deleted or binary files, nor symbolic links.
        with tempfile.TemporaryDirectory() as root:
            def write(path, content="x\n"):
                os.makedirs(os.path.dirname(
                    os.path.join(root, path)), exist_ok=True)
                with open(os.path.join(root, path), "w", encoding="utf-8") as f:
                    f.write(content)
            subprocess.run(["git", "init", "-q", root], check=True)
            for path in ("a.py", "docs/b.md", "gone.md", "image.png"):
                write(path)
            write(".gitignore", "ignored.md\n")
            subprocess.run(["git", "-C", root, "add", "."], check=True)
            os.remove(os.path.join(root, "gone.md"))
            write("new.json", "{}\n")
            write("ignored.md")
            os.symlink("a.py", os.path.join(root, "link.py"))
            self.assertEqual(precheck.repo_files(root), [
                             "a.py", "docs/b.md", "new.json"])


if __name__ == "__main__":
    unittest.main()
