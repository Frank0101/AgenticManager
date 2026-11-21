"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/read_notes.py.
Run as a script, it has end-to-end tests in test_e2e_init.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The vault is a temporary folder of the test's own; the notes read go to the
prep's _raw folder, in the test's output folder, and the task to the working
folder, in the test's own system temporary folder.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import read_notes  # noqa: E402
import reading  # noqa: E402
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

    def test_gather(self):
        # The period's journals that link the person by a confirmed link,
        # by day, then the person's pages, numbered from 1 in one list, each
        # with its file's link; never a page about someone else.
        material = read_notes.gather(PREP)
        self.assertEqual({key: material[key] for key in ("empty", "journal_notes", "pages")},
                         {"empty": False, "journal_notes": 3, "pages": ["Jane"]})
        august, september = (str(Path(self.graph, "journals", name))
                             for name in ("2026_08_20.md", "2026_09_02.md"))
        self.assertEqual([(item["number"], item["date"], item["link"]) for item in material["content"]["items"]],
                         [(1, "2026-08-20", august), (2, "2026-08-20", august), (3, "2026-09-02", september),
                          (4, None, str(Path(self.graph, "pages", "Jane.md")))])
        self.assertEqual(material["content"]["items"][3]["text"],
                         "- Moved to the payments team in the summer")

    def test_until_today(self):
        # A note written after the period, such as before a calibration,
        # stays out of the prep unless start runs with --until-today, which
        # records that the notes run to today; a note dated after today
        # isn't one yet.
        for name, text in [("2026_11_12.md", "- [[Jane]] calibration prep"),
                           ("2999_01_01.md", "- [[Jane]] not written yet")]:
            with open(os.path.join(self.graph, "journals", name), "w", encoding="utf-8") as f:
                f.write(text)

        def dates():
            return [item["date"] for item in read_notes.gather(PREP)["content"]["items"]]
        self.assertNotIn("2026-11-12", dates())
        with mock.patch("sys.stdout"):
            read_notes.main(["start", "--prep", PREP, "--until-today"])
        with open(os.path.join(self.folder, PREP, "person.json"), encoding="utf-8") as f:
            self.assertEqual(
                json.load(f)["notes_end"], date.today().isoformat())
        self.assertIn("2026-11-12", dates())
        self.assertNotIn("2999-01-01", dates())

    def test_runs_the_task_then_takes_the_summary(self):
        # start writes the notes, numbered, to _raw and the task to the
        # working folder, saying how the notes write the person; submit
        # turns each point's cites into the day and link of the notes, most
        # recent first, a page, undated, backing only context.
        started = reading.start(read_notes.SOURCE, PREP)
        self.assertEqual(
            (started["journal_notes"], started["pages"]), (3, ["Jane"]))
        name, path = started["task"].split(": ", 1)
        self.assertEqual((name, path), ("Task notes", os.path.join(
            tempfile.gettempdir(), "perf-review-preps", "Jane-Doe_26-11-10", "notes", "task.md")))
        with open(path, encoding="utf-8") as f:
            task = f.read()
        for expected in ("# Read a manager's notes about a person", "## The person\n\nJane Doe", "- Teamwork: ",
                         "jira_ticket.py --key", "never one per mention",
                         "The notes write Jane Doe as [[Jane]] or [[Jane Promotion]], or as a tag, such as #Jane.",
                         "### Note 1, 2026-08-20\n\n- Planning sync", "### Note 3, 2026-09-02",
                         "### Note 4, page Jane\n\n- Moved to the payments team", "submit --prep Jane-Doe_26-11-10"):
            self.assertIn(expected, task)
        with open(os.path.join(self.folder, PREP, "_raw", "notes_items.json"), encoding="utf-8") as f:
            self.assertEqual([item["number"]
                             for item in json.load(f)["items"]], [1, 2, 3, 4])
        august, september = (str(Path(self.graph, "journals", name))
                             for name in ("2026_08_20.md", "2026_09_02.md"))
        page = str(Path(self.graph, "pages", "Jane.md"))
        # Notes 1 and 2 are of one journal day, so they share a link: a point
        # citing both has that one evidence.
        summary = {"going_well": [{"point": "Presented the migration to the team", "values": ["Teamwork"],
                                   "cites": [1, 2]},
                                  {"point": "The promotion talk went well", "values": [], "cites": [3, 1]}],
                   "to_improve": [], "context": [{"point": "Moved to payments", "cites": [4]}]}
        with self.assertRaisesRegex(SystemExit, "must each be of a day the source was read on(.|\n)*a page, which has no "
                                    "day, backs only a context point"):
            reading.submit(read_notes.SOURCE, PREP, {**summary, "going_well": [
                {**summary["going_well"][0], "cites": [4]}]})
        with self.assertRaisesRegex(SystemExit, "must each be the number of what it rests on, 1 to 4(.|\n)*Input, on stdin"):
            reading.submit(read_notes.SOURCE, PREP, {**summary, "going_well": [
                {**summary["going_well"][0], "cites": [5]}]})
        self.assertFalse(os.path.exists(
            os.path.join(self.folder, PREP, "notes.json")))
        submitted = reading.submit(read_notes.SOURCE, PREP, summary)
        with open(submitted["path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"going_well": [
                {"point": "The promotion talk went well", "values": [],
                 "evidence": [{"date": "2026-09-02", "link": september}, {"date": "2026-08-20", "link": august}]},
                {"point": "Presented the migration to the team", "values": ["Teamwork"],
                 "evidence": [{"date": "2026-08-20", "link": august}]}],
                "to_improve": [], "context": [{"point": "Moved to payments",
                                               "evidence": [{"date": None, "link": page}]}]})

    def test_no_notes(self):
        # With nothing to read, start records the empty summary at once.
        for folder in ("journals", "pages"):
            for name in os.listdir(os.path.join(self.graph, folder)):
                os.remove(os.path.join(self.graph, folder, name))
        done = reading.start(read_notes.SOURCE, PREP)
        self.assertNotIn("task", done)
        with open(done["path"], encoding="utf-8") as f:
            self.assertEqual(
                json.load(f), {"going_well": [], "to_improve": [], "context": []})

    def test_refuses_what_it_cant_take(self):
        with self.assertRaisesRegex(SystemExit, "aren't listed yet: run .* start --prep"):
            reading.submit(read_notes.SOURCE, PREP, {
                           "going_well": [], "to_improve": [], "context": []})
        reading.start(read_notes.SOURCE, PREP)
        with self.assertRaisesRegex(SystemExit, "must have the parts going_well, to_improve, context(.|\n)*python3 read_notes.py submit"):
            reading.submit(read_notes.SOURCE, PREP, {"going_well": []})


if __name__ == "__main__":
    unittest.main()
