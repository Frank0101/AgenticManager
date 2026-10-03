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

## Uninstall

Removes every skill installed from this repo and leaves the others. Requires `jq`.

```bash
npx skills list -g --json | jq -r '.[] | select(.source == "Frank0101/AgenticManager") | .name' | xargs npx skills remove -y -g
```

## Requirements

- **Node.js 18+**, to install skills with `npx`.
- **Python 3.8+**, available as `python3` where the agent runs. Every skill starts by running `agentic-manager-check-config`, which is a Python script.

## Configuration

Skills read an `agentic-manager.json` file from the folder where you run the agent, for example your Obsidian or Logseq vault. If that folder is inside a git repository, they read it from the repository root instead. If the file is missing, skills stop.

Copy [agentic-manager.json](agentic-manager.json) from this repo into that folder. It lists every supported group and source, all disabled. Only two kinds of change are expected:

- Set `enabled` to `true` for the sources you use.
- Fill in their settings, such as the Jira `personal-access-token`.

Don't add groups or sources: skills only know how to use the ones in the file.

| Group            | Area                              | Source       | How skills reach it                    |
| ---------------- | --------------------------------- | ------------ | -------------------------------------- |
| `documentation`  | Where documentation lives         | `notion-mcp` | Notion MCP                             |
| `source_control` | Where the code is hosted          | `github-cli` | `gh` CLI                               |
| `workflow`       | Where work items and tickets live | `jira-api`   | Jira API, with `personal-access-token` |
| `messaging`      | Where the team chats              | `slack-mcp`  | Slack MCP                              |

## Available skills

| Skill                                                               | Description                                                                     |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| [agentic-manager-check-config](skills/agentic-manager-check-config) | Validates and reads `agentic-manager.json`. Prerequisite for every other skill. |
