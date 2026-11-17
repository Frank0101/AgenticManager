"""What the skill's scripts share: the prep folder's name and the closed set of
files it holds, how to find a prep's folder, the person a prep is for, the
review's period and its days and months, who the person is in each source,
the parts every summary has, the manager's view, previous reviews, the
period's feedback, the manager's notes, the person's work in Jira, GitHub and
Notion, their Slack messages, and the report's constants and how it writes a
figure. The rules of each file are one function, applied when it is written
and by the final check, so the two can't differ. Scripts import the shared
library's names from here, so they don't depend on the order of their imports.
"""
from dataclasses import dataclass
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
from agentic_manager.github import commit_authors, gh_json, gh_orgs, profile_name, dated_query, pull_search_url, require_gh, search_pulls, selection  # noqa: E402,F401
from agentic_manager.jira import JiraClient, browse_url, is_sub_task, plain_text, project_of, search_url as jira_search_url  # noqa: E402,F401
from agentic_manager.logseq import descendants, graph_path, journal_day, links, notes, page_aliases, page_title, parse_blocks  # noqa: E402,F401
from agentic_manager.output_file import json_text, read_json, write_output_file, write_output_json  # noqa: E402,F401
from agentic_manager.protocol import fill as fill_protocol  # noqa: E402,F401
from agentic_manager.output_folder import CHARTS_DIR, RAW_DIR, clear_folder, folder_problem, new_run, output_folder, run_document, run_folder, work_folder  # noqa: E402,F401
from agentic_manager.period import add_period_arguments, days, is_day, period_problem, shown  # noqa: E402,F401
from agentic_manager.tasks import submit_section, task_line, write_task as write_task_file  # noqa: E402,F401
from agentic_manager.svg import GRID, SURFACE, INK, MUTED, arc_segment, esc, legend, nice_step, svg, text, text_width  # noqa: E402,F401
from agentic_manager.text import SMALL_TYPE, ai_marked, as_name, display_date, number, plural, word_count  # noqa: E402,F401

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
MAX_VALUES = 2
# The limits the protocol's point rules give, filled from the three above.
POINT_LIMITS = {"point_words": POINT_WORDS,
                "max_point_words": MAX_POINT_WORDS, "max_values": MAX_VALUES}
VALUES = "values"
RATINGS = "perf-review-ratings"
# A point's evidence links: a Slack message's address, or a note's file, by
# its absolute path, which a Markdown preview opens where a file:// address
# isn't.
WEB_LINK = "https://"
SUMMARY_HELP = "\n".join(
    f"  {part:<11} {meaning}, each point "
    + ('{"point": "...", "values": ["..."]}, values every company value it clearly shows or calls for, as rules.py prints '
       f'them, at most {MAX_VALUES}, or [] when none fits' if part in VALUED_PARTS else "a sentence")
    for part, meaning in SUMMARY_PARTS.items())
# The manager's overall view of the person, summarised: the report checks it
# against the period's evidence, so the manager can revisit it.
ORIENTATION = "orientation.json"
# What the manager gives, previous reviews or the period's feedback, is a
# list of pieces, each a summary with its period as the source names it, such
# as a date or "Mid Year Review 2026", null when it names none, and its date,
# the last day of that period as the agent reads it from the source, which
# it has in hand, such as 2026-06-30 for a mid-year review, null when the
# source gives no hint of one. The period is what a reader is shown; the date
# only orders a piece among the other evidence, so a day the agent inferred
# never reads as one the source gave. The agent lists them from the most
# recent, those with no date first, as the most recent of all; what the
# manager gives counts, so how old it is isn't checked.
PIECE_FIELDS = ("period", "date")
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
# What the person's Slack messages show, read by subagents a month each and
# merged, every point with the days and links it rests on.
SLACK = "slack.json"
# The library's RAW_DIR holds what each source gave: the readers' answers, a
# folder per source, kept so a summary can be traced back to the notes and
# synopses it came from, and the raw file of each source of the work. The
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
# script's, so not marked as the agent's, then a table for each part, by its
# heading, in order.
# A valued part's table puts each point under the first company value it names, the
# one it shows most, so it shows once, the second value it names beside it,
# the values with the most points first, those naming none under NO_VALUE,
# last, as it is no value; context names no value, so its table isn't
# grouped. Each point's source, by the summary file it comes from, as the
# report names it; and what a reading's reference names, by its source,
# beside the day it was seen on, or a page, which has no day, by its title.
OBSERVATION_HEADINGS = {"going_well": "Going well",
                        "to_improve": "To improve", "context": "Context"}
OBSERVATIONS_SUBTITLE = "*What the period's feedback, the manager's notes and Slack show, by company value.*"
NO_VALUE = "No value"
OBSERVATION_SOURCES = {"feedback": "Feedback", "reviews": "Review",
                       "notes": "Manager's notes", "slack": "Slack"}
REFERENCE_NAMES = {"notes": "Journal", "slack": "Slack"}
PAGE_REFERENCE = "Page"
# The summaries data.json is built from, by name: the manager's view, and
# those the observations' points come from.
SUMMARY_FILES = {"orientation": ORIENTATION, "reviews": REVIEWS, "feedback": FEEDBACK,
                 "notes": NOTES, "slack": SLACK}
# A review dated within the period is what the person heard in it, as the
# feedback is, so its points join the observations; one dated before it, or
# undated, the most recent of them, is a previous review, only compared
# with. Pieces, the feedback's and those reviews', are referred to
# by their period, a reading's points by their evidence.
PIECE_SOURCES = ("feedback", "reviews")
# Every point of the period, of the latest previous review and of the
# manager's view has an id, by its part and its place in the table's order,
# the review's and the view's prefixed, such as G1, R-I2 and V-C1: the step
# change and the view check cite them, so they name a point the report then
# shows as the tables do, never a text the agent retyped.
POINT_IDS = {"going_well": "G", "to_improve": "I", "context": "C"}
REVIEW_ID = "R-"
VIEW_ID = "V-"
# A point's id written in a text, which only the rows' evidence may hold: the
# report shows a cited point by its text, so an id in a summary means nothing.
POINT_ID_TEXT = re.compile(
    rf"\b(?:{REVIEW_ID}|{VIEW_ID})?[{''.join(POINT_IDS.values())}]\d+\b")
# The step change: how the period compares with the latest previous review,
# the baseline, a review point to a row, each change one of STEP_CHANGES, in
# the report's order, with its label. A to-improve point of the review always
# has a row, as the manager needs to know where each stands; one the period
# no longer raises counts as improved, said as not raised again rather than
# as a proven change. A going-well point has one only when the period shows
# it held or worsened, and context only for a significant change: a review
# context point that changed, or, a row with no review point, by the None
# key, a period context point the review didn't have, standing for itself.
STEP_CHANGE_HEADING = "Step change"
STEP_CHANGES = {"improved": "Improved", "still_to_improve": "Still to improve", "worsened": "Worsened",
                "held": "Held", "context_change": "Context changed", "new_context": "New context"}
STEP_CHANGE_PARTS = {"going_well": ("held", "worsened"), "to_improve": ("improved", "still_to_improve", "worsened"),
                     "context": ("context_change",), None: ("new_context",)}
STEP_CHANGE_ROW = ("review_point", "change", "evidence")
STEP_CHANGE_SHAPE = ('{"summary": "...", "rows": [{"review_point": "R-I1", "change": "improved", '
                     '"evidence": ["I2", ...]}, ...]}')
NOT_RAISED = "Not raised again in the period"
# The manager view check: the manager's view, the baseline, against the
# period's evidence, so the manager can revisit it. Every point of the view,
# context too, has a row, as the manager needs to know where each stands:
# confirmed or contradicted by the points it cites, or with little support,
# citing what little there is or nothing; and, a row with no view point, by
# the None key, a strong theme of the period the view doesn't mention.
VIEW_CHECK_HEADING = "Manager view check"
VIEW_CHECKS = {"confirmed": "Confirmed", "little_support": "Little support", "contradicted": "Contradicted",
               "not_in_view": "Not in the manager's view"}
VIEW_CHECK_PARTS = {**{part: ("confirmed", "little_support", "contradicted") for part in SUMMARY_PARTS},
                    None: ("not_in_view",)}
VIEW_CHECK_ROW = ("view_point", "check", "evidence")
VIEW_CHECK_SHAPE = ('{"summary": "...", "rows": [{"view_point": "V-I1", "check": "confirmed", '
                    '"evidence": ["I2", ...]}, ...]}')
NO_SUPPORT = "No support in the period"
# A section with nothing to compare, with no previous review, says so alone,
# and why, by its Comparison's not_applicable, without its subtitle, which
# describes a comparison that isn't there. The manager's view always has
# points, as its summary is refused without one, so it has none.
NOT_APPLICABLE = "N/A"
# What the agents read, each made from data.json, and what they write: one
# summarises each table of observations, a few flowing paragraphs above it,
# another writes the step change, the last the view check. Each is about OBSERVATIONS_WORDS words,
# by part, fewer for a table of few points, the context half as long, as it
# says facts once rather than weighing themes. An agent writes up to any
# number it is told and a little over a target, so it is told the target
# alone, in the protocol, the help and the error, and only more than
# MAX_OBSERVATIONS_WORDS, a margin it never sees, is refused.
BRIEF = "brief.json"
STEP_CHANGE_BRIEF = "step_change_brief.json"
VIEW_CHECK_BRIEF = "view_check_brief.json"
CONTENT = "content.json"
STEP_CHANGE = "step_change.json"
VIEW_CHECK = "view_check.json"
OBSERVATIONS_WORDS = {"going_well": 150,
                      "to_improve": 150, "context": 75, "step_change": 150, "view_check": 150}
MAX_OBSERVATIONS_WORDS = {"going_well": 200,
                          "to_improve": 200, "context": 100, "step_change": 200, "view_check": 200}
# The chart of the resolved issues by epic, beside the main focus.
EPICS_CHART = "jira_epics.svg"
# The GitHub cells of the report, in order, as the Jira ones, and the chart
# of the merged pull requests by repository, beside their main focus.
GITHUB_CELLS = (("opened", "github_opened_over_time.svg"), ("merged", "github_merged_over_time.svg"),
                ("merged_lines", "github_pr_size.svg"))
REPOS_CHART = "github_repos.svg"
CHART_FILES = (*(chart for _, chart in JIRA_CELLS), EPICS_CHART, *(chart for _, chart in GITHUB_CELLS),
               REPOS_CHART)


@dataclass(frozen=True)
class Comparison:
    """A section comparing a baseline, the latest previous review or the
    manager's view, with the period's points: its file and heading, how a
    problem names it and its baseline, its task's name, which set_comparison.py
    --of takes too, its rows' fields and categories, which may cite nothing
    and which baseline points must each have one, how its table shows them,
    its subtitle, the script's, a line under its heading, where {name} stands
    for the baseline's name, and, only when its baseline may be missing, why
    there is one, why there is none and what it says then."""
    file: str
    heading: str
    name: str
    task: str
    words: str
    shape: str
    row: tuple[str, str, str]
    example: str
    kinds: dict
    labels: dict
    every: tuple
    may_cite_none: tuple
    null_cites: str | None
    summary_of: str
    baseline_points: str
    of_baseline: str
    null_row: str
    missing_hint: str
    columns: tuple[str, str]
    counted: tuple[str, str]
    no_evidence: str
    subtitle: str
    present: str | None = None
    absent: str | None = None
    not_applicable: str | None = None


# The two comparisons, each read the same way: by its file's rules, its
# report section and its check.
STEP_CHANGE_COMPARISON = Comparison(
    file=STEP_CHANGE, heading=STEP_CHANGE_HEADING, name="step change", task="step-change", words="step_change", shape=STEP_CHANGE_SHAPE,
    row=STEP_CHANGE_ROW, example="R-I1", kinds=STEP_CHANGE_PARTS, labels=STEP_CHANGES, every=("to_improve",),
    may_cite_none=("improved",), null_cites="context", summary_of="how the period compares with the latest previous review",
    baseline_points="the latest review's points", of_baseline="the review", null_row="a period context point",
    missing_hint="give every to-improve point of the latest review one, improved, still_to_improve or worsened",
    columns=("Review point", "Change"), counted=("change", "changes"), no_evidence=NOT_RAISED,
    subtitle="*How the period compares with the latest previous review{name}: what improved, persisted, worsened "
    "or held, and how the context changed.*",
    present="there is a previous review", absent="there is no previous review", not_applicable=f"{NOT_APPLICABLE}: no review before the period to compare with")
VIEW_CHECK_COMPARISON = Comparison(
    file=VIEW_CHECK, heading=VIEW_CHECK_HEADING, name="manager view check", task="view-check", words="view_check",
    shape=VIEW_CHECK_SHAPE, row=VIEW_CHECK_ROW, example="V-I1", kinds=VIEW_CHECK_PARTS, labels=VIEW_CHECKS,
    every=tuple(SUMMARY_PARTS), may_cite_none=("little_support",), null_cites=None,
    summary_of="how the period's evidence bears on the manager's view", baseline_points="the view's points",
    of_baseline="the view", null_row="a strong theme of the period the view doesn't mention",
    missing_hint="give every point of the manager's view one, confirmed, little_support or contradicted",
    columns=("View point", "Check"), counted=("check", "checks"), no_evidence=NO_SUPPORT,
    subtitle="*How the manager's view, given at the start of the prep, holds against the period's evidence: what "
    "it confirms, what has little support or is contradicted, and what the view leaves out.*")


def expected_files(prep):
    """Every file the prep folder `prep` holds, and nothing else: the person,
    the period and who they are in each source, the manager's view of them,
    their previous reviews, the period's feedback, the manager's notes on
    them, what their Slack messages show, the report's data, the brief of
    its observations and the agent's summaries of them, the brief of the
    step change and the agent's step change, the brief of the view check and
    the agent's view check, the _raw folder of what each source gave, and
    the report with its _charts folder."""
    return {PERSON, ORIENTATION, REVIEWS, FEEDBACK, NOTES, SLACK, DATA, BRIEF, CONTENT, STEP_CHANGE_BRIEF, STEP_CHANGE,
            VIEW_CHECK_BRIEF, VIEW_CHECK, RAW_DIR, report_name(prep), CHARTS_DIR}


def report_name(prep):
    """The file name of the prep `prep`'s report, <Person>_Review_Prep.md,
    from its folder's name, <Person>_<YY-MM-DD>."""
    return run_document(prep, REPORT_KIND, "prep", "Person")


def fetched(paths, root=""):
    """The fields to fetch for the fields at `paths`, such as
    "fields.status.name", that are under `root`, such as "fields.": each
    one's first name below it, once, in order."""
    return list(dict.fromkeys(path.removeprefix(root).split(".")[0] for path in paths if path.startswith(root)))


def write_raw_work(prep, source, raw, days):
    """Writes `raw`, what `source` gave, such as {"created": [...]} for
    "notion", to its raw file in the prep `prep`; returns the file's path.
    Exits, writing nothing, when `raw` breaks a rule, `days` the period's."""
    if problems := raw_work_problems(source, raw, days):
        raise SystemExit("; ".join(problems))
    return write_raw(prep, f"{source}.json", json_text(raw))


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


def write_prep_file(prep, name, value):
    """Writes `value` as indented JSON to the file `name` of the prep folder
    `prep`, through the shared writer; returns the file's path."""
    path, _ = write_output_json(FOLDER_NAME, f"{prep}/{name}", value)
    return path


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
    return [day.isoformat() for day in days(date.fromisoformat(start), date.fromisoformat(end))]


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
    date a day or null, its summary meeting summary_problems() with `values`, and each meeting
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
        if not (piece["date"] is None or is_day(piece["date"])):
            problems.append(f"{what}'s date, {piece['date']!r}, must be the last day of its period as YYYY-MM-DD, "
                            "such as 2026-06-30 for a mid-year review, or null when the source gives no hint of one")
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
              "evidence": '[{"date": "YYYY-MM-DD", "link": "https://... or /path/to/note.md"}, ...]',
              "links": '["https://... or /path/to/note.md", ...]'}
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
    a text or null, the link a web address or a file's absolute path."""
    return (isinstance(item, dict) and sorted(item) == ["date", "link"]
            and (item["date"] is None or isinstance(item["date"], str))
            and isinstance(item["link"], str) and (item["link"].startswith(WEB_LINK) or os.path.isabs(item["link"])))


def content_problems(content, observations):
    """Why `content` isn't the agent's summaries of `observations`,
    data.json's, empty when it is: one for each part of OBSERVATION_HEADINGS,
    each a text of at most its MAX_OBSERVATIONS_WORDS words, empty exactly when
    its table holds no point, a valued part's naming every company value its
    table groups points under; one a point names only second is the agent's
    to weigh, so it isn't checked, and context names none."""
    if not (isinstance(content, dict) and sorted(content) == sorted(OBSERVATION_HEADINGS)):
        return [f"content.json must be {{{', '.join(f'\"{part}\": \"...\"' for part in OBSERVATION_HEADINGS)}}}"]
    problems = []
    for part in OBSERVATION_HEADINGS:
        text, points = content[part], observations[part]
        if not isinstance(text, str):
            problems.append(f"content.json's {part} must be a text")
        elif points and not text.strip():
            problems.append(
                f"content.json's {part} is empty: summarise its table's points")
        elif not points and text.strip():
            problems.append(
                f"content.json's {part} must be empty, as its table holds no point")
        elif problem := _length_problem(f"content.json's {part}", text, part):
            problems.append(problem)
        elif part in VALUED_PARTS and (missing := [group["value"] for group in points
                                                   if group["value"] and group["value"].casefold() not in text.casefold()]):
            problems.append(f"content.json's {part} doesn't name {', '.join(missing)}: say, even briefly, how "
                            "its table's points show each value they are grouped under")
    return problems


def data_comparison_problems(comparison, value, data):
    """Why `value` isn't the file of `comparison`, a Comparison, against
    data.json, `data`, empty when it is: step_change_problems() or
    view_check_problems()."""
    if comparison is STEP_CHANGE_COMPARISON:
        return step_change_problems(value, data["observations"], data["reviews"])
    return view_check_problems(value, data["observations"], data["view"])


def step_change_problems(step_change, observations, reviews):
    """Why `step_change`, step_change.json's, isn't the step change from the
    latest previous review in `reviews`, data.json's, to the period's points
    in `observations`, empty when it is, by comparison_problems(): null when
    there is no previous review; each row's change one of STEP_CHANGE_PARTS
    for its review point's part, every to-improve point of the review with a
    row, only an improved one citing nothing, and a row with no review point
    citing the period context point it stands for."""
    return comparison_problems(STEP_CHANGE_COMPARISON, step_change, observations,
                               None if reviews is None else baseline_points(reviews["latest"]))


def view_check_problems(view_check, observations, view):
    """Why `view_check`, view_check.json's, isn't the check of the manager's
    view, `view`, data.json's, against the period's points in
    `observations`, empty when it is, by comparison_problems(): every view
    point with one row, confirmed,
    little_support or contradicted, only little_support citing nothing; and
    a row with no view point not_in_view, citing the points of the theme."""
    return comparison_problems(VIEW_CHECK_COMPARISON, view_check, observations, baseline_points(view))


def comparison_problems(comparison, value, observations, baseline):
    """Why `value`, the file of `comparison`, a Comparison, isn't the
    comparison of `baseline`, {id: (part, point)} or None when there is
    nothing to compare, with the period's points in `observations`,
    data.json's, empty when it is: null exactly when `baseline` is None;
    else a summary, not empty, of at most its MAX_OBSERVATIONS_WORDS words,
    and rows, each {point, kind, evidence} by its row's field names: the
    point one of the baseline's ids, once, or null; the kind one of its
    kinds for the point's part, or for None when it has none; the evidence
    period point ids, each once, at least one but for a kind that may cite
    none, and with null_cites a point of that part among them when the
    point is null; and every baseline point of its every parts with a
    row."""
    what = comparison.file
    if baseline is None:
        return [] if value is None else [f"{what} must be null, as {comparison.absent} to compare with"]
    if not (isinstance(value, dict) and sorted(value) == ["rows", "summary"]
            and isinstance(value["summary"], str) and isinstance(value["rows"], list)):
        return [f"{what} must be {comparison.shape}" + (f", as {comparison.present}" if comparison.present else "")]
    problems = []
    summary = value["summary"]
    if not summary.strip():
        problems.append(
            f"{what}'s summary is empty: summarise {comparison.summary_of}")
    elif problem := _length_problem(f"{what}'s summary", summary, comparison.words):
        problems.append(problem)
    elif ids := POINT_ID_TEXT.findall(summary):
        problems.append(f"{what}'s summary names {', '.join(ids)}: say what the points show in words, as ids "
                        "belong only in the rows' evidence")
    point_field, kind_field, _ = comparison.row
    period = period_points(observations)
    seen = []
    for number, row in enumerate(value["rows"], 1):
        field = f"{what}'s row {number}"
        if not (isinstance(row, dict) and sorted(row) == sorted(comparison.row)
                and (row[point_field] is None or isinstance(row[point_field], str))
                and isinstance(row[kind_field], str) and isinstance(row["evidence"], list)
                and all(isinstance(item, str) for item in row["evidence"])):
            problems.append(f'{field} must be {{"{point_field}": "{comparison.example}" or null, '
                            f'"{kind_field}": "...", "evidence": ["I2", ...]}}')
            continue
        point, kind, evidence = row[point_field], row[kind_field], row["evidence"]
        if point is not None and point not in baseline:
            problems.append(f"{field}'s {point_field}, {point!r}, must be one of {comparison.baseline_points}: "
                            f"{', '.join(baseline) or 'it has none'}, or null for {comparison.null_row}")
            continue
        if point is not None and point in seen:
            problems.append(
                f"{field}'s {point_field}, {point}, has a row already: give each one row")
        seen.append(point)
        part = baseline[point][0] if point else None
        allowed = comparison.kinds[part]
        if kind not in allowed:
            problems.append(f"{field}'s {kind_field}, {kind!r}, must be {' or '.join(allowed)} for "
                            + (f"a {part} point of {comparison.of_baseline}" if part
                               else f"a row with no {point_field}"))
        if unknown := [item for item in evidence if item not in period]:
            problems.append(f"{field}'s evidence names {', '.join(unknown)}, not points of the period: cite the "
                            "brief's ids, such as G1")
        elif len(set(evidence)) != len(evidence):
            problems.append(
                f"{field}'s evidence names a point more than once: name each once")
        elif not evidence and kind not in comparison.may_cite_none:
            problems.append(
                f"{field}'s evidence is empty: cite the period points that show it, by their ids")
        elif point is None and comparison.null_cites and not any(
                period[item][0] == comparison.null_cites for item in evidence):
            problems.append(f"{field} has no {point_field}, so its evidence must cite the period "
                            f"{comparison.null_cites} point it stands for, such as "
                            f"{point_id(comparison.null_cites, 1)}")
    if missing := [point for point, (part, _) in baseline.items() if part in comparison.every and point not in seen]:
        problems.append(
            f"{what} has no row for {', '.join(missing)}: {comparison.missing_hint}")
    return problems


def _length_problem(what, text, part):
    """Why `text`, `what`, the summary of `part`, is too long, or None: more
    than its MAX_OBSERVATIONS_WORDS words, the error giving the target
    alone."""
    if word_count(text) <= MAX_OBSERVATIONS_WORDS[part]:
        return None
    return (f"{what} has {word_count(text)} words, more than {OBSERVATIONS_WORDS[part]}: cut it to about "
            f"{OBSERVATIONS_WORDS[part]}, keeping what matters most")


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
    """{id: (part, point)}: every point of `baseline`, the latest previous
    review or the manager's view as data.json holds it, by its id, part by
    part."""
    return {point["id"]: (part, point) for part in SUMMARY_PARTS for point in baseline[part]}


def point_id(part, number, prefix=""):
    """The id of the `number`th point of `part`, from 1, in its table, after
    `prefix`, REVIEW_ID in the latest previous review, VIEW_ID in the
    manager's view: G1, I2, C3, R-G1 or V-C1."""
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
