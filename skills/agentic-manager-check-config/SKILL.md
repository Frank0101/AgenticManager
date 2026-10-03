---
name: agentic-manager-check-config
description: Validates the AgenticManager config (~/.config/agentic-manager/config.json) and resolves which tool each area (documentation, source control, workflow, messaging) uses and through which channel. Prerequisite for every AgenticManager skill; run it first and stop the calling skill if it fails. Use when another AgenticManager skill says to run agentic-manager-check-config, or when the user asks to check or set up the AgenticManager configuration.
---

# Check Config

Prerequisite for all AgenticManager skills. It validates the user's config and tells the calling skill which tools to use and how to reach them.

## The config

- **User config:** `~/.config/agentic-manager/config.json`. One global file, used wherever the agent runs.
- **Template:** [config-template.json](config-template.json) in this skill's folder. It lists every supported group and source, all disabled, and is the only definition of what AgenticManager supports.

The user can only change two things in their config: set a source's `enabled` to `true` or `false`, and fill in its settings (any key other than `enabled`). Groups and sources left out of the config count as disabled.

Never suggest, add or accept a group or source that isn't in the template, even if a connector for it is available in the session. The script rejects them.

## Instructions

1. Run the script:

   ```bash
   python3 <path to this skill's folder>/scripts/check_config.py
   ```

   It prints one line of JSON. Do not read or validate the config yourself.

2. If it exits with `0` (`"ok":true`): tell the user the configuration is OK, summarize the enabled sources per group, and return `sources` to the calling skill. For each group with no enabled source, name the source the template lists for it.

3. If it exits with `1` (`"ok":false`) or `python3` is unavailable: **stop**. The calling skill must not continue, and you must not guess settings or create defaults.
   - Show the user the `error` and the `path`.
   - If the config is missing, offer to create it from the template. Only if the user agrees, run the script again with `--init`. It copies the template to `path`, never overwriting an existing file, and returns `"created": true`. Then tell the user to edit `path`: enable the sources they use and fill in their settings.
   - Once fixed, the user can re-run the original skill.

## The result

On success the script returns the configuration resolved for skills to use:

```json
{
  "ok": true,
  "path": "/Users/me/.config/agentic-manager/config.json",
  "template": "/path/to/this/skill/config-template.json",
  "created": false,
  "sources": {
    "documentation": [{ "tool": "notion", "channel": "mcp", "settings": {} }],
    "source_control": [],
    "workflow": [
      {
        "tool": "jira",
        "channel": "api",
        "settings": { "personal-access-token": "..." }
      }
    ],
    "messaging": []
  }
}
```

- `sources` has every supported group, listing only its **enabled** sources. A group with no enabled source is an empty list.
- Each source is already split into its `tool`, `channel` and `settings`, so you never need to parse the name.

## How the calling skill uses it

The calling skill refers to groups, not to specific tools. `sources` tells it which tool to use for a group and how to reach it:

| Channel | How to reach the tool                                            |
| ------- | ---------------------------------------------------------------- |
| `mcp`   | Use the tool's MCP tools                                         |
| `cli`   | Run the tool's command-line program through bash                 |
| `api`   | Call the tool's API, using the source's settings for credentials |

Example: a skill says "search in the documentation".

1. Look at `sources.documentation`.
2. It contains `notion` with channel `mcp`.
3. Search Notion using its MCP tools.

If a skill needs a group whose list is empty, it must stop and tell the user to enable that group's source in their config.
