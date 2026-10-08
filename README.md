# AgenticManager

A library of reusable Agent Skills that work with both Claude Code and Codex. Skills are installed with the `skills` CLI via `npx`.

## Install

Skills are installed globally, so they are available in every folder where you run the agent.

```bash
npx skills add Frank0101/AgenticManager --skill '*' --agent claude-code codex -g -y
```

## Use without installing

You can also clone the repo and start Claude Code or Codex inside it: the skills are available there without installing them, so you need Node.js only for the tech investigation's diagrams.

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

- **Node.js 18+**, to install skills with `npx`. The tech investigation also needs **Node.js 22.13+**: the pinned Mermaid CLI, with Puppeteer's headless browser, draws and checks its architecture maps and sequence diagrams. Without it the investigation stops at its first step and asks you to install it. If rendering reports a missing `chrome-headless-shell`, install it with `npx -y -p @mermaid-js/mermaid-cli@12.0.0 puppeteer browsers install chrome-headless-shell`.
- **Python 3.14+**, available as `python3` where the agent runs. Skills use it to check your config and to run their scripts. Sprint reports also need IANA timezone data, normally provided by macOS and Linux. If it is missing, install it with `python3 -m pip install tzdata`.

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

| Skill                                                                           | What it does                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [agentic-manager-jira-sprint-report](skills/agentic-manager-jira-sprint-report) | Writes an exec-ready report of a Jira sprint, closed or in progress: goal outcome, carry-over, achievements, blockers, scope timeline, burndown, delivery by epic and retro notes. Needs `jira-api` enabled in `sources.workflow`.                                                                                                                                                                                       |
| [agentic-manager-tech-investigation](skills/agentic-manager-tech-investigation) | Investigates a technical system or proposal by comparing its documentation (the vision), tickets (the delivery) and code (the implementation): the current state, the current milestone and a target architecture, with as-is and to-be architecture maps, flow diagrams, gaps and open decisions. Uses the `mcp` and `cli` sources enabled in `sources.documentation`, `sources.workflow` and `sources.source_control`. |

Ask the agent in your own words.

### Sprint reports

For example, "how did the last PROJ sprint go?". It works for a closed sprint or one still running, and reports the goal outcome, what was delivered against what was committed, a scope timeline with a burndown, delivery by epic, risks and notes for the retro. Figures are always as they were when the sprint closed (for a running sprint, when you asked), so the same sprint gives the same report whenever you ask. The few parts that need judgment are written by the agent and marked "[AI Gen.]": the goal outcome, the epic commentary, key achievements, blockers and risks, and the retro notes. Everything else is generated from Jira's data and checked.

Reports are written to the `jira-sprint-reports` folder of your `output.root`, or to a temporary folder if you haven't set one; the agent gives you a link to open them. Asking again for the same sprint replaces its previous report folder, including the written commentary, so keep a copy elsewhere if you want to retain an earlier version.

Dates use your Jira account's timezone. If Jira doesn't return a usable one, the report stops and asks you to check the account's timezone.

### Tech investigations

For example, "investigate how the payments retry service works today and what its next milestone should be", or "give me a 100-word exec summary of the acme search rewrite". A short summary is always built on a full investigation, so it takes as long as the full document, and you can then ask for more detail without the agent starting again.

The agent reads the sources you've enabled through `mcp` or `cli` in `documentation` (the vision), `workflow` (the delivery) and `source_control` (the implementation). Where they disagree, code and configuration win over the work tracker, and the work tracker over documentation. If a group has no such source, the agent tells you how to enable one and asks whether to go on without it; what depends on that group is then marked unverified. If no group has one, it stops. Sources reached through `api` or `fs` aren't used.

Every full report has two layers: an executive account of the problem, scope, roadmap and current milestone, and an architect account of the current architecture, the next evolution and the target architecture, with system maps and flow diagrams. The report doesn't recommend a design: future direction comes from source-backed plans and proposals, and what isn't known stays marked as unresolved. When there is no system to draw, or nothing changing it, the report leaves out the architect summary or the later stages, and the research ledger records why.

Investigations are written to the `tech-investigations` folder of your `output.root`, or to a temporary folder if you haven't set one: one folder per topic and day, such as `Payments-Retry-Service_26-10-05`, holding the report, the research ledger, the architecture images and any short output you asked for. When you tell the agent you're happy with a document or summary, it keeps a copy in the `_examples` folder there and uses those as models of tone and voice for later investigations, never as evidence.
