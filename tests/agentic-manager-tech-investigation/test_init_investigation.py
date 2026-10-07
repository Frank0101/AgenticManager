# Unit tests for skills/agentic-manager-tech-investigation/scripts/init_investigation.py
# and save_example.py. The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The config's path is patched to the test's own config, in a temporary folder.
from datetime import date
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR), "scripts"))
import check_report  # noqa: E402
import init_investigation  # noqa: E402
import save_example  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import temp_output  # noqa: E402

TODAY = date(2026, 10, 5)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)

    def test_new_investigation(self):
        result = init_investigation.init("Acme-Search", today=TODAY)
        path = os.path.join(self.folder, "Acme-Search_26-10-05")
        self.assertEqual({k: result[k] for k in ("investigation", "investigation_dir", "follow_up", "files", "earlier")},
                         {"investigation": "Acme-Search_26-10-05", "investigation_dir": path,
                          "follow_up": False, "files": [], "earlier": []})
        self.assertEqual(os.listdir(path), ["ledgers.md"])
        with open(os.path.join(self.folder, "_examples", "README.md"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("## Index\n"))

    def test_skeleton_passes_the_ledger_check(self):
        from pathlib import Path
        path = Path(self.folder) / "ledgers.md"
        os.makedirs(self.folder, exist_ok=True)
        path.write_text(init_investigation.ledger_skeleton("Acme-Search"))
        self.assertEqual(check_report.check_ledger(path), ([], []))

    def test_follow_up_keeps_the_ledger(self):
        init_investigation.init("Acme-Search", today=TODAY)
        ledger = os.path.join(self.folder, "Acme-Search_26-10-05", "ledgers.md")
        with open(ledger, "w", encoding="utf-8") as f:
            f.write("work so far")
        result = init_investigation.init("Acme-Search", today=TODAY)
        self.assertTrue(result["follow_up"])
        self.assertEqual(result["files"], ["ledgers.md"])
        with open(ledger, encoding="utf-8") as f:
            self.assertEqual(f.read(), "work so far")

    def test_earlier_folders_and_examples(self):
        for name in ("Acme-Search_26-09-01", "2026-09-20--acme-search", "Acme-Search_26-08-01",
                     "Other_26-09-02", "_examples/Acme-Search_26-09-01--exec-summary",
                     "_examples/Acme-Search_26-09-01--exec-summary--2", "_examples/Other_26-09-02--long-analysis"):
            os.makedirs(os.path.join(self.folder, name))
        with open(os.path.join(self.folder, "_examples", "Acme-Search_26-09-01--exec-summary", "exec-summary.md"), "w") as f:
            f.write("x")
        result = init_investigation.init("Acme-Search", "exec-summary", today=TODAY)
        self.assertEqual(result["earlier"], ["2026-09-20--acme-search", "Acme-Search_26-09-01", "Acme-Search_26-08-01"])
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


class SaveExampleTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=TODAY)
        self.source = os.path.join(self.folder, "Acme-Search_26-10-05")
        files = {"Acme-Search_Report.md": "![Map](architecture-as-is.svg)\n[Ledger](ledgers.md#f01)\n"
                                          "[Web](https://example.com) [Missing](gone.md)\n",
                 "architecture-as-is.svg": "<svg/>", "mermaids.md": "unlinked",
                 "exec-summary.md": "Summary. [Full report](Acme-Search_Report.md)\n"}
        for name, text in files.items():
            with open(os.path.join(self.source, name), "w", encoding="utf-8") as f:
                f.write(text)

    def test_copies_linked_files_and_indexes_newest_first(self):
        first = save_example.save("Acme-Search_26-10-05", "Acme-Search_Report.md", "long-analysis", "Clear roadmap.")
        self.assertEqual(sorted(first["files"]), ["Acme-Search_Report.md", "architecture-as-is.svg", "ledgers.md"])
        second = save_example.save("Acme-Search_26-10-05", "exec-summary.md", "exec-summary", "Tight summary.")
        self.assertEqual(sorted(second["files"]), ["Acme-Search_Report.md", "architecture-as-is.svg",
                                                   "exec-summary.md", "ledgers.md"])
        third = save_example.save("Acme-Search_26-10-05", "exec-summary.md", "exec-summary", "Revised.")
        self.assertTrue(third["example"].endswith("Acme-Search_26-10-05--exec-summary--2"))
        with open(os.path.join(self.folder, "_examples", "README.md"), encoding="utf-8") as f:
            index = f.read().split("## Index\n", 1)[1]
        self.assertEqual(index.strip().splitlines(), [
            "- [Acme-Search_26-10-05--exec-summary--2/exec-summary.md]"
            "(Acme-Search_26-10-05--exec-summary--2/exec-summary.md) — Revised.",
            "- [Acme-Search_26-10-05--exec-summary/exec-summary.md]"
            "(Acme-Search_26-10-05--exec-summary/exec-summary.md) — Tight summary.",
            "- [Acme-Search_26-10-05--long-analysis/Acme-Search_Report.md]"
            "(Acme-Search_26-10-05--long-analysis/Acme-Search_Report.md) — Clear roadmap.",
        ])

    def test_refusals(self):
        cases = [("missing.md", "exec-summary", "Note."), ("exec-summary.md", "Exec Summary", "Note."),
                 ("exec-summary.md", "exec-summary", " "), ("exec-summary.md", "exec-summary", "a\nb")]
        for document, wanted, note in cases:
            with self.subTest(document=document, wanted=wanted, note=note):
                with self.assertRaises(SystemExit):
                    save_example.save("Acme-Search_26-10-05", document, wanted, note)


if __name__ == "__main__":
    unittest.main()
