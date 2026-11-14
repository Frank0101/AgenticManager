"""Records the Notion pages a prep's person created in the period in their raw file, which work.json is built from.

The agent searches Notion through its MCP and gives this script each
search's results as returned, unchanged, so no page is copied by hand: the
script keeps the pages of their own and checks the searches. Edited pages
aren't kept: Notion knows only a page's last editor, so their count would
miss what others edited after.
"""
import argparse
import json
import os

from common import (NOTION_LIMIT, PERSON, period_days, prep_dir, raw_work_problems, read_json, stdin_json,
                    work_items, write_work)

INPUT = """Input, on stdin: every search made, each over a range of days, with its results
exactly as the search returned them, such as:

  python3 set_notion.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"created": [
    {"start": "2026-07-01", "end": "2026-07-05",
     "results": [{"id": "1a2b...", "title": "Billing migration plan", "url": "https://www.notion.so/...",
                  "type": "page", "timestamp": "2026-07-03T06:19:00.000Z", "path": "Engineering / Billing"}]},
    {"start": "2026-07-06", "end": "2026-07-12", "results": []}
   ]}
  END_OF_INPUT

  created  the searches for pages the person created, a calendar week of the
           period each, Monday to Sunday, the first and last clipped to it,
           or shorter when one returns NOTION_LIMIT results: each its range,
           start and end as YYYY-MM-DD, and results, the search's results
           list, databases and their rows included, unchanged

The ranges cover the period day by day, with no gap. When a search of a
single day still returns NOTION_LIMIT results, give it "full": true: its
results are taken as all there are.

It writes the searches to Notion's raw file in the prep's _raw, and work.json
once Jira's and GitHub's are in too. Prints one line of JSON: raw, the raw
file's path, work, work.json's, or null until it is built, and pages, how
many pages of their own the searches found.
""".replace("NOTION_LIMIT", str(NOTION_LIMIT))


def set_notion(prep, found):
    """Check the searches `found` against the prep `prep`'s period and write
    them to Notion's raw file, and work.json once Jira and GitHub are in too;
    returns {raw, work}, the files' paths. Exits, writing nothing, with every
    problem."""
    period = period_days(read_json(os.path.join(prep_dir(prep), PERSON)))
    if problems := raw_work_problems("notion", found, period):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_work(prep, "notion", found, period)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the Notion pages the prep's person created in the period.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    paths = set_notion(args.prep, stdin_json(INPUT))
    pages = work_items("notion", read_json(paths["raw"]))["created"]
    print(json.dumps({**paths, "pages": len(pages)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
