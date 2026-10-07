---
name: agentic-manager-tech-investigation
description: Investigates a technical system, proposal, capability or engineering problem by triangulating the team's documentation (the vision), work tracker (the delivery) and source control (the implementation), and iterates until it converges on an evidence-backed account of the current state, the current milestone and the directional target architecture, with a fixed executive/product layer and architect layer, as-is and to-be architecture maps, numbered Mermaid sequence diagrams, and a detailed research queue and evidence ledger. Also produces short outputs, such as an exec summary, from the same full investigation. Use when the user asks to investigate, map or explain a system or proposal, asks what exists today versus what is planned, or asks for its architecture, current milestone, first iteration or target state.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/output_diagram.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/check_report.py *)
---

# Tech Investigation

Investigates a technical system, proposal, capability or engineering problem, and produces the clearest evidence-backed account possible of:

1. What exists today, and how it works end to end.
2. What is being delivered.
3. What the sources establish the current milestone is intended to deliver: the milestone being delivered now, which is the first practical iteration when the work is just starting.
4. What the directional target architecture could become.
5. What the sources say will be kept, changed or built, and what remains undecided.
6. Which decisions and evidence gaps remain open.

The result must make sense to a new reader, be useful to the engineers who build it, and stand up against the evidence available.

The investigation's files are written to the `tech-investigations` folder of the output root the user set in the config (`output.root`), or to a temporary folder if none is set. Scripts give you that folder and write the files in it (see [Saving files](#saving-files)); never choose a folder yourself, and never read the config to find it.

## Prerequisite

Run `agentic-manager-utils-check-config`. If it fails, stop here.

This skill needs sources of three groups, each the evidence for one side of the picture:

| Group            | Evidence of        | What to look for                                                                  |
| ---------------- | ------------------ | --------------------------------------------------------------------------------- |
| `documentation`  | The vision         | Intent, architecture, decisions, proposals, constraints, meeting notes, outcomes. |
| `workflow`       | The delivery       | Scope, acceptance criteria, owners, progress, dependencies, blockers.             |
| `source_control` | The implementation | Code, configuration, infrastructure, tests, workflows, pull requests, releases.   |

Use every enabled source of each group whose channel is `mcp` (its MCP tools) or `cli` (its command-line program, through bash). Sources reached through `api` or `fs` need a script this skill doesn't have, so skip them; if one is enabled, tell the user it isn't used here.

- If none of the three groups has a usable source, stop and tell the user which `mcp` and `cli` sources each group has, showing their `setup` and the config `path`.
- If one or two groups have none, tell the user which, with those sources' `setup` and the config `path`, and ask whether to go on without them. If they agree, treat those groups as unavailable (see [When a source is unavailable](#when-a-source-is-unavailable)).

Other enabled groups, such as a local vault or messaging, aren't evidence for this skill; don't use them, including their results when they come mixed into a documentation source's search. A runbook or status note in a repository is reported operational state, not code or configuration: label it as reported and keep the claim unverified. Read code, configuration and structure, never data files holding customer or personal data; describe such a corpus by its schema and controls. Search each group for its role above, but classify each claim by its evidence: a ticket's status is delivery evidence, while a design note is vision evidence even when stored in a repository or work tracker. Neither proves implementation.

## Saving files

Three scripts handle the output folder: two of the shared library, in the `agentic-manager-utils-lib` skill installed next to this one, and one of this skill. `<lib>` below is the library's folder, `${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager`, and `<scripts>` this skill's `scripts` folder, `${CLAUDE_SKILL_DIR}/scripts`, where `${CLAUDE_SKILL_DIR}` is this skill's folder. Call them by exactly those paths: in Claude Code, the skill pre-approves them there, so they run without a permission prompt. Each prints what's wrong and exits non-zero on failure; handle the diagram exceptions below, and otherwise stop and report it.

- **The folder:** `python3 <lib>/output_folder.py --name tech-investigations` prints one line of JSON with the `folder`, created if missing, and whether it is `temporary`.
- **A file:** write every file of this skill, new or changed, with `output_file.py`, never with your own file tools. It takes the file's whole content on standard input, replaces the file if it exists, and creates missing folders on the way. `--path` is relative to `<folder>`:

  ```bash
  python3 <lib>/output_file.py --name tech-investigations --path '<path inside the folder>' <<'END_OF_FILE'
  <the file's whole content>
  END_OF_FILE
  ```

  For a small update, read the affected text and use the same command with `--patch`. Standard input is a JSON array of exact replacements:

  ```json
  [{"old": "Unique existing text", "new": "Updated text"}]
  ```

  Each nonempty `old` must match exactly once, in order; all edits are validated before writing. Missing or ambiguous matches leave the file unchanged: reread the affected section and retry with sufficient context. Patches cannot create files or write outside the same output folder. Use full writes for new files or substantial reorganisations. Neither mode replaces reading the current content; do not regenerate a long file for a small change.

- **Working files** (map sources being tried, sequence drafts, a working copy of a long report or ledger you keep in step) go in your own scratch or temp folder, not the investigation folder; only finished content goes through the writers. Try layouts with `output_diagram.py --check`, which writes nothing there.
- **A diagram image:** `python3 <scripts>/output_diagram.py` takes the same `--name` and `--path` (ending in `.svg`) and a Mermaid diagram on standard input, renders it with the Mermaid CLI through Node.js 22.13+, checks that every connection line keeps to the map's line rules (see [The architecture map](#the-architecture-map)), and writes the SVG. If the lines break the rules, it writes nothing and names each bad line: fix the diagram and run it again. If Node.js isn't available, it exits with code `3`. With `--check` (and optionally `--theme dark`), it renders a diagram from standard input, a map or a sequence, without writing anything to the folder: it applies the line rules to a map and prints the rendered `width` and `height`. Add `--png` to also get a PNG preview of the layout in the system temp folder (its `png` path), which you can open as an image to inspect it.

## Evidence authority

Every claim follows one chain of authority, from most to least authoritative: **source_control → workflow → documentation**. When two sources in the chain disagree, the earlier one wins, for every kind of claim: what exists, what is being delivered and what the current milestone is. Documentation is the least authoritative: use it mainly for vision and target direction, never to override what the work tracker or the code shows. Classify evidence by its content, not its storage location: a design note in a repository is documentation, not implementation evidence.

- **Code and configuration are the source of truth for current status.** Merged code establishes implementation. Deployment is a separate claim: require configuration or deployment evidence for the relevant environment and revision. An open pull request shows a candidate change, not the merged current state.
- **The work tracker explains delivery context:** why changes were made, their scope, dependencies, and the wider milestone. A Done ticket cannot override code or prove implementation.
- **Documentation supplies general vision and intended direction.** Even approved documents cannot override code/configuration or the delivery context established by the work tracker.
- Resolve conflicting accounts using the higher-authority evidence, retaining the discrepancy and its resolution in the ledger. Within code/configuration, identify the applicable revision and environment; do not silently combine different states.
- A clue found in documentation or workflow must generate validation actions down to source control before becoming a current-state fact. Record a proposal as a proposal while validation is pending. If validation is blocked, retain the original claim and mark implementation unverified.
- Starting from code/configuration, follow workflow and documentation when they help explain purpose, rationale and milestone context. Their absence does not invalidate an observed implementation fact.

### Reporting contract

The report describes evidence recorded in the ledger; it does not recommend a design or delivery plan. Future milestones and target architecture may be reconstructed from the team's work tracker and documentation without implementation evidence. Distinguish documented decisions, source-authored proposals and clearly labelled inferences that connect those sources. Cite the underlying sources, including for inferred future direction.

Do not introduce investigator recommendations, preferred backends, new milestones, implementation sequencing, retirement plans or suggested owners. Recording your own proposal in the ledger does not make it evidence. If the sources do not establish a choice, disposition or owner, report it as unresolved. In particular, do not invent decommissioning to make an evolution diagram appear complete. Withdraw unsupported earlier conclusions in the ledger before updating the report and diagrams.

Rendering uses the ledger's established findings only. If a missing fact requires research, return to the investigation and update the ledger first; do not fill the gap while writing the report.

### When a source is unavailable

A source is unavailable when its group has no usable source, a call to it errors, it comes back empty because of access (a permission denial, a single sign-on block, a 404 on a resource a document names), or you decided not to check it. Then:

1. Say so in the same response in which it happened, before any summary or conclusion: not later, and not only if asked.
2. Try at least one fallback first, such as another query, another enabled source of the same group, or another of the source's tools. Only mark the source unavailable once the fallback has also failed or none exists.
3. Go on with the available sources.
4. Mark the conclusions that depend on the missing source as **Unverified**.
5. Never replace missing evidence with assumptions.
6. When implementation couldn't be checked, never present documentation or delivery claims (a ticket's Done status, a document's description of existing code) as implementation fact. Label them as vision or delivery claims.
7. Record what must be checked once access is available.

Never let a failed call pass silently into an answer without caveats.

## Core principles

- Establish concrete implementation details in the research ledger. In report diagrams, use purposeful logical groups when they explain the architecture more clearly, with their contents and boundaries explained in text.
- Tell deployed services apart from libraries, repositories, jobs, workflows, stores, external products and logical capabilities.
- Never invent implementation details to make a diagram look complete.
- Label uncertain choices **Open**, **TBC** or **Unverified**, and list the candidates the evidence supports.
- Keep current implementation, current delivery, the current milestone and the directional target separate.
- Establish current implementation and behavior only from code/configuration. Use workflow to explain delivery and milestone context, and documentation for general vision; apply the evidence authority order when they conflict.
- Keep security, data-classification, identity, network and execution boundaries visible.
- Treat the first draft as a hypothesis to test, not as the answer. Don't stop because the document looks polished: stop only when the [convergence criteria](#convergence-criteria) are met.

## Interrogating the architecture

### Begin with the simplest truthful explanation

First explain what we are trying to achieve, why, what the current milestone is, and what happens from beginning to end. Don't introduce the full target architecture before the current milestone is understandable. Complexity must be earned by evidence and need.

### Treat confusion as evidence of an unclear model

If an explanation needs repeated qualification, check whether one box holds several responsibilities, a logical capability is shown as a service, one product name covers several capabilities, current and target states are mixed, or a familiar term hides an open implementation choice. Correct the model; don't add prose around an unclear diagram.

### Challenge every generic noun

Interrogate labels such as platform, pipeline, service, registry, store, gateway, runtime, credential store, integration and automation. For each, ask:

1. What type of thing is it, and what is its concrete name?
2. Where does it run or live?
3. Who invokes it, and what does it call?
4. What data does it read or write?
5. What identity and credentials does it use?
6. Who owns it?
7. Does it exist today, and what evidence proves that?

Resolve generic terms to concrete implementation in the ledger when evidence allows. Report diagrams may deliberately abstract these into named logical groups; explain the mapping in text. Distinguish this simplification from a capability whose implementation is still an open decision.

### Separate concepts with different responsibilities

Test distinctions such as: orchestrator versus execution library; CI job versus the framework it runs; source repository versus runtime registry; registry versus release automation; secret storage versus secret injection; encryption tooling versus runtime credential access; service identity versus the secret it authenticates with; a definition versus its execution; the production path versus a test path; a job runner versus the restricted-data environment its work needs; evidence storage versus gate evaluation; human approval versus automated promotion.

Keep responsibilities with different owners, maturity, deployment, data access or security boundaries distinct in the inventory. A report diagram may group them only when the abstraction does not conceal a distinction material to understanding the approach; explain meaningful differences in the summary or commentary.

### Trace the real call path

For each interaction, find who initiates it; the interface (HTTP, CLI, SDK, queue, file, database or in-process call); the inputs and version selectors; where configuration is resolved; which component does the work; the success, blocked, unavailable and error outcomes; where the result and evidence are stored; and which identities, versions and build revisions are recorded. A diagram shows communication, not conceptual association.

## Investigating the sources

### `documentation`: the vision

Search for current architecture and design documents, product and platform proposals, decision records, meeting notes and transcripts, security and privacy analyses, runbooks, older designs that explain how the proposal evolved, and named services, repositories, teams, tickets and owners.

For every material document, note whether it describes the current or target state, when it was created and last edited, whether it is verified or approved, whether it is a decision, proposal, recap, transcript or informal analysis, and whether newer evidence supersedes it.

Documentation establishes intent and context. On its own, it proves neither delivery nor deployment.

### `workflow`: the delivery

Find the relevant epics, stories, tasks, bugs and spikes: search by the topic's terms and by the identifiers the documentation names, then read the ones that matter in full, children and linked issues included. Read their summary and description, status and resolution, acceptance criteria, assignee and team, dependencies and links, blockers and risks, comments holding delivery decisions, links to documents, repositories, pull requests, builds or releases, and how the current scope differs from the original.

Use them to tell what is committed, active, blocked, deferred, complete or outside the current iteration. A ticket marked Done is delivery evidence, not proof that the implementation is deployed or works as described. A ticket a document names that doesn't exist is a finding.

### `source_control`: the implementation

First confirm the CLI is signed in (for `gh`, `gh auth status`). Then search code, repositories and pull requests, and read files and history (for `gh`: `gh search code`, `gh search prs`, `gh search repos`, `gh repo list <owner>`, `gh pr list --repo <owner>/<repo>` and `gh api`). Use the owner or organization the documents and tickets point to; if that isn't clear, ask the user.

- A repository a document names that doesn't resolve under that owner is a finding (a stale document, the wrong owner, a personal repository): state it, then search the owner's repositories for the equivalent code by package name, file name or a keyword from the document, rather than stopping.
- If a search fails or comes back empty for access reasons, don't conclude the code doesn't exist: retry another way first (see [When a source is unavailable](#when-a-source-is-unavailable)).

Find every relevant repository, and inspect where relevant: default-branch code; service and package boundaries; API routes and contracts; runtime and environment configuration; infrastructure definitions; authentication and secret injection; database, registry, storage, model and provider integrations; tests, fixtures and runnable examples; CI/CD workflows and job definitions; recent merged and open pull requests and branches; releases, tags, images and deployment manifests; deprecated or unused paths; code owners.

Prefer the default branch and deployed configuration for the current state. An open pull request proves work exists, not that it is live; code on the default branch doesn't prove deployment without release or environment evidence.

Before concluding that a repository is only a placeholder, lacks a service, or has no implementation, inspect relevant active branches and open/recently merged pull requests as well as the default branch. Also look in the history for experiments that were merged and later removed or moved (for example a demo or lab under `scripts/`, or code a document or evidence log describes but the default branch no longer has): read them at the last commit that had them, pin that commit, and include them as experimental or historical context with their maturity stated. Follow stacked PR base/head relationships and the actual merge destination. Record release/default, development baseline and open candidates separately, each with a pinned revision. A merge into a development branch is not a release; substantial development code must not disappear from the architecture just because the default branch is scaffolding. Bound negative claims to the revisions and paths actually searched.

### Triangulating

For every important component or claim, ask: what does the documentation say should exist; what does the work tracker say is being delivered; what does the code show exists; is it merged; is there evidence it is deployed or configured; does it match the design; is the ticket's status consistent with the code; are names and boundaries consistent across sources; is an old implementation being mistaken for the current one; is a proposal being presented as a running service?

## Ledgers

Keep `<investigation>/ledgers.md` throughout the investigation (see [Saving files](#saving-files)). It is the persistent research record behind the two report layers, with substantially more detail than the report. Use stable IDs to connect actions, sources, findings and components. Keep one current account, with completed actions and concise corrections retained for traceability; do not append copies of earlier ledgers or contradictory status snapshots.

### Use it as the live research plan

Create the ledger before substantive research, holding the plan (boundary and research queue), and add each finding, review and correction only when it happens; use it to guide the next check, not as a record assembled after drafting the report. Use `Q` for actions, `S` for sources, `F` for findings, `C` for components, `D` for decisions and `G` for evidence gaps; keep IDs stable when records move or conclusions change.

For each meaningful research step or small coherent batch:

1. Select a ready queue item whose answer could most affect the architecture, milestone or confidence in a conclusion. Mark it in progress and state what evidence would resolve it. Check existing findings and reading coverage before repeating a search or read.
2. Inspect that evidence and record the exact source, revision and reading depth while it is available. Record failed checks and unread portions too; do not reconstruct coverage from memory at the end.
3. Update the linked finding and component records: what the evidence establishes, what it contradicts and what remains uncertain. Distinguish a hypothesis from a validated conclusion.
4. Add newly exposed questions and dependencies to the queue before closing the current action. Complete an investigation question when its answer is established; an unresolved implementation decision can remain open under its own D ID, with any further research tracked by Q IDs.
5. Save the ledger through the output writer before moving to unrelated research: at least after discovery, after each source group, after the first draft and after each review round. When conclusions change, refresh the resume block and all affected parts of the evolving report and diagrams. Use bounded patches for small updates.

Do not leave the entire investigation under umbrella actions such as “read repositories” or “check tickets”. Split work by material entry path, component boundary or delivery question. Before switching repositories or source groups, persist the findings and coverage already established, resolve access attempts, and update the ready/blocked/completed queue. A ledger assembled only before report writing does not satisfy this live-plan requirement.

Keep entries concise and decision-relevant; the ledger is not a transcript of tool calls. Before a handoff or context reset, leave the next action, its reason and the evidence needed to resolve it explicit. On resuming, use the saved state and revalidate only where changed revisions, stale evidence or a new question require it. If earlier coverage was not recorded, label that uncertainty instead of claiming a full read.

### Resume here

Start the ledger with a short current-state block: investigation scope and phase, decisive finding IDs, next ready action IDs, blockers/decisions and the evidence needed to resolve them, plus the report's review state. Refresh it after material discoveries and before handover. On resuming, read this block and the referenced records first, then expand only as needed.

Keep sections in this order, with exactly these headings: `## Resume here`; `## Research action queue`; `## Boundary, method and access`; `## Revisions and source register` (with `### File reading coverage`); `## Findings and validation chains` (one `### F01 — <short title>` per finding); `## Component inventory and evolution` (which also maps each diagram name to its components); `## Decisions and precise evidence gaps`; `## Correction history`. Record only what has happened: never write a review, correction or answer before it takes place. Store each evidence explanation once in its finding and reference its ID from actions, components and reviews. Retain exact source links in findings or source records, rather than repeating long evidence narratives.

### Research action queue

Place `## Research action queue` immediately after `## Resume here`, with three subsections in order: `### Ready / in progress`, `### Blocked`, and `### Completed`. Keep empty subsections with an explicit “None” so the queue remains visible. Keep completed actions in this queue, not in a separate section farther down the ledger.

Start this before research, with the initial plan. Append an action whenever reading or review raises a material question, clue, contradiction, dependency or improvement. The starting question is provisional: expand the plan and boundaries as evidence requires. Do not discard a relevant question because it was absent from the initial request.

| ID | Trigger / linked finding | Question or check | Sources and validation required | Depends on | Priority / severity | Status | Outcome / finding IDs |
| -- | ------------------------ | ----------------- | ------------------------------- | ---------- | ------------------- | ------ | --------------------- |

Process ready actions, prioritizing those that could change the architecture, milestone or conclusions. Actions move from pending to in progress, then to answered/applied, blocked by a precise evidence gap, an open decision with an owner or an explicitly unassigned role, or rejected/out of scope with a reason. Add follow-up actions before closing a parent when its answer exposes new questions. Retry blocked work when new evidence or access makes it actionable. Move resolved actions to the queue’s Completed subsection without changing IDs. Every actionable follow-up has a queue entry; decisions and gaps supplement the queue rather than replacing it. Keep blocked actions visible through a gap or decision ID with its next check and owner; do not leave obsolete pending statuses beside their resolutions.

Review improvements belong in this same queue. Use Critical for a wrong current-state claim, major missing component or confused current/target state; High for unsupported claims, contradictions or wrong boundaries; Medium for incomplete validation, missing interactions or unclear scope; Low for presentation. Record the resolution before considering the review complete.

### Revisions and source register

| Source ID | Group / evidence kind | Exact reference | Revision / environment / date checked | Material read and findings | Access limits / superseded by |
| --------- | --------------------- | --------------- | ------------------------------------- | -------------------------- | ---------------------------- |

Use file paths, symbols and commit references for code, configuration paths and environments for deployment, ticket IDs and relevant comments for workflow, and document sections and dates for vision. Record searches and fallback attempts too, including their coverage when nothing was found. Track coverage across architecture, delivery, implementation, security/data, identity/credentials and runtime/operations for all three groups. Earlier investigations are leads to revalidate, not current evidence.

For each material code/configuration file, record its exact revision, reading depth (full, specific sections, search-only or unread), supported finding IDs and any outstanding check. A repository tree or entrypoint read does not establish that every module was read. If output was truncated, identify the unread portion and reread it before relying on it; otherwise record a precise gap. Use the same distinction for document sections and ticket comments.

### Findings and validation chains

Write each finding under its own `### F01 — <short title>` heading, then its fields as short labelled lines: **Claim**, **Kind**, **Evidence** (source IDs and precise links), **Validation chain** (and the deepest level checked), **Confidence and limitations**, **Related actions**, **Supersedes or contradicted by**.

Kinds include observed implementation, configured/deployed state, delivery context, documented vision, inference and proposal. Keep provisional claims distinguishable from validated facts. Record what each source actually establishes, not merely a list of links. A document → ticket → code chain must retain the exact code/configuration that validates or contradicts the original claim. Code findings may link upward to delivery and vision for explanation. Record remaining gaps and never promote an inaccessible claim into a fact.

### Component inventory and evolution

For each component, retain its ID, concrete name and type; responsibility; repository, paths and revision; implementation status and separate deployment evidence; runtime; callers and outgoing connections; interfaces and inputs/outputs; configuration resolution; identities and credential injection; data classes and trust boundaries; error/blocked paths; ownership where evidenced; tests and operational evidence; and whether it was read in full. Link every conclusion to finding IDs.

Record the as-is, proposed to-be and milestone change for each component, including reuse, modification, addition or retirement, delivery context, dependencies and exclusions. Keep decisions with their candidate options, constraints, tradeoffs, rationale, source authority, approval/proposal status and owner. Unknowns generate queue actions. Store these details as tables or per-component entries rather than forcing everything into one wide table.

Keep a concise correction history: the superseded claim, the finding that corrected it, and the report sections or diagrams updated. Preserve the reason a conclusion changed without copying an earlier document.

Maintain one evolving `<Topic>_Report.md` from the reconciled findings. Link its material claims to original evidence and its detailed support in this ledger. When a finding changes, update all affected report sections and diagrams. Handover requires no actionable research or review item left; blocked questions and decisions remain visible with their reason and next step.

## Component status

Give every component one implementation status. Positive implementation claims require code/configuration; search outcomes and insufficient evidence are labeled explicitly:

- 🟩 **Implemented**: merged code establishes the implementation; this does not imply deployment.
- 🟨 **Implemented, needs significant work**: an implementation exists but does not meet the proposed capability.
- 🟦 **In development**: code shows active changes, not yet merged into the default branch, including code merged only into a development branch and an experiment branch with no pull request (say which); link workflow for delivery context.
- 🟥 **No implementation found**: a search outcome, not proof of absence. State why implementation was expected, where you searched and any access limitations. If access prevented validation, implementation status remains unverified; record this search outcome alongside it.
- ⬜ **Unverified**: access or evidence is insufficient. A ticket or document alone cannot establish implementation.
- ⚫ **Legacy or superseded**: code/configuration establishes an older implementation; explain evidence for its replacement or retirement.

Record deployment separately as evidenced for a named environment/revision, explicitly not deployed where configuration establishes that, or unverified. Record milestone inclusion and proposed target additions separately too. Never give green because a document describes a component or a ticket is Done, and never treat an intended target status as current implementation.

## Steps

### 1. Define the investigation

Identify the topic, starting questions, provisional system boundaries and initial research plan, plus a destination page if named. Infer these from the request and context; ask only when ambiguity materially changes the investigation. Open the research action queue and expand it throughout discovery. The initial plan must never prevent following material questions that emerge later. Every report serves both executive/product and architect readers using the fixed structure below; do not select one audience or omit a layer.

**A request for a short output** (an exec summary, "100 words", "keep it simple", a one-paragraph status, a chat-sized update) **is about the output's format, never the investigation's scope or rigor.** Run every step below in full, exactly as for the long document, and write that document; then compress it into the short format as a last step. A later request for more detail, another angle or the full document is then answered from the same investigation, not researched again, unless it asks something the investigation didn't cover.

Then prepare the investigation's folders:

1. Get the `folder` and whether it is `temporary` from `output_folder.py` (see [Saving files](#saving-files)). If it fails, stop here.
2. Choose a short, filename-safe topic name, `<Topic>`, with capitalised words separated by hyphens, preserving meaningful acronyms: for example `Payments-Retry-Service`. Honour an exact name supplied by the user. Use the same topic name for the folder and full report.
3. The investigation's own folder is `<Topic>_<YY-MM-DD>` in `<folder>`, with today's date at the end: `<investigation>` below is that relative path, and `<investigation_dir>` its full path. Its files are written there with `--path '<investigation>/<file>'`, which creates it. If it already exists, this is a follow-up: continue the investigation in it.
4. If `<folder>` holds folders of the same topic on other days (including older date-first names), or `<investigation_dir>` already has files, read them first. An earlier investigation of the topic is a lead to verify, not evidence to copy, since its sources may have changed.

   The full report is `<Topic>_Report.md`; the research ledger is `ledgers.md`, diagram preparation is kept in `mermaids.md`, and map filenames are `architecture-as-is.svg`, `architecture-next.svg` and `architecture-to-be.svg`. For example:

   ```text
   Payments-Retry-Service_26-10-05/
   ├── ledgers.md
   ├── mermaids.md
   ├── Payments-Retry-Service_Report.md
   ├── architecture-as-is.svg
   ├── architecture-next.svg
   └── architecture-to-be.svg
   ```

5. The approved examples are in `<folder>/_examples`, `<examples_dir>` below, next to the investigations' folders (the underscore lists it first). If it has no `README.md`, write it (`--path '_examples/README.md'`) with this index:

   ```markdown
   # Examples

   Tech investigations the user approved, kept for their tone, structure and style only. They are never evidence: the topics they describe may have changed since.

   Each example has its own `<Topic>_<YY-MM-DD>--<format>` folder, with a numeric suffix when needed. One line per example, newest first: a link to its document and what makes it a good example.

   ## Index
   ```

Look in `<examples_dir>` for one or two approved outputs of the format asked for (its `README.md` indexes them), and skim them for tone and voice only; the fixed report structure below takes precedence over examples. Never reuse a fact, status or claim from an example: its topic may be stale.

### 2. Map the investigation

Add the source families and independent questions for each group to the action queue. Begin with source control where identifiable, then workflow and documentation for context. Discovery may start anywhere, but every workflow/documentation implementation claim must be traced down to code/configuration. Append validation actions as you find clues. Follow every material identifier you find: a service or component, repository or package, endpoint, configuration repository, CI job or workflow, ticket, pull request or commit, registry, datastore, infrastructure component, security mechanism, team or code owner, or superseding document.

Follow an identifier when it could change the current architecture, the delivery status, a component's classification, a security boundary, the current milestone's scope, the target architecture or the work required. Stop a branch only when it is irrelevant, duplicated, inaccessible or too weak to change a conclusion, and record material inaccessible sources as gaps.

Then build the **component inventory**, and finish it before drafting the document or diagrams. Keep updating the ledgers while you read. A conclusion or diagram drawn from a partial reading misleads more than a gap that is stated.

1. **Inventory the investigated system across every source.** Use each relevant repository's full file tree for discovery, then inventory every deployable or runnable unit material to the investigated system: services, web and desktop apps, CLIs, workers, jobs, servers and functions (for example everything under `services/`, `apps/` or `cmd/`), and every library that talks to something outside its own process. Include their deployment workloads and infrastructure dependencies. Add relevant components named by documentation and tickets even if no code was found. A repository containing a general platform is not itself the investigation boundary: record unrelated units as excluded, with a reason, rather than auditing the whole platform.
2. **Trace every material component and boundary.** For each inventoried component, read its README and the code/configuration needed to establish the claimed behavior, callers, outgoing calls and trust boundaries: HTTP, gRPC and SDK clients, queues, the child processes it starts, the files and folders it reads or writes, its environment variables and configuration, its network policies, and the identity and credentials it uses. A search hit is a lead, not a reading. Read complete relevant modules rather than relying on search snippets. Follow callers and dependencies until material behavior and boundaries are established; expand scope when they reveal a relevant issue. If you delegate, require exact revisions, file/section coverage and the connections found; check that the returned coverage supports the claims.
3. **Record it in the ledgers.** Each component gets an entry in the ledger inventory, linked to findings for where it runs and each of its connections. Record partial reading explicitly. If an unread part could change a material claim, investigate it or keep that claim unverified with a precise gap. Unrelated internals may be excluded with a reason; do not describe selective reading as a full audit.

The inventory is complete when every material component and connection is supported at the claimed level, or has an explicit evidence gap. Unread, available evidence that could change a material conclusion remains actionable; unrelated platform code does not. Then establish the report baseline and keep updating it as evidence changes.

### 3. Maintain the evolving report

Once the component inventory is complete, write `<investigation>/<Topic>_Report.md` in the [document's structure](#the-document), from the evidence so far. Treat its conclusions as hypotheses to test. Update this same file during subsequent research and review; “draft” and “final” describe review states, not separate files or a reason to defer corrections. Keep approved example snapshots separate as described below.

### 4. Review the draft critically

Review it as each of these readers:

- **Software architect:** are responsibilities and boundaries right?
- **Implementing engineer:** can the code be found and the changes understood?
- **Delivery lead:** does it match the tickets' scope, status, dependencies and blockers?
- **SRE or platform engineer:** are execution, deployment, identity, credentials and operations concrete? Do logical groups and omitted details preserve the material execution, deployment and trust boundaries established by the inventory?
- **Security and privacy reviewer:** are data classes, trust boundaries and restricted paths visible?
- **Product owner:** is the current milestone understandable and deliberately scoped?
- **New reader:** can the flow be followed without the conversation that produced it?

Also ask, as a stakeholder would: what is this component in practice; does it exist; where is it implemented, and in which repository; which ticket delivers it; is it a service, library, job, workflow, datastore or logical capability; who calls it, through which interface; why is it a separate box; where are its configuration and credentials resolved; does this happen in CI, the application or another runtime; does this path use production or restricted data; is it current, in delivery, in the current milestone or target; where does it run; what is explicitly not being built; could an engineer implement the work from this description? When one can't be answered clearly, investigate and revise rather than adding vague prose.

Challenge every component, interaction, status and conclusion, and append every research or improvement action to the queue before editing.

### 5. Apply every improvement

Apply every improvement the evidence supports. When a claim or component changes, check everything it affects: both report layers, the current state, the delivery context, all selected diagrams and their commentary, the current milestone's boundaries, component statuses and work required, open decisions and references. Never fix one paragraph and leave a contradicting diagram or conclusion.

### 6. Review again, and research again

Review the whole document again, not only what changed. Ask whether the improvements introduced contradictions; whether revised boundaries reveal missing components; whether a concrete name points to another repository, ticket or document; whether the code changes how a ticket reads, or a ticket changes how a document should be labeled; whether recent evidence supersedes an older source; whether diagram numbers and commentary still match; whether every status is still justified; and whether the remaining unknowns are really unresolved.

When new questions arise, append them to the queue, go back to the sources, update the findings and the document, and review again. Repeat steps 4 to 6 until the [convergence criteria](#convergence-criteria) are met; there is no fixed number of rounds.

### 7. Reflect before handing over

Run `python3 <scripts>/check_report.py --report '<absolute report path>'`. Fix every reported error, review warnings, and rerun after corrections. This read-only check covers structure, table citations, local artifacts and diagram order; it does not prove source fidelity, Mermaid syntax, fixed map geometry or actual viewer sizing. Complete those reviews separately. A reference-list entry does not replace a source link beside a material table claim. What it enforces, so you can write for it from the start: every data row of every table, the roadmap and decision tables included, has a source link or a link to a ledger gap, written `ledgers.md#<anchor>` with the heading's GitHub-style anchor (lower case, punctuation dropped, each space a hyphen: `### F03 — Delivery is exploration` is `#f03--delivery-is-exploration`), which the check validates; reference and shortcut links count when a definition names them; the roadmap rows read exactly "Current milestone", "Next milestones" and "Broader product direction"; each map's source sits in `mermaids.md` under its stage heading, which names its SVG file; and a map shown as raw Mermaid because Node.js is missing says its layout is unchecked.

Answer, and record the answers in the ledger as a `### Reflection` subsection of `## Correction history`: what changed between the first and final drafts; which first assumptions were disproved; which components became more concrete; which conflicts were resolved; which conclusions depend on unavailable evidence; which decisions still need a human owner; and why another round is unlikely to improve the document with what is known now. Hand over only when the last answer is clear and defensible.

### 8. Hand over

- Link both `ledgers.md` and the report. Always give the user a link they can click to open the document: a Markdown link to its full absolute path, such as `[<Topic>_Report.md](<investigation_dir>/<Topic>_Report.md)`.
- If they asked for a short format, write it to `<investigation>/<format>.md` (for example `exec-summary.md`), show it in the chat and link the full document under it. Otherwise, give a few lines on the headline: the current reality, the current milestone and the main open decision.
- Name every source that was unavailable, and what it leaves unverified.
- If they named a destination page in an enabled `documentation` source, show what you will write there and publish it only after they approve.
- If `temporary` is `true`, say the folder is temporary: offer to copy the document somewhere they choose, and mention that setting `output.root` in the config keeps investigations and examples.

### 9. Keep approved outputs as examples

When the user says they are happy with a document or summary this skill produced, copy it, exactly as approved and with its original filename, into `_examples/<Topic>_<YY-MM-DD>--<format>/` in `<folder>`, where `format` is `long-analysis`, `exec-summary` or another short label for the shape they asked for (such as `slack-update`). Never overwrite an earlier example: if that folder exists, append `--2`, `--3`, and so on, choosing the first unused name. Copy its locally linked documents and images into that example folder too, preserving relative paths, so the approved version remains self-contained after the investigation changes. Use the shared writer for every copied file. Each approved version is kept separately, so the collection shows how the user's style has evolved. Then add one line for it at the top of the `## Index` list in `_examples/README.md`, writing the whole index again: its link and what makes it a good example. If `temporary` is `true`, say the example will be lost when the temporary folder is cleared.

## The document

Every investigation writes `<Topic>_Report.md` with exactly these two layers and the headings below, in this order, and no other `##` or `###` heading anywhere (use `####` for flow titles and further structure). Keep headings when evidence is missing and explain the gap. The executive/product layer must be independently readable: include essential conclusions, caveats and decisions there even when developed again in the architect layer. Do not add a third engineering layer; detailed implementation evidence belongs in `ledgers.md`. Requested short extracts are additional artifacts, never replacements for this report.

Write the entire Executive / product summary, including its tables, for a technical leader such as a director of engineering or CTO. Assume familiarity with technical language; focus on capability, maturity, strategic tradeoffs, delivery implications, dependencies and decisions. Use precise technical terms when they clarify the point rather than replacing them with vague descriptions or explaining familiar concepts. Give enough context for unfamiliar project names and organisation-specific terminology. Include low-level implementation detail only when it materially supports a leadership-level conclusion or decision, and explain that implication; keep the full mechanics in Architect. Preserve the distinctions between experiments, implemented capabilities and verified deployment, with source links beside claims. Review this layer independently for clarity, relevance and concision, not for the absence of technical vocabulary. The Architect layer provides the detailed technical account.

```markdown
# <Technical topic>

Evidence snapshot: <date, as "5 October 2026">. Code links pin inspected commits; ticket, PR and document links may display later changes. Evidence revisions and access limits are recorded in the [Research ledger](ledgers.md).

## Executive / product summary

### Problem and intended outcome

In approximately 100 words, explain the problem, who it affects, why it matters and the intended product outcome in plain language. This is a prose-length target, excluding source links, not an exact word-count requirement.

### Roadmap

A table with fixed columns: stage / intended outcome / commitment and evidence / dependencies. Use exactly these three rows, in order:

- **Current milestone:** the outcome being pursued now and its evidenced delivery context.
- **Next milestones:** subsequent outcomes in their evidenced order; distinguish committed work from proposals.
- **Broader product direction:** the longer-term ambition, including relevant options that are not yet delivery commitments.

Keep this table a high-level overview; expand the current row in the next section rather than packing its delivery detail into the table. Organise the rows around evidenced outcomes and their sequence. Include timing only when sources establish a relevant commitment; do not impose a calendar-based structure. Keep all three rows when evidence is missing and state what is not established. Link claims to their sources. Label proposals and optional directions; do not invent dates, commitments or delivery progress from vision documents.

### Current milestone - deep dive

In approximately 200 words of prose, excluding source links, combine current status and the current milestone in one executive deep-dive immediately after the roadmap. Treat this as a length target, not an exact word-count requirement. Explain where things stand today, what this milestone should achieve, the gap between them, essential scope boundaries, success evidence and principal dependencies. Distinguish implemented progress, verified deployment and ticket-reported progress; retain material evidence limits so this layer stands alone. If no milestone is defined in the sources, say that it is not established. Do not add a separate Current status section or another executive milestone section or repeat the roadmap row verbatim. Keep this explanation at technical-leadership level. Put branch/file inventories, execution steps and detailed validation procedures in Architect; include a specific implementation fact here only when it explains a material delivery risk, tradeoff or decision.

### Key decisions and risks

Open with one sentence saying these items describe implications of the linked evidence, and whether decision ownership is established in the inspected sources. Then a table with fixed columns: decision or risk / why it matters / deciding role. "Why it matters" states the evidenced consequence with its source links; "deciding role" names the role a source establishes, or "Not established". Name roles, not people, anywhere in the report or the ledger. Don't add investigator assessments here: state only what the evidence implies.

Surface only decisions, blockers, risks and uncertainties that warrant technical-leadership attention: material effects on scope, sequencing, investment, ownership, delivery confidence, or operational/security exposure. Use the same director-of-engineering/CTO language as the rest of the executive layer. Explain the evidenced consequence or tradeoff and why it matters now. Name an owner only when established by a source; otherwise write "Not established". Keep implementation-level issues in Architect unless their implications meet this threshold. Do not populate this section merely to repeat every technical gap; if no leadership-level item is evidenced, say so. Link the supporting evidence.

## Architect summary

### Current architecture

Start with approximately 300 words explaining the current approach, principal responsibilities and interactions, implementation maturity and material deployment limits. Then show a system design map followed by focused sequence diagrams for materially distinct flows, followed by one shared commentary explaining the map and sequences together. The map establishes the baseline structure and boundaries; the sequences establish the separate entry paths and their meaningful boundaries. Explain logical grouping and material omissions. Keep the detailed inventory, revisions and reading coverage in the ledger. Preserve source links near claims.

### Next evolution

Start with approximately 300 words explicitly comparing the next evolution with Current architecture: what is retained, added, changed or retired; why; and what that enables. Cover the current milestone's technical scope, dependencies, acceptance evidence and material exclusions. When the milestone is discovery (spikes, ADRs, an evaluation), show what its tickets would build to qualify the capability, such as an export or publication job and an evaluation runner, as proposed components with hosting undecided, and a sequence for that qualification flow ending in the human decision it informs. In-flight candidate work outside the milestone's epic stays as labelled candidate context from Current architecture, not part of the next evolution; include subsequent steps only where evidenced, distinguishing commitments from proposals. Then show a system design map followed by focused sequence diagrams for materially distinct flows, followed by one shared commentary explaining the map and sequences together. The diagrams highlight what changed versus Current architecture using explicit labels and consistent names. Keep detailed change tables and execution/validation procedures in the ledger unless a compact detail is necessary to explain the approach; do not append an exhaustive implementation plan to this section.

### Target architecture

Start with approximately 300 words explaining the longer-term approach and how it evolves beyond Next evolution towards the roadmap's broader product direction. Identify retained foundations, further changes, their rationale and resulting capabilities. Separate agreed direction, documented vision and source-backed inference; do not imply that the target is the current milestone's scope. Then show a system design map followed by focused sequence diagrams for materially distinct flows, followed by one shared commentary explaining the map and sequences together. The diagrams highlight the further changes versus Next evolution, not only versus the current baseline. Keep names consistent across stages so the direction is easy to follow.

The opening-summary and commentary lengths are approximate prose targets, excluding headings, diagram source and citations. Each of these three sections follows summary → system design map → one or more focused sequence diagrams → one shared commentary. Do not interleave explanatory paragraphs between the diagrams. Title each sequence with a `#### <Component> — <flow>` heading (such as `#### Helpdesk API — ticket search`), and put the shared commentary under `#### Reading the design and flows together`. Each sequence numbers its own steps from 1; the commentary names the flow, then its steps ("**Helpdesk API:** steps 1–3 …"). Aim for approximately 100 words of shared commentary for a single flow, allowing more where multiple flows or material boundaries need explanation. Connect the map’s services, stores and boundaries to the numbered interactions and explain the architectural point once, rather than concatenate separate diagram descriptions. Keep preparatory system-map source in `mermaids.md`, not in expandable source blocks in the report.

### Technical decisions and gaps

Focus on unresolved technical choices, evidence gaps and missing validation, explaining their impact on the next evolution or target. Open with one sentence saying the table records source-backed differences and unresolved decisions, and does not select an option or assign an owner. The decision table has fixed columns: decision / established position or unresolved choice / evidence / status / owner (an evidenced role, or "Not established"). After it, one paragraph on how material discrepancies were resolved by evidence level (for example a proposed ADR isn't accepted architecture, a feature-branch merge isn't a default-branch release, a ticket status can't override code), and one on the precise remaining gaps, linking the ledger's findings and gaps by ID. Do not fill a column by inventing alternatives or assigning a deciding role. Include unresolved discrepancies between code, tickets and vision; keep resolved rationale alongside the relevant architecture. Link detailed component findings and queue actions in the ledger rather than reproducing research bookkeeping.

### References

Link every material code/configuration reference, ticket, document and pull request, grouped under bold labels by evidence kind: **Implementation and configuration**, **Delivery**, and **Vision, rationale and reported operational gaps**. Mark historical or superseded sources. Link the research ledger for the full validation trail.
```

### Diagrams

Maintain `<investigation>/mermaids.md` as the editable system-map preparation file alongside `ledgers.md`. Give each map a stable heading identifying its stage; record its SVG filename and retain its exact Mermaid block. Update this file first when changing a map, then regenerate its SVG. Maintain sequence diagrams directly in the report; do not duplicate them in `mermaids.md`. This file derives from ledger evidence and introduces no new research claims. Before drawing a proposed flow, map each material interaction to a finding and source section that supports its responsibility and endpoints, not just the desired outcome. A list of lifecycle steps does not establish that one service executes them all. Where the actor, runtime or call target is unspecified (such as a call to a resource no configuration sets), label the boundary unresolved or use an explanatory note; do not invent a call or self-action to complete the sequence. Preserve independent author/reviewer or requester/approver roles when sources require separation. The report contains rendered maps and directly rendered sequence blocks, without duplicate map-source details.

In each of Current architecture, Next evolution and Target architecture, use one system design map and as many focused numbered sequences as there are materially distinct flows. Maps show how separate entry paths fit into the overall structure; each sequence explains one coherent flow. Do not combine independent entry paths into a fictional end-to-end operation or use `par` unless they actually execute concurrently within one operation. Preserve comparable flows across stages where they exist, and explain when a flow is introduced, changes or falls outside the milestone. Diagram counts may differ between stages. Keep names, grouping, orientation and participant order consistent where practical to enable comparison. Prefer clarity over implementation granularity: omit details that do not help explain the approach, and group complexity into clearly named logical components whose contents are explained in the summary, commentary or ledger. Simplification must not invent connections, imply deployment, combine incompatible states or hide a material trust boundary.

- Every existing entry path into the capability gets its own component and its own sequence in Current architecture (when no caller is evidenced, the sequence starts from a generic `Client / operator` actor), labelled with its maturity: implemented routes, diagnostic or test routes, development services and experiments or labs that exercise the capability end to end (including ones on branches or removed from the default branch). Simplify inside a path, never by omitting one. Open pull requests built on a development branch belong to that branch's component, labelled as candidate; give them their own sequence only for a materially distinct flow.
- Draw from the researched inventory, but do not reproduce every component or connection. Record what logical groups represent and any consequential omissions in the ledger. A logical group is not automatically a deployed service or a single runtime.
- Treat the system map and sequences as two views of the same architecture. Use the same canonical component IDs and displayed names for map nodes and sequence participants; keep status or role qualifiers separate from the name. Maintain the name-to-inventory mapping in the ledger. Do not rename a concrete service to a generic responsibility in a sequence. If a sequence expands an internal module, explicitly identify its parent service, or show it as an internal action of that service. Human-role qualifiers must map clearly to the map’s actors. Match call paths, stores and boundaries as well as wording, and check these correspondences before handover.
- Keep names and abstraction levels consistent across stages. In Next evolution and Target architecture, explicitly label retained, changed and new elements and distinguish proposals from implemented paths. Commentary explains the design delta, not merely the boxes.
- Show only interactions needed to understand the approach. Use purpose or interface labels as appropriate; exact protocols, identities and stores belong on the diagram only when they affect the explanation. Preserve material data/credential boundaries and failure or human-decision paths.
- Preserve native Mermaid sequence rendering by default. After rendering the exact sequence sources, compare their SVG viewBox widths and the intended Markdown viewer display width. If fitting each to the same page width makes text sizes materially different (more than about 15%), inspect the actual reader’s preview; shorten or split a too-wide flow without losing material steps, then adjust only narrower diagram containers by the measured width ratio where needed. Record the final visual check and preserve comparable readability, not merely successful Mermaid parsing. If the actual viewer is unavailable, say that display-scale verification remains unverified. If one diagram displays at a different scale, investigate that diagram in the actual reader’s viewer and keep working diagrams unchanged. Do not impose report-wide zoom, CSS, HTML wrappers or font/spacing overrides to fix a local discrepancy; the only wrapper allowed is the single container below. A standalone render or simulated preview does not establish that the real Markdown preview works; preserve a known-good baseline and revert changes that regress it. If the screenshot confirms one narrower diagram is enlarged by fitting the same page width, constrain only that diagram’s container width using a measured ratio to a correctly displayed peer: put `<div style="width:62.42%; margin:0 auto;">` (with the measured percentage) on its own line before the fence, a blank line on each side of the fence, and `</div>` after it. Preserve its Mermaid source and the other diagrams, and verify that the Markdown viewer renders the fence inside the container.
- When using a sequence, number the principal interactions with `autonumber`, which numbers every arrow, replies included; the commentary's step ranges follow those numbers. The shared commentary after all diagrams may explain related numbered steps together; avoid a long implementation-level step list. Use comparable use cases across stages where useful, without forcing every participant onto another map.
- Current architecture is the baseline. Next evolution compares with current; Target architecture compares with next. Label retained, added, changed and retired elements or interactions, and explain why changes matter. Identify retirement explicitly rather than silently dropping an element. Change labels are separate from implementation status: a proposed addition is still proposed. If evidence cannot support a required map or flow, retain its position with an explicit gap rather than inventing a flow.

### The architecture map

- Draw architecture, not only capabilities or workstreams: show the concrete services/processes, material stores, runtime or hosting boundaries and external providers needed to understand the system. Label arrows with meaningful interfaces or data operations. Keep publication writers separate from runtime readers where identities differ. Unknown hosting stays explicitly unknown; a proposed service must not look deployed.
- Abstract internal modules only when doing so preserves which process runs them, what it calls and where data lives. Do not replace independently deployed systems, POCs or stores with a generic foundation or responsibility box. Keep source-backed current wiring separate from optional candidate behavior and source-authored proposals.
- Inspect the actual maps visually, including scope outlines, text, edge labels, crossings and styling: render each with `output_diagram.py --check --png` and open the PNG preview as an image. The preview shows the layout in Mermaid's own colours; to see the dark styling and crosses, also look at the written SVG rasterised (on macOS, `qlmanage -t -s 2000 -o <scratch folder> <svg>`). Syntax and coordinate checks alone are insufficient. Hidden layout edges must hide their labels too; connections must not appear to terminate at unrelated nodes or imply junctions where they merely cross.
- Show distinct POCs and their eventual replacements separately when their lifecycle differs. Distinguish reusing code or patterns from retaining the experimental runtime. Record each source-backed disposition and retirement condition in the ledger. Where disposition is unknown, preserve the component as context and say its future is unresolved; do not recommend retirement or retention.
- Show all diagram components at the same positions across stages, including components later decommissioned. A red outline identifies the complete architecture carried at that stage, including unchanged components, not only the work introduced in that step. In Current architecture it includes the existing paths and labelled candidate context (development branches, open pull requests, experiments); future jobs stay outside. The outline covers the system's own components, including the stores and cloud resources its code provisions or calls (such as a knowledge base or a graph database), not human actors or third-party sources it reads from. It may be a polygon or several outlines. A component included in one stage stays visible in the next unless its transfer out of the investigated system is explained; decommissioned components remain visible in grey with a source-backed lifecycle label. Where future disposition is unresolved, keep its position and outline for comparison but label it “Future unresolved — current context” in the diagram. Explain in the legend that this context is not a commitment to include it in the future solution. Pending selection or absence of new work is not removal. Outside the outline means not yet included in that stage, with normal appearance. Do not imply that separate experiments inevitably survive as one integrated solution.
- Before handover, account for every previously included component in the next stage: retained, adapted, decommissioned, explicitly transferred, or unresolved and preserved as context. Record the disposition and any unresolved decision in the ledger. Do not let a component silently lose its outline, or infer retirement from an omitted connection.
- Connections may change between stages. Colour added or changed arrows red relative to the preceding stage, leaving unchanged arrows neutral. Keep proposed versus implemented connections distinct through line style and labels; red means change, not implementation status. Check that changing edges does not move the components.
- Reserve greyed-out components for decommissioning and overlay a prominent diagonal cross while keeping names readable. Add the Mermaid class `decommissioned` to rectangular retired nodes; the renderer draws the cross without changing layout. Label confirmed removal `Decommissioned`, and future removal `Planned decommissioning` or `Proposed decommissioning` according to the evidence. Never grey a component merely because it is outside scope, optional or not yet implemented. Do not invent retirement decisions to make the evolution look cleaner.
- Label shared target context and partial foundations explicitly. Scope highlighting does not prove deployment or integration. Current sequences explain actual entry paths; future maps distinguish agreed plans, proposals and unresolved alternatives. Verify fixed component positions across rendered maps, without requiring identical connections or scope outlines.
- Prefer Mermaid `flowchart LR` for landscape system maps, wider than tall and close to the proportions of the accompanying sequence diagram. Aim for roughly 1.5:1–2.5:1 width to height as a layout guide, not a hard limit; prioritise readable labels and comparable layouts over an exact ratio: widen labels rather than truncate them, even past the ratio. Inspect the rendered dimensions and regroup or shorten labels when the result is tall or excessively wide; do not stretch the SVG or add empty space to manufacture the ratio. Every connection line must run horizontally, vertically or at 45°, with rounded corners. Begin with `%%{init: {"flowchart": {"curve": "rounded"}, "elk": {"lineHops": "gap"}}}%%`; never select another curve or arc-shaped line hops. The renderer checks this layout constraint.
- Mermaid techniques for the maps, as the pinned renderer behaves:
  - It lays flowcharts out with ELK. `flowchart.rankSpacing` and `nodeSpacing` have no effect; to make a wide map more compact, add `"nodePlacementStrategy": "NETWORK_SIMPLEX"` to the `elk` settings and regroup nodes. Don't switch to another layout engine: its lines break the line rules.
  - Mermaid keywords such as `graph`, `end`, `subgraph`, `style` and `class` can't be node IDs, and a subgraph ID equal to a node ID silently swallows the node: prefix subgraph IDs (`grp_`).
  - Write a small generator in your scratch folder that emits all three stages' maps from one list of nodes and connections, so the order and the `linkStyle` indexes stay the same.
  - Give each node a 3-line label: name / status (its current implementation status, the same in every stage) / change label (what it means at that stage) (such as "Future unresolved — current context"), with `&nbsp;` for an empty line; a person's or external system's status line reads "Person" or "External".
  - Every call in a sequence has a matching connection on the same stage's map (its reply rides on that connection; self-actions and decision notes need none), and every human role in a sequence is one of the map's actors, with the role as a qualifier in brackets ("Client / operator (source owner)") rather than a new actor.
  - To keep components at the same positions across the three stages, give every stage's map the same nodes and the same connections, in the same order, and keep each label's number of lines the same: write an empty line as `&nbsp;`, since a trailing empty `<br/>` collapses, and fix the label width in `themeCSS` wide enough for the longest label, "Future unresolved — current context" needing about 260px (for example `.node .label div{width:260px !important;max-width:260px !important;white-space:nowrap !important}`), since a wider or wrapped label moves its neighbours; keep connection labels identical across stages too. Then compare the `nodes` positions that `output_diagram.py --check` prints for each stage's map: they must match. Hide a connection a stage doesn't have with `themeCSS` in the init block, `[data-id=L_<from>_<to>_0]{opacity:0}`, which hides its label too; add, remove or reorder nothing. A hidden connection still shapes the layout in every stage: if one stretches the maps, move or regroup its nodes rather than drop it. Drop a source-backed connection only as a last resort, and then explain it in the commentary and the ledger.
  - Draw proposed connections with `-.->`, and add `.edge-pattern-dotted{stroke-dasharray:6 4 !important}` to `themeCSS`: Mermaid's own inline style otherwise drops a `linkStyle` dash on some connections.
  - Draw the red outline with a `classDef` on the carried components (for example `classDef carried stroke:#e5484d,stroke-width:3px`) or a styled subgraph, and grey decommissioned components with a `classDef` of their own plus the `decommissioned` class, which only adds the cross.
  - Sequence participants can't break lines: use the map's name on one line.
  - Alternatives in one stage: put "Alternative — unresolved" on each alternative's change line rather than moving it into a new subgraph (which would move it), keep it inside the outline only if the sources carry it at that stage, and say in the commentary whether the alternatives exclude each other.
- Use subgraphs for material runtime or trust boundaries. Label logical groupings and proposed or unverified placement explicitly; a runtime grouping is not required for every deployment unit.
- Nodes may represent concrete components or logical groups. Show implementation status where it helps avoid confusing current and planned capabilities; split or annotate a group whose members have materially different maturity. Detailed per-component statuses remain in the ledger.
- In the shared target-context maps, use dashed arrows for proposed connections and open pull requests, and solid arrows for interactions the code has, on the default branch or a labelled development branch. Keep this meaning consistent across stages. Simplify low-level hops without claiming a direct protocol or trust relationship that does not exist.
- Render maps with `output_diagram.py --theme dark`, using `architecture-as-is.svg`, `architecture-next.svg` and `architecture-to-be.svg` for the current, next and target maps respectively. Embed the SVG before the sequence diagrams and keep its Mermaid source in `mermaids.md`. Re-render whenever its source changes. Sequences stay as Mermaid blocks; place the shared commentary after the last sequence in the section. If Node.js is unavailable (exit code `3`), show the map as Mermaid and disclose that its layout is unchecked.
- Validate every sequence by rendering its exact Mermaid source with the same pinned renderer before handover, and repeat after edits: `python3 <scripts>/output_diagram.py --check < sequence.mmd` checks it without saving an SVG in the report folder, and its `width` is the viewBox width to compare between sequences. Checking interaction numbering alone does not validate syntax. Avoid raw semicolons in message and note text: Mermaid treats them as statement separators. If rendering is unavailable, disclose that sequence syntax is unchecked.

### The current milestone

The milestone the team is delivering now: at the start of a project, its first iteration; later, the next step from where delivery stands. Take it from the work tracker (the active epic, milestone or sprint goal) and say so; if none is defined, report that the milestone is not established rather than proposing one. With several tracks, the milestone is the active epic's; a track with no epic is current or candidate context, and its in-flight work appears in the roadmap's next milestones labelled as candidate. The tracker outranks documentation (see [Evidence authority](#evidence-authority)): if the active epic holds only discovery work, such as spikes, ADRs and an evaluation, that discovery is the current milestone, however much bigger a goal documentation states. A documented goal or OKR the tracker doesn't carry yet goes in the roadmap's next milestones or broader direction, labelled as documentation, and the deep dive notes that the tracker doesn't track it.

Research and record its practical outcome, first use case, component changes, execution flow and identity, data/environment boundaries, acceptance evidence, human decisions and exclusions in the ledger. The report summarises the details needed to understand the approach within its agreed section lengths.

Check for scope creeping in: more products, production data, release gates, pull-request automation, rewrites, new gateways, long-term governance, target-state credential systems or production infrastructure. A narrow milestone isn't incomplete when its exclusions are deliberate and visible.

### Writing style

- Lead with plain English, then introduce the technical terms.
- Stay high level but operationally concrete, with short, precise component names and concise diagram interactions.
- Explain why a component exists, not only what it is called.
- Use purposeful names for logical groups, explaining what they contain; avoid vague boxes that conceal unresolved responsibilities.
- Make uncertainty explicit, link the sources of material claims, and never overstate completeness when a source was unavailable.

## Convergence criteria

The document is ready only when all of these hold.

**Evidence coverage**

- Every group has been investigated or explicitly marked unavailable.
- Every material linked source has been followed.
- Vision, delivery, implementation, security, identity and operations are covered.
- No known relevant document, ticket, repository or pull request is left unexamined.
- The topic-bounded inventory is complete: every material component and connection has been read to the depth needed for its claims, or its limits are recorded as a precise gap. Unrelated units discovered in repository trees are excluded with a reason; their unread code is not a gap in this investigation.
- Diagrams represent the material approach faithfully at the chosen abstraction level. Grouping and omission decisions are traceable to the inventory; consequential changes and boundaries remain explicit. No implemented connection is drawn from a search alone.
- Refined searches no longer change the architecture materially.

**Claims**

- Every material claim says what kind of evidence backs it.
- Current implementation claims rest only on code/configuration; deployment is independently evidenced or unverified. Workflow explains delivery context and documentation establishes intended direction. Future-state inferences cite these sources; no investigator recommendations enter the report or diagrams. Every material lower-authority implementation claim has a completed validation chain to code/configuration or an explicit gap.
- Conflicts are resolved or explicitly documented.
- Historical sources aren't presented as current, and no assumption is written as a fact.

**Components**

- Every component has one clear responsibility and a type.
- Logical diagram groups have clear meanings and map to concrete inventory entries or explicitly proposed capabilities.
- Material responsibility, maturity and security distinctions remain visible even when low-level components are grouped.
- Every status is backed by evidence.
- Current, in-delivery, current-milestone and target components aren't mixed.
- Selected diagrams identify material placement as evidenced, unverified or proposed and agree across the three architectural stages.

**Flows**

- Every interaction has a real initiator and recipient.
- Every numbered arrow has matching commentary, and every commentary step is in the diagram.
- Material inputs, outputs and failure outcomes are explained; low-level versions and mechanics remain traceable in the ledger.
- Credential and data boundaries are visible where material, and human decisions are explicit.
- Diagrams and prose tell the same story.

**Scope**

- The current milestone and its exclusions faithfully reflect the sources. Broad or undefined scope remains broad or explicitly undefined; do not redesign the milestone to pass this review.
- Reused, changed and new components can be told apart.
- No target-state capability has leaked into the current milestone's commitments.
- Delivery status is kept apart from architectural ambition.

**Research queue and improvements**

- No actionable research question or validation task remains pending; the initial scope has expanded to cover every material discovery.
- Every finding is traceable to exact evidence and the deepest validation reached.
- Both fixed report layers are complete, and the executive/product layer stands alone. Each of the first three architect sections has a roughly 300-word opening and a landscape system map and focused sequences for materially distinct flows, followed by one shared commentary connecting structure and flow (roughly 100 words for a single flow, longer where needed for multiple flows); next compares against current and target against next, with change labels distinct from implementation status.
- No Critical, High or Medium improvement is still actionable.
- Every Low improvement is applied or consciously rejected.
- Every blocked improvement says what evidence or decision is missing.
- Every open decision lists its candidate options where known.
- The final review raises no new material issue.

"No open issues" never means inventing answers to questions that need an outside decision. It means every issue found has been resolved by evidence, corrected in the document, rejected with a documented reason, marked as an evidence gap, marked as a decision with an evidenced owner or explicitly unassigned ownership, or classified as out of scope: no silent ambiguity, no unexamined contradiction, no unsupported certainty, no known relevant evidence ignored, no actionable quality issue left unapplied.

Don't iterate until the document has no questions. Iterate until the relevant available evidence has been examined, every material question is investigated, every resolvable ambiguity is resolved, and every remaining uncertainty is visible and precise, with evidenced ownership or an explicit ownership gap.
