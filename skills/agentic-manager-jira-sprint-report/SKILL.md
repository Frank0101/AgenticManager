---
name: agentic-manager-jira-sprint-report
description: Writes a short, exec-ready report of one Jira sprint, closed or still running - goal outcome, carry-over from the previous sprint, key achievements, blockers and risks, a dated scope timeline (added, descoped, completed) with its commentary, a burndown, delivery by epic and notes for the retro - as Markdown with SVG charts, built from the Jira REST API. Use when the user asks for a sprint report, summary or review, or "how did the sprint go" / "how is the sprint going", for a project, board or sprint.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/prepare_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/finish_report.py *)
---

# Sprint Report

Writes a short, exec-ready report of one Jira sprint, closed or still running. Scripts generate the whole report: figures, tables, charts, the timeline and its commentary. You write only the parts the report marks [AI Gen.]: the goal outcome, the epic commentary, Key Achievements, Blockers & Risks and the retro notes.

The report's files go to the `jira-sprint-reports` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

## Prerequisite

Run `agentic-manager-utils-check-config`. If it fails, stop here.

This skill needs the `jira-api` source. If `sources.workflow.jira-api.enabled` isn't `true`, stop and tell the user to enable it, showing its `setup` and the config `path`. The scripts read its settings themselves; never read, pass or show them.

## 1. Prepare

`<scripts>` is `${CLAUDE_SKILL_DIR}/scripts`; call the scripts by exactly that path, so they run without a permission prompt.

```bash
python3 <scripts>/prepare_report.py <selector>
```

| The user names            | Selector                                  |
| ------------------------- | ----------------------------------------- |
| a sprint id               | `--sprint-id 123`                         |
| a project key             | `--project PROJ` (the last closed sprint) |
| a project, current sprint | `--project PROJ --active`                 |
| a board id                | `--board 42` (add `--active` as needed)   |
| a sprint name             | `--sprint-name "Sprint 3" --project PROJ` |

If the user doesn't say which project, board or sprint, ask; don't guess. A bare number is tried as `--sprint-id`, then as `--board` if Jira returns 404. If the script fails, report its message. Two failures have a fix: a discrepancy with Jira's sprint report usually means the sprint changed during the fetch, so run it again; an empty sprint report means the board doesn't serve it, so retry with `--board` and another scrum board of the project.

It prints one line of JSON with `report_dir`, `temporary`, `brief` and `content_path`. Read the `brief`: the sprint and its goal, the verdicts you can choose from, each epic's tickets with their commentary `group`, `scope` (`original` is the commitment, `extra` was added later), latest `points`, `status`, `flagged`, description and, for blocker candidates, their comments, and `report_facts`, the report's own figures in its exact wording.

## 2. Write content.json

Write it through the shared writer, with the `content_path` from step 1, and the same way for every revision; never with your own file tools:

```bash
python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py --name jira-sprint-reports --path '<content_path>' <<'END_OF_FILE'
{
  "goal_verdict": "Partially met",
  "epic_commentary": {
    "PROJ-10": {
      "completed": "Staff can now sign in with their work account.",
      "in_review": "Password reset by email is built and waiting for review.",
      "not_completed": "Audit logging of sign-ins hasn't started.",
      "descoped": "The admin screen for sign-in providers was dropped."
    }
  },
  "key_achievements": "One paragraph.",
  "blockers_risks": "One paragraph.",
  "retro_notes": ["4 tickets (8 pts) were descoped: was the commitment too large?"]
}
END_OF_FILE
```

Write the parts in this order.

**Goal themes.** A theme is usually the text before a goal line's colon ("Search" in "Search: let staff find past orders"). Its tickets are those of the epic whose name contains the theme's word, plus any ticket whose summary names it, in any epic. If a mapping isn't obvious, ask the user to confirm it.

**`epic_commentary`**: for every epic in the brief, one sentence per `group` it has tickets in, and none for the others; `{}` for an epic with none. Say what changed for users or the system ("Staff can now sign in with their work account"), using the epic's description for context and each ticket's summary and description. Merge small items. At most 60 words per epic. Describe a ticket with no description from its summary alone; if a whole group has only bare summaries, add that "the tickets carry no detail".

**`key_achievements`**: one paragraph of at most 80 words on what the sprint achieved, a step above the epic commentary: the `completed` tickets, by goal theme in the goal's order, then the other epics in the brief's order.

**`blockers_risks`**: one paragraph of at most 80 words on the commitment still open: tickets with `scope` `original` in the `in_review` and `not_completed` groups. Group them by goal theme, then by epic, and say what the open work holds back. Give a reason only where a comment states one ("under discussion with Security"), and say when a ticket is `flagged`. If nothing from the commitment is open, say so.

**`goal_verdict`**: one of the brief's `goal_verdicts`, word for word. A theme is met when none of its commitment tickets is open at the end (not completed or in review); extra work doesn't decide it, and descoped work doesn't count against it. Closed sprint: "Fully met" if every theme is met, "Not met" if none is, otherwise "Partially met". Running sprint, past its halfway day: "At risk" if any theme has more than half its commitment pts open, otherwise "On track". If part of a theme maps to no ticket, judge by the tickets that do, and raise it when you tell the user the report is ready.

**`retro_notes`**: 1 to 5 notes for the team's retro, each a fact followed by a question ending with "?". Look across the report for what most departed from the plan and what the team can learn from it: patterns between epics, the timeline and the goal, not only the largest figure. Quote figures and ticket references word for word from `report_facts`, or as `KEY (N pts)` with the brief's `points`; don't derive new figures. Frame causes as questions, never as findings the data can't show.

Rules for all of it (`finish_report.py` rejects text that breaks the ones it can check):

- No ticket keys except in the retro notes, and no figures except quoted ones in the retro notes: the generated parts show them.
- Only what the tickets, descriptions and comments say. Never carry customer data from descriptions (names, contact details, account IDs, financial details), and never name colleagues: name the team ("with Security").
- A work item is a ticket; it is completed, never closed. Write pts, never points; numbers as digits, never "one" to "twenty"; dates as `DD/MM/YYYY`. No em dashes.

## 3. Finish

```bash
python3 <scripts>/finish_report.py --report-dir <report_dir>
```

It draws the charts, writes the report and checks it, printing only what failed. Fix `content.json` and run it again until it passes. Never edit the report by hand, and never give the user a report that fails.

## 4. Tell the user

Say that the report is ready, with a Markdown link to its full path, which the script prints. Don't recap anything the report already shows. Add only what it doesn't: a doubt about your own judgment, such as a goal theme that maps to no ticket, and, if `temporary` is `true`, that the folder is temporary and setting `output.root` in the config keeps reports.
