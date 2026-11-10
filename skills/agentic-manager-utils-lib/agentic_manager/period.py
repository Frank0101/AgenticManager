"""A period of days a skill reports on, such as the last 3 months: its exact first and last days, and when it is valid.

A period the user names relative to today, such as "the last 3 months", is
turned into dates here, by one rule, so every skill reads it the same way and
the user confirms exact dates rather than words: it ends today and starts the
same day N months earlier, or that month's last day when it is shorter (31/05
three months back from 31/08, 28/02 from 31/05). Both days are part of it. A
period can't end after today, since nothing has happened there yet, and can't
start after it ends.
"""
import argparse
from datetime import date
import calendar
import json
import os
import sys

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.text import display_date  # noqa: E402

OUTPUT = """Prints one line of JSON:
  start, end   the period's first and last days, as YYYY-MM-DD, for a
               script's --start and --end
  shown        the period as the user reads it, such as
               "10/08/2026 to 10/11/2026", to confirm with them
Fails with a message on stderr when the period isn't valid.
"""


def resolve(args, today):
    """{start, end, shown} of the period the command line `args` names, or
    exits with why it isn't valid."""
    if args.last_months is not None:
        try:
            start, end = last_months(args.last_months, today)
        except ValueError as error:
            raise SystemExit(str(error))
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        raise SystemExit(
            "name the period: --last-months N, or both --start and --end")
    if problem := period_problem(start, end, today):
        raise SystemExit(problem)
    return {"start": start.isoformat(), "end": end.isoformat(), "shown": shown(start, end)}


def last_months(months, today):
    """(start, end) of the last `months` months up to `today`, both days part
    of it: from the same day `months` months earlier, or that month's last day
    when it is shorter, to today."""
    if months < 1:
        raise ValueError(f"a period of {months} months must be at least 1")
    return months_before(today, months), today


def months_before(day, months):
    """The same day `months` months before `day`, or that month's last day
    when it is shorter."""
    month_index = day.year * 12 + day.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def period_problem(start, end, today):
    """Why the period from `start` to `end`, both dates, isn't valid on
    `today`, or None: it ends after today, or starts after it ends."""
    if end > today:
        return f"the period ends on {display_date(end)}, after today, {display_date(today)}: end it today or earlier"
    if start > end:
        return f"the period starts on {display_date(start)}, after it ends, on {display_date(end)}"
    return None


def shown(start, end):
    """The period as the user reads it, such as "10/08/2026 to 10/11/2026"."""
    return f"{display_date(start)} to {display_date(end)}"


def add_period_arguments(parser):
    """Adds --start and --end, the period's first and last days, to the
    command line `parser`, both required."""
    parser.add_argument("--start", type=day_argument, required=True,
                        help="the period's first day, as YYYY-MM-DD")
    parser.add_argument("--end", type=day_argument, required=True,
                        help="the period's last day, as YYYY-MM-DD, today at the latest")


def day_argument(text):
    """`text` as a date, if it is one as YYYY-MM-DD; else an argparse error,
    so --start and --end can use it as their type."""
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} must be a date as YYYY-MM-DD, such as 2026-08-10")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Turn the period the user names into exact days, and check it: the last N months up to "
        "today, or a first and last day they give.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--last-months", type=int, metavar="N",
                        help="the last N months, ending today, such as 3 for the last 3 months")
    parser.add_argument("--start", type=day_argument,
                        help="the period's first day, as YYYY-MM-DD, with --end")
    parser.add_argument("--end", type=day_argument,
                        help="the period's last day, as YYYY-MM-DD, today at the latest, with --start")
    args = parser.parse_args(argv)
    if args.last_months is not None and (args.start or args.end):
        parser.error(
            "give either --last-months or --start and --end, not both")
    return args


def main():
    print(json.dumps(resolve(parse_args(), date.today())))


if __name__ == "__main__":
    main()
