# AgenticManager

A library of reusable Agent Skills that work with both Claude Code and Codex, meant to help with a manager's tasks. Skills are installed with the `skills` CLI via `npx`.

## Install

Skills are installed globally, so they are available in every folder where you run the agent.

Installing needs Node.js 22.20+, for `npx` and the `skills` CLI.

```bash
npx skills add Frank0101/AgenticManager --skill '*' --agent claude-code codex -g -y
```

## Use without installing

You can also clone the repo and start Claude Code or Codex inside it: the skills are available there for dogfooding.

```bash
git clone https://github.com/Frank0101/AgenticManager.git
```

- If the skills are also installed globally, the agent may run the installed version instead of the clone's, so your local changes wouldn't take effect. Uninstall the global skills first when you want to test the clone.
- Don't run `npx skills` from inside the repo folder: a bug in the `skills` CLI makes uninstalling delete the skills from the clone.

## List

```bash
npx skills list -g
```

## Update

Run the install command again. It reinstalls the latest version of every skill from this repo, including new ones. It doesn't remove skills that were renamed or deleted in the repo: if `npx skills list -g` shows one that is no longer listed under [Available skills](#available-skills), remove it with `npx skills remove <name> -g`.

## Uninstall

Removes every skill installed from this repo and leaves the others. Requires `jq`.

```bash
npx skills list -g --json | jq -r '.[] | select(.source == "Frank0101/AgenticManager") | .name' | xargs npx skills remove -y -g
```

## Requirements

- **Python 3.14+**, available as `python3` where the agent runs.

Individual skills may have additional dependencies, listed in [Available skills](#available-skills).

## Configuration

Skills read one global config, `~/.config/agentic-manager/config.json`, wherever you run the agent. You can create it from the [template](skills/agentic-manager-utils-lib/agentic_manager/config-template.json), which lists every supported source, all disabled, by group inside its `sources` object.

- Enable the sources you use by setting `enabled` to `true`, and fill in all their properties.
- Set `output.root` to the folder where skills write their files, such as reports. If you don't set it, they write to a temporary folder.

> [!CAUTION]
> You can't add anything that isn't in the template: keys, groups, sources or settings that it doesn't list will cause an error.

## Available skills

| Skill                                                                           | What it does                                                                                                                                                           | Additional dependencies |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| [agentic-manager-jira-sprint-report](skills/agentic-manager-jira-sprint-report) | Writes an exec-ready report of a Jira sprint, closed or in progress, with its goal outcome, scope timeline, burndown, delivery by epic and retro notes.                | -                       |
| [agentic-manager-tech-investigation](skills/agentic-manager-tech-investigation) | Investigates a technical system or proposal by comparing its documentation, tickets and code, and reports the current state, the current milestone and the next steps. | Node.js 22.13+.         |
