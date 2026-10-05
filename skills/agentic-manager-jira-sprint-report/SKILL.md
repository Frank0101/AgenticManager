---
name: agentic-manager-jira-sprint-report
description: Writes a short, exec-ready report of one Jira sprint, closed or still running - goal outcome, key achievements, blockers and risks, a dated scope timeline (added, removed, completed), a burndown, delivery by epic and notes for the retro - as Markdown with SVG charts, built from the Jira REST API. Use when the user asks for a sprint report, summary or review, or "how did the sprint go" / "how is the sprint going", for a project, board or sprint.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_sprint.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/build_sprint_data.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_charts.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py *)
---

# Sprint Report

Writes a short, exec-ready report of one Jira sprint. Scripts do all fetching, classification, arithmetic, charts, formatting and checking; don't re-derive figures by hand. Your job is what needs judgment: the goal verdict, a sentence per epic, the blockers story, achievements and retro prompts.

Closed and active sprints are equally supported. A report on a sprint in progress has the same shape; only the tense and a few labels change.

The report's files are written to the `jira-sprint-reports` folder of the output root the user set in the config (`output.root`), or to a temporary folder if none is set. The scripts choose the folder themselves; don't pass one.

## Prerequisite

Run `agentic-manager-utils-check-config`. If it fails, stop here.

This skill needs the `jira-api` source: it uses Jira endpoints (sprint reports, changelogs) that other channels don't offer. If `sources.workflow.jira-api.enabled` isn't `true`, stop and tell the user to enable it, showing its `setup` and the config `path`. The scripts read its `base-url`, `email` and `api-token` from the config themselves; never read, pass or show them.

## Steps

`<scripts>` is this skill's `scripts` folder, `${CLAUDE_SKILL_DIR}/scripts`. Call the scripts by exactly that path: in Claude Code, the skill pre-approves them there, so they run without a permission prompt. Every script prints what's wrong and exits non-zero on failure; stop and report it rather than working around it.

```text
fetch_sprint.py       → <report_dir>/_raw/        Jira REST, fresh every run
build_sprint_data.py  → data.json                 computation only, no network
  you write           → content.json              judgment text
make_charts.py        → 3 SVG charts
make_report.py        → <label>_Sprint_Report.md
check_report.py       → must pass
```

### 1. Fetch

```bash
python3 <scripts>/fetch_sprint.py <selector>
```

| The user names            | Selector                                  | Sprint                   |
| ------------------------- | ----------------------------------------- | ------------------------ |
| a sprint id               | `--sprint-id 123`                         | that sprint              |
| a project key             | `--project PROJ`                          | the most recently closed |
| a project, current sprint | `--project PROJ --active`                 | the one in progress      |
| a board id                | `--board 42` (add `--active` as needed)   | same, on that board      |
| a sprint name             | `--sprint-name "Sprint 3" --project PROJ` | that sprint              |

- If the user asks how the current sprint is going, pass `--active`.
- A bare number could be a sprint or a board: try `--sprint-id` first, and if Jira returns 404, retry as `--board`.
- If the user doesn't say which project, board or sprint, ask. Don't guess.
- Only active and closed sprints can be reported.

The script prints one line of JSON with `report_dir`, `label` and `temporary`. The report folder is `<label>_<YY-MM-DD>` in that `jira-sprint-reports` folder (`<temp>/agentic-manager/jira-sprint-reports` when no output root is set, and `temporary` is then `true`). Every run is a full regeneration: it deletes any earlier report of the same sprint there. Never reuse files from an earlier run.

### 2. Compute

```bash
python3 <scripts>/build_sprint_data.py --report-dir <report_dir> --today <YYYY-MM-DD>
```

It cross-checks the scope and the completed issues against Jira's own sprint report. On a discrepancy it writes nothing. Usually the sprint changed during the fetch, so run step 1 again. If Jira's sprint report is empty, the sprint's origin board doesn't serve it: fetch again with `--board`, using another scrum board of the project.

Jira's sprint report shows today's membership, so it can't verify an issue that was moved into or out of this sprint after the moment the report describes (see the first bullet below). Such issues are left out of the comparison and named in `membership_cross_check_excluded_keys` and in the generated report.

What to know before writing prose about `data.json` (the script's docstring has the full method):

- **Every figure is as it was at the time, never as Jira shows it today.** Each issue's status, resolution, points, flag, priority and epic are rebuilt from its changelog: issues in the sprint as at the moment it closed (for an active sprint, the fetch), removed issues as at their removal. Running the report again later gives the same figures. Comments are fetched up to the same moment.
- **Sprint moves after that moment are ignored.** Timeline quantities use each issue's estimate at that moment (or at its removal). The burndown instead uses each day's status and estimate, so reopening and re-estimation can change its line without a timeline scope movement.
- **Original commitment is what was in the sprint at its start** (`startDate` as Jira records it, even if someone edited it), whenever it was added. Anything that joined after that moment is extra (`addedMidSprint`), even on the same day. Issues that joined and left before the start aren't part of the sprint (`removed_before_start_keys`).
- **Completed matches Jira's sprint report.** Everything in Jira's Done category when the sprint closed counts, including duplicates and Won't Do. Work finished after the close is carried over. `non_delivery_closures` names the duplicates and Won't Dos; mention them as an annotation, never subtract them from the headline.
- **Removals have three meanings; never merge them into one "removed" figure.** In `removed_summary`: `descoped_incomplete` is real descope; `already_done_on_arrival` is work already Done when it entered the sprint, later tidied out; `completed_before_removal` is work delivered here and then removed.
- **Original work that was Done at the start and is reopened while in the sprint isn't initial commitment.** It counts as extra scope (`addedMidSprint`) from the day it was reopened: delivery if it is Done again, carried over if not, a removal if it leaves. Its points are on the burndown's committed + extra line from that day.
- **Issues already Done when they entered the sprint** (at the start for original work, on joining for extra work) and not reopened through that moment are in `already_done_on_arrival`. They were never work in this sprint, so they're left out of the burndown's baseline, as in Jira's own burndown. One still in the sprint is credited as completed on the day it entered, as Jira's sprint report counts it, which is why the Completed column total can exceed the delivered figure: quote delivery as the real figure and name the already-done points separately. One later removed is only a removal, never a completion.
- `blocker_candidate_keys` lists flagged issues, blocked-type statuses and high-priority open issues. Their comments are in `_raw/comments/<KEY>.json`.

### 3. Write content.json

Run `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py --name jira-sprint-reports` to get the output `folder`. Write `<report_dir>/content.json` through the shared writer, using the final folder name from `report_dir` as `<report-folder>` (relative to that `folder`):

```bash
python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py --name jira-sprint-reports --path '<report-folder>/content.json' <<'END_OF_FILE'
<the complete JSON content below, filled in>
END_OF_FILE
```

Use the same command for revisions, never your own file tools. Use bare Jira keys (`PROJ-12`); the generator links them. Don't repeat figures the generator produces.

```json
{
  "goal_verdict": "Partially met",
  "epic_commentary": { "PROJ-10": "One sentence on this epic's own numbers." },
  "scope_notes": ["Why later scope was added, one clause per addition."],
  "delivery_commentary": "One factual conclusion the epic table supports.",
  "key_achievements": ["One or two bullets."],
  "blockers_risks": ["One or two bullets."],
  "retro_notes": ["Zero to three questions worth asking in the retro."]
}
```

- **`goal_verdict`**: read `sprint_goal`, find its themes and check which issues cover each (epic, summary, labels); ask the user to confirm a mapping that isn't obvious. Closed: "Fully met", "Partially met" or "Not met". Active: "On track", "At risk" or "Too early to tell". No goal set: "No goal set in Jira for this sprint"; don't invent one.
- **`epic_commentary`**: one short sentence for every entry in `data.json`'s `epics`, keyed by its `key` (issues without an epic are under `__no_epic__`). Refer to that epic's own numbers. If it has removed issues, say which kind of removal (see step 2).
- **`scope_notes`**: why scope was added later, where the reason is known or obvious. The generator already states the in-scope split, removals, already-done work and each leave-and-return; don't restate them, or walk through the arithmetic.
- **`delivery_commentary`**: where delivery actually concentrated, not a restatement of rows.
- **`key_achievements`**: highlights tied to a goal theme (or, with no goal, to the epic that progressed), each naming the 1-3 issues that best show it.
- **`blockers_risks`**: from `blocker_candidate_keys` and their comments: what blocked it, how it resolved or that it didn't, and the impact. Also look in `issues` for an old `created` date still in a not-Done status: a stalled issue nobody flagged. Comments exist only for blocker candidates, so judge stalled issues by age and status alone. If nothing rose to this level, say so rather than inventing a risk.
- **`retro_notes`**: optional extra questions backed by evidence, framed as what's worth asking, not as decisions. The generator always adds a full sprint-health review (planning baseline, target completion, goal, scope added and removed, completion rates, board-data quality, unfinished work); don't repeat it.

Keep the report short and exec-ready. All text goes into a document the user shares: no em dashes (the generator replaces any with commas).

### 4. Charts

```bash
python3 <scripts>/make_charts.py --report-dir <report_dir>
```

Writes two outcome charts (stories and points: original vs extra, completed vs not) and a burndown. Add `--print-series` to print the burndown's daily numbers instead, to compare with the timeline table.

When writing about the burndown:

- The baseline is the commitment at the sprint start, less what was already Done then (as in Jira's burndown).
- Each daily reading uses membership, status and estimates at the end of that day in the site's offset. The closing day stops at the exact closing instant, and an active snapshot's current day at the fetch instant. Reopening adds outstanding work back on its actual day; re-estimation changes points from its actual day onward.
- The vertical movement on the start day reflects closures, removals, reopening and estimate changes that day. It isn't a delivery pace.
- For a closed sprint the chart runs to the close date, and its last value is what was carried over: work finished after the close still counts as open.
- For an active sprint past its end date, the chart stops at the end date, not today.

### 5. Report

```bash
python3 <scripts>/make_report.py --report-dir <report_dir>
```

It owns every table, figure, date (`DD/MM/YYYY`), link and generated note. Never edit the Markdown by hand: change `content.json` and run it again.

### 6. Check

```bash
python3 <scripts>/check_report.py --report-dir <report_dir>
```

It verifies the figures against `data.json`, that every table column sums to its total, the cell formats, dates, em dashes and links. If it fails, fix `content.json` and rerun steps 5 and 6. Don't hand over a report that fails.

### 7. Hand over

Always give the user a link they can click to open the report: a Markdown link to its full absolute path, such as `[<label>_Sprint_Report.md](<report_dir>/<label>_Sprint_Report.md)`. Add a few lines on the headline (goal verdict, delivered vs committed, main risk), and, if `temporary` is `true`, say the folder is temporary: offer to copy the report and its three `.svg` charts somewhere they choose, and mention that setting `output.root` in the config keeps reports. Don't paste the whole report into the chat unless asked.
