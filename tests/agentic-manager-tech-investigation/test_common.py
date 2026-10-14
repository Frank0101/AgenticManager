"""Unit tests for skills/agentic-manager-tech-investigation/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, temp_output  # noqa: E402


class StructureTest(unittest.TestCase):
    def test_report_headings(self):
        # skip: the section titles left out, in order; both layers repeat two titles
        executive = ["Executive / product summary", "Problem and intended outcome", "Current status",
                     "Next steps and evolution", "Key decisions and risks"]
        architect = ["Architect summary", "Current status", "Next steps and evolution",
                     "Key decisions and gaps"]
        references = ["References"]
        cases = [((), executive + architect + references),
                 (("evolution",), [t for t in executive if t != "Next steps and evolution"]
                  + [t for t in architect if t != "Next steps and evolution"] + references),
                 (("architecture",), executive + references)]
        for skip, titles in cases:
            with self.subTest(skip=skip):
                self.assertEqual(
                    [title for _, title in common.report_headings(skip)], titles)

    def test_read_skip(self):
        # Only content.json's known dimensions, in their own order; nothing
        # without a readable content.json.
        cases = [(None, ()), ("not JSON", ()), ("[]", ()), ('{"skip": "evolution"}', ()),
                 ('{"skip": ["evolution", "design", "architecture"]}', ("architecture", "evolution"))]
        for text, expected in cases:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                if text is not None:
                    with open(os.path.join(folder, common.CONTENT), "w", encoding="utf-8") as f:
                        f.write(text)
                self.assertEqual(common.read_skip(folder), expected)

    def test_expected_files(self):
        base = {"ledgers.md", "content.json", "Acme_Report.md"}
        cases = [("a report", (), base),
                 ("with a short output", ("exec-summary",),
                  base | {"exec-summary.json", "exec-summary.md"})]
        for name, formats, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.expected_files(
                    "Acme_Report.md", formats), expected)

    def test_short_formats(self):
        # Only a <format>.json with its <format>.md; the research artifacts' names are never formats.
        cases = [(["exec-summary.json", "exec-summary.md"], {"exec-summary"}),
                 (["notes.md"], set()), (["draft.json"], set()),
                 (["content.json", "content.md"], set()),
                 (["ledgers.json", "ledgers.md"], set()),
                 (["Bad Name.json", "Bad Name.md"], set())]
        for names, expected in cases:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as folder:
                for name in names:
                    open(os.path.join(folder, name), "w").close()
                self.assertEqual(common.short_formats(folder), expected)

    def test_check_format(self):
        for label, ok in (("exec-summary", True), ("long-analysis", True), ("slack-update2", True),
                          ("Exec Summary", False), ("exec_summary", False), ("-exec", False), ("", False)):
            with self.subTest(label=label):
                if ok:
                    self.assertEqual(common.check_format(label), label)
                else:
                    with self.assertRaisesRegex(SystemExit, "short lower-case label"):
                        common.check_format(label)


class FoldersTest(unittest.TestCase):
    def test_investigation_dir(self):
        folder = temp_output(self)
        self.assertEqual(common.investigation_dir(INVESTIGATION),
                         (os.path.join(folder, INVESTIGATION), folder, False))
        with self.assertRaisesRegex(SystemExit, "without .."):
            common.investigation_dir("../elsewhere")

    def test_topic_of(self):
        cases = [("/out/Acme-Search_26-10-05", "Acme-Search"), ("/out/Acme-Search_26-10-05/", "Acme-Search"),
                 ("QA-Tools_26-01-31", "QA-Tools")]
        for folder, topic in cases:
            with self.subTest(folder=folder):
                self.assertEqual(common.topic_of(folder), topic)
        for folder in ("/out/Acme-Search", "/out/2026-10-05--acme-search"):
            with self.subTest(folder=folder), self.assertRaisesRegex(SystemExit, "not an investigation folder"):
                common.topic_of(folder)


class MarkdownTest(unittest.TestCase):
    def test_table(self):
        # Cells stay on one line, and a pipe in one is escaped once.
        self.assertEqual(common.table(["A", "B"], [["x | y", "a\nb"], ["already \\| escaped", 3]]),
                         "| A | B |\n| --- | --- |\n| x \\| y | a b |\n| already \\| escaped | 3 |")


class ReferencesTest(unittest.TestCase):
    DEFINED = {"proj-1": "https://acme.example/browse/PROJ-1",
               "api": "https://git.example/acme/api/tree/abc"}

    def test_autolink(self):
        # text: (written, unresolved). A ticket links once the ledger links one of
        # its project; any other key-shaped text is written as code.
        cases = [
            ("PROJ-2 is open.",
             ("[PROJ-2](https://acme.example/browse/PROJ-2) is open.", [])),
            ("acme/api#12 and other/repo#3", ("[acme/api#12](https://git.example/acme/api/pull/12) and "
                                              "[other/repo#3](https://git.example/other/repo/pull/3)", [])),
            ("OPS-1, #9 and UTF-8",
             ("`OPS-1`, #9 and `UTF-8`", ["#9"])),
            ("[PROJ-3](https://x/browse/PROJ-3), `PROJ-4`, https://x/PROJ-5",
             ("[PROJ-3](https://x/browse/PROJ-3), `PROJ-4`, https://x/PROJ-5", [])),
            ("#### PROJ-6 heading", ("#### PROJ-6 heading", [])),
            ("#12 at the start", ("#12 at the start", ["#12"])),
        ]
        for text, expected in cases:
            with self.subTest(text):
                self.assertEqual(common.autolink(text, self.DEFINED), expected)
        # Two hosts and an unlinked repository: no host to choose.
        two = {**self.DEFINED, "b": "https://other.example/x/y/blob/abc/f"}
        self.assertEqual(common.autolink("z/w#1", two)[1], ["z/w#1"])

    def test_id_order_and_finding_blocks(self):
        # IDs sort by number; each finding's block runs to the next finding.
        self.assertEqual(sorted(["S10", "S2", "F01", "Q3"], key=common.id_order), [
                         "F01", "Q3", "S2", "S10"])
        text = "intro\n### F01 — One\n\n- a\n### F02 — Two\n- b\n"
        self.assertEqual(common.finding_blocks(text),
                         {"F01": "### F01 — One\n\n- a", "F02": "### F02 — Two\n- b"})

    def test_unlinked_references(self):
        text = "PROJ-1 [PROJ-2][p] acme/app#3, #4 and `PROJ-5`\n### PROJ-6\n[p]: https://x/PROJ-7"
        self.assertEqual(common.unlinked_references(text),
                         ["PROJ-1", "acme/app#3", "#4"])

    def test_review_rounds_and_the_choice_to_stop(self):
        def review(row_id, outcome):
            return [row_id, "Independent review", common.REVIEW_QUESTION, "s", "None", "High", outcome]
        # (completed rows, rounds, reviewed)
        cases = [([], 0, False), ([review("Q01", "Raised Q02")], 1, False),
                 ([review("Q01", "Raised Q02"), review(
                     "Q03", "Nothing doable found")], 2, True),
                 ([review("Q01", "Raised Q02"), review("Q03", "Stopped by the user: enough")], 1, True)]
        for completed, rounds, done in cases:
            with self.subTest(completed=completed):
                self.assertEqual(common.review_rounds(completed), rounds)
                self.assertEqual(common.reviewed(completed), done)
        self.assertIsNone(common.outcome_problem(
            "Q03", "Stopped by the user: enough", common.REVIEW_QUESTION))

    def test_closing_values(self):
        # (function, value, accepted)
        cases = [(common.outcome_problem, "F01, F02", True), (common.outcome_problem, "G03", True),
                 (common.outcome_problem, "Rejected by the user: not needed", True),
                 (common.outcome_problem, "Answered within scope",
                  False), (common.outcome_problem, "", False),
                 (common.status_problem,
                  "🟨 Implemented, needs significant work (routes read)", True),
                 (common.status_problem, "Implemented", False),
                 (common.depth_problem, "partial: lines 1-70 of 474", True),
                 (common.depth_problem, "Full", True), (common.depth_problem, "skimmed", False)]
        for function, value, accepted in cases:
            with self.subTest(function=function.__name__, value=value):
                problem = function(
                    value) if function is common.depth_problem else function("X01", value)
                self.assertEqual(problem is None, accepted, problem)

    def test_unread_components(self):
        definitions = {
            "search": "https://git.example/acme/api/tree/abc/services/search"}
        component = ["C01", "n", "r", "[search][search]", "🟩 Implemented"]
        cases = [([], ["C01"]),
                 ([["S01", "[f](https://git.example/acme/api/blob/abc/services/search/README.md)", "README", ""]],
                  ["C01"]),
                 ([["S01", "[f](https://git.example/acme/api/blob/abc/services/searcher/main.py)", "full", ""]],
                  ["C01"]),
                 ([["S01", "[f](https://git.example/acme/api/blob/abc/services/search/main.py)", "Full", ""]], [])]
        for coverage, expected in cases:
            with self.subTest(coverage=coverage):
                self.assertEqual(common.unread_components(
                    [component], coverage, definitions), expected)
        self.assertEqual(common.unread_components(
            [component[:4] + ["⬜ Unverified"]], [], definitions), [])


if __name__ == "__main__":
    unittest.main()
