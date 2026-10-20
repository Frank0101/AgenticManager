"""Unit tests for skills/agentic-manager-tech-investigation/scripts/init_investigation.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The config's path is patched to the test's own config, in a temporary folder.
"""

import json
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
import init_investigation  # noqa: E402
import output_diagram  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import temp_output  # noqa: E402
from agentic_manager import config  # noqa: E402

TODAY = date(2026, 10, 5)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_asks_for_node_before_creating_anything(self):
        # The sequences need Node.js, so the first script asks for it
        # before any research is done, not when the report is built.
        with mock.patch.object(output_diagram.shutil, "which", return_value=None):
            with self.assertRaisesRegex(SystemExit, "Node.js 22.13 or newer is needed"):
                init_investigation.main(["--topic", "Acme-Search"])
        self.assertFalse(os.path.exists(self.folder))

    def test_new_investigation_then_a_rerun_replaces_it(self):
        # A new investigation starts with a ledger skeleton that passes the
        # ledger check; running it again the same day starts from scratch.
        result = init_investigation.init("Acme-Search", today=TODAY)
        path = os.path.join(self.folder, "Acme-Search_26-10-05")
        ledger = os.path.join(path, "ledger.md")
        self.assertEqual({k: result[k] for k in ("investigation", "investigation_dir", "replaced")},
                         {"investigation": "Acme-Search_26-10-05", "investigation_dir": path,
                          "replaced": False})
        self.assertEqual(os.listdir(path), ["ledger.md"])
        self.assertEqual(check_report.check_ledger(Path(ledger)), ([], []))
        # The examples folder is there from the first run, empty.
        self.assertEqual(os.listdir(
            os.path.join(self.folder, "_examples")), [])
        # Everything of the earlier run goes, the ledger and the generated files alike, but not
        # the folders of other days.
        with open(ledger, "w", encoding="utf-8") as f:
            f.write("work so far")
        with open(os.path.join(path, "content.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        os.makedirs(os.path.join(self.folder, "Acme-Search_26-10-04"))
        result = init_investigation.init("Acme-Search", today=TODAY)
        self.assertTrue(result["replaced"])
        self.assertTrue(os.path.isdir(os.path.join(
            self.folder, "Acme-Search_26-10-04")))
        self.assertEqual(os.listdir(path), ["ledger.md"])
        self.assertEqual(check_report.check_ledger(Path(ledger)), ([], []))

    def sources(self, **enabled):
        """Write the test's config with the given sources, {group: [names]}, enabled."""
        path = config.CONFIG_PATH
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
        settings["sources"] = {group: {name: {"enabled": True}
                                       for name in names} for group, names in enabled.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f)

    def test_first_actions_and_sources(self):
        # One search of the topic per group with a usable source, in the
        # sources' order of authority; an api or fs source of documentation or
        # code, and any tracker but jira-api, isn't usable.
        signed_in = mock.Mock(return_value=mock.Mock(returncode=0))
        cases = [
            ("every group", {"documentation": ["notion-mcp"], "workflow": ["jira-api"],
                             "source_control": ["github-cli"], "local_vault": ["logseq-fs"]},
             {"code": ["github-cli"], "tracker": ["jira-api"],
                 "documentation": ["notion-mcp"]}, [],
             [("Q01", "Search the code for Acme Search", "github-cli"),
              ("Q02", "Search the tracker for Acme Search",
               "jira-api (tickets.py search)"),
              ("Q03", "Search the documentation for Acme Search", "notion-mcp")],
             "Sources used: code: github-cli; tracker: jira-api; documentation: notion-mcp."),
            ("no tracker", {"documentation": ["notion-fs"], "source_control": ["github-cli"]},
             {"code": ["github-cli"], "tracker": [],
                 "documentation": []}, ["tracker", "documentation"],
             [("Q01", "Search the code for Acme Search", "github-cli")],
             "Sources used: code: github-cli. No usable source for: tracker, documentation."),
        ]
        for name, enabled, sources, missing, actions, boundary in cases:
            with self.subTest(name):
                self.sources(**enabled)
                result = init_investigation.init(
                    "Acme-Search", today=TODAY, run=signed_in)
                self.assertEqual(
                    (result["sources"], result["missing"]), (sources, missing))
                ledger = Path(result["investigation_dir"]) / "ledger.md"
                body = ledger.read_text(encoding="utf-8")
                rows = check_report.ledger_rows(body, "### Ready")
                self.assertEqual([(row[0], row[2], row[3])
                                 for row in rows], actions)
                self.assertIn(
                    f"## Boundary, method and access\n\n{boundary}\n", body)
                self.assertEqual(check_report.check_ledger(ledger), ([], []))
        self.assertEqual(signed_in.call_args.args[0], [
                         "gh", "auth", "status"])

    def test_gh_must_be_usable_before_anything_is_created(self):
        self.sources(source_control=["github-cli"])
        cases = [("not signed in", mock.Mock(return_value=mock.Mock(returncode=1)), "gh isn't signed in"),
                 ("not installed", mock.Mock(side_effect=FileNotFoundError), "gh can't be run")]
        for name, run, expected in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(SystemExit, expected):
                    init_investigation.init(
                        "Acme-Search", today=TODAY, run=run)
                self.assertFalse(os.path.exists(self.folder))
        # Without github-cli, gh isn't asked.
        self.sources(source_control=["gitlab-cli"])
        unused = mock.Mock()
        init_investigation.init("Acme-Search", today=TODAY, run=unused)
        unused.assert_not_called()

    def test_examples(self):
        # Every approved example, newest first by date then copy; other
        # folders, in _examples or beside it, are not examples.
        for name in ("Acme-Search_26-09-01", "2026-09-20--acme-search", "Other_26-09-02",
                     "_examples/Acme-Search_26-09-01", "_examples/Acme-Search_26-09-01--2",
                     "_examples/Other_26-08-02", "_examples/not-an-example"):
            os.makedirs(os.path.join(self.folder, name))
        example = os.path.join(self.folder, "_examples",
                               "Acme-Search_26-09-01")
        with open(os.path.join(example, "Acme-Search_Report.md"), "w", encoding="utf-8") as f:
            f.write("x")
        with open(os.path.join(example, "description.md"), "w", encoding="utf-8") as f:
            f.write("# Acme-Search_26-09-01\n\n**Why it's good:** Clear milestone.\n")
        result = init_investigation.init("Acme-Search", today=TODAY)
        self.assertEqual([(os.path.basename(e["folder"]), e["documents"], e["note"]) for e in result["examples"]],
                         [("Acme-Search_26-09-01--2", [], ""),
                          ("Acme-Search_26-09-01",
                           ["Acme-Search_Report.md"], "Clear milestone."),
                          ("Other_26-08-02", [], "")])

    def test_topic_names(self):
        for topic, ok in (("Payments-Retry-Service", True), ("QA-Tools", True), ("iOS-App", True),
                          ("Payments Retry", False), ("../Escape", False), ("Trailing-", False)):
            with self.subTest(topic=topic):
                if ok:
                    init_investigation.init(topic, today=TODAY)
                else:
                    with self.assertRaises(SystemExit):
                        init_investigation.init(topic, today=TODAY)


if __name__ == "__main__":
    unittest.main()
