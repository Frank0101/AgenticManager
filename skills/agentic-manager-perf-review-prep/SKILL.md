---
name: agentic-manager-perf-review-prep
disable-model-invocation: true
description: Helps a manager prepare a performance review of one person over a review period, from the evidence of their work in Jira, GitHub, the documentation, the team's messages and the manager's own notes.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py --needs jira-api github-cli notion-mcp slack-mcp logseq-fs company.values --sensitive) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/extract_saved.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_jira_account.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/rules.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/read_notes.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/jira_ticket.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_work.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/read_notion.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_notion.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/read_slack.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/prepare_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_observations.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_step_change.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/finish_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/backup_prep.py *)
---

# Performance Review Prep

Helps a manager prepare a performance review of one person over a review period.

The skill's files go to the `perf-review-preps` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

```text
perf-review-preps/
└── Jane-Doe_26-11-10/
    ├── _raw/                         what each source gave: read_notes.py writes notes_items.json, read_slack.py
    │                                 slack_items.json, fetch_work.py jira.json and github.json, set_notion.py notion.json
    ├── _charts/                      finish_report.py writes (the report's charts)
    ├── person.json                   init_prep.py and set_identities.py write (the person, the period, their accounts)
    ├── manager_feedback.json         set_summary.py writes (the current manager feedback, summarised)
    ├── other_feedback.json           set_summary.py writes (the period's other feedback, summarised)
    ├── previous_feedback.json        set_summary.py writes (the previous feedback, summarised)
    ├── notes.json                    read_notes.py writes (what the manager's notes say)
    ├── slack.json                    read_slack.py writes (what the person's Slack messages show)
    ├── data.json                     prepare_report.py writes (the model the report reads)
    ├── observations_brief.json       prepare_report.py writes
    ├── observations_content.json     set_observations.py writes
    ├── step_change_brief.json        prepare_report.py writes
    ├── step_change_content.json      set_step_change.py writes
    └── Jane-Doe_Review_Prep.md       finish_report.py writes
```

To change a prep that is already done, as the manager asks, go straight to [step 9](#9-change-a-finished-prep), without the prerequisite.

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py --needs jira-api github-cli notion-mcp slack-mcp logseq-fs company.values --sensitive`, pre-approved in the frontmatter, and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

## Writing to the manager

In every message to the manager, write the person's name as the manager gave it, `person` in `person.json`, not the name an account shows; or "they". Never "he" or "she", nor any pronoun guessed from their name or anything else.

## 1. Agree what the prep is for

Call every script by exactly the path this skill shows, so it runs without a permission prompt; a script's `--help` gives its commands and arguments.

The prep needs, from the manager:

- **the person**, by their name;
- **the period**, such as the last 3, 6 or 12 months, or a first and last day.

Take what the manager gave when calling the skill, such as "for Jane Doe over the last 6 months", and ask, in one message, only for what is missing.

Turn the period into exact days with `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py`, for the last months or for days the manager named, which it checks. A first day without a last one runs up to today, which is the usual case, as a review is rarely prepared for an old period: pass today as the last day, and the confirmation at the end of step 2 shows it. For any other wording, such as "this year" or "H1", work out the first and last day yourself and pass them. If the script refuses a period, tell the manager why and ask again.

Then look the person up in Jira with `python3 ${CLAUDE_SKILL_DIR}/scripts/find_jira_account.py --person <name>`. Every other source is searched from the Jira account, so the account is found first and confirmed, with the period, at the end of step 2:

- **Pick the account.** An account is the person when its name is theirs, in full or as a short form, such as Al for Alan. If none could be them, stop and tell the manager the person must be in Jira for the prep; if Jira hides the email of the one you pick, stop and tell them the prep needs it, as it finds the person in the other sources.
- **One account** is not asked about here: go on.
- **Several such accounts:** propose the one you pick, such as the active one, say briefly why, and ask the manager to confirm it before going on.

Then start the prep with `python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py`, for the person, the account's `accountId` and the period's days. It prints the prep folder's name, `prep`, which later steps pass as `<prep>`. The folder is named after the Jira account's official name, such as `Jane-Doe`, even when the manager gave a short form, such as Jane: `person.json` and the report keep the name as the manager gave it. This is on purpose, so the same person always gets the same folder, and a rerun on the same day replaces it; don't ask the manager about it. If the manager corrects the account or the period at the end of step 2, start again from here: the same day's prep is rebuilt from scratch.

## 2. Find the person in each source

Who the person is in GitHub, Notion, Slack and the vault is the manager's to confirm, with their Jira account and the period, in one message at the end of this step: a wrong account would quietly bring in someone else's work. The prep needs the person in every source, as a review drawn from some of them would read as if they did nothing in the others: if a source has no one who could be them, or the manager says they aren't in one, stop and tell the manager which source, and that the prep needs the person in every one.

1. **Look them up,** all three at once, as none needs another's result. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py --prep <prep>` for GitHub and the vault. Search Notion and Slack yourself, through their MCPs' user search: Notion by the Jira account's email, which `init_prep.py` printed in `person`, under its Jira account, and only if that finds no one, by the person's name; Slack by the words of the person's name, each a keyword of its own, never in quotes, as its search doesn't match an email or a quoted name, and if that finds no one, by each word alone, picking the account that shows the Jira email.
2. **Pick the person in each source.** An account is the person when its email is the Jira account's, or its name is theirs, in full or as a short form, such as Al for Alan; GitHub's accounts are found by that email already. Several accounts you can't tell apart are a question for the manager. In the vault, pick every link about the person, their tag and the pages about them, such as `[[Jane]]` and `[[Jane Promotion]]`, and every alias their page declares, such as `[[JD]]`, and leave out one that only shares letters with their name, such as `[[Janet]]`.
3. **Ask the manager to confirm,** in one message: the period, as `period.py`'s `shown`, the Jira account with its name and email, and for each other source the account or links you picked and, briefly, why, and your questions where you couldn't pick. Don't list what you left out. For example:

   > I'll prepare Jane Doe's review for 10/05/2026 to 10/11/2026. Here's who I think Jane is in each source:
   >
   > - Jira: Jane Doe, jane.doe@acme.test.
   > - GitHub: janedoe, whose commits use Jane's Jira email.
   > - Notion: Jane Doe, with the same email.
   > - Slack: two accounts, Jane Doe and Jane Doe (Contractor). Which one is Jane?
   > - Your notes: `[[Jane]]` (120 mentions, its own page) and `[[Jane Promotion]]` (8).
   >
   > Is that right?

   A reply that doesn't answer each question, such as a plain yes, confirms only what you found: ask the open questions again. Don't go on until every source is settled.

4. **Record it** with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py --prep <prep>`; its `--help` shows the input. Run it again with every source to record a correction.

## 3. Hear the manager's feedback

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/rules.py` once, here, for all three feedbacks (see [Summaries](#summaries)). Then take them in this order, each asked in a message with no other question in it, `<person>` being the person's name, `<period>` the period as step 1 showed it and `<first day>` its first day. End each question with: "Paste it, give me a path or a link to it, or sum up its main points. Say \"none\" if there isn't any."

| Feedback                 | Ask                                                                                                                                                                                                                                                                                                                           | `--of`     |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Current manager feedback | > What is your current manager feedback on `<person>` for `<period>`, such as the notes of your 1:1s or your mid-period reflection? Cover what's going well or exceeding, what to improve or stretch, including what you want to see next, any support they need and any context, such as a long absence or a change of role. | `manager`  |
| Other feedback           | > Do you have other feedback on `<person>` given in `<period>`, such as their OKRs, feedback from other people, or kudos and recognition they received?                                                                                                                                                                       | `other`    |
| Previous feedback        | > Do you have `<person>`'s previous feedback, before `<first day>`? It is usually the previous official feedback: the mid-year review for an end-of-year review, or last year's end-of-year review for a mid-year one.                                                                                                        | `previous` |

## 4. Gather more feedback from the manager's notes and Slack

The manager's own notes on the person, in their vault, and the person's Slack messages are many, and most aren't feedback, so subagents read them, never you: their context would fill yours. The notes are gathered and numbered by a script, so one subagent has only to judge them: it writes their summary, each point citing the notes it rests on. Slack is read a month at a time, by a subagent for each month who lists what it finds, and then one judge writes the summary from every month's list, so a behaviour that repeats over months is seen as the pattern it is. Say nothing to the manager while the subagents work, not even as each one finishes.

1. **Start.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/read_notes.py start --prep <prep>` and `python3 ${CLAUDE_SKILL_DIR}/scripts/read_slack.py start --prep <prep>`. The notes script prints `task`, the line `Task <name>: <path>` of its task, or `path` instead when it had nothing to read and recorded an empty summary; the Slack script prints `tasks`, one such line for each month, and `judge`, the line of the judge's task, whose file exists once every month is submitted.
2. **Hand out the tasks.** Give the notes task, and each month's Slack task, to a fresh subagent each, all at once, only its path, with: "Do the task in <path> exactly as written there, then reply in one line." If the tool caps how many subagents run at once, start the next task as soon as one replies. A month's reader follows every conversation and describes it, but judges nothing, so its subagent can run on a smaller model than yours; the notes subagent and the judge only judge, so they use yours. Once every month has replied, give the `judge` task to one more fresh subagent the same way, unless its file isn't there: no month listed a conversation, so the last month's submit recorded the empty Slack summary (`path`) and there is nothing to hand out.
3. **Finish** once the notes subagent has replied, and the judge if there was one: tell the manager, in one line, that what their notes say and what the person's Slack shows are recorded, with a Markdown link to each, `notes.json` and `slack.json` in the prep's folder, `prep_dir` as step 1 printed it, and go on.

## 5. Gather the data points

The person's work in Jira, GitHub and Notion, in the period. It and step 4 don't need each other, so start it as soon as step 4's subagents are handed their tasks, without waiting for them. Say nothing to the manager about it while it runs, unless a script stops; step 4's message is sent as soon as both summaries are recorded, without waiting for this step.

1. **Jira and GitHub.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_work.py --prep <prep>`: it fetches the issues and pull requests, with no judgment, into their raw files.
2. **Notion.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/read_notion.py start --prep <prep>`: it prints `task`, the line `Task notion: <path>` of the task that finds the pages the person created. Give it to a fresh subagent the same way as in step 4. That work is mechanical, so use the cheapest model the tool offers; when it replies, go on.

## 6. Summarise the observations

Once steps 4 and 5 are done, run `python3 ${CLAUDE_SKILL_DIR}/scripts/prepare_report.py --prep <prep>`: it builds `data.json`, the model the report reads, from the raw files and the summaries of the current manager feedback, the other and previous feedback, the notes and Slack, with no network, then a brief for each task, and prints `tasks`, a line `Task <name>: <path>` for each of its tasks: one summarises the three tables of observations, what is going well, what to improve and the context, and one writes the step change from the previous feedback, when there is one. Give each to a fresh subagent, all at once, the same way as in step 4. Each task holds its own instructions and records what it writes with a script that checks it as it's written. Once all have replied, go on to step 7.

## 7. Finish

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/finish_report.py --prep <prep>`: it checks `observations_content.json` and `step_change_content.json` field by field, then writes the report, `<Person>_Review_Prep.md`, and its charts from `data.json` and those two, and checks the whole prep. If its `problems` aren't empty, fix what each names by running again the step that writes that file, step 6 for `observations_content.json` and `step_change_content.json`, then run it again; if you can't, stop and tell the manager what they say.

## 8. Tell the manager

Say the prep is ready, with a Markdown link to its report. Don't recap the report; add only a doubt about your own judgment that it doesn't show, such as a summary you weren't sure how to weigh. If step 1's `temporary` is `true`, add that the folder is temporary and setting `output.root` in the config keeps preps.

## 9. Change a finished prep

Once a prep is done, the manager may ask you to change it. Work only from what they already know: the prep's files, their notes, the links already in those files and what they tell you. Never search Slack or Notion again.

Before each change the manager asks for, run `python3 ${CLAUDE_SKILL_DIR}/scripts/backup_prep.py save --prep <prep>` once: it keeps the prep as it is before the change. If the manager asks to undo it, run `python3 ${CLAUDE_SKILL_DIR}/scripts/backup_prep.py restore --prep <prep>`.

Make each change where the report's text comes from, in a feedback of step 3 or in the notes, never in the report or in the summaries built from them, then run again only the steps that follow and tell the manager as in step 8:

- **The manager has updated their notes.** Read them again up to today with `python3 ${CLAUDE_SKILL_DIR}/scripts/read_notes.py start --prep <prep> --until-today`, hand out its task as in step 4, then run steps 6 and 7. The notes come only from the vault: something the manager tells you in chat they add to their vault first, or it goes into a feedback of step 3.
- **The manager wants to change a feedback of step 3**, adding to it, cutting it or replacing part or all of it. Update its summary as [Summaries](#summaries) says, record it whole again with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py --prep <prep> --of <manager|other|previous>`, then run steps 6 and 7.

## Summaries

What the manager tells you in step 3 is one text per feedback, recorded as one summary, all three the same way. `rules.py` prints the parts of a summary, the company's values, and `rules`, how to write a point and pick its values, with examples.

Once the manager answers, summarise what they gave, without showing them the summary. If something isn't clear, such as a word you can't read for sure or a document you couldn't open, ask them about it, all in one message, and wait for their answer. Then record it with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_summary.py --prep <prep> --of <manager|other|previous>`, whose `--help` shows the input, tell them in one line that it's recorded, with a Markdown link to the `path` the script printed, and go on to the next question: that line can open its message.

Each part is a list of points, written as `rules` says. Keep what the text says about the person and their work, add nothing it doesn't, and put each in the part it belongs to; leave a part empty when the text says nothing of it, and all three when it says nothing of the person. When `rules` would keep a judgement of the person's character as the text puts it, ask the manager first what was observed.
