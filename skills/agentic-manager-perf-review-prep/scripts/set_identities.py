"""Records who a prep's person is in GitHub, Notion, Slack and the vault, as the manager confirmed, in its person.json.

Their Jira account is already there, confirmed with the period, and is kept
as it is, with the person and the period. The agent writes the four other
sources as JSON on stdin, a quoted here-document, so nothing in them needs
escaping. They are checked before anything is written, by the rules the
final check applies, which then hold for the whole file, and replace the
ones recorded before, so a correction from the manager is one more call with
every source in it.
"""
import argparse
import json
import os

from common import (JIRA_SOURCE, PERSON, SOURCES, prep_dir, read_json, sources_problems, stdin_json,
                    write_prep_file)

# The sources the manager confirms here: every one but Jira's.
OTHER_SOURCES = tuple(source for source in SOURCES if source != JIRA_SOURCE)
INPUT = """Input, on stdin: every source but jira-api, which init_prep.py recorded,
each as the manager confirmed it, such as:

  python3 set_identities.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {
    "github-cli": {"id": "janedoe", "name": "Jane Doe"},
    "notion-mcp": {"id": "2a4c1e8f-1234-4abc-9def-0123456789ab", "name": "Jane Doe"},
    "slack-mcp": {"id": "U012AB3CD", "name": "Jane Doe"},
    "logseq-fs": {"links": ["Jane", "Jane Promotion"]}
  }
  END_OF_INPUT

  id      the account's id: the GitHub login, the Notion user's id or the
          Slack user's id
  name    the name the account gives, as the source shows it, or its id
          when it gives none, such as a GitHub login whose profile has no name
  links   the vault's links about the person, as written in the notes: their
          tag and the pages about them, such as Jane for [[Jane]]

Prints one line of JSON: path, the file written, and sources, every source
it now records, jira-api's too.
"""


def set_identities(prep, identities):
    """Record `identities`, who the person is in every source but Jira's, in
    the prep `prep`'s person.json, keeping the person, the period and the
    Jira account, after checking them; returns the file's path and every
    source it records. Exits, writing nothing, with every problem."""
    path = os.path.join(prep_dir(prep), PERSON)
    if isinstance(identities, dict) and JIRA_SOURCE in identities:
        raise SystemExit(f"leave {JIRA_SOURCE} out: the Jira account was confirmed with the period in step 1, "
                         f"and init_prep.py recorded it\n\n{INPUT}")
    if problems := sources_problems(identities, OTHER_SOURCES):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    person = read_json(path)
    sources = {JIRA_SOURCE: person["sources"].get(JIRA_SOURCE), **identities}
    if problems := sources_problems(sources, SOURCES):
        raise SystemExit("; ".join(problems) +
                         ": start the prep again with init_prep.py")
    return write_prep_file(prep, PERSON, {**person, "sources": sources}), sources


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record who the prep's person is in GitHub, Notion, Slack and the vault, as the manager "
        "confirmed.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    path, sources = set_identities(args.prep, stdin_json(INPUT))
    print(json.dumps({"path": path, "sources": sources}, ensure_ascii=False))


if __name__ == "__main__":
    main()
