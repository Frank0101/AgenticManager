---
name: agentic-manager-check-config
description: Validates the AgenticManager config (~/.config/agentic-manager/config.json), checks that the groups a calling skill needs (documentation, source_control, workflow, messaging) have an enabled source, and returns which tool each group uses and through which channel. Prerequisite for every AgenticManager skill; run it first and stop the calling skill if it fails. Use when another AgenticManager skill says to run agentic-manager-check-config, or when the user asks to check or set up the AgenticManager configuration.
---

# Check Config

Prerequisite for all AgenticManager skills. It validates the user's config, checks that the groups the calling skill needs are available, and tells the calling skill which tools to use and how to reach them.

## The config

- **User config:** `~/.config/agentic-manager/config.json`. One global file, used wherever the agent runs.
- **Template:** [config-template.json](config-template.json) in this skill's folder. It lists every supported group and source, all disabled, and is the only definition of what AgenticManager supports.

The config must have exactly the template's groups, sources and settings. The user can only change two things: set a source's `enabled` to `true` or `false`, and fill in its settings (any key other than `enabled`). An enabled source must have every setting filled in. The script enforces all of this.

Never suggest adding, removing or renaming a group, source or setting, even if a connector for another tool is available in the session. If the script reports something missing after an update, tell the user to copy it from the template.

## Input

The calling skill names the groups it needs, for example "run agentic-manager-check-config for `workflow` and `source_control`". Each requested group must have at least one enabled source.

| Group            | Area                              |
| ---------------- | --------------------------------- |
| `documentation`  | Where documentation lives         |
| `source_control` | Where the code is hosted          |
| `workflow`       | Where work items and tickets live |
| `messaging`      | Where the team chats              |

When the user runs this skill directly to check their config, pass no groups: every group is returned and none is required.

## Instructions

1. Run the script, passing the requested groups:

   ```bash
   python3 <path to this skill's folder>/scripts/check_config.py workflow source_control
   ```

   It prints one line of JSON. Do not read or validate the config yourself.

2. If it exits with `1` (`"ok":false`) or `python3` is unavailable: **stop**. The calling skill must not continue, and you must not guess settings or create defaults.
   - Show the user every entry in `errors`, and the config `path`.
   - If the config is missing, offer to create it from the template. Only if the user agrees, run the script again with `--init` and the same groups. It copies the template to `path`, never overwriting an existing file, and returns `"created": true`. Then tell the user to edit `path`: enable the sources they use and fill in their settings.
   - Once fixed, the user can re-run the original skill.

3. If it exits with `0` (`"ok":true`): tell the user the configuration is OK and which source each requested group will use, then return `sources` to the calling skill. When run without groups, also name, for each group with no enabled source, the source the template lists for it.

## Output

On success the script returns the enabled sources of the requested groups:

```json
{
  "ok": true,
  "path": "/Users/me/.config/agentic-manager/config.json",
  "template": "/path/to/this/skill/config-template.json",
  "created": false,
  "sources": {
    "documentation": [
      {
        "source": "notion-mcp",
        "tool": "notion",
        "channel": "mcp",
        "settings": {}
      }
    ],
    "source_control": [
      {
        "source": "github-cli",
        "tool": "github",
        "channel": "cli",
        "settings": {}
      }
    ],
    "workflow": [
      {
        "source": "jira-api",
        "tool": "jira",
        "channel": "api",
        "settings": { "personal-access-token": "..." }
      }
    ],
    "messaging": []
  }
}
```

- `sources` has one entry per requested group (every group when none was requested), listing only its **enabled** sources.
- Each source names the `tool`, the `channel` used to reach it, and the `settings` it needs, such as credentials.

On failure it returns `"ok": false` and an `errors` list, each entry explaining one problem and how to fix it:

```json
{
  "ok": false,
  "path": "/Users/me/.config/agentic-manager/config.json",
  "template": "/path/to/this/skill/config-template.json",
  "created": false,
  "errors": [
    "no enabled source for \"source_control\": enable \"source_control.github-cli\" in /Users/me/.config/agentic-manager/config.json"
  ]
}
```

## How the calling skill uses it

The calling skill refers to groups, not to specific tools. For each group it needs, it uses the sources in `sources.<group>`, reaching each tool through its channel:

| Channel | How to reach the tool                                            |
| ------- | ---------------------------------------------------------------- |
| `mcp`   | Use the tool's MCP tools                                         |
| `cli`   | Run the tool's command-line program through bash                 |
| `api`   | Call the tool's API, using the source's settings for credentials |

Example: a skill says "list the open tickets".

1. It ran agentic-manager-check-config for `workflow`.
2. `sources.workflow` contains `jira` with channel `api`.
3. It calls the Jira API, authenticating with `settings.personal-access-token`.

If a group has several enabled sources, use all of them.
