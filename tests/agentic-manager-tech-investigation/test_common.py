"""Unit tests for skills/agentic-manager-tech-investigation/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import CODE_HOST, INVESTIGATION, temp_output  # noqa: E402


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
    DEFINED = {"proj-1": "https://acme.example/browse/PROJ-1"}

    def setUp(self):
        self.enterContext(mock.patch.object(
            common, "CODE_HOST", {"host": CODE_HOST}))

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
        # With no code host, no pull request can be linked.
        with mock.patch.object(common, "CODE_HOST", {"host": None}):
            self.assertEqual(common.autolink(
                "z/w#1", self.DEFINED)[1], ["z/w#1"])

    def test_the_code_host_is_the_one_gh_is_signed_in_to(self):
        # name: (github-cli usable, gh's hosts, the code host)
        cases = [("one host", True, ["github.com"], "https://github.com"),
                 ("an enterprise host", True, [
                  "git.acme.example"], "https://git.acme.example"),
                 ("two hosts", True, ["a.example", "b.example"], None),
                 ("signed in to none", True, [], None),
                 ("github-cli not enabled", False, ["github.com"], None)]
        for name, usable, hosts, expected in cases:
            with self.subTest(name), mock.patch.object(common, "CODE_HOST", {}), \
                    mock.patch.object(common, "gh_available", return_value=usable), \
                    mock.patch.object(common, "gh_hosts", return_value=hosts) as asked:
                self.assertEqual(common.code_host(), expected)
                common.code_host()
                # gh is asked once a run, and not at all without github-cli.
                self.assertEqual(asked.call_count, 1 if usable else 0)

    def test_id_order_and_cited_sources(self):
        # IDs sort by number; a source is cited by the findings whose Sources name it.
        self.assertEqual(sorted(["S10", "S2", "F01", "Q3"], key=common.id_order), [
                         "F01", "Q3", "S2", "S10"])
        findings = common.table(common.FINDING_HEADER, [
            ["F01", "One.", "S01 (lines 1-9); [S02](#s02)",
             "Read."], ["F02", "Two.", "F01", "Inferred."],
            ["F03", "Three.", "S02", "Read."]])
        self.assertEqual(common.cited_sources(f"## Findings\n\n{findings}\n"),
                         {1: {"F01"}, 2: {"F01", "F03"}})

    def test_an_unlinked_pull_request_says_why(self):
        # A bare #123 names no repository; owner/repo#123 needs the code host.
        self.assertEqual(common.unresolved_message(["#4", "acme/api#5", "#4"]),
                         "#4: a pull request names its repository, as owner/repo#123, also in a range; acme/api#5: a "
                         "pull request links to the host gh is signed in to, so it needs the github-cli source "
                         "enabled and gh signed in to one host (gh auth status)")

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
        # (the reviews table's rounds, reviewed)
        cases = [([], False), ([["1", "Q02"]], False),
                 ([["1", "Q02"], ["2", "No issue raised"]], True),
                 ([["1", "Q02"], ["2", "Stopped by the user: enough"]], True)]
        for rounds, done in cases:
            with self.subTest(rounds=rounds):
                self.assertEqual(common.reviewed(rounds), done)

    def test_a_component_status_is_an_allowed_one(self):
        # (status, accepted)
        for status, accepted in (("🟦 In development (on a branch)", True), ("Implemented", False)):
            with self.subTest(status):
                problem = common.status_problem("X01", status)
                self.assertEqual(problem is None, accepted, problem)

    def test_how_a_question_closes_and_the_scope_boundaries(self):
        # A question closes on the findings that answer it, never on a gap, a
        # decision or a choice not to pursue it; a scope question is closed by
        # the boundary the user decided, and a question the scope leaves out by
        # the boundary that does.
        asked = "Scope boundary: Should the investigation cover billing?"
        # (name, problem, accepted)
        cases = [("answered", common.outcome_problem("Q07", "F01, F02"), True),
                 ("a gap", common.outcome_problem("Q07", "G03"), False),
                 ("a decision", common.outcome_problem("Q07", "D01"), False),
                 ("rejected", common.outcome_problem(
                     "Q07", "Rejected by the user: not needed"), False),
                 ("answered in words", common.outcome_problem(
                     "Q07", "Answered within scope"), False),
                 ("no answer", common.outcome_problem("Q07", ""), False),
                 ("decided", common.outcome_problem(
                     "Q07", "Decided by the user: [U01](#u01)", asked), True),
                 ("decided with no boundary", common.outcome_problem(
                     "Q07", "Decided by the user: include", asked), False),
                 ("answered by findings", common.outcome_problem(
                     "Q07", "[F01](#f01)", asked), False),
                 ("left out by a boundary", common.outcome_problem(
                     "Q09", "Outside the scope decided in [U01](#u01)"), True),
                 ("left out by a question", common.outcome_problem(
                     "Q09", "Outside the scope decided in [Q07](#q07)"), False),
                 ("a boundary", common.scope_problem(
                     ["U01", "Billing", "include", "[Q07](#q07)"]), True),
                 ("no topic", common.scope_problem(
                     ["U01", "", "include", "Q07"]), False),
                 ("an answer not allowed", common.scope_problem(
                     ["U01", "Billing", "maybe", "Q07"]), False),
                 ("asked in no question", common.scope_problem(["U01", "Billing", "exclude", "None"]), False)]
        for name, problem, accepted in cases:
            with self.subTest(name):
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

    def test_a_gap_names_what_blocks_it(self):
        # A gap nothing blocks is work to do, so it must be a question in the
        # queue and not a gap; scope is a scope question, so no gap waits on
        # the user. (Blocked by, the problem's text, or None)
        cases = [("No access to the cluster", None), ("Waiting on decision D01", None),
                 ("Waiting on decision", "waits on a decision but names none"),
                 ("Out of scope, approved by the user", "is blocked by"),
                 ("Not done yet", "is blocked by"), ("Not started", "is blocked by"), ("", "is blocked by")]
        for blocker, expected in cases:
            with self.subTest(blocker):
                problem = common.gap_problem(
                    ["G01", "Gap", "Missing", "Read it", blocker, "Code", "Owner"])
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")

    def test_a_sources_group_is_one_of_the_groups(self):
        # (Kind, the group as the config names it, accepted): the ledger uses
        # the names code, tracker and documentation, never the config's keys.
        cases = [("code", "source_control", True), ("documentation: vision", "documentation", True),
                 ("Tracker", "workflow", True), ("source_control", None, False), ("", None, False)]
        for value, group, accepted in cases:
            with self.subTest(value):
                row = ["S01", value,
                       "[x](https://example.com/x)", "d", "full", "None", "None"]
                self.assertEqual(common.group_of(row), group)
                self.assertEqual(common.group_problem(row) is None, accepted)

    def test_a_sources_coverage_and_replacement_give_its_mark(self):
        # (Coverage, Superseded by, the report's mark, the problem's text or
        # None, and the kind when not documentation): code read in part names
        # the lines read; a page, anything.
        cases = [("full", "None", None, None), ("Full: every line", "None", None, None),
                 ("partial: lines 1-80 of 352", "None", "limited", None, "code"),
                 ("partial: lines 1-80, 200-240 of 352",
                  "None", "limited", None, "code"),
                 ("partial: the routes", "None", "limited",
                  "names the lines read", "code"),
                 ("entry points: routes", "None", "limited",
                  "Coverage starts with one of", "code"),
                 ("listing", "None", "limited",
                  None), ("search hit", "None", "limited", None),
                 ("can't access: not on the main branch at abc",
                  "None", "limited", None),
                 ("full", "S02", "superseded", None),
                 ("partial: the summary",
                  "[S02](#s02)", "limited, superseded", None),
                 ("skimmed", "None", "limited", "Coverage starts with one of"),
                 ("full", "the 2026 design", "superseded", "Superseded by is None"),
                 ("full", "S01", "superseded", "Superseded by is None"),
                 ("full", "S02, S03", "superseded", "Superseded by is None")]
        for case in cases:
            coverage, superseded, mark, expected, kind = (
                *case, "documentation")[:5]
            with self.subTest(coverage=coverage, superseded=superseded):
                row = ["S01", kind, "[x](https://example.com/x)", "2026-10-01", coverage, "None",
                       superseded]
                self.assertEqual(common.source_mark(row), mark)
                problem = common.coverage_problem(
                    row) or common.superseded_problem(row)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")

    def test_a_finding_states_a_claim_its_sources_and_limits(self):
        # (row, the problem's text, or None)
        cases = [(["F01", "A claim.", "S01 (lines 1-9)", "Read."], None),
                 (["F01", "A conclusion.", "F02, F03", "Inferred."], None),
                 (["F01", " ", "S01", "Read."], "Claim holds the claim"),
                 (["F01", "A claim.", "the code", "Read."],
                  "Sources names the sources"),
                 (["F01", "A claim.", "S01", ""], "Limits says how")]
        for row, expected in cases:
            with self.subTest(row=row):
                problem = common.finding_problem(row)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")

    def test_unread_components(self):
        # A component claiming code needs a code source, read in full or in
        # part, of its path, a file under it, or a folder above it, which
        # covers its files; a README or another document beside the code
        # isn't code.
        definitions = {"search": "https://git.example/acme/api/tree/abc/services/search",
                       "client": "https://git.example/acme/api/blob/abc/app/plugins/client.ts"}
        unread = {"C01": ["acme/api: services/search"]}

        def source(path, coverage, kind="code"):
            return ["S01", kind, f"[f](https://git.example/acme/api/{path})", "abc", coverage, "None", "None"]
        cases = [("nothing read", "[search][search]", [], unread),
                 ("its README in full", "[search][search]",
                  [source("blob/abc/services/search/README.md", "full")], unread),
                 ("a design note under it", "[search][search]",
                  [source("blob/abc/services/search/docs/design.md", "full")], unread),
                 ("a listing of it", "[search][search]", [
                  source("tree/abc/services/search", "listing")], unread),
                 ("a sibling folder", "[search][search]",
                  [source("blob/abc/services/searcher/main.py", "full")], unread),
                 ("a document at its path", "[search][search]",
                  [source("blob/abc/services/search/main.py", "full", "documentation")], unread),
                 ("a file under it", "[search][search]",
                  [source("blob/abc/services/search/main.py", "Full")], {}),
                 ("lines of it", "[search][search]",
                  [source("blob/abc/services/search/main.py", "partial: lines 1-80")], {}),
                 ("a folder above it", "[client][client]", [source("tree/abc/app/plugins", "full")], {})]
        for name, repository, sources, expected in cases:
            with self.subTest(name):
                component = ["C01", "n", "r", repository, "🟩 Implemented"]
                self.assertEqual(common.unread_components(
                    [component], sources, definitions), expected)
        self.assertEqual(common.unread_components(
            [["C01", "n", "r", "[search][search]", "⬜ Unverified"]], [], definitions), {})
        # The message names the path to read.
        self.assertIn("C01 links acme/api: services/search",
                      common.unread_message(unread))


if __name__ == "__main__":
    unittest.main()
