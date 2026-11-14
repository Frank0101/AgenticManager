"""What the skill's scripts share: the prep folder's name and the closed set of
files it holds, how to find a prep's folder, the person a prep is for, the
review's period and its days and months, who the person is in each source, the parts
every summary has, the manager's view, previous reviews, the period's
feedback, the manager's notes, the person's work in Jira, GitHub and Notion, and their Slack
messages. The rules of each file are one function, applied when it is written
and by the final check, so the two can't differ. Scripts import the shared
library's names from here, so they don't depend on the order of their imports.
"""
from datetime import date, timedelta
import json
import os
import sys
from urllib.parse import quote

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.config import company_setting  # noqa: E402,F401
from agentic_manager.failures import stops_on_failure  # noqa: E402,F401
from agentic_manager.github import commit_authors, gh_available, gh_json, gh_orgs, gh_signed_in, profile_name  # noqa: E402,F401
from agentic_manager.jira import JiraClient, browse_url, plain_text  # noqa: E402,F401
from agentic_manager.logseq import graph_path, links, notes, page_aliases  # noqa: E402,F401
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.protocol import fill as fill_protocol  # noqa: E402,F401
from agentic_manager.output_folder import DAY_FOLDER, clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.period import add_period_arguments, period_problem, shown  # noqa: E402,F401
from agentic_manager.text import as_name, word_count  # noqa: E402,F401

# How to write a point and pick its values, with their examples, lives in the
# protocol's shared part _point.md, the one place for them: the merges' tasks
# fill it in, and rules.py prints it for the agent.
PROTOCOL = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "..", "protocol")

# The skill's output folder, and a prep folder's files in it: the person the
# manager confirmed, which every later step reads rather than being told again.
FOLDER_NAME = "perf-review-preps"
PERSON = "person.json"
# The person's fields: the person as the manager named them, the name every
# message to the manager and every summary uses; the period's first and last
# days, as YYYY-MM-DD; and who the person is in each source the skill reads,
# as the manager confirmed. How the period reads is worked out from them
# wherever it is shown, never stored.
PERSON_FIELDS = ("person", "start", "end", "sources")
# Who the person is in each source, by the fields each records: an account's
# id and the name it gives, or in the vault the links about the person, their
# tag and the pages about them, such as [[Jane]] and [[Jane Promotion]], whose
# aliases count too. A field is a text, or, in LIST_FIELDS, a list of texts.
# The Jira account is confirmed with the period and read from Jira by its id;
# its email finds the person in the other sources, so it can't be missing.
# The others are confirmed once it is there. The person is in every source: a
# review drawn from some of them would read as one where the person did
# nothing in the others.
JIRA_SOURCE = "jira-api"
ACCOUNT = ("id", "name")
SOURCES = {JIRA_SOURCE: ("id", "name", "email"), "github-cli": ACCOUNT, "notion-mcp": ACCOUNT,
           "slack-mcp": ACCOUNT, "logseq-fs": ("links",)}
LIST_FIELDS = {"links"}
# Every summary the skill records, of the manager's view, reviews, feedback
# or notes, has the same parts, so each reads, and is compared with the
# evidence, the same way: each a list of points in the agent's words, a part
# with nothing to say left empty. A point is a sentence; only one far longer
# is refused, as a length is room, not a quota. A point that is good also names
# every company value it clearly shows, and one to improve every value it
# calls for, up to MAX_VALUES, the most first, or none when none fits: one
# value per point would let the most common one, such as delivery, hide the
# others. The writing step can then speak to each value from what was
# gathered; a context point is neither, so it names none.
SUMMARY_PARTS = {"going_well": "what is going well or exceeding",
                 "to_improve": "what are improvement or stretch areas, including what they should achieve next",
                 "context": "facts the review must take into account, such as a long absence, a change of "
                 "role or support they need"}
VALUED_PARTS = ("going_well", "to_improve")
POINT_WORDS = 25
MAX_POINT_WORDS = 40
VALUES = "values"
RATINGS = "perf-review-ratings"
MAX_VALUES = 2
# A point's evidence links: a Slack message's address, or a note's file.
LINK_SCHEMES = ("https://", "file://")
SUMMARY_HELP = "\n".join(
    f"  {part:<11} {meaning}, each point "
    + ('{"point": "...", "values": ["..."]}, values every company value it clearly shows or calls for, as rules.py prints '
       f'them, at most {MAX_VALUES}, or [] when none fits' if part in VALUED_PARTS else "a sentence")
    for part, meaning in SUMMARY_PARTS.items())
# The manager's overall view of the person, summarised: guidance for the
# writing step, the only one that reads it, so the evidence is gathered without
# it and can contradict it.
ORIENTATION = "orientation.json"
# What the manager gives, previous reviews or the period's feedback, is a
# list of pieces, each a summary with its period as the source names it, such
# as a date or "Mid Year Review 2026", null when it names none: a label, not
# days worked out, so nothing is inferred and a piece with none still counts.
# The agent lists them from the most recent, those with no period first, as
# the most recent of all; what the manager gives counts, so how old it is isn't checked.
PIECE_FIELDS = ("period",)
# The person's previous performance reviews, with the colleagues' feedback
# gathered for them, each with its rating when it gives one, which must be one
# of the company's.
REVIEWS = "reviews.json"
REVIEW_FIELDS = (*PIECE_FIELDS, "rating")
# What the person heard about their work during the period, unlike the
# manager's own notes: their OKRs, the notes of their 1:1s and the kudos or
# recognition they received. Read with judgment, never tracked as
# commitments.
FEEDBACK = "feedback.json"
# The manager's own notes on the person in their vault: from the journals of
# the period, what they noticed, each point with the days it was seen on and
# the notes' files, a pattern one point with all of them; from the person's
# pages, only context, which has no date. Read by subagents, a month of
# journals each, then merged, as Slack is.
NOTES = "notes.json"
# The person's work in the period, in Jira, GitHub and Notion. Each source's
# script writes what it gathered to its raw file, _raw/<source>.json: Jira's
# issues and GitHub's pull requests as their APIs return them, with the
# period and the searches that found them, so whose each item is, and why it
# is there, can be checked again without searching again; Notion's searches,
# which only the agent reaches, with their results as returned. Once every
# source's is in, work.json is built from them, with no network, and nowhere
# else: for each source its items, each with its title, date and link, for
# the writing step to cite, the facts worked out from them, once, and for
# Jira and GitHub the address of each list's search, to see the same items
# live.
WORK = "work.json"
WORK_LISTS = {"jira": ("created", "resolved"), "github": (
    "opened", "merged"), "notion": ("created",)}
# What a raw file holds beside its lists: the period and, for each list, the
# search that found it, Jira's JQL or GitHub's query on github.com, whose
# org: terms are alternatives.
RAW_FIELDS = {"jira": ("start", "end", "base_url", "created_jql", "resolved_jql"),
              "github": ("start", "end", "orgs", "opened_query", "merged_query"), "notion": ()}
# The fields of a raw item work.json is built from, and those kept only to
# check whose it is: Jira's assignee, reporter and updated, GitHub's author
# and updatedAt. A parent, which Jira leaves out when an issue has none,
# needs its own.
RAW_ITEM_FIELDS = {"jira": ("key", "fields.summary", "fields.issuetype.name", "fields.status.name",
                            "fields.created", "fields.resolutiondate", "fields.assignee",
                            "fields.reporter", "fields.updated"),
                   "github": ("number", "title", "repository.nameWithOwner", "url", "createdAt", "closedAt",
                              "author", "updatedAt")}
PARENT_FIELDS = ("key", "fields.summary", "fields.issuetype.name")
# Notion's search filters by creation date but returns only the last edit's,
# so a created page is dated by the range of the search that found it,
# `between`, a calendar week at most; `path` is where it sits. A search
# returns at most NOTION_LIMIT results, rows included, and no next page, so
# a full one is searched again in shorter ranges; a single day can't be
# split, so one still full keeps what it found. A database's rows aren't
# pages of their own.
NOTION_LIMIT = 50
# The facts of each source. The activity over time isn't one: each item
# has its day, and grouping them, such as by week, is for whatever shows it.
FACT_KEYS = {"jira": ("counts", "created_by_type", "resolved_by_type", "focus"),
             "github": ("counts",), "notion": ("counts",)}
SEARCHED = ("jira", "github")
# The share of the resolved issues the main focus covers.
FOCUS_SHARE = 0.8
# What the person's Slack messages show, read by subagents a month each and
# merged, every point with the days and links it rests on.
SLACK = "slack.json"
# What each source gave: the readers' answers, a folder per source, kept so a
# summary can be traced back to the notes and synopses it came from, and the
# raw file of each source of the work.
RAW_DIR = "_raw"


def expected_files():
    """Every file a prep folder holds, and nothing else: the person, the
    period and who they are in each source, the manager's view of them, their previous
    reviews, the period's feedback, the manager's notes on them, what their Slack
    messages show, their work in Jira, GitHub and Notion, and the _raw folder
    of what each source gave."""
    return {PERSON, ORIENTATION, REVIEWS, FEEDBACK, NOTES, SLACK, WORK, RAW_DIR}


def write_work(prep, source, raw, days):
    """Writes `raw`, what `source` gave, such as {"created": [...]} for
    "notion", to its raw file in the prep `prep`, then, once every
    source's is in and follows its rules, as one from an earlier version or
    period doesn't, work.json, built from them; returns {raw, work}, the
    files' paths, work null until it is built. Exits, writing nothing, when
    `raw` breaks a rule, `days` the period's."""
    if problems := raw_work_problems(source, raw, days):
        raise SystemExit("; ".join(problems))
    path = write_raw(prep, f"{source}.json", json.dumps(
        raw, ensure_ascii=False, indent=1))
    raws = read_raw_work(prep)
    ready = raws is not None and not any(raw_work_problems(
        source, other, days) for source, other in raws.items())
    return {"raw": path, "work": write_prep_file(prep, WORK, build_work(raws, days)) if ready else None}


def raw_work_problems(source, raw, days):
    """Why `raw` isn't the raw file of `source`, empty when it is: its
    RAW_FIELDS, for the period of `days`, and its lists, each item with its
    RAW_ITEM_FIELDS, or for Notion its searches by notion_searches_problems(),
    and following the rules of items_problems() once built."""
    fields = (*RAW_FIELDS[source], *WORK_LISTS[source])
    if not (isinstance(raw, dict) and sorted(raw) == sorted(fields)
            and all(isinstance(raw[name], list) for name in WORK_LISTS[source])):
        return [f"the {source} raw file must hold {', '.join(fields)}"]
    if "start" in raw and (raw["start"], raw["end"]) != (days[0], days[-1]):
        return [f"the {source} raw file is for {raw['start']} to {raw['end']}, not the period: run "
                "fetch_work.py again"]
    if source == "notion":
        problems = notion_searches_problems(raw["created"], days)
    else:
        problems = [f"the {source} raw file's {name}: {item!r:.80} lacks {missing}"
                    for name in WORK_LISTS[source] for item in raw[name]
                    if (missing := _raw_missing(source, item))]
    return problems or items_problems(source, work_items(source, raw), days)


def notion_searches_problems(searches, days):
    """Why `searches`, Notion's searches for created pages, aren't those of
    the period of `days`, empty when they are: each {start, end, results}, its
    results as the search returned them, a page with its title and url; their
    ranges covering the period day by day, with no gap or overlap, each within
    a calendar week; none full but a single day, marked "full": true; and no
    page found by two of them."""
    if not all(isinstance(search, dict) and set(search) - {"full"} == {"start", "end", "results"}
               and search.get("full", True) is True and isinstance(search["results"], list)
               and all(isinstance(result, dict) for result in search["results"]) for search in searches):
        return ['each Notion search must be {"start", "end", "results": [...]}, its results as it returned them']
    searches = sorted(searches, key=lambda search: str(search["start"]))
    pages = [result for search in searches for result in search["results"]
             if is_notion_page(result)]
    if not all(isinstance(page.get(key), str) for page in pages for key in ("title", "url")):
        return ["each page a Notion search returned must have its title and url, as the search gave them"]
    try:
        covered = [day for search in searches for day in days_between(
            search["start"], search["end"])]
    except (TypeError, ValueError):
        return ["each Notion search's start and end must be days as YYYY-MM-DD"]
    problems = [] if covered == days else [
        f"the Notion searches must cover {days[0]} to {days[-1]} day by day, with no gap or overlap"]
    for search in searches:
        span = f"the Notion search of {search['start']} to {search['end']}"
        if date.fromisoformat(search["start"]).isocalendar()[:2] != date.fromisoformat(search["end"]).isocalendar()[:2]:
            problems.append(
                f"{span} spans more than a calendar week: search week by week, Monday to Sunday")
        if "full" in search and search["start"] != search["end"]:
            problems.append(f"{span} is full, which only a search of a single day may be: search that range "
                            "again in shorter ranges")
        elif "full" not in search and len(search["results"]) >= NOTION_LIMIT:
            problems.append(f"{span} returned {NOTION_LIMIT} results, the most it returns, so some may be "
                            "missing: search that range again in shorter ranges")
    urls = [page["url"] for page in pages]
    return problems + [f"{url} was found by two Notion searches, so the creation filter can't be trusted: "
                       "search again" for url in sorted(set(urls)) if urls.count(url) > 1]


def is_notion_page(result):
    """Whether `result`, as Notion's search returned it, is a page of its own:
    not a database, nor a database's row, which has a parent data source."""
    return result.get("type") == "page" and not result.get("parent_data_source_url")


def _raw_missing(source, item):
    """The first of the RAW_ITEM_FIELDS of `source` that `item` lacks, such as
    "fields.status.name", a Jira issue's parent's included, or None."""
    missing = _missing(item, RAW_ITEM_FIELDS[source])
    if missing or source != "jira" or not item["fields"].get("parent"):
        return missing
    parent = _missing(item["fields"]["parent"], PARENT_FIELDS)
    return parent and f"fields.parent.{parent}"


def _missing(item, paths):
    """The first of `paths`, dotted keys such as "fields.status.name", that
    `item` doesn't hold, a value of null included, or None."""
    for path in paths:
        value = item
        for key in path.split("."):
            if not (isinstance(value, dict) and key in value):
                return path
            value = value[key]
    return None


def write_raw(prep, relative, text):
    """Writes `text` to the file `relative` of the prep `prep`'s _raw
    folder, through the shared writer; returns its path."""
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{RAW_DIR}/{relative}", (text + "\n").encode("utf-8"))
    return path


def read_raw_work(prep):
    """{source: raw}: every source's raw file of the prep `prep`, or None
    while one is missing."""
    paths = {source: os.path.join(
        prep_dir(prep), RAW_DIR, f"{source}.json") for source in WORK_LISTS}
    if not all(os.path.exists(path) for path in paths.values()):
        return None
    return {source: read_json(path) for source, path in paths.items()}


def build_work(raws, days):
    """work.json from `raws`, every source's raw file: for each source its
    items, its facts over `days` and, for those SEARCHED, each list's search
    address."""
    work = {}
    for source, raw in raws.items():
        lists = work_items(source, raw)
        work[source] = {
            **lists, **source_facts(source, lists, days), **search_urls(source, raw)}
    return work


def work_items(source, raw):
    """{list: items}: the items of `raw`, the raw file of `source`, as
    work.json records them, without the fields kept only to check them, and
    of Notion's results only the pages of their own."""
    if source == "jira":
        return {"created": [issue_item(raw["base_url"], issue, "created") for issue in raw["created"]],
                "resolved": [issue_item(raw["base_url"], issue, "resolutiondate") for issue in raw["resolved"]]}
    if source == "github":
        return {name: sorted((pr_item(pr, pr[stamp]) for pr in raw[name]), key=lambda item: (item["date"], item["url"]))
                for name, stamp in (("opened", "createdAt"), ("merged", "closedAt"))}
    return {"created": sorted(({"title": result["title"], "url": result["url"], "path": result.get("path") or "",
                                "between": [search["start"], search["end"]]}
                               for search in raw["created"] for result in search["results"] if is_notion_page(result)),
                              key=lambda page: (page["between"][0], page["url"]))}


def issue_item(base_url, issue, dated_by):
    """A Jira issue as work.json records it, its link on the site at
    `base_url`, dated by the day of its field `dated_by`. Its parent is kept
    with its type and title, as the main focus is worked out from the
    parents."""
    fields = issue["fields"]
    parent = fields.get("parent")
    return {"key": issue["key"], "title": fields.get("summary") or "", "type": fields["issuetype"]["name"],
            "parent": {"key": parent["key"], "title": parent["fields"].get("summary") or "",
                       "type": parent["fields"]["issuetype"]["name"]} if parent else None,
            "status": fields["status"]["name"], "url": browse_url(base_url, issue["key"]),
            "date": (fields[dated_by] or "")[:10]}


def pr_item(pr, stamp):
    """A pull request as work.json records it, dated by the day of `stamp`,
    a merged one by when it was closed, as gh's search gives no merge time
    and a merged search finds only merged ones."""
    return {"repo": pr["repository"]["nameWithOwner"], "number": pr["number"], "title": pr["title"],
            "url": pr["url"], "date": (stamp or "")[:10]}


def search_urls(source, raw):
    """{<list>_search_url: address}: for a SEARCHED source, the address of
    each list's search, Jira's JQL on its site or GitHub's query on
    github.com, which finds the same items live; {} for any other."""
    if source == "jira":
        return {f"{name}_search_url": f"{raw['base_url']}/issues/?jql={quote(raw[f'{name}_jql'])}"
                for name in WORK_LISTS[source]}
    if source == "github":
        return {f"{name}_search_url": f"https://github.com/search?q={quote(raw[f'{name}_query'])}&type=pullrequests"
                for name in WORK_LISTS[source]}
    return {}


def work_from_raw_problems(work, raws, days):
    """Why `work` isn't work.json as build_work() makes it from `raws`, every
    source's raw file, or None while one is missing, empty when it is."""
    if raws is None:
        return ["the work's raw files are missing: run fetch_work.py and set_notion.py again"]
    if any(raw_work_problems(source, raw, days) for source, raw in raws.items()):
        return ["the work's raw files break their rules: run fetch_work.py and set_notion.py again"]
    if work != build_work(raws, days):
        return ["work.json doesn't match the raw files it is built from: run fetch_work.py again"]
    return []


def prep_dir(prep):
    """The absolute path of the prep folder `prep` inside the skill's output
    folder. Exits if `prep` isn't a prep folder name, <Person>_<YY-MM-DD>,
    would lead outside it or doesn't exist."""
    if not DAY_FOLDER.fullmatch(prep):
        raise SystemExit(f"{prep!r} is not a prep folder, <Person>_<YY-MM-DD>")
    folder, _ = output_folder(FOLDER_NAME)
    path = target(folder, prep)
    if not os.path.isdir(path):
        raise SystemExit(
            f"{prep} doesn't exist in {folder}: run init_prep.py first")
    return path


def write_prep_file(prep, name, value):
    """Writes `value` as indented JSON to the file `name` of the prep folder
    `prep`, through the shared writer; returns the file's path."""
    path, _ = write_output_file(FOLDER_NAME, f"{prep}/{name}",
                                (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return path


def script_command(script):
    """The command that runs the skill's script `script`, by the folder the
    agent ran one of the skill's scripts from, so every command a task names
    matches the one the skill pre-approves."""
    # abspath, not realpath: the agent runs a script by the path the skill
    # pre-approves, which can be a symlink to the installed skill.
    ran = os.path.dirname(os.path.abspath(sys.argv[0]))
    here = os.path.dirname(os.path.realpath(__file__))
    folder = ran if os.path.realpath(ran) == here else here
    return f"python3 {os.path.join(folder, script)}"


def require_gh(run, what):
    """Exits, saying what to do, unless gh can be used and is signed in, as
    `run` runs it; `what` says what is fetched with it, such as "the
    person's pull requests are fetched"."""
    if not gh_available():
        raise SystemExit(
            f"gh isn't installed or the github-cli source isn't enabled: {what} with it")
    if not gh_signed_in(run):
        raise SystemExit(
            "gh isn't signed in: run gh auth login, then run this again")


def stdin_json(usage):
    """The JSON the agent wrote on stdin. Exits, showing `usage`, the input
    to send, when it isn't JSON."""
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise SystemExit(f"the input isn't JSON: {error}\n\n{usage}")


def person_problems(person, today):
    """Why `person` isn't a valid person.json on `today`, its sources aside,
    empty when it is: its fields are PERSON_FIELDS, the person is named by
    letters or digits, and the period's days are dates as YYYY-MM-DD of a
    period that can be reported on. Its sources follow sources_problems()."""
    if not isinstance(person, dict):
        return ["the person must be a JSON object"]
    problems = []
    if sorted(person) != sorted(PERSON_FIELDS):
        problems.append(f"the person's fields must be {', '.join(PERSON_FIELDS)}, "
                        f"not {', '.join(person) or 'none'}")
    name = person.get("person")
    if not isinstance(name, str) or not as_name(name):
        problems.append(f"{name!r} must name the person, such as Jane Doe")
    days = {}
    for field in ("start", "end"):
        value = person.get(field)
        try:
            days[field] = date.fromisoformat(
                value if isinstance(value, str) else "")
        except ValueError:
            problems.append(
                f"the period's {field}, {value!r}, must be a date as YYYY-MM-DD")
    if len(days) == 2 and (problem := period_problem(days["start"], days["end"], today)):
        problems.append(problem)
    return problems


def period_days(person):
    """Every day of the review's period in `person`, a prep's person.json, as
    YYYY-MM-DD."""
    return days_between(person["start"], person["end"])


def days_between(start, end):
    """Every day from `start` to `end`, both as YYYY-MM-DD, in the same form."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]


def months_of(first, last):
    """{YYYY-MM: {start, end}}: each month from `first` to `last`, its days
    within them, as YYYY-MM-DD."""
    months, day = {}, first
    while day <= last:
        following = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
        months[f"{day:%Y-%m}"] = {"start": day.isoformat(),
                                  "end": min(last, following - timedelta(days=1)).isoformat()}
        day = following
    return months


def sources_problems(sources, names):
    """Why `sources` doesn't say who the person is in each of the sources
    `names`, empty when it does: it has those sources, no others, and each
    holds its fields of SOURCES, each a text that isn't blank or, in
    LIST_FIELDS, a list of such texts, at least one, each once."""
    if not isinstance(sources, dict):
        return ["the sources must be a JSON object"]
    problems = []
    if sorted(sources) != sorted(names):
        problems.append(f"the sources must be {', '.join(names)}, "
                        f"not {', '.join(sources) or 'none'}")
    for source in names:
        if source not in sources:
            continue
        fields, found = SOURCES[source], sources[source]
        if not (isinstance(found, dict) and sorted(found) == sorted(fields)
                and all(_filled(found[field], field in LIST_FIELDS) for field in fields)):
            wanted = "{" + ", ".join(f'"{field}": ' + ('["...", ...]' if field in LIST_FIELDS else '"..."')
                                     for field in fields) + "}"
            problems.append(f"{source} must be {wanted}, not {found!r}")
    return problems


def _filled(value, is_list):
    """Whether `value` is a text that isn't blank or, `is_list`, a list of
    such texts, at least one, each once."""
    if not is_list:
        return _is_text(value)
    return (isinstance(value, list) and bool(value) and all(_is_text(item) for item in value)
            and len(set(value)) == len(value))


def _is_text(item):
    """Whether `item` is a text that isn't blank."""
    return isinstance(item, str) and bool(item.strip())


def name_words(text):
    """The words of a name, accents dropped and case folded, so José and jose
    are one word."""
    return [word for word in as_name(text).casefold().split("-") if word]


def company_names(key):
    """The names of the company setting `key`'s entries, such as each value
    of company.values, in the config's order."""
    return [next(iter(entry.values())) for entry in company_setting(key)]


def orientation_problems(orientation, values):
    """Why `orientation` isn't the summary of the manager's view, empty when
    it is, by summary_problems()."""
    return summary_problems(orientation, "the orientation", values)


def reviews_problems(reviews, ratings, values):
    """Why `reviews` aren't the previous reviews, empty when they are:
    pieces, by pieces_problems(), each with a rating too, null or one of
    `ratings`."""
    def rules(piece, what):
        if piece["rating"] is not None and piece["rating"] not in ratings:
            return [f"{what}'s rating, {piece['rating']!r}, must be one of the company's: "
                    f"{', '.join(ratings)}, or null when it gives none of them"]
        return []
    return pieces_problems(reviews, ("reviews", "review"), REVIEW_FIELDS, values, rules)


def feedback_problems(feedback, values):
    """Why `feedback` isn't the period's feedback, empty when it is: pieces,
    by pieces_problems()."""
    return pieces_problems(feedback, ("feedback", "feedback piece"), PIECE_FIELDS, values, lambda piece, what: [])


def pieces_problems(value, names, fields, values, rules):
    """Why `value` isn't a list of pieces, empty when it is, `names` naming
    them all and one, such as ("feedback", "feedback piece"): {"pieces": [...]}, none when there are none, each with
    `fields` and the parts of SUMMARY_PARTS, its period a text or null, its
    summary meeting summary_problems() with `values`, and each meeting
    `rules(piece, what)`, which gets the name to give it in a problem."""
    kind, item = names
    if not (isinstance(value, dict) and list(value) == ["pieces"] and isinstance(value["pieces"], list)):
        return [f'the {kind} must be {{"pieces": [...]}}, with [] when there are none']
    problems = []
    for number, piece in enumerate(value["pieces"], 1):
        what = f"{item} {number}"
        if not (isinstance(piece, dict) and sorted(piece) == sorted((*fields, *SUMMARY_PARTS))):
            problems.append(f"{what} must have the fields {', '.join((*fields, *SUMMARY_PARTS))}, "
                            f"with null for what it doesn't give")
            continue
        problems += summary_problems({part: piece[part]
                                     for part in SUMMARY_PARTS}, what, values)
        if not (piece["period"] is None or _is_text(piece["period"])):
            problems.append(f"{what}'s period, {piece['period']!r}, must be a text, such as "
                            "\"Mid Year Review 2026\", or null when it names none")
        problems += rules(piece, what)
    return problems


def notes_problems(notes, values, days):
    """Why `notes` aren't the summary of the manager's notes, empty when they
    are: summary_problems() with `days`, every day of the period, a context
    point's evidence undated when it comes from a page, which has no day."""
    return summary_problems(notes, "the notes summary", values, days, undated_context=True)


def slack_problems(slack, values, days):
    """Why `slack` isn't the summary of the person's Slack messages, empty
    when it is: summary_problems() with `days`, every day of the period."""
    return summary_problems(slack, "the Slack summary", values, days)


def work_problems(work, days):
    """Why `work` isn't the person's work, empty when it is: for each source
    of WORK_LISTS, its lists, by items_problems(), its FACT_KEYS, matching the
    items, and, for those SEARCHED, each list's search address."""
    if not (isinstance(work, dict) and sorted(work) == sorted(WORK_LISTS)):
        return [f"the work must hold {', '.join(WORK_LISTS)}"]
    problems = []
    for source, lists in WORK_LISTS.items():
        keys = work_keys(source)
        if not (isinstance(work[source], dict) and sorted(work[source]) == sorted(keys)
                and all(isinstance(work[source][name], list) for name in lists)):
            problems.append(f"the work's {source} must hold {', '.join(keys)}")
            continue
        problems += items_problems(source,
                                   {name: work[source][name] for name in lists}, days)
    if problems:
        return problems
    return [f"the work's {source} facts don't match its items: run fetch_work.py again, which builds it anew"
            for source, lists in WORK_LISTS.items()
            if any(work[source][key] != value for key, value in source_facts(
                source, {name: work[source][name] for name in lists}, days).items())]


def work_keys(source):
    """What the work of `source` holds: its lists, its FACT_KEYS and, when it
    is SEARCHED, each list's <list>_search_url."""
    return (*WORK_LISTS[source], *FACT_KEYS[source],
            *(f"{name}_search_url" for name in WORK_LISTS[source] if source in SEARCHED))


def items_problems(source, lists, days):
    """Why `lists`, {list: items} of `source`, don't follow their rules,
    empty when they do: each item an object with a title, a link and a date,
    one of `days`, but a created Notion page, `between`, two of them, a Notion
    page with its path too, and listed once."""
    problems = []
    for name, items in lists.items():
        problems += [f"the work's {source} {name}: {item!r:.80} needs a title, a link"
                     + (", its path" if source == "notion" else "")
                     + (" and the range it was found in, within the period" if (source, name) == ("notion", "created")
                        else " and a day in the period")
                     for item in items if not _is_work_item(source, name, item, days)]
        urls = [item.get("url") for item in items if isinstance(item, dict)]
        problems += [f"the work's {source} {name} lists {url} more than once"
                     for url in sorted(set(urls), key=str) if urls.count(url) > 1]
    return problems


def _is_work_item(source, name, item, days):
    """Whether `item` of the list `name` of `source` follows its rules."""
    if (source, name) == ("notion", "created"):
        return (_is_item(item, days, dated=False) and isinstance(item.get("path"), str)
                and isinstance(item.get("between"), list) and len(item["between"]) == 2
                and all(day in days for day in item["between"]))
    return _is_item(item, days, dated=True) and (source != "notion" or isinstance(item.get("path"), str))


def _is_item(item, days, dated):
    """Whether `item` is an object with a title, a link and, when `dated`, a
    date, one of `days`. A link is a web address, http or https: a Jira
    item's is made from the site's base-url, which a self-hosted site may
    serve over http."""
    return (isinstance(item, dict) and _is_text(item.get("title"))
            and str(item.get("url", "")).startswith(("http://", "https://"))
            and (not dated or item.get("date") in days))


def source_facts(source, lists, days):
    """The facts of `lists`, the items of `source`, in the period of `days`,
    as FACT_KEYS names them: counts, how many items each list holds; for
    Jira, created_by_type and resolved_by_type, the issues of each type, most
    first, and focus, the main focus of the resolved issues."""
    facts: dict = {"counts": {name: len(items)
                              for name, items in lists.items()}}
    if source == "jira":
        facts |= {"created_by_type": by_type(lists["created"]), "resolved_by_type": by_type(lists["resolved"]),
                  "focus": focus(lists["resolved"])}
    return facts


def by_type(issues):
    """[{type, issues}]: how many of `issues` there are of each type, most
    first, then by type."""
    types = {}
    for issue in issues:
        types[issue["type"]] = types.get(issue["type"], 0) + 1
    return [{"type": kind, "issues": count} for kind, count in sorted(types.items(), key=lambda pair: (-pair[1], pair[0]))]


def focus(resolved):
    """The main focus of the issues `resolved`: the fewest of their parents,
    the most issues first, whose issues are at least FOCUS_SHARE of those
    with a parent, with every parent tied with the last one, each {key,
    title, issues}; or, when none has a parent, their projects the same way,
    the title null. A fixed number of parents would give someone who works
    on two as long a list as someone who works on eight."""
    with_parent = [issue for issue in resolved if issue["parent"]]
    counts = {}
    for issue in with_parent or resolved:
        key, title = ((issue["parent"]["key"], issue["parent"]["title"]) if with_parent
                      else (issue["key"].rsplit("-", 1)[0], None))
        counts[(key, title)] = counts.get((key, title), 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0][0]))
    total, covered, cutoff = sum(counts.values()), 0, 0
    for _, count in ranked:
        covered += count
        if covered >= FOCUS_SHARE * total:
            cutoff = count
            break
    return [{"key": key, "title": title, "issues": count} for (key, title), count in ranked if count >= cutoff]


def summary_problems(summary, what, values, days=None, undated_context=False):
    """Why `summary`, the summary of `what`, such as "the orientation", doesn't
    have the parts of SUMMARY_PARTS, empty when it does: each a list of
    points, a point of VALUED_PARTS {"point", "values"}, its values up to
    MAX_VALUES of `values`, each once, any other a text; each point's text
    not blank, of at most MAX_POINT_WORDS words, and listed once, with at
    least one point in all. With `days`, the days the source was read on as
    YYYY-MM-DD, it is a reading's summary: every point, context too, has
    "evidence", what it rests on, each {date, link} with its link once, the
    date one of `days`, or null in a context point with `undated_context`,
    as one from an undated page; and it may be empty, as a source may hold
    nothing to say."""
    if not (isinstance(summary, dict) and sorted(summary) == sorted(SUMMARY_PARTS)):
        found = ", ".join(summary) if isinstance(
            summary, dict) else repr(summary)
        return [f"{what} must have the parts {', '.join(SUMMARY_PARTS)}, not {found or 'none'}"]
    problems = []
    for part, points in summary.items():
        fields = point_fields(part, "evidence" if days is not None else None)
        if not (isinstance(points, list) and all(is_point(point, fields) for point in points)):
            problems.append(
                f"{what}'s {part} must be a list of points, each {point_shape(fields)}, or [] for none")
            continue
        texts = [point["point"] if fields else point for point in points]
        problems += [f"{what}'s {part} lists {text!r} more than once: list each once"
                     for text in sorted(set(texts)) if texts.count(text) > 1]
        problems += [f"{what}'s {part}: {text[:60]!r}... has {word_count(text)} words: keep a point to a "
                     f"sentence of about {POINT_WORDS}, at most {MAX_POINT_WORDS}, or split it"
                     for text in texts if word_count(text) > MAX_POINT_WORDS]
        if "values" in fields:
            problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s values, {point['values']!r}, must each "
                         f"be one of the company's: {', '.join(values)}, listed once, at most {MAX_VALUES}, or [] "
                         "when none fits"
                         for point in points if len(point["values"]) > MAX_VALUES
                         or len(set(point["values"])) != len(point["values"]) or not set(point["values"]) <= set(values)]
        if "evidence" in fields:
            undated = part not in VALUED_PARTS and undated_context
            allowed = {*(days or []), *([None] if undated else [])}
            problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s evidence must each be of a day the source "
                         f"was read on{', or null for an undated page' if undated else ''}, each link once"
                         for point in points if not {item["date"] for item in point["evidence"]} <= allowed
                         or len({item["link"] for item in point["evidence"]}) != len(point["evidence"])]
    if not problems and days is None and not any(summary.values()):
        problems.append(
            f"{what} has no points: summarise what it says in its parts")
    return problems


def point_fields(part, evidence=None):
    """The fields of a point of `part`: point, then values in VALUED_PARTS,
    and `evidence`, the field naming what it rests on in a reading's summary,
    links in the merge's answer; none, a sentence alone, for a context point
    with no evidence."""
    valued = part in VALUED_PARTS
    if not (valued or evidence):
        return ()
    return ("point", *(("values",) if valued else ()), *((evidence,) if evidence else ()))


def point_shape(fields):
    """How a point with `fields` is written, for an error: a sentence when it
    has none."""
    shapes = {"point": '"..."', "values": '["...", ...] or []',
              "evidence": '[{"date": "YYYY-MM-DD", "link": "https://... or file://..."}, ...]',
              "links": '["https://... or file://...", ...]'}
    return "{" + ", ".join(f'"{field}": {shapes[field]}' for field in fields) + "}" if fields else "a sentence"


def is_point(point, fields):
    """Whether `point` is a point with `fields`: an object of them, its point
    a text that isn't blank, its values a list of texts, its evidence a list
    of at least one {date, link}, the date a text or null, and its links,
    the merge's, a list of at least one text; with no fields, such a text
    alone."""
    if not fields:
        return _is_text(point)

    def listed(key, at_least_one, each):
        return isinstance(point[key], list) and (bool(point[key]) or not at_least_one) and all(map(each, point[key]))
    return (isinstance(point, dict) and sorted(point) == sorted(fields) and _is_text(point["point"])
            and ("values" not in point or listed("values", False, lambda value: isinstance(value, str)))
            and ("evidence" not in point or listed("evidence", True, _is_evidence))
            and ("links" not in point or listed("links", True, lambda link: isinstance(link, str))))


def _is_evidence(item):
    """Whether `item` is a piece of a point's evidence: {date, link}, the date
    a text or null, the link a web or file address."""
    return (isinstance(item, dict) and sorted(item) == ["date", "link"]
            and (item["date"] is None or isinstance(item["date"], str))
            and isinstance(item["link"], str) and item["link"].startswith(LINK_SCHEMES))
