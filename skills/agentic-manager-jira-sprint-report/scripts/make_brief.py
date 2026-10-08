"""
Write <report_dir>/brief.json: everything the agent reads to write content.json,
from data.json and the raw comments.

Usage:
    python3 make_brief.py --report-dir <report_dir>

The agent writes only the parts marked [AI Gen.]. Gathering their material
is bookkeeping, not judgment, so it happens here: the agent reads one file
instead of joining data.json's spells, epics and the raw comment files, which
costs tokens and invites slips.

  * Tickets are grouped by epic, each with its commentary group, scope, latest
    estimate, flag and, for blocker candidates, the comments up to the end.
    Work the sprint didn't do (left_out in data.json) isn't listed under epics,
    so commentary doesn't describe it as this sprint's work.
  * Epics come in order of completed pts, commitment and extra together: the
    order Key Achievements takes after the goal's themes. Matching tickets to
    themes is left to the agent, since it is the same reading as the goal
    verdict, which is an interpretation.
  * Comment authors are left out: AI text names teams, never colleagues.
  * goal_tickets separately includes every original commitment ticket, including
    work excluded from commentary, so goal themes have their full denominator.
    Its outcome distinguishes completed, not_completed and removed work.
  * report_facts are the generated report's own sentences and figures, in its
    exact wording, so the retro notes can quote them in a single pass, without
    first generating the report and reading it back.
"""
import argparse
import os
import re

from common import (BRIEF_FILE, DATA_FILE, NO_EPIC, RAW_DIR, SCOPE_GROUPS, allowed_verdicts, display_date,
                    load_json, parse_ts, plain_text, ratio, report_timezone, write_json)
from make_report import Report


def comments(raw_dir, key, zone):
    """A ticket's comments, dated in the reporting timezone like every other
    date, and without their authors."""
    path = os.path.join(raw_dir, "comments", f"{key}.json")
    if not os.path.exists(path):
        return []
    return [{"date": parse_ts(c["created"]).astimezone(zone).strftime("%d/%m/%Y") if c.get("created") else None,
             "text": plain_text(c.get("body"))}
            for c in load_json(path) if plain_text(c.get("body")).strip()]


def plain(markdown):
    """Report text without its links and HTML, as a reader sees it."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", markdown)
    return re.sub(r"<[^>]+>", "", text).replace("\\|", "|")


def report_facts(data):
    """The generated report's figures and sentences, word for word."""
    report = Report(data, {})
    facts = [
        f"Sprint target completion: {plain(report.target_completion_value())}"]
    facts.append(plain(report.commentary()))
    for epic in data["epics"]:
        name = epic["name"] if epic["key"] == NO_EPIC else f"{epic['key']}: {epic['name']}"
        for scope, words in (("original", "of its commitment"), ("extra", "of its extra work")):
            if epic[f"{scope}_stories_total"]:
                facts.append(f"{name} completed " + ratio(
                    epic[f"{scope}_stories_done"], epic[f"{scope}_stories_total"],
                    epic[f"{scope}_points_done"], epic[f"{scope}_points_total"]) + f" {words}")
    return facts


def build_brief(data, raw_dir):
    candidates = set(data["blocker_candidate_keys"])
    zone = report_timezone(data["report_timezone"])
    epics = []
    for epic in data["epics"]:
        tickets = []
        for group in SCOPE_GROUPS:
            for ticket in epic["scope_groups"][group]:
                tickets.append({
                    "key": ticket["key"], "group": group,
                    **{k: ticket[k] for k in ("scope", "points", "status", "flagged", "summary", "description")},
                    **({"comments": comments(raw_dir, ticket["key"], zone)} if ticket["key"] in candidates else {}),
                })
        completed = epic["original_points_done"] + epic["extra_points_done"]
        epics.append({"key": epic["key"], "name": epic["name"], "description": epic["description"],
                      "completed_pts": completed, "tickets": tickets})
    epics.sort(key=lambda e: -e["completed_pts"])
    return {
        "sprint": {
            "name": data["sprint_name"], "status": data["sprint_status"],
            "goal": [line.strip() for line in data["sprint_goal"].splitlines() if line.strip()],
            "start": display_date(data["sprint_start"]), "end": display_date(data["sprint_end"]),
            "today": display_date(data["today"]),
            "goal_verdicts": list(allowed_verdicts(data)),
        },
        "epics": epics,
        "goal_tickets": [{
            **{k: spell[k] for k in ("key", "summary", "points", "outcome")},
            "epic_key": spell["parentKey"] or NO_EPIC,
            "epic_name": spell["parentSummary"] if spell["parentKey"] else "(no epic)",
        } for spell in data["spells"] if spell["counted"] and spell["scope"] == "original"],
        "report_facts": report_facts(data),
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json")
    args = parser.parse_args()
    data = load_json(os.path.join(args.report_dir, DATA_FILE))
    out = os.path.join(args.report_dir, BRIEF_FILE)
    write_json(out, build_brief(data, os.path.join(args.report_dir, RAW_DIR)))
    print("wrote", out)


if __name__ == "__main__":
    main()
