#!/usr/bin/env python3
"""Runs every skill's tests. Run from anywhere:
  python3 tests/run.py                 every skill
  python3 tests/run.py <skill> ...     only those skills
  add -v to list each test

tests/<skill>/ mirrors skills/<skill>/. Skill names contain hyphens, so these folders
can't be Python packages and `unittest discover` skips them. Instead, each
tests/<skill>/test_*.py is loaded by file path.

Each skill's tests run in their own Python process. Unit tests import a skill's
modules by name (common, check_config...), and a process keeps one module per
name, so two skills with a module of the same name would otherwise see each
other's.
"""

import glob
import importlib.util
import os
import subprocess
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def skills():
    return sorted({os.path.basename(os.path.dirname(p))
                   for p in glob.glob(os.path.join(TESTS_DIR, "*", "test_*.py"))})


def load_suite(skill):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, skill, "test_*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"can't load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


# Runs one skill's tests in this process.
def run_skill(skill, verbose):
    suite = load_suite(skill)
    if suite.countTestCases() == 0:
        print(f"no tests found under {TESTS_DIR}/{skill}/test_*.py")
        return False
    result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
    return result.wasSuccessful()


def main():
    args = sys.argv[1:]
    verbose = "-v" in args
    wanted = [a for a in args if a != "-v" and a != "--in-process"]
    if "--in-process" in args:
        sys.exit(0 if run_skill(wanted[0], verbose) else 1)

    available = skills()
    unknown = [s for s in wanted if s not in available]
    if unknown:
        print(
            f"no tests for {', '.join(unknown)} (have: {', '.join(available)})")
        sys.exit(1)
    if not available:
        print(f"no tests found under {TESTS_DIR}/<skill>/test_*.py")
        sys.exit(1)

    failed = []
    for skill in wanted or available:
        print(f"=== {skill}", flush=True)
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--in-process", skill]
                              + (["-v"] if verbose else []))
        if proc.returncode != 0:
            failed.append(skill)
    print(f"\n{'FAILED: ' + ', '.join(failed) if failed else 'all skills passed'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
