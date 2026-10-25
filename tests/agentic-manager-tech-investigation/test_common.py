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
        # Every section is always in the report, in this order.
        self.assertEqual([title for _, title in common.report_headings()], [
            "Executive / product summary", "Problem and purpose", "Current status", "Direction",
            "Key decisions and risks", "Architect summary", "How it works today", "Target design",
            "Open technical choices and gaps", "References"])

    def test_expected_files(self):
        self.assertEqual(common.expected_files("Acme_Report.md"),
                         {"ledger.md", "content.json", "Acme_Report.md"})


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

    def test_design_problem(self):
        # name: (table, row, the problem's text, or None when the row is allowed)
        component = ["C01", "Search API (service)", "Serves",
                     "p", "🟩 Implemented", "d", "F01", "n", "B01"]
        connection = ["E01", "C01", "C02", "HTTP",
                      "query", "yes", "I01", "🟩 Implemented", "F02"]
        cases = [
            ("a component in a boundary", "components", component, None),
            ("a component outside any", "components",
             component[:8] + ["None"], None),
            ("a component with no boundary", "components",
             component[:8] + [""], "Boundary names"),
            ("a component resting on nothing", "components",
             component[:6] + ["", "n", "B01"], "Evidence names"),
            ("an unverified component with no gap", "components",
             component[:4] + ["⬜ Unverified"] + component[5:], "names the gap"),
            ("an unverified component with its gap", "components",
             component[:4] + ["⬜ Unverified"] + component[5:6] + ["G01"] + component[7:], None),
            ("a connection", "connections", connection, None),
            ("a connection of unknown identity", "connections",
             connection[:6] + ["Unknown"] + connection[7:], None),
            ("a connection from two components", "connections", connection[:1] + ["C01, C03"] + connection[2:],
             "From names one component"),
            ("a connection to nothing", "connections", connection[:2] + ["the index"] + connection[3:],
             "To names one component"),
            ("a connection with no identity", "connections", connection[:6] + [""] + connection[7:],
             "Identity names"),
            ("a connection with no state", "connections", connection[:7] + ["live"] + connection[8:],
             "E01: State starts with"),
            ("a boundary", "boundaries", [
             "B01", "Production cluster", "network", "F04"], None),
            ("an identity resting on nothing", "identities", ["I01", "token", "token", "the API", "-"],
             "Evidence names"),
            ("a flow", "flows", [
             "P01", "A user searches", "E01, E02", "F02"], None),
            ("a flow with no connections", "flows", ["P01", "A user searches", "the search", "F02"],
             "Connections in order names"),
        ]
        for name, table, row, expected in cases:
            with self.subTest(name):
                problem = common.design_problem(table, row)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")

    def test_the_review_ends_on_a_round_raising_nothing_or_the_choice_to_stop(self):
        def review(row_id, outcome):
            return [row_id, "Independent review", common.REVIEW_QUESTION, "s", "None", outcome]
        # (completed rows, reviewed)
        cases = [([], False), ([review("Q01", "Raised Q02")], False),
                 ([review("Q01", "Raised Q02"), review(
                     "Q03", "No issue raised")], True),
                 ([review("Q01", "Raised Q02"), review("Q03", "Stopped by the user: enough")], True)]
        for completed, done in cases:
            with self.subTest(completed=completed):
                self.assertEqual(common.reviewed(completed), done)
        self.assertIsNone(common.outcome_problem(
            "Q03", "Stopped by the user: enough", common.REVIEW_QUESTION))

    def test_closing_values(self):
        # (function, value, accepted)
        cases = [(common.outcome_problem, "F01, F02", True), (common.outcome_problem, "G03", False), (common.outcome_problem, "D01", False),
                 (common.outcome_problem, "Rejected by the user: not needed", False),
                 (common.outcome_problem, "Answered within scope",
                  False), (common.outcome_problem, "", False),
                 (common.status_problem,
                  "🟦 In development (on a branch)", True),
                 (common.status_problem, "Implemented", False),
                 (common.depth_problem, "partial: lines 1-70 of 474", True),
                 (common.depth_problem, "Full",
                  True), (common.depth_problem, "skimmed", False)]
        for function, value, accepted in cases:
            with self.subTest(function=function.__name__, value=value):
                problem = function(
                    value) if function is common.depth_problem else function("X01", value)
                self.assertEqual(problem is None, accepted, problem)

    def test_a_blocked_question_names_what_blocks_it(self):
        # Q03 is blocked; Q04 is still open, so it blocks nothing.
        # (Depends on, accepted)
        cases = [("G01", True), ("D02", True), ("Q03", True),
                 ("Q04", False), ("None", False), ("", False)]
        for depends_on, accepted in cases:
            with self.subTest(depends_on):
                problem = common.blocked_problem("Q09", depends_on, {"Q03"})
                self.assertEqual(problem is None, accepted, problem)

    def test_a_sources_group_is_one_of_the_groups(self):
        # (Group / evidence kind, group, accepted)
        cases = [("source_control", "source_control", True), ("documentation: vision", "documentation", True),
                 ("Workflow", "workflow", True), ("code", None, False), ("", None, False)]
        for value, group, accepted in cases:
            with self.subTest(value):
                row = ["S01", value,
                       "[x](https://example.com/x)", "d", "Read.", "None", ""]
                self.assertEqual(common.group_of(row), group)
                self.assertEqual(common.group_problem(row) is None, accepted)

    def test_a_sources_limits_give_its_mark(self):
        # (Access limits / superseded by, mark, accepted)
        cases = [("None", None, True), ("", None, True),
                 ("Limited: only lines 1-200 read", "limited", True),
                 ("superseded by the 2026 design", "superseded", True),
                 ("only lines 1-200 read", None, False)]
        for value, mark, accepted in cases:
            with self.subTest(value):
                row = ["S01", "documentation",
                       "[x](https://example.com/x)", "d", "Read.", value, ""]
                self.assertEqual(common.limit_mark(row), mark)
                self.assertEqual(common.limits_problem(row) is None, accepted)

    def test_unread_components(self):
        # A component claiming code needs coverage, at a reading depth, of its
        # path, a file under it, or a folder above it, which covers its files.
        definitions = {"search": "https://git.example/acme/api/tree/abc/services/search",
                       "client": "https://git.example/acme/api/blob/abc/app/plugins/client.ts"}
        unread = {"C01": ["acme/api: services/search"]}
        cases = [("nothing read", "[search][search]", [], unread),
                 ("a README", "[search][search]",
                  [["S01", "[f](https://git.example/acme/api/blob/abc/services/search/README.md)", "README"]], unread),
                 ("a sibling folder", "[search][search]",
                  [["S01", "[f](https://git.example/acme/api/blob/abc/services/searcher/main.py)", "full"]], unread),
                 ("a file under it", "[search][search]",
                  [["S01", "[f](https://git.example/acme/api/blob/abc/services/search/main.py)", "Full"]], {}),
                 ("a folder above it", "[client][client]",
                  [["S01", "[plugins](https://git.example/acme/api/tree/abc/app/plugins)", "full"]], {})]
        for name, repository, coverage, expected in cases:
            with self.subTest(name):
                component = ["C01", "n", "r", repository, "🟩 Implemented"]
                self.assertEqual(common.unread_components(
                    [component], coverage, definitions), expected)
        self.assertEqual(common.unread_components(
            [["C01", "n", "r", "[search][search]", "⬜ Unverified"]], [], definitions), {})
        # The message names the path to read.
        self.assertIn("C01 links acme/api: services/search",
                      common.unread_message(unread))


if __name__ == "__main__":
    unittest.main()
