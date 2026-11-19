"""Unit tests for skills/agentic-manager-perf-review-prep/scripts/read_slack.py.
The flow every reading shares is tested in test_read_notes.py; here, what is
Slack's: a task for each month, the items each lists and the ranges it
declares searched, which must cover its month, and the judge's task, which
merges every month's items into one numbered list.
Run with: python3 tests/run.py agentic-manager-perf-review-prep
"""

import json
import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
import read_slack  # noqa: E402
import reading  # noqa: E402
sys.path.insert(0, TEST_DIR)
from prep_fixture import PREP, temp_output, write_prep  # noqa: E402

PERIOD = {"2026-08": ("2026-08-10", "2026-08-31"), "2026-09": ("2026-09-01", "2026-09-30"),
          "2026-10": ("2026-10-01", "2026-10-31"), "2026-11": ("2026-11-01", "2026-11-10")}


def link(number):
    return f"https://acme.slack.com/archives/C1/p{number}"


def item(day, number, description="In a cross-team channel, posted the rollout plan; three people asked"):
    return {"date": day, "link": link(number), "description": description}


def searched(month, search=("sent", "mentioned"), pages=2):
    first, last = PERIOD[month]
    return [{"search": name, "from": first, "to": last, "pages": pages} for name in search]


def answer(month, *items):
    return {"searched": searched(month), "items": list(items)}


class ReadSlackTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        write_prep(self.folder, slack=None)

    def submit_months(self, answers):
        """Submits each month's answer; returns the last result."""
        result = None
        for month, given in answers.items():
            result = reading.submit(
                read_slack.SOURCE, PREP, given, f"month:{month}")
        return result

    def test_start_writes_a_task_for_each_month(self):
        # A task for each calendar month, the first and last clipped to the
        # period, its searches bounded by it, and the judge's task named, its
        # file not written until every month is in.
        started = reading.start(read_slack.SOURCE, PREP)
        self.assertEqual([line.split(": ")[0] for line in started["tasks"]],
                         [f"Task month:{month}" for month in PERIOD])
        self.assertTrue(started["judge"].startswith("Task slack: "))
        self.assertFalse(os.path.exists(started["judge"].split(": ", 1)[1]))
        with open(started["tasks"][0].split(": ", 1)[1], encoding="utf-8") as f:
            task = f.read()
        for expected in ("# Read a month of a person's Slack messages", "be inclusive",
                         "From 2026-08-10 to 2026-08-31", "`from:<@U012AB3CD> after:2026-08-09 before:2026-09-01`",
                         "exclude the day they name", "search the days one didn't reach again",
                         "read every thread that has replies to the end, with `slack_read_thread`, yourself and not through other agents, whoever started it",
                         "purely social or personal", "how the person answered",
                         "with no reply is listed only if it is itself a request",
                         "how the conversation ended", "up to 50 words",
                         "submit --prep Jane-Doe_26-11-10 --task month:2026-08"):
            self.assertIn(expected, task)
        self.assertNotIn("## The company's values", task)

    def test_the_last_month_writes_the_judge_task(self):
        # Every month's items go into one list by day, numbered from 1, a
        # conversation listed twice once; the declared ranges are kept with
        # them in _raw; the judge's task shows the list and the answer's shape.
        started = reading.start(read_slack.SOURCE, PREP)
        judge = started["judge"].split(": ", 1)[1]
        sept, aug = item(
            "2026-09-12", 2, "In the squad channel, Sam thanked Jane"), item("2026-08-20", 1)
        answers = {"2026-10": answer("2026-10", item("2026-10-03", 3)), "2026-09": answer("2026-09", sept, item("2026-09-02", 4)),
                   "2026-11": answer("2026-11"), "2026-08": answer("2026-08", aug, {**sept, "date": "2026-08-31"})}
        for month in list(answers)[:-1]:
            self.assertEqual(reading.submit(read_slack.SOURCE, PREP, answers[month], f"month:{month}"),
                             {"task": f"month:{month}", "items": len(answers[month]["items"])})
        self.assertFalse(os.path.exists(judge))
        last = reading.submit(read_slack.SOURCE, PREP,
                              answers["2026-08"], "month:2026-08")
        self.assertEqual(last["judge"], started["judge"])
        with open(os.path.join(self.folder, PREP, "_raw", "slack_items.json"), encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual([(entry["number"], entry["date"], entry["link"]) for entry in raw["items"]],
                         [(1, "2026-08-20", link(1)), (2, "2026-08-31", link(2)), (3, "2026-09-02", link(4)),
                          (4, "2026-10-03", link(3))])
        self.assertEqual(len(raw["searched"]), 8)
        with open(judge, encoding="utf-8") as f:
            text = f.read()
        for expected in ("# Judge what a person's Slack messages show", "## The company's values", "- Teamwork: ",
                         "1. 2026-08-20: In a cross-team channel", "2. 2026-08-31: In the squad channel, Sam thanked Jane",
                         "4. 2026-10-03:", "never one per mention", "had not been informed or involved beforehand",
                         "stopped, clarified or closed by someone else", "submit --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'",
                         '"cites": [3, 41]'):
            self.assertIn(expected, text)
        self.assertNotIn("slack_search_public", text)
        self.assertNotIn("--task", text.split("## Submit")[1])

    def test_nothing_listed_in_any_month_records_the_empty_summary(self):
        # With no conversation in any month, the last month's submit records
        # the empty summary and says its path; no judge task is written.
        started = reading.start(read_slack.SOURCE, PREP)
        months = list(PERIOD)
        for month in months[:-1]:
            self.assertNotIn("path", reading.submit(
                read_slack.SOURCE, PREP, answer(month), f"month:{month}"))
        last = reading.submit(read_slack.SOURCE, PREP,
                              answer(months[-1]), f"month:{months[-1]}")
        self.assertNotIn("judge", last)
        with open(last["path"], encoding="utf-8") as f:
            self.assertEqual(
                json.load(f), {"going_well": [], "to_improve": [], "context": []})
        self.assertFalse(os.path.exists(started["judge"].split(": ", 1)[1]))
        with open(os.path.join(self.folder, PREP, "_raw", "slack_items.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["items"], [])

    def test_the_judge_cites_items_by_number(self):
        # The points cite the numbers of the merged list, a pattern all of
        # its own; the script adds each one's day and link, the most recent
        # first.
        answers = {"2026-08": answer("2026-08", item("2026-08-20", 1)), "2026-09": answer("2026-09", item("2026-09-02", 2)),
                   "2026-10": answer("2026-10"), "2026-11": answer("2026-11")}
        reading.start(read_slack.SOURCE, PREP)
        self.submit_months(answers)
        summary = {"going_well": [{"point": "Helped colleagues with the rollout, as they thanked Jane for", "values": ["Teamwork"],
                                   "cites": [1, 2]}], "to_improve": [], "context": []}
        with self.assertRaisesRegex(SystemExit, "must each be the number of what it rests on, 1 to 2(.|\n)*Input, on stdin"):
            reading.submit(read_slack.SOURCE, PREP, {
                           **summary, "going_well": [{**summary["going_well"][0], "cites": [3]}]})
        submitted = reading.submit(read_slack.SOURCE, PREP, summary)
        with open(submitted["path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"going_well": [{**{key: value for key, value in summary["going_well"][0].items()
                                                               if key != "cites"},
                                                            "evidence": [{"date": "2026-09-02", "link": link(2)},
                                                                         {"date": "2026-08-20", "link": link(1)}]}],
                                            "to_improve": [], "context": []})

    def test_a_month_that_leaves_days_unsearched_is_refused(self):
        # The error names the days to search and shows the part's shape, the
        # ranges declared and a command to copy; nothing is written.
        reading.start(read_slack.SOURCE, PREP)
        given = {"searched": [{**searched("2026-09")[0], "to": "2026-09-20"}, searched("2026-09")[1]],
                 "items": [item("2026-09-02", 1)]}
        with self.assertRaisesRegex(SystemExit, "the sent search doesn't cover 2026-09-21 to 2026-09-30(.|\n)*"
                                    'python3 read_slack.py submit --prep Jane-Doe_26-11-10 --task month:2026-09(.|\n)*"searched": \\['):
            reading.submit(read_slack.SOURCE, PREP, given, "month:2026-09")
        self.assertFalse(reading.answered(
            read_slack.SOURCE, PREP, "month:2026-09"))

    def test_refuses_what_it_cant_take(self):
        reading.start(read_slack.SOURCE, PREP)
        link_none = {**item("2026-09-02", 1), "link": None}
        cases = [("an item with no link", "month:2026-09", answer("2026-09", link_none), "link, None, must be the address"),
                 ("a day of another month", "month:2026-09", answer("2026-09", item("2026-10-02", 1)),
                  "must be the day of what it comes from"),
                 ("not the shape", "month:2026-09",
                  {"items": []}, 'must be {"searched": \\[...\\], "items": \\[...\\]}'),
                 ("not a task of the prep", "month:2025-01",
                  answer("2026-09"), "isn't a task of this prep"),
                 ("the judge before the months", None, {"going_well": [], "to_improve": [], "context": []},
                  "aren't listed yet(.|\n)*every part before the judge's")]
        for name, task, given, expected in cases:
            with self.subTest(name), self.assertRaisesRegex(SystemExit, expected):
                reading.submit(read_slack.SOURCE, PREP, given, task)

    def test_searched_problems(self):
        # name: (the ranges searched, expected in its problems, or None for
        # none): each of the two searches must cover every day of the month,
        # September here.
        first, last = PERIOD["2026-09"]
        days = common.days_between(first, last)

        def sent(start, end, pages=2):
            return {"search": "sent", "from": start, "to": end, "pages": pages}

        def mentioned(start, end, pages=1):
            return {"search": "mentioned", "from": start, "to": end, "pages": pages}
        cases = [("covered", searched("2026-09"), None),
                 ("several ranges", [sent(first, "2026-09-10"), sent("2026-09-11", "2026-09-20"),
                                     sent("2026-09-15", last), mentioned(first, last)], None),
                 ("a gap", [sent(first, "2026-09-10"), sent("2026-09-15", last), mentioned(first, last)],
                  "the sent search doesn't cover 2026-09-11 to 2026-09-14: search those days, and add them to"),
                 ("two gaps", [sent(first, "2026-09-10"), sent("2026-09-12", "2026-09-29"), mentioned(first, last)],
                  "doesn't cover 2026-09-11, 2026-09-30"),
                 ("a missing search", [
                  sent(first, last)], f"the mentioned search doesn't cover {first} to {last}"),
                 ("a range outside the month", [sent("2026-08-25", last), mentioned(first, last)],
                  "searched entry 1's range, 2026-08-25 to 2026-09-30, must be days of the month"),
                 ("a range backwards", [sent(last, first), mentioned(
                     first, last)], "the first not after the last"),
                 ("no pages", [sent(first, last, 0), mentioned(
                     first, last)], "searched entry 1 must be"),
                 ("pages not a number", [{**sent(first, last), "pages": "2"}, mentioned(
                     first, last)], "searched entry 1 must be"),
                 ("an unknown search", [{**sent(first, last), "search": "all"}, mentioned(first, last)],
                  "searched entry 1 must be"),
                 ("a field missing", [{"search": "sent", "from": first, "to": last}, mentioned(first, last)],
                  "searched entry 1 must be"),
                 ("not a list", {"sent": 1}, '"searched" must be a list of'),
                 ("nothing searched", [], "the sent search doesn't cover")]
        for name, given, expected in cases:
            with self.subTest(name):
                problems = read_slack.searched_problems(given, days)
                if expected is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertIn(expected, " ".join(problems))


if __name__ == "__main__":
    unittest.main()
