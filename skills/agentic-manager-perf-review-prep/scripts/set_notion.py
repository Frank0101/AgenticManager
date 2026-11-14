"""Records the Notion pages a prep's person created in the period in their raw file, which work.json is built from.

The agent searches Notion through its MCP and this script checks what it
found. Edited pages aren't kept: Notion knows only a page's last editor, so
their count would miss what others edited after. Database rows don't count. A
search returns at most SEARCH_LIMIT results, so a full one is searched again in
shorter ranges; a single day still full keeps what it found. Results carry only
the last edit's date, so pages are searched by week and dated by their range;
one found twice means the filter failed, and is refused rather than trusted.
"""
import argparse
import json
import os
from datetime import date

from common import PERSON, days_between, period_days, prep_dir, read_json, stdin_json, write_work

SEARCH_LIMIT = 50
INPUT = """Input, on stdin: every search made, each over a range of days, such as:

  python3 set_notion.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"created": [
    {"start": "2026-07-01", "end": "2026-07-05",
     "pages": [{"title": "Billing migration plan", "url": "https://www.notion.so/...",
                "path": "Engineering / Billing"}]},
    {"start": "2026-07-06", "end": "2026-07-12", "pages": []}
   ]}
  END_OF_INPUT

  created  the searches for pages the person created, a calendar week of the
           period each, Monday to Sunday, the first and last clipped to it,
           or shorter when one returns SEARCH_LIMIT results:
           each its range, start and end as YYYY-MM-DD, and its pages,
           title, url and path, where the result says the page sits, ""
           when it says nothing

Give as pages only the results that are pages of their own, never a
database's row. The ranges cover the period day by day, with no gap. When a search of a single day still returns SEARCH_LIMIT results, give
it "full": true: its pages are taken as all there are.

It writes the pages to Notion's raw file in the prep's _raw, and work.json
once Jira's and GitHub's are in too. Prints one line of JSON: raw, the raw
file's path, work, work.json's, or null until it is built, and pages, how
many pages it holds.
""".replace("SEARCH_LIMIT", str(SEARCH_LIMIT))


def set_notion(prep, found):
    """Check the searches `found` against the prep `prep`'s period and write
    the pages they found to Notion's raw file, and work.json once Jira and
    GitHub are in too; returns {raw, work}, the files' paths. Exits,
    writing nothing, with every problem."""
    folder = prep_dir(prep)
    period = period_days(read_json(os.path.join(folder, PERSON)))
    if problems := searches_problems(found, period):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    pages = [{"title": page["title"], "url": page["url"], "path": page["path"],
              "between": [search["start"], search["end"]]}
             for search in found["created"] for page in search["pages"]]
    return write_work(prep, "notion", {"created": sorted(pages, key=lambda page: (page["between"][0], page["url"]))},
                      period)


def searches_problems(found, period):
    """Why `found` isn't the searches of the period of the days `period`,
    empty when it is: {"created": searches} whose ranges cover the period day
    by day, with no gap or overlap, each within a calendar week, none full
    but a single day, marked full, each page with its title, url and path,
    and no page found by two searches."""
    if not (isinstance(found, dict) and list(found) == ["created"] and isinstance(found["created"], list)
            and all(isinstance(search, dict) and set(search) - {"full"} == {"end", "pages", "start"}
                    and search.get("full", True) is True and isinstance(search["pages"], list)
                    for search in found["created"])):
        return ['the input must be {"created": [{"start", "end", "pages": [...]}, ...]}']
    searches = sorted(found["created"],
                      key=lambda search: str(search["start"]))
    pages = [page for search in searches for page in search["pages"]]
    if not all(isinstance(page, dict) and all(isinstance(page.get(key), str) for key in ("title", "url", "path"))
               for page in pages):
        return ['each page must be {"title", "url", "path"}']
    try:
        covered = [day for search in searches for day in days_between(
            search["start"], search["end"])]
    except (TypeError, ValueError):
        return ["each search's start and end must be days as YYYY-MM-DD"]
    problems = [] if covered == period else [
        f"the searches must cover {period[0]} to {period[-1]} day by day, with no gap or overlap"]
    for search in searches:
        span = f"the search of {search['start']} to {search['end']}"
        if date.fromisoformat(search["start"]).isocalendar()[:2] != date.fromisoformat(search["end"]).isocalendar()[:2]:
            problems.append(
                f"{span} spans more than a calendar week: search week by week, Monday to Sunday")
        if "full" in search and search["start"] != search["end"]:
            problems.append(f"{span} is full, which only a search of a single day may be: search that range "
                            "again in shorter ranges")
        elif "full" not in search and len(search["pages"]) >= SEARCH_LIMIT:
            problems.append(f"{span} found {SEARCH_LIMIT} pages, the most it returns, so some may be missing: "
                            "search that range again in shorter ranges")
    urls = [page["url"] for page in pages]
    return problems + [f"{url} was found by two searches, so the creation filter can't be trusted: search again"
                       for url in sorted(set(urls)) if urls.count(url) > 1]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the Notion pages the prep's person created in the period.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    paths = set_notion(args.prep, stdin_json(INPUT))
    print(json.dumps(
        {**paths, "pages": len(read_json(paths["raw"])["created"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
