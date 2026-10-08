# Contributing

The design choices behind AgenticManager, to help you work on it. For installing and using the skills, see the [README](README.md).

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
tests/run.py             runs every skill's tests, each skill in its own process
.claude/skills  ─┐       symlinks to skills/, so the skills load when you run
.agents/skills  ─┘       Claude Code or Codex inside this repo
```

The symlinks let you use the skills while you build them. Edits to a skill apply to the next agent session; a running session keeps the instructions it already loaded.

## Skills and the config

Every skill starts by running `agentic-manager-utils-check-config`. The check only validates the config: it fails if the config is missing or malformed, and otherwise returns every supported source by [group](skills/agentic-manager-utils-check-config/SKILL.md#groups), saying whether each is enabled and, if not, how to enable it. It doesn't know what the calling skill needs.

The exception is the [utilities](#utilities), which don't run the check.

Each skill decides what it needs from that result. A skill that can work with whatever tool a team uses asks for any enabled source of a group, such as `workflow`, and reaches it through its channel: MCP, a CLI, an API or files on disk. A skill whose steps only work with one tool, such as a script that calls Jira's API, asks for that source, such as `jira-api`. Either way, the user's config decides what is available, and nothing about a team's tools or credentials lives in this repo.

The check never returns setting values. Settings can hold secrets, such as tokens, and anything the check prints reaches the agent and can end up in the chat. So the check only confirms that every setting of an enabled source is filled in, and a script that needs a setting reads it from the config itself. This is why an `api` or `fs` source is always reached through a script, while `mcp` and `cli` sources are reached by the agent directly, as the tech investigation does.

For the same reason, the agent never reads the output root from the config. Every skill gets its output folder from the library's `output_folder.py`, which reads only `output.root`: a skill's scripts import it, and the agent runs it when it writes a skill's files itself. Those files then go through the library's `output_file.py`, which refuses any path outside the skill's output folder. That makes it safe to pre-approve, as a skill's own scripts are, whereas the agent's file tools would need either a prompt for every write or an approval to write anywhere, the config included.

The output writer also supports exact text patches within the same folder boundary. Each replacement's `old` text must be nonempty and match exactly once; the entire batch is validated before the file is written. This avoids resending long files for small edits while refusing ambiguous or stale context. Concurrent edits can invalidate the expected text, so the writer rejects conflicting patches rather than merging them.

## Utilities

Skills named `agentic-manager-utils-*` are utilities: they're used by other skills or by you while you work on the repo, not by the people who install the skills, so the README doesn't mention them.

| Skill                                                                           | Purpose                                                                                                   |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| [agentic-manager-utils-check-config](skills/agentic-manager-utils-check-config) | Validates the user's config and returns every source, enabled or not, without setting values.             |
| [agentic-manager-utils-refactoring](skills/agentic-manager-utils-refactoring)   | Reviews the repo's eight concerns, fixes substantive problems, validates and formats the requested files. |
| [agentic-manager-utils-lib](skills/agentic-manager-utils-lib)                   | Code shared by the other skills, such as reading the config, the Jira client and writing output.          |

Refactoring reviews the repository for correctness, consistency, audience, clarity, quality, simplicity, tests and gaps between files. Those concerns supply the scope without a separate issue list. Mechanical checks supply leads, not mandatory cleanup. A concrete effect on normal supported use or ongoing development justifies a fix; cosmetic preferences, marginal cases and optional hardening don't block completion. Simplicity weighs each proposed fix's practical benefit against its maintenance cost, retaining necessary validation while discouraging speculative checks and fallback layers.

Reviewers trace important supported behavior through its implementation and tests, checking relevant boundaries and interactions rather than exhaustively inventing inputs. Fresh independent reviewers help when complexity warrants them, and a repository-wide review includes the important paths crossing file groups. Completion means substantive findings are resolved and appropriate validation passes, with material limits disclosed; it doesn't require repeated zero-finding rounds or a perfection score.

## Shared code

`npx skills` installs each skill as its own folder, side by side, with no shared folder and no install step. So code shared by several skills lives in a skill of its own, `agentic-manager-utils-lib`, as the `agentic_manager` Python package. A script finds it next to its own skill's folder and adds it to Python's path before importing it; the agent runs its modules by the same path.

This relies on all the skills being installed together, which the README's install command does. Every skill already depends on check-config the same way. If the library is missing, check-config fails and tells the user to reinstall every skill.

## The template

[config-template.json](skills/agentic-manager-utils-check-config/config-template.json) is the only definition of what's supported: every group, and every source with its settings. A source is named `<tool>-<channel>`, such as `jira-api`. The groups sit inside a `sources` object, so the config can hold settings that aren't sources, such as `output.root`, the folder skills write to.

A user's config may only contain what the template lists, but it may leave things out: a missing group or source counts as disabled, and a missing output setting as not set. So existing configs keep working when the template gains new sources or settings.

## Script-owned skills

AI-written content goes only where it needs judgment: it costs tokens, and it can come out differently on every run. So when a skill's output has numbers that must be right every time, such as the sprint report, or a fixed template, scripts own everything mechanical: fetching, classification, arithmetic, charts, formatting. The agent writes only the judgment text, in a small JSON file the generator reads. A checker script then validates the finished output against the data. Scripts also prepare what the agent reads: a brief holding only the material for its parts, so it never joins raw files itself, and one command each to run the pipeline before and after its writing. The skill's instructions then cover only the judgment; the reasons behind the scripts' rules live in their header comments, next to the code they justify. Prose rules alone don't stop a table drifting when it is edited by hand; a check that fails does.

Such skills use only the Python standard library (charts are drawn as SVG by hand), so they need Python 3.14+ and, for timezone conversion, IANA timezone data from the system or the `tzdata` package. A skill that produces files writes them to a folder of its own in the user's output root, or in the system temp folder if the config doesn't set one, and tells the user where. Output settings are optional, so a skill works before the user has chosen a folder.

Sprint dates and daily boundaries use `zoneinfo` with the API account's named timezone, saved from Jira's current-user profile in the fetch metadata. This keeps timeline dates and burndown boundaries consistent across daylight-saving changes. A missing or unavailable timezone stops the report rather than guessing a fixed offset.

A report on a past period must give the same figures whenever it is run. Jira's issue fields hold their state today, so the scripts rebuild every field that matters to a figure from the issue's changelog, as it was at the moment the report describes, and never read the current value unless the changelog shows it held then too.

## Investigation reports

Investigation ledgers keep a compact resume block followed by one research action queue, grouped into ready/in progress, blocked and completed actions. Findings own the evidence explanations; inventories and reviews reference stable IDs. File-level reading depth prevents discovery searches from being mistaken for full validation. One report evolves throughout research, with concise corrections retained instead of duplicate draft snapshots.

The tech investigation is script-owned too, although nearly all its text needs judgment: the research, the ledger, what the maps show and the report's prose stay with the agent, and scripts own the rest. `make_report.py` writes the report's fixed template from `content.json`, resolving ledger IDs to anchors, and `build_maps.py` draws all three stages' maps from one `maps.json`, so each stage has the same nodes and connections and the change colours come from comparing stages rather than from the agent. Both check what an instruction alone wouldn't hold: sequences against their stage's map, steps the commentary names, component positions across stages, components leaving the outline unexplained. A report may skip the architect layer or the evolution sections when the finished research shows they don't apply, with the reason recorded in the ledger; `check_report.py` reads the same choice from `content.json`, so the structure check stays exact. Short outputs, such as an exec summary, take whatever shape the question needs, so `make_summary.py` fixes only their frame: the file, the link to the full report and the word limit the user asked for. The ledger stays Markdown the agent edits, since it is reasoned over during the research; `init_investigation.py` writes its skeleton and `check_report.py` checks its structure.

### The architecture map

Investigation diagrams explain the approach rather than reproduce the implementation inventory. The maps retain concrete services, stores, hosting and material interfaces; internal details can be grouped where they do not affect those relationships. Fixed component positions support stage comparison, while scope outlines, changed connections and explicit lifecycle labels show evolution. The current stage is evidence; the next and target stages reconstruct a design no code shows yet, so a component whose responsibility that design gives to another is shown replaced, greyed without the cross that a sourced decommissioning gets. The ledger retains the mapping and evidence. Visual inspection complements syntax and geometry checks. A read-only report checker catches fixed-structure, local-artifact, table-citation and diagram-order errors. It complements source review and actual diagram rendering; passing it is not evidence that a claim or proposed interaction is true.

The tech investigation's map is the one output drawn by a tool outside Python: viewers draw Mermaid with their own versions and settings, so the skill's `output_diagram.py` renders it once with the Mermaid CLI, pinned to one version and run through `npx`, and `build_maps.py` checks every connection line against the map's rules before writing the SVGs. Rendering several diagrams, the three maps or every sequence, takes one Mermaid CLI run, through a Markdown file of their blocks, since each run starts a browser. A check that fails stops a bad layout, where an instruction to the agent alone wouldn't. Node.js stays optional: without it the scripts exit with code 3, and the skill shows the map as a Mermaid block instead. `output_diagram.py` lives in the skill, not the library, until another skill needs it.

## Pitfalls

- **Running `npx skills` inside this repo can delete source files.** The `skills` CLI has a bug: `remove -g` also deletes `<current folder>/.agents/skills/<skill>`, and here that's a symlink to `skills/`, so it deletes the skill's source. Adding `--agent` to the README's uninstall command doesn't work around it: the CLI then keeps the shared `~/.agents/skills` copy whenever another installed agent uses that folder.
