# AGENTS.md

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
tests/run.py             runs every skill's tests, each skill in its own process (its own
                         tests are in tests/runner/)
.claude/skills  ─┐       symlinks to skills/, so the skills load when you run
.agents/skills  ─┘       Claude Code or Codex inside this repo
```

The symlinks let you use the skills while you build them. Edits to a skill apply to the next agent session; a running session keeps the instructions it already loaded. If the skills are also installed globally (`~/.claude/skills`, `~/.agents/skills`), a session here may load the installed copy instead of the one you're editing, so a change you test may not be the one that runs.

## Rules that always apply

- **Never change the developer's config.** The one exception is creating it when it's missing: you may ask whether to create it from the template, and only if the developer explicitly approves, create it with `check_config.py --init`. For any other problem, tell the developer how to fix it and never make the change yourself.
- **Keep the developer's config out of the repo.** Skills run here read the developer's config (`~/.config/agentic-manager/config.json`), as they do anywhere else, but nothing from it may end up in the repo: not in tests, examples or code, and not as assumptions about which sources are enabled.
- **Never read or display secrets.** Settings in the user's config can hold secrets, such as tokens, and anything the agent reads can end up in the chat. Never read the config file directly: use a script or a helper from the library (see [Utilities](#utilities)), and never write a script or helper that prints settings from the config. Never display a secret in the chat, in output or in files; refer to a setting by name instead, for example "using your `api-token`".
- **Never put secrets or internal data in this repo.** Skills are often based on real work cases. Keep real names, ticket numbers, project keys, URLs, channel names, messages, documents and credentials out of skills, examples, tests and commit messages; use made-up examples such as `PROJ-123` or `acme`. Anything specific to a team belongs in the user's config, as a setting. Before committing, check the diff for anything that came from a real case.
- **Never change the developer's installed skills** (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`).
- **Never run `npx skills` from inside this repo.** The `skills` CLI has a bug: `remove -g` also deletes `<current folder>/.agents/skills/<skill>`, and here that's a symlink to `skills/`, so it deletes the skill's source. Run it from another folder.

## The template

[config-template.json](skills/agentic-manager-utils-lib/agentic_manager/config-template.json), in the [library](#utilities), is the only definition of what's supported: every group, and every source with its settings. A source is named `<tool>-<channel>`, such as `jira-api`. The groups sit inside a `sources` object, so the config can hold settings that aren't sources, such as `output.root`, the folder skills write to.

A user's config may only contain what the template lists, but it may leave things out: a missing group or source counts as disabled, and a missing output setting as not set. So existing configs keep working when the template gains new sources or settings, and a skill works before the user has chosen an output folder.

### Adding a source or a group

- Add the source to [config-template.json](skills/agentic-manager-utils-lib/agentic_manager/config-template.json) under its group in `sources`, named `<tool>-<channel>` (channel `mcp`, `cli`, `api` or `fs`), with `"enabled": false`.
- Give each setting a placeholder in angle brackets, such as `"<token>"`. The config check (see [Writing a skill](#the-rules)) reports a placeholder as not filled in when the source is enabled.
- For a new group, also add it to the groups table in the library's [SKILL.md](skills/agentic-manager-utils-lib/SKILL.md#config-sources), and for a new channel, to its channels table. Tests check that both match the template.

## Utilities

Skills named `agentic-manager-utils-*` are utilities: they're used by other skills, not invoked by the user. At the moment there is one: `agentic-manager-utils-lib`, exposing the `agentic_manager` Python package under `skills/agentic-manager-utils-lib/agentic_manager/`, with the helpers shared by all the skills.

Skills must use the library: shared code goes in it and is used from there, never reimplemented or copied into a skill. Keep in the library only what any skill using the same tool or the config would need, such as the Jira client and helpers for Jira keys and timestamps. Choices that belong to one skill, such as which issue fields it fetches, stay in that skill.

`npx skills` installs each skill as its own folder, side by side, with no shared folder and no install step, so a script finds the library next to its own skill's folder, and the agent runs its modules by the same path. This relies on all the skills being installed together, which a normal install does; if the library is missing, a skill's prerequisite tells the user to reinstall every skill.

To use it from a script:

- Add the library to the path before importing, as sprint-report's `common.py` does:

  ```python
  LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         "..", "..", "agentic-manager-utils-lib")
  sys.path.insert(0, LIB_DIR)
  from agentic_manager import config
  ```

- Use `realpath`, not `abspath`: Claude Code installs skills as symlinks to `~/.agents/skills`.
- In a skill with several scripts, do this once in the skill's shared module and import the library's names from there. The scripts then don't depend on the order of their imports.

Before creating a skill or working on an existing one, read the library's modules, starting from the list in its [SKILL.md](skills/agentic-manager-utils-lib/SKILL.md), so you know what is already there and how to use it. Each module's header comment says what it does, how to call it and why it works that way.

## Where AI is used

AI-written content goes only where it needs judgment: it costs tokens, and it can come out differently on every run. Judgment is research, conclusions and prose; anything deterministic belongs in a script: fetching, arithmetic, classification by fixed rules, charts, fixed templates and formats, headings, table structure, links and anchors, file layout, diagram mechanics and checks. So when a skill's output has numbers that must be right every time, such as a report, or a fixed template, scripts own everything mechanical, and the agent writes only the judgment text, in a small JSON file the generator reads and never by editing the generated output. A checker script then validates the finished output against the data. Scripts also prepare what the agent reads: a brief holding only the material for its parts, so it never joins raw files itself, and one command each to run the pipeline before and after its writing. The skill's instructions then cover only the judgment; the reasons behind the scripts' rules live in their header comments, next to the code they justify. Prose rules alone don't stop a table drifting when it is edited by hand; a check that fails does.

### Model, views and checker

Skills that split the work this way follow a model-view approach, with the checker as a separate witness:

- **Model.** One script works out every fact the output needs, once, from the raw data, and stores it in a data file such as `data.json`: events, outcomes, flags (reopened, came back, done at start), totals, blocker candidates. A derived fact is computed there and nowhere else, including a fact that is a simple condition on events.
- **Views.** Everything that renders (tables, charts, timeline, burndown, commentary, a brief for the agent) reads the stored facts and never derives them again. When a view needs a fact the model doesn't hold, add it to the model, so every view agrees by construction.
- **Checker.** The checker recomputes figures from the model's most basic data (the events) independently of the views, and checks the stored derived facts against them, so a bug in the model can't pass by agreeing with itself. This is the one deliberate duplication.
- **Tests** follow the same split: the model's logic is tested on its own, with one table of cases; a view is tested against a model fixture, not by re-deriving the model's facts.

## Writing a skill

### The shape of a skill

Every skill other than a utility starts with the prerequisite, step 1. A skill that produces a document then follows the rest of these steps. Each script step is one command, pre-approved in the frontmatter.

1. **Prerequisite:** run the library's `check_config.py` and state the sources the skill needs (see the prerequisite in [The rules](#the-rules)).
2. **Gather:** collect what the document is built from.
   - When it is a fetch of known data, as for a sprint report, one script does it, builds everything deterministic and writes a brief holding only what the agent needs. It prints one line of JSON on stdout (the paths the next step needs) and progress on stderr; on failure it exits non-zero with a message that says what to do.
   - When it is research, as for a tech investigation, the agent does it and keeps its working notes in files, such as the ledger, written through `output_file.py`. Scripts own what is mechanical about them: the folder, the skeleton and the structure check.
3. **Write:** the agent produces only the parts that need judgment, as a JSON file written through `output_file.py`. The skill gives its schema, the rules for each part and their limits.
4. **Finish:** a script validates the agent's text field by field before generating anything, with errors that name the field to fix. Then it generates the document and runs its checker, which also fails on any file outside the skill's declared set, printing only what needs action.
5. **Tell the user** it's ready, with a link.

Re-running a step regenerates its output. To change the document, edit the JSON and run Finish again; never edit generated files.

### The rules

- Put it in `skills/agentic-manager-<name>/SKILL.md`. The folder name and the frontmatter `name` must match.
- Add a new skill to every file that lists all the skills.
- Unless it's a utility (`agentic-manager-utils-*`), start the instructions with the prerequisite: run the library's `agentic_manager/check_config.py`. The check only validates the config: it fails if the config is missing or malformed, and otherwise returns every supported source by [group](skills/agentic-manager-utils-lib/SKILL.md#config-sources), saying whether each is enabled and, if not, how to enable it. On a failure, or after creating the config, it also prints `next_steps`, which the agent follows, so skills don't repeat them. The check doesn't know what the skill needs, so the skill names it: any enabled source of a group, such as `workflow`, when it can work with whatever tool a team uses, or a specific source, such as `jira-api`, when its steps only work with one tool. It also says what it does if they aren't enabled (usually stop and show their `setup`):

  ```markdown
  ## Prerequisite

  Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`.

  This skill needs any enabled source of `workflow`, and the `github-cli` source. If one is missing, stop and tell the user how to enable it, showing its `setup` and the config `path`.
  ```

- If the skill runs its own scripts, pre-approve them in the frontmatter so Claude Code doesn't ask permission for each step, and tell the agent to call them by that same path: `allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py *)`, one per script, separated by spaces. Never pre-approve a command that changes the user's config or anything outside the skill's own output; without the ` *`, a rule approves only the command with no arguments, as `check_config.py`'s does, so its `--init` still asks.
- Scripts use only the Python standard library and need Python 3.14+: skills have no install step, so nothing else can be relied on (charts are drawn as SVG by hand). A tool outside Python is the exception, and the skill lists it as a dependency, as the tech investigation does with the pinned Mermaid CLI it runs through `npx`.
- Reach each enabled source's tool through its channel (`mcp`, `cli`, `api` or `fs`). Never hard-code a tool, URL or credential: the user's config decides what is available.
- Reach an `api` or `fs` source through a script that reads its settings with `agentic_manager.config.read_source()`: the check never returns setting values, and the agent never reads the config (see [Rules that always apply](#rules-that-always-apply)). An `mcp` or `cli` source needs no settings, so the agent uses it directly, as the tech investigation does. Never read the config from the skill's instructions, and never pass a setting to a script on its command line.
- A skill that writes files gets its output folder from the library's `agentic_manager/output_folder.py`, never from code of its own: a script imports its `output_folder()`, as the sprint report's `fetch_sprint.py` does. When the agent writes a skill's files itself, it writes every file through the library's `agentic_manager/output_file.py`, never with its own file tools, as the tech investigation does; pre-approve it in the frontmatter: `Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *)`. State near the top of the skill's instructions that its files go to the user's configured output root, or to a temporary folder if none is set.
- A skill that writes files declares the closed set of files its output folder holds, in three places that agree: an `expected_files` function in its `common.py`, a file tree in its SKILL.md, and its final check, which fails on any other file (names starting with a dot, such as `.DS_Store`, are ignored). The agent's working files go in its own scratch folder, never the output folder. The agent writes only the files its SKILL.md names; scripts write the rest. A set can depend on the run, such as the short outputs asked for, and the function then takes what it depends on. When a skill's files change, update the function, the tree, the check and their tests together.
- Running a skill again for the same subject starts from scratch. A skill that keeps its files in a folder per subject deletes the earlier folders it would build over before it starts: the sprint report's `fetch_sprint.py` every earlier report of the same sprint, the tech investigation's `init_investigation.py` the folder of the same topic and day, leaving earlier days'. So a document is always built from fresh data and research, never from the leftovers of an earlier run, and nothing in the folder is hand-kept. A skill never reads what an earlier run left either, whether that run was on the same day or an earlier one, so it fetches or reads every source again. The skill's instructions tell the agent to warn the user before running over an existing folder.
- A length given for AI-written text is room to articulate, never a quota. State it as an approximate target or an "at most", tell the agent to write fewer words when the point is simple or the evidence thin, and have a check flag only excess or a stub (far below the target, such as under a third), never brevity. A check that pushes the agent up to a minimum produces padding.
- When you move work from a skill's instructions into a script (see [Where AI is used](#where-ai-is-used)), the output must stay the same and keep its quality: compare the script's output with what the skill produced before.
- Put the reasons for a script's rules in its header comment: the decisions that justify the code, in a few lines, not what the code already says. Describe what the script does, not who calls it or how: a list of its callers goes stale whenever one changes.
- A skill that produces a report ends by saying it's ready, with a link to it. Don't recap what the report shows; add only a doubt about your own judgment that the report doesn't show.
- When changing a report rule, update its generator, checker and relevant tests together.
- Don't add guardrails for improbable cases, such as an agent writing fields from an older version of the skill: deal with them if they happen. A skill always assumes it runs from a clean state.

## Testing

```bash
python3 tests/run.py                   # every skill; add -v to list each test
python3 tests/run.py <skill> ...       # only those skills
```

- After changing a skill, run its tests; after changing the library, run every skill's tests, since they all use it.
- Run the tests with Python 3.14+, which the repo requires. `python3` on a machine can be an older one, and then the tests fail to import, for example with `unsupported operand type(s) for |`.
- Every script or module gets unit tests in `tests/<skill>/test_<module>.py`, calling its functions directly. The shared library is a skill too: its tests go in `tests/agentic-manager-utils-lib/`.
- Tests that run a whole script, or several in a row, are end-to-end tests: name them `test_e2e_<what>.py`. Add them where a script's command line or output is a contract, or where scripts must fit together.
- Put data shared by several test files in a module not named `test_*`, such as `sprint_fixture.py`.
- Skill names contain hyphens, so `python3 -m unittest discover` doesn't find the tests; use `run.py`. It runs each skill's tests in their own Python process, so modules with the same name in different skills don't clash.
- Run scripts with `HOME` pointed at a temporary folder holding the test's own config, and `TMPDIR` too when a script may fall back to the system temp folder, as the existing tests do.
- Write cases that check the same thing the same way as one test over a table of cases, each in a `subTest`, rather than one test per case.
- When you add a skill with scripts, add its test folder to `executionEnvironments` in `pyrightconfig.json`, with the skill's `scripts` folder in `extraPaths`, so editors resolve the tests' imports.

## Formatting

Python files are formatted with autopep8 and Markdown and JSON files with Prettier, both with their default settings, as the editor's Format Document does. Format the files you change. If the formatters aren't installed, run the copies bundled in the editor's extensions.
