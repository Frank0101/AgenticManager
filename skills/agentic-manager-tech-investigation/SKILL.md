---
name: agentic-manager-tech-investigation
description: Investigates a technical system, proposal, capability or engineering problem and writes an evidence-backed report of its vision, purpose and impact, its current status, done and in progress, and its direction and target architecture, cross-checking the team's code, tracker and documentation. Use when the user asks to investigate, map or explain a system or proposal, asks what exists today versus what is planned, or asks for its architecture, current status or target state.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/extract_saved.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/investigate.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/tickets.py *)
---

# Tech Investigation

Investigates a technical system, proposal, capability or engineering problem, and produces the clearest evidence-backed account of:

- what the vision, purpose and impact are
- what its current status is: what is done, how it works (its system design today), and what is in progress
- what the direction is, and the system design it targets

A script runs the investigation. It hands out one task at a time, takes your answer, checks it, and records everything it implies. In order, the tasks answer the research questions, asking the user whenever research reaches something only they can put in or out of scope, then build the system design, run the independent review and write the report. Your part is the judgment: reading, claims, questions, design and prose.

The investigation's files go to the `tech-investigations` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The script chooses the folder; don't pass one.

```text
tech-investigations/
├── _examples/                             reports the user approved, kept as examples
└── Payments-Retry-Service_26-10-05/
    ├── ledger.md                          the research record: sources, findings, questions, design
    ├── content.json                       the report's text, as you submitted it
    └── Payments-Retry-Service_Report.md   the report, generated from the two above
```

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill reads three kinds of source: the code, from any enabled `source_control` source; the tracker, from the `jira-api` source, which this skill's client reads; and the documentation, from any enabled `documentation` source.

All three are required. If any of them isn't enabled, stop and tell the user how to enable it, showing its `setup` and the config `path`.

## Run the investigation

Call every script by exactly the path this skill shows, or a task prints, so it runs without a permission prompt; a script's `--help` gives its commands and arguments.

1. **Name the topic.** Use the name the user gives; otherwise choose a short one, in capitalised words joined by hyphens, such as `Payments-Retry-Service`.
2. **Start it** with `python3 ${CLAUDE_SKILL_DIR}/scripts/investigate.py start --topic <Topic>`. It creates the investigation's folder and prints its name, such as `Payments-Retry-Service_26-10-05`. It replaces a folder of the same topic and day, so every run starts from scratch: never read or reuse what an earlier run left. It also lists the approved examples: skim one for tone only, never for facts.
3. **Work the tasks.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/investigate.py next --investigation <investigation>`, do what the task says, and submit your answer with the command it ends with. Then run `next` again, until it says the investigation is finished. A task holds its own rules, what the ledger holds for it and an example of the answer. When `submit` refuses an answer, it names each problem by its field and writes nothing, but for the report's text, which the write task then shows with its problems: fix them all and submit again. Never open or edit the ledger or the report: the script keeps them.
4. **Work in parallel** when there are several research questions: `next --max 4` hands out up to 4. Give each task to a subagent exactly as printed, adding only: "Submit your answer with the task's command; if the script refuses it, fix every problem it names and submit again, until it is accepted, then reply in one line." Choose each subagent's model for its task: a smaller one where the work is reading a few tickets or pages and recording them, your own where the reading takes judgment, such as tracing code. Never one more expensive than your own. The script checks each answer as it is submitted; verifying the claims against their sources is the independent review's job.
5. **Hand over** as the last task says, once `next` says the investigation is finished.
