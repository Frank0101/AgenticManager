"""Checks that README.md's table of skills lists exactly the skills in skills/,
the utilities aside: the table is written by hand, for people, so this keeps it
from going stale when a skill is added, renamed or removed.
Run with: python3 tests/run.py repo
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
# The README section that lists the skills, and a row of its table: the
# skill's name, linked to its folder.
SECTION = "## Available skills"
ROW = re.compile(r"^\|\s*\[([^\]]+)\]\(skills/([^)]+)\)", re.M)
# Skills other skills use, which the user doesn't invoke: not listed.
UTILITY_PREFIX = "agentic-manager-utils-"


class ReadmeTest(unittest.TestCase):
    def test_the_table_lists_every_skill(self):
        with open(os.path.join(REPO_ROOT, "README.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn(SECTION, text)
        section = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
        rows = ROW.findall(section)
        for name, folder in rows:
            with self.subTest(name):
                self.assertEqual(name, folder,
                                 f"README.md: the row for {name} links skills/{folder}; link the skill's own folder")
        skills = sorted(name for name in os.listdir(os.path.join(REPO_ROOT, "skills"))
                        if os.path.isfile(os.path.join(REPO_ROOT, "skills", name, "SKILL.md"))
                        and not name.startswith(UTILITY_PREFIX))
        self.assertEqual(sorted(name for name, _ in rows), skills,
                         f"README.md's {SECTION} table must list exactly the skills in skills/, the utilities "
                         "aside: add a row for a new skill, or remove the row of one that is gone")


if __name__ == "__main__":
    unittest.main()
