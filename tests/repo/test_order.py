"""Checks that every module of the library and of each skill's scripts reads
top-down: each module-level function or class comes below the first one that
uses it, and `main` comes last. An agent reading from the top then meets what
a module does before the details it rests on. Uses from `main` don't count,
since it is last, and neither does a function that module-level code calls,
which Python needs defined first.
Run with: python3 tests/run.py repo
"""

import ast
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import code_map  # noqa: E402

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def bound(node):
    """The names a function or class binds itself: its arguments, its
    assignments and what it defines or imports inside."""
    names = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
            names.add(inner.id)
        elif isinstance(inner, ast.arg):
            names.add(inner.arg)
        elif isinstance(inner, DEFINITIONS) and inner is not node:
            names.add(inner.name)
        elif isinstance(inner, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in inner.names}
    return names


def used(node, defined):
    """The module's definitions `node` refers to, in the order it first does."""
    own = bound(node)
    found = [inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)
             and isinstance(inner.ctx, ast.Load) and inner.id in defined and inner.id not in own
             and inner.id != getattr(node, "name", None)]
    return list(dict.fromkeys(found))


def out_of_order(source):
    """The definitions of `source` that come above every function using them,
    as 'name (used by first)', and 'main' if it isn't last."""
    tree = ast.parse(source)
    definitions = [n for n in tree.body if isinstance(n, DEFINITIONS)]
    position = {d.name: i for i, d in enumerate(definitions)}
    pinned = {name for n in tree.body if not isinstance(n, DEFINITIONS)
              for name in used(n, position)}
    users = {}
    for d in definitions:
        if d.name != "main":
            for name in used(d, position):
                users.setdefault(name, []).append(position[d.name])
    wrong = [f"{name} (used by {definitions[min(at)].name})" for name, at in users.items()
             if name not in pinned and name != "main" and min(at) > position[name]]
    if "main" in position and position["main"] != len(definitions) - 1:
        wrong.append("main")
    return wrong


class OrderTest(unittest.TestCase):
    def test_every_module_reads_top_down(self):
        for skill, folder in code_map.folders().items():
            for name in sorted(os.listdir(folder)):
                if name.endswith(".py"):
                    with self.subTest(f"{skill}/{name}"), open(os.path.join(folder, name), encoding="utf-8") as f:
                        self.assertEqual(out_of_order(f.read()), [],
                                         f"{skill}/{name}: move each below the first function that uses it")

    def test_out_of_order(self):
        cases = [
            ("top-down", "def run():\n    helper()\n\ndef helper():\n    pass\n\ndef main():\n    run()\n", []),
            ("a helper above its user", "def helper():\n    pass\n\ndef run():\n    helper()\n",
             ["helper (used by run)"]),
            ("main not last",
             "def main():\n    run()\n\ndef run():\n    pass\n", ["main"]),
            # A local name that shadows a function is no use of it.
            ("shadowed", "def text():\n    pass\n\ndef run(text):\n    return text\n", []),
            # Module-level code needs the function defined first.
            ("called at import", "def helper():\n    return 1\n\nVALUE = helper()\n\ndef run():\n    helper()\n", []),
        ]
        for name, source, expected in cases:
            with self.subTest(name):
                self.assertEqual(out_of_order(source), expected)


if __name__ == "__main__":
    unittest.main()
