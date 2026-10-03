# AgenticManager

A library of reusable Agent Skills that work with both Claude Code and Codex. Skills are installed with the `skills` CLI via `npx`.

## Install

Skills are installed globally, so they are available in every folder where you run the agent.

```bash
npx skills add Frank0101/AgenticManager --skill '*' --agent claude-code codex -g -y
```

## List

```bash
npx skills list -g
```

## Update

Run the install command again. It reinstalls the latest version of every skill from this repo, including new ones.

Your config keeps working when an update adds new sources: anything it doesn't list counts as disabled. When a skill needs one of them, it tells you what to add.

## Uninstall

Removes every skill installed from this repo and leaves the others. Requires `jq`.

```bash
npx skills list -g --json | jq -r '.[] | select(.source == "Frank0101/AgenticManager") | .name' | xargs npx skills remove -y -g
```

## Requirements

- **Node.js 18+**, to install skills with `npx`.
- **Python 3.8+**, available as `python3` where the agent runs. Every skill starts with `agentic-manager-check-config`, which runs a Python script.

## Configuration

Skills read one global config, `~/.config/agentic-manager/config.json`, wherever you run the agent. If it's missing, ask the agent to check the AgenticManager configuration and it will offer to create it from the [template](skills/agentic-manager-check-config/config-template.json).

The template lists every supported source, all disabled. In your config, you can only:

- Set `enabled` to `true` for the sources you use.
- Fill in all their settings, such as the Jira `personal-access-token`.

> [!CAUTION]
> The template shows everything that's supported. Adding groups, sources or settings that aren't in it will cause an error.

Skills never change your config on their own. If something is wrong, or a skill needs a source you haven't enabled, the skill stops and tells you how to fix it. The agent may offer to make the change, but only makes it once you approve.

## Available skills

| Skill                                                               | Description                                                          |
| ------------------------------------------------------------------- | -------------------------------------------------------------------- |
| [agentic-manager-check-config](skills/agentic-manager-check-config) | Validates and reads your config. Prerequisite for every other skill. |
