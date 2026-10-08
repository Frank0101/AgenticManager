# Unit tests for skills/agentic-manager-tech-investigation/scripts/init_investigation.py.
# The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The config's path is patched to the test's own config, in a temporary folder.
import os
import sys
import unittest
from datetime import date
from pathlib import Path

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
import init_investigation  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import temp_output  # noqa: E402

TODAY = date(2026, 10, 5)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_new_investigation_then_a_follow_up(self):
        # A new investigation starts with a ledger skeleton that passes the
        # ledger check; a follow-up the same day keeps the ledger as it is.
        result = init_investigation.init("Acme-Search", today=TODAY)
        path = os.path.join(self.folder, "Acme-Search_26-10-05")
        ledger = os.path.join(path, "ledgers.md")
        self.assertEqual({k: result[k] for k in ("investigation", "investigation_dir", "follow_up", "files", "earlier")},
                         {"investigation": "Acme-Search_26-10-05", "investigation_dir": path,
                          "follow_up": False, "files": [], "earlier": []})
        self.assertEqual(os.listdir(path), ["ledgers.md"])
        self.assertEqual(check_report.check_ledger(Path(ledger)), ([], []))
        with open(os.path.join(self.folder, "_examples", "README.md"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("## Index\n"))
        with open(ledger, "w", encoding="utf-8") as f:
            f.write("work so far")
        result = init_investigation.init("Acme-Search", today=TODAY)
        self.assertEqual(
            (result["follow_up"], result["files"]), (True, ["ledgers.md"]))
        with open(ledger, encoding="utf-8") as f:
            self.assertEqual(f.read(), "work so far")

    def test_earlier_folders_and_examples(self):
        for name in ("Acme-Search_26-09-01", "2026-09-20--acme-search", "Acme-Search_26-08-01",
                     "Other_26-09-02", "_examples/Acme-Search_26-09-01--exec-summary",
                     "_examples/Acme-Search_26-09-01--exec-summary--2", "_examples/Other_26-09-02--long-analysis"):
            os.makedirs(os.path.join(self.folder, name))
        with open(os.path.join(self.folder, "_examples", "Acme-Search_26-09-01--exec-summary", "exec-summary.md"), "w",
                  encoding="utf-8") as f:
            f.write("x")
        result = init_investigation.init(
            "Acme-Search", "exec-summary", today=TODAY)
        self.assertEqual(result["earlier"], [
                         "2026-09-20--acme-search", "Acme-Search_26-09-01", "Acme-Search_26-08-01"])
        self.assertEqual([(os.path.basename(e["folder"]), e["documents"]) for e in result["examples"]],
                         [("Acme-Search_26-09-01--exec-summary--2", []),
                          ("Acme-Search_26-09-01--exec-summary", ["exec-summary.md"])])

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
