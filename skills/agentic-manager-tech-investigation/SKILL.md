---
name: agentic-manager-tech-investigation
description: Investigates a technical system, proposal, capability or engineering problem and writes an evidence-backed report of its vision, purpose and impact, its current status, done and in progress, and its direction and target architecture, cross-checking the team's code, tracker and documentation. Use when the user asks to investigate, map or explain a system or proposal, asks what exists today versus what is planned, or asks for its architecture, current status or target state.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/extract_saved.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_investigation.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/ledger.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/tickets.py *)
---

# Tech Investigation

Investigates a technical system, proposal, capability or engineering problem, and produces the clearest evidence-backed account of:

- what the vision, purpose and impact are
- what its current status is: what is done, how it works (its system design today), and what is in progress
- what the direction is, and the system design it targets

The work has five steps: [1. Define](#1-define), [2. Research](#2-research), [3. Review](#3-review), [4. Write](#4-write) and [5. Hand over](#5-hand-over).

The investigation's files go to the `tech-investigations` folder of the user's configured output root (`output.root`), or to a temporary folder if none is set. The scripts choose the folder; don't pass one.

```text
tech-investigations/
├── _examples/                             reports the user approved, kept as examples
└── Payments-Retry-Service_26-10-05/
    ├── ledger.md                          the research record: sources, findings, open questions
    ├── content.json                       the report's text, which you write
    └── Payments-Retry-Service_Report.md   the report, generated from the two above
```

An investigation's folder holds only these files, and the final check fails on any other; anything else you need goes in your own scratch folder.

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill reads three kinds of source (see [Sources and evidence](#sources-and-evidence)): the code, from any enabled `source_control` source; the tracker, from the `jira-api` source, which this skill's client reads; and the documentation, from any enabled `documentation` source.

All three are required. If any of them isn't enabled, stop and tell the user how to enable it, showing its `setup` and the config `path`.

## Sources and evidence

The investigation reads three kinds of source. Each tells you something different:

| Source        | What it tells you                                      |
| ------------- | ------------------------------------------------------ |
| Code          | What is implemented.                                   |
| Tracker       | The plan: scope, owners and progress.                  |
| Documentation | The vision: purpose, intent, decisions and the target. |

A component or capability is in the state its strongest evidence shows:

| State          | Evidence                                                     |
| -------------- | ------------------------------------------------------------ |
| Vision         | Only in the documentation.                                   |
| Planned        | In the tracker, with no code.                                |
| In development | Code written but not merged: an open pull request or branch. |
| Implemented    | Merged to the main branch.                                   |

When sources disagree about a fact, such as which queue a service uses, code wins over the tracker, and the tracker wins over the documentation. A ticket marked Done with no merged code is still only planned: the tracker reports it as done, but no implementation was found.

More rules apply to every investigation:

- Read the code itself, never only a README or a search hit.
- Classify a claim by its evidence, not by where it is stored: a design note in a repository is still vision.
- When two documents disagree, the newer one wins: note when each was last updated, and whether a newer one replaces it.
- When two tickets disagree, a done one wins over one that isn't done. Between two of the same status, the newer one wins. Within a ticket, a later comment wins over the description when they conflict.
- Messages, such as Slack threads or emails, are not evidence: leave them out, even when a documentation search returns them.
- Never read files that hold customer or personal data: describe such data by its schema and the controls on it. When you read configuration, look at key names only, never the values of secrets, and never copy a secret into the ledger or the report.
- Name roles, never people, in the report: "the platform team", "the feature's owner".

## 1. Define

Agree what is being investigated, then create the investigation's folder.

1. **Name the topic.** Use the name the user gives; otherwise choose a short one, in capitalised words joined by hyphens, such as `Payments-Retry-Service`.
2. **Agree the boundary.** Skim the documentation first: search it for the topic and read titles, summaries and the start of the main pages, just enough to see what the topic includes and what sits next to it, such as sibling projects, shared platforms or older systems with the same name. This is not research: read no code or tickets, and take no facts from it for the report; research reads these pages again, properly. Then ask the user as few questions as you need to settle what is in and out. For each topic next to this one, the answer is one of:

   | Answer       | What it means                                                          |
   | ------------ | ---------------------------------------------------------------------- |
   | Include      | Researched like the rest of the topic.                                 |
   | Mention only | Named in the report, with one line on how it connects; not researched. |
   | Exclude      | Left out of the report.                                                |

3. **Start the investigation.** Call every script by exactly the path this skill shows, so it runs without a permission prompt; a script's `--help` gives its commands and arguments. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/init_investigation.py --topic <Topic>`. It creates the investigation's folder and prints its name, such as `Payments-Retry-Service_26-10-05`, which the other scripts take as `--investigation`. In the folder it creates the ledger, `ledger.md`: the record of the research, which holds every source you read, what you found in it, and what is still open. The report is written from the ledger, and every claim in it traces back there.

   Work with the ledger only through `python3 ${CLAUDE_SKILL_DIR}/scripts/ledger.py`; never open or edit the file. `ledger.py help` lists its commands and, for each table, the columns, the values they accept and a command to copy. `ledger.py status` shows where the investigation stands: the queue, the counts and what is still open.

   `init_investigation.py` replaces a folder of the same topic and day, so every run starts from scratch; never read or reuse what an earlier run left. It also lists the approved examples: skim one for tone only, never for facts.

4. **Record the boundary.** Write the user's answers in the ledger's `Boundary` section: one line saying what the topic covers, then each topic next to it with its answer (include, mention only or exclude), one line each. If there were none, say so.

## 2. Research

Build the ledger, methodically, until it can answer the three questions this skill exists for: the vision, purpose and impact; the current status, what is done, how it works (its system design today) and what is in progress; and the direction, with the system design it targets. Every answer rests on evidence the ledger holds.

Use those three questions as your compass. Before you add a question to the queue, ask whether its answer would change one of them. If it would, add it; if not, leave it.

### The queue

The ledger keeps a queue of open questions. `init_investigation.py` starts it with three: what the documentation, the tracker and the code each say about the topic.

Take the next question with `python3 ${CLAUDE_SKILL_DIR}/scripts/ledger.py next --investigation <investigation>`: it follows the queue's order and skips a question that depends on one not yet answered. For each question:

1. **Read** only what this question needs: the least that answers it. Anything else the reading makes you want to know, such as a link to follow, another component or a claim to check, is a new question, not part of this one.
2. **Record** each source you read and each finding in the ledger, before you read anything else.
3. **Add** to the end of the queue every new question the reading raised that passes the compass, naming the open questions it depends on. You know them now, while you have the context; `next` uses them to choose.
4. **Close** the question: answered, with the findings that answer it, or blocked, with what stops you. Blocking it blocks every question that depends on it too. If the same reading answered another question already in the queue, close that one too.

`ledger.py help --table loop` shows the command for each step. When a tool's result is too large and saved to a file, list what you need from it with `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/extract_saved.py`, rather than reading it whole.

To work in parallel, take up to 4 questions with `ledger.py next --max 4` and give each to a subagent. Brief each subagent with its question, the rule to read only what it needs, and the ledger's input format (`ledger.py help --table batch`). It returns, without writing to the ledger: the sources it read with their revisions, the files it read and how deeply, its draft findings, and the new questions it noticed. Record each result with `ledger.py batch`, after checking that each finding is backed by what the subagent read; add its new questions as the Add step says; then close the questions.

### What you record

`ledger.py help` gives each table's columns; what goes in them is yours:

- A **source** is one thing you read, at one revision: a code folder or file, a ticket, a page, or a search with its exact query.
- A **finding** is one claim a source shows, in your words, citing the source. It says what the evidence shows, not what you conclude from it; a conclusion is a finding of its own, citing the findings it rests on.
- A **component** is a part of the system, as [Building the system design](#building-the-system-design) defines it: add it the first time you meet it, and update its state as you learn more.
- A **gap** is evidence you can't get yourself, such as a repository you have no access to.
- A **decision** is a choice that waits on a person, such as which runtime a team will use.

A question you can't answer is blocked by a gap or a decision. A source you can't read, for lack of access or because a call fails, is a gap: say so at once, block the questions that need it, and never fill the hole with assumptions.

### Reading the documentation

Read the documentation through its enabled source, with no special procedure: search for what the question needs, and read the pages it leads to. The rules in [Sources and evidence](#sources-and-evidence) apply: it is vision, the newer of two documents wins, and messages are left out.

### Reading the tracker

Read tickets only with `python3 ${CLAUDE_SKILL_DIR}/scripts/tickets.py`. Read a ticket in full: description, status, acceptance criteria, links and comments. Use `--prs` when its code matters, to list the pull requests linked to it. Each type tends to hold something different: an epic, the scope; a story, what is being delivered; a spike, a decision or an investigation's outcome; a bug, what is broken today.

The tracker can mislead you in two ways:

- **Open sub-tasks under a closed story.** A story's status stands over its sub-tasks': they are often left open after the story closes, so don't read them as unfinished work.
- **A renamed project.** Projects get renamed and tickets moved, and a search on an old project key returns nothing, without an error. `tickets.py` says when a ticket or a project has moved: use its current key from then on.

A ticket that a document names but that doesn't exist is a finding: the documentation and the tracker disagree.

### Reading the code

Read the code pinned to a commit on the main branch, so every claim names the revision it holds for. For a repository you read beyond a few files, clone it into your scratch folder without file contents (`git clone --filter=blob:none`) and check out that commit; for a few files, or for pull requests, use the CLI.

Record each file or folder you read, and how deeply, as file coverage: a component is Implemented or In development only once the code behind it is recorded as read.

Before concluding something doesn't exist, look where it could be hiding: active branches, open pull requests, and the history, for something merged and later removed. Record where you looked.

### Building the system design

Collect enough to draw an accurate diagram of the system, as it is today and as the target describes it. Each piece you're missing is a question for the queue. Each piece has its own table in the ledger, and each row cites the findings it rests on.

1. **Components:** every part that runs, stores or talks across a boundary, such as a service, job, library that calls out, store, queue or external product, and the people or roles that act on it. Each has a type, a [state](#sources-and-evidence) and the boundary it sits in. Challenge a generic noun, such as "platform" or "gateway": what runs where, called by whom, and what proves it exists.
2. **Connections:** who calls whom, how (HTTP, queue, file, SDK), in which direction, with what data, whether the caller waits for a reply, and with which identity.
3. **Boundaries:** what groups components, such as a network, an environment, a trust zone or the team that owns them.
4. **Identities:** the credentials or accounts connections use, and what each can reach; several connections often share one.
5. **Main flows:** for each entry point that matters, the connections it uses, in order.
6. **Unknowns:** a component or connection you can't establish is recorded with the state Unverified, linked to the gap that explains it; a caller you can't identify is a component of unknown type. Never guess one.

### When research is finished

Research is finished when `ledger.py next` returns nothing and no question is in progress: each one is answered, or blocked by something you can't do yourself.

## 3. Review

When research is finished, have the ledger reviewed by someone who didn't build it: a subagent given only the brief below. Change nothing while it runs.

> Read the research ledger at `<ledger path>` in full. It must answer three questions: the vision, purpose and impact; the current status, what is done, how it works (its system design today) and what is in progress; and the direction, with the system design it targets. Judge whether it does, and list only significant issues: a question that should have been asked and wasn't, or a finding that claims more than its sources show. An issue is significant only if settling it could change one of the three answers. Leave out completeness for its own sake, cosmetic points and improbable cases. For each issue, say what would settle it.

Judge each issue yourself by the same test, and drop any that couldn't change an answer. Add every one left to the queue as a question, with its dependencies, before you change anything. Record the round with `ledger.py review --raised <the questions, or none>`, then go back to [2. Research](#2-research) for them.

The review is finished when a round raises nothing. A good investigation needs one or two rounds; after three, before starting a fourth, show the user what each round found and ask whether to go on. If they stop, record it with `ledger.py review --stopped '<what they said>'`.

## 4. Write

The report has two layers, which don't repeat each other. The executive layer, for a technical leader, says what the system is for, where it stands, where it is going and what needs deciding, with no configuration detail. The architect layer, for engineers, says how it works and how it will change, with no ticket status or plan.

1. **Read the brief:** `ledger.py brief` prints everything the report rests on, from the ledger as it stands. Write from it, not from memory.
2. **Write `content.json`**, one field per section below, each claim linked to the ledger, such as `[F03](ledger:F03)`. Write it through the shared writer, the same way for every revision; its `--help` shows how to change part of it later. It holds only the sections; the script writes the title, the evidence date and the references, from the ledger. The first write, which shows the file's shape:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py --name tech-investigations --path '<investigation>/content.json' <<'END_OF_FILE'
   {
     "purpose": ["Paragraph [F01](ledger:F01)."],
     "current_status": ["Paragraph [F02](ledger:F02)."],
     "direction": ["Paragraph [F07](ledger:F07)."],
     "key_decisions": [
       {"decision": "Which queue to use", "why": "It sets the replay cost", "position": "Unresolved", "evidence": "[D01](ledger:D01)"}
     ],
     "architecture": {
       "today": {"summary": ["Paragraph [C01](ledger:C01) [E01](ledger:E01)."]},
       "target": {"summary": ["Paragraph [F07](ledger:F07)."]}
     },
     "open_choices_and_gaps": [
       {"decision": "Retry limit", "why": "Sets how long a payment can hang", "position": "Not decided", "evidence": "[G01](ledger:G01)"}
     ]
   }
   END_OF_FILE
   ```

3. **Generate the report** with `python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py --investigation <investigation>`. It writes nothing until `content.json` is valid, and lists every problem to fix. Never edit the report: change `content.json` and run it again.

**Report, don't recommend.** The report describes what the evidence shows. It never adds your own recommendations, preferred options, plans or owners; what the sources don't settle is reported as open.

### The executive layer

Approximate lengths are room to explain, not quotas: write less when the point is simple or the evidence thin.

- **Problem and purpose** (`purpose`, about 150 words): the problem, who it affects, why it matters and the intended outcome, in plain language. End with each topic the boundary marked mention only, in one line on how it connects.
- **Current status** (`current_status`, about 200 words): what is done, what is in progress, and the gap between them, keeping implemented, in development and planned apart, as the [states](#sources-and-evidence) do. Name the evidence limits that matter, such as a source you couldn't read.
- **Direction** (`direction`, about 200 words): what comes next, in the order the sources give, separating what the tracker plans from what only the documentation proposes. Give timing only where a source commits to it.
- **Key decisions and risks** (`key_decisions`): only the decisions, blockers and risks that need a leader's attention, each with why it matters and its evidence. An empty list is fine.

### The architect layer

Cite the system design's rows, such as a component (C03) or a connection (E05), as well as findings, so an engineer can go from a sentence to what it describes.

- **How it works today** (`architecture.today`, about 300 words): the system design as the ledger records it, saying why each main component exists, not only its name. Cover the entry points, the boundaries of trust, data and identity, and the technical limits, and mark what is only in development.
- **Target design** (`architecture.target`, about 300 words): what the target keeps, adds, changes or removes compared with today, and why, from the tracker and the documentation. Keep what the tracker plans apart from what only the documentation proposes, and name the technical choices still open.
- **Open technical choices and gaps** (`open_choices_and_gaps`): the choices and evidence gaps that matter to the target, each with why it matters and its evidence. Look where the sources disagree: vision with no ticket, a ticket with no code, code the design doesn't mention, and a ticket status the code contradicts.

### Diagrams

To decide: drawn from the ledger's system design, or written by hand.

## 5. Hand over

1. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py --report '<absolute report path>' --handover`, and fix every error it reports.
2. Tell the user the report is ready, with the full paths of the report and the ledger. Don't recap the report; add only a doubt about your own judgment that it doesn't show. If the folder is temporary, say so and offer to copy the report and the ledger.
3. Offer to keep the report as an example for future investigations. If the user says they're happy with it, keep it with `python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py --investigation <investigation> --note '<one line on what makes it good>'`.
