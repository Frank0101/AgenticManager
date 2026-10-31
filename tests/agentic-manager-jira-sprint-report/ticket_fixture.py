"""Hand-made tickets and changelog entries for the unit tests of a ticket's
events and what is built from them, in test_common.py and
test_build_sprint_data.py: Sprint 7 starts on 02/03/2026 at 09:00 and closes
on 13/03 at 17:00, at +01:00.
"""

import os
import sys
from datetime import timedelta, timezone

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import common  # noqa: E402
sys.path.insert(0, TEST_DIR)
from sprint_fixture import STATUS  # noqa: E402

START = "2026-03-02T09:00:00.000+0100"
START_DATE = "2026-03-02"
CLOSE = "2026-03-13T17:00:00.000+0100"
FIELDS = ("customfield_flag", "customfield_points")
PLUS_ONE = timezone(timedelta(hours=1))
CATEGORIES = {i: category for i, category in STATUS.values()}

# Sprint 6 closed an hour before Sprint 7 started.
PREVIOUS = {"id": 6, "name": "Sprint 6",
            "completeDate": "2026-03-02T08:00:00.000+0100"}


def at(day, time="10:00"):
    return f"2026-{day}T{time}:00.000+0100"


def raw(key, created="2026-02-20T10:00:00.000+0100", status="To Do", points=None, resolution=None,
        parent=None, **fields):
    """A raw issue as Jira's API returns it today."""
    return {"key": key, "fields": {
        "summary": f"Summary of {key}", "created": created,
        "status": {"id": STATUS[status][0], "name": status, "statusCategory": {"key": STATUS[status][1]}},
        "resolution": {"name": resolution} if resolution else None,
        "issuetype": {"name": "Story"}, "priority": {"name": "Medium"},
        "parent": ({"id": f"id-{parent}", "key": parent, "fields": {"summary": f"Epic {parent}"}}
                   if parent else None),
        "customfield_points": points, **fields}}


def done(key, **kwargs):
    return raw(key, status="Done", resolution="Done", **kwargs)


def joined(created, sprint="7"):
    return {"created": created, "field": "sprint", "from": "", "to": sprint,
            "fromString": None, "toString": None}


def left(created, sprint="7"):
    return {"created": created, "field": "sprint", "from": sprint, "to": "",
            "fromString": None, "toString": None}


def changed(created, field, old, new, old_id=None, new_id=None):
    return {"created": created, "field": field, "from": old_id, "fromString": old,
            "to": new_id, "toString": new}


def carried(created=PREVIOUS["completeDate"]):
    """Moved from Sprint 6 into Sprint 7 when Sprint 6 closed; Jira keeps
    Sprint 6 in the field."""
    return {"created": created, "field": "sprint", "from": "6", "to": "6, 7",
            "fromString": None, "toString": None}


def points(created, old, new):
    return changed(created, "points", old, new)


def flag(created, on=True):
    return changed(created, "flagged", None if on else "Impediment", "Impediment" if on else None,
                   None if on else "[10000]", "[10000]" if on else None)


def context(epics=None, previous=None):
    return common.Context("7", START, CATEGORIES, FIELDS, epics or {}, PLUS_ONE, previous)


def events(issue, changes):
    """The ticket's events, from which the model works out its spells."""
    return common.ticket_events(issue, changes, context(), CLOSE)
