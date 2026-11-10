---
name: agentic-manager-perf-review-prep
disable-model-invocation: true
description: Helps a manager prepare a performance review of one person over a review period, from the evidence of their work in Jira, GitHub, the documentation, the team's messages and the manager's own notes. In development; not ready to use.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_orientation.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_feedback.py *)
---

# Performance Review Prep

Helps a manager prepare a performance review of one person over a review period. The skill is in development: only its first steps are built.

The skill's files go to the `perf-review-preps` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

```text
perf-review-preps/
└── Jane-Doe_26-11-10/
    ├── request.json      init_prep.py writes (the person and the period the manager confirmed)
    ├── identities.json   set_identities.py writes (who the person is in each source, as the manager confirmed)
    ├── orientation.json  set_orientation.py writes (the manager's overall view of the person, summarised)
    └── feedback.json     set_feedback.py writes (the person's previous feedback, each piece summarised)
```

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill needs the `jira-api`, `github-cli`, `notion-mcp`, `slack-mcp` and `logseq-fs` sources, and the `company.perf-review-ratings` and `company.values` settings. If a source isn't enabled or a setting isn't set, stop and tell the user how to fix it, showing its `setup` and the config `path`: the ratings are the company's performance review ratings, lowest first, and the values its values, each with what it means. The scripts read the config's settings themselves: never read the config file, or pass or show a setting, except what a script prints for you, such as the company's ratings.

## Writing to the manager

In every message to the manager, and in every summary, write the person's name, or "they": never "he" or "she", nor any pronoun guessed from their name or anything else.

## Summaries

What the manager tells you and what the person's previous feedback says are recorded as summaries, in three parts:

- `going_well`: what is going well or exceeding;
- `to_improve`: what are improvement or stretch areas;
- `context`: facts that are neither good nor bad, such as a long absence or a change of role.

Each part is a list of points, in your words: one sentence each, about 25 words at most, such as "Delivers tickets reliably and with good quality". Each point stands on its own: say what it is about, such as a promotion, so it reads without the source. Keep every point the source makes, add none it doesn't, and put each in the part it belongs to; leave a part empty when the source says nothing of it.

## 1. Agree what the prep is for

Call every script by exactly the path this skill shows, so it runs without a permission prompt; a script's `--help` gives its commands and arguments.

The prep needs, from the manager:

- **the person**, by their name;
- **the period**, such as the last 3, 6 or 12 months, or a first and last day.

Take what the manager gave when calling the skill, such as "for Jane Doe over the last 6 months", and ask, in one message, only for what is missing.

Turn the period into exact days with `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py`: `--last-months N` for the last N months, or `--start` and `--end` for days the manager named, which it checks. For any other wording, such as "this year" or "H1", work out the first and last day yourself and pass them. Then ask the manager to confirm the person and the period, as its `shown`: "I'll prepare Jane Doe's review for 10/05/2026 to 10/11/2026. Is that right?" If the script refuses a period, tell the manager why and ask again. Don't go on until they confirm.

Once they do, start the prep:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py --person '<name>' --start <YYYY-MM-DD> --end <YYYY-MM-DD>
```

It creates the prep's folder, replacing one of the same person and day, records the request in it, and prints the folder's name, `prep`, which later steps pass as `<prep>`.

## 2. Find the person in each source

Who the person is in each source is the manager's to confirm, as the period was: a wrong account would quietly bring in someone else's work.

1. **Look them up.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py --prep <prep>` for Jira, GitHub and the vault. Search Notion and Slack yourself, through their MCPs' user search: by the full name, and, if it finds no one, by each word of it and by the email Jira shows.
2. **Pick the person in each source.** An account is the person when its name is theirs, in full or as a short form, such as Al for Alan, or when its email is the one Jira shows; the same email in several sources makes it surer. A source with no such account, or with several you can't tell apart, is a question for the manager. In the vault, pick every link about the person, their tag and the pages about them, such as `[[Jane]]` and `[[Jane Promotion]]`, and leave out one that only shares letters with their name, such as `[[Janet]]`.
3. **Ask the manager to confirm,** in one message: for each source, the account or links you picked and, briefly, why, and your questions where you couldn't pick. Don't list what you left out. For example:

   > Here's who I think Jane Doe is in each source:
   >
   > - Jira: Jane Doe, jane.doe@acme.test.
   > - GitHub: janedoe, whose commits use that email.
   > - Notion: Jane Doe, with the same email.
   > - Slack: two accounts, Jane Doe and Jane Doe (Contractor). Which one is Jane?
   > - Your notes: `[[Jane]]` (120 mentions, its own page) and `[[Jane Promotion]]` (8).
   >
   > Is that right?

   A reply that doesn't answer each question, such as a plain yes, confirms only what you found: ask the open questions again. The manager may say the person isn't in a source, such as someone with no GitHub account: record it as absent. Don't go on until every source is settled.

4. **Record it** with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py --prep <prep>`; its `--help` shows the input. Run it again with every source to record a correction.

## 3. Hear the manager's view

Before any evidence is gathered, ask the manager, in a message of its own, for their overall view of the person over the period:

> Before I look at any evidence: what's your overall view of Jane Doe over this period? A few points or sentences are enough: what's going well or exceeding, what are improvement or stretch areas, and any context the review should take into account, such as a long absence or a change of role. I'll take it as guidance, and point out where the evidence says otherwise.

Wait for their answer, summarise it as [Summaries](#summaries) says, and ask them to confirm the summary, part by part. Once they do, record it with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_orientation.py --prep <prep>`; its `--help` shows the input. Only the writing step reads it, so the evidence is gathered without it and can contradict it.

## 4. Read the previous feedback

Previous feedback is whatever the manager gives as such: a review, a colleague's feedback or their own notes on either. Take it as it comes: its days and its rating are recorded when it gives them, and never asked for. It often comes from several places, so ask for more until the manager has none.

1. **Get the rules.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/set_feedback.py rules --prep <prep>`: it prints the company's ratings, `earliest_end`, the first day dated feedback may end on, 2 years before the period starts, and the parts of a summary.
2. **Ask the manager**, in a message of its own, giving `earliest_end` as DD/MM/YYYY:

   > Do you have any previous feedback on Jane Doe since 10/08/2024, such as reviews or a colleague's feedback? Paste it, or give me a path or a link to it, such as a PDF exported from your HR tool. Say "none" if there isn't any.

   If they say none, record `{"reviews": []}` (step 5) and go on.

3. **Read and summarise it** yourself, as you did the manager's view. For each piece, note the period it covers as YYYY-MM-DD, its rating, as the company's ratings name it, and a summary of what it says, as [Summaries](#summaries) says. When the feedback names its period rather than its days, such as "MYR 2026" or "2025 annual review", work the days out and say they're worked out; leave out a day nothing in it points to. Leave out a piece that ends before `earliest_end`, and a rating that isn't on the company's scale. Keep a rating you're unsure is the feedback's own, such as one on a colleague's line, and say why you're unsure.
4. **Ask the manager to confirm,** in one message: for each piece, its period and its rating where it has them, and its summary, part by part, then each period you worked out, each rating you're unsure of and what you left out, each with why. Ask them to paste a piece you couldn't open. Don't go on until they confirm.
5. **Record it** with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_feedback.py write --prep <prep>`, with every piece confirmed so far, so a stopped run keeps them; its `--help` shows the input. Run it again with every piece to record a correction.
6. **Ask for more:** "Any more previous feedback on Jane Doe?" Go back to 3 with what the manager gives, and go on once they have no more.

## 5. Tell the user

Say the prep is started, with a Markdown link to its `prep_dir`, and that the next steps, starting with the person's personal OKRs and 1:1 notes, aren't built yet. If step 1's `temporary` is `true`, add that the folder is temporary and setting `output.root` in the config keeps preps.
