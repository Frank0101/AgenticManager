"""Checks that every skill follows an archetype (see AGENTS.md, Archetypes):
README.md's table of skills names one of archetypes/ for each, AGENTS.md lists
every archetype there is, and a skill has what its archetype's file says is
checked, such as the scripts of its steps.
Run with: python3 tests/run.py repo
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
ARCHETYPES = os.path.join(REPO_ROOT, "archetypes")
# A row of README.md's table of skills: the skill, linked to its folder, then
# its archetype, linked to its file.
ROW = re.compile(
    r"^\|\s*\[([^\]]+)\]\(skills/[^)]+\)\s*\|\s*\[[^\]]+\]\(archetypes/([^)]+)\)", re.M)
# The scripts of the steps every report archetype has: Finish, its view and its
# checker.
REPORT_SCRIPTS = ("finish_report.py", "make_report.py", "check_report.py")
FINISH = re.compile(r"^finish_(\w+)\.py$")


def missing_scripts(archetype, skill_md, scripts):
    """The scripts a skill of an archetype lacks, given its SKILL.md's text
    and the names in its scripts folder, as the archetype's file says under
    Checked."""
    if archetype == "conversation-document.md":
        kinds = [m.group(1) for m in map(FINISH.match, scripts) if m]
        if len(kinds) != 1:
            return ["finish_<kind>.py, one"]
        return [name for name in (f"make_{kinds[0]}.py", f"check_{kinds[0]}.py") if name not in scripts]
    wanted = list(REPORT_SCRIPTS)
    if archetype == "data-report.md":
        wanted += ["build_data.py", *(["make_charts.py"] if "_charts/" in skill_md else []),
                   *(["make_brief.py", "prepare_report.py"] if "brief.json" in skill_md else [])]
    return [name for name in wanted if name not in scripts]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class ArchetypesTest(unittest.TestCase):
    def test_every_skill_names_an_archetype(self):
        rows = dict(ROW.findall(read(os.path.join(REPO_ROOT, "README.md"))))
        skills = [name for name in os.listdir(os.path.join(REPO_ROOT, "skills"))
                  if os.path.isfile(os.path.join(REPO_ROOT, "skills", name, "SKILL.md"))
                  and not name.startswith("agentic-manager-utils-")]
        for skill in sorted(skills):
            with self.subTest(skill):
                self.assertIn(skill, rows, f"README.md: give {skill} its archetype, linked to its file in "
                              "archetypes/, in the table's Archetype column")
                self.assertTrue(os.path.isfile(os.path.join(ARCHETYPES, rows[skill])),
                                f"README.md: {skill}'s archetype, archetypes/{rows[skill]}, doesn't exist")

    def test_agents_lists_every_archetype(self):
        listed = set(re.findall(
            r"\]\(archetypes/([^)]+\.md)\)", read(os.path.join(REPO_ROOT, "AGENTS.md"))))
        self.assertEqual(listed, set(os.listdir(ARCHETYPES)),
                         "AGENTS.md's Archetypes must list every file of archetypes/, and only those")

    def test_skills_have_their_scripts(self):
        for skill, archetype in ROW.findall(read(os.path.join(REPO_ROOT, "README.md"))):
            folder = os.path.join(REPO_ROOT, "skills", skill)
            with self.subTest(skill):
                missing = missing_scripts(archetype, read(os.path.join(folder, "SKILL.md")),
                                          os.listdir(os.path.join(folder, "scripts")))
                self.assertEqual(missing, [], f"{skill}: a skill of its archetype has these scripts, as "
                                 f"archetypes/{archetype} says under Checked: add them")

    def test_missing_scripts(self):
        # name: (archetype, SKILL.md's text, its scripts, the scripts missing)
        data = ["build_data.py", *REPORT_SCRIPTS]
        cases = [("data report", "data-report.md", "data.json", data, []),
                 ("no check", "data-report.md", "data.json",
                  data[:-1], ["check_report.py"]),
                 ("charts", "data-report.md", "_charts/",
                  data, ["make_charts.py"]),
                 ("a brief", "data-report.md", "brief.json", data,
                  ["make_brief.py", "prepare_report.py"]),
                 ("research report", "research-report.md",
                  "", list(REPORT_SCRIPTS), []),
                 ("no finish", "research-report.md", "", list(REPORT_SCRIPTS[1:]),
                  ["finish_report.py"]),
                 ("conversation document", "conversation-document.md", "",
                  ["finish_deck.py", "make_deck.py", "check_deck.py"], []),
                 ("no view", "conversation-document.md", "",
                  ["finish_deck.py", "check_deck.py"], ["make_deck.py"]),
                 ("no finish command", "conversation-document.md", "",
                  ["make_deck.py", "check_deck.py"], ["finish_<kind>.py, one"])]
        for name, archetype, text, scripts, expected in cases:
            with self.subTest(name):
                self.assertEqual(missing_scripts(
                    archetype, text, scripts), expected)


if __name__ == "__main__":
    unittest.main()
