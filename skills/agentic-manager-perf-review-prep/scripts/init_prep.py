"""Prepares a prep's new folder, <Person>_<YY-MM-DD> for today, replacing one of the same person and day, and starts its person.json.

Every run starts from scratch: nothing an earlier run left is read. The
person as the manager named them, the period and the Jira account they
confirmed are checked by the final check's rules before they are written;
the other sources are added once the manager confirms them, so the only
source here is Jira's. The account's name and email are read from Jira by its
id, never copied by hand, and the folder is named after its name, so the same
person always gets the same folder, however the manager calls them.
"""
import argparse
from datetime import date
import json
import os

from common import (FOLDER_NAME, JIRA_SOURCE, PERSON, JiraClient, add_period_arguments, as_name, clear_folder,
                    day_folder, output_folder, person_problems, shown, sources_problems, stops_on_failure,
                    write_prep_file)

OUTPUT = """Prints one line of JSON:
  folder, temporary   the skill's output folder, and whether it is temporary
  prep                the prep folder's name, for --prep
  prep_dir            its absolute path
  replaced            whether a folder of the same person and day was deleted
  person              what person.json records: the person, the period's start
                      and end, and sources, with jira-api, the person's Jira
                      account: id, name and email
  shown               the period as the manager reads it, such as
                      "01/07/2026 to 10/11/2026"
"""


def init(person, account, period_start, period_end, today=None, client=None):
    """Create the prep's folder for `person`, whose Jira account is
    `account`, over the period, after checking them, and record them in its
    person.json; returns where it is and what it recorded."""
    today = today or date.today()
    user = (client or JiraClient()).user(account)
    if user is None:
        raise SystemExit(f"Jira has no person's account {account}: look the person up again with "
                         "find_jira_account.py, and pass the accountId of the account the manager confirmed")
    if not user["emailAddress"]:
        raise SystemExit(f"Jira hides the email of {user['displayName']}'s account, and the person is found in "
                         "the other sources by it: tell the manager, who can ask a Jira admin to show it")
    recorded = {"person": " ".join(person.split()), "start": period_start.isoformat(),
                "end": period_end.isoformat(), "sources": {JIRA_SOURCE: {
                    "id": user["accountId"], "name": user["displayName"], "email": user["emailAddress"]}}}
    if problems := person_problems(recorded, today) + sources_problems(recorded["sources"], (JIRA_SOURCE,)):
        raise SystemExit("; ".join(problems))
    folder, temporary = output_folder(FOLDER_NAME)
    prep = day_folder(as_name(user["displayName"]), today)
    replaced = clear_folder(os.path.join(folder, prep))
    write_prep_file(prep, PERSON, recorded)
    return {"folder": folder, "temporary": temporary, "prep": prep, "prep_dir": os.path.join(folder, prep),
            "replaced": replaced, "person": recorded, "shown": shown(period_start, period_end)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Prepare a prep's folder for a person, on the Jira account and over the period the manager "
        "confirmed.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--person", required=True,
                        help="the person's name as the manager gives it, such as 'Jane Doe'")
    parser.add_argument("--account", required=True,
                        help="the accountId of the person's Jira account, as find_jira_account.py printed it")
    add_period_arguments(parser)
    args = parser.parse_args(argv)
    with stops_on_failure():
        result = init(args.person, args.account, args.start, args.end)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
