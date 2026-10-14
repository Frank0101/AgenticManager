---
name: agentic-manager-utils-lib
disable-model-invocation: true
description: Python code shared by the other AgenticManager skills, such as checking and reading the config, the Jira client and writing to the output folder. Not a task to run; never invoke it.
---

# Shared code

This skill holds no instructions of its own. Its `agentic_manager` Python package is shared by the other AgenticManager skills, whose scripts and prerequisites find it next to their own folder, so it must be installed alongside them.

Its modules, and every public function in them with what it is for, are listed by `agentic_manager/code_map.py`, which builds the map from their header comments and docstrings; each module's header comment says how to call it and why it works that way.

## Config sources

`agentic_manager/check_config.py` validates the user's config against `agentic_manager/config-template.json`, the only definition of what AgenticManager supports. The groups of the template's `sources`:

| Group            | Area                              |
| ---------------- | --------------------------------- |
| `documentation`  | Where documentation lives         |
| `local_vault`    | Where the user's own notes live   |
| `source_control` | Where the code is hosted          |
| `workflow`       | Where work items and tickets live |
| `messaging`      | Where the team chats              |

A source is named `<tool>-<channel>`. The channels, and how a skill reaches a tool through each:

| Channel | How to reach the tool                                     |
| ------- | --------------------------------------------------------- |
| `mcp`   | Use the tool's MCP tools                                  |
| `cli`   | Run the tool's command-line program through bash          |
| `api`   | Run a script of the calling skill                         |
| `fs`    | Run a script of the calling skill, which reads the folder |
