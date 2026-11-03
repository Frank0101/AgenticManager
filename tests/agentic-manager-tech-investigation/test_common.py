"""Unit tests for skills/agentic-manager-tech-investigation/scripts/common.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import CODE_HOST, INVESTIGATION, assert_problem, source_row, temp_output  # noqa: E402

# A repository on the tests' code host, and a link to a path in it.
API = "https://git.example/acme/api/"


def api(path):
    """A link to `path` in API, such as blob/abc/app.py, as a Reference holds it."""
    return f"[f]({API}{path})"


class StructureTest(unittest.TestCase):
    def test_report_headings(self):
        # Every section is always in the report, in this order.
        self.assertEqual([title for _, title in common.report_headings()], [
            "Executive / product summary", "Problem and purpose", "Current status", "Direction",
            "Key decisions and risks", "Architect summary", "How it works today", "Target design",
            "Open technical choices and gaps"])

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


class DesignTest(unittest.TestCase):
    def test_an_identity_has_the_state_of_its_connections(self):
        # The most advanced state of the connections that use it; one no
        # connection uses has none, and a ruled-out connection uses none.
        def connection(ident, identity, state):
            return [ident, "C01", "C02", "HTTP", "q", "yes", identity, state, "Unchanged", "F01"]
        states = common.identity_states([connection("E01", "I01", "🟨 Planned"),
                                         connection(
                                             "E02", "I01", "🟩 Live"),
                                         connection(
                                             "E03", "I02", "🟪 Vision"),
                                         connection(
                                             "E04", "Unknown", "🟩 Live"),
                                         connection(
                                             "E05", "I02", "✖ Ruled out"),
                                         connection("E06", "I03", "✖ Ruled out")])
        self.assertEqual(
            states, {"I01": "🟩 Live", "I02": "🟪 Vision"})

    def test_a_flow_has_the_state_of_its_least_advanced_step_and_runs_in_order(self):
        def connection(ident, start, end, state="🟩 Live"):
            return [ident, start, end, "HTTP", "q", "yes", "None", state, "Unchanged", "F01"]
        connections = [connection("E01", "C01", "C02"), connection("E02", "C02", "C03", "🟨 Planned"),
                       connection("E03", "C02", "C04"), connection(
                           "E04", "C05", "C06"),
                       connection("E06", "C08", "C03")]
        connections += [connection("E05", "C02", "C07", "⬜ Unverified")]
        # name: (the connections walked, the flow's State)
        states = [("all live", "E01, E03", "🟩 Live"),
                  ("one step planned", "E01, E02", "🟨 Planned"),
                  ("one step unverified", "E01, E05", "🟩 Live, unverified: E05"),
                  ("planned, one step unverified", "E01, E02, E05",
                   "🟨 Planned, unverified: E05"),
                  ("none verified", "E05", "⬜ Unverified")]
        for name, walked, expected in states:
            with self.subTest(name):
                self.assertEqual(common.flow_states([["P01", "x", walked, "", "Unchanged", "F01"]], connections),
                                 {"P01": expected})
        # name: (the connections in order, the problem's text, or None)
        cases = [("a chain", "E01, E02", None),
                 ("a branch from a component reached", "E01, E02, E03", None),
                 ("a part that fetches from a component reached", "E01, E02, E06", None),
                 ("out of order", "E06, E01",
                  "E01 runs from C01 to C02, neither of which the flow has reached yet"),
                 ("a jump", "E01, E04", "E04 runs from C05 to C06")]
        for name, walked, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.flow_order_problem(
                    ["P01", "x", walked, "", "Unchanged", "F01"], connections), expected)

    def test_nothing_connects_to_or_flows_through_what_is_ruled_out(self):
        # A part shown not to exist has no live connection, and a flow lists
        # only the steps that happen.
        def component(ident, state):
            return [ident, "n", "service", "None", "r", "None", state, "Unchanged", "F01"]

        def connection(ident, start, end, state):
            return [ident, start, end, "HTTP", "q", "yes", "None", state, "Unchanged", "F01"]
        components = {row[0]: row for row in (
            component("C01", "🟩 Live"), component("C02", "✖ Ruled out"))}
        # name: (From, To, State, the problem's text, or None)
        cases = [("between parts that exist", "C01", "C03", "🟩 Live", None),
                 ("to a ruled-out part", "C01", "C02",
                  "🟩 Live", "To C02 is ✖ Ruled out"),
                 ("from a ruled-out part, unverified", "C02", "C01",
                  "⬜ Unverified", "From C02 is ✖ Ruled out"),
                 ("to a ruled-out part, ruled out too", "C01", "C02", "✖ Ruled out", None)]
        for name, start, end, state, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.connection_ruled_out_problem(
                    connection("E09", start, end, state), components), expected)
        connections = {row[0]: row for row in (connection("E01", "C01", "C03", "🟩 Live"),
                                               connection("E02", "C03", "C02", "✖ Ruled out"))}
        # name: (the connections walked, the problem's text, or None)
        cases = [("only connections that exist", "E01", None),
                 ("through a ruled-out connection", "E01, E02", "P01: E02 is ✖ Ruled out")]
        for name, walked, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.flow_ruled_out_problem(
                    ["P01", "x", walked, "", "Unchanged", "F01"], connections), expected)

    def test_a_status_rests_on_the_kind_of_source_it_claims(self):
        # A planned row needs a finding read in the tracker, a vision one in
        # the documentation, reached through a conclusion too.
        # A search hit or a listing says where to look, not what a page says,
        # so only a source read in full or in part counts.
        sources = {row[0]: row for row in (
            source_row("S01", "code"), source_row("S02", "tracker: story"),
            source_row("S03", "documentation: page",
                       coverage="partial: sections: Decision"),
            source_row("S04", "tracker: search", coverage="search hit"),
            source_row("S05", "documentation: space", coverage="listing"))}
        findings = {"F01": ["F01", "c", "S01"], "F02": ["F02", "c", "S02"],
                    "F03": ["F03", "c", "S03"], "F04": ["F04", "c", "F02"],
                    "F05": ["F05", "c", "S04"], "F06": ["F06", "c", "S05"]}
        # name: (status, evidence, the problem's text, or None)
        cases = [("planned, from the tracker", "🟨 Planned", "F02", None),
                 ("planned, from a search hit in the tracker", "🟨 Planned",
                  "F05", "needs a finding read in the tracker"),
                 ("a vision, from a listing of the documentation", "🟪 Vision",
                  "F06", "needs a finding read in the documentation"),
                 ("planned, from code only", "🟨 Planned",
                  "F01", "needs a finding read in the tracker"),
                 ("planned, through a conclusion", "🟨 Planned", "F04", None),
                 ("a vision, from the documentation", "🟪 Vision", "F03", None),
                 ("a vision, from the tracker only", "🟪 Vision",
                  "F02", "needs a finding read in the documentation"),
                 ("code, checked elsewhere", "🟩 Live", "F02", None)]
        for name, status, evidence, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.evidence_problem(
                    "C01", status, evidence, findings, sources), expected)

    def test_a_connection_claiming_code_rests_on_code_read(self):
        # A call is made by code: a connection marked 🟩 or 🟦 reaches, through
        # its findings, a code source read in full or in part that isn't a
        # README or another document; a listing or a search hit says where to
        # look. Any other state rests on its own kind of source.
        sources = {row[0]: row for row in (
            source_row("S01", reference=api("blob/abc/app/server.py")),
            source_row("S02", reference=api("blob/abc/README.md")),
            source_row("S03", reference=api(
                "tree/abc/app"), coverage="listing"),
            source_row("S04", reference="`gh search code retry`",
                       coverage="search hit"),
            source_row("S05", "documentation", api("blob/abc/app/server.py")))}
        findings = {"F01": ["F01", "c", "S01"], "F02": ["F02", "c", "S02"], "F03": ["F03", "c", "S03"],
                    "F04": ["F04", "c", "S04"], "F05": ["F05", "c", "F06"], "F06": ["F06", "c", "S01"],
                    "F07": ["F07", "c", "S05"]}
        # name: (State, Evidence, the problem's text, or None)
        cases = [("code read", "🟩 Live", "F01", None),
                 ("only its README", "🟩 Live", "F02",
                  "needs a finding read in the code"),
                 ("only a listing", "🟦 In development",
                  "F03", "needs a finding read in the code"),
                 ("only a search hit", "🟩 Live", "F04",
                  "needs a finding read in the code"),
                 ("the code as a document", "🟩 Live", "F07",
                  "needs a finding read in the code"),
                 ("code through a conclusion", "🟩 Live", "F05", None),
                 ("planned, with no code", "🟨 Planned", "F02", None),
                 ("unverified", "⬜ Unverified", "G01", None)]
        for name, state, evidence, expected in cases:
            with self.subTest(name):
                row = ["E01", "C01", "C02", "HTTP", "q", "yes",
                       "None", state, "Unchanged", evidence]
                assert_problem(self, common.connection_code_problem(
                    row, findings, sources, {}), expected)

    def test_a_connection_to_a_mention_only_part_cites_its_decision(self):
        # C02 is a part of a topic the user decided as mention only, U01.
        components = {"C01": ["C01", "API", "service", "None", "r", "None", "🟩 Live", "Unchanged", "F01"],
                      "C02": ["C02", "Gateway", "store", "None", "r", "None", "🟩 Live", "Unchanged", "F01, U01"]}
        # name: (From, To, Evidence, the problem's text, or None)
        cases = [("between researched parts", "C01", "C01", "F01", None),
                 ("from it", "C02", "C01", "F01",
                  "From C02 is a part of a topic decided as mention only"),
                 ("to it", "C01", "C02", "F01",
                  "To C02 is a part of a topic decided as mention only"),
                 ("to it, citing the decision", "C01", "C02", "F01, U01", None),
                 ("to a component the design doesn't hold", "C01", "C09", "F01", None)]
        for name, start, end, evidence, expected in cases:
            with self.subTest(name):
                row = ["E01", start, end, "HTTP", "q", "yes",
                       "None", "🟩 Live", "Unchanged", evidence]
                assert_problem(self, common.connection_scope_problem(
                    row, components, {"U01"}), expected)

    def test_code_is_linked_at_the_revision_read(self):
        # Either revision may be the other's short form, in any case.
        # (one, other, the same commit)
        cases = [("abc1234", "abc1234def567", True), ("abc1234def567", "abc1234", True),
                 ("ABC1234", "abc1234", True), ("abc1234", "abd1234", False), ("", "abc1234", False)]
        for one, other, same in cases:
            with self.subTest(one=one, other=other):
                self.assertEqual(common.same_revision(one, other), same)
        # A Revision names its commit within any text; one naming none, such
        # as a page's date, is itself.
        for revision, expected in (("abc1234", "abc1234"), ("merged as abc1234 on main", "abc1234"),
                                   ("2026-10-01", "2026-10-01")):
            with self.subTest(revision=revision):
                self.assertEqual(common.source_revision(
                    source_row(revision=revision)), expected)
        # name: (the source's row, the problem's text, or None)
        cases = [("the short form of its Revision", source_row(reference=api("blob/abc1234/app.py"),
                                                               revision="abc1234def567"), None),
                 ("the full form of its Revision", source_row(reference=api("blob/abc1234def567/app.py"),
                                                              revision="abc1234"), None),
                 ("a commit within its Revision's text", source_row(reference=api("blob/abc1234/app.py"),
                                                                    revision="merged as abc1234"), None),
                 ("another commit", source_row(reference=api("blob/abc1234/app.py"), revision="def5678"),
                  "S01: Reference links code at abc1234, Revision is def5678"),
                 ("a branch", source_row(reference=api("tree/main/app"), revision="abc1234"),
                  "Reference links code at main"),
                 ("a branch, as its Revision too", source_row(reference=api("blob/main/x.py"), revision="main"),
                  "S01: Reference links code at main: link it at the commit it was read at"),
                 ("a pull request", source_row(reference=api(
                     "pull/7"), revision="abc1234"), None),
                 ("a source other than code", source_row(kind="tracker", reference=api("blob/main/app.py"),
                                                         revision="Done"), None)]
        for name, row, expected in cases:
            with self.subTest(name):
                assert_problem(
                    self, common.source_pin_problem(row, {}), expected)
        # A component links its code at a commit, inline or by reference.
        definitions = {"app": f"{API}tree/main/app",
                       "pinned": f"{API}tree/abc1234/app"}
        cases = [("at a commit", "[app][pinned]", None), ("inline at a commit", api("tree/abc1234/app"), None),
                 ("at a branch", "[app][app]",
                  "C01: Repository, paths, revision links code at main"),
                 ("no code", "None", None)]
        for name, code, expected in cases:
            with self.subTest(name):
                component = ["C01", "n", "service", "None",
                             "r", code, "🟩 Live", "Unchanged", "F01"]
                assert_problem(self, common.component_pin_problem(
                    component, definitions), expected)

    def test_design_problem(self):
        # Rows are built by column name from one valid row per table, so each
        # case says only what it changes.
        valid = {"components": {"ID": "C01", "Name": "Search API", "Kind": "service", "Boundary": "B01",
                                "Responsibility": "Serves", "Repository, paths, revision": "p", "State": "🟩 Live",
                                "In the target": "Unchanged", "Evidence": "F01"},
                 "connections": {"ID": "E01", "From": "C01", "To": "C02", "How": "HTTP", "Data": "query",
                                 "Waits for reply": "yes", "Identity": "I01", "State": "🟩 Live",
                                 "In the target": "Unchanged", "Evidence": "F02"},
                 "boundaries": {"ID": "B01", "Name": "Production cluster", "Kind": "network", "Within": "None",
                                "Evidence": "F04"},
                 "identities": {"ID": "I01", "Name": "web token", "Kind": "service account: token",
                                "What it can reach": "calls on C02", "State": "None: no connection uses it",
                                "In the target": "Unchanged", "Evidence": "F01"},
                 "flows": {"ID": "P01", "Entry point": "A user searches", "Connections in order": "E01, E02",
                           "State": "🟩 Live", "In the target": "Unchanged", "Evidence": "F02"}}
        headers = {"components": common.COMPONENT_HEADER, "connections": common.CONNECTION_HEADER,
                   "boundaries": common.BOUNDARY_HEADER, "identities": common.IDENTITY_HEADER,
                   "flows": common.FLOW_HEADER}

        def row(table, **changed):
            cells = {**valid[table], **
                     {column.replace("_", " "): value for column, value in changed.items()}}
            return [cells[column] for column in headers[table]]
        # name: (table, the row, the problem's text, or None when the row is allowed)
        cases = [
            ("a component in a boundary", "components", row("components"), None),
            ("a component outside any", "components",
             row("components", Boundary="None"), None),
            ("a component with detail after its kind", "components",
             row("components", Kind="service: Fastify"), None),
            ("a component of a kind not listed", "components",
             row("components", Kind="gizmo"), "Kind starts with one of"),
            ("a change in the target with no evidence", "components",
             row("components", In_the_target="Replaced by sync"), "In the target says how"),
            ("a change in the target citing its evidence", "components",
             row("components", In_the_target="Replaced by sync (F02)"), None),
            ("a planned component waiting on an open decision", "components",
             row("components", State="🟨 Planned", Evidence="D01"), None),
            ("a live component resting on no finding", "components",
             row("components", Kind="external", Evidence="U02"), "names in Evidence the finding"),
            ("a component with no boundary", "components",
             row("components", Boundary=""), "Boundary names"),
            ("a component resting on nothing", "components",
             row("components", Evidence=""), "Evidence names"),
            ("an unverified component with no gap", "components",
             row("components", State="⬜ Unverified"), "names the gap"),
            ("a ruled-out component with the finding showing it", "components",
             row("components", State="✖ Ruled out: a module inside the API", Evidence="F03"), None),
            ("a ruled-out component with no finding", "components",
             row("components", State="✖ Ruled out", Evidence="G01"), "the finding that shows it doesn't exist"),
            ("a ruled-out connection with no finding", "connections",
             row("connections", State="✖ Ruled out", Evidence="D01"), "the finding that shows it doesn't exist"),
            ("an unverified component with its gap", "components",
             row("components", State="⬜ Unverified", Evidence="G01"), None),
            ("an unverified component with its scope decision", "components",
             row("components", State="⬜ Unverified", Evidence="U02"), None),
            # A scope decision explains a row only when it left its topic
            # mention only: an included one is researched like the rest, and
            # what the user excluded isn't drawn at all.
            ("an unverified component citing an included topic", "components",
             row("components", State="⬜ Unverified", Evidence="F01, U01"), "names the gap"),
            ("a component resting only on an included topic", "components",
             row("components", State="🟨 Planned", Evidence="U01"), "Evidence names"),
            ("a component of an excluded topic", "components",
             row("components", Evidence="F01, U03"), "U03, which the user excluded"),
            ("an unverified connection to an excluded topic", "connections",
             row("connections", State="⬜ Unverified", Evidence="G01, U03"), "U03, which the user excluded"),
            ("a connection", "connections", row("connections"), None),
            ("a connection that goes away", "connections",
             row("connections", In_the_target="Removed once sync runs (F03)"), None),
            ("a connection's change with no evidence", "connections",
             row("connections", In_the_target="Removed"), "In the target says how"),
            ("a connection whose how has detail", "connections",
             row("connections", How="in-process: a library call"), None),
            ("a connection of a kind not listed", "connections",
             row("connections", How="GitHub API"), "How starts with one of"),
            ("a reply waited for, with detail", "connections",
             row("connections", Waits_for_reply="yes, within 12 s"), None),
            ("a reply neither waited for nor not", "connections",
             row("connections", Waits_for_reply="sometimes"), "Waits for reply starts with"),
            ("a connection of unknown identity", "connections",
             row("connections", Identity="Unknown"), None),
            ("a connection from two components", "connections",
             row("connections", From="C01, C03"), "From names one component"),
            ("a connection to nothing", "connections",
             row("connections", To="the index"), "To names one component"),
            ("a connection with no identity", "connections",
             row("connections", Identity=""), "Identity names"),
            ("a connection with no state", "connections",
             row("connections", State="live"), "E01: State starts with"),
            ("a boundary", "boundaries", row("boundaries"), None),
            ("a boundary with detail", "boundaries",
             row("boundaries", Kind="cloud account: eu-west-2"), None),
            ("a boundary of a kind not listed", "boundaries",
             row("boundaries", Kind="external SaaS"), "Kind starts with one of"),
            ("a boundary within another", "boundaries",
             row("boundaries", Within="B02"), None),
            ("a boundary within itself", "boundaries",
             row("boundaries", Within="B01"), "Within names the boundary"),
            ("a boundary within no boundary", "boundaries",
             row("boundaries", Within="the cloud"), "Within names the boundary"),
            ("an identity", "identities", row("identities"), None),
            ("an identity of a kind not listed", "identities",
             row("identities", Kind="token"), "Kind starts with one of"),
            ("an identity's change with no evidence", "identities",
             row("identities", In_the_target="Gains write access"), "In the target says how"),
            ("an identity reaching no component", "identities",
             row("identities", What_it_can_reach="the API"), "What it can reach names the components"),
            ("an identity resting on nothing", "identities",
             row("identities", Evidence="-"), "Evidence names"),
            ("a flow", "flows", row("flows"), None),
            ("a flow with no connections", "flows",
             row("flows", Connections_in_order="the search"), "Connections in order names"),
        ]
        scope = {"U01": "include", "U02": "mention only", "U03": "exclude"}
        for name, table, row, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.design_problem(
                    table, row, scope), expected)

    def test_a_component_status_is_an_allowed_one(self):
        # (status, accepted)
        for status, accepted in (("🟦 In development (on a branch)", True), ("Live", False)):
            with self.subTest(status):
                problem = common.status_problem("X01", status)
                self.assertEqual(problem is None, accepted, problem)

    def test_unread_components(self):
        # A component claiming code needs a code source, read in full or in
        # part, that its Evidence's findings cite, of its path, a file under
        # it, or a folder above it read in full, which covers its files; a
        # folder or a pull request read file by file covers the files it
        # names, a pull request's at its Revision. A README or another
        # document beside the code isn't code. A link that is no path in a
        # repository, such as a page or a pull request, is covered by a read
        # of that link.
        definitions = {"search": f"{API}tree/abc/services/search", "client": f"{API}blob/abc/app/plugins/client.ts",
                       "page": "https://code.example/acme/tool", "pull": f"{API}pull/7"}
        unread = {"C01": ["acme/api: services/search"]}
        client_unread = {"C01": ["acme/api: app/plugins/client.ts"]}

        def source(path, coverage, kind="code", revision="abc"):
            return source_row(kind=kind, reference=api(path), revision=revision, coverage=coverage)
        # name: (the component's code, its sources, what is unread, and its
        # evidence when not F01, which cites the source)
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
                 ("a file under it, through a conclusion", "[search][search]",
                  [source("blob/abc/services/search/main.py", "full")], {}, "F02"),
                 ("a file under it no finding of its evidence cites", "[search][search]",
                  [source("blob/abc/services/search/main.py", "full")], unread, "F08"),
                 ("a folder above it", "[client][client]",
                  [source("tree/abc/app/plugins", "full")], {}),
                 ("a folder above it, read in part", "[client][client]",
                  [source("tree/abc/app/plugins", "partial: files: server.ts")], client_unread),
                 ("a folder above it, naming its file", "[client][client]",
                  [source("tree/abc/app", "partial: files: plugins/client.ts")], {}),
                 ("a folder naming a file under it", "[search][search]",
                  [source("tree/abc/services", "partial: files: search/main.py, other/x.py")], {}),
                 ("a folder naming only its README", "[search][search]",
                  [source("tree/abc/services", "partial: files: search/README.md")], unread),
                 ("a pull request naming its file", "[client][client]",
                  [source("pull/7", "partial: files: app/plugins/client.ts")], {}),
                 ("a pull request at another revision", "[client][client]",
                  [source("pull/7", "partial: files: app/plugins/client.ts", revision="def")], client_unread),
                 ("a pull request naming other files", "[client][client]",
                  [source("pull/7", "partial: files: app/main.ts")], client_unread),
                 ("a page read in full at its link", "[tool][page]",
                  [source_row(reference="[t](https://code.example/acme/tool)")], {}),
                 ("a pull request it links, read",
                  "[pull][pull]", [source("pull/7", "full")], {}),
                 ("a pull request it links, naming files of it", "[pull][pull]",
                  [source("pull/7", "partial: files: app/main.ts")], {}),
                 ("a pull request it links, naming no file of its code", "[pull][pull]",
                  [source("pull/7", "partial: files: README.md")], {"C01": [f"{API}pull/7"]})]
        findings = {"F01": ["F01", "c", "S01", "None"], "F02": ["F02", "c", "F01", "None"],
                    "F08": ["F08", "c", "S99", "None"]}
        for name, repository, sources, expected, *evidence in cases:
            with self.subTest(name):
                component = ["C01", "n", "service", "None", "r",
                             repository, "🟩 Live", "Unchanged", (evidence or ["F01"])[0]]
                self.assertEqual(common.unread_components(
                    [component], findings, {row[0]: row for row in sources}, definitions), expected)
        # No code is asked of an unverified row, of an external part, or of
        # a part of a mention-only topic citing that decision (U02 here, not
        # U01, which included its topic).
        # name: (kind, state, evidence, unread)
        cases = [("unverified", "service", "⬜ Unverified", "G01", {}),
                 ("an external part", "external",
                  "🟩 Live", "F01", {}),
                 ("a mention-only part", "store", "🟩 Live", "F01, U02", {}),
                 ("a part of an included topic", "store", "🟩 Live", "F01, U01", unread)]
        for name, kind, state, evidence, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.unread_components(
                    [["C01", "n", kind, "None", "r", "[search][search]",
                        state, "Unchanged", evidence]], findings, {},
                    definitions, {"U02"}), expected)
        # The message names the path to read.
        self.assertIn("C01 links acme/api: services/search",
                      common.unread_message(unread))


class LedgerRulesTest(unittest.TestCase):
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

    def test_how_a_question_closes_and_the_scope_boundaries(self):
        # A question closes on the findings that answer it, never on a gap, a
        # decision or a choice not to pursue it; a scope question is closed by
        # the boundary the user decided, and a question the scope leaves out by
        # a boundary that left its topic out, mention only or excluded.
        asked = "Scope boundary: Should the investigation cover billing?"
        scope = {"U01": "mention only", "U02": "include", "U03": "exclude"}

        def closed(outcome, question="Read the code"):
            return common.outcome_problem("Q07", outcome, question, scope)
        # (name, problem, accepted)
        cases = [("answered", closed("F01, F02"), True),
                 ("a gap", closed("G03"), False),
                 ("a decision", closed("D01"), False),
                 ("rejected", closed("Rejected by the user: not needed"), False),
                 ("answered in words", closed("Answered within scope"), False),
                 ("no answer", closed(""), False),
                 ("decided", closed(
                     "Decided by the user: [U01](#u01)", asked), True),
                 ("decided with no boundary", closed(
                     "Decided by the user: include", asked), False),
                 ("answered by findings", closed("[F01](#f01)", asked), False),
                 ("left out by a boundary", closed(
                     "Outside the scope decided in [U01](#u01)"), True),
                 ("left out by an exclusion", closed(
                     "Outside the scope decided in [U03](#u03)"), True),
                 ("left out by an inclusion", closed(
                     "Outside the scope decided in [U02](#u02)"), False),
                 ("left out by a boundary the ledger doesn't hold",
                  closed("Outside the scope decided in [U09](#u09)"), False),
                 ("left out by a question", closed(
                     "Outside the scope decided in [Q07](#q07)"), False),
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
                assert_problem(self, common.gap_problem(
                    ["G01", "Gap", blocker, "Owner", "F01"]), expected)

    def test_a_sources_reference_links_it(self):
        # A link, or for a search, its exact query; a backticked text that
        # isn't a search's links nothing.
        # name: (the source's row, the problem's text, or None)
        cases = [("a link", source_row(), None),
                 ("a search's query", source_row(
                     reference="`retry`", coverage="search hit"), None),
                 ("a path in backticks", source_row(
                     reference="`src/app.py`"), "S01: link the Reference"),
                 ("plain text", source_row(reference="src/app.py"),
                  "S01: link the Reference"),
                 # Brackets between backticks are code, never a link.
                 ("a pattern's brackets, not a search", source_row(
                     reference="`grep 'PROJ-6[0-9][0-9]'`", coverage="listing"), "S01: link the Reference"),
                 ("a search whose pattern has brackets", source_row(
                     reference="`grep 'PROJ-6[0-9][0-9]'`", coverage="search hit"), None)]
        for name, row, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.source_problem(row, {}), expected)

    def test_a_sources_group_is_one_of_the_groups(self):
        # (Kind, the group as the config names it, accepted): the ledger uses
        # the names code, tracker and documentation, never the config's keys.
        cases = [("code", "source_control", True), ("documentation: vision", "documentation", True),
                 ("Tracker", "workflow", True), ("source_control", None, False), ("", None, False)]
        for value, group, accepted in cases:
            with self.subTest(value):
                row = source_row(kind=value)
                self.assertEqual(common.group_of(row), group)
                self.assertEqual(common.group_problem(row) is None, accepted)

    def test_a_sources_coverage_and_replacement_follow_their_rules(self):
        # (Coverage, Superseded by, the problem's text or None, and the kind
        # when not documentation): code read in part names the lines read; a
        # page, anything.
        cases = [("full", "None", None), ("Full: every line", "None", None),
                 ("partial: lines 1-80 of 352", "None", None, "code"),
                 ("partial: lines 1-80, 200-240 of 352", "None", None, "code"),
                 ("partial: the routes", "None", "names the lines read", "code"),
                 ("entry points: routes", "None",
                  "Coverage starts with one of", "code"),
                 ("listing", "None", None), ("search hit", "None", None),
                 ("can't access: not on the main branch at abc", "None", None),
                 ("full", "S02", None),
                 ("partial: sections: Summary", "[S02](#s02)", None),
                 ("skimmed", "None", "Coverage starts with one of"),
                 ("full", "the 2026 design", "Superseded by is None"),
                 ("full", "S01", "Superseded by is None"),
                 ("full", "S02, S03", "Superseded by is None")]
        for case in cases:
            coverage, superseded, expected, kind = (*case, "documentation")[:4]
            with self.subTest(coverage=coverage, superseded=superseded):
                row = source_row(kind=kind, revision="2026-10-01",
                                 coverage=coverage, superseded=superseded)
                assert_problem(self, common.coverage_problem(
                    row) or common.superseded_problem(row), expected)

    def test_a_finding_states_a_claim_its_sources_and_limits(self):
        # (row, the problem's text, or None)
        cases = [(["F01", "A claim.", "S01 (lines 1-9)", "Read."], None),
                 (["F01", "A conclusion.", "F02, F03", "Inferred."], None),
                 (["F01", " ", "S01", "Read."], "Claim holds the claim"),
                 (["F01", "A claim.", "the code", "Read."],
                  "Sources names the sources"),
                 (["F01", "A claim.", "S01", ""], "Limits says what")]
        for row, expected in cases:
            with self.subTest(row=row):
                assert_problem(self, common.finding_problem(row), expected)

    def test_a_finding_explains_each_partial_read(self):
        # Each source a finding cites that was read only in part, of
        # `partial`, has its own reason in Limits, "S01 read in part: …".
        partial = {"S01", "S02"}
        # name: (Sources, Limits, the sources left unexplained)
        cases = [("explained", "S01", "S01 read in part: the rest is tests.", []),
                 ("explained, as a citation",
                  "[S01](#s01)", "[S01](#s01) read in part: the rest is tests.", []),
                 ("two read in part, one explained", "S01, S02",
                  "S01 read in part: the rest is tests.", ["S02"]),
                 ("an empty reason", "S01", "S01 read in part: .", ["S01"]),
                 ("a reason for another source", "S01",
                  "S02 read in part: the rest is tests.", ["S01"]),
                 ("a source read in full", "S03", "None", [])]
        for name, sources, limits, expected in cases:
            with self.subTest(name):
                self.assertEqual(common.unexplained_partial_reads(["F01", "A claim.", sources, limits], partial),
                                 expected)

    def test_a_finding_cites_only_lines_its_source_covers(self):
        # Lines a finding cites of a file read in part lie within what its
        # Coverage names; a source read in full, or with no lines named,
        # leaves nothing to compare.
        sources = {"S01": source_row(coverage="partial: lines 1-80, 200-240 of 352"),
                   "S02": source_row(coverage="full"),
                   "S03": source_row(coverage="partial: sections: Decision")}
        # name: (Sources, the problem's text, or None)
        cases = [("lines read", "S01 (lines 10-40, 200-240)", None),
                 ("a single line read", "[S01](#s01) (line 72)", None),
                 ("lines past the read", "S01 (lines 70-90)",
                  "F01: cites lines 70-90 of S01, which its Coverage doesn't include"),
                 ("a line unread among several", "S01 (lines 1-3, 95, 238-245)",
                  "cites lines 95, 238-245 of S01"),
                 ("the unread lines of the source they follow",
                  "S02 (lines 500-510); S01 (lines 1-10)", None),
                 ("a source read in full", "S02 (lines 900-910)", None),
                 ("a part named by sections", "S03 (lines 5-9)", None),
                 ("no lines cited", "S01", None)]
        for name, cited, expected in cases:
            with self.subTest(name):
                assert_problem(self, common.unread_lines_problem(
                    ["F01", "A claim.", cited, "None"], sources), expected)

    def test_every_read_but_a_full_one_leaves_a_part_unread(self):
        # A finding citing any of these explains why the unread part can't
        # change it; can't access reads nothing, so there is no part.
        cases = [("full", False), ("partial: lines 1-80", True), ("listing", True),
                 ("search hit", True), ("can't access: no permission", False)]
        for coverage, expected in cases:
            with self.subTest(coverage):
                self.assertEqual(common.read_in_part(
                    source_row(coverage=coverage)), expected)


if __name__ == "__main__":
    unittest.main()
