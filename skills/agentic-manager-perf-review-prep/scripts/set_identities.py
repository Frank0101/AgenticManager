"""Records who a prep's person is in each source, as the manager confirmed, in identities.json.

The agent writes the identities as JSON on stdin, a quoted here-document, so
nothing in them needs escaping. They are checked before anything is written,
by the rules the final check applies, and written whole each time, so a
correction from the manager is one more call with every source in it.
"""
import argparse
import json
import sys

from common import IDENTITIES, identities_problems, prep_dir, write_prep_file

INPUT = """Input, on stdin: every source, each as the manager confirmed it, such as:

  python3 set_identities.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {
    "jira-api": {"id": "5b10ac8d82e05b22cc7d4ef5", "name": "Jane Doe"},
    "github-cli": {"id": "janedoe", "name": "Jane Doe"},
    "notion-mcp": {"id": "2a4c1e8f-1234-4abc-9def-0123456789ab", "name": "Jane Doe"},
    "slack-mcp": {"absent": true},
    "logseq-fs": {"links": ["Jane", "Jane Promotion"]}
  }
  END_OF_INPUT

  id      the account's id: Jira's accountId, the GitHub login, the Notion
          user's id or the Slack user's id
  name    the name the account gives, as the source shows it
  links   the vault's links about the person, as written in the notes: their
          tag and the pages about them, such as Jane for [[Jane]]
  absent  true when the manager says the person isn't in that source

Prints one line of JSON: path, the file written, and identities.
"""


def set_identities(prep, identities):
    """Write `identities` to the prep `prep`'s identities.json, after checking
    them; returns the file's path. Exits, writing nothing, with every problem."""
    prep_dir(prep)  # exits if the prep isn't there
    if problems := identities_problems(identities):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, IDENTITIES, identities)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record who the prep's person is in each source, as the manager confirmed.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    try:
        identities = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise SystemExit(f"the input isn't JSON: {error}\n\n{INPUT}")
    path = set_identities(args.prep, identities)
    print(json.dumps(
        {"path": path, "identities": identities}, ensure_ascii=False))


if __name__ == "__main__":
    main()
