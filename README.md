# AgenticManager

A library of reusable Agent Skills that work with both Claude and OpenAI (Codex). Skills are installed with the `skills` CLI via `npx`. Below is a recap of the most useful commands.

## Available skills

| Skill                             | Description                                                         |
| --------------------------------- | ------------------------------------------------------------------- |
| [hello-skill](skills/hello-skill) | Example skill used to verify the setup. Copy it to start a new one. |

## Requirements

Node.js 18+ (for `npx`). No global install is needed.

## Install

```bash
# See what's available without installing
npx skills add Frank0101/AgenticManager --list

# Interactive: pick skills and agents
npx skills add Frank0101/AgenticManager

# Install one skill
npx skills add Frank0101/AgenticManager --skill hello-skill

# Install everything, for every detected agent, without prompts
npx skills add Frank0101/AgenticManager --all

# Target specific agents (e.g. Claude Code and Codex only)
npx skills add Frank0101/AgenticManager --skill hello-skill --agent claude-code --agent codex
```

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
