---
name: agentic-manager-jira-sprint-report
description: Writes a short, exec-ready report of one Jira sprint, closed or still running - goal outcome, key achievements, blockers and risks, delivery by epic, target completion and carry-over from the previous sprint, a burndown, a dated scope timeline (added, descoped, completed) with its commentary and notes for the retro - as Markdown with SVG charts, built from the Jira REST API. Use when the user asks for a sprint report, summary or review, or "how did the sprint go" / "how is the sprint going", for a project, board or sprint.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/prepare_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/read_description.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/finish_report.py *)
---

# Sprint Report

Writes a short, exec-ready report of one Jira sprint, closed or still running. Scripts generate the whole report: figures, tables, charts, the timeline and its commentary. You write only the parts the report marks [AI Gen.], in `content.json` (step 2).

The report's files go to the `jira-sprint-reports` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

A report folder holds only these files, and `finish_report.py` fails on any other; anything else you need goes in your own scratch folder.

```text
jira-sprint-reports/
└── PROJ_Sprint_3_26-10-05/
    ├── _raw/                      prepare_report.py writes (the fetched Jira and GitHub data)
    ├── data.json                  prepare_report.py writes
    ├── brief.json                 prepare_report.py writes
    ├── content.json               you write (step 2)
    ├── outcome-tickets.svg        finish_report.py writes
    ├── outcome-pts.svg            finish_report.py writes
    ├── burndown.svg               finish_report.py writes
    └── PROJ_Sprint_3_Sprint_Report.md   finish_report.py writes
```

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill needs the `jira-api` source. If `sources.workflow.jira-api.enabled` isn't `true`, stop and tell the user to enable it, showing its `setup` and the config `path`. The scripts read its settings themselves; never read, pass or show them.

The `github-cli` source is optional: it fetches pull request data into the raw files, not used by the report yet. Without it, the report is the same; don't stop or ask to enable it.

## 1. Prepare

Call the scripts by exactly these paths, so they run without a permission prompt. A script's `--help` gives its commands and arguments.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/prepare_report.py <selector>
```

| The user names            | Selector                                                                                                                                             |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| a sprint id               | `--sprint-id 123` (add `--board 42` to read that board's sprint report)                                                                              |
| a project key             | `--project PROJ` (the last closed sprint)                                                                                                            |
| a project, current sprint | `--project PROJ --active`                                                                                                                            |
| a board id                | `--board 42` (add `--active` as needed)                                                                                                              |
| a sprint name             | `--sprint-name "PROJ Sprint 3"`: its first word is tried as the project key; if the name doesn't start with it, add `--project PROJ` or `--board 42` |

If the user names no sprint, project or board, ask; don't guess. If they name only a sprint, run it alone first, and ask for the project or board only when the script says it couldn't find the sprint. If the script fails, report its message and follow any fix it gives; when it asks for another board, keep the sprint by passing its `--sprint-id` with the `--board`.

Read the `brief`: the sprint and its goal, the verdicts you can choose from, each epic's tickets with their commentary `group`, `carried_in` (still in the previous sprint when it closed), `scope` (`original` is the commitment, `extra` was added later), latest `points`, `status`, `flagged`, description and, for blocker candidates, their comments, `report_facts`, the report's own figures in its exact wording, and `ticket_events`: each listed ticket's status changes.

A description comes as its first chunk, with `description_chunks` when there are more; read another chunk only when it could change a sentence, with `python3 ${CLAUDE_SKILL_DIR}/scripts/read_description.py --report-dir <report_dir> --key KEY --chunk N`.

## 2. Write content.json

Write it through the shared writer, with the `content_path` from step 1, and the same way for every revision; never with your own file tools. Its `--help` shows how to change part of it later. The first write, which shows the file's shape:

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

Work out the goal themes first (they feed three fields), and write the verdict last.

**Goal themes.** A theme is usually the text before a goal line's colon ("Search" in "Search: let staff find past orders"). For goal assessment, use the brief's `goal_tickets`: every original commitment ticket, with its `epic_key`, `epic_name`, `summary`, `points` and `outcome` (`completed`, `not_completed` or `removed`, meaning descoped). It includes work already Done at the start and non-delivery completions, so the goal's commitment is complete; use only the tickets under `epics` for epic commentary and achievements. A theme's tickets are those of the epic whose name contains the theme's word, plus any ticket whose summary names it, in any epic. If a theme, or part of one, matches nothing or the match is doubtful, make the best reading and say so in step 4.

**`epic_commentary`**: for every epic in the brief, one sentence per `group` it has tickets in. Say what changed for users or the system ("Staff can now sign in with their work account"), using the epic's description for context and each ticket's summary and description. Merge small items. At most 60 words in total per epic. Describe a ticket with no description from its summary alone; if a whole group has only bare summaries, add that "the tickets carry no detail".

**`key_achievements`**: one paragraph of at most 100 words on what the sprint achieved, a step above the epic commentary: the `completed` tickets, by goal theme in the goal's order, then the other epics in the brief's order.

**`blockers_risks`**: one paragraph of at most 100 words on the commitment still open: tickets with `scope` `original` in the `in_review` and `not_completed` groups. Group them by goal theme, then by epic, and say what the open work holds back. Give a reason only where a comment states one ("under discussion with Security"), and say when a ticket is flagged. If nothing from the commitment is open, say so.

**`retro_notes`**: 1 to 5 notes for the team's retro, each a fact followed by a question ending with "?". Look across `report_facts` and the brief, including `carried_in` tickets that are still open, for what most departed from the plan and what the team can learn from it: patterns between epics, the timeline commentary and the goal, not only the largest figure. Quote figures word for word from `report_facts`, and name tickets as `KEY (N pts)` with the brief's `points`; don't derive new figures. Frame causes as questions, never as findings the data can't show.

**`goal_verdict`**: one of the brief's `goal_verdicts`, word for word; if it offers only one, use it. A theme is met when none of its commitment tickets is open at the end (the `not_completed` outcome in `goal_tickets`, including work in review); extra work doesn't decide it, and descoped work doesn't count against it. Closed sprint: "Fully met" if every theme is met, "Not met" if none is, otherwise "Partially met". Running sprint, when the brief offers it: "At risk" if any theme has more than half its commitment pts open, otherwise "On track". If part of a theme maps to no ticket, judge by the tickets that do.

Rules for all of it. `finish_report.py` rejects text that breaks the wording and format rules, naming the field; it can't check the content rules, so you are the only guard for them:

- No ticket keys except in the retro notes, and no figures except quoted ones in the retro notes: the generated parts show them.
- Only what the tickets, descriptions and comments say. Never carry customer data from descriptions (names, contact details, account IDs, financial details), and never name colleagues: name the team ("with Security").
- A work item is a ticket; it is completed, never closed. Write pts, never points; numbers as digits, never "one" to "twenty"; dates as `DD/MM/YYYY`.

## 3. Finish

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/finish_report.py --report-dir <report_dir>
```

It draws the charts, writes the report and checks it, printing only what failed. For content failures, fix `content.json` and run it again until it passes. For data, model or chart failures, report the failed checks to the user; changing prose cannot repair them. Never edit the report by hand, and never give the user a report that fails.

## 4. Tell the user

Say that the report is ready, with a Markdown link to its full path, which the script prints. Don't recap anything the report already shows. Add only what it doesn't: a doubt about your own judgment, such as a goal theme that maps to no ticket, and, if step 1's `temporary` is `true`, that the folder is temporary and setting `output.root` in the config keeps reports.
