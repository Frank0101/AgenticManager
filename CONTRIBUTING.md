# Contributing

The design choices behind AgenticManager, to help you work on it. For installing and using the skills, see the [README](README.md).

## Layout

```text
skills/<skill>/          one folder per skill
  SKILL.md               instructions the agent follows
  scripts/               optional helper scripts
tests/<skill>/           tests for that skill, mirroring skills/
tests/run.py             runs every skill's tests
.claude/skills  ─┐       symlinks to skills/, so the skills load when you run
.agents/skills  ─┘       Claude Code or Codex inside this repo
```

The symlinks let you use the skills while you build them. Edits to a skill apply to the next agent session; a running session keeps the instructions it already loaded.

## Skills and the config

Every skill starts by running `agentic-manager-utils-check-config`, passing the [groups](skills/agentic-manager-utils-check-config/SKILL.md#input) it needs. If the config is invalid, or no source is available for a requested group, the check fails and the skill can handle the situation. On success, the check returns the enabled sources of each group.

The exception is the [utilities](#utilities), which don't run the check.

Skills refer to groups, such as `workflow`, never to specific tools. The user's config decides which tool backs each group and how to reach it: through MCP, a CLI or an API. So the same skill works for teams using different tools, and nothing about a team's tools or credentials lives in this repo.

## Utilities

Skills named `agentic-manager-utils-*` are utilities: they're used by other skills or by you while you work on the repo, not by the people who install the skills, so the README doesn't mention them.

| Skill                                                                           | Purpose                                                                                       |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [agentic-manager-utils-check-config](skills/agentic-manager-utils-check-config) | Validates the user's config and returns the sources of the groups a skill needs.              |
| [agentic-manager-utils-refactoring](skills/agentic-manager-utils-refactoring)   | Reviews the whole repo, fixes what's wrong and reviews again until nothing is left to change. |

## The template

[config-template.json](skills/agentic-manager-utils-check-config/config-template.json) is the only definition of what's supported: every group, and every source with its settings. A source is named `<tool>-<channel>`, such as `jira-api`.

A user's config may only contain what the template lists, but it may leave things out: a missing group or source counts as disabled. So existing configs keep working when the template gains new sources.

## Pitfalls

- **Don't run `npx skills` from inside this repo.** The `skills` CLI has a bug: `remove -g` also deletes `<current folder>/.agents/skills/<skill>`, and here that's a symlink to `skills/`, so it deletes the skill's source. Adding `--agent` to the README's uninstall command doesn't work around it: the CLI then keeps the shared `~/.agents/skills` copy whenever another installed agent uses that folder.
