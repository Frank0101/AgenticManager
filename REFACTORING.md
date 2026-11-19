# Refactoring

Instructions for a full review of the repo, run when the developer asks. It isn't a skill: nothing outside `skills/` is installed, so it stays internal. Follow AGENTS.md throughout.

## How the review is split

The split is about the context an agent can hold. Reading every file of the repo at once would leave too little room to read any of them well, so the review reads widely or deeply, never both:

- **Step 1 reads every Markdown file together**, and only those: it is the one place files are compared across the repo, and text keeps the read light enough to hold all of it.
- **Step 2 reads one skill at a time, in depth**: its Markdown, code and tests, and whatever else helps refactor it. AGENTS.md and the skill's archetype are the common reference, so a skill that matches them matches every other skill too, without loading them, and code another skill could share is found by looking in the others for what this one does.

## What counts as an issue

A refactoring cleans, consolidates and simplifies: it never makes the code more defensive. Fix only real issues: something wrong, unclear, inconsistent with another file, duplicated, or longer than it needs to be. Never add a check or a guard for a case no run has produced or that needs something improbable, such as a hand-edited output or a broken install, and leave cosmetic preferences alone. A fix that adds code needs a real case behind it; prefer the one that removes code.

After changing anything, read the pass's files again in full, not only what you changed: a change that is right locally can contradict another file. A pass ends when a full read finds no real issue; it never keeps going to find something small.

The reading can be split across reviewers working in parallel, along the same lines as the steps: one reviewer for step 1, and one per skill for step 2. Check every issue they report against the code yourself before acting on it, and drop any that isn't real. Prove a fixed bug with a test that fails on the code before the fix.

A change that alters what was agreed with the developer and written in a skill's Markdown files is a behavior change: describe it and ask before making it. Fix everything else directly. When the developer's answer states a general principle, consider adding it to AGENTS.md, so the next run applies it to every file.

## 1. Markdown, across the repo

1. Read README.md, AGENTS.md, the archetypes' files, every SKILL.md and every other `.md` file in the repo, except this one, in full.
2. Fix the real issues: anything not correct, clear, simple, consistent with the other files or minimal.
3. Check the archetypes: each archetype's file agrees with AGENTS.md, README.md's table gives each skill the archetype it is, and each SKILL.md follows its archetype's file, its steps in the same order and its files and scripts named the same way.
4. Check that each file's sections come in the order its reader needs them, a SKILL.md as AGENTS.md sets out, and that files of the same kind put their shared sections in the same order.

## 2. One skill at a time

Go one skill at a time, starting with `agentic-manager-utils-lib`, since every other skill uses it; the library has no archetype. Everything you read serves refactoring the skill at hand: read another skill's code when it helps with this one, such as to compare a helper or see how a skill of the same archetype solved the same problem, but not to review it, which its own turn does. For each skill:

1. Read in full its SKILL.md and its other Markdown, such as its protocols; its scripts or modules; and its tests, with AGENTS.md and the file of its archetype (README.md's table names it).
2. Check that the code is correct, clear, simple and minimal, and that it is consistent:
   - across the skill's scripts;
   - with what the SKILL.md says the skill does;
   - with its archetype: the steps it takes, in order, and the files and scripts they need, as the code and the files it writes actually are, not only as the SKILL.md says;
   - with its header comments and docstrings, whose first sentence, which the code map shows, says what each module and function is for (the tests check only that they exist);
   - with the library;
   - with AGENTS.md.
3. Check that nothing is written twice: no helper, constant or pattern, such as a regular expression, public or private, repeats one in the library, the skill's shared module or another script. A private one that another module needs is made public, with a docstring, not rewritten.
4. Check whether another skill already does what this one does, in a helper public or private, or something close enough to share, first in the skills of the same archetype, whose steps and so code are most alike, then in every other. You know what each part of this skill does, so look for that in the others, not for its name. When two do the same job, move one into the library and have both skills use it. A helper another skill could use belongs in the library even when no other skill has written it yet.
5. Check that each module reads top-down, as AGENTS.md sets out: `tests/repo/` checks that each function comes below the first one that uses it, so check that they are grouped by what they serve.
6. Check the tests the same way, and also that they don't grow wildly: tests that check the same thing in the same way become one test over a table of cases.
7. Fix the real issues you found, in the code, the tests or the skill's Markdown, and run the skill's tests, or every skill's after changing the library. The files to read again are the skill's, with AGENTS.md and its archetype's file.

## 3. Type checks

Run pyright, the checker behind Pylance, with the repo's `pyrightconfig.json`:

```bash
npx -y pyright
```

Fix every error and warning it reports, then run the tests of each skill you changed.

## 4. Format

Format every file you changed, Markdown included (see Formatting in AGENTS.md).

## 5. Report

Tell the developer, file by file, what you changed and why, in a line each. Then list, numbered:

- each behavior change, with a concrete case of what goes wrong today and the fix you propose;
- each real issue you left alone, such as one whose fix gains little, and why.

When the developer asks about an item, explain it plainly: what it is, the fix and why you left it, with your recommendation. Then wait for their answer. Don't commit.
