"""What the skill's scripts share: the prep folder's name and the closed set of
files it holds, how to find a prep's folder, the request a prep is built for,
who the person is in each source, the parts every summary has, the manager's
view, the person's previous feedback, check-ins and the manager's notes. The
rules of each file are one function, applied when it is written and by the
final check, so the two can't differ.
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
from agentic_manager.jira import JiraClient, plain_text  # noqa: E402,F401
from agentic_manager.logseq import graph_path, links, notes  # noqa: E402,F401
from agentic_manager.output_file import read_json, target, write_output_file  # noqa: E402,F401
from agentic_manager.protocol import fill as fill_protocol  # noqa: E402,F401
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
# Every summary the skill records, of the manager's view, feedback, check-ins
# or notes, has the same parts, so each reads, and is compared with the evidence, the same
# way: each a list of points in the agent's words, a part with nothing to say
# left empty. A point is a sentence; only one far longer is refused, as a
# length is room, not a quota. A point that is good or to improve also names
# the company value it shows most clearly, or none when none fits, so the
# writing step can speak to the values from what was gathered; a context point
# is neither, so it names none.
SUMMARY_PARTS = {"going_well": "what is going well or exceeding",
                 "to_improve": "what are improvement or stretch areas",
                 "context": "facts that are neither good nor bad, such as a long absence or a change of role"}
VALUED_PARTS = ("going_well", "to_improve")
POINT_WORDS = 25
MAX_POINT_WORDS = 40
VALUES = "values"
SUMMARY_HELP = "\n".join(
    f"  {part:<11} {meaning}, each point "
    + ('{"point": "...", "value": "..."}, value the company value it shows most clearly, as rules.py prints '
       'them, or null when none fits' if part in VALUED_PARTS else "a sentence")
    for part, meaning in SUMMARY_PARTS.items())
# The manager's overall view of the person, summarised: guidance for the
# writing step, the only one that reads it, so the evidence is gathered without
# it and can contradict it.
ORIENTATION = "orientation.json"
# What the manager gives, previous feedback or check-ins, is a list of
# pieces, each a summary with the days it covers when it gives them, null
# otherwise, so a note with no date still counts; a piece of the same days
# twice is one recorded twice.
PIECE_DAYS = ("start", "end")
# The person's previous feedback, such as reviews or a colleague's feedback,
# with its rating when it gives one: a rating must be one of the company's,
# one on an old scale is left out. Feedback with an end day must end at most
# FEEDBACK_YEARS before the period starts: older feedback says little about
# the person now.
FEEDBACK = "feedback.json"
FEEDBACK_FIELDS = (*PIECE_DAYS, "rating")
FEEDBACK_YEARS = 2
# The person's check-ins, their OKRs and 1:1 notes, shared with them, unlike
# the manager's own notes: what they and the manager agreed during the period,
# so a dated piece must overlap it. Read with judgment by the writing step,
# never tracked as commitments.
CHECK_INS = "check-ins.json"
# The manager's own notes on the person in their vault: from the journals of
# the period, what they noticed, each point with the days it was seen on, a
# pattern one point with all its days; from the person's pages, only context,
# which has no date. Read by subagents, a month of journals each, then merged.
NOTES = "notes.json"
RATINGS = "perf-review-ratings"


def expected_files():
    """Every file a prep folder holds, and nothing else: the request, who the
    person is in each source, the manager's view of them, their previous
    feedback, their check-ins and the manager's notes on them."""
    return {REQUEST, IDENTITIES, ORIENTATION, FEEDBACK, CHECK_INS, NOTES}


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
    if not is_list:
        return _is_text(value)
    return (isinstance(value, list) and bool(value) and all(_is_text(item) for item in value)
            and len(set(value)) == len(value))


def _is_text(item):
    """Whether `item` is a text that isn't blank."""
    return isinstance(item, str) and bool(item.strip())


def company_names(key):
    """The names of the company setting `key`'s entries, such as each value
    of company.values, in the config's order."""
    return [next(iter(entry.values())) for entry in company_setting(key)]


def orientation_problems(orientation, values):
    """Why `orientation` isn't the summary of the manager's view, empty when
    it is, by summary_problems()."""
    return summary_problems(orientation, "the orientation", values)


def feedback_problems(feedback, request, ratings, values):
    """Why `feedback` isn't the person's previous feedback for `request`, empty
    when it is: pieces, by pieces_problems(), each with a rating too, null or
    one of `ratings`, and ending, when it has an end day, from
    earliest_feedback_end() to the period's end."""
    earliest, latest = earliest_feedback_end(
        request), date.fromisoformat(request["end"])

    def rules(piece, days, what):
        problems = []
        if piece["rating"] is not None and piece["rating"] not in ratings:
            problems.append(f"{what}'s rating, {piece['rating']!r}, must be one of the company's: "
                            f"{', '.join(ratings)}, or null when it gives none of them")
        if "end" in days and not earliest <= days["end"] <= latest:
            problems.append(f"{what} ends on {days['end']:%d/%m/%Y}: only feedback that ends from "
                            f"{earliest:%d/%m/%Y} to {latest:%d/%m/%Y} counts; leave it out")
        return problems
    return pieces_problems(feedback, ("feedback", "feedback"), FEEDBACK_FIELDS, values, rules)


def check_ins_problems(check_ins, request, values):
    """Why `check_ins` aren't the person's check-ins for `request`,
    empty when they are: pieces, by pieces_problems(), each overlapping the
    period when it has a day."""
    first, last = date.fromisoformat(
        request["start"]), date.fromisoformat(request["end"])

    def rules(piece, days, what):
        if days.get("end", first) < first or days.get("start", last) > last:
            return [f"{what} covers no day of the period, {first:%d/%m/%Y} to {last:%d/%m/%Y}: leave it out"]
        return []
    return pieces_problems(check_ins, ("check-ins", "check-in"), PIECE_DAYS, values, rules)


def notes_problems(notes, values, days):
    """Why `notes` aren't the summary of the manager's notes, empty when they
    are: summary_problems() with `days`, the days of the notes read."""
    return summary_problems(notes, "the notes summary", values, days)


def pieces_problems(value, names, fields, values, rules):
    """Why `value` isn't a list of pieces, empty when it is, `names` naming
    them all and one, such as ("check-ins", "check-in"): {"pieces": [...]}, none when there are none, each with
    `fields` and the parts of SUMMARY_PARTS, its days null or dates as
    YYYY-MM-DD, starting no later than it ends, no two of the same days, its
    summary meeting summary_problems() with `values`, and
    each meeting `rules(piece, days, what)`, which gets its parsed days and
    the name to give it in a problem."""
    kind, item = names
    if not (isinstance(value, dict) and list(value) == ["pieces"] and isinstance(value["pieces"], list)):
        return [f'the {kind} must be {{"pieces": [...]}}, with [] when there are none']
    problems, periods = [], []
    for number, piece in enumerate(value["pieces"], 1):
        what = f"{item} {number}"
        if not (isinstance(piece, dict) and sorted(piece) == sorted((*fields, *SUMMARY_PARTS))):
            problems.append(f"{what} must have the fields {', '.join((*fields, *SUMMARY_PARTS))}, "
                            f"with null for what it doesn't give")
            continue
        problems += summary_problems({part: piece[part]
                                     for part in SUMMARY_PARTS}, what, values)
        days = {}
        for field in PIECE_DAYS:
            if piece[field] is None:
                continue
            try:
                days[field] = date.fromisoformat(
                    piece[field] if isinstance(piece[field], str) else "")
            except ValueError:
                problems.append(
                    f"{what}'s {field}, {piece[field]!r}, must be a date as YYYY-MM-DD, or null")
        problems += rules(piece, days, what)
        if len(days) < 2:
            continue
        if days["start"] > days["end"]:
            problems.append(f"{what} starts after it ends")
        periods.append((days["start"], days["end"]))
    problems += [f"two pieces of the {kind} cover {start:%d/%m/%Y} to {end:%d/%m/%Y}: record each once"
                 for start, end in sorted(set(periods)) if periods.count((start, end)) > 1]
    return problems


def pieces_order(piece):
    """The key that sorts pieces: those with days first, oldest first, then
    those with none, kept in the order given."""
    first, last = piece["start"] or piece["end"], piece["end"] or piece["start"]
    return (first is None, first or "", last or "")


def earliest_feedback_end(request):
    """The first day dated previous feedback may end on: FEEDBACK_YEARS before the
    request's period starts, the 28th for a 29 February."""
    start = date.fromisoformat(request["start"])
    try:
        return start.replace(year=start.year - FEEDBACK_YEARS)
    except ValueError:
        return start.replace(year=start.year - FEEDBACK_YEARS, day=28)


def summary_problems(summary, what, values, days=None):
    """Why `summary`, the summary of `what`, such as "the orientation", doesn't
    have the parts of SUMMARY_PARTS, empty when it does: each a list of
    points, a point of VALUED_PARTS {"point", "value"}, its value null or one
    of `values`, any other a text; each point's text not blank, of at most
    MAX_POINT_WORDS words, and listed once, with at least one point in all.
    With `days`, the days notes were taken on as YYYY-MM-DD, a point of
    VALUED_PARTS also has "dates", the days it was seen on, each one of
    `days`, and the summary may be empty, as notes may hold nothing to say."""
    if not (isinstance(summary, dict) and sorted(summary) == sorted(SUMMARY_PARTS)):
        found = ", ".join(summary) if isinstance(
            summary, dict) else repr(summary)
        return [f"{what} must have the parts {', '.join(SUMMARY_PARTS)}, not {found or 'none'}"]
    fields = ("point", "value") if days is None else (
        "point", "value", "dates")
    problems = []
    for part, points in summary.items():
        valued = part in VALUED_PARTS
        if not (isinstance(points, list) and all(_is_point(point, fields if valued else None) for point in points)):
            shape = ("{" + ", ".join(f'"{field}": ' + {"point": '"..."', "value": '"..." or null',
                                                       "dates": '["YYYY-MM-DD", ...]'}[field] for field in fields) + "}"
                     if valued else "a sentence")
            problems.append(
                f"{what}'s {part} must be a list of points, each {shape}, or [] for none")
            continue
        texts = [point["point"] if valued else point for point in points]
        problems += [f"{what}'s {part} lists {text!r} more than once: list each once"
                     for text in sorted(set(texts)) if texts.count(text) > 1]
        problems += [f"{what}'s {part}: {text[:60]!r}... has {len(text.split())} words: keep a point to a "
                     f"sentence of about {POINT_WORDS}, at most {MAX_POINT_WORDS}, or split it"
                     for text in texts if len(text.split()) > MAX_POINT_WORDS]
        if not valued:
            continue
        problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s value, {point['value']!r}, must be one of "
                     f"the company's: {', '.join(values)}, or null when none fits"
                     for point in points if point["value"] is not None and point["value"] not in values]
        if days is not None:
            problems += [f"{what}'s {part}: {point['point'][:60]!r}...'s dates, {point['dates']!r}, must each be a "
                         "day a note was taken on, listed once"
                         for point in points if len(set(point["dates"])) != len(point["dates"])
                         or not set(point["dates"]) <= set(days)]
    if not problems and days is None and not any(summary.values()):
        problems.append(
            f"{what} has no points: summarise what it says in its parts")
    return problems


def _is_point(point, fields):
    """Whether `point` is a point of a part: with `fields`, an object of
    them, its point a text that isn't blank, its value a text or null and
    its dates, if it has them, a list of texts, at least one; without, such a
    text alone."""
    if fields is None:
        return _is_text(point)
    return (isinstance(point, dict) and sorted(point) == sorted(fields) and _is_text(point["point"])
            and (point["value"] is None or isinstance(point["value"], str))
            and ("dates" not in point or (isinstance(point["dates"], list) and bool(point["dates"])
                                          and all(isinstance(day, str) for day in point["dates"]))))
