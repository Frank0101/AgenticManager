"""Looks a person up in Jira by the name the manager gives, read-only, and prints the accounts they could be.

The manager confirms the person's Jira account with the period, before the
prep starts, so the prep's folder and every later search start from one
account: its email finds the person in the other sources. Jira's user search
matches a full name, so each word of it is tried when the full name finds no
one, such as a name the manager shortens. It lists candidates and never
chooses: the account is the manager's to confirm.
"""
import argparse
import json

from common import JiraClient, name_words, stops_on_failure

OUTPUT = """Prints one line of JSON:
  person    the name looked up, as given
  accounts  each Jira account found by the full name, or by each word of it
            when the full name finds none: accountId, displayName,
            emailAddress (null when the site hides it) and active
"""


def find(person, client=None):
    """{person, accounts}: the Jira accounts the person `person` could be."""
    person = " ".join(person.split())
    return {"person": person, "accounts": jira_candidates(client or JiraClient(), person)}


def jira_candidates(client, person):
    """The Jira accounts found for `person`'s full name or, when it finds none,
    for each word of it, each account once, in the order found."""
    found = client.users(person)
    if not found:
        found = [user for word in name_words(person)
                 for user in client.users(word)]
    return list({user["accountId"]: user for user in found}.values())


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Look a person up in Jira by their name, and print the accounts they could be.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--person", required=True,
                        help="the person's name as the manager gives it, such as 'Jane Doe'")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps(find(args.person), ensure_ascii=False))


if __name__ == "__main__":
    main()
