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
sys.path.insert(0, TEST_DIR)
from investigation_fixture import temp_output  # noqa: E402
from agentic_manager import config  # noqa: E402

TODAY = date(2026, 10, 5)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

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
        # One question about the topic per group, the documentation first; a
        # source of another group, such as a local vault, is not used.
        signed_in = mock.Mock(return_value=mock.Mock(returncode=0))
        cases = [
            ("every group", {"documentation": ["notion-mcp"], "workflow": ["jira-api"],
                             "source_control": ["github-cli"], "local_vault": ["logseq-fs"]},
             {"code": ["github-cli"], "tracker": ["jira-api"],
                 "documentation": ["notion-mcp"]},
             [("Q01", "What does the documentation say about Acme Search?", "notion-mcp"),
              ("Q02", "What does the tracker say about Acme Search?",
               "jira-api (tickets.py search)"),
              ("Q03", "What does the code say about Acme Search?", "github-cli")]),
        ]
        for name, enabled, sources, actions in cases:
            with self.subTest(name):
                self.sources(**enabled)
                result = init_investigation.init(
                    "Acme-Search", today=TODAY, run=signed_in)
                self.assertEqual(result["sources"], sources)
                ledger = Path(result["investigation_dir"]) / "ledger.md"
                body = ledger.read_text(encoding="utf-8")
                rows = check_report.ledger_rows(body, "### Ready")
                self.assertEqual([(row[0], row[2], row[3])
                                 for row in rows], actions)
                # The boundary is the user's, written after the ledger exists.
                self.assertIn(
                    "## Boundary\n\nNone yet.\n", body)
                self.assertEqual(check_report.check_ledger(ledger), ([], []))
        self.assertEqual(signed_in.call_args.args[0], [
                         "gh", "auth", "status"])

    def test_every_group_needs_a_usable_source_before_anything_is_created(self):
        # A code source other than a cli one, an api or fs source of the
        # documentation, and any tracker but jira-api, isn't usable; gh isn't
        # asked when a group has none.
        unused = mock.Mock()
        cases = [("no tracker", {"documentation": ["notion-mcp"], "source_control": ["github-cli"]}, "tracker"),
                 ("code through an mcp source", {"documentation": ["notion-mcp"], "workflow": ["jira-api"],
                                                 "source_control": ["github-mcp"]}, "code"),
                 ("unusable channels", {"documentation": ["notion-fs"], "workflow": ["linear-api"],
                                        "source_control": ["github-api"]}, "code, tracker, documentation")]
        for name, enabled, missing in cases:
            with self.subTest(name):
                self.sources(**enabled)
                with self.assertRaisesRegex(SystemExit, f"No usable source for: {missing}\\."):
                    init_investigation.init(
                        "Acme-Search", today=TODAY, run=unused)
                self.assertFalse(os.path.exists(self.folder))
        unused.assert_not_called()

    def test_gh_must_be_usable_before_anything_is_created(self):
        every = {"documentation": ["notion-mcp"], "workflow": ["jira-api"]}
        self.sources(source_control=["github-cli"], **every)
        cases = [("not signed in", mock.Mock(return_value=mock.Mock(returncode=1)), "gh isn't signed in"),
                 ("not installed", mock.Mock(side_effect=FileNotFoundError), "gh can't be run")]
        for name, run, expected in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(SystemExit, expected):
                    init_investigation.init(
                        "Acme-Search", today=TODAY, run=run)
                self.assertFalse(os.path.exists(self.folder))
        # Without github-cli, gh isn't asked.
        self.sources(source_control=["gitlab-cli"], **every)
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
            f.write("# Acme-Search_26-09-01\n\n**Why it's good:** Clear status.\n")
        result = init_investigation.init("Acme-Search", today=TODAY)
        self.assertEqual([(os.path.basename(e["folder"]), e["documents"], e["note"]) for e in result["examples"]],
                         [("Acme-Search_26-09-01--2", [], ""),
                          ("Acme-Search_26-09-01",
                           ["Acme-Search_Report.md"], "Clear status."),
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
