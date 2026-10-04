# AgenticManager

A library of reusable Agent Skills that work with both Claude Code and Codex. Skills are installed with the `skills` CLI via `npx`.

## Install

Skills are installed globally, so they are available in every folder where you run the agent.

```bash
npx skills add Frank0101/AgenticManager --skill '*' --agent claude-code codex -g -y
```

## Use without installing

You can also clone the repo and start Claude Code or Codex inside it: the skills are available there without installing them, so you don't need Node.js.

```bash
git clone https://github.com/Frank0101/AgenticManager.git
```

- The skills are available only when the agent runs in the repo folder.
- Use either the clone or the installed skills, not both, so the agent doesn't find each skill twice.
- Don't run `npx skills` from inside the repo folder: a bug in the `skills` CLI makes uninstalling delete the skills from the clone.

## List

```bash
npx skills list -g
```

## Update

Run the install command again. It reinstalls the latest version of every skill from this repo, including new ones.

Your config keeps working when an update adds new sources or settings: a source it doesn't list counts as disabled, and an `output` setting it doesn't list as not set. When a skill needs one of them, it tells you what to add.

## Uninstall

Removes every skill installed from this repo and leaves the others. Requires `jq`.

```bash
npx skills list -g --json | jq -r '.[] | select(.source == "Frank0101/AgenticManager") | .name' | xargs npx skills remove -y -g
```

## Requirements

- **Node.js 18+**, to install skills with `npx`.
- **Python 3.8+**, available as `python3` where the agent runs. Skills use it to check your config and to run their scripts.

## Configuration

Skills read one global config, `~/.config/agentic-manager/config.json`, wherever you run the agent. If it's missing, any skill you run will offer to create it from the [template](skills/agentic-manager-utils-check-config/config-template.json).

The template lists every supported source, all disabled, by group inside its `sources` object. In your config, you can only:

- Set `enabled` to `true` for the sources you use.
- Fill in all their settings, such as the Jira `api-token`, or for `local_vault.logseq-fs` the `path` of your Logseq folder.
- Set `output.root` to the folder where skills write their files, such as reports. If you don't set it, they write to a temporary folder.

> [!CAUTION]
> Adding keys, groups, sources or settings that aren't in the template will cause an error.

Skills never change your config on their own. If something is wrong, or a skill needs a source you haven't enabled, the skill tells you how to fix it. The agent may offer to make the change, but only makes it once you approve.

## Available skills

| Skill                                                                           | What it does                                                                                                                                                                                                           |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [agentic-manager-jira-sprint-report](skills/agentic-manager-jira-sprint-report) | Writes an exec-ready report of a Jira sprint, closed or in progress: goal outcome, achievements, blockers, scope timeline, burndown, delivery by epic and retro notes. Needs `jira-api` enabled in `sources.workflow`. |

Ask the agent in your own words, for example "how did the last PROJ sprint go?". Reports are written to the `jira-sprint-reports` folder of your `output.root`, or to a temporary folder if you haven't set one; the agent gives you a link to open them.

The burndown uses each day's closing status, estimates and sprint membership. On the day a sprint closes it stops at the exact closing time; an active sprint's current day stops at the fetch time. Later changes are excluded from a closed sprint's figures. Work that was already Done at the start and is reopened counts as added scope from the day it was reopened.
