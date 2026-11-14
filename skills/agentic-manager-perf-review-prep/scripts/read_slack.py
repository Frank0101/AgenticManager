"""Reads a prep's person's Slack messages: start writes the tasks, submit takes each answer, finished reports the result.

Slack is reached only through its MCP, which a subagent can call and a script
can't, so nothing is gathered ahead: each task is a month of the period, with
the searches to run, and its subagent reads the messages itself and writes a
synopsis of each conversation. Messages are evidence rather than judgment,
so every item and point keeps the links it rests on. A last subagent judges
and merges the synopses, as reading.py runs every reading.
"""
import os
from datetime import date, timedelta

from common import PERSON, SLACK, days_between, months_of, prep_dir, read_json
import reading
from reading import MERGE

READING_ANSWER = """{"items": [
  {"date": "YYYY-MM-DD", "link": "https://<workspace>.slack.com/archives/<channel>/p<message>",
   "synopsis": "In #<channel>, a cross-team channel, posted the rollout plan; three people asked..."}
 ]}"""
MERGE_ANSWER = """{"going_well": [{"point": "...", "values": ["<each company value it clearly shows or calls for, at most two>"],
                 "links": ["https://...", ...]}],
 "to_improve": [{"point": "...", "values": [], "links": ["https://..."]}],
 "context": [{"point": "...", "links": ["https://...", ...]}],
 "in_doubt": ["YYYY-MM-DD: what the conversation says, and why you left it out"]}"""


def gather(prep):
    """The material of Slack: the months of the period, each a task, and the
    content, {account: {id, name}, months: {YYYY-MM: {start, end}}}, each
    month's first and last day within the period."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    months = months_of(date.fromisoformat(
        person["start"]), date.fromisoformat(person["end"]))
    return {"months": sorted(months), "tasks": [f"month:{month}" for month in sorted(months)],
            "content": {"account": person["sources"]["slack-mcp"], "months": months}}


def task_text(prep, task, material):
    """(protocol, body) of the month `task`: the person's Slack account and
    the filters that bound the month's searches, Slack's after: and before:
    excluding the day they name."""
    content = material["content"]
    month = content["months"][task.split(":")[1]]
    after = date.fromisoformat(month["start"]) - timedelta(days=1)
    before = date.fromisoformat(month["end"]) + timedelta(days=1)
    account = content["account"]
    return "slack", ("## The month\n\n"
                     f"From {month['start']} to {month['end']}. The person's Slack account is {account['name']}, "
                     f"<@{account['id']}>. Bound every search with `after:{after} before:{before}`, or a shorter range "
                     "within it: `after:` and `before:` exclude the day they name, so the days from D1 to D2 are "
                     "`after:<the day before D1> before:<the day after D2>`.\n\n"
                     f"- what they sent: `from:<@{account['id']}> after:{after} before:{before}`;\n"
                     f"- what mentions them: the keyword `<@{account['id']}>`, with `after:{after} before:{before}`.")


def task_days(material, task):
    """Every day of the month `task` within the period."""
    return days_between(**material["content"]["months"][task.split(":")[1]])


SOURCE = reading.Source(name="slack", script="read_slack.py", output=SLACK, what="Slack summary", gather=gather,
                        task_text=task_text, task_days=task_days,
                        answers={"reading": READING_ANSWER, MERGE: MERGE_ANSWER})


def main(argv=None):
    reading.command_line(SOURCE, "Read the prep's person's Slack messages: start writes a task for each month of the "
                         "period, each for a subagent that searches Slack itself and writes a synopsis of each conversation, and names the merge task, written once "
                         "they are all answered; finished says what the merge made of them.", argv)


if __name__ == "__main__":
    main()
