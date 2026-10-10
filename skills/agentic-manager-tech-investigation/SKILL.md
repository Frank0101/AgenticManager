---
name: agentic-manager-tech-investigation
description: Investigates a technical system, proposal, capability or engineering problem by triangulating the team's documentation (the vision), work tracker (the delivery) and source control (the implementation), and iterates until it converges on an evidence-backed account of the current state, the current milestone and the directional target architecture, with a fixed executive/product layer and architect layer, one Mermaid sequence diagram for each architect section, and a detailed research queue and evidence ledger. Also produces short outputs, such as an exec summary, from the same full investigation. Use when the user asks to investigate, map or explain a system or proposal, asks what exists today versus what is planned, or asks for its architecture, current milestone, first iteration or target state.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_investigation.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_summary.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/ledger.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/output_diagram.py *)
---

# Tech Investigation

Investigates a technical system, proposal, capability or engineering problem, and produces the clearest evidence-backed account of:

1. What exists today, and how it works end to end.
2. What is being delivered, and what the current milestone is: the one being delivered now, which is the first practical iteration when the work is just starting.
3. What the directional target architecture could become.
4. What the sources say will be kept, changed or built, and which decisions and evidence gaps remain open.

The result must make sense to a new reader, be useful to the engineers who build it, and stand up against the evidence available.

The investigation's files are written to the `tech-investigations` folder of the output root the user set in the config (`output.root`), or to a temporary folder if none is set. Scripts give you that folder and write the files in it (see [Saving files](#saving-files)); never choose a folder yourself, and never read the config to find it.

You do the research and write what needs judgment: the ledger and the report's text (`content.json`). Scripts own everything mechanical: the folder, the ledger's skeleton, the report's template, and the checks.

## Prerequisite

Run the config check, by exactly this path so it runs without a permission prompt:

```bash
python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py
```

It prints one line of JSON. If it fails (`"ok": false`), stop here: show the user its `errors` and `path`, and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ available as `python3`, and stop; if the script is missing, tell them to reinstall every skill, and stop. On success, `sources` lists every supported source by group, each with its `tool`, `channel`, whether it is `enabled` and, if not, how to enable it in `setup`; follow `next_steps` too if it is there.

This skill needs sources of three groups, each the evidence for one side of the picture:

| Group            | Evidence of        | What to look for                                                                  |
| ---------------- | ------------------ | --------------------------------------------------------------------------------- |
| `documentation`  | The vision         | Intent, architecture, decisions, proposals, constraints, meeting notes, outcomes. |
| `workflow`       | The delivery       | Scope, acceptance criteria, owners, progress, dependencies, blockers.             |
| `source_control` | The implementation | Code, configuration, infrastructure, tests, workflows, pull requests, releases.   |

Use every enabled source of each group whose channel is `mcp` (its MCP tools) or `cli` (its command-line program, through bash). Sources reached through `api` or `fs` need a script this skill doesn't have, so skip them; if one is enabled, tell the user it isn't used here.

- If none of the three groups has a usable source, stop and tell the user which `mcp` and `cli` sources each group has, showing their `setup` and the config `path`.
- If one or two groups have none, tell the user which, with those sources' `setup` and the config `path`, and ask whether to go on without them. If they agree, treat those groups as unavailable (see [When a source is unavailable](#when-a-source-is-unavailable)).

It also needs Node.js 22.13 or newer, which draws and checks the sequence diagrams. `init_investigation.py`, the first script you run, stops with a message if it is missing: tell the user to install it, and run the script again once they have.

Other enabled groups, such as a local vault or messaging, aren't evidence for this skill; don't use them. Material the user supplies, such as a pasted message or document, may be used as reported context only: label it as reported, never let it establish implementation, delivery or intent, and record the exception and its source in the ledger's `## Boundary, method and access`. Classify each claim by its evidence, not where it is stored: a ticket's status is delivery evidence, a design note is vision evidence even in a repository, and neither proves implementation. A runbook or status note in a repository is reported operational state: label it as reported and keep the claim unverified. Read code, configuration and structure, never data files holding customer or personal data; describe such a corpus by its schema and controls.

## Saving files

`<lib>` is the shared library's folder, `${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager`, and `<scripts>` this skill's `scripts` folder, `${CLAUDE_SKILL_DIR}/scripts`. Call the scripts by exactly those paths so they run without a permission prompt. Each prints one line of JSON, or what's wrong on standard error with a non-zero exit (`make_report.py` and `check_report.py` report a failed check as `"ok": false` and an `errors` list in that JSON, also with a non-zero exit); handle the cases named below, and otherwise stop and report it. `<investigation>` is the folder name `init_investigation.py` prints.

| Script                                                                        | What it does                                                                                                                                     |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `<scripts>/init_investigation.py --topic <Topic> [--format <format>]`         | Creates the investigation's folder, replacing one of the same topic and day, with its ledger skeleton, and lists the approved examples (step 1). |
| `<scripts>/make_report.py --investigation <investigation>`                    | Writes `<Topic>_Report.md` from `content.json`, then checks it ([The document](#the-document)).                                                  |
| `<scripts>/make_summary.py --investigation <investigation> --format <format>` | Writes a short output, `<format>.md`, from `<format>.json` (step 6).                                                                             |
| `<scripts>/check_report.py --report '<absolute report path>' [--handover]`    | Checks the report, its local files and the ledger's structure, read-only (step 5).                                                               |
| `<scripts>/ledger.py <command> --investigation <investigation> ...`           | Edits and reads the ledger by ID ([The ledger](#the-ledger)).                                                                                    |
| `<scripts>/save_example.py ...`                                               | Keeps an approved document as an example (step 7).                                                                                               |
| `<scripts>/output_diagram.py [--png] < diagram.mmd`                           | Renders one sequence to try it, writing nothing to the folder: its `width` and `height`, and a PNG preview with `--png`.                         |

Write your own files, `ledgers.md`, `content.json` and a short output's `<format>.json`, with the library's `output_file.py`, never with your own file tools. It takes the file's whole content on standard input, replaces the file if it exists, and creates missing folders. `--path` is relative to the skill's output folder, `tech-investigations`:

```bash
python3 <lib>/output_file.py --name tech-investigations --path '<investigation>/<file>' <<'END_OF_FILE'
<the file's whole content>
END_OF_FILE
```

For a small update, read the affected text and add `--patch`. Standard input is then a JSON array of exact replacements:

```json
[{ "old": "Unique existing text", "new": "Updated text" }]
```

Each `old` must match exactly once; a missing or ambiguous match leaves the file unchanged, so reread the section and retry with more context. In `content.json`, `old` and `new` are JSON text, escapes included. Use full writes for new files or substantial reorganisations. For the ledger's tables use `ledger.py` instead of a patch (see [The ledger](#the-ledger)).

Never edit the report: change `content.json` and run `make_report.py` again. Working files (a diagram being tried) go in your own scratch folder, not the investigation folder.

## Evidence authority

Every claim follows one chain of authority, from most to least authoritative: **source_control → workflow → documentation**. When two sources disagree, the earlier one wins, for every kind of claim.

- **Code and configuration are the source of truth for current status.** Merged code establishes implementation. Deployment is a separate claim that needs configuration or deployment evidence for the environment and revision. An open pull request is a candidate change, not the merged state.
- **The work tracker explains delivery:** why changes were made, their scope, dependencies and the wider milestone. A Done ticket cannot prove implementation.
- **Documentation supplies vision and intended direction.** Even approved documents cannot override code or the tracker.
- Keep a discrepancy and its resolution in the ledger. Within code, identify the revision and environment; don't combine different states.
- A clue from documentation or workflow generates validation actions down to source control before it becomes a current-state fact; until then it is a proposal. If validation is blocked, keep the claim and mark implementation unverified.
- Starting from code, follow workflow and documentation for purpose and milestone context. Their absence doesn't invalidate an observed implementation fact.

### Reporting contract

The report describes evidence recorded in the ledger; it doesn't recommend a design or delivery plan. Future milestones and the target may be reconstructed from the tracker and documentation without implementation evidence, as long as you distinguish documented decisions, source-authored proposals and clearly labelled inferences, and cite the sources, including for inferred direction.

Don't introduce your own recommendations, preferred backends, new milestones, sequencing, retirement plans or suggested owners. Your own proposal in the ledger isn't evidence. If the sources don't establish a choice, disposition or owner, report it as unresolved, and never invent decommissioning to make an evolution look complete. Showing a component as replaced in a future stage describes the reconstructed design, not a retirement plan. Rendering uses the ledger's established findings only: if a missing fact needs research, go back and update the ledger first.

### When a source is unavailable

A source is unavailable when its group has none usable, a call errors, it comes back empty because of access (a permission denial, a single sign-on block, a 404 on a resource a document names), or you decided not to check it. Then:

1. Say so in the same response, before any summary or conclusion.
2. Try a fallback first: another query, another enabled source of the group, or another tool of the source. Mark the source unavailable only when that fails or none exists.
3. Go on with the available sources, mark the conclusions that depend on the missing one **Unverified**, and record what to check once access is available.
4. Never replace missing evidence with assumptions. When implementation couldn't be checked, label documentation and delivery claims (a Done ticket, a document describing existing code) as vision or delivery claims, never as implementation fact.

## Doing the research

### Principles

- Begin with the simplest truthful explanation: what we are trying to achieve, why, what the current milestone is, and what happens from beginning to end. Earn complexity with evidence.
- Keep current implementation, current delivery, the current milestone and the directional target separate. Never invent implementation details to complete a diagram; label uncertain choices **Open**, **TBC** or **Unverified**, with the candidates the evidence supports.
- Tell deployed services apart from libraries, repositories, jobs, workflows, stores, external products and logical capabilities. Keep security, data-classification, identity, network and execution boundaries visible.
- Treat confusion as evidence of an unclear model. If an explanation needs repeated qualification, check whether a box holds several responsibilities, a capability is shown as a service, or one product name covers several things; fix the model rather than adding prose.
- Challenge generic nouns (platform, pipeline, registry, gateway, integration): what concrete thing is it, where does it run, who calls it and what does it call, what data and credentials does it use, who owns it, and what proves it exists? Keep responsibilities with different owners, maturity, deployment, data access or security boundaries distinct in the inventory.
- Trace the real call path: who initiates it, through which interface, with which inputs, which component does the work, what the success, blocked and error outcomes are, and where results and evidence are stored. A diagram shows communication, not association.
- Treat the first draft as a hypothesis to test, not the answer. Don't stop because the document looks polished: stop only when the [convergence criteria](#convergence-criteria) are met.

### The sources

**`documentation`: the vision.** Search for current architecture and design documents, proposals, decision records, meeting notes, security analyses, runbooks, and older designs that show how the proposal evolved. For each material document note whether it describes the current or target state, when it was last edited, whether it is a decision, proposal, recap or transcript, and whether newer evidence supersedes it. It establishes intent and context, never delivery or deployment.

**`workflow`: the delivery.** Search by the topic's terms and the identifiers documents name, then read the relevant epics, stories, tasks, bugs and spikes in full, with children and links: description, status, acceptance criteria, owners, dependencies, blockers, decision comments and links to documents, code or releases, and how the scope changed. Use them to tell what is committed, active, blocked, deferred or done. A ticket a document names that doesn't exist is a finding.

**`source_control`: the implementation.** First confirm the CLI is signed in (for `gh`, `gh auth status`), then search code, repositories and pull requests and read files and history (`gh search code`, `gh search prs`, `gh repo list <owner>`, `gh pr list --repo <owner>/<repo>`, `gh api`). Use the owner the documents and tickets point to; if unclear, ask the user.

- A repository a document names that doesn't resolve is a finding (stale document, wrong owner): state it, then search the owner's repositories for the equivalent code.
- If a search fails or comes back empty for access reasons, don't conclude the code doesn't exist; retry another way.
- Look at runtime and environment configuration, infrastructure, authentication and secret injection, integrations, tests, CI/CD, releases and deployment manifests, deprecated paths and code owners.
- Prefer the default branch and deployed configuration for the current state. Before concluding a repository is a placeholder or lacks a service, check active branches, open and recently merged pull requests (following stacked PR bases and the real merge destination), and the history for experiments that were merged and later removed: read them at the last commit that had them, pin it, and include them as experimental or historical context. Record release/default, development baseline and open candidates separately, each with a pinned revision. A merge into a development branch is not a release. Bound negative claims to the revisions and paths you searched.

**Triangulate** every important claim: what the documentation says should exist, what the tracker says is being delivered, what the code shows, whether it is merged, whether there is deployment evidence, and whether names and statuses agree. Watch for an old implementation mistaken for the current one, and a proposal presented as a running service. As a rule of thumb:

- Documentation without a ticket or code is vision or a proposal.
- A ticket without code is planned, in progress, blocked or unverified delivery.
- Code without documentation shows an implementation whose purpose or direction is unclear.
- A Done ticket with merged code is strong delivery evidence; merged code with deployment or configuration evidence is strong current-state evidence.
- Conflicting evidence is reported, investigated, and either resolved or kept explicitly in the ledger.

### The ledger

Keep `<investigation>/ledgers.md` while you research, not as something assembled after drafting. `init_investigation.py` writes its skeleton: the sections `check_report.py` expects, in order, with the queue's and source register's tables. It is the persistent research record behind the report, with much more detail than the report. Use stable IDs: `Q` actions, `S` sources, `F` findings, `C` components, `D` decisions, `G` gaps. Keep one current account; retain completed actions rather than appending copies of earlier ledgers.

Edit the ledger with `ledger.py`, not with patches. `next-id --kind S` prints the next free ID. `row --table sources --id S07`, with the row's other cells as a JSON list on standard input, adds the row or replaces the one with that ID and keeps the table sorted. `move --id Q05 --to completed --set "Status=Answered"` moves a queue row. `remove --table sources --id S07` deletes a row (`file-coverage` has no ID, so `--match` takes text its Source cell contains). `finding` takes a JSON object on standard input, with a `title` and each labelled field below, and adds the next finding, or with `--id F07` replaces that one; `remove --table findings --id F07` deletes it. `link --key some-doc --url <URL>` defines a link and `unlink --key some-doc` removes it. `text --section "Resume here"` replaces the body of that section, of Boundary, method and access or of Reflection. The tables are `queue-ready`, `queue-blocked`, `queue-completed`, `sources`, `file-coverage`, `decisions`, `gaps` and `components`. A source or a gap ends with an `Areas` cell naming the evidence areas it bears on (architecture, delivery, implementation, security and data, identity and credentials, runtime and operations), comma separated. Use a patch only for prose none of these covers.

Three commands only read, so you never open the whole ledger to find something: `status` prints the queue (ready and blocked actions), the counts, how many sources of each group and how many gaps each evidence area has, which sources have no area, and the sections not yet started; `find --text <text>` lists every row, finding and link that mentions the text, such as a document's name or a URL; `show --id F07` prints one finding or row, and `show --table findings` lists every finding's title.

Define every URL once, in `## Links`, and write `[text][key]` wherever it is used (`[text][]` when the key is the text). A revision change is then one edit, and `check_report.py` fails a key with no definition and warns about one never used.

- **Resume here:** a short block at the top: scope and phase, decisive findings, next ready actions, blockers and the evidence needed, review state. Refresh it after material discoveries and before handover; on resuming, read it first.
- **Research action queue:** `### Ready / in progress`, `### Blocked` and `### Completed`, each with the table (keep an empty one's "None"). Add an action whenever reading raises a material question, clue, contradiction or dependency; the starting question is provisional. Prioritise what could most change the architecture, milestone or a conclusion. Split work by entry path, component boundary or delivery question rather than umbrella actions like "read repositories". Every actionable follow-up has a queue entry: decisions and gaps supplement the queue, they don't replace it, so a gap whose next check can be done now is a ready action, not just a gap. A blocked action names its gap or decision, next check and owner, and is retried when new evidence or access makes it actionable. Resolved actions move to Completed without changing their IDs. Review improvements go in the same queue, with Critical for a wrong current-state claim or confused current/target, High for unsupported claims or wrong boundaries, Medium for incomplete validation, Low for presentation.
- **Findings:** one claim each, about 80 words (a topic with ten facts is ten findings, so each can be updated, superseded and cited on its own; the check warns over 150 words). One `### F01 — <short title>` heading each, then short labelled lines: **Claim**, **Kind** (observed implementation, configured/deployed state, delivery context, documented vision, inference, proposal), **Evidence** (the source IDs, and a precise place such as a file and lines only where the register's reference is not enough), **Validation and limits** (the deepest level reached and what stays uncertain), and, only when it applies, **Supersedes or contradicted by**. The queue already links actions to findings, so a finding does not list them. Store each evidence explanation once and reference its ID elsewhere. A document → ticket → code chain keeps the exact code that confirms or contradicts the claim. `sync-sources` writes each source row's `Findings:` from the findings whose Evidence names it; run it after adding findings, and `check_report.py --handover` fails a row that disagrees.
- **Source register:** an exact reference for every source that is a link: a ticket or document by its URL, code and configuration pinned to the commit (`.../blob/<sha>/<path>`, or `.../tree/<sha>` for a repository, branch or listing, with a pull request's URL beside it); only a search record, which has no URL, is exempt, and it is labelled `search record`. Also record the revision or date checked, what was read at what depth (full, sections, search-only, unread) and what it supports (for a repository, the depth is in `### File reading coverage`, so the row points there), and in `Areas` the evidence areas it bears on: `status` uses them to show which areas each group has covered, so there is no coverage table to keep. Use the gaps' `Areas` the same way. Record searches and fallbacks, including what a failed one covered. Every `### File reading coverage` row links the files it covers at the same pinned revision. The same goes for anything you put in backticks in the ledger or the report, such as a repository, branch, commit, file, directory, tool name or identifier: link it at its pinned revision (a line anchor for a symbol), or write it as plain words without backticks. Link everything that can be a link, so any claim can be followed to its original source: every ticket, pull request, decision record, document or page, repository, branch, commit, file and symbol you name, including a mention in plain words of a specific source such as "the SRE handover". `check_report.py --handover` fails a register or coverage row without a link, a backticked reference outside a link, and a ticket key or pull request number outside a link. A tree or entrypoint read doesn't establish that every module was read; if output was truncated, reread it or record the gap. Make the same distinction for document sections and ticket comments.
- **Component inventory and evolution:** one row for every material component: its name and type, responsibility, repository, paths and revision, implementation status (see [Component status](#component-status)), the separate deployment evidence and how much of it you read, callers and outgoing connections, and how it changes in the next steps (current → next). Unknowns generate queue actions.
- **Open decisions** (`D` IDs): each with its established position or unresolved choice, candidate options, constraints, tradeoffs, rationale, source authority, approval or proposal status and owner, which waits on a person.
- **Evidence gaps** (`G` IDs): each with what is established and what is missing, what would close it, its source authority and the owner and next check, which waits on evidence. A gap whose next check can be done now is a ready action in the queue.
- **Reflection:** written once before handover (step 5).

#### The working loop

Create the ledger, with the plan (boundary and queue), before substantive research. Then repeat these steps for each research step or small coherent batch. Do them in this order, with the command named, while the evidence is in front of you.

1. **Pick the next action.** Run `status`: it lists the ready and blocked actions and, per evidence area, how many sources each group has and how many gaps remain. Take the ready action whose answer could most affect the architecture, milestone or confidence in a conclusion, and favour an area a group hasn't covered. `move` it to in progress with what evidence would resolve it. Run `find --text <source or term>` first; if it is already there, use what the ledger holds instead of reading it again.
2. **Read, then record the source at once.** Add the source with `row --table sources`: its exact reference as a link, the revision or date, what you read and at what depth (failed checks and unread portions included), and **its areas**. Set the areas now, since you know what the source bears on. For code, add `file-coverage` rows. Do not postpone this to the end: coverage rebuilt from memory is a guess, and `status` only counts what was tagged.
3. **Write the findings.** One claim each, through `finding`, citing the source IDs. Keep a hypothesis distinct from a validated conclusion. Then run `sync-sources`. When a finding replaces an earlier one, replace that finding (`finding --id`) and note the supersession in its optional field. Add or update the component row (`row --table components`, with the node's ID) when you learn something about a component.
4. **Add the follow-ups before closing the action.** Every new question, clue, contradiction or dependency gets its own queue entry (`row --table queue-ready`). A gap whose next check can be done now is a ready action as well as a gap. Then `move` the answered action to completed, with its finding IDs. Close an action only when its answer is established; an unresolved choice stays open under a D ID and further research under Q IDs.
5. **Refresh the resume block** (`text --section "Resume here"`) after any material discovery, and before switching repository or source group.

Do not:

- leave the investigation under umbrella actions such as "read repositories" or "check tickets";
- assemble the ledger only before the report is written, or write several sources' rows from memory afterwards;
- edit the ledger with a patch where a command exists, or open the whole file to find something `find`, `show` or `status` would print;
- write `content.json` from memory or from command output instead of from a full read of the final ledger;
- claim a full read when coverage wasn't recorded: say so instead.

Before a handover or context reset, leave the next action and why explicit in the resume block. On resuming, run `status`, trust the saved state, and revalidate only where revisions changed, evidence is stale or a new question needs it. Record only what has happened: never write a review, correction or answer before it takes place. When a conclusion changes, refresh every affected part of the report and diagrams.

### Component status

Give every component one implementation status. Positive claims need code or configuration:

- 🟩 **Implemented**: merged code establishes it; this doesn't imply deployment.
- 🟨 **Implemented, needs significant work**: it exists but doesn't meet the proposed capability.
- 🟦 **In development**: unmerged or development-branch code, or an experiment branch with no pull request (say which).
- 🟥 **No implementation found**: a search outcome, not proof of absence; say why it was expected, where you searched and any access limits.
- ⬜ **Unverified**: access or evidence is insufficient. A ticket or document alone can't establish implementation.
- ⚫ **Legacy or superseded**: code establishes an older implementation; give the evidence for its replacement.

Record deployment separately: evidenced for a named environment and revision, explicitly not deployed, or unverified. Never give green because a document describes a component or a ticket is Done.

## Steps

### 1. Define the investigation

Identify the topic, starting questions, provisional boundaries and an initial plan, and a destination page if named. Infer them from the request; ask only when ambiguity materially changes the investigation. The plan is provisional and should grow with the evidence. Every report has both layers; only the research can show that some sections don't apply (see [Sections that don't apply](#sections-that-dont-apply)), so never narrow the research on that expectation.

**A request for a short output** (an exec summary, "100 words", a one-paragraph status) **is about the output's format, never the investigation's scope or rigor.** Do the full investigation and write the full report, then compress it as the last step. A later request for more detail is answered from the same investigation.

Then:

1. Choose a short, filename-safe `<Topic>`, capitalised words separated by hyphens, such as `Payments-Retry-Service`; honour a name the user gives.
2. Run `python3 <scripts>/init_investigation.py --topic <Topic> --format <format>`, where `<format>` is `long-analysis` or the short format asked for (such as `exec-summary`). If it fails, stop. It prints the `folder`, whether it is `temporary`, `<investigation>` (`<Topic>_<YY-MM-DD>`) and `investigation_dir`, and writes the ledger skeleton and the examples' index. Every run starts from scratch: a folder of the same topic and day is deleted first (`replaced` says so), so tell the user before you run it when one exists, and never build on what an earlier run left.
3. Never read or reuse what an earlier run left, on this or another day: its ledger and report included. Search and read every source again from the topic alone.
4. Skim an approved `examples` entry of that format for tone only. Never reuse a fact, status or claim from one.

The folder ends up like this:

```text
Payments-Retry-Service_26-10-05/
├── ledgers.md                         you write
├── content.json                       you write
└── Payments-Retry-Service_Report.md   make_report.py writes
```

The folder holds only these files, and `check_report.py --handover` fails on any other: keep working files in your own scratch folder. A short output adds its `<format>.json` (you write) and `<format>.md` (`make_summary.py` writes).

### 2. Research

Add each group's source families and questions to the queue. Discovery can start anywhere, but every implementation claim from workflow or documentation must be traced down to code. Follow identifiers (services, repositories, endpoints, CI jobs, tickets, pull requests, registries, datastores, security mechanisms, owners, superseding documents) when they could change the architecture, delivery status, a classification, a boundary, the milestone's scope or the target. Stop a branch when it is irrelevant, duplicated, inaccessible or too weak to change a conclusion, and record material inaccessible sources as gaps.

Build the **component inventory** and finish it before you write the report, keeping the ledger current as you read:

1. **Inventory the investigated system.** Use each relevant repository's file tree for discovery, then list every deployable or runnable unit material to the system (services, apps, CLIs, workers, jobs, functions) and every library that talks outside its own process, with their workloads and infrastructure. Add components that documentation or tickets name even if no code was found. A repository holding a general platform isn't the boundary: record unrelated units as excluded, with a reason.
2. **Trace material components and boundaries:** read each one's README and the code needed to establish its behavior, callers, outgoing calls (HTTP, gRPC, SDKs, queues, child processes, files), configuration, network policies and credentials. A search hit is a lead, not a reading. If you delegate, ask for exact revisions, coverage and connections, and check that the coverage supports the claims.
3. **Record it.** Each component gets an inventory row linked to findings for where it runs and each connection. Record partial reading; investigate it or keep the claim unverified if an unread part could change a material claim.

The inventory is done when every material component and connection is supported at the claimed level or has an explicit gap.

### 3. Draft and keep the report current

**First read the whole ledger, once, in full, with your file-reading tool.** The commands were for building it; the report must rest on the ledger as it now stands, not on what you remember writing or on `status` and `show` output. Read it again in full if you change findings, components, decisions or gaps afterwards, before you rewrite the text they feed. Then write `content.json` and run `make_report.py`, and fix whatever it lists. Update the same files as research continues; "draft" and "final" are review states, not separate files.

### 4. Review and iterate

Read the draft as its different readers would: an architect (are boundaries right?), an implementing engineer (can the code be found?), a delivery lead (does it match the tickets?), an SRE (are execution, identity and credentials concrete?), a security reviewer (are data classes and trust boundaries visible?), a product owner (is the milestone understandable and deliberately scoped?) and a new reader (can the flow be followed alone?). Ask, as a stakeholder would:

- What is this component in practice, and does it exist? Where is it implemented, in which repository, and which ticket delivers it?
- Is it a service, library, job, workflow, datastore or logical capability, and why is it a separate box?
- Who calls it, through which interface? Where are its configuration and credentials resolved?
- Does this happen in CI, the application or another runtime, and does the path use production or restricted data?
- Is it current, in delivery, in the current milestone or target, and what evidence supports its status?
- What is explicitly not being built, and could an engineer implement the work from this description?

Also ask of the generated report: does the architect layer repeat the executive layer? Move each fact to the layer it belongs to. Read the whole generated report once, start to end, against the ledger, and check that each sequence displays correctly in the viewer the user will read it in (or say in the ledger that this remains unverified).

When a question can't be answered clearly, investigate and revise rather than adding vague prose.

Record each improvement in the queue before applying it, and when a claim changes, update everything it touches: both layers, the sequences, statuses, decisions and references. Then review the whole document again: do the changes contradict each other, do revised boundaries reveal missing components, does a concrete name lead to another source, does newer evidence supersede an older source, do the sequences and the text still tell the same story? Go back to the sources for new questions and repeat until the [convergence criteria](#convergence-criteria) are met; there is no fixed number of rounds.

### 5. Reflect before handing over

Write the `## Reflection` section with `ledger.py text --section Reflection`: what changed between the first and final drafts, which assumptions were disproved, which components became more concrete, which conflicts were resolved, which conclusions depend on unavailable evidence, which decisions need a human owner, and why another round is unlikely to help. Then run `python3 <scripts>/check_report.py --report '<absolute report path>' --handover`, fix every error, review the warnings and rerun; a file that isn't one of the skill's is an error. Passing proves structure, not source fidelity or how the real viewer displays the diagrams.

### 6. Hand over

- Link both `ledgers.md` and the report as Markdown links to their full absolute paths, such as `[<Topic>_Report.md](<investigation_dir>/<Topic>_Report.md)`.
- If they asked for a short format, compress the finished report into it, adding nothing the report doesn't say. Choose a format name other than `content` or `ledgers`, write `<investigation>/<format>.json` (for example `exec-summary.json`) and run `python3 <scripts>/make_summary.py --investigation <investigation> --format <format>`, which writes `<format>.md` with the link to the full report at its end:

  ```json
  {
    "title": "Optional heading",
    "max_words": 100,
    "body": ["Markdown blocks in the shape the question needs."]
  }
  ```

  The body is free (paragraphs, bullets, `##` headings, a table); only the title's `#` is the script's. Set `max_words` to the limit the user gave, and leave it out when they gave none. Show the result in the chat and link the full document under it. Otherwise, say the report is ready, with the links, and don't recap it.

- Name every source that was unavailable and what it leaves unverified, and add any doubt about your own judgment that the report doesn't show.
- If they named a destination page in an enabled `documentation` source, show what you will write and publish it only after they approve.
- If `temporary` is `true`, say the folder is temporary: offer to copy the document somewhere they choose, and mention that setting `output.root` in the config keeps investigations and examples.

### 7. Keep approved outputs as examples

When the user says they are happy with a document or summary, keep it as an example: `python3 <scripts>/save_example.py --investigation <investigation> --file <document> --format <format> --note '<what makes it a good example>'`, where `<format>` is `long-analysis`, `exec-summary` or another short label for the shape they asked for, and the note is one line. It copies the document and the local files it links into a new `_examples` entry, never overwriting an earlier one, and adds it to the index. If `temporary` is `true`, say the example is lost when the temporary folder is cleared.

## The document

Every investigation writes `<Topic>_Report.md` with two layers, an executive/product summary and an architect summary. `make_report.py` owns its template: headings, table headers, fixed sentences, layout and links. You write `content.json`, which holds only the text that needs judgment, then run `python3 <scripts>/make_report.py --investigation <investigation>`. If `content.json` has problems it writes nothing and lists them all; otherwise it writes the report and prints the check's `errors` and `warnings` (including prose far from its target length).

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
      "evidence": "Ledger links"
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
      "decision": "A decision or an evidence gap",
      "why": "Why it matters",
      "position": "Established position",
      "evidence": "Ledger links"
    }
  ],
  "references": {
    "implementation": ["[README](https://...)"],
    "delivery": [{ "text": "[PROJ-123](https://...)", "historical": true }],
    "vision": []
  }
}
```

- `evidence_snapshot` is the date, `YYYY-MM-DD`, when you last checked the evidence; the report states it under the title.
- Text is Markdown: paragraphs are list items, table cells and references are one line each. No `#` to `###` headings (`####` is fine), code fences or HTML.
- Link the ledger as `[F03](ledger:F03)`: the script resolves the ID and fails on one the ledger doesn't have. `[ledger](ledger:)` links the ledger itself.
- Every claim traces to the ledger, which links the original sources: each paragraph, each `flow_gap`, each `why` and each decision's `evidence` carries a ledger link, and the script fails on one that doesn't. Every table row also needs a source link or a ledger link beside its claim; a row whose every cell is a gap ("Not established", "Unverified") needs no source link.
- Name roles, never people, in the report and the ledger.
- Lengths below are approximate targets: room to articulate, not quotas. Write fewer words when the evidence is thin or the point is simple; the script warns only above one and a half times the target, or under a third of it.

**The two layers do different jobs and must not repeat each other.** The executive layer says what the capability is for, where it stands, what is planned and what needs deciding: status, maturity, the milestone, delivery progress, dependencies, risks and the plan, with no configuration detail. The architect layer says how it works: the components and their responsibilities, how they interact, the boundaries of identity, data and trust, the technical constraints and the technical choices still open, with no tracker status, milestone or plan (those are the executive layer's). A fact belongs to one layer; the other may use it in a clause only where its argument needs it. The two Current status sections and the two Next steps and evolution sections each have the same name and a different content.

The executive layer must be independently readable, and written for a technical leader such as a director of engineering or CTO: capability, maturity, tradeoffs, delivery implications, dependencies and decisions, with precise technical terms where they help and enough context for unfamiliar project names. Include low-level detail only when it supports a leadership-level conclusion. Keep experiments, implemented capabilities and verified deployment distinct, with source links beside claims. Detailed evidence belongs in the ledger; don't add a third layer. When evidence is missing for a section, keep it and explain the gap.

- **`problem`** (about 150 words): the problem, who it affects, why it matters and the intended product outcome, in plain language.
- **`current_status`** (about 200 words; the executive view: no ports, credentials, limits or other configuration, which are the architect layer's): where things stand, what the current milestone should achieve, the gap between them, scope boundaries, success evidence and principal dependencies. Distinguish implemented progress, verified deployment and ticket-reported progress, and keep material evidence limits so the layer stands alone. If no milestone is defined, say it is not established; if `evolution` is skipped, say where things stand and that nothing is changing it.
- **`next_steps`** (about 200 words, in the same style as `current_status`, so the plan, the timing the sources state and what each depends on, not how the architecture changes; left out when `evolution` is skipped): the next milestones in their evidenced order and the broader product direction, together. Separate committed work from proposals and documented vision, say what each depends on, and say what is not established rather than filling it in. Add timing only where a source commits to it, and label proposals and optional directions as such.
- **`key_decisions`** (the Key decisions and risks table): only decisions, blockers, risks and uncertainties that warrant leadership attention (effects on scope, sequencing, investment, ownership, delivery confidence or exposure). Each row has the `decision` or risk, `why` it matters, the established `position` (where it stands, or the unresolved choice) and the `evidence`, which carries the ledger links the script requires. State what the evidence implies, not your assessment. An empty list is fine; the script says so.
- **`architecture`**: the Architect summary has two sections, `current` and `next` (left out when `evolution` is skipped), named like the executive layer's and laid out by the script as the text, then one titled sequence. Each has a `summary` (about 300 words) and a `sequence` (`title` and `lines`). Where evidence can't support a flow, give a `flow_gap` saying what is missing instead of a sequence.
  - `current`: how the system works today, for an engineer: the components and their responsibilities, how they interact, the boundaries of identity, data and trust, the entry paths, technical limits, deployment gaps in configuration terms, and what is only a candidate or unmerged. Leave out tracker status, the milestone and the plan. The sequence is the main flow, or the one that best shows how the parts interact.
  - `next`: how the architecture changes in the next steps, compared with Current: what is retained, added, changed or retired, why, and what it enables, plus the technical choices still open and the technical acceptance criteria. Leave out milestone dates, delivery status and the roadmap. Separate committed work from documented vision and source-backed inference, and don't present the target as the current milestone's scope. When the milestone is discovery (spikes, decision records, an evaluation), show what its tickets would build to qualify the capability as proposed components with hosting undecided, and make the sequence end in the human decision it informs. In-flight candidate work outside the milestone's epic stays labelled candidate context from Current.
- **`decisions_and_gaps`** (the Key decisions and gaps table, in the Architect summary): the unresolved technical choices and the evidence gaps that matter to the next steps. It has the same four fields as `key_decisions`: the `decision` or gap, `why` it matters, the established `position` (for a gap, what is established and what is missing) and the `evidence` with its ledger links. There is no status or owner column and no commentary under the table: the full gaps and how conflicts were resolved stay in the ledger. Don't invent alternatives. To find them, look for vision with no ticket, a ticket with no code, code absent from the design, statuses that disagree with the code, implementations that differ from the design, legacy components current documents still reference, open pull requests that materially change the picture, and missing deployment evidence.
- **`references`** (its own `## References` section, always present): every material code or configuration reference, ticket, document and pull request, under `implementation`, `delivery` and `vision`. Mark historical or superseded sources with `"historical": true`.

### Sections that don't apply

Some questions don't fit every section: "does the team have a documentation repository?" has no system to describe, and a system nothing is changing has no next steps. List the dimension in `skip`:

| `skip`         | When the research shows                                                        | Sections left out                         |
| -------------- | ------------------------------------------------------------------------------ | ----------------------------------------- |
| `architecture` | The subject isn't a system of components and flows: a practice, a team choice. | The whole Architect summary.              |
| `evolution`    | Nothing is changing it: no active epic or milestone, proposal or decision.     | Next steps and evolution, in both layers. |

- Skipping shapes the output, never the research: investigate all three groups in full.
- Not applicable is not unknown. Skip `evolution` only when the sources establish that nothing is changing it (not when they are silent or unavailable), and `architecture` only when there is no system to describe (not because evidence is thin).
- Record each skip with its reason and evidence in the ledger's `## Boundary, method and access`.
- The executive layer and the References always remain. With `evolution` skipped, `content.json` has no `next_steps` and only `architecture.current`. With `architecture` skipped, `content.json` has no `architecture` or `decisions_and_gaps`; every claim then keeps its source link beside it.

### The current milestone

The milestone the team is delivering now: at the start of a project its first iteration, later the next step from where delivery stands. Take it from the work tracker (the active epic, milestone or sprint goal) and say so; if none is defined, report it as not established rather than proposing one. With several tracks, the milestone is the active epic's; a track without an epic is candidate context. The tracker outranks documentation: if the active epic holds only discovery work, that discovery is the milestone, however large a goal a document states. A documented goal the tracker doesn't carry goes in Next steps and evolution, labelled as documentation.

Record its practical outcome, first use case, component changes, execution flow and identity, data and environment boundaries, acceptance evidence, human decisions and exclusions in the ledger. Watch for scope creeping in: more products, production data, release gates, rewrites, new gateways, target-state credential systems. A narrow milestone isn't incomplete when its exclusions are deliberate and visible.

## Diagrams

Each Architect summary section ends with one Mermaid sequence diagram, from `content.json`. It derives from ledger evidence and adds no new claims. Before drawing a flow, tie each material interaction to a finding that supports its responsibility and endpoints. Where the actor, runtime or call target is unspecified, mark the boundary unresolved or use a note rather than invent a call. Keep independent author/reviewer or requester/approver roles apart.

- **One flow per section, the one that explains most.** Don't combine independent entry paths into a fictional end-to-end operation, or use `par` unless they run concurrently in one operation; say in the text what the diagram leaves out. Without an evidenced caller, start from a generic `Client / operator` actor.
- **Names:** use the names the text and the ledger use, don't rename a concrete service to a generic responsibility, and show an internal module as an action of its parent service. Write a human role as a bracketed qualifier ("Client / operator (source owner)"), not a new actor.
- **Sequence lines:** the script adds `sequenceDiagram` and `autonumber`, which numbers every arrow, replies included, so don't number messages yourself. No raw semicolons in message or note text (Mermaid reads them as separators). Show only interactions needed to understand the approach, and keep material data and credential boundaries and failure or human-decision paths.
- **Rendering:** `make_report.py` renders the sequences to check their syntax, and fails on one that doesn't draw. To see one, try it with `output_diagram.py --png` and open the preview.
- **Candidate work:** label open pull requests and unmerged branches as candidate in the title or a note, and never draw a proposed interaction as if the code had it.

## Writing style

- Lead with plain English, then introduce the technical terms.
- Keep it high level but operationally concrete, with short, precise component names and concise diagram interactions.
- Explain why a component exists, not only what it is called.
- Make uncertainty explicit, link the sources of material claims, and never overstate completeness when a source was unavailable.

## Convergence criteria

The document is ready only when all of these hold.

**Evidence coverage**

- Every group has been investigated or explicitly marked unavailable.
- Every material linked source has been followed.
- Vision, delivery, implementation, security, identity and operations are covered.
- No known relevant document, ticket, repository or pull request is left unexamined.
- The topic-bounded inventory is complete: every material component and connection has been read to the depth needed for its claims, or its limits are recorded as a precise gap. Unrelated units discovered in repository trees are excluded with a reason; their unread code is not a gap in this investigation.
- The sequences represent the material approach faithfully at the chosen abstraction level. What they leave out is said in the text; no implemented interaction is drawn from a search alone.
- Refined searches no longer change the architecture materially.

**Claims**

- Every material claim says what kind of evidence backs it.
- Current implementation claims rest only on code/configuration; deployment is independently evidenced or unverified. Workflow explains delivery context and documentation establishes intended direction. Future-state inferences cite these sources; no investigator recommendations enter the report or diagrams. Every material lower-authority implementation claim has a completed validation chain to code/configuration or an explicit gap.
- Conflicts are resolved or explicitly documented.
- Historical sources aren't presented as current, and no assumption is written as a fact.

**Components**

- Every component has one clear responsibility and a type.
- Material responsibility, maturity and security distinctions remain visible even when low-level components are described together.
- Every status is backed by evidence.
- Current, in-delivery, current-milestone and target components aren't mixed.
- The sequences identify material placement as evidenced, unverified or proposed.

**Flows**

- Every interaction has a real initiator and recipient.
- Material inputs, outputs and failure outcomes are explained; low-level versions and mechanics remain traceable in the ledger.
- Credential and data boundaries are visible where material, and human decisions are explicit.
- The sequences and the text tell the same story, and the executive and architect layers don't repeat each other.

**Scope**

- The current milestone and its exclusions faithfully reflect the sources. Broad or undefined scope remains broad or explicitly undefined; do not redesign the milestone to pass this review.
- Reused, changed and new components can be told apart in Next steps and evolution.
- No target-state capability has leaked into the current milestone's commitments.
- Delivery status is kept apart from architectural ambition.

**Research queue and improvements**

- No actionable research question or validation task remains pending; the initial scope has expanded to cover every material discovery.
- Every finding is traceable to exact evidence and the deepest validation reached.
- Both fixed report layers are complete, apart from sections the research showed don't apply, and the executive/product layer stands alone. Each Architect summary section the report shows has its text and one sequence (or a stated flow gap), and Next steps and evolution compares against Current.
- No Critical, High or Medium improvement is still actionable.
- Every Low improvement is applied or consciously rejected.
- Every blocked improvement says what evidence or decision is missing.
- Every open decision lists its candidate options where known.
- The final review raises no new material issue.

"No open issues" never means inventing answers to questions that need an outside decision. It means every issue found has been resolved by evidence, corrected in the document, rejected with a documented reason, marked as an evidence gap, marked as a decision with an evidenced owner or explicitly unassigned ownership, or classified as out of scope: no silent ambiguity, no unexamined contradiction, no unsupported certainty, no known relevant evidence ignored, no actionable quality issue left unapplied.

Don't iterate until the document has no questions. Iterate until the relevant available evidence has been examined, every material question is investigated, every resolvable ambiguity is resolved, and every remaining uncertainty is visible and precise, with evidenced ownership or an explicit ownership gap.
