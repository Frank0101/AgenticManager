"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/read_notes.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The vault is a temporary folder, and the system's temporary folder, where the
notes' working folder goes, the test's own.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import read_notes  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, temp_output, write_prep  # noqa: E402

# A journal of the prep's period, 10/08/2026 to 10/11/2026, which links Jane,
# as [[Jane]] or as a tag, whatever its case, and other people.
JOURNAL = """- Planning sync
\t- [[Sam]] set up the agenda
\t- [[Jane]] presented the migration, great questions
\t\t- the team asked for the slides
\t\t- [[Jane]] shared them right after
- #jane didn't flag the delay until asked
\t- the second time this month
- [[Sam]] on leave
"""
GOING_WELL = {"part": "going_well", "point": "Presented the migration to the team",
              "value": "Teamwork", "date": "2026-08-20"}
TO_IMPROVE = {"part": "to_improve", "point": "Didn't flag a delay until asked",
              "value": None, "date": "2026-08-20"}


class ReadNotesTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, notes=None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        self.graph = os.path.join(self.root, "graph")
        for folder, name, text in [("journals", "2026_08_20.md", JOURNAL),
                                   ("journals", "2026_07_01.md",
                                    "- [[Jane]] before the period"),
                                   ("journals", "2026_09_02.md",
                                    "- [[Jane promotion]] talk went well"),
                                   ("journals", "notes.md",
                                    "- [[Jane]] not a journal day"),
                                   ("pages", "Jane.md",
                                    "- Moved to the payments team in the summer"),
                                   ("pages", "Sam.md", "- [[Jane]] mentors Sam")]:
            os.makedirs(os.path.join(self.graph, folder), exist_ok=True)
            with open(os.path.join(self.graph, folder, name), "w", encoding="utf-8") as f:
                f.write(text)
        for target, attribute, value in ((read_notes, "graph_path", lambda: self.graph),
                                         (read_notes.tempfile, "gettempdir", lambda: self.root)):
            patcher = mock.patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_linking_blocks(self):
        # Each block that links the person, whatever its case, shown in the
        # block it sits in, siblings and all, with each line that links the
        # person marked; a block at the top shows itself. Two mentions in one
        # block are one note.
        self.assertEqual(read_notes.linking_blocks(JOURNAL, {"jane"}), [
            {"text": "- Planning sync\n\t- [[Sam]] set up the agenda\n"
             "→ \t- [[Jane]] presented the migration, great questions\n\t\t- the team asked for the slides\n"
             "→ \t\t- [[Jane]] shared them right after"},
            {"text": "→ - #jane didn't flag the delay until asked\n\t- the second time this month"}])

    def test_journal_day(self):
        for title, expected in [("2026_08_20", date(2026, 8, 20)), ("2026_02_30", None), ("notes", None)]:
            with self.subTest(title):
                self.assertEqual(read_notes.journal_day(title), expected)

    def test_gather(self):
        # The period's journals that link the person by a confirmed link, by
        # month, and the person's pages; never a page about someone else.
        material = read_notes.gather(PREP)
        self.assertEqual(sorted(material["months"]), ["2026-08", "2026-09"])
        self.assertEqual([note["date"] for note in material["months"]["2026-08"]], [
                         "2026-08-20", "2026-08-20"])
        self.assertEqual(material["months"]["2026-09"], [
            {"date": "2026-09-02", "text": "→ - [[Jane promotion]] talk went well"}])
        self.assertEqual(material["pages"], [
                         {"title": "Jane", "text": "- Moved to the payments team in the summer"}])

    def test_items_problems(self):
        # name: (the answer, the days of its notes, expected in its problems,
        # or None for none); no days is the pages' task.
        days, values = ["2026-08-20"], ["Teamwork", "Ownership"]
        context = {"part": "context", "point": "Moved team",
                   "value": None, "date": None}
        cases = [("valid", {"items": [GOING_WELL, TO_IMPROVE], "in_doubt": ["2026-08-20: x"]}, days, None),
                 ("none", {"items": [], "in_doubt": []}, days, None),
                 ("pages", {"items": [context], "in_doubt": []}, [], None),
                 ("not an object", [GOING_WELL], days,
                  'must be {"items": [...], "in_doubt": [...]}'),
                 ("no date", {"items": [{**GOING_WELL, "date": None}], "in_doubt": []}, days,
                  "date, None, must be the day of the note"),
                 ("a field missing", {"items": [{k: v for k, v in GOING_WELL.items() if k != "value"}],
                                      "in_doubt": []}, days, "must have the fields part, point, value, date"),
                 ("another day", {"items": [{**GOING_WELL, "date": "2026-08-21"}], "in_doubt": []}, days,
                  "must be the day of the note"),
                 ("a value not the company's", {"items": [{**GOING_WELL, "value": "Grit"}], "in_doubt": []},
                  days, "'Grit', must be one of the company's"),
                 ("a value on context", {"items": [{**context, "date": "2026-08-20", "value": "Teamwork"}],
                                         "in_doubt": []}, days, "context has none"),
                 ("a dated page item", {"items": [{**context, "date": "2026-08-20"}], "in_doubt": []}, [],
                  "null: pages have no date"),
                 ("going well from a page", {"items": [{**GOING_WELL, "date": None}], "in_doubt": []}, [],
                  "pages give only context"),
                 ("a point too long", {"items": [{**GOING_WELL, "point": "word " * 41}], "in_doubt": []}, days,
                  "at most 40 words")]
        for name, answer, task_days, expected in cases:
            with self.subTest(name):
                problems = read_notes.items_problems(
                    answer, values, task_days)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))

    def test_runs_the_tasks_then_merges(self):
        # start gathers, writes every month and the pages, and names the
        # merge task, which the last reading answer writes; the merge's submit
        # says finished, with what the reading tasks left out in doubt, as
        # they wrote it.
        started = read_notes.start(PREP)
        self.assertEqual(started["months"], ["2026-08", "2026-09"])
        lines = started["tasks"]
        self.assertEqual([line.split(": ")[0] for line in lines],
                         ["Task month:2026-08", "Task month:2026-09", "Task pages"])
        with open(lines[0].split(": ", 1)[1], encoding="utf-8") as f:
            task = f.read()
        for expected in ("# Read a month of a manager's notes", "## The person\n\nJane Doe", "- Teamwork: ",
                         "jira_ticket.py --key", "### 2026-08-20\n\n- Planning sync",
                         "submit --prep Jane-Doe_26-11-10 --task month:2026-08"):
            self.assertIn(expected, task)
        merge = started["merge"].split(": ", 1)[1]
        self.assertEqual(read_notes.submit(PREP, "month:2026-08", {"items": [GOING_WELL, TO_IMPROVE],
                                                                   "in_doubt": []}),
                         {"task": "month:2026-08", "items": 2})
        self.assertFalse(os.path.exists(merge))
        read_notes.submit(PREP, "month:2026-09",
                          {"items": [], "in_doubt": ["2026-09-02: a talk, no behaviour"]})
        read_notes.submit(PREP, "pages", {"items": [{"part": "context", "point": "Moved to payments",
                                                     "value": None, "date": None}], "in_doubt": []})
        with open(merge, encoding="utf-8") as f:
            text = f.read()
        self.assertIn('"point": "Moved to payments"', text)
        self.assertIn("- 2026-09-02: a talk, no behaviour", text)
        merged = {"going_well": [{"point": "Presented the migration to the team", "value": "Teamwork",
                                  "dates": ["2026-08-20"]}],
                  "to_improve": [], "context": ["Moved to payments"]}
        with self.assertRaisesRegex(SystemExit, "must each be a day a note was taken on"):
            read_notes.submit(PREP, "merge", {**merged, "going_well": [{**merged["going_well"][0],
                                                                        "dates": ["2026-09-03"]}]})
        # A note left out in doubt may become a point, with its day, when
        # another settles it; the merge lists it in promoted, and notes.json
        # holds only the summary.
        talk = {"point": "Gave a talk the team praised",
                "value": None, "dates": ["2026-09-02"]}
        summary = {**merged, "going_well": [*merged["going_well"], talk]}
        # A promoted line must be one left out in doubt, copied exactly; once
        # promoted, it is no longer listed as left out.
        promoted = {"line": "2026-09-02: a talk, no behaviour",
                    "settled_by": "the praise in August"}
        with self.assertRaisesRegex(SystemExit, "isn't one of the notes left out in doubt: copy it exactly"):
            read_notes.submit(PREP, "merge", {**summary, "promoted": [
                              {**promoted, "line": "2026-09-02: a talk"}]})
        submitted = read_notes.submit(
            PREP, "merge", {**summary, "promoted": [promoted]})
        with open(submitted["notes"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), summary)
        done = read_notes.finished(PREP)
        self.assertEqual((done["finished"], done["in_doubt"], done["promoted"]),
                         (True, [], [promoted]))
        self.assertTrue(done["correct"].endswith(
            "submit --prep Jane-Doe_26-11-10 --task merge"))

    def test_no_notes(self):
        # With nothing to read, start records the empty summary at once.
        for folder in ("journals", "pages"):
            for name in os.listdir(os.path.join(self.graph, folder)):
                os.remove(os.path.join(self.graph, folder, name))
        done = read_notes.start(PREP)
        self.assertEqual((done["finished"], done["in_doubt"]), (True, []))
        with open(done["notes"], encoding="utf-8") as f:
            self.assertEqual(
                json.load(f), {"going_well": [], "to_improve": [], "context": []})

    def test_every_protocol_file_is_filled(self):
        # A placeholder nothing fills would reach a subagent as {{name}}; the
        # shared parts reach every task that names them.
        for name in ("notes", "pages", "merge"):
            with self.subTest(name):
                text = read_notes.read_protocol(name)
                self.assertNotIn("{{", text)
                self.assertIn('never "he" or "she"', text)

    def test_refuses_what_it_cant_take(self):
        with self.assertRaisesRegex(SystemExit, "run .* start --prep"):
            read_notes.submit(PREP, "merge", {})
        read_notes.start(PREP)
        with self.assertRaisesRegex(SystemExit, "isn't a task of this prep"):
            read_notes.submit(PREP, "month:2025-01",
                              {"items": [], "in_doubt": []})
        with self.assertRaisesRegex(SystemExit, "must be the day of the note(.|\n)*The answer's shape"):
            read_notes.submit(PREP, "month:2026-08", {"items": [{**GOING_WELL, "date": "2026-08-21"}],
                                                      "in_doubt": []})


if __name__ == "__main__":
    unittest.main()
