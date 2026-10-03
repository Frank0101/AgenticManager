---
name: agentic-manager-check-config
description: Validates agentic-manager.json and resolves which tool each area (documentation, source control, workflow) uses and through which channel. Prerequisite for every AgenticManager skill; run it first and stop the calling skill if it fails. Use when another AgenticManager skill says to run agentic-manager-check-config, or when the user asks to check the AgenticManager configuration.
---

# Check Config

Prerequisite for all AgenticManager skills. It validates `agentic-manager.json` in the folder where the agent is running and tells the calling skill which tools to use and how to reach them.

## Concepts

The config file lists the tools available in that folder. Each tool belongs to a group, and each one can be switched on or off:

```json
{
  "documentation": {
    "notion-mcp": {
      "enabled": true,
      "workspace": "acme"
    }
  }
}
```

| Term        | Meaning                                             | In the JSON                                    | Example         |
| ----------- | --------------------------------------------------- | ---------------------------------------------- | --------------- |
| **group**   | An area of work                                     | A top-level key                                | `documentation` |
| **source**  | A tool in a group, plus how to reach it             | A key inside a group, named `<tool>-<channel>` | `notion-mcp`    |
| **tool**    | The product                                         | The first part of a source name                | `notion`        |
| **channel** | How skills communicate with the tool                | The suffix of a source name                    | `mcp`           |
| **setting** | Extra information a source needs (credentials, ...) | Any key of a source other than `enabled`       | `workspace`     |

Groups:

| Group            | Area                              | Example source |
| ---------------- | --------------------------------- | -------------- |
| `documentation`  | Where documentation lives         | `notion-mcp`   |
| `source_control` | Where the code is hosted          | `github-cli`   |
| `workflow`       | Where work items and tickets live | `jira-api`     |
| `messaging`      | Where the team chats              | `slack-mcp`    |

Channels:

| Channel | How to communicate                                               |
| ------- | ---------------------------------------------------------------- |
| `mcp`   | Use the tool's MCP tools                                         |
| `cli`   | Run the tool's command-line program through bash                 |
| `api`   | Call the tool's API, using the source's settings for credentials |

Every source needs an `enabled` boolean. All groups are optional.

## Instructions

1. Run the script from the folder where the agent is running (not from this skill's folder). The script looks for `agentic-manager.json` there, or in the git root if that folder is inside a git repository:

   ```bash
   python3 <path to this skill's folder>/scripts/check_config.py
   ```

   It prints one line of JSON. Do not read or validate the file yourself.

2. If it exits with `0` (`"ok":true`): tell the user the configuration is OK, summarize the enabled sources per group, mention any `warnings`, and return `sources` to the calling skill.

3. If it exits with `1` (`"ok":false`) or `python3` is unavailable: **stop**. The calling skill must not continue, and you must not guess settings or create defaults.
   - Show the user the `error` and the `path`.
   - If the file is missing, offer to create one containing `{}`, and create it only if the user agrees.
   - Once fixed, the user can re-run the original skill.

The script fails if a group is not an object of sources, a source name does not end in `-mcp`, `-cli` or `-api`, or `enabled` is missing or not a boolean. Unknown top-level keys only produce a warning.

## The result

On success the script returns the configuration resolved for skills to use:

```json
{
  "ok": true,
  "path": "/path/to/agentic-manager.json",
  "sources": {
    "documentation": [
      {
        "tool": "notion",
        "channel": "mcp",
        "settings": { "workspace": "acme" }
      }
    ],
    "source_control": [],
    "workflow": []
  },
  "warnings": []
}
```

- `sources` has one entry per group, listing only the **enabled** sources. A group with no enabled source is an empty list. Disabled sources are left out.
- Each source is already split into its `tool`, `channel` and `settings`, so you never need to parse the name.
- `warnings` lists non-blocking problems, such as an unknown top-level key.

## How the calling skill uses it

The calling skill refers to groups, not to specific tools. `sources` tells it which tool to use for a group and how to reach it.

Example: a skill says "search in the documentation".

1. Look at `sources.documentation`.
2. It contains `notion-mcp`, so the tool is Notion and the channel is `mcp`.
3. Search Notion using its MCP tools.

If a group has several enabled sources, use all of them. If a skill needs a group whose list is empty, it must stop and tell the user to enable a source for it in `agentic-manager.json`.
