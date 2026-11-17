"""Checks that every skill's prerequisite runs the config check as its
frontmatter pre-approves it, needing only what the template has.

A pre-approval matches a command exactly, so a prerequisite and a frontmatter
that differ make the check ask permission on every run; an argument the check
doesn't take fails every run.
Run with: python3 tests/run.py repo
"""

import os
import re
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(REPO_ROOT, "skills")
LIB = os.path.join(SKILLS, "agentic-manager-utils-lib")
sys.path.insert(0, LIB)
from agentic_manager.check_config import TEMPLATE_PATH, argument_errors  # noqa: E402
from agentic_manager.config import load_json  # noqa: E402

# The check's command, in a prerequisite's backticks or a frontmatter's Bash().
CHECK = r"python3 \$\{CLAUDE_SKILL_DIR\}/\.\./agentic-manager-utils-lib/agentic_manager/check_config\.py[^`)]*"


class PrerequisiteTest(unittest.TestCase):
    def test_every_skill_runs_the_check_it_pre_approves(self):
        template = load_json(TEMPLATE_PATH)
        for name in sorted(os.listdir(SKILLS)):
            path = os.path.join(SKILLS, name, "SKILL.md")
            if name.startswith("agentic-manager-utils-") or not os.path.isfile(path):
                continue
            with self.subTest(name), open(path, encoding="utf-8") as f:
                text = f.read()
                approved = re.findall(rf"Bash\(({CHECK})\)", text)
                run = re.findall(
                    rf"## Prerequisite\n\nRun the config check, `({CHECK})`", text)
                self.assertTrue(run, f"{name}/SKILL.md: start its prerequisite with \"Run the config check, "
                                "`python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/"
                                "check_config.py --needs ...`\", as AGENTS.md shows")
                self.assertEqual(approved, run, f"{name}/SKILL.md: pre-approve in its frontmatter exactly the "
                                 "command its prerequisite runs, Bash(<command>), and only that one")
                self.assertEqual(argument_errors(run[0].split()[2:], template), [],
                                 f"{name}/SKILL.md: give the check only its options and, after --needs, the "
                                 "template's groups, sources and company settings, as company.<setting>")


if __name__ == "__main__":
    unittest.main()
