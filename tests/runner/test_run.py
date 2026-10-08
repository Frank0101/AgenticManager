# Unit tests for tests/run.py, the test runner, using isolated fixture suites.
# They have a folder of their own: run.py discovers any tests/<name>/ folder.
# Run with: python3 tests/run.py runner
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RUNNER = Path(__file__).resolve().parents[1] / "run.py"
SPEC = importlib.util.spec_from_file_location("repo_test_runner", RUNNER)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patcher = mock.patch.object(runner, "TESTS_DIR", str(self.root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fixture(self, skill, passes=True):
        folder = self.root / skill
        folder.mkdir(exist_ok=True)
        (folder / "test_sample.py").write_text(
            "import unittest\nclass Sample(unittest.TestCase):\n"
            f"    def test_result(self):\n        self.assertTrue({passes!r})\n",
            encoding="utf-8")

    def test_discovery_and_loading(self):
        for skill in ("zeta", "alpha"):
            self.fixture(skill)
        (self.root / "empty").mkdir()
        (self.root / "empty" / "fixture.py").write_text("", encoding="utf-8")
        (self.root / "test_top.py").write_text("", encoding="utf-8")
        self.assertEqual(runner.skills(), ["alpha", "zeta"])
        self.assertEqual(runner.load_suite("alpha").countTestCases(), 1)
        self.assertEqual(runner.load_suite("empty").countTestCases(), 0)

    def test_suite_outcomes(self):
        self.fixture("pass")
        self.fixture("fail", False)
        for skill, expected in (("pass", True), ("fail", False), ("empty", False)):
            with self.subTest(skill), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.run_skill(
                    skill, verbose=False), expected)

    def test_main_dispatch(self):
        cases = [
            ([], ["alpha", "zeta"], [0, 0], 0, [
             "alpha", "zeta"], "all skills passed"),
            (["zeta", "-v"], ["alpha", "zeta"], [1], 1, ["zeta"], "FAILED: zeta"),
            (["missing"], ["alpha"], [], 1, [], "no tests for missing"),
            ([], [], [], 1, [], "no tests found"),
        ]
        for args, available, codes, expected, selected, message in cases:
            with self.subTest(args=args, available=available):
                output = io.StringIO()
                results = [subprocess.CompletedProcess(
                    [], code) for code in codes]
                with mock.patch.object(sys, "argv", [str(RUNNER), *args]), \
                        mock.patch.object(runner, "skills", return_value=available), \
                        mock.patch.object(runner.subprocess, "run", side_effect=results) as run, \
                        contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                    runner.main()
                self.assertEqual(raised.exception.code, expected)
                self.assertIn(message, output.getvalue())
                self.assertEqual(run.call_args_list, [mock.call(
                    [sys.executable, os.path.abspath(
                        RUNNER), "--in-process", skill]
                    + (["-v"] if "-v" in args else [])) for skill in selected])

    def test_in_process_dispatch(self):
        for success in (True, False):
            with self.subTest(success=success):
                with mock.patch.object(sys, "argv", [str(RUNNER), "--in-process", "alpha", "-v"]), \
                        mock.patch.object(runner, "run_skill", return_value=success) as run, \
                        self.assertRaises(SystemExit) as raised:
                    runner.main()
                self.assertEqual(raised.exception.code, 0 if success else 1)
                run.assert_called_once_with("alpha", True)


if __name__ == "__main__":
    unittest.main()
