# AgenticManager

A library of reusable Agent Skills that work with both Claude and OpenAI (Codex). Skills are installed with the `skills` CLI via `npx`. Below is a recap of the most useful commands.

## Available skills

| Skill                               | Description                                                                     |
| ----------------------------------- | ------------------------------------------------------------------------------- |
| [check-config](skills/check-config) | Validates and reads `agentic-manager.json`. Prerequisite for every other skill. |
| [hello-skill](skills/hello-skill)   | Example skill used to verify the setup. Copy it to start a new one.             |

## Requirements

- **Node.js 18+**, to install skills with `npx`.
- **Python 3.8+**, available as `python3` on the machine where the agent runs. Every skill needs it, because each one runs `check-config` first, and `check-config` is a Python script. Without Python, skills will stop at that step.

No global install is needed.

## Configuration

Skills read their settings from an `agentic-manager.json` file in the root of the repository where you use them. The file must exist and contain a JSON object, even if it is just `{}`. Every skill first runs `check-config`, and stops if the file is missing or invalid.

```bash
echo '{}' > agentic-manager.json
```

The file only declares which tools are available in the repository. The skills decide what is supported and how each tool is used.

```json
{
  "documentation": {
    "notion-mcp": { "enabled": true }
  },
  "source_control": {
    "github-cli": { "enabled": true }
  },
  "workflow": {
    "jira-api": {
      "enabled": true,
      "personal-access-token": "<token>"
    }
  }
}
```

| Term        | Meaning                                             | In the JSON                                    | Example                 |
| ----------- | --------------------------------------------------- | ---------------------------------------------- | ----------------------- |
| **group**   | An area of work                                     | A top-level key                                | `documentation`         |
| **source**  | A tool in a group, plus how to reach it             | A key inside a group, named `<tool>-<channel>` | `notion-mcp`            |
| **tool**    | The product                                         | The first part of a source name                | `notion`                |
| **channel** | How skills communicate with the tool                | The suffix of a source name                    | `mcp`                   |
| **setting** | Extra information a source needs (credentials, ...) | Any key of a source other than `enabled`       | `personal-access-token` |

Every source needs an `enabled` flag (`true` or `false`).

Groups:

| Group            | Area                              | Example source |
| ---------------- | --------------------------------- | -------------- |
| `documentation`  | Where documentation lives         | `notion-mcp`   |
| `source_control` | Where the code is hosted          | `github-cli`   |
| `workflow`       | Where work items and tickets live | `jira-api`     |
| `messaging`      | Where the team chats              | `slack-mcp`    |

Channels:

| Channel | How skills communicate with the tool |
| ------- | ------------------------------------ |
| `mcp`   | Through MCP                          |
| `cli`   | Through bash CLI calls               |
| `api`   | Through API calls                    |

All groups are optional. Keep disabled sources in the file if you want to switch them on later. An unknown top-level key produces a warning. A group that is not an object of sources, a source name that doesn't end in `-mcp`, `-cli` or `-api`, or a source without a boolean `enabled` makes `check-config` fail. More settings will be documented here as skills start using them.

## Install

```bash
# See what's available without installing
npx skills add Frank0101/AgenticManager --list

# Interactive: pick skills and agents
npx skills add Frank0101/AgenticManager

# Install one skill
npx skills add Frank0101/AgenticManager --skill check-config --skill hello-skill

# Install everything, for every detected agent, without prompts
npx skills add Frank0101/AgenticManager --all

# Target specific agents (e.g. Claude Code and Codex only)
npx skills add Frank0101/AgenticManager --skill check-config --skill hello-skill --agent claude-code --agent codex
```

Skills depend on `check-config`, so always install it together with the skills you use.

Add `-g` to install globally instead of into the current project. Add `--copy` to copy files instead of symlinking.

## List

```bash
npx skills list          # project-level
npx skills list -g       # global
```

## Update

```bash
npx skills update                 # all installed skills
npx skills update hello-skill     # one skill
npx skills update -g              # global only
```

Updates follow the default branch of this repo.

## Uninstall

```bash
npx skills remove hello-skill          # one skill
npx skills remove hello-skill -g       # from global scope
npx skills remove hello-skill -a codex # from one agent only
npx skills remove --all                # everything
```

## Use a skill

Once installed, skills load automatically when a request matches the skill's `description`. You can also ask for one by name, for example "use hello-skill".

## License

TBD
