"""Prepares a prep's new folder, <Person>_<YY-MM-DD> for today, replacing one of the same person and day, and records the request in it.

Every run starts from scratch, so a prep is always built from fresh data:
nothing an earlier run left, on this or another day, is read or reused. The
request holds the person as the manager named them and the period as exact
days, checked before anything is written by the rules the final check applies,
so a request that can't be prepared never reaches a later step. The person's
name is only a starting point: who they are in each source is resolved later.
"""
import argparse
from datetime import date
import json
import os

from common import (FOLDER_NAME, REQUEST, add_period_arguments, as_name, clear_folder, day_folder, output_folder,
                    request_problems, shown, write_prep_file)

OUTPUT = """Prints one line of JSON:
  folder, temporary   the skill's output folder, and whether it is temporary
  prep                the prep folder's name, for --prep
  prep_dir            its absolute path
  replaced            whether a folder of the same person and day was deleted
  request             what was recorded: the person, and the period's start
                      and end
  shown               the period as the manager reads it, such as
                      "01/07/2026 to 10/11/2026"
"""


def init(person, period_start, period_end, today=None):
    """Create the prep's folder for `person` over the period, after checking
    the request, and record it; returns where it is and what it recorded."""
    today = today or date.today()
    request = {"person": " ".join(person.split()), "start": period_start.isoformat(),
               "end": period_end.isoformat()}
    if problems := request_problems(request, today):
        raise SystemExit("; ".join(problems))
    folder, temporary = output_folder(FOLDER_NAME)
    prep = day_folder(as_name(request["person"]), today)
    replaced = clear_folder(os.path.join(folder, prep))
    write_prep_file(prep, REQUEST, request)
    return {"folder": folder, "temporary": temporary, "prep": prep, "prep_dir": os.path.join(folder, prep),
            "replaced": replaced, "request": request, "shown": shown(period_start, period_end)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Prepare a prep's folder for a person over a period the manager confirmed.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--person", required=True,
                        help="the person's name as the manager gives it, such as 'Jane Doe'")
    add_period_arguments(parser)
    args = parser.parse_args(argv)
    print(json.dumps(init(args.person, args.start, args.end), ensure_ascii=False))


if __name__ == "__main__":
    main()
