"""What the skill's scripts share: the prep folder's name and the closed set of
files it holds, how to find a prep's folder, the request a prep is built for
and who the person is in each source. The rules of each file are one function,
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


def expected_files():
    """Every file a prep folder holds, and nothing else: the request and who
    the person is in each source."""
    return {REQUEST, IDENTITIES}


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
