---
name: agentic-manager-utils-check-config
description: Validates the AgenticManager config (~/.config/agentic-manager/config.json) and returns every supported source by group (documentation, local_vault, source_control, workflow, messaging), with its tool, its channel, whether it is enabled and, if not, how to enable it. Never returns setting values such as tokens. Prerequisite for every AgenticManager skill except the agentic-manager-utils-* utilities; run it first. The calling skill decides from the result whether it can go on. Use when another AgenticManager skill says to run agentic-manager-utils-check-config, or when asked directly to check or set up the AgenticManager configuration.
---

# Check Config

Prerequisite for every AgenticManager skill except the `agentic-manager-utils-*` utilities. It validates the user's config and tells the calling skill which sources are enabled and how to reach them. It doesn't decide whether the calling skill can go on: the calling skill does, from the sources it needs.

## The config

- **User config:** `~/.config/agentic-manager/config.json`. One global file, used wherever the agent runs.
- **Template:** [config-template.json](config-template.json) in this skill's folder. Its `sources` object lists every supported group and source, all disabled, and its `output` object the settings for where skills write files. The template is the only definition of what AgenticManager supports.

The config may only contain keys, groups, sources and settings from the template. It may leave some out: a missing group or source counts as disabled, and a missing output setting as not set, so the config keeps working when the template gains new ones. The user can only change two things: set a source's `enabled` to `true` or `false`, and fill in settings (any key other than `enabled`). An enabled source must have every setting filled in. The `output` settings are optional: when `output.root` isn't set, skills write to the system temp folder. The script enforces all of this.

This skill never changes the config on its own. When something is wrong, it stops, reports the problem and explains how to fix it. It changes the config only with the user's explicit approval (see step 2).

Never suggest a group, source or setting that isn't in the template, even if a connector for another tool is available in the session.

Settings can hold secrets, such as tokens. The script checks that they're filled in but never returns their values, so they never reach the agent or the chat. Never read the config yourself to find a value, and refer to a setting by name, for example "using your `api-token`". This applies to the calling skill too.

## Groups

| Group            | Area                              |
| ---------------- | --------------------------------- |
| `documentation`  | Where documentation lives         |
| `local_vault`    | Where the user's own notes live   |
| `source_control` | Where the code is hosted          |
| `workflow`       | Where work items and tickets live |
| `messaging`      | Where the team chats              |

## Instructions

1. Run the script:

   ```bash
   python3 <path to this skill's folder>/scripts/check_config.py
   ```

   It prints one line of JSON. Do not read or validate the config yourself.

2. If it exits with `1` (`"ok": false`) or `python3` is unavailable, the check has failed. Don't return any sources, and don't guess settings or create defaults. Handle it with the user as below, then report the failure to the calling skill.
   - If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ available as `python3`.
   - Otherwise, show the user every entry in `errors`, and the config `path`.
   - If the config is missing, offer to create it from the template. Only if the user agrees, run the script again with `--init`. It copies the template to `path`, never overwriting an existing file, and returns `"created": true`. Then tell the user to edit `path`: enable the sources they use and fill in their settings, and optionally set `output.root`.
   - For any other error, you may offer to make the fix it describes, but edit the config only after the user explicitly approves.

3. If it exits with `0` (`"ok": true`), return `sources` to the calling skill. When run directly, not by another skill, tell the user the configuration is OK and list the enabled sources by group; for each group with none, name its sources and their `setup`.

## Output

On success the script returns every source of the template by group:

```json
{
  "ok": true,
  "path": "/Users/me/.config/agentic-manager/config.json",
  "template": "/path/to/this/skill/config-template.json",
  "created": false,
  "sources": {
    "documentation": {
      "notion-mcp": { "tool": "notion", "channel": "mcp", "enabled": true }
    },
    "local_vault": {
      "logseq-fs": {
        "tool": "logseq",
        "channel": "fs",
        "enabled": false,
        "setup": "set \"sources.local_vault.logseq-fs.enabled\" to true, then fill in \"path\""
      }
    },
    "source_control": {
      "github-cli": { "tool": "github", "channel": "cli", "enabled": true }
    },
    "workflow": {
      "jira-mcp": {
        "tool": "jira",
        "channel": "mcp",
        "enabled": false,
        "setup": "set \"sources.workflow.jira-mcp.enabled\" to true"
      },
      "jira-api": { "tool": "jira", "channel": "api", "enabled": true }
    },
    "messaging": {
      "slack-mcp": {
        "tool": "slack",
        "channel": "mcp",
        "enabled": false,
        "setup": "set \"sources.messaging.slack-mcp.enabled\" to true"
      }
    }
  }
}
```

- Each source names the `tool`, the `channel` used to reach it, and whether it is `enabled`.
- A disabled source also has `setup`: how to enable it in the config, naming any settings to fill in.
- Setting values are never returned, and neither is `output`: a skill gets its folder itself (see below).

On failure it returns `"ok": false` and an `errors` list, each entry explaining one problem and how to fix it:

```json
{
  "ok": false,
  "path": "/Users/me/.config/agentic-manager/config.json",
  "template": "/path/to/this/skill/config-template.json",
  "created": false,
  "errors": [
    "sources.workflow.jira-api.api-token is not filled in: fill it in, or disable \"sources.workflow.jira-api\""
  ]
}
```

## How the calling skill uses it

The calling skill decides what it needs, and checks it in `sources`:

- **A specific source**, such as a step whose script calls one tool's API: check that `sources.<group>.<source>.enabled` is `true`. If it isn't, stop and tell the user to enable it, showing its `setup` and the config `path`.
- **Any source of a group**, such as "list the open tickets" in whatever tool the team uses: use every enabled source of `sources.<group>`. If none is enabled, stop and tell the user which sources the group has, showing their `setup` and the config `path`.

Reach each tool through its channel:

| Channel | How to reach the tool                                     |
| ------- | --------------------------------------------------------- |
| `mcp`   | Use the tool's MCP tools                                  |
| `cli`   | Run the tool's command-line program through bash          |
| `api`   | Run a script of the calling skill                         |
| `fs`    | Run a script of the calling skill, which reads the folder |

An `api` or `fs` source always goes through a script, since its settings, such as a token or the folder to read, aren't returned. The script reads them with `agentic_manager.config.read_source()`. A skill that writes files gets its folder from `agentic_manager/output_folder.py`, in the `agentic-manager-utils-lib` skill.
