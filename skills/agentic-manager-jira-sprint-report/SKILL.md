---
name: agentic-manager-jira-sprint-report
description: Writes a short, exec-ready report of one Jira sprint, closed or still running - goal outcome, carry-over from the previous sprint, key achievements, blockers and risks, a dated scope timeline (added, descoped, completed) with its commentary, a burndown, delivery by epic and notes for the retro - as Markdown with SVG charts, built from the Jira REST API. Use when the user asks for a sprint report, summary or review, or "how did the sprint go" / "how is the sprint going", for a project, board or sprint.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_sprint.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/build_sprint_data.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_charts.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py *)
---

# Sprint Report

Writes a short, exec-ready report of one Jira sprint. Scripts do all fetching, classification, arithmetic, charts, formatting and checking; don't re-derive figures by hand. Your job is what needs judgment: the goal verdict, what each epic delivered in scope terms, the achievements, the blockers and risks, and the retro notes.

Closed and active sprints are equally supported. A report on a sprint in progress has the same shape; only the tense and a few labels change.

The report's files are written to the `jira-sprint-reports` folder of the output root the user set in the config (`output.root`), or to a temporary folder if none is set. The scripts choose the folder themselves; don't pass one.

## Prerequisite

Run `agentic-manager-utils-check-config`. If it fails, stop here.

This skill needs the `jira-api` source: it uses Jira endpoints (sprint reports, changelogs) that other channels don't offer. If `sources.workflow.jira-api.enabled` isn't `true`, stop and tell the user to enable it, showing its `setup` and the config `path`. The scripts read its `base-url`, `email` and `api-token` from the config themselves; never read, pass or show them.

## Vocabulary and formatting

Generated text follows these rules, the text you write included; `check_report.py` fails a report that breaks one. Jira’s goal, sprint names and epic names are copied source text: preserve their wording and punctuation, with only presentation escaping, line breaks and Jira links added. Do not apply generated-text vocabulary, number or punctuation restrictions to those source fields.

- **A work item is a ticket**: stories, spikes and bugs alike. Never "story", "stories", "issue" or "issues", in any sense ("problem" or "question" instead).
- **One label per idea**: **Commitment** (the work in the sprint at its start), **Extra** (added after it), **Descoped**, and **Not completed** for a closed sprint or **Open** for one still running. Capitalised in headings, labels and tags, lower case in running text. Tickets are **completed**, never "closed". The word "closed" appears only in the timeline's "(sprint closed)" label, which the generator writes: for the sprint, write "at the close" or "when the sprint ended".
- **An amount of work**: `N tickets (N pts)`, such as "7 tickets (7 pts)". Points are always "pts" ("1 pt"), never "points" or "story points".
- **Done out of total**: `N/M tickets (N/M pts)`, such as "11/22 tickets (34/74 pts)". Never a bare ratio: any `N/M` must be followed by "tickets" or "pts".
- **Only tickets or only points**: `N tickets (X% of …)` or `N pts (X% of …)`, such as "6 tickets (27% of commitment)". With its share, an amount reads `N tickets | X% of commitment (N pts | Y%)`. Inside the chart bars, for space only: `3 (50%)`.
- **Word limits** count words separated by spaces, in your text only (the generator's labels don't count): "JavaScript" and "per-market" are 1 word each.
- **Percentages** are whole numbers, "<1%" for a share above zero that would round to 0%. **Numbers** are always digits: the words "one" to "twenty" fail the check in any sense, so rephrase ("in a single view", not "in one view").
- **One ticket**: `KEY (N pts)`, with its latest estimate, or `KEY (– pts)` with none, such as "PROJ-14 (2 pts) was reopened". **A list of tickets**: the amount, then the keys in brackets, sorted: "3 tickets (5 pts) were descoped (PROJ-11, PROJ-12, PROJ-13)". A re-estimate reads "Re-estimated: 5 → 3 pts" as a timeline tag; in running text the change replaces the points: "PROJ-15 (5 → 3 pts) was re-estimated", "2 tickets (5 → 8 pts) were re-estimated (PROJ-15, PROJ-16)".
- **An epic**: `KEY: Name`, or "(no epic)".
- **Bold** only for a label that introduces a value, such as "Open:"; never for a value.
- **Dates**: `DD/MM/YYYY`.

The script-generated timeline commentary is historical: “already Done at the start” uses the entry estimate; other references use the estimate at the end of the membership spell being described (at removal or the report cutoff). Re-estimates show that spell’s first old estimate and final estimate. The checker validates these fixed phrases against the corresponding spell. AI-written sections continue to use the ticket’s latest estimate at the report cutoff or its last removal.

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

The script reads the API account's named timezone from Jira's current-user profile and saves it in the fetch metadata. Every report date and daily boundary uses that timezone, including daylight-saving changes. If it is missing or unavailable, follow the script's error and fetch again. Older raw data without it must also be fetched again.

The script prints one line of JSON with `report_dir`, `label` and `temporary`. The report folder is `<label>_<YY-MM-DD>` in that `jira-sprint-reports` folder (`<temp>/agentic-manager/jira-sprint-reports` when no output root is set, and `temporary` is then `true`). Every run is a full regeneration: it deletes any earlier report of the same sprint there. Never reuse files from an earlier run.

### 2. Compute

```bash
python3 <scripts>/build_sprint_data.py --report-dir <report_dir>
```

The snapshot date is derived from the saved fetch timestamp in the reporting timezone. No date argument is needed.

It cross-checks the scope and the completed issues against Jira's own sprint report. On a discrepancy it writes nothing. Usually the sprint changed during the fetch, so run step 1 again. If Jira's sprint report is empty, the sprint's origin board doesn't serve it: fetch again with `--board`, using another scrum board of the project.

Jira's sprint report shows today's membership, so it can't verify an issue that was moved into or out of this sprint after the moment the report describes (see the first bullet below). Such issues are left out of the comparison and named in `membership_cross_check_excluded_keys` and in the generated report.

What to know before writing prose about `data.json` (the script's docstring has the full method):

- **One model for the whole report.** A spell is one continuous stretch a ticket spent in the sprint: a ticket that leaves and comes back has two. `spells` holds every spell of every ticket, each with its dated `events`, and every figure in the report is built from them. The history (the timeline table and the burndown) shows every spell's events. The final situation (the charts, the header, the epic table and the commentary under the timeline) counts each spell by where it ended. Write prose from `spells`, `outcome_breakdown_*` and `epics`, never from the raw files. The check replays the events and fails the report if any part disagrees.
- **Spells.** The original commitment is the spell of every ticket in the sprint at its start instant (`startDate` as Jira records it, even if someone edited it), Done or not: a ticket already Done then is committed work completed from the start, and if it is reopened its points move back to not completed. Every time a ticket leaves the sprint its spell ends, descoped, at its estimate then; every time it joins after the start, including when it comes back, a new spell of extra work begins, at its estimate and state then. So a ticket that leaves and comes back, even the same day, counts as original Descoped and then as extra work. An extra spell that ends with the ticket leaving was never part of the commitment: the history shows it, the final situation doesn't count it (`counted` false). Tickets that joined and left before the start are in no part of the report (`left_before_start_keys`).
- **Events.** Each spell's `events` are, in time order: `committed` (at the start) or `joined` (after it), then `completed`, `reopened` and `reestimated` (with `fromPoints`), and `removed` when the ticket left. Each event carries the estimate and the Done state right after it, and its date in the reporting timezone.
- **Outcome and estimate.** A spell's `outcome` is its state after its last event: `completed` or `not_completed` if the ticket is in the sprint at the end, `removed` (shown as Descoped) if not. Its `points` are its latest estimate: at the end, or when the ticket left. The timeline and the burndown use each event's own estimate.
- **Every figure is as it was at the time, never as Jira shows it today.** The end is the moment the sprint closed (for an active sprint, the fetch); events, sprint moves and field changes after it are ignored, and each ticket's status, resolution, flag, priority and epic are as at the end or at its removal. Running the report again later gives the same figures. Comments are fetched up to the same moment. Descriptions are the one exception: Jira keeps no usable history of them, so they read as at the fetch.
- **Carried over (`carriedIn`) is original work that was in the previous sprint at the instant it closed.** The previous sprint (`previous_sprint`) is the closed sprint, of those the board lists, that started last before this one. Having been in it at some point isn't enough: work removed from it before it closed wasn't carried over, and work that joined this sprint after its start is extra, not carry-over.
- **Completed means in Jira's Done category**, including duplicates and Won't Do, as in Jira's sprint report. Work finished after the close isn't completed. `non_delivery_closures` names the duplicates and Won't Dos that ended completed (one that was descoped counts as descoped, not here); mention them as an annotation, never subtract them from the headline.
- **Each epic in `epics` carries its scope** for its commentary: the epic's `description`, and its counted tickets sorted into `scope_groups`, each with its `summary` and `description`: `completed`, `in_review` (not completed, in a status whose name contains "review" at the end), `not_completed` and `descoped`. Work the sprint didn't do is in `left_out` instead, with its `reason`: resolved as Duplicate or Won't Do (`non_delivery`), or already Done when its spell began and never reopened (`done_at_start`), whether it then stayed or was descoped: the work happened before the sprint. The figures still count it, as completed or descoped; the AI-written text doesn't describe it as work of this sprint. So an epic's table figures can show a descoped ticket while its commentary has no Descoped sentence.
- `blocker_candidate_keys` lists flagged tickets, blocked-type statuses and high-priority open tickets still in the sprint. Their comments are in `_raw/comments/<KEY>.json`.

### 3. Write content.json

Run `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py --name jira-sprint-reports` to get the output `folder`. Write `<report_dir>/content.json` through the shared writer, using the final folder name from `report_dir` as `<report-folder>` (relative to that `folder`):

```bash
python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py --name jira-sprint-reports --path '<report-folder>/content.json' <<'END_OF_FILE'
<the complete JSON content below, filled in>
END_OF_FILE
```

For revisions, run the same command again with the complete updated JSON on standard input (a heredoc, or piped from a scratch file in your scratch or temp folder that you delete afterwards), never your own file tools. Use bare Jira keys (`PROJ-12`); the generator links them. `epic_commentary`, `key_achievements` and `blockers_risks` name none, and state no figures: the generator shows them. Only `retro_notes` quote figures, as below.

```json
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
  "key_achievements": "One paragraph on the scope completed across the epics.",
  "blockers_risks": "One paragraph on the commitment still open, and why where a comment says.",
  "retro_notes": [
    "4 tickets (8 pts) were descoped: was the commitment too large?"
  ]
}
```

- **`goal_verdict`**: read `sprint_goal`, find its themes and check which tickets cover each (by epic, and by each ticket's `summary` and `labels`; in `spells` a ticket's epic is `parentKey` and `parentSummary`); ask the user to confirm a mapping that isn't obvious. A theme is usually the text before a goal line's colon ("Search" in "Search: let staff find past orders"). A theme names an epic, and a ticket's summary names a theme, when the theme's word appears in it as a whole word, ignoring case and plural "s" ("Search" names "Acme: Search Service - Pilot" and "Add filters to search / billing"; "Reports" doesn't name "reporting"). A theme's tickets are those in the epic it names, plus any ticket whose summary names the theme, whichever epic it is in; a ticket that names 2 themes counts for both. Write `key_achievements` and `blockers_risks` first, then judge each theme by its commitment tickets (extra work doesn't decide it, and descoped work doesn't count against it): met if none of them is still open at the end (not completed or in review), not met otherwise. If a theme's parts don't visibly map to tickets (no ticket names them), judge it by the tickets that do and tell the user about the doubt when you hand over the report. Then combine: closed, "Fully met" if every theme is met, "Not met" if none is, otherwise "Partially met"; active, "Too early to tell" before the sprint's halfway day, then "At risk" if any theme has more than half its commitment pts still open, otherwise "On track". Exactly one of these, word for word; `make_report.py` rejects anything else. Closed: "Fully met", "Partially met" or "Not met". Active: "On track", "At risk" or "Too early to tell". No goal set: "No goal set in Jira for this sprint"; don't invent one.
- **`epic_commentary`**: what each epic actually delivered, in scope terms, for a reader who wants to know what the product can do now. For every entry in `data.json`'s `epics`, keyed by its `key` (tickets without an epic are under `__no_epic__`), write one sentence for each of its `scope_groups` that has tickets, and none for the empty ones; the generator adds the labels (Completed, In review, Not completed or Open, Descoped). An epic with no tickets in any group gets `{}`, and the table shows "–".
  - Read the epic's `description` for context, then each group's tickets' summaries and descriptions, and say what changed for users or the system: "Staff can now sign in with their work account", not "PROJ-12 and PROJ-14 were completed". Merge small items ("small fixes to the export").
  - Describe only the tickets in that group. Leave out the `left_out` tickets, and don't mention estimates, counts or dates: the table's columns show the figures.
  - No ticket keys. At most 60 words per epic, one sentence per group. Only what the tickets say; don't guess at reasons or impact they don't state.
  - A ticket with no description is described from its summary alone, plainly, without expanding on it, alongside the tickets that have one. If a whole group has nothing but bare summaries, name the work by its summaries and add that the tickets carry no detail: "Work on search deployments, the release process and the dashboard was completed; the tickets carry no detail."
  - Descriptions can hold customer data (names, contact details, account IDs, financial details). Never carry any of it into the text.
  - Don't name colleagues in any AI-written part: name the team instead ("with Security").
- There is no field for why scope changed: the timeline's commentary is generated from the data alone, and `make_report.py` rejects a `scope_notes` field. Don't add reasons the data can't show anywhere else in the report either.
- **`key_achievements`**: one paragraph of at most 80 words summarising what the sprint achieved, from the epics' `completed` groups: the outcomes, a step above the epic commentary's detail. Plain sentences, no labels. Describe tickets without descriptions as in `epic_commentary`. Lead with the goal's themes, in the goal's order, each with its tickets as defined under `goal_verdict` (a ticket of 2 themes under the first, once), then other epics by completed pts, commitment and extra together. Leave out the `left_out` tickets. No ticket keys.
- **`blockers_risks`**: one paragraph of at most 80 words on the commitment still open at the end: the tickets with `scope` `original` in the epics' `in_review` and `not_completed` groups, not descoped or extra work. Group them by goal theme first, in the goal's order, then the rest by epic, and say what is at stake: the goal theme or epic the open work holds back, not an impact the tickets don't state. Give a reason only where a comment states it, or what it waits on if a comment says so ("under discussion with Security"); otherwise say what is open, not why. Comments exist for `blocker_candidate_keys`, in `_raw/comments/<KEY>.json`. Say a ticket is flagged when its `flagged` field in `spells` is set. If nothing from the commitment is open, say so rather than inventing a risk. No ticket keys.
- **`retro_notes`**: write them last, after a first run of steps 4 and 5, so you can read the generated report and quote it: for that first run, put a single placeholder note (`["To be written?"]`), then rewrite content.json with the real notes and run step 5 again. The check fails while the placeholder is still there. 1 to 5 notes for the team's retro, each a fact the report already shows (in the header, the timeline and its commentary, the epic table, the achievements or the risks) followed by a question for the team, ending with "?": "4 tickets (8 pts) were descoped: was the commitment too large?". Pick what most departed from the plan. Quote amounts and ticket references word for word from elsewhere in the report, choosing ticket references with their latest estimate rather than historical estimates from the timeline commentary, and take other facts only from the report's own text (the header, the timeline commentary, the epic table, including an epic's figures with its `KEY: Name`, as the report renders it; a verb around a quoted amount is fine, as in "PROJ-10: Sign-in completed 3/7 tickets (9/30 pts) of its commitment"): don't derive new figures, such as one epic's open pts. Tickets keep the report's forms (`KEY (N pts)`, `N tickets (N pts) (KEY, KEY)`). Don't suggest causes or actions the data can't show.

Keep the report short and exec-ready. All text goes into a document the user shares: no em dashes in generated prose (the generator replaces them with commas in `content.json`). Copied Jira fields keep their punctuation.

Everything you write here is the only text in the report not generated from the data, so the generator marks each part "[AI Generated]" on its heading or label: the Goal outcome row, the epic table's Commentary column, Key Achievements, Blockers & Risks and Notes for Sprint Retro. Don't write the label yourself. Keep these parts as accurate as the tickets, descriptions and comments allow.

### 4. Charts

```bash
python3 <scripts>/make_charts.py --report-dir <report_dir>
```

Writes two outcome charts (tickets and pts) and a burndown. Each outcome chart shows the final situation of the counted spells in three rows on one scale, split into Completed, Not completed (Open while the sprint runs) and Descoped: work carried over from the previous sprint, new commitment, and extra scope. A bracket groups the first two as the original commitment. The longest bar spans the full width and the others are sized against it. The report's header table also states the carry-over. Add `--print-series` to print the burndown's daily numbers instead, to compare with the timeline table.

When writing about the burndown:

- It replays the same events as the timeline: each day, the open points of every spell then in the sprint, counted or not, at that day's estimates, in the saved reporting timezone. The closing day stops at the exact closing instant, and an active snapshot's current day at the fetch instant.
- The first point is the whole original commitment at the start, at the estimates it had then, including work already Done. The start day's end-of-day reading follows at the same x, so the vertical movement shows the work already Done at the start plus that day's closures, removals, reopening and estimate changes. It isn't a delivery pace. The ideal line starts from the same first point.
- Reopening adds points back on its day, re-estimation changes them from its day, and a removal takes them off (it isn't delivery: the charts show it as Descoped).
- For a closed sprint the chart runs to the close date, and its last value is what was left open: work finished after the close still counts as open.
- For an active sprint past its end date, the chart stops at the end date, not today.

### 5. Report

```bash
python3 <scripts>/make_report.py --report-dir <report_dir>
```

It owns every table, figure, date (`DD/MM/YYYY`), link and generated note. Never edit the Markdown by hand: change `content.json` and run it again.

The header table, above the charts, is fixed: a `| Field | Detail |` table with exactly these rows, in this order, and nothing else. The check fails on any other row, order or format.

| Field                         | Detail                                                                                                                                                                                                                                                                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Dates`                       | `DD/MM/YYYY–DD/MM/YYYY` (start–end), plus ` (completed DD/MM/YYYY)` if the sprint closed on another day than its end                                                                                                                                                                                                                                               |
| `Goal`                        | Jira's sprint goal, one line per `<br>`, Jira keys linked; or `*No goal was set in Jira for this sprint*`                                                                                                                                                                                                                                                          |
| `Goal outcome [AI Generated]` | `goal_verdict`, one of the values in step 3                                                                                                                                                                                                                                                                                                                        |
| `Sprint target completion`    | `X%, N/M tickets (N/M pts) completed`: the whole percentage of the commitment's tickets completed, then the ratios: the commitment's tickets completed, of all of them (a ticket that left the sprint counts as not completed, even if it came back; one Done at the start, as completed unless it was reopened); ` so far` after `completed` for an active sprint |
| `Carried over from <sprint>`  | `N tickets \| X% of commitment (N pts \| Y%); N tickets (N pts) completed`, with ` so far` added for an active sprint                                                                                                                                                                                                                                              |
| `Carried over`                | instead of the row above, when the board has no earlier closed sprint: `None: no earlier sprint on this board`                                                                                                                                                                                                                                                     |

The timeline table is a real timeline, in 75% type, with four columns:

| Column       | Content                                                                                                                                                                                                           |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Date`       | the day, with `(sprint start)`, `(today)` or `(sprint closed)`; it spans the day's rows                                                                                                                           |
| `Ticket`     | one row per ticket with events that day: its link and its estimate at the end of the day, such as `PROJ-12 (3 pts)`                                                                                               |
| `Events`     | the ticket's events that day as coloured tags, in time order                                                                                                                                                      |
| `End of day` | on the first day, `Commitment: N tickets (N pts)`; on every day of the burndown, `Open: N tickets (N pts) of the commitment` and `N tickets (N pts) with extra`, the burndown's readings; it spans the day's rows |

The tags are `Added`, `Already done` (next to `Added`, for work Done when it entered), `Completed`, `Reopened`, `Descoped` and `Re-estimated: old → new pts` (`–` for no estimate). A ticket leaving the sprint is `Descoped` and coming back is `Added`, every time; work added after the first day is extra. Every spell is shown, including extra spells that ended descoped, which the final situation doesn't count. A day with no events has `–`. There is no total row: the paragraph under the table gives the state at the end.

Right under the timeline, its commentary: at most 100 words of plain text, generated from the spells, on everything that departed from the ideal sprint (all of it committed on the first day, completed steadily, nothing left at the end). In this order, leaving out what didn't happen: the commitment, with what was already Done at the start and what was descoped; the extra work, with what had no estimate and what was added and descoped again; reopened, re-estimated, and left-and-came-back tickets; then what is open, or was not completed at the close, and how much of it is from the commitment. It names no dates. A kind of departure names its tickets when it has up to 3, else counts them, and if the text is still over 100 words, all are counted. Two caveats follow whenever they apply, and are never cut: tickets resolved as Duplicate or Won't Do, and tickets whose membership couldn't be checked against Jira.

### 6. Check

```bash
python3 <scripts>/check_report.py --report-dir <report_dir>
```

It replays every spell's events and verifies that the charts' figures, the burndown, each timeline day (its tickets, estimates, tags and end-of-day figures), the header, the paragraph and the epic table all match them, that each epic's commentary has a sentence for exactly its groups with tickets, within 60 words and with no ticket keys, that Key Achievements and Blockers & Risks are one paragraph each within 80 words and with no ticket keys, that the retro has 1 to 5 notes each ending with a question, that every AI-written part is marked "[AI Generated]", then the cell formats, dates, em dashes and links. If it fails, fix `content.json` and rerun steps 5 and 6. Don't hand over a report that fails.

### 7. Hand over

Always give the user a link they can click to open the report: a Markdown link to its full absolute path, such as `[<label>_Sprint_Report.md](<report_dir>/<label>_Sprint_Report.md)`. Add a few lines on the headline (goal verdict, delivered vs committed, main risk), and, if `temporary` is `true`, say the folder is temporary: offer to copy the report and its three `.svg` charts somewhere they choose, and mention that setting `output.root` in the config keeps reports. Don't paste the whole report into the chat unless asked.
