"""Checks that every script answers --help, saying what it does and, when it
parses its arguments with argparse, what each command and argument is for:
a skill's instructions send the agent to a script's --help for what they
don't spell out, so a command or argument it doesn't describe can't be found.
Run with: python3 tests/run.py repo
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import code_map  # noqa: E402

# An argparse entry: a line indented by two spaces, such as "  --deck DECK".
ENTRY = re.compile(r"^  (\S.*?)(?: {2,}\S.*)?$")
# The line that lists a script's commands, such as "  {row,show}".
CHOICES = re.compile(r"^  \{(.+)\}", re.M)


def scripts():
    """Every module run as a script, by its path."""
    for folder in code_map.folders().values():
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if name.endswith(".py"):
                with open(path, encoding="utf-8") as f:
                    if 'if __name__ == "__main__":' in f.read():
                        yield path


def undescribed(text):
    """The commands and arguments an argparse help leaves without a description."""
    lines, missing, inside = text.splitlines(), [], False
    for i, line in enumerate(lines):
        # Only the argument sections, never the description above them.
        if not line.startswith(" "):
            inside = line in ("options:", "positional arguments:")
            continue
        if not inside:
            continue
        if choices := CHOICES.match(line):
            listed = {m[1] for m in (
                re.match(r"^ {4}(\S+) {2,}\S", l) for l in lines) if m}
            missing += [c for c in choices[1].split(",") if c not in listed]
        elif (entry := ENTRY.match(line)) and not line.rstrip().endswith(":"):
            follows = lines[i + 1] if i + 1 < len(lines) else ""
            described = entry.group(
                0) != f"  {entry[1]}" or follows.startswith("    ")
            if not described:
                missing.append(entry[1])
    return missing


class HelpTest(unittest.TestCase):
    def test_every_script_says_what_it_does_and_what_each_argument_is_for(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, TMPDIR=home)
            for path in scripts():
                where = os.path.relpath(path, REPO_ROOT)
                with self.subTest(where):
                    run = subprocess.run([sys.executable, path, "--help"], env=env,
                                         capture_output=True, text=True, timeout=60)
                    self.assertEqual(run.returncode, 0,
                                     run.stdout + run.stderr)
                    self.assertTrue(run.stdout.strip(),
                                    f"{where}: --help prints nothing")
                    if run.stdout.startswith("usage:"):
                        self.assertEqual(undescribed(run.stdout), [],
                                         f"{where}: describe these in --help")
                    # Each command lists its own arguments.
                    for choices in CHOICES.findall(run.stdout):
                        for command in choices.split(","):
                            sub = subprocess.run([sys.executable, path, command, "--help"], env=env,
                                                 capture_output=True, text=True, timeout=60)
                            self.assertEqual(
                                sub.returncode, 0, f"{where} {command}: " + sub.stderr)
                            self.assertEqual(undescribed(sub.stdout), [],
                                             f"{where} {command}: describe these in --help")

    def test_undescribed(self):
        cases = [
            ("the description is not an argument",
             "usage: x\n\nWrites a file:\n  python3 x.py --deck D\n\noptions:\n  --deck DECK  the deck\n", []),
            ("described", "usage: x\n\noptions:\n  -h, --help  show this\n  --deck DECK  the deck\n", []),
            ("described on the next line",
             "options:\n  --report-dir REPORT_DIR\n                        the folder\n", []),
            ("not described", "options:\n  --deck DECK\n  --open  open it\n",
             ["--deck DECK"]),
            ("commands", "positional arguments:\n  {row,show}\n    row   writes a row\n", [
             "show"]),
        ]
        for name, text, expected in cases:
            with self.subTest(name):
                self.assertEqual(undescribed(text), expected)


if __name__ == "__main__":
    unittest.main()
