---
name: agentic-manager-perf-review-prep
disable-model-invocation: true
description: Helps a manager prepare a performance review of one person over a review period, from the evidence of their work in Jira, GitHub, the documentation, the team's messages and the manager's own notes. In development; not ready to use.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/period.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_prep.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/find_person.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py *)
---

# Performance Review Prep

Helps a manager prepare a performance review of one person over a review period. The skill is in development: only its first steps are built.

The skill's files go to the `perf-review-preps` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

```text
perf-review-preps/
└── Jane-Doe_26-11-10/
    ├── request.json      init_prep.py writes (the person and the period the manager confirmed)
    └── identities.json   set_identities.py writes (who the person is in each source, as the manager confirmed)
```

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill needs the `jira-api`, `github-cli`, `notion-mcp`, `slack-mcp` and `logseq-fs` sources. If one is missing, stop and tell the user how to enable it, showing its `setup` and the config `path`. The scripts read the config's settings themselves: never read the config file, or pass or show a setting.

## Writing to the manager

In every message to the manager, write the person's name, or "they": never "he" or "she", nor any pronoun guessed from their name or anything else.

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
2. **Judge each source.** An account is the person when its name is theirs, in full or as a short form, such as Al for Alan, or when its email is the one Jira shows; the same email in several sources makes it surer. A source with no such account, or with several, is a question for the manager. In the vault, offer every link that could be about the person, their tag and the pages about them, such as `[[Jane]]` and `[[Jane Promotion]]`, with how often notes use each and whether it has a page, for the manager to choose every one that is.
3. **Ask the manager to confirm,** in one message: for each source, who you found and how, and your questions where you couldn't settle it. For example:

   > Here's who I think Jane Doe is in each source:
   >
   > - **Jira:** Jane Doe, jane.doe@acme.test, the only account with that name.
   > - **GitHub:** janedoe, whose commits use that email.
   > - **Notion:** Jane Doe, with the same email.
   > - **Slack:** two accounts, Jane Doe and Jane Doe (Contractor). Which one is Jane?
   > - **Your notes:** `[[Jane]]` (120 mentions, its own page) and `[[Jane Promotion]]` (8). Which of these are about Jane?
   >
   > Is that right?

   The manager may say the person isn't in a source, such as someone with no GitHub account: record it as absent. Ask again until every source is settled; don't go on until they confirm.

4. **Record it** with `python3 ${CLAUDE_SKILL_DIR}/scripts/set_identities.py --prep <prep>`; its `--help` shows the input. Run it again with every source to record a correction.

## 3. Tell the user

Say the prep is started, with a Markdown link to its `prep_dir`, and that the next steps, starting with fetching the person's work from each source, aren't built yet. If step 1's `temporary` is `true`, add that the folder is temporary and setting `output.root` in the config keeps preps.
