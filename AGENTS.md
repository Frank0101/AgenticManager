# AGENTS.md

How this repo works, for you: its layout, the rules to follow and the design choices behind them. [README.md](README.md) is the only other document, and it is for the user (installing, configuring and using the skills): keep user-facing content there and everything about working on the repo here.

## Layout

```text
skills/<skill>/          one folder per skill
  SKILL.md               instructions the agent follows
  scripts/               optional helper scripts
skills/agentic-manager-utils-lib/
  agentic_manager/       Python package shared by the other skills: their scripts import it,
                         and the agent runs some of its modules
tests/<skill>/           tests for that skill, mirroring skills/: unit tests per script or
                         module (test_<module>.py) and end-to-end tests (test_e2e_*.py)
tests/run.py             runs every skill's tests, each skill in its own process (its own
                         tests are in tests/runner/)
.claude/skills  ─┐       symlinks to skills/, so the skills load when you run
.agents/skills  ─┘       Claude Code or Codex inside this repo
```

The symlinks let you use the skills while you build them. Edits to a skill apply to the next agent session; a running session keeps the instructions it already loaded.

## Rules that always apply

- **Never change the developer's config without their approval, and keep it out of the repo.** Skills run here read the developer's config (`~/.config/agentic-manager/config.json`), as they do anywhere else. If it's missing, you may ask whether to create it from the template. For any other problem, show how to fix it; you may ask whether to make the change. Change the file only after the developer explicitly approves. Nothing from their config may end up in the repo: not in tests, examples or code, and not as assumptions about which sources are enabled.
- **Never change the developer's installed skills** (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`).
- **Never run `npx skills` from inside this repo.** The `skills` CLI has a bug: `remove -g` also deletes `<current folder>/.agents/skills/<skill>`, and here that's a symlink to `skills/`, so it deletes the skill's source. Adding `--agent` to the README's uninstall command doesn't work around it: the CLI then keeps the shared `~/.agents/skills` copy whenever another installed agent uses that folder. Run it from another folder.
- **Never display secrets**, such as tokens from the user's config, in the chat, in output or in files. Skills must refer to a setting by name instead, for example "using your `api-token`".
- **Never put secrets or internal data in this repo.** Skills are often based on real work cases. Keep real names, ticket numbers, project keys, URLs, channel names, messages, documents and credentials out of skills, examples, tests and commit messages; use made-up examples such as `PROJ-123` or `acme`. Anything specific to a team belongs in the user's config, as a setting. Before committing, check the diff for anything that came from a real case.

## Skills and the config

Every skill starts by running `agentic-manager-utils-check-config`, except the [utilities](#utilities). The check only validates the config: it fails if the config is missing or malformed, and otherwise returns every supported source by [group](skills/agentic-manager-utils-check-config/SKILL.md#groups), saying whether each is enabled and, if not, how to enable it. It doesn't know what the calling skill needs.

Each skill decides what it needs from that result. A skill that can work with whatever tool a team uses asks for any enabled source of a group, such as `workflow`, and reaches it through its channel: MCP, a CLI, an API or files on disk. A skill whose steps only work with one tool, such as a script that calls Jira's API, asks for that source, such as `jira-api`. Either way, the user's config decides what is available, and nothing about a team's tools or credentials lives in this repo.

The check never returns setting values. Settings can hold secrets, such as tokens, and anything the check prints reaches the agent and can end up in the chat. So the check only confirms that every setting of an enabled source is filled in, and a script that needs a setting reads it from the config itself. This is why an `api` or `fs` source is always reached through a script, while `mcp` and `cli` sources are reached by the agent directly, as the tech investigation does.

For the same reason, the agent never reads the output root from the config. Every skill gets its output folder from the library's `output_folder.py`, which reads only `output.root`: a skill's scripts import it, and the agent runs it when it writes a skill's files itself. Those files then go through the library's `output_file.py`, which refuses any path outside the skill's output folder. That makes it safe to pre-approve, as a skill's own scripts are, whereas the agent's file tools would need either a prompt for every write or an approval to write anywhere, the config included.

The output writer also supports exact text patches within the same folder boundary. Each replacement's `old` text must be nonempty and match exactly once; the entire batch is validated before the file is written. This avoids resending long files for small edits while refusing ambiguous or stale context. Concurrent edits can invalidate the expected text, so the writer rejects conflicting patches rather than merging them.

## The template

[config-template.json](skills/agentic-manager-utils-check-config/config-template.json) is the only definition of what's supported: every group, and every source with its settings. A source is named `<tool>-<channel>`, such as `jira-api`. The groups sit inside a `sources` object, so the config can hold settings that aren't sources, such as `output.root`, the folder skills write to.

A user's config may only contain what the template lists, but it may leave things out: a missing group or source counts as disabled, and a missing output setting as not set. So existing configs keep working when the template gains new sources or settings, and a skill works before the user has chosen an output folder.

## Utilities

Skills named `agentic-manager-utils-*` are utilities: they're used by other skills, not by the people who install the skills, so the README doesn't mention them.

| Skill                                                                           | Purpose                                                                                          |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [agentic-manager-utils-check-config](skills/agentic-manager-utils-check-config) | Validates the user's config and returns every source, enabled or not, without setting values.    |
| [agentic-manager-utils-lib](skills/agentic-manager-utils-lib)                   | Code shared by the other skills, such as reading the config, the Jira client and writing output. |

## Sharing code between skills

`npx skills` installs each skill as its own folder, side by side, with no shared folder and no install step. So code that more than one skill needs lives in a skill of its own, `agentic-manager-utils-lib`, as the `agentic_manager` Python package in `skills/agentic-manager-utils-lib/agentic_manager/`, not in a copy per skill. A script finds it next to its own skill's folder, and the agent runs its modules by the same path.

This relies on all the skills being installed together, which the README's install command does. Every skill already depends on check-config the same way. If the library is missing, check-config fails and tells the user to reinstall every skill.

- In a script that uses it, add the library to the path before importing, as `check_config.py` does:

  ```python
  LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         "..", "..", "agentic-manager-utils-lib")
  sys.path.insert(0, LIB_DIR)
  from agentic_manager import config
  ```

- Use `realpath`, not `abspath`: Claude Code installs skills as symlinks to `~/.agents/skills`.
- In a skill with several scripts, do this once in the skill's shared module and import the library's names from there, as sprint-report's `common.py` does. The scripts then don't depend on the order of their imports.
- Keep in the library only what any skill using the same tool or the config would need, such as the Jira client and helpers for Jira keys and timestamps. Choices that belong to one skill, such as which issue fields it fetches, stay in that skill.

## Script-owned skills

AI-written content goes only where it needs judgment: it costs tokens, and it can come out differently on every run. So when a skill's output has numbers that must be right every time, such as the sprint report, or a fixed template, scripts own everything mechanical: fetching, classification, arithmetic, charts, formatting. The agent writes only the judgment text, in a small JSON file the generator reads. A checker script then validates the finished output against the data. Scripts also prepare what the agent reads: a brief holding only the material for its parts, so it never joins raw files itself, and one command each to run the pipeline before and after its writing. The skill's instructions then cover only the judgment; the reasons behind the scripts' rules live in their header comments, next to the code they justify. Prose rules alone don't stop a table drifting when it is edited by hand; a check that fails does.

Such skills use only the Python standard library (charts are drawn as SVG by hand), so they need Python 3.14+ and, for timezone conversion, IANA timezone data from the system or the `tzdata` package.

### The sprint report

The agent writes only the goal verdict, each epic's commentary, Key Achievements, Blockers & Risks and the retro notes, each marked with a small `[AI Gen.]` label. The timeline's commentary is generated, not written: what departed from the ideal sprint is a fact of the data. The rules for figures, formats and wording, and the reasons for them, are in the scripts' header comments: `build_sprint_data.py` (the model of a ticket's time in the sprint), `common.py` (the vocabulary and formats), `make_report.py` (the report's layout) and `make_charts.py` (the charts).

Sprint dates and daily boundaries use `zoneinfo` with the API account's named timezone, saved from Jira's current-user profile in the fetch metadata. This keeps timeline dates and burndown boundaries consistent across daylight-saving changes. A missing or unavailable timezone stops the report rather than guessing a fixed offset.

A report on a past period must give the same figures whenever it is run. Jira's issue fields hold their state today, so the scripts rebuild every field that matters to a figure from the issue's changelog, as it was at the moment the report describes, and never read the current value unless the changelog shows it held then too.

### Investigation reports

Investigation ledgers keep a compact resume block followed by one research action queue, grouped into ready/in progress, blocked and completed actions. Findings own the evidence explanations; inventories and reviews reference stable IDs. File-level reading depth prevents discovery searches from being mistaken for full validation. One report evolves throughout research, with concise corrections retained instead of duplicate draft snapshots.

The tech investigation is script-owned too, although nearly all its text needs judgment: the research, the ledger, what the maps show and the report's prose stay with the agent, and scripts own the rest. `make_report.py` writes the report's fixed template from `content.json`, resolving ledger IDs to anchors, and `build_maps.py` draws all three stages' maps from one `maps.json`, so each stage has the same nodes and connections and the change colours come from comparing stages rather than from the agent. Both check what an instruction alone wouldn't hold: sequences against their stage's map, steps the commentary names, component positions across stages, components leaving the outline unexplained. A report may skip the architect layer or the evolution sections when the finished research shows they don't apply, with the reason recorded in the ledger; `check_report.py` reads the same choice from `content.json`, so the structure check stays exact. Short outputs, such as an exec summary, take whatever shape the question needs, so `make_summary.py` fixes only their frame: the file, the link to the full report and the word limit the user asked for. The ledger stays Markdown the agent edits, since it is reasoned over during the research; `init_investigation.py` writes its skeleton and `check_report.py` checks its structure.

### The architecture map

Investigation diagrams explain the approach rather than reproduce the implementation inventory. The maps retain concrete services, stores, hosting and material interfaces; internal details can be grouped where they do not affect those relationships. Fixed component positions support stage comparison, while scope outlines, changed connections and explicit lifecycle labels show evolution. The current stage is evidence; the next and target stages reconstruct a design no code shows yet, so a component whose responsibility that design gives to another is shown replaced, greyed without the cross that a sourced decommissioning gets. The ledger retains the mapping and evidence. Visual inspection complements syntax and geometry checks. A read-only report checker catches fixed-structure, local-artifact, table-citation and diagram-order errors. It complements source review and actual diagram rendering; passing it is not evidence that a claim or proposed interaction is true.

The tech investigation's map is the one output drawn by a tool outside Python: viewers draw Mermaid with their own versions and settings, so the skill's `output_diagram.py` renders it once with the Mermaid CLI, pinned to one version and run through `npx`, and `build_maps.py` checks every connection line against the map's rules before writing the SVGs. Rendering several diagrams, the three maps or every sequence, takes one Mermaid CLI run, through a Markdown file of their blocks, since each run starts a browser. A check that fails stops a bad layout, where an instruction to the agent alone wouldn't. Node.js is required, with no fallback to an unrendered map, because a diagram nobody has drawn can't be known to draw: `init_investigation.py` asks for it before any research starts. `output_diagram.py` lives in the skill, not the library, until another skill needs it.

## Writing a skill

### The shape of a skill

A skill that produces a document follows these steps. Each script step is one command, pre-approved in the frontmatter.

1. **Prerequisite:** run check-config and state the sources the skill needs.
2. **Gather:** collect what the document is built from.
   - When it is a fetch of known data, as for a sprint report, one script does it, builds everything deterministic and writes a brief holding only what the agent needs. It prints one line of JSON on stdout (the paths the next step needs) and progress on stderr; on failure it exits non-zero with a message that says what to do.
   - When it is research, as for a tech investigation, the agent does it and keeps its working notes in files, such as the ledger, written through `output_file.py`. Scripts own what is mechanical about them: the folder, the skeleton and the structure check.
3. **Write:** the agent produces only the parts that need judgment, as a JSON file written through `output_file.py`. The skill gives its schema, the rules for each part and their limits.
4. **Finish:** a script validates the agent's text field by field before generating anything, with errors that name the field to fix. Then it generates the document and runs its checker, printing only what needs action.
5. **Tell the user** it's ready, with a link.

Re-running a step regenerates its output. To change the document, edit the JSON and run Finish again; never edit generated files.

### The rules

- Put it in `skills/agentic-manager-<name>/SKILL.md`. The folder name and the frontmatter `name` must match.
- Unless it's a utility (`agentic-manager-utils-*`), start the instructions with the prerequisite: run the check, stop if it fails, then name what the skill needs from the sources it returns, either specific sources or any source of a group, and what it does if they aren't enabled (usually stop and show their `setup`):

  ```markdown
  ## Prerequisite

  Run `agentic-manager-utils-check-config`. If it fails, stop here.

  This skill needs any enabled source of `workflow`, and the `github-cli` source. If one is missing, stop and tell the user how to enable it, showing its `setup` and the config `path`.
  ```

- If the skill runs its own scripts, pre-approve them in the frontmatter so Claude Code doesn't ask permission for each step, and tell the agent to call them by that same path: `allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py *)`, one per script, separated by spaces. Never pre-approve a command that changes the user's config or anything outside the skill's own output; without the ` *`, a rule approves only the command with no arguments, as check-config's does, so its `--init` still asks.
- Reach each enabled source's tool through its channel (`mcp`, `cli`, `api` or `fs`). Never hard-code a tool, URL or credential.
- Reach an `api` or `fs` source through a script that reads its settings with `agentic_manager.config.read_source()`. Never read the config from the skill's instructions, and never pass a setting to a script on its command line.
- A skill that writes files gets its output folder from the library's `agentic_manager/output_folder.py`, never from code of its own: a folder of its own in the user's output root, or in the system temp folder if the config sets none, created if missing, and whether it is temporary, so the skill can tell the user. A script imports its `output_folder()`, as the jira-sprint-report skill's `fetch_sprint.py` does. When the agent writes a skill's files itself, it runs the file, which prints the same, and writes every file through the library's `agentic_manager/output_file.py`, never with its own file tools, as the tech-investigation skill does. The writer only writes inside the skill's output folder, so pre-approve both in the frontmatter: `Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *)` and the same for `output_file.py`. State this in the skill's instructions, near the top: that its files go to the user's configured output root, or to a temporary folder if none is set.
- Give the agent only the work that needs judgment: research, classification, conclusions and prose. Anything deterministic belongs in a script: fixed templates and formats, headings, table structure, links and anchors, file layout, diagram mechanics and checks. The agent fills the content in a JSON file that a generator reads, and never edits the generated output by hand, as the jira-sprint-report skill does with `content.json` and `make_report.py` (see Script-owned skills). When you move work from a skill's instructions into a script, the output must stay the same and keep its quality: compare the script's output with what the skill produced before.
- Put the reasons for a script's rules in its header comment: the decisions that justify the code, in a few lines, not what the code already says.
- A skill that produces a report ends by saying it's ready, with a link to it. Don't recap what the report shows; add only a doubt about your own judgment that the report doesn't show.
- When changing a report rule, update its generator, checker and relevant tests together.
- Add the skill to the README's Available skills section, written for the user: what it is for and how to ask. A utility goes in the Utilities table above instead; the README never mentions utilities.

## Adding a source or a group

- Add the source to [config-template.json](skills/agentic-manager-utils-check-config/config-template.json) under its group in `sources`, named `<tool>-<channel>` (channel `mcp`, `cli`, `api` or `fs`), with `"enabled": false`.
- Give each setting a placeholder in angle brackets, such as `"<token>"`. The check reports a placeholder as not filled in when the source is enabled.
- For a new group, also add it to the groups table in the check-config [SKILL.md](skills/agentic-manager-utils-check-config/SKILL.md), and for a new channel, to its channels table. Tests check that both match the template.

## Testing

```bash
python3 tests/run.py                   # every skill; add -v to list each test
python3 tests/run.py <skill> ...       # only those skills
```

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
