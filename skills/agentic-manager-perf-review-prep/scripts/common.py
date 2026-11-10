"""What the skill's scripts share: the prep folder's name and the closed set of
files it holds, how to find a prep's folder, the request a prep is built for,
who the person is in each source, the parts every summary has, the manager's
view and the person's previous feedback. The rules of each file are one function,
applied when it is written and by the final check, so the two can't differ.
Scripts import the shared library's names from here, so they don't depend on
the order of their imports.
"""
from datetime import date
import json
import os
import sys

# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
from agentic_manager.config import company_setting  # noqa: E402,F401
from agentic_manager.failures import stops_on_failure  # noqa: E402,F401
from agentic_manager.github import commit_authors, gh_available, gh_orgs, gh_signed_in, profile_name  # noqa: E402,F401
from agentic_manager.jira import JiraClient  # noqa: E402,F401
from agentic_manager.logseq import graph_path, links, notes  # noqa: E402,F401
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.output_folder import DAY_FOLDER, clear_folder, day_folder, output_folder  # noqa: E402,F401
from agentic_manager.period import add_period_arguments, period_problem, shown  # noqa: E402,F401
from agentic_manager.text import as_name  # noqa: E402,F401

# The skill's output folder, and a prep folder's files in it: the request the
# manager confirmed, which every later step reads rather than being told again.
FOLDER_NAME = "perf-review-preps"
REQUEST = "request.json"
# The request's fields: the person as the manager named them, and the
# period's first and last days, as YYYY-MM-DD. How the period reads is worked
# out from them wherever it is shown, never stored.
REQUEST_FIELDS = ("person", "start", "end")
# Who the person is in each source the skill reads, as the manager confirmed,
# by the fields each records: an account's id and the name it gives, or in the
# vault the links about the person, their tag and the pages about them, such
# as [[Jane]] and [[Jane Promotion]], whose aliases count too. A field is a
# text, or, in LIST_FIELDS, a list of texts. A source the manager says they
# aren't in is {"absent": true}, so a later step reports them as not there
# rather than as having done nothing.
IDENTITIES = "identities.json"
ACCOUNT = ("id", "name")
SOURCES = {"jira-api": ACCOUNT, "github-cli": ACCOUNT,
           "notion-mcp": ACCOUNT, "slack-mcp": ACCOUNT, "logseq-fs": ("links",)}
LIST_FIELDS = {"links"}
ABSENT = {"absent": True}
# Every summary the skill records, of the manager's view or of feedback, has
# the same parts, so each reads, and is compared with the evidence, the same
# way: each a list of points in the agent's words, a part with nothing to say
# left empty. A point is a sentence; only one far longer is refused, as a
# length is room, not a quota.
SUMMARY_PARTS = {"going_well": "what is going well or exceeding",
                 "to_improve": "what are improvement or stretch areas",
                 "context": "facts that are neither good nor bad, such as a long absence or a change of role"}
POINT_WORDS = 25
MAX_POINT_WORDS = 40
# The manager's overall view of the person, summarised: guidance for the
# writing step, the only one that reads it, so the evidence is gathered without
# it and can contradict it.
ORIENTATION = "orientation.json"
# The person's previous feedback, such as reviews or a colleague's feedback,
# taken as the manager gives it: each a summary, with its days and its rating
# when the manager gives them, null otherwise, so a note with neither still
# counts. A rating must be one of the company's: one on an old scale is left
# out. Feedback with an end day must end at most REVIEW_YEARS before the
# period starts: older feedback says little about the person now.
FEEDBACK = "feedback.json"
REVIEW_FIELDS = ("start", "end", "rating")
REVIEW_YEARS = 2
RATINGS = "perf-review-ratings"


def expected_files():
    """Every file a prep folder holds, and nothing else: the request, who the
    person is in each source, the manager's view of them and their previous
    feedback."""
    return {REQUEST, IDENTITIES, ORIENTATION, FEEDBACK}


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


def stdin_json(usage):
    """The JSON the agent wrote on stdin. Exits, showing `usage`, the input
    to send, when it isn't JSON."""
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise SystemExit(f"the input isn't JSON: {error}\n\n{usage}")


def request_problems(request, today):
    """Why `request` isn't a valid request on `today`, empty when it is: its
    fields are REQUEST_FIELDS, the person is named by letters or digits, and
    the period's days are dates as YYYY-MM-DD of a period that can be
    reported on."""
    if not isinstance(request, dict):
        return ["the request must be a JSON object"]
    problems = []
    if sorted(request) != sorted(REQUEST_FIELDS):
        problems.append(f"the request's fields must be {', '.join(REQUEST_FIELDS)}, "
                        f"not {', '.join(request) or 'none'}")
    person = request.get("person")
    if not isinstance(person, str) or not as_name(person):
        problems.append(f"{person!r} must name the person, such as Jane Doe")
    days = {}
    for field in ("start", "end"):
        value = request.get(field)
        try:
            days[field] = date.fromisoformat(
                value if isinstance(value, str) else "")
        except ValueError:
            problems.append(
                f"the request's {field}, {value!r}, must be a date as YYYY-MM-DD")
    if len(days) == 2 and (problem := period_problem(days["start"], days["end"], today)):
        problems.append(problem)
    return problems


def identities_problems(identities):
    """Why `identities` doesn't say who the person is in each source, empty
    when it does: it has each of SOURCES, and each is ABSENT, or holds the
    source's fields, each a text that isn't blank or, in LIST_FIELDS, a list
    of such texts, at least one, each once."""
    if not isinstance(identities, dict):
        return ["the identities must be a JSON object"]
    problems = []
    if sorted(identities) != sorted(SOURCES):
        problems.append(f"the identities must be those of {', '.join(SOURCES)}, "
                        f"not {', '.join(identities) or 'none'}")
    for source, fields in SOURCES.items():
        found = identities.get(source)
        if source not in identities or found == ABSENT:
            continue
        if not (isinstance(found, dict) and sorted(found) == sorted(fields)
                and all(_filled(found[field], field in LIST_FIELDS) for field in fields)):
            wanted = "{" + ", ".join(f'"{field}": ' + ('["...", ...]' if field in LIST_FIELDS else '"..."')
                                     for field in fields) + "}"
            problems.append(f"{source} must be {wanted}, or {{\"absent\": true}} when the person isn't in "
                            f"it, not {found!r}")
    return problems


def _filled(value, is_list):
    """Whether `value` is a text that isn't blank or, `is_list`, a list of
    such texts, at least one, each once."""
    def text(item):
        return isinstance(item, str) and bool(item.strip())
    if not is_list:
        return text(value)
    return (isinstance(value, list) and bool(value) and all(text(item) for item in value)
            and len(set(value)) == len(value))


def orientation_problems(orientation):
    """Why `orientation` isn't the summary of the manager's view, empty when
    it is, by summary_problems()."""
    return summary_problems(orientation, "the orientation")


def feedback_problems(feedback, request, ratings):
    """Why `feedback` isn't the person's previous feedback for `request`, empty
    when it is: {"reviews": [...]}, none for a person with none, each with
    REVIEW_FIELDS and the parts of SUMMARY_PARTS, its days null or dates as
    YYYY-MM-DD, starting no later than it ends, ending from
    earliest_review_end() to the period's end, its rating null or one of
    `ratings`, and no two of the same days."""
    if not (isinstance(feedback, dict) and list(feedback) == ["reviews"] and isinstance(feedback["reviews"], list)):
        return ['the feedback must be {"reviews": [...]}, with [] when the person has no previous feedback']
    earliest, latest = earliest_review_end(
        request), date.fromisoformat(request["end"])
    problems, periods = [], []
    for number, review in enumerate(feedback["reviews"], 1):
        what = f"feedback {number}"
        if not (isinstance(review, dict) and sorted(review) == sorted((*REVIEW_FIELDS, *SUMMARY_PARTS))):
            problems.append(f"{what} must have the fields {', '.join((*REVIEW_FIELDS, *SUMMARY_PARTS))}, "
                            "with null for a day or rating the feedback doesn't give")
            continue
        problems += summary_problems({part: review[part]
                                     for part in SUMMARY_PARTS}, what)
        if review["rating"] is not None and review["rating"] not in ratings:
            problems.append(f"{what}'s rating, {review['rating']!r}, must be one of the company's: "
                            f"{', '.join(ratings)}, or null when it gives none of them")
        days = {}
        for field in ("start", "end"):
            if review[field] is None:
                continue
            try:
                days[field] = date.fromisoformat(
                    review[field] if isinstance(review[field], str) else "")
            except ValueError:
                problems.append(
                    f"{what}'s {field}, {review[field]!r}, must be a date as YYYY-MM-DD, or null")
        if "end" in days and not earliest <= days["end"] <= latest:
            problems.append(f"{what} ends on {days['end']:%d/%m/%Y}: only feedback that ends from "
                            f"{earliest:%d/%m/%Y} to {latest:%d/%m/%Y} counts; leave it out")
        if len(days) < 2:
            continue
        if days["start"] > days["end"]:
            problems.append(f"{what} starts after it ends")
        periods.append((days["start"], days["end"]))
    problems += [f"two pieces of feedback cover {start:%d/%m/%Y} to {end:%d/%m/%Y}: record each once"
                 for start, end in sorted(set(periods)) if periods.count((start, end)) > 1]
    return problems


def feedback_order(review):
    """The key that sorts previous feedback: what has days first, oldest
    first, then what has none, kept in the order given."""
    first, last = review["start"] or review["end"], review["end"] or review["start"]
    return (first is None, first or "", last or "")


def earliest_review_end(request):
    """The first day dated previous feedback may end on: REVIEW_YEARS before the
    request's period starts, the 28th for a 29 February."""
    start = date.fromisoformat(request["start"])
    try:
        return start.replace(year=start.year - REVIEW_YEARS)
    except ValueError:
        return start.replace(year=start.year - REVIEW_YEARS, day=28)


def summary_problems(summary, what):
    """Why `summary`, the summary of `what`, such as "the orientation", doesn't
    have the parts of SUMMARY_PARTS, empty when it does: each a list of
    points, each a text that isn't blank, of at most MAX_POINT_WORDS words,
    and listed once, with at least one point in all."""
    if not (isinstance(summary, dict) and sorted(summary) == sorted(SUMMARY_PARTS)):
        found = ", ".join(summary) if isinstance(
            summary, dict) else repr(summary)
        return [f"{what} must have the parts {', '.join(SUMMARY_PARTS)}, not {found or 'none'}"]
    problems = []
    for part, points in summary.items():
        if not (isinstance(points, list) and all(isinstance(point, str) and point.strip() for point in points)):
            problems.append(
                f"{what}'s {part} must be a list of points, each a sentence, or [] for none")
            continue
        problems += [f"{what}'s {part} lists {point!r} more than once: list each once"
                     for point in sorted(set(points)) if points.count(point) > 1]
        problems += [f"{what}'s {part}: {point[:60]!r}... has {len(point.split())} words: keep a point to a "
                     f"sentence of about {POINT_WORDS}, at most {MAX_POINT_WORDS}, or split it"
                     for point in points if len(point.split()) > MAX_POINT_WORDS]
    if not problems and not any(summary.values()):
        problems.append(
            f"{what} has no points: summarise what it says in its parts")
    return problems
