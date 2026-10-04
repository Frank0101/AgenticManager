---
name: agentic-manager-utils-refactoring
disable-model-invocation: true
description: Reviews a whole repository (docs such as README, CONTRIBUTING and AGENTS, skills, scripts and tests) for correctness, consistency, audience, clarity, quality, tests and gaps a change left elsewhere, and scores it. If anything needs changing, applies the fixes and reviews every file again, looping until a full review finds nothing to change, then formats the changed files. Run only when invoked explicitly as /agentic-manager-utils-refactoring, never on a general request to review or clean up a repo.
---

# Refactoring

Reviews every file in the repo, fixes what's wrong and reviews again, until a full review finds nothing to change, then formats the changed files. It's a utility (`agentic-manager-utils-*`), so it doesn't run `agentic-manager-utils-check-config` first.

## Score

The score is 100% only when a full review finds nothing to change or improve. Any finding, however small, means the score is below 100%. A round that changed anything is never a 100% round; only the round after it can be. A round that didn't read every file in full can't score 100%.

## Instructions

1. **Learn the repo's rules.** Read the files that say how the repo works, such as `README.md`, `CONTRIBUTING.md`, `AGENTS.md` and `CLAUDE.md`. They define what correct means here, for example which reader each document is for. Follow them in every round.

2. **Review from scratch.** List the files with `git ls-files` and `git ls-files --others --exclude-standard` (new files not committed yet), and read every one in full, skipping only generated, vendored and binary files and lock files. Every round has the same scope as the first: every file, read in full, including files no fix touched and files you read earlier in this run or earlier in the conversation. Never narrow a round to recent changes, and never replace reading a file with searching it. Apply what earlier rounds taught you to every file: a fix can make an untouched file wrong. This is slow by design; don't shorten it. Run the tests, if there are any. Look for:
   - **Correctness:** code does what its docs and comments say; docs describe what the code actually does; commands and examples work.
   - **Consistency:** the same fact is stated the same way everywhere; no file contradicts another; terms, spelling and formatting match.
   - **Audience:** each document speaks to its reader and holds only what that reader needs.
   - **Clarity:** every sentence has one meaning; it's clear who "you" and "it" refer to; nothing is repeated within a file.
   - **Quality:** no dead code, unused helpers or features nothing needs; code reads like the code around it.
   - **Tests:** they pass, cover every behavior, and match the code and docs.
   - **Gaps:** what a change should have changed elsewhere and didn't. Take every change, both this run's fixes and everything that differs from git's last commit, and ask of each one, against the whole repo:
     - It states a fact: where else is that fact stated, and does it still match?
     - It adds or changes something (a feature, setting, command or behavior): does every document whose reader needs it explain it, such as the README for the user?
     - It removes or renames something: does anything still refer to the old name?
     - It touches code: is part of it needed, or likely needed, by more than one place, so it belongs in the repo's shared code (here, `agentic-manager-utils-lib`)? Does it now duplicate code elsewhere?
     - It adds or changes a test: do several tests now check the same thing the same way, so they could become one test over a table of cases, or be grouped better?

3. **Score the round.** State how many files you read in full and how many step 2 listed; if they differ, the round isn't finished, so read the rest first. Then list every finding with its file and line, what's wrong and the fix, and give the round's score. Show the findings table to the user.

4. **If the score is below 100%, fix and repeat.** Apply every fix, run the tests, then go back to step 2 and review everything again from scratch.

5. **Stop and ask the user** instead of fixing when a finding needs their decision: a change of behavior or design, removing content they wrote, or two rules that contradict each other. Also stop if 10 rounds go by without reaching 100%, and show what keeps coming back.

6. **Format.** When a round scores 100%, format every file that differs from git's last commit, once, whether this run changed it or it was already changed or new before (`git status --short` lists them; skip deleted files), with the formatter the user's editor applies to its type, as its "Format Document" command would. Then run the tests again. Formatting only changes layout, so it doesn't start a new round.
   - Find the formatter in the repo's editor settings (such as `.vscode/settings.json`), then in the user's (for VS Code on macOS, `~/Library/Application Support/Code/User/settings.json`), for example `ms-python.autopep8` for Python or `esbenp.prettier-vscode` for JSON.
   - Run that formatter from the command line. If it isn't installed, run the copy bundled in the editor's extension (for VS Code, under `~/.vscode/extensions/`).
   - For a file type with no formatter set, use the one whose style the repo's files of that type already follow, and say so in the report.
   - If no formatter can be run, don't format by hand; say so in the report.

7. **Report.** Show a table of every round with the files it read in full out of those listed, its findings and fixes, then the formatters you ran and the final test result.

## Rules

- Change only what a finding calls for. Don't add features.
- Don't commit or push; the user decides when.
- Never display secrets found in the repo or in config. If you find one committed, report it as a finding without showing its value.
