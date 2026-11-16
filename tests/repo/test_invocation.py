"""Checks that every skill runs only when the user calls it by its name.

A skill starts long work, with subagents, fetches and an output folder, so an
agent starting one on its own, because a conversation touched on what it
does, would spend time and tokens the user never asked for.
Run with: python3 tests/run.py repo
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
# The SKILL.md's frontmatter, and the line that keeps an agent from starting
# the skill on its own.
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
BY_NAME_ONLY = "disable-model-invocation: true"


class InvocationTest(unittest.TestCase):
    def test_every_skill_runs_by_its_name_only(self):
        skills = os.path.join(REPO_ROOT, "skills")
        for name in sorted(os.listdir(skills)):
            path = os.path.join(skills, name, "SKILL.md")
            if not os.path.isfile(path):
                continue
            with self.subTest(name), open(path, encoding="utf-8") as f:
                frontmatter = FRONTMATTER.match(f.read())
                self.assertTrue(frontmatter and BY_NAME_ONLY in frontmatter[1].split("\n"),
                                f"{name}/SKILL.md: add `{BY_NAME_ONLY}` to its frontmatter, so the skill runs only "
                                "when the user calls it by its name")


if __name__ == "__main__":
    unittest.main()
