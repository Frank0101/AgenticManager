---
name: agentic-manager-tech-investigation
description: Investigates a technical system, proposal, capability or engineering problem by triangulating the team's documentation (the vision), work tracker (the delivery) and source control (the implementation), and iterates until it converges on an evidence-backed account of the current state, the current milestone and the directional target architecture, with a fixed executive/product layer and architect layer, one Mermaid sequence for each architect section with the design of the components it crosses, and a detailed research queue and evidence ledger. Also produces short outputs, such as an exec summary, from the same full investigation. Use when the user asks to investigate, map or explain a system or proposal, asks what exists today versus what is planned, or asks for its architecture, current milestone, first iteration or target state.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/extract_saved.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_investigation.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_summary.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/ledger.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/output_diagram.py *)
---

# Tech Investigation

Investigates a technical system, proposal, capability or engineering problem, and produces the clearest evidence-backed account of:

1. What exists today, and how it works end to end.
2. What is being delivered now: the current milestone.
3. What the directional target architecture could become.
4. What the sources say will be kept, changed or built, and which decisions and evidence gaps remain open.

The result must make sense to a new reader, be useful to the engineers who build it, and stand up against the evidence.

You do the research and write what needs judgment: the ledger's content and the report's text (`content.json`). Scripts own everything mechanical: the folder, the ledger's tables and allowed values, links, the report's template and the checks. The folder is `tech-investigations` in the output root the user set in the config (`output.root`), or a temporary folder if none is set: scripts choose it and write in it, and you never read the config. When a script refuses something, its message says what it accepts: fix the input, never work around the check.

The work has five phases: [Define](#1-define), [Research](#2-research), [Write](#3-write), [Review](#4-review) and [Hand over](#5-hand-over). `ledger.py status` ends with a `next:` line naming the phase you are in and what to do; check it whenever you're unsure, and follow it.

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill needs sources of three groups, each the evidence for one side of the picture:

| Group            | Called here       | Evidence of        | What to look for                                                                  |
| ---------------- | ----------------- | ------------------ | --------------------------------------------------------------------------------- |
| `documentation`  | the documentation | The vision         | Intent, architecture, decisions, proposals, constraints, meeting notes, outcomes. |
| `workflow`       | the tracker       | The delivery       | Scope, acceptance criteria, owners, progress, dependencies, blockers.             |
| `source_control` | the code          | The implementation | Code, configuration, infrastructure, tests, workflows, pull requests, releases.   |

Use every enabled source of these groups whose channel is `mcp` or `cli`; one reached through `api` or `fs` needs a script this skill doesn't have, so tell the user it isn't used. If no group has a usable source, stop and show each group's `mcp` and `cli` sources with their `setup` and the config `path`. If one or two have none, say which, with the same details, and ask whether to go on without them; if the user agrees, those groups are unavailable (see [Unavailable sources](#unavailable-sources)).

It also needs Node.js 22.13 or newer, to draw and check the diagrams: `init_investigation.py` stops with a message if it is missing.

## Working with the scripts

`<scripts>` is `${CLAUDE_SKILL_DIR}/scripts` and `<lib>` is `${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager`: call them by exactly these paths, so they run without a permission prompt. Each prints one line of JSON (`ledger.py`'s `status`, `find`, `show`, `brief` and `help`, and `extract_saved.py`, print plain text), or what's wrong on standard error with a non-zero exit. `<investigation>` is the folder name `init_investigation.py` prints. A script's `--help` gives its arguments.

Write the ledger only through `ledger.py`, and `content.json` and a short output's `<format>.json` only with `<lib>/output_file.py --name tech-investigations --path '<investigation>/<file>'`, the file's whole content on standard input; never with your own file tools. Never edit the report: change `content.json` and run `make_report.py` again. Working files, such as a diagram being tried or a row written to a file, go in your own scratch folder.

The investigation's folder holds only these files, and the handover check fails on any other.

```text
tech-investigations/
├── _examples/                             save_example.py writes, the documents the user approved
│   └── Payments-Retry-Service_26-10-05--long-analysis/
│       ├── description.md                 what makes it good
│       ├── Payments-Retry-Service_Report.md
│       └── ledgers.md
└── Payments-Retry-Service_26-10-05/
    ├── ledgers.md                         init_investigation.py and ledger.py write
    ├── content.json                       you write
    ├── Payments-Retry-Service_Report.md   make_report.py writes
    ├── exec-summary.json                  you write, only for a short output
    └── exec-summary.md                    make_summary.py writes, only for a short output
```

## Rules that hold throughout

### Code is the source of truth

Read the code: entrypoints, routes, handlers, configuration. A README, a file listing or a search hit says what someone meant, not what the code does. A component is 🟩 or 🟨 only once its code is read, and `ledger.py` refuses those statuses until file coverage at depth `full` or `entrypoints and routes` exists under its path. Merged code establishes implementation; deployment is a separate claim that needs configuration or deployment evidence for a named environment and revision. An open pull request is a candidate, not the merged state.

### Evidence authority

One chain of authority holds for every claim: **code → tracker → documentation**. When two sources disagree, the earlier one wins.

- **The tracker explains delivery:** why, scope, dependencies, the milestone. A Done ticket can't prove implementation.
- **Documentation supplies vision and intent.** Even an approved document can't override code or the tracker.
- A clue from documentation or the tracker becomes a current-state fact only after you trace it to code. Until then it is a proposal; if you can't trace it, the claim stays Unverified.
- Classify a claim by its evidence, not where it is stored: a design note in a repository is vision; a runbook or status note is reported operational state, so the claim stays unverified.
- Keep conflicts and how they were resolved in the ledger. Within code, name the revision and environment; don't combine different states. Bound a negative claim to the exact query, paths and revision searched.
- Material the user pastes is reported context: label it, never let it establish implementation, delivery or intent, and record it in the boundary section.
- A link inside a primary source may be followed whatever tool it points to; other enabled groups (a local vault, messaging) aren't primary sources, so don't search them.

### Stay on the topic you were asked

Investigate what the user asked, with common sense about what it includes. When you find a connection to something outside it and can't tell whether it belongs (a sibling project, a shared platform, an older product with the same name), ask the user: "I see a link to X; do you want it in the investigation?" Record the answer in the ledger's `## Boundary, method and access`. If no answer comes, leave the topic unresearched, as a gap blocked by "Asked the user, no answer" naming the question, and carry on with the rest. Never include or leave out a topic on your own, and never present a general instruction as the user's answer to a specific question.

A request for a short output (an exec summary, "100 words") is about the format, never the scope or rigor: do the full investigation, then compress it.

### Read as deep as the claims need

How deep to read is your judgment, never a question for the user: they asked for the investigation because they don't know these details. Read whatever could change a claim, status, decision or gap in the report. Leave a file, pull request, ticket or document unread, or read it only in part, when nothing resting on it could change, and record what you left and why, in its file coverage row or in the outcome of the action that closes it, citing the findings that rest on it. Ask the user only about scope ([Stay on the topic you were asked](#stay-on-the-topic-you-were-asked)).

### Data and secrets

Read code, configuration and structure, never data files holding customer or personal data: describe such a corpus by its schema and controls. Configuration often holds secrets, encrypted or not: when you read a config file, print key names only, never the values under a secrets section, and never copy a secret into the ledger or the report.

### Report, don't recommend

The report describes evidence in the ledger. The target and future milestones may be reconstructed from the tracker and documentation, as long as documented decisions, source-authored proposals and labelled inferences stay distinct and cited. Never add your own recommendations, preferred options, milestones, sequencing, retirement plans or owners; what the sources don't establish is reported as unresolved.

### Unavailable sources

A source is unavailable when its group has none usable, a call errors, it comes back empty for access reasons (permission denial, single sign-on block, a 404 on something a document names), or you chose not to check it. Say so in the same response, before any conclusion. Try a fallback first (another query, source or tool). Then carry on with the rest, mark the conclusions that depend on it **Unverified**, record what to check once access exists, and never fill the hole with assumptions.

## The process

### 1. Define

Infer the topic, starting questions, provisional boundary and a destination page if named; ask only when ambiguity materially changes the investigation. Choose a short `<Topic>`, capitalised words joined by hyphens (honour a name the user gives), and run `<scripts>/init_investigation.py --topic <Topic> --format <format>`, where `<format>` is `long-analysis` or the short format asked for. Every run starts from scratch: never read or reuse what an earlier run left, on this or another day. Skim an approved example of that format for tone only, never for facts.

Run `ledger.py help` ([The ledger](#the-ledger)), then write the boundary and the first queue actions in the ledger before any substantive research.

### 2. Research

Repeat this loop for each action, or a small coherent batch, while the evidence is in front of you:

1. **Pick** the ready action whose answer could most change the architecture, the milestone or a conclusion; `status` shows which evidence areas each group hasn't covered yet. Run `find --text <source or term>` first and use what the ledger already holds.
2. **Read, then record the source at once**, with its exact reference, revision, what you read at what depth, and its areas. For code, add a file coverage row per file or folder read. Coverage rebuilt from memory afterwards is a guess.
3. **Write the findings**, one claim each, citing the source IDs, and update the component rows.
4. **Queue the follow-ups**: every new question, clue, contradiction or dependency that could change the report ([Read as deep as the claims need](#read-as-deep-as-the-claims-need)) is its own action, split by component, entry path or delivery question, never an umbrella like "read repositories". Then close the action with the findings, decision or gap that answer it.
5. **Refresh** `## Resume here` after a material discovery and before switching repository or source group.

What to read:

- **Documentation:** current and older designs, proposals, decision records, meeting notes, security analyses, runbooks. Note for each whether it describes the current or target state, its last edit, and whether newer evidence supersedes it.
- **Tracker:** the epics, stories, spikes and bugs on the topic and the identifiers documents name, in full: description, status, acceptance criteria, dependencies, decision comments, links. In a list query ask only for key, summary, status and parent. If a result is too large and saved to a file, list what you need from it with `<lib>/extract_saved.py --path <file> --fields key,fields.parent.key,fields.parent.fields.summary,fields.status.name,fields.summary`, rather than searching again, reading it whole or writing code to read it. A ticket a document names that doesn't exist is a finding. Projects get renamed and tickets moved, and a search on an old project key then returns nothing without an error: before concluding a project or ticket has nothing, open one of its tickets directly, which resolves to its current key. Search under the current key from then on, and record the move as a finding.
- **Code:** confirm the CLI is signed in, then search and read code, configuration, infrastructure, secrets wiring, CI/CD, manifests and tests, pinned to a commit. Clone each repository you read beyond a few files into your scratch folder, blobless (`git clone --filter=blob:none`), check out the pinned commit and read it there, as should any subagent you delegate to; use the CLI for pull requests, workflow runs, releases and a few files of a repository you only touch. Use the owner the documents and tickets point to, or ask. Before concluding something doesn't exist, check active branches, open and recently merged pull requests (following stacked bases), and history for experiments merged and later removed. Record release, development baseline and open candidates separately.

Build the **component inventory** as you go: every deployable or runnable unit and every library that talks outside its process, plus components documents or tickets name even without code. For each material one, read the code needed to establish what it does, who calls it, what it calls (HTTP, queues, SDKs, files), its configuration, network policies and credentials.

- Tell services apart from libraries, jobs, stores, external products and logical capabilities.
- Challenge generic nouns (platform, gateway, pipeline): what runs where, called by whom, with what data and credentials, and what proves it exists.
- Units of a shared repository unrelated to the topic are excluded with a reason, not read.
- If you delegate reading to a subagent, ask for exact revisions, coverage and connections, returned as the input of `<scripts>/ledger.py batch` (its `help --table batch` shows the shape): source rows, file coverage rows and draft findings. Check that the coverage supports its claims and correct what doesn't before writing them with `batch`.

Research is finished when nothing is left ready: every material component and connection is supported at the level its status claims, or has a gap blocked by something you can't do yourself (`ledger.py help --table gaps` lists the accepted blockers).

### 3. Write

1. **Read the brief once, in full:** `<scripts>/ledger.py brief --investigation <investigation>` prints everything the report rests on from the ledger as it stands, without the queue and research notes. Write from it, not from memory or what earlier commands printed.
2. **Write `content.json`** ([The report](#the-report)) and run `<scripts>/make_report.py --investigation <investigation>`. It writes nothing until `content.json` is valid, and lists every problem.
3. **Read the generated report start to end, as each of its readers would:** an architect (are the boundaries right?), an engineer (can the code be found?), a delivery lead (does it match the tickets?), an SRE (are execution, identity and credentials concrete?), a security reviewer (are data and trust boundaries visible?), a product owner (is the milestone deliberate?), a new reader (can the flow be followed alone?). Every question this raises is a queue action: answer it from the sources, update the ledger and every part of the report it touches, and regenerate. When an explanation needs repeated qualification, fix the model (a box with two responsibilities, one name for several things) rather than adding prose.

### 4. Review

Only when nothing is left to research and the report is drafted, start an independent review: a subagent (the Agent tool, general-purpose) given only this brief. "Read the research ledger at `<ledger path>` and the report at `<report path>` in full, and list the real issues. A real issue would change a claim, status, decision or gap in the report once dealt with, or is a place where the ledger contradicts the report: a claim that is wrong or unsupported by its evidence, an action left open or closed without a clear reason, or a part left unread or read in part that could change a claim resting on it. A part left unread is not an issue when nothing resting on it could change. For each, say whether the agent could do it now with the tools and sources the ledger already uses, and what exactly it would run or read. Then list separately, in a line each, the record fixes: inconsistencies inside the ledger that change nothing in the report, such as a stale cell or a missing citation. Judge the work, not whether you would conclude differently, and leave out improbable corner cases, cosmetic preferences and defensive additions." Change nothing while it runs.

Judge each issue it calls real against the brief's definition yourself: one that would change no claim, status, decision or gap in the report is at most a record fix, and an improbable or defensive one is dropped. Every real issue left that it marks doable becomes a ready action; one that can't be done is a gap with its blocker, if it isn't one already. Apply the record fixes at once: they don't open another round. Then record the review with `ledger.py review --raised <the actions its real issues became, comma separated, or none>`, go back to research for those actions, and tell the user in a few lines what it found and what you did.

Once they're done, run another round with the same brief, until one raises no action; the handover check requires that last round. A strict reviewer can keep finding something, so after three rounds, before starting another, show the user in a few lines what each round found and ask whether to go on; if they choose to stop, record it with `ledger.py review --stopped '<what they said>'`, which ends the review as such a round does.

### 5. Hand over

Write `## Reflection` (`ledger.py text --section Reflection`): what changed between the first and final drafts, which assumptions were disproved, which conclusions depend on unavailable evidence, which decisions need a human owner, and why another round is unlikely to help. Run `check_report.py --report '<absolute report path>' --handover` and fix every error. Then:

- Link `ledgers.md` and the report by their full absolute paths. Don't recap the report; name every unavailable source and what it leaves unverified, and add any doubt about your own judgment the report doesn't show.
- List your depth calls in a few lines: each source a report claim rests on that you left unread or read only in part, and why the claim doesn't depend on the rest, so the user can ask for more.
- For a short format, compress the finished report, adding nothing it doesn't say: write `<investigation>/<format>.json` and run `<scripts>/make_summary.py --investigation <investigation> --format <format>`, then show the result and link the full report. Its shape is `{"title": "Optional heading", "max_words": 100, "body": ["Markdown blocks"]}`; set `max_words` only to a limit the user gave.
- For a destination page in an enabled `documentation` source, show what you'll write and publish only after the user approves.
- If the folder is `temporary`, say so, offer to copy the document, and mention that setting `output.root` keeps investigations and examples.

End by offering to keep the document as an example for future investigations. When the user says they're happy with it, keep it: `save_example.py --investigation <investigation> --file <document> --format <format> --note '<one line on what makes it good>'`.

## The ledger

`ledgers.md` is the research record behind the report, with far more detail than the report, kept while you research. Use stable IDs: `Q` actions, `S` sources, `F` findings, `C` components, `D` decisions, `G` gaps.

**`ledger.py help`** prints every command with its input and a command to copy, and for each table its columns, the values each column accepts and a worked row. Read `ledger.py help --table <name>` before writing one for the first time, and copy its command. `ledger.py` refuses a row that breaks a rule the handover check applies, and warns when a row cites an ID not recorded yet or a finding's claim runs far past its length.

Never open the ledger while you research: `status`, `find --text`, `show --id` and `next-id --kind` answer what you need. The ledger stores IDs and links rewritten, so to edit a finding, a row or a section, read it as written with `show --raw`, change it and write it back: what you didn't change stays the same.

Links: write `[text](url)` anywhere, and ticket keys, pull requests (`owner/repo#123`) and IDs plainly: `ledger.py` links them for you, a ticket or pull request once the ledger links any ticket of its project or page of its code host, such as in a source row. Put anything else in backticks only inside a link to its pinned revision; otherwise write it as plain words. Link everything a claim rests on, so any claim can be followed to its source, and the source to its exact reference.

What each part is for:

- **Resume here:** scope and phase, decisive findings, the next actions and why, blockers, review state. Read it first when resuming.
- **Research action queue:** Priority Critical for a wrong current-state claim, High for an unsupported claim or wrong boundary, Medium for incomplete validation, Low for presentation. A blocked action names its gap or decision; a completed one, the findings, decision or gap that answer it, or the user's choice not to pursue it, written only after they said so.
- **Boundary, method and access:** the topic's boundary, the user's answers on scope, sources used and not used, skipped report sections and why.
- **Source register and file coverage:** every source with an exact reference: a link pinned to a commit for code, a search's exact query in backticks. File coverage, each file or folder read and how deeply, is what makes a component's status believable.
- **Findings:** one claim each, about 80 words: a topic with ten facts is ten findings. Its Kind is observed implementation, configured/deployed state, delivery context, documented vision, inference or proposal; its Evidence, source IDs plus a precise location where the register isn't enough; its Validation and limits, the deepest level reached and what stays uncertain.
- **Component inventory:** every material component, with deployment recorded separately from implementation.
- **Open decisions:** choices that wait on a person.
- **Evidence gaps:** what would close each gap and what blocks it. A gap nothing blocks is work you can do now, so it is a ready action instead.

Record only what has happened: never write a review, correction or answer before it takes place.

## The report

`<Topic>_Report.md` has two layers, an executive/product summary and an architect summary. `make_report.py` owns the template; you write `content.json`:

```json
{
  "title": "<Technical topic>",
  "skip": [],
  "evidence_snapshot": "2026-10-05",
  "problem": ["Paragraph."],
  "current_status": ["Paragraph."],
  "next_steps": ["Paragraph."],
  "key_decisions": [
    {
      "decision": "Decision or risk",
      "why": "Why it matters",
      "position": "Established position",
      "evidence": "[F03](ledger:F03)"
    }
  ],
  "architecture": {
    "current": {
      "summary": ["Paragraph."],
      "sequence": {
        "title": "Helpdesk API — ticket search",
        "lines": [
          "actor U as Client / operator",
          "participant H as Helpdesk API",
          "U->>H: Search tickets",
          "H-->>U: Results or error"
        ]
      }
    },
    "next": { "summary": ["Paragraph."], "sequence": { "...": "..." } }
  },
  "decisions_and_gaps": [
    {
      "decision": "Decision or gap",
      "why": "Why it matters",
      "position": "Established position",
      "evidence": "[G01](ledger:G01)"
    }
  ],
  "references": {
    "implementation": ["[README](https://...)"],
    "delivery": [{ "text": "[PROJ-123](https://...)", "historical": true }],
    "vision": []
  }
}
```

`evidence_snapshot` is the date you last checked the evidence. Every claim traces to the ledger: link it as `[F03](ledger:F03)`, and the script fails a paragraph, `flow_gap` or `evidence` without one. Name roles, never people. Lead with plain English, then the technical terms; explain why a component exists, not only its name; make uncertainty explicit, and never overstate completeness when a source was unavailable. Word counts below are approximate targets, room to articulate rather than quotas: write fewer when the point is simple or the evidence thin.

**The two layers do different jobs and don't repeat each other.** The executive layer, for a technical leader such as a CTO, says what the capability is for, where it stands, what is planned and what needs deciding: maturity, the milestone, delivery progress, dependencies, risks. It reads on its own and has no configuration detail. The architect layer, for engineers, says how it works: components, interactions, boundaries of identity, data and trust, technical constraints and open technical choices, with no tracker status, milestone or plan. A fact belongs to one layer; the other may use it in a clause where its argument needs it.

**The current milestone** comes from the tracker (the active epic, milestone or sprint goal), and the report says so; if none is defined, it is not established, never proposed. At the start of a project it is the first practical iteration. With several tracks, it is the active epic's; work outside that epic is candidate context. If that epic holds only discovery work, the discovery is the milestone, however large a goal a document states. A documented goal the tracker doesn't carry belongs in Next steps, labelled as documentation. Keep its exclusions visible, and don't let target-state scope creep into it.

The fields:

- **`problem`** (about 150 words): the problem, who it affects, why it matters and the intended outcome, in plain language.
- **`current_status`** (about 200 words): where things stand, what the current milestone should achieve, the gap between them, scope boundaries and principal dependencies. Keep implemented code, verified deployment and ticket-reported progress distinct, and keep material evidence limits.
- **`next_steps`** (about 200 words): the next milestones in their evidenced order and the broader direction, separating committed work from proposals and documented vision, with timing only where a source commits to it.
- **`key_decisions`:** only decisions, blockers, risks and uncertainties that warrant leadership attention. An empty list is fine.
- **`architecture.current`** (about 300 words): how it works today, entry paths, boundaries, technical limits, deployment gaps in configuration terms, what is only a candidate. Its sequence is the main flow.
- **`architecture.next`** (about 300 words): what is retained, added, changed or retired compared with Current, why, and the technical choices still open. When the milestone is discovery work, show what its tickets would build as proposed components and end the sequence in the human decision it informs.
- **`decisions_and_gaps`:** the open technical choices and evidence gaps that matter to the next steps. Look for vision with no ticket, a ticket with no code, code the design doesn't mention, statuses that disagree with code, and missing deployment evidence. Don't invent alternatives.
- **`references`:** every material code reference, ticket, document and pull request, with superseded ones marked `historical`.

**Sections that don't apply:** list `architecture` in `skip` when the subject isn't a system of components (a practice, a team choice), and `evolution` when the sources establish that nothing is changing it, not when they are silent. Skipping shapes the output, never the research. Record each skip and its evidence in the boundary section.

## Diagrams

Each architect section ends with one Mermaid sequence, built only from ledger findings: tie each interaction to a finding that supports its endpoints, and where a caller or target isn't established, mark it unresolved in a note rather than inventing a call. When the evidence supports no flow, write `flow_gap` in its place: why there is none, linked to its gap.

- One flow per section, the one that explains most; say in the text what it leaves out. Don't merge independent entry paths into one fictional operation.
- Every participant is a component of the ledger, named as in its Name and type cell without the type ("Search API" for "Search API (service)"), optionally with a qualifier in brackets; `make_report.py` refuses any other. Declare a person with `actor`, named by role, such as "Client / operator (source owner)". Show an internal module as an action of its service.
- Group the participants inside a trust, network or deployment boundary in a `box` named after it, with a colour only as `rgb()`.
- The script also draws the flow's design from the sequence: its components, coloured by status and shaped by the type in their Name and type cell (a store, a queue, topic or stream, an external product), with an arrow per request and the boxes as groups. So write a request as a solid arrow and a reply as a dashed one: only solid arrows appear in the design.
- Label unmerged work as candidate in the title or a note, and never draw a proposed interaction as if the code had it.
- Keep material data and credential boundaries, and failure and human-decision paths.
- The script adds `sequenceDiagram` and `autonumber` and refuses what Mermaid can't draw; `output_diagram.py --png` previews one.
