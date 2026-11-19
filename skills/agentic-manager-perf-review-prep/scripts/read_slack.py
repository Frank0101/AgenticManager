"""Reads a prep's person's Slack messages: start writes a task for each month, submit takes each month's items, then the judge's summary.

Slack is reached only through its MCP, which a subagent can call and a script
can't, so nothing is gathered ahead: a reader for each month searches it and
lists every conversation, judging nothing, as a month alone can't show a
pattern. A search is long, so a reader can stop early and sample: it declares
the ranges it searched, and an answer that leaves a day of its month
unsearched is refused. One judge then sees every month's items in one list.
"""
import os
from datetime import date, timedelta

from common import PERSON, SLACK, day_ranges, days_between, months_of, prep_dir, read_json
import reading

SEARCHES = ("sent", "mentioned")
SEARCHED_SHAPE = ('{"search": "sent" | "mentioned", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", '
                  '"pages": <pages read, 1 or more>}')
READER_ANSWER = """{"searched": [
   {"search": "sent", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "pages": 14},
   {"search": "mentioned", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "pages": 3}],
 "items": [{"date": "YYYY-MM-DD", "link": "https://<workspace>.slack.com/archives/<channel>/p<message>",
            "description": "In #<channel>, a cross-team channel, posted the rollout plan; three people asked..."}]}"""
READER_HELP = """\
  searched    every range of days you searched, one entry per range of each of the two searches, with the pages you read: for each search, together they cover every day of the month
  items       every conversation that could be part of a pattern, each {"date": ..., "link": ..., "description": ...}, the link copied exactly as the search gives it"""
JUDGE_ANSWER = """{"going_well": [{"point": "Posted the rollout plan in a cross-team channel, which prompted three follow-up questions",
                "values": ["<each company value it clearly shows or calls for, at most 2>"], "cites": [3, 41]}],
 "to_improve": [{"point": "...", "values": [], "cites": [12]}],
 "context": [{"point": "...", "cites": [7]}]}"""


def parts(prep):
    """{task: {start, end}}: a task for each month of the period, such as
    month:2026-09, its first and last day, within the period."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    months = months_of(date.fromisoformat(
        person["start"]), date.fromisoformat(person["end"]))
    return {f"month:{month}": days for month, days in months.items()}


def reader_task_text(prep, task, part):
    """(protocol, body) of the task of a month: the person's Slack account and
    the filters that bound its searches, Slack's after: and before:
    excluding the day they name."""
    account = read_json(os.path.join(prep_dir(prep), PERSON))[
        "sources"]["slack-mcp"]
    after = date.fromisoformat(part["start"]) - timedelta(days=1)
    before = date.fromisoformat(part["end"]) + timedelta(days=1)
    return "slack-reader", ("## The month\n\n"
                            f"From {part['start']} to {part['end']}. The person's Slack account is {account['name']}, "
                            f"<@{account['id']}>. Bound every search with `after:{after} before:{before}`, or a shorter range "
                            "within it: `after:` and `before:` exclude the day they name, so the days from D1 to D2 are "
                            "`after:<the day before D1> before:<the day after D2>`.\n\n"
                            f"- what they sent: `from:<@{account['id']}> after:{after} before:{before}`;\n"
                            f"- what mentions them: the keyword `<@{account['id']}>`, with `after:{after} before:{before}`.")


def judge_task_text(prep, content):
    """(protocol, body) of the judge's task: every item the readers listed, in
    one list by day, numbered, each with its day and description."""
    found = "\n".join(f"{item['number']}. {item['date']}: {item['description']}"
                      for item in content["items"])
    return "slack-judge", "## What the readers found\n\n" + (found or "Nothing.")


def searched_problems(searched, days):
    """Why `searched`, the ranges a reader says it searched, isn't a list of
    them, empty when it is: each of SEARCHED_SHAPE, its days of `days`, those
    of the reader's month, the first not after the last, and, for each of
    SEARCHES, the ranges together covering every day of `days`."""
    if not isinstance(searched, list):
        return [f'"searched" must be a list of {SEARCHED_SHAPE}, one for each range searched']
    problems, covered = [], {search: set() for search in SEARCHES}
    for number, entry in enumerate(searched, 1):
        what = f"searched entry {number}"
        if not (isinstance(entry, dict) and sorted(entry) == ["from", "pages", "search", "to"]
                and entry["search"] in SEARCHES and isinstance(entry["pages"], int)
                and not isinstance(entry["pages"], bool) and entry["pages"] >= 1):
            problems.append(f"{what} must be {SEARCHED_SHAPE}")
        elif not (entry["from"] in days and entry["to"] in days and entry["from"] <= entry["to"]):
            problems.append(f"{what}'s range, {entry['from']} to {entry['to']}, must be days of the month, "
                            "the first not after the last")
        else:
            covered[entry["search"]] |= set(
                days_between(entry["from"], entry["to"]))
    for search in SEARCHES:
        if missing := [day for day in days if day not in covered[search]]:
            problems.append(f"the {search} search doesn't cover {day_ranges(missing)}: search those days, "
                            "and add them to \"searched\"")
    return problems


SOURCE = reading.Source(
    name="slack", script="read_slack.py", output=SLACK, what="Slack summary", task_text=judge_task_text,
    answer_shape=JUDGE_ANSWER, cites="in the list, from 1",
    terms={"cited": "conversations",
           "citations_more": "They are numbered as in the list, from 1."},
    readers=reading.Readers(parts=parts, task_text=reader_task_text, answer_shape=READER_ANSWER, help=READER_HELP,
                            coverage_problems=searched_problems))


def main(argv=None):
    reading.command_line(SOURCE, "Read the prep's person's Slack messages: start writes a task for each month, each "
                         "for a subagent that searches Slack itself and lists its conversations; submit checks each "
                         "month's items and the ranges it searched, then the summary the judge writes from every "
                         "month's items, each point citing them, and writes it.", argv)


if __name__ == "__main__":
    main()
