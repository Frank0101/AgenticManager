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

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.batch import gather  # noqa: E402,F401
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
# A point's links: a Slack message's address, or a note's file.
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
# The person's work in the period, in Jira, GitHub and Notion: the items
# themselves, each with its title, date and link, for the writing step to
# cite. Each source is written by its own script, which keeps the others'. Once all are in, the
# facts, counts by month and by area, are worked out from the items, once,
# and a subagent's commentary on each source reads them: the figures are the
# script's, the reading of them, volume, focus and how they shifted, the
# commentary's. Notion's search filters by creation date but returns only the
# last edit's, so a created page is dated by the range it was found in,
# `between`, and an edited one by its last edit; `path` is where it sits.
WORK = "work.json"
WORK_LISTS = {"jira": ("resolved", "open"), "github": (
    "opened", "merged"), "notion": ("created", "edited")}
FACTS = "facts"
COMMENTARY = "commentary"
MAIN_AREAS = 3
COMMENTARY_WORDS = 80
MAX_COMMENTARY_WORDS = 120
# What the person's Slack messages show, read by subagents a month each and
# merged, every point with the days and links it rests on.
SLACK = "slack.json"
# What each reading by subagents gathered, the tasks they were given and what
# they answered, a folder per source, kept so a summary can be traced back to
# the notes and synopses it came from.
RAW_DIR = "_raw"


def expected_files():
    """Every file a prep folder holds, and nothing else: the person, the
    period and who they are in each source, the manager's view of them, their previous
    reviews, the period's feedback, the manager's notes on them, what their Slack
    messages show, their work in Jira, GitHub and Notion, and the _raw folder
    of what the subagents were shown and wrote."""
    return {PERSON, ORIENTATION, REVIEWS, FEEDBACK, NOTES, SLACK, WORK, RAW_DIR}


def write_raw(prep, relative, text):
    """Writes `text` to the file `relative` of the prep `prep`'s _raw
    folder, through the shared writer; returns its path."""
    path, _ = write_output_file(
        FOLDER_NAME, f"{prep}/{RAW_DIR}/{relative}", (text + "\n").encode("utf-8"))
    return path


def write_work(prep, sources, days):
    """Writes the sources `sources`, such as {"notion": {...}}, to the prep
    `prep`'s work.json, keeping the other sources there and dropping the
    facts and commentary, which no longer match; returns the file's path.
    Exits, writing nothing, when the work breaks a rule, `days` the
    period's."""
    path = os.path.join(prep_dir(prep), WORK)
    work = read_json(path) if os.path.exists(path) else {}
    work = {name: value for name, value in {
        **work, **sources}.items() if name in WORK_LISTS}
    if problems := work_problems(work, days, final=False):
        raise SystemExit("; ".join(problems))
    return write_prep_file(prep, WORK, work)


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
    """Every day from `start` to `end`, both as YYYY-MM-DD, as YYYY-MM-DD."""
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
    are: summary_problems() with `days`, every day of the period, every point
    linked to its notes, a context point's dates empty when it comes from a
    page, which has no day."""
    return summary_problems(notes, "the notes summary", values, days, linked=True, undated_context=True)


def slack_problems(slack, values, days):
    """Why `slack` isn't the summary of the person's Slack messages, empty
    when it is: summary_problems() with `days`, every day of the period, and
    every point linked."""
    return summary_problems(slack, "the Slack summary", values, days, linked=True)


def work_problems(work, days, final=True):
    """Why `work` isn't the person's work, empty when it is: for each source
    of WORK_LISTS, its lists, each item an object with a
    title, a link and a date, one of `days`, but an open issue, undated, and
    a created Notion page, `between`, two of them, a Notion page with its
    path too, and listed once; then facts that match the items, and a
    commentary. Unless `final`, a source not yet gathered, the facts and the
    commentary may be missing."""
    keys = [*WORK_LISTS, FACTS, COMMENTARY]
    if not (isinstance(work, dict) and set(work) <= set(keys)):
        return [f"the work may hold only {', '.join(keys)}"]
    if final and (missing := [key for key in keys if key not in work]):
        return [f"the work is missing {', '.join(missing)}"]
    problems = []
    for source, lists in WORK_LISTS.items():
        if source not in work:
            continue
        found = work[source]
        if not (isinstance(found, dict) and sorted(found) == sorted(lists)
                and all(isinstance(found[name], list) for name in lists)):
            problems.append(
                f"the work's {source} must have the lists {', '.join(lists)}")
            continue
        for name in lists:
            problems += [f"the work's {source} {name}: {item!r:.80} needs a title, a link"
                         + (", its path" if source == "notion" else "")
                         + (" and the range it was found in, within the period" if name == "created"
                            else "" if name == "open" else " and a day in the period")
                         for item in found[name] if not _is_work_item(source, name, item, days)]
            urls = [item.get("url")
                    for item in found[name] if isinstance(item, dict)]
            problems += [f"the work's {source} {name} lists {url} more than once"
                         for url in sorted(set(urls), key=str) if urls.count(url) > 1]
    if problems:
        return problems
    if FACTS in work and work[FACTS] != work_facts(work, days):
        problems.append(
            "the work's facts don't match its items: run work_commentary.py start again")
    if COMMENTARY in work:
        problems += commentary_problems(work[COMMENTARY])
    return problems


def _is_work_item(source, name, item, days):
    """Whether `item` of the list `name` of `source` follows its rules."""
    if name == "created":
        return (_is_item(item, days, dated=False) and isinstance(item.get("path"), str)
                and isinstance(item.get("between"), list) and len(item["between"]) == 2
                and all(day in days for day in item["between"]))
    return _is_item(item, days, dated=name != "open") and (source != "notion" or isinstance(item.get("path"), str))


def _is_item(item, days, dated):
    """Whether `item` is an object with a title, a link and, when `dated`, a
    date, one of `days`. A link is a web address, http or https: a Jira
    item's is made from the site's base-url, which a self-hosted site may
    serve over http."""
    return (isinstance(item, dict) and _is_text(item.get("title"))
            and str(item.get("url", "")).startswith(("http://", "https://"))
            and (not dated or item.get("date") in days))


def work_facts(work, days):
    """The facts of the work `work` in the period of `days`, for each source:
    by_month, each month's count of each list,
    open issues aside as they have no date, of areas, how many it touched,
    and main_areas, the MAIN_AREAS it touched most, each with its count of
    items, so a shift in focus shows by month; and by_area, each area's count of each list, most first. An
    issue's area is its parent, "no parent" when it has none; a pull
    request's, its issue's, or its repository when no issue lists it; a
    Notion page's, where it sits."""
    months = sorted({day[:7] for day in days})
    issues = {item["key"]: item for name in WORK_LISTS["jira"]
              for item in work["jira"][name]}

    def parent_area(issue):
        parent = issue.get("parent")
        return ("no parent", None, None) if not parent else (parent["type"], parent["key"], parent["title"])

    def area(source, item):
        if source == "jira":
            return parent_area(item)
        if source == "notion":
            return ("location", None, item["path"] or None)
        issue = issues.get(item.get("issue") or "")
        return ("repository", None, item["repo"]) if issue is None else parent_area(issue)

    def month(name, item):
        return (item["between"][0] if name == "created" else item["date"])[:7]

    facts = {}
    for source, lists in WORK_LISTS.items():
        dated = [name for name in lists if name != "open"]
        by_month = []
        for this in months:
            items = [(name, item) for name in dated for item in work[source]
                     [name] if month(name, item) == this]
            touched = {}
            for _, item in items:
                touched[area(source, item)] = touched.get(
                    area(source, item), 0) + 1
            by_month.append({"month": this, **{name: sum(1 for n, _ in items if n == name) for name in dated},
                             "areas": len(touched),
                             "main_areas": [{"area": title or key or kind, "items": count}
                                            for (kind, key, title), count in sorted(
                                                touched.items(), key=lambda pair: (-pair[1], str(pair[0])))[:MAIN_AREAS]]})
        counts = {}
        for name in lists:
            for item in work[source][name]:
                counts.setdefault(area(source, item), dict.fromkeys(lists, 0))[
                    name] += 1
        by_area = [{"kind": kind, "key": key, "title": title, **numbers}
                   for (kind, key, title), numbers in sorted(counts.items(),
                                                             key=lambda pair: (-sum(pair[1].values()), str(pair[0])))]
        facts[source] = {"by_month": by_month, "by_area": by_area}
    return facts


def commentary_problems(commentary):
    """Why `commentary` isn't the commentary on the work, empty when it is:
    for each source of WORK_LISTS, a text of at most MAX_COMMENTARY_WORDS
    words."""
    if not (isinstance(commentary, dict) and sorted(commentary) == sorted(WORK_LISTS)):
        return [f"the commentary must have {', '.join(WORK_LISTS)}"]
    problems = []
    for source in WORK_LISTS:
        text = commentary[source]
        if not _is_text(text) or word_count(text) > MAX_COMMENTARY_WORDS:
            problems.append(f"the commentary's {source} must be a paragraph of about {COMMENTARY_WORDS} words, "
                            f"at most {MAX_COMMENTARY_WORDS}")
    return problems


def summary_problems(summary, what, values, days=None, linked=False, undated_context=False, read_links=None):
    """Why `summary`, the summary of `what`, such as "the orientation", doesn't
    have the parts of SUMMARY_PARTS, empty when it does: each a list of
    points, a point of VALUED_PARTS {"point", "values"}, its values up to
    MAX_VALUES of `values`, each once, any other a text; each point's text
    not blank, of at most MAX_POINT_WORDS words, and listed once, with at
    least one point in all. With `days`, the days the source was read on as
    YYYY-MM-DD, a point of VALUED_PARTS also has "dates", the days it was
    seen on, each one of `days`, and the summary may be empty, as a source
    may hold nothing to say. `linked` gives every point, context too,
    "links", the addresses of what it rests on, a web or a file address, and
    "dates", empty for a context point only with `undated_context`, as one
    from an undated page; with
    `read_links`, each link one of them, the links of what was read."""
    if not (isinstance(summary, dict) and sorted(summary) == sorted(SUMMARY_PARTS)):
        found = ", ".join(summary) if isinstance(
            summary, dict) else repr(summary)
        return [f"{what} must have the parts {', '.join(SUMMARY_PARTS)}, not {found or 'none'}"]
    problems = []
    for part, points in summary.items():
        fields = point_fields(part, days is not None, linked)
        undated = part not in VALUED_PARTS and undated_context
        if not (isinstance(points, list) and all(_is_point(point, fields, undated) for point in points)):
            shape = ("{" + ", ".join(f'"{field}": ' + {"point": '"..."', "values": '["...", ...] or []',
                                                       "dates": '["YYYY-MM-DD", ...]',
                                                       "links": '["https://... or file://...", ...]'}[field] for field in fields)
                     + "}" if fields else "a sentence")
            problems.append(
                f"{what}'s {part} must be a list of points, each {shape}, or [] for none")
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
        if "dates" in fields:
            problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s dates, {point['dates']!r}, must each be a "
                         "day the source was read on, listed once"
                         for point in points if len(set(point["dates"])) != len(point["dates"])
                         or not set(point["dates"]) <= set(days or [])]
        if "links" in fields and read_links is not None:
            problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s links must each be the link of something "
                         "read, as its synopsis gives it"
                         for point in points if not set(point["links"]) <= set(read_links)]
    if not problems and days is None and not any(summary.values()):
        problems.append(
            f"{what} has no points: summarise what it says in its parts")
    return problems


def point_fields(part, dated, linked):
    """The fields of a point of `part`: point, then values in VALUED_PARTS,
    dates when the summary is `dated` and the point valued or `linked`, and
    links when `linked`; none, a sentence alone, for a context point of a
    summary that isn't linked."""
    valued = part in VALUED_PARTS
    if not (valued or linked):
        return ()
    return ("point", *(("values",) if valued else ()), *(("dates",) if dated else ()),
            *(("links",) if linked else ()))


def _is_point(point, fields, undated=False):
    """Whether `point` is a point with `fields`: an object of them, its point
    a text that isn't blank, its values a list of texts, its dates a list of
    texts, at least one unless `undated`, and its links a list of web or file
    addresses, at least one; with no fields, such a text alone."""
    if not fields:
        return _is_text(point)

    def texts(key, at_least_one):
        return (isinstance(point[key], list) and (bool(point[key]) or not at_least_one)
                and all(isinstance(item, str) for item in point[key]))
    return (isinstance(point, dict) and sorted(point) == sorted(fields) and _is_text(point["point"])
            and ("values" not in point or texts("values", False))
            and ("dates" not in point or texts("dates", not undated))
            and ("links" not in point or (texts("links", True) and all(link.startswith(LINK_SCHEMES)
                                                                       for link in point["links"]))))
