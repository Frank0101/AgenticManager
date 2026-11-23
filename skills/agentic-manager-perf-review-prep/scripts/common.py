"""What the skill's scripts share: the prep folder's name and the closed set of
files it holds, how to find a prep's folder, the person a prep is for, the
review's period and its days and months, who the person is in each source,
the parts every summary has, the current manager feedback, the period's other
feedback, the previous feedback, the manager's notes, the person's work in Jira, GitHub and
Notion, their Slack messages, and the report's constants and how it writes a
figure. The rules of each file are one function, applied when it is written
and by the final check, so the two can't differ. Scripts import the shared
library's names from here, so they don't depend on the order of their imports.
"""
from datetime import date, timedelta
from urllib.parse import quote
import os
import re
import sys

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.commands import library_command, script_command, stdin_json  # noqa: E402,F401
from agentic_manager.config import company_setting  # noqa: E402,F401
from agentic_manager.json_path import is_number  # noqa: E402,F401
from agentic_manager.failures import stops_on_failure  # noqa: E402,F401
from agentic_manager.github import authored_searches, commit_authors, gh_orgs, profile_name, dated_query, pull_search_url, require_gh, search_pulls, selection  # noqa: E402,F401
from agentic_manager.jira import JiraClient, browse_url, is_sub_task, plain_text, project_of, search_url as jira_search_url  # noqa: E402,F401
from agentic_manager.logseq import descendants, graph_path, journal_day, links, notes, page_aliases, page_title, parse_blocks  # noqa: E402,F401
from agentic_manager.output_file import json_text, read_json, write_output_file, write_output_json  # noqa: E402,F401
from agentic_manager.protocol import fill as fill_protocol  # noqa: E402,F401
from agentic_manager.output_folder import CHARTS_DIR, RAW_DIR, clear_folder, folder_problem, new_run, run_document, run_folder, work_folder  # noqa: E402,F401
from agentic_manager.period import add_period_arguments, calendar_weeks, calendar_week, days, is_day, months_of, period_problem, shown  # noqa: E402,F401
from agentic_manager.tasks import submit_section, task_line, write_task as write_task_file  # noqa: E402,F401
from agentic_manager.svg import GRID, SURFACE, INK, MUTED, arc_segment, esc, legend, nice_step, svg, text, text_width  # noqa: E402,F401
from agentic_manager.text import CHART_IMAGE, SMALL_TYPE, ai_marked, chart_image, html_table, as_name, number, plural, word_count  # noqa: E402,F401

# How to write a point and pick its values, with their examples, lives in the
# protocol's shared part _point.md, the one place for them: the notes' and Slack's tasks
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
# The last day the manager's notes were read to, set only when a change to a
# finished prep reads them up to today, as notes written after the period,
# such as before a calibration, still speak of it; without it, the notes are
# the period's, as everything else.
NOTES_END = "notes_end"
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
# Every summary the skill records, of the current manager feedback, the other and
# the previous feedback, the notes or Slack, has the same parts, so each reads, and is
# compared with the evidence, the same way: each a list of points in the agent's words, a part
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
# A point is written to up to POINT_WORDS words; only one of more than
# MAX_POINT_WORDS, a margin the agent never sees, is refused, as an agent
# told a ceiling writes up to it.
POINT_WORDS = 30
MAX_POINT_WORDS = 40
MAX_VALUES = 2
# A description of a conversation a reader lists is told DESCRIPTION_WORDS, and
# only one of more than MAX_DESCRIPTION_WORDS, a margin the agent never
# sees, is refused, as points are: it carries more than a point does.
DESCRIPTION_WORDS = 50
MAX_DESCRIPTION_WORDS = 65
# The limits the protocol's point rules give, filled from the above.
POINT_LIMITS = {"point_words": POINT_WORDS, "max_values": MAX_VALUES}
VALUES = "values"
# A point's evidence links: a Slack message's address, or a note's file, by
# its absolute path, which a Markdown preview opens where a file:// address
# isn't.
WEB_LINK = "https://"
SUMMARY_HELP = "\n".join(
    f"  {part:<11} {meaning}, each point "
    + ('{"point": "...", "values": ["..."]}, values every company value it clearly shows or calls for, as rules.py prints '
       f'them, at most {MAX_VALUES}, or [] when none fits' if part in VALUED_PARTS else "a sentence")
    for part, meaning in SUMMARY_PARTS.items())
# What the manager gives is one text each, summarised in the
# same parts the same way, so only its file tells them apart: their current
# feedback on the person; the other feedback the person got
# in the period, such as 1:1s, OKRs or kudos, read with judgment, never
# tracked as commitments; and the previous feedback, usually the previous
# official review, which the period is compared with. A text may say nothing
# of the person, so a summary may have no points.
MANAGER_FEEDBACK = "manager_feedback.json"
OTHER_FEEDBACK = "other_feedback.json"
PREVIOUS_FEEDBACK = "previous_feedback.json"
FEEDBACK_FILES = {"manager": MANAGER_FEEDBACK,
                  "other": OTHER_FEEDBACK, "previous": PREVIOUS_FEEDBACK}
# What each is called, as the manager is asked for it, in the report and in
# every problem.
FEEDBACK_NAMES = {"manager": "current manager feedback",
                  "other": "other feedback", "previous": "previous feedback"}
# The manager's own notes on the person in their vault: from the journals of
# the days notes_days() gives, what they noticed, each point with the days it was seen on and
# the notes' files, a pattern one point with all of them; from the person's
# pages, only context, which has no date. Read by one subagent.
NOTES = "notes.json"
# The person's work in the period, in Jira, GitHub and Notion. Each source's
# script writes what it gathered to its raw file, _raw/<source>.json: Jira's
# issues and GitHub's pull requests as their APIs return them, with the
# period and the searches that found them, so whose each item is, and why it
# is there, can be checked again without searching again; Notion's searches,
# which only the agent reaches, with their results as returned. build_data.py
# builds data.json from them, the one model the report reads: each item, with
# its title, date and link, built here, and every fact worked out from them.
DATA = "data.json"
WORK_LISTS = {"jira": ("created", "resolved"), "github": (
    "opened", "merged"), "notion": ("created",)}
# What a raw file holds beside its lists: the period and, for each list, the
# search that found it, Jira's JQL or GitHub's query on github.com, whose
# org: terms are alternatives; and Jira's story points fields, every one the
# site has, as projects may estimate in different ones, an issue's points the
# first of them it has.
RAW_FIELDS = {"jira": ("start", "end", "base_url", "points_fields", "created_jql", "resolved_jql", "parents"),
              "github": ("start", "end", "orgs", "opened_query", "merged_query"), "notion": ()}
# The fields of a raw item data.json is built from, a pull request's size
# included, and those kept only to check whose it is: Jira's assignee,
# reporter and updated, GitHub's author and updatedAt. A parent, which Jira leaves out when an issue has none,
# needs its own.
RAW_ITEM_FIELDS = {"jira": ("key", "fields.summary", "fields.issuetype.name", "fields.status.name",
                            "fields.created", "fields.resolutiondate", "fields.assignee",
                            "fields.reporter", "fields.updated"),
                   "github": ("number", "title", "repository.nameWithOwner", "url", "createdAt", "mergedAt",
                              "additions", "deletions", "changedFiles", "author.login", "updatedAt")}
PARENT_FIELDS = ("key", "fields.summary", "fields.issuetype.name")
# Notion's search filters by creation date but returns only the last edit's,
# so a created page is dated by the range of the search that found it,
# `between`, a calendar week at most; `path` is where it sits. A search
# returns at most NOTION_LIMIT results, rows included, and no next page, so
# a full one is searched again in shorter ranges; a single day can't be
# split, so one still full keeps what it found. A database's rows aren't
# pages of their own.
NOTION_LIMIT = 50
# The share of the resolved issues the main focus covers.
FOCUS_SHARE = 0.8
# The most epics, or repositories, the charts give a colour of their own:
# those holding the most work, the rest drawn together as others, so a
# legend stays readable and no two share a colour.
MAX_GROUPS = 9
# A merged pull request's size is the lines it changed, which tell a large
# change from a small one better than files, which a rename moves by the
# hundred; their distribution is counted on a log scale, as sizes run from a
# few lines to many thousands, in BINS_PER_DECADE bins for each power of
# ten: fewer would blur its shape, more make it ragged.
BINS_PER_DECADE = 4
# What the person's Slack messages show, read a month at a time by subagents and
# judged by another, every point with the days and links it rests on.
SLACK = "slack.json"
# The library's RAW_DIR holds what each source gave: the notes read and the
# conversations found, kept so a summary can be traced back to what it rests
# on, and the raw file of each source of the work. The
# report, <Person>_Review_Prep.md, is drawn from the files above, and
# CHARTS_DIR holds the charts it shows, each a view of data.json, as SVG.
REPORT_KIND = "Review_Prep.md"
# The Jira cells of the report, in order: each a fact's figure, linked to
# its search, with what it is made of, and below it its chart.
JIRA_CELLS = (("created", "jira_created_over_time.svg"), ("resolved", "jira_resolved_over_time.svg"),
              ("resolved_points", "jira_story_points.svg"))
# Each figure's heading, which its chart's axis repeats.
HEADINGS = {"created": "Issues created", "resolved": "Issues resolved", "resolved_points": "SP resolved",
            "opened": "PRs created", "merged": "PRs merged", "merged_lines": "PRs size"}
# The Notion section's heading of its table of the pages created.
PAGES_HEADING = "Pages created"
# The Observations section: under its heading, OBSERVATIONS_SUBTITLE, the
# script's, so not marked as the agent's, then each part, by its heading, in
# order, its points folded under the agent's summaries.
# A valued part groups each point under the first company value it names, the
# one it shows most, so it shows once, the second value it names beside it,
# the values with the most points first, those naming none under NO_VALUE,
# last, as it is no value: a fold for each value summarised, one under the
# ALSO heading for the points under no value, then the points no summary
# covers, grouped by value; context names no value, so its points are one
# fold, not grouped. Each point's source, by the summary file it comes from, as the
# report names it; and what a reading's reference names, by its source,
# beside the day it was seen on, or a page, which has no day, by its title.
OBSERVATION_HEADINGS = {"going_well": "Going well",
                        "to_improve": "To improve", "context": "Context"}
OBSERVATIONS_SUBTITLE = ("*What the current manager feedback, the period's other feedback, the manager's notes and "
                         "Slack show, by company value.*")
NO_VALUE = "No value"
# The heading over the summary of the points under no value, after the
# values' summaries.
ALSO = "Also"
# What the fold under a valued part's summaries holds: the points no summary
# covers, those of a value left unsaid and, with no ALSO summary, those under no
# value, so every point is still one fold away.
OTHER_POINTS = ("other point", "other points")
OBSERVATION_SOURCES = {"manager": "Manager feedback", "other": "Other feedback",
                       "notes": "Manager's notes", "slack": "Slack"}
REFERENCE_NAMES = {"notes": "Journal", "slack": "Slack"}
PAGE_REFERENCE = "Page"
# The summaries recorded for a prep, by name: the three feedbacks, the previous
# one being what the period is compared with, and those the observations'
# points come from.
SUMMARY_FILES = {**FEEDBACK_FILES, "notes": NOTES, "slack": SLACK}
# Every point of the period and of the previous feedback has an id, by its
# part and its place in the table's order, the previous feedback's prefixed,
# such as G1 and P-I2: the step change cites them, so they name a point the
# report then shows as the tables do, never a text the agent retyped.
POINT_IDS = {"going_well": "G", "to_improve": "I", "context": "C"}
PREVIOUS_ID = "P-"
# A point's id written in a text, which only the rows' evidence may hold: the
# report shows a cited point by its text, so an id in a summary means nothing.
POINT_ID_TEXT = re.compile(
    rf"\b(?:{PREVIOUS_ID})?[{''.join(POINT_IDS.values())}]\d+\b")
# The step change: how the period compares with the previous feedback,
# the baseline, a point of it to a row, each change one of STEP_CHANGES, in
# the report's order, with its label. A to-improve point of the previous feedback always
# has a row, as the manager needs to know where each stands; one the period
# no longer raises counts as improved, said as not raised again rather than
# as a proven change. A going-well point has one only when the period shows
# it held or worsened, and context only for a significant change: a context
# point of the previous feedback that changed, or, a row with no previous point, by the None
# key, a period context point the previous feedback didn't have, standing for itself.
STEP_CHANGE_HEADING = "Step change"
STEP_CHANGES = {"improved": "Improved", "still_to_improve": "Still to improve", "worsened": "Worsened",
                "held": "Held", "context_change": "Context changed", "new_context": "New context"}
STEP_CHANGE_PARTS = {"going_well": ("held", "worsened"), "to_improve": ("improved", "still_to_improve", "worsened"),
                     "context": ("context_change",), None: ("new_context",)}
STEP_CHANGE_ROW = ("previous_point", "change", "evidence")
# The agent's summaries of the observations: in going well and to improve,
# one for each company value it judges worth saying, by the value's name,
# and a line on the points under no value that matter, or null; in context,
# a text. The report shows each value's in the table's order, the script's.
OBSERVATIONS_SHAPE = ('{"going_well": {"values": {"<company value>": "...", ...}, "also": "..." or null}, '
                      '"to_improve": {"values": {...}, "also": null}, "context": "..."}')
STEP_CHANGE_SHAPE = ('{"summary": "...", "rows": [{"previous_point": "P-I1", "change": "improved", '
                     '"evidence": ["I2", ...]}, ...]}')
NOT_RAISED = "Not raised again in the period"
# The step change with no previous feedback says so alone, and why, without
# its subtitle, which describes a step change that isn't there. A previous
# feedback with no points is as good as none.
STEP_CHANGE_NOT_APPLICABLE = "N/A: no previous feedback to compare with"
STEP_CHANGE_SUBTITLE = ("*How the period compares with the previous feedback: what improved, persisted, worsened "
                        "or held, and how the context changed.*")
STEP_CHANGE_TASK = "step-change"
# Work and impact, the report's first section, as calibration starts from it:
# what the person worked on and with what impact, a paragraph for each
# initiative, the agent's to name and group, under its subtitle, the
# script's. Each initiative cites its evidence, a period point by its id or
# an item of data.json by its link: a Jira issue or epic, a pull request or a
# Notion page; the report folds a table of it under each paragraph. The
# initiatives come most recent first, by the latest day of their evidence,
# undated last, worked out by the script, never the agent.
WORK_IMPACT_HEADING = "Work and impact"
WORK_IMPACT_SUBTITLE = "*What the person worked on, each initiative's impact and the person's part in it, the most recent first.*"
# The work and its impact's two parts, as the Observations' are: the
# period's initiatives, then, only with previous feedback, a short list of
# what the person worked on before the period, as that feedback says it, for
# a review that looks back over the whole year. It is a reminder, so it cites
# nothing.
WORK_PERIOD_HEADING = "In the period"
EARLIER_WORK_HEADING = "Before the period"
EARLIER_WORK_TASK = "earlier-work"
EARLIER_WORK_SHAPE = '{"bullets": ["...", ...]}'
MAX_EARLIER_BULLETS = 5
WORK_IMPACT_TASK = "work-impact"
OBSERVATIONS_TASK = "observations"
WORK_IMPACT_SHAPE = ('{"initiatives": [{"title": "...", "impact": "...", "paragraph": "...", '
                     '"evidence": ["G2", "https://...", ...]}, ...]}')
WORK_IMPACT_FIELDS = ("title", "impact", "paragraph", "evidence")
# How the evidence table names each kind of item data.json holds.
WORK_KINDS = {"issue": "Jira", "epic": "Jira epic",
              "pr": "GitHub", "page": "Notion"}
# How the evidence table names a Notion page's link, which has no key.
NOTION_KEY = "Notion page"
# What the agents read, each made from data.json, and what they write: one
# summarises the observations, a few sentences for each company value worth
# saying in going well and to improve and a paragraph of context, another
# writes the step change, the others the work and its impact. Each text is
# about WORDS words, by what it is, fewer when there is little
# to say. An agent writes up to any
# number it is told and a little over a target, so it is told the target
# alone, in the protocol, the help and the error, and only more than
# MAX_WORDS, a margin it never sees, is refused.
OBSERVATIONS_BRIEF = "observations_brief.json"
STEP_CHANGE_BRIEF = "step_change_brief.json"
WORK_IMPACT_BRIEF = "work_impact_brief.json"
OBSERVATIONS_CONTENT = "observations_content.json"
STEP_CHANGE_CONTENT = "step_change_content.json"
WORK_IMPACT_CONTENT = "work_impact_content.json"
EARLIER_WORK_BRIEF = "earlier_work_brief.json"
EARLIER_WORK_CONTENT = "earlier_work_content.json"
WORDS = {"value": 75, "context": 150, "step_change": 150,
                      "work_impact": 100, "work_impact_line": 30, "earlier_work": 30}
MAX_WORDS = {"value": 100, "context": 200, "step_change": 200,
             "work_impact": 130, "work_impact_line": 40, "earlier_work": 40}
# The chart of the resolved issues by epic, beside the main focus.
EPICS_CHART = "jira_epics.svg"
# The GitHub cells of the report, in order, as the Jira ones, and the chart
# of the merged pull requests by repository, beside their main focus.
GITHUB_CELLS = (("opened", "github_opened_over_time.svg"), ("merged", "github_merged_over_time.svg"),
                ("merged_lines", "github_pr_size.svg"))
REPOS_CHART = "github_repos.svg"
CHART_FILES = (*(chart for _, chart in JIRA_CELLS), EPICS_CHART, *(chart for _, chart in GITHUB_CELLS),
               REPOS_CHART)


def expected_files(prep):
    """Every file the prep folder `prep` holds, and nothing else: the person,
    the period and who they are in each source, the current manager feedback on
    them, the period's other feedback, the previous feedback, the manager's notes on
    them, what their Slack messages show, the report's data, the brief of
    its observations and the agent's summaries of them, the brief of the
    step change and the agent's step change, the brief of the work and its
    impact and the agent's account of it, the brief of the work before the
    period and the agent's list of it, the _raw folder of what each
    source gave, and the report with its _charts folder."""
    return {PERSON, *FEEDBACK_FILES.values(), NOTES, SLACK, DATA, OBSERVATIONS_BRIEF, OBSERVATIONS_CONTENT, STEP_CHANGE_BRIEF, STEP_CHANGE_CONTENT,
            WORK_IMPACT_BRIEF, WORK_IMPACT_CONTENT, EARLIER_WORK_BRIEF, EARLIER_WORK_CONTENT, RAW_DIR, report_name(
                prep),
            CHARTS_DIR}


def report_name(prep):
    """The file name of the prep `prep`'s report, <Person>_Review_Prep.md,
    from its folder's name, <Person>_<YY-MM-DD>."""
    return run_document(prep, REPORT_KIND, "prep", "Person")


def fetched(paths, root=""):
    """The fields to fetch for the fields at `paths`, such as
    "fields.status.name", that are under `root`, such as "fields.": each
    one's first name below it, once, in order."""
    return list(dict.fromkeys(path.removeprefix(root).split(".")[0] for path in paths if path.startswith(root)))


def write_raw_work(prep, source, raw, days, help=""):
    """Writes `raw`, what `source` gave, such as {"created": [...]} for
    "notion", to its raw file in the prep `prep`; returns the file's path.
    Exits, writing nothing, when `raw` breaks a rule, `days` the period's,
    with every problem and then `help`."""
    if problems := raw_work_problems(source, raw, days):
        raise SystemExit("; ".join(problems) + help)
    return write_prep_file(prep, f"{RAW_DIR}/{source}.json", raw)


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
    results as the search returned them, each with its type, which tells a
    page from a database, and a page with its title and url; their
    ranges covering the period day by day, with no gap or overlap, each within
    a calendar week; none full but a single day, marked "full": true; and no
    page found by two of them."""
    if not all(isinstance(search, dict) and set(search) - {"full"} == {"start", "end", "results"}
               and search.get("full", True) is True and isinstance(search["results"], list)
               and all(isinstance(result, dict) for result in search["results"]) for search in searches):
        return ['each Notion search must be {"start", "end", "results": [...]}, its results as it returned them']
    if not all(isinstance(result.get("type"), str) and result["type"]
               for search in searches for result in search["results"]):
        # Without its type a page isn't counted, so it would go missing quietly.
        return ["each result of a Notion search must have its type, as the search gave it: pass the results "
                "unchanged, every field included"]
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
    problems = []
    if missing := [day for day in days if day not in covered]:
        problems.append(f"the Notion searches don't cover {day_ranges(missing)}: search those days, and add them "
                        "to the searches")
    if repeated := sorted({day for day in covered if covered.count(day) > 1 and day in days}):
        problems.append(
            f"the Notion searches overlap on {day_ranges(repeated)}: each day is in one search only")
    if beyond := sorted({day for day in covered if day not in days}):
        problems.append(
            f"the Notion searches go beyond the period, on {day_ranges(beyond)}")
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


def read_raw_work(prep):
    """{source: raw}: every source's raw file of the prep `prep`, or None
    while one is missing."""
    paths = {source: os.path.join(
        prep_dir(prep), RAW_DIR, f"{source}.json") for source in WORK_LISTS}
    if not all(os.path.exists(path) for path in paths.values()):
        return None
    return {source: read_json(path) for source, path in paths.items()}


def work_items(source, raw):
    """{list: items}: the items of `raw`, the raw file of `source`, as
    data.json records them, without the fields kept only to check them, and
    of Notion's results only the pages of their own, each with its space, the
    first place of its path, or none at the top of the workspace."""
    if source == "jira":
        parents = {parent["key"]: parent for parent in raw["parents"]}
        return {name: [issue_item(raw["base_url"], issue, dated_by, raw["points_fields"], parents)
                       for issue in raw[name]]
                for name, dated_by in (("created", "created"), ("resolved", "resolutiondate"))}
    if source == "github":
        return {name: sorted((pr_item(pr, pr[stamp]) for pr in raw[name]), key=lambda item: (item["date"], item["url"]))
                for name, stamp in (("opened", "createdAt"), ("merged", "mergedAt"))}
    return {"created": sorted(({"title": result["title"], "url": result["url"], "path": result.get("path") or "",
                                "space": (result.get("path") or "").split(" / ")[0] or None,
                                "between": [search["start"], search["end"]]}
                               for search in raw["created"] for result in search["results"] if is_notion_page(result)),
                              key=lambda page: (page["between"][0], page["url"]))}


def issue_item(base_url, issue, dated_by, points_fields, parents):
    """A Jira issue as data.json records it, its link on the site at
    `base_url`, dated by the day of its field `dated_by`, its points the
    first of `points_fields` it has, or null when it isn't estimated, and its
    epic, {key, title, url}, or null, by epic_of() from `parents`. Jira's
    own sub-task flag says which issue is one, as type names differ from site
    to site."""
    fields = issue["fields"]
    epic = epic_of(fields, parents)
    return {"key": issue["key"], "title": fields.get("summary") or "", "type": fields["issuetype"]["name"],
            "epic": {"key": epic["key"], "title": epic["fields"].get("summary") or "",
                     "url": browse_url(base_url, epic["key"])} if epic else None,
            "status": fields["status"]["name"], "url": browse_url(base_url, issue["key"]),
            "date": (fields[dated_by] or "")[:10],
            "points": next((fields[field] for field in points_fields if fields.get(field) is not None), None)}


def epic_of(fields, parents):
    """The epic of the Jira issue whose fields are `fields`, as Jira gives
    it, or None: its parent, or for a sub-task, whose parent is a story, the
    story's parent, from `parents`, {key: story}."""
    parent = fields.get("parent")
    if is_sub_task(fields) and parent:
        return ((parents.get(parent["key"]) or {}).get("fields") or {}).get("parent")
    return parent


def pr_item(pr, stamp):
    """A pull request as data.json records it, dated by the day of `stamp`,
    when it was opened or merged, with its size: the lines it added and
    removed, and the files it changed."""
    return {"repo": pr["repository"]["nameWithOwner"], "number": pr["number"], "title": pr["title"],
            "url": pr["url"], "date": (stamp or "")[:10], "lines": pr["additions"] + pr["deletions"],
            "files": pr["changedFiles"]}


def items_problems(source, lists, days):
    """Why `lists`, {list: items} of `source`, don't follow their rules,
    empty when they do: each item an object with a title, a link and a date,
    one of `days`, but a Notion page its path and `between`, two of them, a
    Jira issue its points too, a number or null, and listed once."""
    problems = []
    for name, items in lists.items():
        problems += [f"the work's {source} {name}: {item!r:.80} needs a title, a link"
                     + (", its path and the range it was found in, within the period" if source == "notion"
                        else " and a day in the period")
                     + (", and points, a number or null" if source == "jira" else "")
                     for item in items if not _is_work_item(source, name, item, days)]
        urls = [item.get("url") for item in items if isinstance(item, dict)]
        problems += [f"the work's {source} {name} lists {url} more than once"
                     for url in sorted(set(urls), key=str) if urls.count(url) > 1]
    return problems


def _is_work_item(source, name, item, days):
    """Whether `item` of the list `name` of `source` follows its rules."""
    if source == "notion":
        return (_is_item(item, days, dated=False) and isinstance(item.get("path"), str)
                and isinstance(item.get("between"), list) and len(item["between"]) == 2
                and all(day in days for day in item["between"]))
    points = item.get("points") if isinstance(item, dict) else None
    return _is_item(item, days, dated=True) and (source != "jira" or points is None or is_number(points))


def _is_item(item, days, dated):
    """Whether `item` is an object with a title, a link and, when `dated`, a
    date, one of `days`. A link is a web address, http or https: a Jira
    item's is made from the site's base-url, which a self-hosted site may
    serve over http."""
    return (isinstance(item, dict) and _is_text(item.get("title"))
            and str(item.get("url", "")).startswith(("http://", "https://"))
            and (not dated or item.get("date") in days))


def prep_dir(prep):
    """The absolute path of the prep folder `prep` inside the skill's output
    folder. Exits if `prep` isn't a prep folder name, <Person>_<YY-MM-DD>,
    would lead outside it or doesn't exist."""
    return run_folder(FOLDER_NAME, prep, "prep", "Person", "init_prep.py")


def previous_dir(prep):
    """The folder in the system's temporary folder that keeps the prep `prep`
    as it was before the last change to the finished prep, so the manager can
    go back to it."""
    return work_folder(FOLDER_NAME, prep, "previous")


def link_commands():
    """The commands a task reads a linked item with, by the paths the skill
    pre-approves, as its protocol names them: jira_ticket, which reads a Jira
    ticket, pull_request, which reads a pull request, and extract_saved,
    which lists what a too large result holds."""
    return {"jira_ticket": f"{script_command(__file__, 'jira_ticket.py')} --key <key>",
            "pull_request": "gh pr view <url> --comments",
            "extract_saved": library_command(__file__, "extract_saved.py")}


def write_prep_file(prep, name, value):
    """Writes `value` as indented JSON to the file `name` of the prep folder
    `prep`, through the shared writer; returns the file's path."""
    path, _ = write_output_json(FOLDER_NAME, f"{prep}/{name}", value)
    return path


def person_problems(person, today):
    """Why `person` isn't a valid person.json on `today`, its sources aside,
    empty when it is: its fields are PERSON_FIELDS, NOTES_END too once set,
    the person is named by letters or digits, the period's days are dates as
    YYYY-MM-DD of a period that can be reported on, and NOTES_END a day after
    it, today at the latest. Its sources follow sources_problems()."""
    if not isinstance(person, dict):
        return ["the person must be a JSON object"]
    problems = []
    if sorted(set(person) - {NOTES_END}) != sorted(PERSON_FIELDS):
        problems.append(f"the person's fields must be {', '.join(PERSON_FIELDS)}, and {NOTES_END} once the notes "
                        f"were read to today, not {', '.join(person) or 'none'}")
    name = person.get("person")
    if not isinstance(name, str) or not as_name(name):
        problems.append(f"{name!r} must name the person, such as Jane Doe")
    days = {}
    for field in ("start", "end"):
        value = person.get(field)
        if isinstance(value, str) and is_day(value):
            days[field] = date.fromisoformat(value)
        else:
            problems.append(
                f"the period's {field}, {value!r}, must be a date as YYYY-MM-DD")
    if len(days) == 2 and (problem := period_problem(days["start"], days["end"], today)):
        problems.append(problem)
    if NOTES_END in person and "end" in days:
        value = person[NOTES_END]
        if not (isinstance(value, str) and is_day(value) and days["end"] < date.fromisoformat(value) <= today):
            problems.append(f"the notes' last day, {value!r}, must be a date as YYYY-MM-DD after the period's end "
                            "and not after today")
    return problems


def notes_days(person):
    """Every day the manager's notes are read on in `person`, a prep's
    person.json, as YYYY-MM-DD: the period's, or up to NOTES_END once set."""
    return days_between(person["start"], person.get(NOTES_END, person["end"]))


def period_days(person):
    """Every day of the review's period in `person`, a prep's person.json, as
    YYYY-MM-DD."""
    return days_between(person["start"], person["end"])


def days_between(start, end):
    """Every day from `start` to `end`, both as YYYY-MM-DD, in the same form."""
    return [day.isoformat() for day in days(date.fromisoformat(start), date.fromisoformat(end))]


def day_ranges(days):
    """`days`, as YYYY-MM-DD in order, as the ranges of consecutive days they
    make, "2026-09-01 to 2026-09-30, 2026-10-04": a single day alone."""
    runs = []
    for day in days:
        if runs and date.fromisoformat(day) - date.fromisoformat(runs[-1][1]) == timedelta(days=1):
            runs[-1][1] = day
        else:
            runs.append([day, day])
    return ", ".join(first if first == last else f"{first} to {last}" for first, last in runs)


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


def feedback_problems(feedback, kind, values):
    """Why `feedback`, the summary of what the manager gave in a step, `kind`
    a key of FEEDBACK_FILES, such as "other", doesn't have the parts of
    SUMMARY_PARTS, empty when it does, by summary_problems(): it may have no
    points, as a text may say nothing of the person."""
    return summary_problems(feedback, f"the {FEEDBACK_NAMES[kind]}", values)


def summary_problems(summary, what, values, days=None, undated_context=False):
    """Why `summary`, the summary of `what`, such as "the notes summary", doesn't
    have the parts of SUMMARY_PARTS, empty when it does: each a list of
    points, a point of VALUED_PARTS {"point", "values"}, its values up to
    MAX_VALUES of `values`, each once, any other a text; each point's text
    not blank, of at most MAX_POINT_WORDS words, and listed once. With `days`, the days the source was read on as
    YYYY-MM-DD, it is a reading's summary: every point, context too, has
    "evidence", what it rests on, each {date, link} with its link once, the
    date one of `days`, or null in a context point with `undated_context`,
    as one from an undated page. It may be empty, as a source may hold
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
                     f"sentence of up to {POINT_WORDS}, or split it"
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
                         f"{', and a page, which has no day, backs only a context point' if undated_context and part in VALUED_PARTS else ''}"
                         for point in points if not {item["date"] for item in point["evidence"]} <= allowed
                         or len({item["link"] for item in point["evidence"]}) != len(point["evidence"])]
    return problems


def point_fields(part, evidence=None):
    """The fields of a point of `part`: point, then values in VALUED_PARTS,
    and `evidence`, the field naming what it rests on in a reading's summary,
    cites in a reading's answer; none, a sentence alone, for a context point
    with no evidence."""
    valued = part in VALUED_PARTS
    if not (valued or evidence):
        return ()
    return ("point", *(("values",) if valued else ()), *((evidence,) if evidence else ()))


def point_shape(fields):
    """How a point with `fields` is written, for an error: a sentence when it
    has none."""
    shapes = {"point": '"..."', "values": '["...", ...] or []',
              "evidence": '[{"date": "YYYY-MM-DD", "link": "https://... or /path/to/note.md"}, ...]',
              "cites": '[1, 2, ...]'}
    return "{" + ", ".join(f'"{field}": {shapes[field]}' for field in fields) + "}" if fields else "a sentence"


def is_point(point, fields):
    """Whether `point` is a point with `fields`: an object of them, its point
    a text that isn't blank, its values a list of texts, its evidence a list
    of at least one {date, link}, the date a text or null, and its cites,
    a reading's, a list of at least one number, from 1, each once; with no
    fields, such a text alone."""
    if not fields:
        return _is_text(point)

    def listed(key, at_least_one, each):
        return isinstance(point[key], list) and (bool(point[key]) or not at_least_one) and all(map(each, point[key]))
    return (isinstance(point, dict) and sorted(point) == sorted(fields) and _is_text(point["point"])
            and ("values" not in point or listed("values", False, lambda value: isinstance(value, str)))
            and ("evidence" not in point or listed("evidence", True, _is_evidence))
            and ("cites" not in point or (listed("cites", True, _is_number) and len(set(point["cites"])) == len(point["cites"]))))


def _is_number(value):
    """Whether `value` is a whole number from 1, as an item's number."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_evidence(item):
    """Whether `item` is a piece of a point's evidence: {date, link}, the date
    a text or null, the link a web address or a file's absolute path."""
    return (isinstance(item, dict) and sorted(item) == ["date", "link"]
            and (item["date"] is None or isinstance(item["date"], str))
            and isinstance(item["link"], str) and (item["link"].startswith(WEB_LINK) or os.path.isabs(item["link"])))


def agent_files():
    """(file, task, check) of each file step 6's agents write, in the order
    the report shows them: the task that writes it and the function that
    says why its value breaks its rules against data.json, each called as
    check(value, data)."""
    return ((WORK_IMPACT_CONTENT, WORK_IMPACT_TASK, work_impact_content_problems),
            (EARLIER_WORK_CONTENT, EARLIER_WORK_TASK, earlier_work_content_problems),
            (OBSERVATIONS_CONTENT, OBSERVATIONS_TASK, observations_content_problems),
            (STEP_CHANGE_CONTENT, STEP_CHANGE_TASK, step_change_content_problems))


def observations_content_problems(observations_content, data):
    """Why `observations_content` isn't the agent's summaries of data.json's
    observations, in `data`, empty when it is, as OBSERVATIONS_SHAPE: in a valued part,
    `values`, each the name of a company value its table groups points
    under, at least one when it groups any, and `also`, a text only when its
    table holds points under no value, else null, each text not blank, of at
    most its MAX_WORDS words, naming no id; context a text of at
    most its words, empty exactly when its table holds no point."""
    what, observations = OBSERVATIONS_CONTENT, data["observations"]
    if not (isinstance(observations_content, dict) and sorted(observations_content) == sorted(OBSERVATION_HEADINGS)
            and all(_is_value_summaries(observations_content[part]) for part in VALUED_PARTS)
            and isinstance(observations_content["context"], str)):
        return [f"{what} must be {OBSERVATIONS_SHAPE}"]
    problems = []
    for part in VALUED_PARTS:
        groups = observations[part]
        named = [group["value"] for group in groups if group["value"]]
        values, also = observations_content[part]["values"], observations_content[part]["also"]
        if unknown := [value for value in values if value not in named]:
            problems.append(f"{what}'s {part} summarises {', '.join(unknown)}, which its table groups no point under: "
                            f"summarise only some of {', '.join(named) or 'none'}")
        elif named and not values:
            problems.append(
                f"{what}'s {part} summarises no value: summarise each of {', '.join(named)} worth saying")
        texts = [(f"{what}'s {part} {value}", text)
                 for value, text in values.items()]
        if also is not None:
            if all(group["value"] for group in groups):
                problems.append(
                    f"{what}'s {part} also must be null, as its table holds no point under no value")
            else:
                texts.append((f"{what}'s {part} also", also))
        for field, text in texts:
            if not text.strip():
                problems.append(
                    f"{field} is empty: say what its points show, or leave it out")
            elif problem := _length_problem(field, text, "value"):
                problems.append(problem)
            elif ids := POINT_ID_TEXT.findall(text):
                problems.append(
                    f"{field} names {', '.join(ids)}: say what the points show in words")
    text, points = observations_content["context"], observations["context"]
    if points and not text.strip():
        problems.append(
            f"{what}'s context is empty: summarise its table's points")
    elif not points and text.strip():
        problems.append(
            f"{what}'s context must be empty, as its table holds no point")
    elif problem := _length_problem(f"{what}'s context", text, "context"):
        problems.append(problem)
    return problems


def _is_value_summaries(value):
    """Whether `value` is a valued part's summaries as OBSERVATIONS_SHAPE
    says: {values: {name: text}, also: text or null}."""
    return (isinstance(value, dict) and sorted(value) == ["also", "values"] and isinstance(value["values"], dict)
            and all(isinstance(text, str) for text in value["values"].values())
            and (value["also"] is None or isinstance(value["also"], str)))


def step_change_content_problems(step_change, data):
    """Why `step_change`, step_change_content.json's, isn't the step change from the
    previous feedback to the period's points, those of data.json, `data`,
    empty when it is: null exactly when there is no
    previous feedback; else a summary, not empty, of at most its
    MAX_WORDS words, naming no id, and rows, each {previous_point,
    change, evidence}: the point one of the previous feedback's ids, a row for each aspect of it
    that went differently, or null; the change one of STEP_CHANGE_PARTS for
    the point's part, or for None when it has none; the evidence period
    point ids, each once, at least one but for an improved point, and for a
    row with no previous point a period context point among them; and every
    to-improve point of the previous feedback with at least one row."""
    what = STEP_CHANGE_CONTENT
    previous = data["previous"]
    if previous is None:
        return [] if step_change is None else [f"{what} must be null, as there is no previous feedback to compare with"]
    if not (isinstance(step_change, dict) and sorted(step_change) == ["rows", "summary"]
            and isinstance(step_change["summary"], str) and isinstance(step_change["rows"], list)):
        return [f"{what} must be {STEP_CHANGE_SHAPE}, as there is previous feedback"]
    baseline = baseline_points(previous)
    problems = []
    summary = step_change["summary"]
    if not summary.strip():
        problems.append(
            f"{what}'s summary is empty: summarise how the period compares with the previous feedback")
    elif problem := _length_problem(f"{what}'s summary", summary, "step_change"):
        problems.append(problem)
    elif ids := POINT_ID_TEXT.findall(summary):
        problems.append(f"{what}'s summary names {', '.join(ids)}: say what the points show in words, as ids "
                        "belong only in the rows' evidence")
    point_field, change_field, _ = STEP_CHANGE_ROW
    period = period_points(data["observations"])
    seen = []
    for number, row in enumerate(step_change["rows"], 1):
        field = f"{what}'s row {number}"
        if not (isinstance(row, dict) and sorted(row) == sorted(STEP_CHANGE_ROW)
                and (row[point_field] is None or isinstance(row[point_field], str))
                and isinstance(row[change_field], str) and isinstance(row["evidence"], list)
                and all(isinstance(item, str) for item in row["evidence"])):
            problems.append(f'{field} must be {{"{point_field}": "P-I1" or null, '
                            f'"{change_field}": "...", "evidence": ["I2", ...]}}')
            continue
        point, change, evidence = row[point_field], row[change_field], row["evidence"]
        if point is not None and point not in baseline:
            problems.append(f"{field}'s {point_field}, {point!r}, must be one of the previous feedback's points: "
                            f"{', '.join(baseline) or 'it has none'}, or null for a period context point")
            continue
        seen.append(point)
        part = baseline[point][0] if point else None
        allowed = STEP_CHANGE_PARTS[part]
        if change not in allowed:
            problems.append(f"{field}'s {change_field}, {change!r}, must be {' or '.join(allowed)} for "
                            + (f"a {part} point of the previous feedback" if part
                               else f"a row with no {point_field}"))
        if unknown := [item for item in evidence if item not in period]:
            problems.append(f"{field}'s evidence names {', '.join(unknown)}, not points of the period: cite the "
                            "brief's ids, such as G1")
        elif len(set(evidence)) != len(evidence):
            problems.append(
                f"{field}'s evidence names a point more than once: name each once")
        elif not evidence and change != "improved":
            problems.append(
                f"{field}'s evidence is empty: cite the period points that show it, by their ids")
        elif point is None and not any(period[item][0] == "context" for item in evidence):
            problems.append(f"{field} has no {point_field}, so its evidence must cite the period "
                            f"context point it stands for, such as {point_id('context', 1)}")
    if missing := [point for point, (part, _) in baseline.items() if part == "to_improve" and point not in seen]:
        problems.append(
            f"{what} has no row for {', '.join(missing)}: give every to-improve point of the previous feedback "
            "one, improved, still_to_improve or worsened")
    return problems


def work_impact_content_problems(work_impact, data, ordered=True):
    """Why `work_impact`, work_impact_content.json's, isn't the account of the
    work and its impact from `data`, data.json, empty when it is: at least one
    initiative, each {title, impact, paragraph, evidence}: its title a text,
    not blank, listed once; its impact, a line, and its paragraph not empty,
    each of at most its MAX_WORDS words, naming no id; its evidence at least one of work_evidence()'s
    references, each once; and, when `ordered`, the initiatives most recent
    first, by by_recency()."""
    what = WORK_IMPACT_CONTENT
    if not (isinstance(work_impact, dict) and sorted(work_impact) == ["initiatives"]
            and isinstance(work_impact["initiatives"], list) and work_impact["initiatives"]):
        return [f"{what} must be {WORK_IMPACT_SHAPE}, with at least one initiative"]
    index = work_evidence(data)
    problems, titles = [], []
    for number, initiative in enumerate(work_impact["initiatives"], 1):
        field = f"{what}'s initiative {number}"
        if not (isinstance(initiative, dict) and sorted(initiative) == sorted(WORK_IMPACT_FIELDS)
                and all(isinstance(initiative[name], str) for name in ("title", "impact", "paragraph"))
                and isinstance(initiative["evidence"], list)
                and all(isinstance(item, str) for item in initiative["evidence"])):
            problems.append(
                f'{field} must be {{"title": "...", "impact": "...", "paragraph": "...", '
                '"evidence": ["G2", "https://...", ...]}}')
            continue
        title, impact, paragraph, evidence = (initiative[name]
                                              for name in WORK_IMPACT_FIELDS)
        if not title.strip():
            problems.append(f"{field}'s title is empty: name the initiative")
        elif title in titles:
            problems.append(
                f"{field}'s title, {title!r}, names another initiative too: give each its own")
        titles.append(title)
        for name, text, part, empty in (("impact", impact, "work_impact_line", "say in a line the initiative's impact"),
                                        ("paragraph", paragraph, "work_impact", "say what the person did")):
            if not text.strip():
                problems.append(f"{field}'s {name} is empty: {empty}")
            elif problem := _length_problem(f"{field}'s {name}", text, part):
                problems.append(problem)
            elif ids := POINT_ID_TEXT.findall(text):
                problems.append(f"{field}'s {name} names {', '.join(ids)}: say what the points show in words, as "
                                "ids belong only in its evidence")
        if not evidence:
            problems.append(
                f"{field}'s evidence is empty: cite the points and items it rests on")
        elif unknown := [item for item in evidence if item not in index]:
            problems.append(f"{field}'s evidence names {', '.join(unknown)}, which the brief doesn't hold: cite a "
                            "point by its id, such as G1, or an issue, epic, pull request or page by its link")
        elif len(set(evidence)) != len(evidence):
            problems.append(
                f"{field}'s evidence names an item more than once: name each once")
    if ordered and not problems and work_impact["initiatives"] != by_recency(work_impact["initiatives"], index):
        problems.append(f"{what}'s initiatives must come most recent first, by their evidence's latest day: record "
                        "them with set_work_impact.py, which orders them")
    return problems


def earlier_work_content_problems(earlier_work, data):
    """Why `earlier_work`, earlier_work_content.json's, isn't the list of the
    work before the period from `data`, data.json, empty when it is: null
    exactly when there is no previous feedback; else {bullets}, one to
    MAX_EARLIER_BULLETS, each a text, not blank, of at most its
    MAX_WORDS words, naming no id."""
    what = EARLIER_WORK_CONTENT
    if data["previous"] is None:
        return [] if earlier_work is None else [f"{what} must be null, as there is no previous feedback"]
    if not (isinstance(earlier_work, dict) and sorted(earlier_work) == ["bullets"]
            and isinstance(earlier_work["bullets"], list)
            and all(isinstance(bullet, str) for bullet in earlier_work["bullets"])):
        return [f"{what} must be {EARLIER_WORK_SHAPE}, as there is previous feedback"]
    bullets = earlier_work["bullets"]
    problems = []
    if not 1 <= len(bullets) <= MAX_EARLIER_BULLETS:
        problems.append(f"{what} has {len(bullets)} bullets: write one to {MAX_EARLIER_BULLETS}, the work that "
                        "mattered most")
    for number, bullet in enumerate(bullets, 1):
        field = f"{what}'s bullet {number}"
        if not bullet.strip():
            problems.append(f"{field} is empty: say what the person worked on")
        elif problem := _length_problem(field, bullet, "earlier_work"):
            problems.append(problem)
        elif ids := POINT_ID_TEXT.findall(bullet):
            problems.append(
                f"{field} names {', '.join(ids)}: say what the feedback said in words")
    return problems


def by_recency(initiatives, index):
    """`initiatives` most recent first, by the latest day of their evidence in
    `index`, work_evidence()'s, those with none dated last, each kept in the
    order given among those of the same day."""
    def latest(initiative):
        days = [index[item]["date"]
                for item in initiative["evidence"] if index[item]["date"]]
        return (bool(days), max(days, default=""))
    return sorted(initiatives, key=latest, reverse=True)


def work_evidence(data):
    """{reference: {kind, title, key, link, date, source}}: everything an
    initiative of the work may cite in `data`, data.json: each period point by
    its id, its kind "point", its text as title, no key nor link, its latest
    evidence's day and its source; each Jira issue, its epic, pull request and
    Notion page by its link, its kind one of WORK_KINDS, its title, its key,
    the issue's or epic's, the pull request's repository and number or
    NOTION_KEY, its day its latest in data.json, an epic's its issues' latest
    and a page's the last of the range it was found in, and no source. A
    link that is some issue's epic is an epic, even when the person reported
    it too."""
    index = {point["id"]: {"kind": "point", "title": point["point"], "key": None, "link": None,
                           "date": point["date"], "source": point["source"]}
             for _, point in period_points(data["observations"]).values()}

    def add(kind, title, key, link, day):
        found = index.setdefault(link, {"kind": kind, "title": title, "key": key,
                                        "link": link, "date": day, "source": None})
        found["date"] = max(found["date"] or "", day or "") or None
        if kind == "epic":
            found["kind"] = kind
    for issue in (*data["jira"]["created"], *data["jira"]["resolved"]):
        add("issue", issue["title"], issue["key"], issue["url"], issue["date"])
        if epic := issue["epic"]:
            add("epic", epic["title"], epic["key"], epic["url"], issue["date"])
    for pr in (*data["github"]["opened"], *data["github"]["merged"]):
        add("pr", pr["title"],
            f'{pr["repo"]}#{pr["number"]}', pr["url"], pr["date"])
    for page in data["notion"]["created"]:
        add("page", page["title"], NOTION_KEY, page["url"], page["between"][1])
    return index


def _length_problem(what, text, part):
    """Why `text`, `what`, an agent's text of `part`, a key of WORDS, is too
    long, or None: more than its MAX_WORDS words, the error giving the target
    alone."""
    if word_count(text) <= MAX_WORDS[part]:
        return None
    return (f"{what} has {word_count(text)} words, more than {WORDS[part]}: cut it to about "
            f"{WORDS[part]}, keeping what matters most")


def period_points(observations):
    """{id: (part, point)}: every point of the period in `observations`,
    data.json's, by its id, in the tables' order."""
    return {point["id"]: (part, point) for part in OBSERVATION_HEADINGS
            for point in observation_points(observations, part)}


def observation_points(observations, part):
    """The points of `part` in `observations`, data.json's, in its table's
    order: a valued part's group by group."""
    if part not in VALUED_PARTS:
        return observations[part]
    return [point for group in observations[part] for point in group["points"]]


def baseline_points(baseline):
    """{id: (part, point)}: every point of `baseline`, the previous
    feedback as data.json holds it, by its id, part by
    part."""
    return {point["id"]: (part, point) for part in SUMMARY_PARTS for point in baseline[part]}


def point_id(part, number, prefix=""):
    """The id of the `number`th point of `part`, from 1, in its table, after
    `prefix`, PREVIOUS_ID in the previous feedback: G1, I2, C3 or P-G1."""
    return f"{prefix}{POINT_IDS[part]}{number}"


def types_text(by_type):
    """A breakdown by type, [{type, issues}], as the report writes it, such
    as "2 Task, 1 Bug": how the report and its check write it, so they
    agree."""
    return ", ".join(f"{entry['issues']} {entry['type']}" for entry in by_type)


def average_text(average):
    """The story points' `average` as the report writes it, such as
    "avg=3.3", or "none estimated" when it is null."""
    return "none estimated" if average is None else f"avg={number(average)}"


def repos_text(count):
    """How many repositories pull requests are in, as the report writes it,
    such as "in 3 repositories"."""
    return f"in {count} {plural(count, 'repository', 'repositories')}"


def repo_code(repo, order):
    """The repository `repo`'s code in the report, a letter by its place in
    `order`, data.json's repo_order, A for the first, as an epic's key names
    it in the charts; None for one beyond it."""
    return chr(ord("A") + order.index(repo)) if repo in order else None


def size_text(median, merged):
    """What the PRs size's figure, the `median` lines changed of the `merged`
    pull requests, how many they are, is, as the report writes it, such as
    "median, in 696 merged PRs", or "none merged" when there is none, the
    figure then 0."""
    if median is None:
        return "none merged"
    return f"median, in {merged} merged {plural(merged, 'PR', 'PRs')}"


def details_text(count, names=("point", "points")):
    """What a table's fold says, its `count` items among it, by `names`, the
    one and the many: "Details (29 points)"."""
    return f"Details ({count} {plural(count, *names)})"


def week_text(week):
    """A Notion page's `week`, its first and last day, as the report writes
    it, the month as the charts' axes name it: "13–19 Jul", "28 Jul–3 Aug"
    across two months, or "13 Jul" for a single day."""
    first, last = (date.fromisoformat(day) for day in week)
    if first == last:
        return day_text(week[0])
    start = f"{first.day}" if first.month == last.month else f"{first.day} {first:%b}"
    return f"{start}–{last.day} {last:%b}"


def newest_key(day):
    """The key that sorts, with reverse=True, items by `day`, YYYY-MM-DD or
    None, from the latest, those with none first, as the most recent of all,
    each kept in the order given."""
    return (day is None, day or "")


def latest_day(evidence):
    """The latest day of `evidence`, each {date, link}, the date YYYY-MM-DD or
    None, or None when none is dated, which newest_key() ranks first: the
    day a point of a reading ranks by, so a page beside dated evidence
    doesn't make the point the most recent."""
    return max((item["date"] for item in evidence if item["date"]), default=None)


def day_text(day):
    """A day, as YYYY-MM-DD, as the report writes it, the month as the charts'
    axes name it: "13 Jul"."""
    value = date.fromisoformat(day)
    return f"{value.day} {value:%b}"


def reference_text(source, item):
    """What a reading's reference to `item`, an evidence of `source`, says: its
    source and day, such as "Slack 14 Oct", or, undated, as a page has no day,
    the page's title, its file's name without .md, such as "Page Jane"."""
    if item["date"] is None:
        return f"{PAGE_REFERENCE} {page_title(os.path.basename(item['link']).removesuffix('.md'))}"
    return f"{REFERENCE_NAMES[source]} {day_text(item['date'])}"


def link_href(link, folder):
    """An evidence's `link` as a link in a report in the folder `folder`
    reaches it: a web address as it is, a file by its path relative to the
    folder, as a Markdown preview opens a relative path, but reads an
    absolute one from its workspace and opens no file:// address, with its
    spaces and other such characters escaped, so the link doesn't break."""
    return link if link.startswith(WEB_LINK) else quote(os.path.relpath(link, folder))
