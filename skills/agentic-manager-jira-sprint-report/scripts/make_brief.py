"""Write <report_dir>/brief.json: everything the agent reads to write
content.json, from data.json alone.

The agent writes only the parts marked [AI Gen.]. Gathering their material is
bookkeeping, not judgment, so it happens here: the agent reads one file instead
of joining data.json's spells, epics and comments, which costs tokens and
invites slips. Like the report and the charts, it is a view of data.json: it
never reads the raw files, so every fact it gives is the model's.
"""
import argparse
import os

from common import (BRIEF_FILE, DATA_FILE, SCOPE_GROUPS, allowed_verdicts, chunks, display_date,
                    epic_title, link_text, read_json, spell_epic, write_json)
from make_report import Report


def build_brief(data):
    """The brief: the sprint, each epic's tickets, goal_tickets, report_facts
    and ticket_events. Tickets are grouped by epic, each with its commentary
    group, scope, latest estimate, flag and, for blocker candidates, the
    comments up to the end. Work the sprint didn't do (data.json's left_out)
    isn't listed under the epics, so the commentary doesn't describe it as this
    sprint's work, but goal_tickets holds every ticket of the commitment, that
    work included, so each goal theme has its full denominator."""
    comments = data["blocker_comments"]
    epics = []
    for epic in data["epics"]:
        tickets = []
        for group in SCOPE_GROUPS:
            for ticket in epic["scope_groups"][group]:
                tickets.append({
                    "key": ticket["key"], "group": group,
                    # Still in the previous sprint when it closed, so the
                    # agent sees work that spans sprints, as the charts do.
                    "carried_in": ticket["carriedIn"],
                    **{k: ticket[k] for k in ("scope", "points", "status", "flagged", "summary")},
                    **first_chunk(ticket["description"]),
                    **({"comments": brief_comments(comments[ticket["key"]])} if ticket["key"] in comments else {}),
                })
        completed = epic["original_points_done"] + epic["extra_points_done"]
        epics.append({"key": epic["key"], "name": epic["name"], **first_chunk(epic["description"]),
                      "completed_pts": completed, "tickets": tickets})
    # By completed pts, commitment and extra together: the order Key
    # Achievements takes after the goal's themes. Matching tickets to themes
    # is left to the agent: it is the same reading as the goal verdict, an
    # interpretation.
    epics.sort(key=lambda e: -e["completed_pts"])
    return {
        "sprint": {
            "name": data["sprint_name"], "status": data["sprint_status"],
            "goal": data["sprint_goal"],
            "start": display_date(data["sprint_start"]), "end": display_date(data["sprint_end"]),
            "today": display_date(data["today"]),
            "goal_verdicts": list(allowed_verdicts(data)),
        },
        "epics": epics,
        "goal_tickets": [{
            **{k: spell[k] for k in ("key", "summary", "points", "outcome")},
            **dict(zip(("epic_key", "epic_name"), spell_epic(spell))),
        } for spell in data["spells"] if spell["scope"] == "original"],
        "report_facts": report_facts(data),
        "ticket_events": {key: brief_events(data["ticket_events"][key])
                          for key in dict.fromkeys(t["key"] for epic in epics for t in epic["tickets"])},
    }


def brief_events(events):
    """A ticket's status changes, in time order, dated as the brief dates
    everything: how the work moved, which the spells don't show. The other
    changes are left out: the spells and report_facts give its sprint moves
    and estimates, and the rest doesn't tell how the work went."""
    return [{"date": display_date(e["date"]), "from": e["from"], "to": e["to"]}
            for e in events if e["type"] == "status_changed"]


def brief_comments(comments):
    """A blocker candidate's comments, as data.json holds them, without
    authors, dated as the brief dates everything."""
    return [{"date": display_date(c["date"]) if c["date"] else None, "text": c["text"]} for c in comments]


def first_chunk(description):
    """The description's first chunk and, when there are more, how many in all:
    the agent reads the rest with read_description.py only when it could matter."""
    pieces = chunks(description)
    return {"description": pieces[0], **({"description_chunks": len(pieces)} if len(pieces) > 1 else {})}


def report_facts(data):
    """The generated report's figures and sentences, word for word, so the
    retro notes can quote them without first generating the report and
    reading it back."""
    report = Report(data, {})
    facts = [f"Sprint target completion: {link_text(report.target_completion_value())}",
             link_text(report.commentary())]
    for epic in data["epics"]:
        name = epic_title(epic)
        for scope, words in (("original", "of its commitment"), ("extra", "of its extra work")):
            if epic[f"{scope}_stories_total"]:
                facts.append(
                    f"{name} completed {report.epic_done(epic, scope)} {words}")
    return facts


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json")
    args = parser.parse_args()
    data = read_json(os.path.join(args.report_dir, DATA_FILE))
    out = os.path.join(args.report_dir, BRIEF_FILE)
    write_json(out, build_brief(data))
    print("wrote", out)


if __name__ == "__main__":
    main()
