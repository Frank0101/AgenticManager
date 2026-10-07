# Unit tests for skills/agentic-manager-tech-investigation/scripts/make_summary.py.
# The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The config's path is patched to the test's own config, in a temporary folder.
import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR), "scripts"))
import make_summary  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import INVESTIGATION, LEDGER, temp_output, words  # noqa: E402


class MakeSummaryTest(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.join(temp_output(self), INVESTIGATION)
        os.makedirs(self.folder)
        for name, text in (("ledgers.md", LEDGER), ("Acme-Search_Report.md", "# Acme search\n")):
            with open(os.path.join(self.folder, name), "w", encoding="utf-8") as f:
                f.write(text)

    def make(self, data, wanted="exec-summary"):
        with open(os.path.join(self.folder, f"{wanted}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        return make_summary.make_summary(INVESTIGATION, wanted)

    def test_frame_around_a_free_body(self):
        body = ["**Search API** is merged [F01](ledger:F01).", "## Next\n\n- Publish job\n- Evaluation",
                "| Area | State |\n| --- | --- |\n| API | Merged |"]
        result = self.make({"title": "Acme search", "max_words": 100, "body": body})
        with open(result["path"], encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("# Acme search\n\n**Search API** is merged "
                                        "[F01](ledgers.md#f01--search-api-is-merged)."))
        self.assertIn("## Next\n\n- Publish job", text)
        self.assertTrue(text.endswith("\n\nFull report: [Acme-Search_Report.md](Acme-Search_Report.md)\n"))
        self.assertEqual(result["words"], 13)
        self.assertTrue(result["path"].endswith("exec-summary.md"))

    def test_without_title_or_limit(self):
        result = self.make({"body": [words(500)]}, "slack-update")
        with open(result["path"], encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("word word"))

    def test_problems(self):
        # name: (exec-summary.json, expected in the problems)
        cases = [
            ("over the limit", {"max_words": 100, "body": [words(101)]}, "101 words, over the 100 asked for"),
            ("bad limit", {"max_words": "100", "body": ["Text."]}, "max_words"),
            ("empty body", {"body": []}, "needs a list"),
            ("own title heading", {"body": ["# Title\n\nText."]}, "no # heading"),
            ("unknown ledger ID", {"body": ["See [F09](ledger:F09)."]}, "ledger:F09"),
        ]
        for name, data, expected in cases:
            with self.subTest(name):
                with self.assertRaises(SystemExit) as raised:
                    self.make(data)
                self.assertIn(expected, str(raised.exception))
                self.assertFalse(os.path.exists(os.path.join(self.folder, "exec-summary.md")))

    def test_needs_the_full_report_and_a_format_label(self):
        with self.assertRaises(SystemExit):
            self.make({"body": ["Text."]}, "Exec Summary")
        os.remove(os.path.join(self.folder, "Acme-Search_Report.md"))
        with self.assertRaises(SystemExit) as raised:
            self.make({"body": ["Text."]})
        self.assertIn("write it first", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
