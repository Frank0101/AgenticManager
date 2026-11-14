"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/read_notes.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The vault is a temporary folder of the test's own; the readers' answers go
to the prep's _raw folder, in the test's output folder, and the tasks to the
working folder, in the test's own system temporary folder.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import read_notes  # noqa: E402
import reading  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import DELAY, PREP, PRESENTED, temp_output, write_prep  # noqa: E402

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
        patcher = mock.patch.object(
            read_notes, "graph_path", lambda: self.graph)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_linking_blocks(self):
        # Each block that links the person, whatever its case, shown in the
        # block it sits in, siblings and all, as written; a block at the top
        # shows itself. Two mentions in one block are one note.
        self.assertEqual(read_notes.linking_blocks(JOURNAL, {"jane"}), [
            {"text": "- Planning sync\n\t- [[Sam]] set up the agenda\n"
             "\t- [[Jane]] presented the migration, great questions\n\t\t- the team asked for the slides\n"
             "\t\t- [[Jane]] shared them right after"},
            {"text": "- #jane didn't flag the delay until asked\n\t- the second time this month"}])

    def test_journal_day(self):
        for title, expected in [("2026_08_20", date(2026, 8, 20)), ("2026_02_30", None), ("notes", None)]:
            with self.subTest(title):
                self.assertEqual(read_notes.journal_day(title), expected)

    def test_gather(self):
        # The period's journals that link the person by a confirmed link, by
        # month, and the person's pages, each with its file's link; never a
        # page about someone else.
        material = read_notes.gather(PREP)
        self.assertEqual({key: material[key] for key in ("journal_notes", "months", "pages", "tasks")},
                         {"journal_notes": 3, "months": ["2026-08", "2026-09"], "pages": ["Jane"],
                          "tasks": ["month:2026-08", "month:2026-09", "pages"]})
        content = material["content"]
        self.assertEqual([note["date"] for note in content["months"]["2026-08"]], [
                         "2026-08-20", "2026-08-20"])
        self.assertEqual(content["months"]["2026-09"], [
            {"date": "2026-09-02", "link": Path(self.graph, "journals", "2026_09_02.md").as_uri(),
             "text": "- [[Jane promotion]] talk went well"}])
        self.assertEqual(content["pages"], [
                         {"title": "Jane", "text": "- Moved to the payments team in the summer",
                          "link": Path(self.graph, "pages", "Jane.md").as_uri()}])

    def test_runs_the_tasks_then_merges(self):
        # start gathers, writes every month and the pages, each saying how
        # the notes write the person and each note numbered, in the working
        # folder, and names the merge task, which the last reading answer
        # writes, every synopsis with its note's day and link; each answer
        # is kept in _raw, a month in months; the merge's summary is kept
        # most recent first, and its submit says finished, with what it left
        # out in doubt.
        started = reading.start(read_notes.SOURCE, PREP)
        self.assertEqual(started["months"], ["2026-08", "2026-09"])
        lines = started["tasks"]
        self.assertEqual([line.split(": ")[0] for line in lines],
                         ["Task month:2026-08", "Task month:2026-09", "Task pages"])
        self.assertEqual(lines[0].split(": ", 1)[1], os.path.join(
            tempfile.gettempdir(), "perf-review-preps", "Jane-Doe_26-11-10", "notes", "month", "2026-08", "task.md"))
        with open(lines[0].split(": ", 1)[1], encoding="utf-8") as f:
            task = f.read()
        for expected in ("# Read a month of a manager's notes", "## The person\n\nJane Doe",
                         "jira_ticket.py --key",
                         "The notes write Jane Doe as [[Jane]] or [[Jane Promotion]], or as a tag, such as #Jane.",
                         "### Note 1, 2026-08-20\n\n- Planning sync",
                         "### Note 2, 2026-08-20", "about 60 words",
                         "submit --prep Jane-Doe_26-11-10 --task month:2026-08"):
            self.assertIn(expected, task)
        self.assertNotIn("- Teamwork: ", task)
        merge = started["merge"].split(": ", 1)[1]
        self.assertEqual(reading.submit(read_notes.SOURCE, PREP, "month:2026-08", {"items": [DELAY, PRESENTED]}),
                         {"task": "month:2026-08", "items": 2})
        self.assertFalse(os.path.exists(merge))
        reading.submit(read_notes.SOURCE, PREP, "month:2026-09",
                       {"items": [{"note": 1, "synopsis": "The promotion talk went well"}]})
        reading.submit(read_notes.SOURCE,
                       PREP, "pages", {"items": [{"note": 1, "synopsis": "Moved to payments"}]})
        raw = os.path.join(self.folder, PREP, "_raw", "notes")
        self.assertEqual(sorted(os.path.relpath(os.path.join(where, name), raw)
                                for where, _, names in os.walk(raw) for name in names),
                         [os.path.join("months", "2026-08.json"), os.path.join("months", "2026-09.json"), "pages.json"])
        with open(merge, encoding="utf-8") as f:
            text = f.read()
        august = Path(self.graph, "journals", "2026_08_20.md").as_uri()
        page = Path(self.graph, "pages", "Jane.md").as_uri()
        for expected in ("- Teamwork: ", f'{{"date": "2026-08-20", "link": "{august}", "synopsis": "Presented',
                         f'{{"date": "2026-08-20", "link": "{august}", "synopsis": "Didn\'t flag',
                         f'{{"date": null, "link": "{page}", "synopsis": "Moved'):
            self.assertIn(expected, text)
        self.assertLess(text.index("Presented the migration"),
                        text.index("Didn't flag"))
        september = Path(self.graph, "journals", "2026_09_02.md").as_uri()
        summary = {"going_well": [{"point": "Presented the migration to the team", "values": ["Teamwork"],
                                   "dates": ["2026-08-20"], "links": [august]},
                                  {"point": "The promotion talk went well", "values": [],
                                   "dates": ["2026-08-20", "2026-09-02"], "links": [september]}],
                   "to_improve": [], "context": [{"point": "Moved to payments", "dates": [], "links": [page]}]}
        with self.assertRaisesRegex(SystemExit, "must each be a day the source was read on"):
            reading.submit(read_notes.SOURCE, PREP, "merge", {**summary, "in_doubt": [], "going_well": [
                {**summary["going_well"][0], "dates": ["2026-09-03"]}]})
        with self.assertRaisesRegex(SystemExit, "must each be the link of something read"):
            reading.submit(read_notes.SOURCE, PREP, "merge", {**summary, "in_doubt": [], "going_well": [
                {**summary["going_well"][0], "links": [Path(self.graph, "journals", "2026_08_21.md").as_uri()]}]})
        with self.assertRaisesRegex(SystemExit, '"in_doubt" must be a list of texts'):
            reading.submit(read_notes.SOURCE, PREP, "merge", summary)
        doubts = ["2026-08-20: Didn't flag a delay, but only once and minor",
                  "2026-09-02: Talked about a promotion", "Jane: a page note"]
        submitted = reading.submit(read_notes.SOURCE,
                                   PREP, "merge", {**summary, "in_doubt": doubts})
        with open(submitted["notes"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {**summary, "going_well": [
                {**summary["going_well"][1], "dates": ["2026-09-02", "2026-08-20"]}, summary["going_well"][0]]})
        self.assertFalse(os.path.exists(os.path.join(raw, "merge.json")))
        done = reading.finished(read_notes.SOURCE, PREP)
        self.assertEqual((done["finished"], done["in_doubt"]),
                         (True, [doubts[2], doubts[1], doubts[0]]))
        self.assertTrue(done["correct"].endswith(
            "submit --prep Jane-Doe_26-11-10 --task merge"))
        # remerge writes the merge task again from the kept synopses, with
        # the merge's protocol as it is now, and drops the earlier answer.
        with mock.patch.object(reading, "read_protocol", lambda name: "# A changed merge"):
            again = reading.remerge(read_notes.SOURCE, PREP)
        self.assertEqual(again["merge"], started["merge"])
        with open(merge, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("# A changed merge"))
        self.assertIn('"synopsis": "Moved to payments"', text)
        self.assertFalse(reading.answered(read_notes.SOURCE, PREP, "merge"))

    def test_no_notes(self):
        # With nothing to read, start records the empty summary at once.
        for folder in ("journals", "pages"):
            for name in os.listdir(os.path.join(self.graph, folder)):
                os.remove(os.path.join(self.graph, folder, name))
        done = reading.start(read_notes.SOURCE, PREP)
        self.assertEqual((done["finished"], done["in_doubt"]), (True, []))
        with open(done["notes"], encoding="utf-8") as f:
            self.assertEqual(
                json.load(f), {"going_well": [], "to_improve": [], "context": []})

    def test_refuses_what_it_cant_take(self):
        with self.assertRaisesRegex(SystemExit, "run .* start --prep"):
            reading.submit(read_notes.SOURCE, PREP, "merge", {})
        with self.assertRaisesRegex(SystemExit, "isn't gathered: run .* start"):
            read_notes.main(["finished", "--prep", PREP])
        reading.start(read_notes.SOURCE, PREP)
        with self.assertRaisesRegex(SystemExit, "month:2026-08, month:2026-09, pages not answered yet"):
            reading.remerge(read_notes.SOURCE, PREP)
        with self.assertRaisesRegex(SystemExit, "isn't a task of this prep"):
            reading.submit(read_notes.SOURCE, PREP,
                           "month:2025-01", {"items": []})
        with self.assertRaisesRegex(SystemExit, "missing 2(.|\n)*The answer's shape"):
            reading.submit(read_notes.SOURCE, PREP,
                           "month:2026-08", {"items": [PRESENTED]})


if __name__ == "__main__":
    unittest.main()
