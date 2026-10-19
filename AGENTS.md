# AGENTS.md

## Rules that always apply

For you, working in this repo, whatever the task. A skill's instructions are followed by an agent, so they hold for every skill too.

- **Never read or display secrets.** Settings in the user's config can hold secrets, such as tokens, and anything the agent reads can end up in the chat. Never read the config file directly: use a script or a helper from the library (see [Utilities](#utilities)), and never write one that prints settings from the config. Refer to a setting by name, for example "using your `api-token`", and never display a secret in the chat, in output or in files.
- **Never change the developer's config.** The one exception is creating it when it's missing: you may ask whether to create it from the template and, only if the developer explicitly approves, create it with `check_config.py --init`. For any other problem, tell the developer how to fix it.
- **Keep the developer's config out of the repo.** Skills run here read the developer's config (`~/.config/agentic-manager/config.json`) as they do anywhere else, but nothing from it may end up in tests, examples or code, not even as assumptions about which sources are enabled.
- **Never put secrets or internal data in this repo.** Skills are often based on real work cases. Keep real names, ticket numbers, project keys, URLs, channel names, messages, documents and credentials out of skills, examples, tests and commit messages; use made-up examples such as `PROJ-123` or `acme`. Anything specific to a team belongs in the user's config, as a setting. Before committing, check the diff for anything that came from a real case.
- **A check is a guardrail, never the goal.** When a check fails, do the work it protects. Never change, relabel, reword or fill in anything only so that the check passes, never loosen a check that reports open work to let the work through, and never write a value you can't stand behind. Change a check only for a case it gets wrong: say so and show the case.
- **Choices about scope belong to the user.** Never decide on your own to skip a step a skill requires or to treat a topic as out of scope. Ask, and record their answer where the skill asks for it; until they answer, the work stays open. How deep to go is not such a choice: the user asks for the work because they don't know those details, so a skill states how much evidence is enough, and reports what it left out instead of asking. Whatever you can do yourself, do.
- **Record decisions in the repo.** When the developer settles how the skills or this repo should work, write it in the repo, not only in an agent's local memory, so it applies on every machine and to every agent: in AGENTS.md when it holds for every skill, or in the skill's SKILL.md and scripts when it is the skill's own. AGENTS.md names no skill but the shared library, and describes no other skill's files or scripts; its rules and examples stay general.
- **Generate lists of what exists, never keep them by hand.** A list of things that live in the repo or the output folder, such as examples or the code's modules and functions, is built by a script from the things themselves, each describing itself (a `description.md`, a header comment, a docstring), so it can't go stale and adding or removing one needs no other edit.
- **Never change the developer's installed skills** (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`).
- **Never run `npx skills` from inside this repo.** The `skills` CLI has a bug: `remove -g` also deletes `<current folder>/.agents/skills/<skill>`, and here that's a symlink to `skills/`, so it deletes the skill's source. Run it from another folder.

## Layout

```text
skills/<skill>/          one folder per skill
  SKILL.md               instructions the agent follows
  scripts/               optional helper scripts
skills/agentic-manager-utils-lib/
  agentic_manager/       Python package with the helpers shared by all the skills:
                         their scripts import it
tests/<skill>/           tests for that skill, mirroring skills/: unit tests per script or
                         module (test_<module>.py) and end-to-end tests (test_e2e_*.py)
tests/repo/              checks of the repo's own integrity: every module and listed
                         function says what it is for, every module reads top-down,
                         every script answers --help, and every link to a section in
                         AGENTS.md and each SKILL.md reaches a heading
tests/run.py             runs every skill's tests, each skill in its own process (its own
                         tests are in tests/runner/)
.claude/skills  ─┐       symlinks to skills/, so the skills load when you run
.agents/skills  ─┘       Claude Code or Codex inside this repo
```

The symlinks let you use the skills while you build them. Edits to a skill apply to the next agent session; a running session keeps the instructions it already loaded. If the skills are also installed globally (`~/.claude/skills`, `~/.agents/skills`), a session here may load the installed copy instead of the one you're editing, so a change you test may not be the one that runs.

## Utilities

Skills named `agentic-manager-utils-*` are utilities: other skills use them, the user doesn't invoke them. At the moment there is one, `agentic-manager-utils-lib`: the `agentic_manager` Python package under `skills/agentic-manager-utils-lib/agentic_manager/`, with the helpers shared by all the skills.

Skills must use the library: shared code goes in it and is used from there, never reimplemented or copied into a skill. It keeps only what any skill using the same tool or the config would need, such as the Jira client and helpers for Jira keys and timestamps; choices that belong to one skill, such as which issue fields it fetches, stay in that skill.

Before creating a skill or working on an existing one, print the code map, `python3 skills/agentic-manager-utils-lib/agentic_manager/code_map.py [--skill <skill>]`, so you know what is already there: every module of the library and of each skill's scripts with what it is for, and the functions and classes other code may use. A module's header comment then says how to call it and why it works that way. Before writing a helper, a constant or a pattern, such as a regular expression, search the library and the skill's scripts for one that already does it, and use or extend that. Search the code itself, not only the map: it lists public functions only, and a private one, or one inside a single script, may already do the job. Make such a one public in the library or the skill's shared module, with a docstring, rather than writing another, and move a skill's helper that another skill could use to the library rather than copying it.

`npx skills` installs each skill as its own folder, side by side, with no shared folder and no install step, so a script finds the library next to its own skill's folder, and the agent runs its modules by the same path. This relies on all the skills being installed together, which a normal install does; if the library is missing, a skill's prerequisite tells the user to reinstall every skill. To use it from a script:

- Add the library to the path before importing, as in this example, placed in the skill's shared module:

  ```python
  LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         "..", "..", "agentic-manager-utils-lib")
  sys.path.insert(0, LIB_DIR)
  from agentic_manager import config
  ```

- Use `realpath`, not `abspath`: Claude Code installs skills as symlinks to `~/.agents/skills`.
- In a skill with several scripts, the other scripts import the library's names from that shared module, so they don't depend on the order of their imports.

## The template

[config-template.json](skills/agentic-manager-utils-lib/agentic_manager/config-template.json), in the library, is the only definition of what's supported: every group, and every source with its settings. A source is named `<tool>-<channel>`, such as `jira-api`. The groups sit inside a `sources` object, so the config can hold settings that aren't sources, such as `output.root`, the folder skills write to.

A user's config may only contain what the template lists, but it may leave things out: a missing group or source counts as disabled, and a missing output setting as not set. So existing configs keep working when the template gains new sources or settings, and a skill works before the user has chosen an output folder.

### Adding a source or a group

- Add the source to [config-template.json](skills/agentic-manager-utils-lib/agentic_manager/config-template.json) under its group in `sources`, named `<tool>-<channel>` (channel `mcp`, `cli`, `api` or `fs`), with `"enabled": false`.
- Give each text setting a placeholder in angle brackets, such as `"<token>"`: the config check (see [Prerequisite, sources and permissions](#prerequisite-sources-and-permissions)) reports a placeholder as not filled in when the source is enabled. Give an optional list setting an empty list, `[]`.
- For a new group, also add it to the groups table in the library's [SKILL.md](skills/agentic-manager-utils-lib/SKILL.md#config-sources), and for a new channel, to its channels table. Tests check that both match the template.

## Where AI is used

AI-written content goes only where it needs judgment: it costs tokens, and it can come out differently on every run. Judgment is research, conclusions and prose; anything deterministic belongs in a script: fetching, arithmetic, classification by fixed rules, charts, fixed templates and formats, headings, table structure, links and anchors, file layout, diagram mechanics and checks.

So when a skill's output has numbers that must be right every time, such as a report, or a fixed template, scripts own everything mechanical, and the agent writes only the judgment text, in a small JSON file the generator reads. A checker script then validates the finished output against the data: prose rules alone don't stop a table drifting when it is edited by hand; a check that fails does. Scripts also prepare what the agent reads: a brief holding only the material for its parts, so it never joins raw files itself, and one command each to run the pipeline before and after its writing. The skill's instructions then cover only the judgment.

### Model, views and checker

Skills that split the work this way follow a model-view approach, with the checker as a separate witness:

- **Model.** One script works out every fact the output needs, once, from the raw data, and stores it in a data file such as `data.json`: the basic records, such as events, and every fact derived from them, such as outcomes, flags and totals. A derived fact is computed there and nowhere else, including a fact that is a simple condition on events.
- **Views.** Everything that renders (tables, charts, commentary, a brief for the agent) reads the stored facts and never derives them again. When a view needs a fact the model doesn't hold, add it to the model, so every view agrees by construction.
- **Checker.** The checker recomputes figures from the model's most basic data (the events) independently of the views, and checks the stored derived facts against them, so a bug in the model can't pass by agreeing with itself. This is the one deliberate duplication.
- **Tests** follow the same split: the model's logic is tested on its own, with one table of cases; a view is tested against a model fixture, not by re-deriving the model's facts.

## Writing a skill

### The shape of a skill

Every skill other than a utility starts with the prerequisite, step 1. A skill that produces a document then follows the rest of these steps. Each script step is one command, pre-approved in the frontmatter.

1. **Prerequisite:** run the library's `check_config.py` and state the sources the skill needs (see [Prerequisite, sources and permissions](#prerequisite-sources-and-permissions)).
2. **Gather:** collect what the document is built from.
   - When it is a fetch of known data, one script does it, builds everything deterministic and writes a brief holding only what the agent needs. It prints one line of JSON on stdout (the paths the next step needs) and progress on stderr; on failure it exits non-zero with a message that says what to do.
   - When it is research, the agent does it and keeps its working notes in files, such as a ledger of sources and findings, written through `output_file.py` or a script of the skill that writes through the library. Scripts own what is mechanical about them: the folder, the skeleton, the allowed values and the structure check. They also answer the agent's lookups and print a brief of the notes for writing the document, so the agent doesn't read a notes file whole to research or write.
3. **Write:** the agent produces only the parts that need judgment, as a JSON file written through `output_file.py`. The skill gives its schema, the rules for each part and their limits.
4. **Finish:** a script validates the agent's text field by field before generating anything, with errors that name the field to fix. Then it generates the document and runs its checker, printing only what needs action.
5. **Tell the user** it's ready, with a link. Don't recap what the document shows; add only a doubt about your own judgment that it doesn't show.

Re-running a step regenerates its output. To change the document, edit the JSON and run Finish again; never edit generated files.

### Rules for skills

What a skill's instructions and scripts must do, on top of the rules that always apply.

#### Naming

- Put it in `skills/agentic-manager-<name>/SKILL.md`. The folder name and the frontmatter `name` must match. Name a skill after what it produces, not what it is, such as `agentic-manager-weekly-summary`, and name its output folder after the same thing in the plural, such as `weekly-summaries`, so a user finds a skill's files by its name.
- Add a new skill to every file that lists all the skills.

#### Prerequisite, sources and permissions

- Unless it's a utility, start the instructions with the prerequisite: run the library's `agentic_manager/check_config.py`. The check only validates the config: it fails if the config is missing or malformed, and otherwise returns every supported source by [group](skills/agentic-manager-utils-lib/SKILL.md#config-sources), saying whether each is enabled and, if not, how to enable it. On a failure, or after creating the config, it also prints `next_steps`, which the agent follows, so skills don't repeat them. The check doesn't know what the skill needs, so the skill names it: any enabled source of a group, such as `workflow`, when it can work with whatever tool a team uses, or a specific source, such as `jira-api`, when its steps only work with one tool. It also says what it does if they aren't enabled (usually stop and show their `setup`):

  ```markdown
  ## Prerequisite

  Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

  This skill needs any enabled source of `workflow`, and the `github-cli` source. If one is missing, stop and tell the user how to enable it, showing its `setup` and the config `path`.
  ```

- If the skill runs its own scripts, pre-approve them in the frontmatter so Claude Code doesn't ask permission for each step, and tell the agent to call them by that same path: `allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py *)`, one per script, separated by spaces. Never pre-approve a command that changes the user's config or anything outside the skill's own output; without the ` *`, a rule approves only the command with no arguments, as `check_config.py`'s does, so its `--init` still asks.
- Reach each enabled source's tool through its channel (`mcp`, `cli`, `api` or `fs`). Never hard-code a tool, URL or credential: the user's config decides what is available.
- A program a script runs on the user's machine, such as a browser that pictures pages, is a dependency, not a source, and so are the agent's own tools, such as web search: neither has a config entry. The skill says what it does without them, and the README lists them.
- Reach an `api` or `fs` source through a script that reads its settings with `agentic_manager.config.read_source()`, since the agent never reads them, and never pass a setting to a script on its command line. An `mcp` or `cli` source needs no settings, so the agent uses it directly.

#### Scripts

- Scripts use only the Python standard library and need Python 3.14+: skills have no install step, so nothing else can be relied on (a chart is drawn as SVG by hand). A tool outside Python is the exception, and the skill lists it as a dependency with its version pinned, or, for one that updates itself, such as a browser, the version it was tested with.
- Every module starts with a header comment whose first sentence says what it is for, followed by the reasons for its rules: the decisions that justify the code, in a few lines, not what the code already says. Describe what the script does, not who calls it or how: a list of its callers goes stale whenever one changes.
- A module reads top-down, so an agent meets what it does before the details: its header comment, imports and constants, then its functions and classes, each below the first one that uses it, grouped by what they serve, and `main` last. A function that module-level code calls goes above that code, as Python needs.
- Every function or class other code may use has a docstring whose first sentence says what it is for: in the library, and in a skill's module without a `main`, every public one (top level, no leading underscore); in a skill's command, only those its other scripts import from it. The library's `code_map.py` builds the map of the code from these first sentences, and `tests/repo/` fails when one is missing. The map is for whoever builds a skill, so no SKILL.md asks the agent running it to read it.
- Every script answers `--help` with what it does, its commands and what each argument is for. A SKILL.md spells out its mechanical steps, but a step it leaves to the agent's judgment can need a script or a command it doesn't name, so every SKILL.md that runs scripts says once, where it introduces them, that a script's `--help` gives its commands and arguments.
- A script the agent feeds structured input, such as a JSON object or a row's cells, shows in its `help`, for every command that writes, the input's shape and a command to copy, with the input in a quoted here-document so nothing in it needs escaping; its error for a wrong input shows the same. The agent then never guesses a field's name or fights shell quoting.
- A SKILL.md doesn't repeat what a script tells the agent when it needs it, in its `help`, its errors or its output, such as a table's columns and allowed values, a command's arguments or the shape of its result. It says when to run each script, by its full pre-approved path, and keeps only judgment and what the agent needs before its first call, such as the shape of a file it writes from scratch and a value the script accepts without checking.
- When a tool result is too large and saved to a file, the agent lists what it needs from it with the library's `agentic_manager/extract_saved.py`, never by reading it whole or writing code to pick it apart; pre-approve it in the frontmatter of a skill that may meet one.
- When you move work from a skill's instructions into a script (see [Where AI is used](#where-ai-is-used)), the output must stay the same and keep its quality: compare the script's output with what the skill produced before.

#### Output folder, reruns and examples

- A skill that writes files gets its output folder from the library's `agentic_manager/output_folder.py`, never from code of its own: a script imports its `output_folder()`. When the agent writes a skill's files itself, it writes every file through the library's `agentic_manager/output_file.py`, never with its own file tools; pre-approve it in the frontmatter: `Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *)`. State near the top of the skill's instructions that its files go to the user's configured output root, or to a temporary folder if none is set.
- A skill that writes files declares the closed set of files its output folder holds, in three places that agree: an `expected_files` function in its `common.py`, a file tree in its SKILL.md, drawn from the skill's output folder down so it also shows the shared `_` folders beside the runs, and its final check, which fails on any other file (names starting with a dot, such as `.DS_Store`, are ignored). The agent's working files go in its own scratch folder, never the output folder. The agent writes only the files its SKILL.md names; scripts write the rest. A set can depend on the run, such as optional outputs the user asked for, and the function then takes what it depends on. When a skill's files change, update the function, the tree, the check and their tests together.
- Running a skill again for the same subject on the same day starts from scratch. A skill that keeps a folder per subject names it after the subject and the day, and before it starts deletes only the folder it would build over, the one of the same subject and day; earlier days' folders stay, since they can't clash with the new one. A skill never reads what an earlier run left either, on the same day or an earlier one: it fetches or reads every source again, so a document is always built from fresh data and research, and nothing in the folder is hand-kept. A rerun replaces the earlier folder without a warning or a confirmation: the skill's instructions don't ask the agent to tell the user first.
- A folder of the user's own material that a skill keeps beside its runs, its name starting with `_`, such as approved examples or the user's images, isn't a run's leftovers: every run may read it, and no run deletes it.
- A skill whose output can serve as an example for later runs offers, at its handover, to keep it, and keeps it when the user says they're happy with it, within the same conversation. An example is a folder of its own, holding its files and a `description.md` that says what it is and why it was kept, and a script of the skill lists the examples for the agent, reading each folder's `description.md`, so adding or deleting an example is adding or deleting its folder.

#### Checks and AI-written text

- A rule the final check applies is also applied when the data is written, wherever the script that writes it can: one function in the skill's shared module, called by both, so the two can't differ. The final check keeps it, since a file can be written without the script. A record that cites another must cite one that exists: the script checks once every record of the write is written, so records that cite each other are written together, and nothing ever points at a record that isn't there.
- When changing a report rule, update its generator, checker and relevant tests together.
- A length given for AI-written text is room to articulate, never a quota. State it as an approximate target or an "at most", tell the agent to write fewer words when the point is simple or the evidence thin, and have a check flag only excess or a stub (far below the target, such as under a third), never brevity. A check that pushes the agent up to a minimum produces padding.
- A SKILL.md runs in the order the agent works: the prerequisite, then the steps as they run, with reference material, such as rules and schemas, after the steps or where it is first needed. Sections every SKILL.md has come in the same order in each.
- State each rule once in the SKILL.md, where it belongs: a second sentence repeating it, or an exception to it elsewhere, is where the two drift apart. Prefer the simplest rule: reuse an existing cell, field or file before adding a column, a state or a marker.
- Don't add guardrails for improbable cases, such as an agent writing fields from an older version of the skill: deal with them if they happen. A skill always assumes it runs from a clean state.

## Testing

```bash
python3 tests/run.py                   # every skill; add -v to list each test
python3 tests/run.py <skill> ...       # only those skills
```

- Prove a change to a skill's logic with tests written for it, never by re-checking an output generated before the change, and never edit such an output to make it pass: it was built under the old rules and validates nothing.
- When the developer gives a reference output to match, it is the specification: change the skill until it produces what the reference has, without asking about each difference. Ask only when the reference is ambiguous or conflicts with a rule they stated, and then ask all the questions together.
- After changing a skill, run its tests; after changing the library, run every skill's tests, since they all use it.
- Run the tests with Python 3.14+. `python3` on a machine can be an older one, and then the tests fail to import, for example with `unsupported operand type(s) for |`.
- Skill names contain hyphens, so `python3 -m unittest discover` doesn't find the tests; use `run.py`. It runs each skill's tests in their own Python process, so modules with the same name in different skills don't clash.
- Every script or module gets unit tests in `tests/<skill>/test_<module>.py`, calling its functions directly. The shared library is a skill too: its tests go in `tests/agentic-manager-utils-lib/`.
- Tests that run a whole script, or several in a row, are end-to-end tests: name them `test_e2e_<what>.py`. Add them where a script's command line or output is a contract, or where scripts must fit together.
- Write cases that check the same thing the same way as one test over a table of cases, each in a `subTest`, rather than one test per case.
- Put data shared by several test files in a module not named `test_*`, such as `shared_fixture.py`.
- Run scripts with `HOME` pointed at a temporary folder holding the test's own config, and `TMPDIR` too when a script may fall back to the system temp folder, as the existing tests do.
- When you add a skill with scripts, add its test folder to `executionEnvironments` in `pyrightconfig.json`, with the skill's `scripts` folder in `extraPaths`, so editors resolve the tests' imports.

## Formatting

Python files are formatted with autopep8 and Markdown and JSON files with Prettier, both with their default settings, as the editor's Format Document does. Format the files you change. If the formatters aren't installed, run the copies bundled in the editor's extensions.

## Committing

Commit and push only when the developer asks, on the branch that is checked out, even if it is the default branch; create a branch or a pull request only when they ask for one.

A developer may keep rules for their own machine, such as how to commit, in an `AGENTS.local.md` at the repo root; it is gitignored. When it exists, follow it as well as this file.
