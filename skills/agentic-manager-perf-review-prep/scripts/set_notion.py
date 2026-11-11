"""Records a prep's person's Notion pages in notion.json: those they created, and those they last edited, in the period.

Notion is reached only through its MCP, so the agent searches it and this
script checks what it found before writing it. A search returns at most
SEARCH_LIMIT pages and has no next page, so a list that fills it is refused,
to be searched again in shorter ranges. The search filters by creation date
but returns only the last edit's, so created pages are searched a month at a
time and dated by the range they were found in; a page found by two of them
means the filter failed, and is refused rather than trusted.
"""
import argparse
import json
import os

from common import (ABSENT, IDENTITIES, NOTION, NOTION_LISTS, REQUEST, days_between, notion_problems, prep_dir,
                    read_json, stdin_json, write_prep_file)

SEARCH_LIMIT = 50
INPUT = """Input, on stdin: every search made, each over a range of days, such as:

  python3 set_notion.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {"created": [
    {"start": "2026-07-01", "end": "2026-07-31",
     "pages": [{"title": "Billing migration plan", "url": "https://www.notion.so/..."}]},
    {"start": "2026-08-01", "end": "2026-08-31", "pages": []}
   ],
   "edited": [
    {"start": "2026-07-01", "end": "2026-08-31",
     "pages": [{"title": "Billing migration plan", "url": "https://www.notion.so/...", "date": "2026-08-14"}]}
   ]}
  END_OF_INPUT

  created  the searches for pages the person created, a calendar month of the
           period each, or shorter when one returns SEARCH_LIMIT: each its
           range, start and end as YYYY-MM-DD, and its pages, title and url
  edited   the searches for pages the person last edited, the whole period,
           or shorter ranges when one returns SEARCH_LIMIT: each its range
           and its pages, title, url and date, the day of the last edit

The ranges of each list cover the period day by day, with no gap. Write
{"absent": true} when the manager said the person isn't in Notion.

Prints one line of JSON: path, the file written, and how many pages each list
holds.
""".replace("SEARCH_LIMIT", str(SEARCH_LIMIT))


def set_notion(prep, found):
    """Check the searches `found` against the prep `prep`'s period and write
    the pages they found to notion.json; returns the file's path. Exits,
    writing nothing, with every problem."""
    folder = prep_dir(prep)
    request = read_json(os.path.join(folder, REQUEST))
    if found == ABSENT:
        if read_json(os.path.join(folder, IDENTITIES))["notion-mcp"] != ABSENT:
            raise SystemExit(
                "The person has a Notion account, so their pages must be searched\n\n" + INPUT)
        return write_prep_file(prep, NOTION, ABSENT)
    if problems := searches_problems(found, request):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    pages = {"created": [{**page, "between": [search["start"], search["end"]]}
                         for search in found["created"] for page in search["pages"]],
             "edited": list({page["url"]: page for search in found["edited"] for page in search["pages"]}.values())}
    pages = {name: sorted(items, key=lambda page: (page.get("date") or page["between"][0], page["url"]))
             for name, items in pages.items()}
    if problems := notion_problems(pages, days_between(request["start"], request["end"])):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, NOTION, pages)


def searches_problems(found, request):
    """Why `found` isn't the searches of the period of `request`, empty when
    it is: for each of NOTION_LISTS, searches whose ranges cover the period
    day by day, with no gap or overlap, none full, each page with its title and url, each edited page dated
    within its range, and no created page found by two searches."""
    if not (isinstance(found, dict) and sorted(found) == sorted(NOTION_LISTS)
            and all(isinstance(found[name], list) and all(
                isinstance(search, dict) and sorted(
                    search) == ["end", "pages", "start"]
                and isinstance(search["pages"], list) for search in found[name]) for name in NOTION_LISTS)):
        return ['the input must be {"created": [{"start", "end", "pages": [...]}, ...], "edited": [...]}']
    if not all(isinstance(page, dict) and isinstance(page.get("title"), str) and isinstance(page.get("url"), str)
               for name in NOTION_LISTS for search in found[name] for page in search["pages"]):
        return ['each page must be {"title", "url"}, an edited one with its "date" too']
    problems = []
    period = days_between(request["start"], request["end"])
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
            problems.append(f"the {name} searches must cover {request['start']} to {request['end']} day by day, "
                            "with no gap or overlap")
        for search in searches:
            if len(search["pages"]) >= SEARCH_LIMIT:
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
    written = read_json(path)
    print(json.dumps({"path": path, "counts": {name: len(written.get(name, [])) for name in NOTION_LISTS}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
