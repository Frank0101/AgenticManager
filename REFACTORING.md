# Refactoring

Instructions for a full review of the repo, run when the developer asks. It isn't a skill: nothing outside `skills/` is installed, so it stays internal. Follow AGENTS.md throughout.

## What counts as an issue

Fix only real issues: something wrong, unclear, inconsistent with another file, duplicated, or longer than it needs to be. Leave improbable corner cases, cosmetic preferences and defensive additions alone.

After changing anything, read the pass's files again in full, not only what you changed: a change that is right locally can contradict another file. A pass ends when a full read finds no real issue; it never keeps going to find something small.

A change that alters what a skill does for the user, or what its output contains, is a behavior change: describe it and ask before making it. Fix everything else directly. When the developer's answer states a general principle, consider adding it to AGENTS.md, so the next run applies it to every file.

## 1. Markdown

1. Read README.md, AGENTS.md, every SKILL.md and every other `.md` file in the repo, except this one, in full.
2. Fix the real issues: anything not correct, clear, simple, consistent with the other files or minimal.

## 2. Python

Go one skill at a time, starting with `agentic-manager-utils-lib`, since every other skill uses it. For each skill:

1. Read in full its scripts or modules, its tests and its SKILL.md, and print its code map (`python3 skills/agentic-manager-utils-lib/agentic_manager/code_map.py --skill <skill>`).
2. Check that the code is correct, clear, simple and minimal, and that it is consistent:
   - across the skill's scripts;
   - within each script, with its header comment;
   - with what the SKILL.md says the skill does;
   - with the code map, whose lines, taken from header comments and docstrings, must say what each module and function is for (the tests check only that they exist);
   - with the library;
   - with AGENTS.md.
3. Check that nothing is written twice: no helper, constant or pattern, such as a regular expression, public or private, repeats one in the library, the skill's shared module or another script. A private one that another module needs is made public, with a docstring, not rewritten. A skill's helper that another skill could use belongs in the library.
4. Check the tests the same way, and also that they don't grow wildly: tests that check the same thing in the same way become one test over a table of cases.
5. Fix the real issues you found, in the code, the tests or the SKILL.md, and run the skill's tests, or every skill's after changing the library. The files to read again are the skill's, with AGENTS.md.

## 3. Type checks

Run pyright, the checker behind Pylance, with the repo's `pyrightconfig.json`:

```bash
npx -y pyright
```

Fix every error and warning it reports, then run the tests of each skill you changed.

## 4. Format

Format every file you changed, Markdown included (see Formatting in AGENTS.md).

## 5. Report

Tell the developer, file by file, what you changed and why, in a line each. Then list what you noticed but left alone because it needs their decision, such as a behavior change. Don't commit.
