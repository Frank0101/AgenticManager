---
name: agentic-manager-utils-refactoring
description: Reviews a whole repository (docs such as README, CONTRIBUTING and AGENTS, skills, scripts and tests) for correctness, consistency, quality and clarity, and scores it. If anything needs changing, applies the fixes and reviews again from scratch, looping until a full review finds nothing to change. Use when the user asks to refactor, review, clean up or polish the repo, or to keep reviewing until everything is 100%.
---

# Refactoring

Reviews every file in the repo, fixes what's wrong and reviews again, until a full review finds nothing to change. It's a utility (`agentic-manager-utils-*`), so it doesn't run `agentic-manager-utils-check-config` first.

## Score

The score is 100% only when a full review finds nothing to change or improve. Any finding, however small, means the score is below 100%. A round that changed anything is never a 100% round; only the round after it can be.

## Instructions

1. **Learn the repo's rules.** Read the files that say how the repo works, such as `README.md`, `CONTRIBUTING.md`, `AGENTS.md` and `CLAUDE.md`. They define what correct means here, for example which reader each document is for. Follow them in every round.

2. **Review from scratch.** List the files with `git ls-files` and `git ls-files --others --exclude-standard` (new files not committed yet), and read every one in full, skipping only generated, vendored and binary files and lock files. Don't rely on what you read in earlier rounds: fixes can introduce new problems. Run the tests, if there are any. Look for:
   - **Correctness:** code does what its docs and comments say; docs describe what the code actually does; commands and examples work.
   - **Consistency:** the same fact is stated the same way everywhere; no file contradicts another; terms, spelling and formatting match.
   - **Audience:** each document speaks to its reader and holds only what that reader needs.
   - **Clarity:** every sentence has one meaning; it's clear who "you" and "it" refer to; nothing is repeated within a file.
   - **Quality:** no dead code, unused helpers or features nothing needs; code reads like the code around it.
   - **Tests:** they pass, cover every behavior, and match the code and docs.

3. **Score the round.** List every finding with its file and line, what's wrong and the fix, then give the round's score. Show the findings table to the user.

4. **If the score is below 100%, fix and repeat.** Apply every fix, run the tests, then go back to step 2 and review everything again from scratch.

5. **Stop and ask the user** instead of fixing when a finding needs their decision: a change of behavior or design, removing content they wrote, or two rules that contradict each other. Also stop if 10 rounds go by without reaching 100%, and show what keeps coming back.

6. **Report.** When a round scores 100%, show a table of every round with its findings and fixes, and the final test result.

## Rules

- Change only what a finding calls for. Don't add features.
- Don't commit or push; the user decides when.
- Never display secrets found in the repo or in config. If you find one committed, report it as a finding without showing its value.
