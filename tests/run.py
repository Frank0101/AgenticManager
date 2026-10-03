#!/usr/bin/env python3
#
# Runs every skill's tests. Run from anywhere: python3 tests/run.py
#
# tests/<skill>/ mirrors skills/<skill>/. Skill names contain hyphens, so these folders
# can't be Python packages and `unittest discover` skips them. Instead, each
# tests/<skill>/test_*.py is loaded by file path, under a module name that includes
# the skill, so two skills can have test files with the same name.
import glob
import importlib.util
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, "*", "test_*.py"))):
        skill = os.path.basename(os.path.dirname(path))
        name = f"{skill}.{os.path.splitext(os.path.basename(path))[0]}".replace(
            "-", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


def main():
    suite = load_suite()
    if suite.countTestCases() == 0:
        print(f"no tests found under {TESTS_DIR}/<skill>/test_*.py")
        sys.exit(1)
    result = unittest.TextTestRunner(
        verbosity=2 if "-v" in sys.argv[1:] else 1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
