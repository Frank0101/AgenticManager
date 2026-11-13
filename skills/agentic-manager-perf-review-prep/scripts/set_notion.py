"""Records a prep's person's Notion pages in work.json: those they created, and those they last edited, in the period.

Notion is reached only through its MCP, so the agent searches it and this
script checks what it found. A search returns at most SEARCH_LIMIT pages and
has no next page, so a full one is refused, to be searched again in shorter
ranges, but a day full of one database's rows, a page each to Notion, is
recorded as that database once. Search results carry the last edit's date
only, so created pages are searched by month and dated by their range; one
found twice means the filter failed, and is refused rather than trusted.
"""
import argparse
import json
import os

from common import (PERSON, WORK_LISTS, days_between, period_days, prep_dir, read_json,
                    stdin_json, write_work)

NOTION_LISTS = WORK_LISTS["notion"]

SEARCH_LIMIT = 50
INPUT = """Input, on stdin: every search made, each over a range of days, such as:

  python3 set_notion.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"created": [
    {"start": "2026-07-01", "end": "2026-07-31",
     "pages": [{"title": "Billing migration plan", "url": "https://www.notion.so/...",
                "path": "Engineering / Billing"}]},
    {"start": "2026-08-01", "end": "2026-08-31", "pages": []}
   ],
   "edited": [
    {"start": "2026-07-01", "end": "2026-08-31",
     "pages": [{"title": "Billing migration plan", "url": "https://www.notion.so/...",
                "path": "Engineering / Billing", "date": "2026-08-14"}]}
   ]}
  END_OF_INPUT

  created  the searches for pages the person created, a calendar month of the
           period each, or shorter when one returns SEARCH_LIMIT: each its
           range, start and end as YYYY-MM-DD, and its pages, title, url
           and path, where the result says the page sits, "" when it
           says nothing
  edited   the searches for pages the person last edited, the whole period,
           or shorter ranges when one returns SEARCH_LIMIT: each its range
           and its pages, title, url, path and date, the day of the last
           edit

The ranges of each list cover the period day by day, with no gap. When a
search of a single day still returns SEARCH_LIMIT and all but a few of them
are the rows of one database, give that search full_of, the database, as
{"title", "url", "path"}, and as its pages only the results that aren't its
rows: the database is recorded as one page, and the search is taken as
complete.

It writes notion to work.json, keeping its Jira and GitHub work, and
dropping its facts and commentary, which work_commentary.py works out again.
Prints one line of JSON: path, the file written, and how many pages each list
holds.
""".replace("SEARCH_LIMIT", str(SEARCH_LIMIT))


def set_notion(prep, found):
    """Check the searches `found` against the prep `prep`'s period and write
    the pages they found to work.json; returns the file's path. Exits,
    writing nothing, with every problem."""
    folder = prep_dir(prep)
    period = period_days(read_json(os.path.join(folder, PERSON)))
    if problems := searches_problems(found, period):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    found = {name: [{**search, "pages": search["pages"] + ([{**search["full_of"], "date": search["start"]}]
                                                           if "full_of" in search else [])}
                    for search in found[name]] for name in NOTION_LISTS}
    found["created"] = [{**search, "pages": [{k: v for k, v in page.items() if k != "date"} for page in search["pages"]]}
                        for search in found["created"]]
    pages = {"created": [{**page, "between": [search["start"], search["end"]]}
                         for search in found["created"] for page in search["pages"]],
             "edited": list({page["url"]: page for search in found["edited"] for page in search["pages"]}.values())}
    pages = {name: sorted(items, key=lambda page: (page.get("date") or page["between"][0], page["url"]))
             for name, items in pages.items()}
    return write_work(prep, {"notion": pages}, period)


def searches_problems(found, period):
    """Why `found` isn't the searches of the period of the days `period`,
    empty when it is: for each of NOTION_LISTS, searches whose ranges cover
    the period day by day, with no gap or overlap, none full but a day full of one
    database's rows, named in full_of, each page with its title, url and
    path, each edited page dated within its range, and no created page
    found by two searches."""
    if not (isinstance(found, dict) and sorted(found) == sorted(NOTION_LISTS)
            and all(isinstance(found[name], list) and all(
                isinstance(search, dict) and set(search) -
                {"full_of"} == {"end", "pages", "start"}
                and isinstance(search["pages"], list) for search in found[name]) for name in NOTION_LISTS)):
        return ['the input must be {"created": [{"start", "end", "pages": [...]}, ...], "edited": [...]}']
    if not all(isinstance(page, dict) and all(isinstance(page.get(key), str) for key in ("title", "url", "path"))
               for name in NOTION_LISTS for search in found[name]
               for page in search["pages"] + ([search["full_of"]] if "full_of" in search else [])):
        return ['each page must be {"title", "url", "path"}, an edited one with its "date" too']
    problems = []
    for name in NOTION_LISTS:
        searches = sorted(found[name], key=lambda search: str(search["start"]))
        try:
            covered = [day for search in searches for day in days_between(
                search["start"], search["end"])]
        except (TypeError, ValueError):
            problems.append(
                f"each {name} search's start and end must be days as YYYY-MM-DD")
            continue
        if covered != period:
            problems.append(f"the {name} searches must cover {period[0]} to {period[-1]} day by day, "
                            "with no gap or overlap")
        for search in searches:
            if "full_of" in search and search["start"] != search["end"]:
                problems.append(f"the {name} search of {search['start']} to {search['end']} names full_of, which "
                                "only a search of a single day may: search that range again in shorter ranges")
            elif "full_of" not in search and len(search["pages"]) >= SEARCH_LIMIT:
                problems.append(f"the {name} search of {search['start']} to {search['end']} found {SEARCH_LIMIT} "
                                "pages, the most it returns, so some may be missing: search that range again in "
                                "shorter ranges")
            if name == "edited":
                days = days_between(search["start"], search["end"])
                problems += [f"the edited search of {search['start']} to {search['end']}: page {page!r:.80} isn't "
                             "dated within it" for page in search["pages"]
                             if not (isinstance(page, dict) and page.get("date") in days)]
    urls = [page.get("url") for search in found["created"]
            for page in search["pages"] if isinstance(page, dict)]
    problems += [f"{url} was found by two created searches, so the creation filter can't be trusted: search again"
                 for url in sorted(set(urls), key=str) if urls.count(url) > 1]
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the Notion pages the prep's person created and last edited in the period.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    path = set_notion(args.prep, stdin_json(INPUT))
    written = read_json(path)["notion"]
    print(json.dumps({"path": path, "counts": {name: len(written.get(name, [])) for name in NOTION_LISTS}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
