---
name: agentic-manager-utils-refactoring
disable-model-invocation: true
description: Reviews and refactors a repository for correctness, consistency, audience, clarity, quality, simplicity, tests and gaps between files. Fixes substantive problems in those concerns, defers marginal cases and optional hardening, validates the changes and formats the requested files. Run only when invoked explicitly as /agentic-manager-utils-refactoring, never on a general request to review or clean up a repo.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/precheck.py *)
---

# Refactoring

Resolve substantive repository problems under the [Review concerns](#review-concerns), with focused changes and proportionate validation. It's a utility (`agentic-manager-utils-*`), so it doesn't run `agentic-manager-utils-check-config` first.

## Scope and priorities

- The eight review concerns define the problems to look for. Review the repository against them; the user doesn't need to supply a separate issue list. If the user narrows the scope or highlights an area, honor that instruction.
- Fix concrete correctness, consistency, documentation, maintainability and test problems within those concerns. Findings need evidence of a meaningful effect on ordinary use or ongoing development, such as lost data, incorrect results, a failed documented command, confusing instructions, actual duplication or missing coverage of an important behavior.
- Don't invent requirements for undocumented inputs. Don't spend the run hardening malformed inputs, extreme values, unusual file variants or hypothetical misuse unless those are part of the user's problem or demonstrate a material risk in ordinary use. A technically reproducible edge case alone doesn't establish that it is worth fixing.
- Style preferences, cosmetic imperfections, optional hardening and unrelated issues don't block completion or trigger another round. Briefly record an optional item only when it is useful to the user; otherwise leave it alone.
- Evaluate proposed fixes against the Simplicity concern before changing code; their practical benefit must justify their maintenance cost.

## Instructions

1. **Learn the rules and define the outcome.** Read the repo's rule files, such as `README.md`, `CONTRIBUTING.md`, `AGENTS.md` and `CLAUDE.md`, when present. Identify the repository files and the evidence needed to judge the review concerns. Follow any user-specified scope or priorities. Preserve unrelated work and existing authorization boundaries.

2. **Establish the baseline.** Run the relevant existing tests. List tracked and untracked files with `git ls-files` and `git ls-files --others --exclude-standard`, excluding generated, vendored, binary and lock files. Run the mechanical pre-check when it is useful to the scope, by this path:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/precheck.py
   ```

   It changes nothing and prints JSON containing `leads`, the test listing and `skipped` checks. It scans the repository, so use only leads relevant to the agreed scope. Leads about similar tests, long comments or unused names are hypotheses, not mandatory cleanup. Report skipped checks that limit validation of the requested work.

3. **Collect relevant issues before fixing.** Read each in-scope file in full and assess the eight review concerns. Trace important supported behaviors from their promises through implementation and tests. Check normal use, relevant boundaries and interactions between the affected parts. Choose probes from the contract or an authoritative input format; passing tests establish only the cases they cover. Don't expand this into an exhaustive search for increasingly rare counterexamples.

   When the scope warrants delegation, use fresh read-only reviewers for coherent groups of code and tests, within the available agent slots. Give them the rule files, agreed scope and priorities, affected files, relevant pre-check leads and user-accepted decisions. For a repository-wide review, cover every listed file and have a separate reviewer trace the important paths across groups. If the user requests a narrower refactor, review its affected paths.

   Reviewers return:
   - the reviewed concerns and important behaviors, meaningful checks performed, and evidence or verification limits;
   - each relevant finding: file and line, user impact, violated contract or repo rule, expected and observed behavior, root cause, affected cases and proposed fix;
   - dispositions for relevant mechanical leads, and useful optional items kept out of the fix scope.

   Inspect sibling branches and callers when the same cause can affect ordinary use. Reconcile overlapping findings without losing relevant cases. Resolve in-scope hypotheses before closing the review; don't defer an unfinished check merely to create another round.

4. **Fix and validate the requested outcome.** Apply substantive findings to their root causes and add regression coverage where it meaningfully establishes the affected behavior. Run appropriate tests and checks. Review the resulting diff for unrelated changes and scope expansion. Use an independent review when the change's complexity or risk justifies it; don't repeat full reviews merely to collect two rounds with zero findings.

   Continue only to resolve a substantive in-scope finding, a failing check or a demonstrated regression in the affected workflow. Completion means the substantive findings are resolved and appropriate validation passes, with any material limits disclosed. It does not mean the repository has no conceivable improvement. Honor any user-specified limit on rounds or time.

5. **Decisions and blockers.** Ask only when an unresolved choice changes the agreed behavior or design, removes user-authored content, conflicts with a repo rule, or requires authorization not already given. Complete independent authorized work first. Explain the concrete choice or blocker; don't ask permission again for an already authorized fix.

6. **Format.** Format the files the user requested. Otherwise format the changed files, including new files; skip deleted files and symlinks. When the user asks for all files, include all supported source and documentation files in the repo. Use the formatter the user's editor applies to that type, once per file:
   - Find it in repo editor settings, then the user's settings, such as `~/Library/Application Support/Code/User/settings.json` on macOS. Read only formatter settings; don't display unrelated values.
   - Run the formatter from the command line, using the copy bundled in the editor extension if necessary.
   - If no formatter is configured for a type, use one matching the existing repository style and disclose that fallback.
   - If no formatter can run, report it; don't format by hand.

   Run appropriate tests after formatting. Formatting doesn't require another review round. If validation fails, resolve the failure within the agreed scope.

7. **Report and stop.** State which substantive problems were resolved, the material changes, validation results, formatting performed and any remaining in-scope blocker or useful deferred item. For multiple rounds, summarize what each accomplished. Don't present a percentage score as proof that no problems remain. Stop when the substantive work and validation are complete, or at the user's requested limit.

## Review concerns

Review repository files against these concerns, applying the scope and priority filter above:

- **Correctness:** behavior matches the documented contract and requested outcome.
- **Consistency:** affected code, docs, commands and tests agree.
- **Audience:** user docs, developer docs and agent instructions serve their respective readers.
- **Clarity:** affected explanations are unambiguous and sufficient for the task.
- **Quality:** code is readable and maintainable, with actual dead code and duplication addressed.
- **Simplicity:** use the fewest concepts, branches and abstractions needed for documented supported behavior. Each extra check, fallback or layer must address a demonstrated problem or a concrete requirement of ordinary use. Keep necessary validation, but avoid defensive scaffolding for hypothetical inputs; prefer a clear contract and a straightforward implementation.
- **Tests:** meaningful normal-use and regression cases establish the affected behavior; consolidate cases that check the same thing the same way.
- **Gaps:** affected callers, shared representations and generated outputs preserve what the workflow needs.

## Rules

- Change only what a substantive in-scope finding calls for. Don't add features or unrelated cleanup.
- Don't commit or push; the user decides when.
- Never display secrets found in the repo or config. Report a committed secret without showing its value.
