"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/set_work_impact.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import os
import re
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import set_work_impact  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import BILLING_EVIDENCE, DATA, PREP, WORK_IMPACT_CONTENT, temp_output, write_prep  # noqa: E402

BILLING, RETIREMENT = WORK_IMPACT_CONTENT["initiatives"]


class SetWorkImpactTest(unittest.TestCase):
    def test_set_work_impact(self):
        # name: (the value, what is written, or the problem expected):
        # written most recent first, by the latest day of each initiative's
        # evidence, those with none dated last, once every citation is one of
        # data.json's points or items; refused, writing nothing, with every
        # problem and the input.
        undated = {"title": "Promotion case", "impact": "The manager has a promotion case to put forward.",
                   "paragraph": "Jane prepared a promotion case.", "evidence": ["C1"]}
        long = " ".join(
            ["word"] * (common.MAX_WORDS["work_impact"] + 1))
        long_line = " ".join(
            ["word"] * (common.MAX_WORDS["work_impact_line"] + 1))
        cases = [("as written", WORK_IMPACT_CONTENT, WORK_IMPACT_CONTENT),
                 ("given oldest first", {"initiatives": [
                  RETIREMENT, BILLING]}, WORK_IMPACT_CONTENT),
                 ("an undated one first", {"initiatives": [undated, RETIREMENT, BILLING]},
                  {"initiatives": [BILLING, RETIREMENT, undated]}),
                 ("no initiative", {"initiatives": []},
                  "with at least one initiative"),
                 ("a field missing", {"initiatives": [{"title": "Billing", "evidence": ["G3"]}]},
                  "initiative 1 must be {"),
                 ("a citation data.json doesn't hold", {"initiatives": [{**BILLING, "evidence": ["G9"]}]},
                  "names G9, which the brief doesn't hold"),
                 ("a citation twice", {"initiatives": [{**BILLING, "evidence": ["G3", "G3"]}]},
                  "names an item more than once"),
                 ("no evidence", {"initiatives": [
                  {**BILLING, "evidence": []}]}, "evidence is empty"),
                 ("an id in the paragraph", {"initiatives": [{**BILLING, "paragraph": "Jane did it, as G3 says."}]},
                  "paragraph names G3"),
                 ("a paragraph too long", {"initiatives": [{**BILLING, "paragraph": long}]},
                  f"cut it to about {common.WORDS['work_impact']}"),
                 ("no impact line", {"initiatives": [
                  {**BILLING, "impact": " "}]}, "impact is empty"),
                 ("an id in the impact line", {"initiatives": [{**BILLING, "impact": "As G3 says, it helped."}]},
                  "impact names G3"),
                 ("an impact line too long", {"initiatives": [{**BILLING, "impact": long_line}]},
                  f"cut it to about {common.WORDS['work_impact_line']}"),
                 ("two with one title", {"initiatives": [BILLING, {**RETIREMENT, "title": BILLING["title"]}]},
                  "names another initiative too")]
        for name, value, expected in cases:
            with self.subTest(name):
                folder = temp_output(self)
                write_prep(folder, work_impact_content=None, report=False)
                path = os.path.join(folder, PREP, common.WORK_IMPACT_CONTENT)
                if isinstance(expected, dict):
                    self.assertEqual(common.read_json(
                        set_work_impact.set_work_impact(PREP, value)), expected)
                    continue
                with self.assertRaisesRegex(SystemExit, f"{re.escape(expected)}(.|\n)*"
                                            "python3 set_work_impact.py --prep(.|\n)*END_OF_INPUT"):
                    set_work_impact.set_work_impact(PREP, value)
                self.assertFalse(os.path.exists(path))

    def test_every_kind_of_evidence(self):
        # A point, an epic, a pull request and a Notion page are all cited
        # by what the brief gives: an id or a link.
        index = common.work_evidence(DATA)
        self.assertEqual([index[item]["kind"] for item in BILLING_EVIDENCE],
                         ["epic", "pr", "page", "point", "point"])


if __name__ == "__main__":
    unittest.main()
