---
name: agentic-manager-perf-review-prep
disable-model-invocation: true
description: Helps a manager prepare a performance review of one person over a review period, from the evidence of their work in Jira, GitHub, the documentation, the team's messages and the manager's own notes. In development; not ready to use.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/extract_saved.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_jira_account.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/rules.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/read_notes.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/jira_ticket.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_work.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_notion.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/read_slack.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_prep.py *)
---

# Performance Review Prep

Helps a manager prepare a performance review of one person over a review period. The skill is in development.

The skill's files go to the `perf-review-preps` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

```text
perf-review-preps/
└── Jane-Doe_26-11-10/
    ├── _raw/             read_notes.py and read_slack.py write (each reader's answer, by source: a month's in
    │                     months/, the notes' pages in pages.json); fetch_work.py and set_notion.py write what
    │                     each source gave, with its searches, jira.json, github.json and notion.json
    ├── _charts/          make_report.py writes (the report's charts, one SVG each)
    ├── person.json       init_prep.py and set_identities.py write (the person, the period and who they are in each
    │                     source, as the manager confirmed)
    ├── orientation.json  set_summary.py writes (the manager's overall view of the person, summarised)
    ├── reviews.json      set_summary.py writes (the person's previous performance reviews, each summarised)
    ├── feedback.json     set_summary.py writes (the person's OKRs, 1:1 notes and recognition in the period, each
    │                     piece summarised)
    ├── notes.json        read_notes.py writes (what the manager's own notes say about the person, merged, with
    │                     their links)
    ├── slack.json        read_slack.py writes (what the person's Slack messages show, merged, with their links)
    ├── work.json         fetch_work.py or set_notion.py builds, once _raw holds every source (by source, the
    │                     person's Jira issues, pull requests and Notion pages in the period, each with its day,
    │                     and their facts: the counts, the issues created and resolved by type, the resolved
    │                     ones by epic, the main focus, the resolved issues' story points and the link to each
    │                     search)
    └── Jane-Doe_Review_Prep.md
                          make_report.py writes (the report for the manager, from the files above: for now, the
                          person's Jira figures and main focus)
```

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill needs the `jira-api`, `github-cli`, `notion-mcp`, `slack-mcp` and `logseq-fs` sources, and the `company.perf-review-ratings` and `company.values` settings. If a source isn't enabled or a setting isn't set, stop and tell the user how to fix it, showing its `setup` and the config `path`: the ratings are the company's performance review ratings, lowest first, and the values its values, each with what it means. The scripts read the config's settings themselves: never read the config file, or pass or show a setting, except what a script prints for you, such as the company's ratings.

## Writing to the manager

In every message to the manager, write the person's name as the manager gave it, `person` in `person.json`, never the name an account shows, or "they": never "he" or "she", nor any pronoun guessed from their name or anything else.

## 1. Agree what the prep is for

Call every script by exactly the path this skill shows, so it runs without a permission prompt; a script's `--help` gives its commands and arguments.

The prep needs, from the manager:

- **the person**, by their name;
- **the period**, such as the last 3, 6 or 12 months, or a first and last day.

Take what the manager gave when calling the skill, such as "for Jane Doe over the last 6 months", and ask, in one message, only for what is missing.

Turn the period into exact days with `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py`, for the last months or for days the manager named, which it checks. For any other wording, such as "this year" or "H1", work out the first and last day yourself and pass them. If the script refuses a period, tell the manager why and ask again.

Then look the person up in Jira with `python3 ${CLAUDE_SKILL_DIR}/scripts/find_jira_account.py --person <name>`. Every other source is searched from the Jira account, so the manager confirms it with the period:

- **Pick the account.** An account is the person when its name is theirs, in full or as a short form, such as Al for Alan. With several such accounts, propose the one you pick, such as the active one, and say briefly why. If none could be them, stop and tell the manager the person must be in Jira for the prep; if Jira hides the email of the one you pick, stop and tell them the prep needs it, as it finds the person in the other sources.
- **Ask the manager to confirm** the account, its name and email, and the period, as `period.py`'s `shown`, in one message: "I'll prepare Jane Doe's review (Jira: Jane Doe, jane.doe@acme.test) for 10/05/2026 to 10/11/2026. Is that right?" Don't go on until they confirm both.

Once they do, start the prep with `python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py`, for the person, the confirmed account's `accountId` and the period's days. It prints the prep folder's name, `prep`, which later steps pass as `<prep>`.

## 2. Find the person in each source

Who the person is in GitHub, Notion, Slack and the vault is the manager's to confirm, as their Jira account was: a wrong account would quietly bring in someone else's work. The prep needs the person in every source, as a review drawn from some of them would read as if they did nothing in the others: if a source has no one who could be them, or the manager says they aren't in one, stop and tell the manager which source, and that the prep needs the person in every one.

1. **Look them up.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py --prep <prep>` for GitHub and the vault. Search Notion and Slack yourself, through their MCPs' user search: Notion by the `email` it prints, the Jira account's, and only if that finds no one, by the person's name; Slack by the words of the person's name, each a keyword of its own, never in quotes, as its search doesn't match an email or a quoted name, and if that finds no one, by each word alone, picking the account that shows the Jira email.
2. **Pick the person in each source.** An account is the person when its email is the Jira account's, or its name is theirs, in full or as a short form, such as Al for Alan; GitHub's accounts are found by that email already. Several accounts you can't tell apart are a question for the manager. In the vault, pick every link about the person, their tag and the pages about them, such as `[[Jane]]` and `[[Jane Promotion]]`, and every alias their page declares, such as `[[JD]]`, and leave out one that only shares letters with their name, such as `[[Janet]]`.
3. **Ask the manager to confirm,** in one message: for each source, the account or links you picked and, briefly, why, and your questions where you couldn't pick. Don't list what you left out. For example:

   > Here's who I think Jane Doe is in each source:
   >
   > - GitHub: janedoe, whose commits use Jane's Jira email.
   > - Notion: Jane Doe, with the same email.
   > - Slack: two accounts, Jane Doe and Jane Doe (Contractor). Which one is Jane?
   > - Your notes: `[[Jane]]` (120 mentions, its own page) and `[[Jane Promotion]]` (8).
   >
   > Is that right?

   A reply that doesn't answer each question, such as a plain yes, confirms only what you found: ask the open questions again. Don't go on until every source is settled.

4. **Record it** with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py --prep <prep>`; its `--help` shows the input. Run it again with every source to record a correction.

## 3. Hear the manager's view

Ask the manager, in a message of its own, giving the period as step 1 showed it:

> What's your overall view of Jane Doe over 10/05/2026 to 10/11/2026? A few points or sentences are enough: what's going well or exceeding, what are improvement or stretch areas, including what you want to see from them next, any support or unblocking they need, and any context the review should take into account, such as a long absence or a change of role.

Record their answer as [Summaries](#summaries) says, with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py --prep <prep> --of orientation`.

## 4. Read the previous reviews

Ask the manager, in a message of its own:

> Do you have Jane Doe's previous performance reviews, with the colleagues' feedback gathered for them? Paste them, give me paths or links to them, such as PDFs exported from your HR tool, or sum up their main points. Say "none" if there aren't any.

Record their answer as [Summaries](#summaries) says, each review with its rating, as the company's ratings name it, or null when it gives none of them, with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py --prep <prep> --of reviews`.

## 5. Read the period's OKRs and feedback

Ask the manager, in a message of its own, giving the period as step 1 showed it:

> Do you have anything on Jane Doe from 10/05/2026 to 10/11/2026: their OKRs, the notes of your 1:1s, or kudos and recognition they received? Paste them, give me paths or links to them, or sum up their main points. Say "none" if there isn't any.

Record their answer as [Summaries](#summaries) says, with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py --prep <prep> --of feedback`.

## 6. Gather more feedback from the manager's notes and Slack

The manager's own notes on the person, in their vault, and the person's Slack messages are many, and most aren't feedback, so subagents read them, each source on its own: one task for each month of the period, and for the notes one for the person's pages, which give only context, each writing a synopsis of every note or conversation; then, for each source, one judges them all and merges what matters into a summary, so a behaviour seen in several months becomes one point with all its days. Each task holds its own instructions. You coordinate, and read none of the notes or messages yourself: a fresh subagent hasn't heard the manager's view, so what they say is read without it. Your one judgment is on what the merges left out in doubt, in 3. Say nothing to the manager while the subagents work, not even as each one finishes.

1. **Start.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/read_notes.py start --prep <prep>` and `python3 ${CLAUDE_SKILL_DIR}/scripts/read_slack.py start --prep <prep>`: each prints `tasks`, a line `Task <name>: <path>` for each of its tasks, and `merge`, its merge task's line. When there is nothing to read, a script records an empty summary and prints what `finished` would.
2. **Hand out the tasks.** Give each of both scripts' `tasks` to a fresh subagent, all at once, only its path, with: "Do the task in <path> exactly as written there, then reply in one line." Give a reading task a smaller model than your own, as it only reads and summarises, and a merge your own, as it judges. Once all of a source's tasks have replied, give its `merge` to one more fresh subagent the same way, and once that one has replied, run its script's `finished`. After a break, run `start` again: step 6 starts over.
3. **Finish** once both are finished: your one question is about what the merges left out in doubt, each `finished`'s `in_doubt`. List only those you think may belong in a summary, each with why, and ask whether to add them; when there are none, ask nothing. To add one, read its summary and submit it again, with the point added and its `finished`'s `in_doubt`, with its `correct` command. Then tell the manager, in one line, that what their notes say and what the person's Slack shows are recorded, with a Markdown link to each, the path its `finished` printed, and go on.

## 7. Gather the data points

The person's work in Jira, GitHub and Notion, in the period. Like step 6, it is read without the manager's view, and neither needs the other, so start it as soon as step 6's subagents are handed their tasks, without waiting for them. Say nothing to the manager about it while it runs, unless a script stops; step 6's message is sent as soon as its merges are done, without waiting for this step.

1. **Jira and GitHub.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_work.py --prep <prep>`: it fetches the issues and pull requests, with no judgment, into their raw files, and builds `work.json` once Notion's pages are recorded, in 2.
2. **Notion.** Find the pages the person created: one search per calendar week of the period, Monday to Sunday, the first and last clipped to it, all at once, with the Notion MCP's search, an empty `query` and only filters, as any query text silently drops pages, `created_by_user_ids` set to their Notion id, `created_date_range` set to the week, `page_size` 50 and `max_highlight_length` 0. A result's date is its last edit, not its creation, so each page is dated by the week it was found in. Pages the person edited aren't gathered: Notion knows only a page's last editor, so they would be undercounted.

   When a search returns 50 results, rows included, search its range again in shorter ranges, and record those instead; a single day that still returns 50 is recorded as full, as `set_notion.py`'s `--help` says. Record every search with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_notion.py --prep <prep>`, its results as the search returned them, unchanged: the script keeps the pages of their own, leaving out databases and their rows.

## 8. Write the report

Once step 7 is done, run `python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py --prep <prep>`: it writes the report, `<Person>_Review_Prep.md`, and its charts from `work.json`, with no judgment, and checks them. If its `problems` aren't empty, stop and tell the manager what they say.

## 9. Tell the manager

First check the prep with `python3 ${CLAUDE_SKILL_DIR}/scripts/check_prep.py --prep <prep>`. If it fails, fix what it names, by running again the step that writes that file, and check again. Once it passes, say the prep is ready, with a Markdown link to its report, and that the rest of the report, from what else was gathered, isn't built yet. If step 1's `temporary` is `true`, add that the folder is temporary and setting `output.root` in the config keeps preps.

## Summaries

What the manager tells you in steps 3 to 5, their view, the previous reviews and the period's feedback, is recorded as summaries. Before your first one, run `python3 ${CLAUDE_SKILL_DIR}/scripts/rules.py --prep <prep>` once: it prints the parts of a summary, the company's values and ratings, and `rules`, how to write a point and pick its values, with examples.

Once the manager answers, summarise what they gave, without showing them the summary: one summary for their view, and one for each review and each piece of the period's feedback, such as a document or a 1:1's notes. Give each review or piece its period as it names it, such as a date, "Mid Year Review 2026" or "Q3 2026", or null when it names none, and list them from the most recent, as far as you can tell, those with no period first, as the most recent of all. If something isn't clear, such as a word you can't read for sure or a document you couldn't open, ask them about it, all in one message, and wait for their answer. Then record it with the step's `set_summary.py` command, whose `--help` shows the input, tell them in one line that it's recorded, with a Markdown link to the `path` the script printed, and go on to the next step: that line can open the next step's message, as "a message of its own" means one with no other question in it.

Each part is a list of points, written as `rules` says. Keep what the source says about the person and their work, once even when it says it more than once, add nothing it doesn't, and put each in the part it belongs to; leave a part empty when the source says nothing of it. When the source judges the person's character or intentions and describes no behaviour behind it, ask the manager what was observed; if they don't know, the point stays as the source puts it.
