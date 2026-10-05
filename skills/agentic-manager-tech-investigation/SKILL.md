---
name: agentic-manager-tech-investigation
description: Investigates a technical system, proposal, capability or engineering problem by triangulating the team's documentation (the vision), work tracker (the delivery) and source control (the implementation), and iterates until it converges on an evidence-backed account of the current state, the current milestone and the directional target architecture, with an architecture map of where each component runs, numbered Mermaid sequence diagrams, component statuses, work required, gaps and open decisions. Also produces short outputs, such as an exec summary, from the same full investigation. Use when the user asks to investigate, map or explain a system or proposal, asks what exists today versus what is planned, or asks for its architecture, current milestone, first iteration or target state.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/output_diagram.py *)
---

# Tech Investigation

Investigates a technical system, proposal, capability or engineering problem, and produces the clearest evidence-backed account possible of:

1. What exists today, and how it works end to end.
2. What is being delivered.
3. What the current milestone should deliver: the milestone being delivered now, which is the first practical iteration when the work is just starting.
4. What the directional target architecture could become.
5. What must be kept, changed or built.
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

Search each group for its role above, but classify each claim by its evidence: a ticket's status is delivery evidence, while a design note is vision evidence even when stored in a repository or work tracker. Neither proves implementation.

## Saving files

Three scripts handle the output folder: two of the shared library, in the `agentic-manager-utils-lib` skill installed next to this one, and one of this skill. `<lib>` below is the library's folder, `${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager`, and `<scripts>` this skill's `scripts` folder, `${CLAUDE_SKILL_DIR}/scripts`, where `${CLAUDE_SKILL_DIR}` is this skill's folder. Call them by exactly those paths: in Claude Code, the skill pre-approves them there, so they run without a permission prompt. Each prints what's wrong and exits non-zero on failure; handle the diagram exceptions below, and otherwise stop and report it.

- **The folder:** `python3 <lib>/output_folder.py --name tech-investigations` prints one line of JSON with the `folder`, created if missing, and whether it is `temporary`.
- **A file:** write every file of this skill, new or changed, with `output_file.py`, never with your own file tools. It takes the file's whole content on standard input, replaces the file if it exists, and creates missing folders on the way. `--path` is relative to `<folder>`:

  ```bash
  python3 <lib>/output_file.py --name tech-investigations --path '<path inside the folder>' <<'END_OF_FILE'
  <the file's whole content>
  END_OF_FILE
  ```

  To change a file, read it, then write its whole new content the same way.

- **A diagram image:** `python3 <scripts>/output_diagram.py` takes the same `--name` and `--path` (ending in `.svg`) and a Mermaid diagram on standard input, renders it with the Mermaid CLI through Node.js 22.13+, checks that every connection line keeps to the map's line rules (see [The architecture map](#the-architecture-map)), and writes the SVG. If the lines break the rules, it writes nothing and names each bad line: fix the diagram and run it again. If Node.js isn't available, it exits with code `3`.

## No single source is the truth

Each group shows one side of reality, and none is complete. The account must reconcile all three:

- Documentation without delivery or implementation evidence normally means vision or proposal.
- Delivery without implementation evidence normally means planned, in progress, blocked or unverified.
- Implementation without documentation may show work whose purpose or direction is unclear.
- A ticket marked Done plus merged code is strong delivery evidence.
- Merged code plus deployment or configuration evidence is strong current-state evidence.
- Conflicting evidence must be reported, investigated, and either resolved or explicitly kept.

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

- Prefer concrete services, repositories, packages, jobs, workflows, endpoints, databases and infrastructure over generic labels.
- Tell deployed services apart from libraries, repositories, jobs, workflows, stores, external products and logical capabilities.
- Never invent implementation details to make a diagram look complete.
- Label uncertain choices **Open**, **TBC** or **Unverified**, and list the candidates the evidence supports.
- Keep current implementation, current delivery, the current milestone and the directional target separate.
- For current behavior, prefer direct implementation and operational evidence. For intended direction, prefer approved decisions in the documentation. For scope, status, dependencies and blockers, prefer the work tracker.
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

Replace the generic term with the concrete implementation when the evidence allows. Otherwise keep the logical capability and mark its implementation as an open decision.

### Separate concepts with different responsibilities

Test distinctions such as: orchestrator versus execution library; CI job versus the framework it runs; source repository versus runtime registry; registry versus release automation; secret storage versus secret injection; encryption tooling versus runtime credential access; service identity versus the secret it authenticates with; a definition versus its execution; the production path versus a test path; a job runner versus the restricted-data environment its work needs; evidence storage versus gate evaluation; human approval versus automated promotion.

If two responsibilities differ in owner, maturity, deployment, data access or security boundary, model them as separate components.

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

### Triangulating

For every important component or claim, ask: what does the documentation say should exist; what does the work tracker say is being delivered; what does the code show exists; is it merged; is there evidence it is deployed or configured; does it match the design; is the ticket's status consistent with the code; are names and boundaries consistent across sources; is an old implementation being mistaken for the current one; is a proposal being presented as a running service?

## Ledgers

Keep these in `<investigation>/ledgers.md` throughout the investigation (see [Saving files](#saving-files)), and update them as evidence arrives. They are the working record the document is built from.

**Source coverage**

| Evidence area            | Documentation checked | Work tracker checked | Source control checked | Important sources | Gaps |
| ------------------------ | --------------------- | -------------------- | ---------------------- | ----------------- | ---- |
| Architecture             |                       |                      |                        |                   |      |
| Delivery                 |                       |                      |                        |                   |      |
| Implementation           |                       |                      |                        |                   |      |
| Security and data        |                       |                      |                        |                   |      |
| Identity and credentials |                       |                      |                        |                   |      |
| Runtime and operations   |                       |                      |                        |                   |      |

**Component evidence**

| Component | Runs in | Vision | Delivery | Implementation | Conclusion | Confidence      |
| --------- | ------- | ------ | -------- | -------------- | ---------- | --------------- |
| Its name  | Place   | Design | Tickets  | Repos and code | Reading    | High/Medium/Low |

**Improvements**

| ID  | Severity | Area | Problem | Evidence needed | Proposed improvement | Status |
| --- | -------- | ---- | ------- | --------------- | -------------------- | ------ |

Severities:

- **Critical**: a wrong current-state claim, an unsafe recommendation, a major missing component, or current and target states confused.
- **High**: an unverified implementation claim, an unresolved contradiction, a wrong boundary, or a misleading status.
- **Medium**: generic terminology, a missing interaction, a weak explanation, incomplete triangulation, or unclear scope.
- **Low**: readability, formatting, wording or presentation.

Every improvement ends as one of: applied, rejected with a reason, blocked by missing evidence, or turned into an explicit open decision.

## Component status

Give every component one status:

- 🟩 **Existing**: implemented, with reasonable evidence it is active.
- 🟨 **Exists but needs significant work**: a usable implementation exists but doesn't meet the proposed capability.
- 🟦 **In delivery**: tickets and code show active work, not confirmed complete or deployed.
- 🟥 **Not implemented**: documented or ticketed, but no implementation found.
- ⬜ **Unverified**: access or evidence is insufficient.
- ⚫ **Legacy or superseded**: still in the evidence, but not the current direction.

Never give green only because a document describes a component or a ticket is Done.

## Steps

### 1. Define the investigation

Find the technical question, the system and capability boundaries, the audience, the level of detail, whether the user needs the current state, the delivery status, the current milestone, the target architecture or all four, and the destination page, if they name one.

**A request for a short output** (an exec summary, "100 words", "keep it simple", a one-paragraph status, a chat-sized update) **is about the output's format, never the investigation's scope or rigor.** Run every step below in full, exactly as for the long document, and write that document; then compress it into the short format as a last step. A later request for more detail, another angle or the full document is then answered from the same investigation, not researched again, unless it asks something the investigation didn't cover.

Then prepare the investigation's folders:

1. Get the `folder` and whether it is `temporary` from `output_folder.py` (see [Saving files](#saving-files)). If it fails, stop here.
2. Name the topic with a slug: the topic in a few words, in lower case, with each run of characters other than letters and digits replaced by one hyphen, such as `payments-retry-service`.
3. The investigation's own folder is `<YYYY-MM-DD>--<slug>` in `<folder>`, with today's date: `<investigation>` below is that relative path, and `<investigation_dir>` its full path. Its files are written there with `--path '<investigation>/<file>'`, which creates it. If it already exists, this is a follow-up: continue the investigation in it.
4. If `<folder>` holds folders of the same slug on other days, or `<investigation_dir>` already has files, read them first. An earlier investigation of the topic is a lead to verify, not evidence to copy, since its sources may have changed.
5. The approved examples are in `<folder>/_examples`, `<examples_dir>` below, next to the investigations' folders (the underscore lists it first). If it has no `README.md`, write it (`--path '_examples/README.md'`) with this index:

   ```markdown
   # Examples

   Tech investigations the user approved, kept for their tone, structure and style only. They are never evidence: the topics they describe may have changed since.

   Each example has its own `<YYYY-MM-DD>--<slug>--<format>` folder, with a numeric suffix when needed. One line per example, newest first: a link to its document and what makes it a good example.

   ## Index
   ```

Look in `<examples_dir>` for one or two approved outputs of the format asked for (its `README.md` indexes them), and skim them for tone, structure and voice only. Never reuse a fact, status or claim from an example: its topic may be stale.

### 2. Map the investigation

List the source families and the independent questions to ask each group, and search each group separately, according to its role. Follow every material identifier you find: a service or component, repository or package, endpoint, configuration repository, CI job or workflow, ticket, pull request or commit, registry, datastore, infrastructure component, security mechanism, team or code owner, or superseding document.

Follow an identifier when it could change the current architecture, the delivery status, a component's classification, a security boundary, the current milestone's scope, the target architecture or the work required. Stop a branch only when it is irrelevant, duplicated, inaccessible or too weak to change a conclusion, and record material inaccessible sources as gaps.

Then build the **component inventory**, and finish it before drafting the document or diagrams. Keep updating the ledgers while you read. A conclusion or diagram drawn from a partial reading misleads more than a gap that is stated.

1. **List every component, from every source.** Take each relevant repository's full file tree and list every deployable or runnable unit: services, web and desktop apps, CLIs, workers, jobs, servers and functions (for example everything under `services/`, `apps/` or `cmd/`), and every library that talks to something outside its own process. Add every workload in the deployment manifests and every infrastructure resource they use. Add every component the documentation and the tickets name, even if no code was found for it.
2. **Read every component in full.** For each one, read its README and its own code for everything it calls and everything that calls it: HTTP, gRPC and SDK clients, queues, the child processes it starts, the files and folders it reads or writes, its environment variables and configuration, its network policies, and the identity and credentials it uses. A search hit is a lead, not a reading. If you delegate the reading, tell the helper to read each component in full and to return its connections, and check that it did.
3. **Record it in the ledgers.** Each component gets a row in the component evidence ledger with where it runs, and each of its connections is noted. A component you could not read in full is marked so, with the reason, and stays a gap, never an assumption.

The inventory is complete when every component from step 1 has been read in full or recorded as a gap. Only then write draft 1.

### 3. Write draft 1

Once the component inventory is complete, write `<investigation>/investigation.md` in the [document's structure](#the-document), from the evidence so far. Treat it as a hypothesis to test.

### 4. Review the draft critically

Review it as each of these readers:

- **Software architect:** are responsibilities and boundaries right?
- **Implementing engineer:** can the code be found and the changes understood?
- **Delivery lead:** does it match the tickets' scope, status, dependencies and blockers?
- **SRE or platform engineer:** are execution, deployment, identity, credentials and operations concrete? Is any component in the inventory, or any connection it makes, missing from the map?
- **Security and privacy reviewer:** are data classes, trust boundaries and restricted paths visible?
- **Product owner:** is the current milestone understandable and deliberately scoped?
- **New reader:** can the flow be followed without the conversation that produced it?

Also ask, as a stakeholder would: what is this component in practice; does it exist; where is it implemented, and in which repository; which ticket delivers it; is it a service, library, job, workflow, datastore or logical capability; who calls it, through which interface; why is it a separate box; where are its configuration and credentials resolved; does this happen in CI, the application or another runtime; does this path use production or restricted data; is it current, in delivery, in the current milestone or target; where does it run; what is explicitly not being built; could an engineer implement the work from this description? When one can't be answered clearly, investigate and revise rather than adding vague prose.

Challenge every component, interaction, status and conclusion, and record every finding in the improvements ledger before editing.

### 5. Apply every improvement

Apply every improvement the evidence supports. When a claim or component changes, check everything it affects: the executive summary, the current state, the delivery status, the architecture map, both sequence diagrams and their commentary, the current milestone's boundaries, component statuses and work required, open decisions and references. Never fix one paragraph and leave a contradicting diagram or conclusion.

### 6. Review again, and research again

Review the whole document again, not only what changed. Ask whether the improvements introduced contradictions; whether revised boundaries reveal missing components; whether a concrete name points to another repository, ticket or document; whether the code changes how a ticket reads, or a ticket changes how a document should be labeled; whether recent evidence supersedes an older source; whether diagram numbers and commentary still match; whether every status is still justified; and whether the remaining unknowns are really unresolved.

When new questions arise, go back to the sources, update the ledgers and the document, and review again. Repeat steps 4 to 6 until the [convergence criteria](#convergence-criteria) are met; there is no fixed number of rounds.

### 7. Reflect before handing over

Answer, for yourself: what changed between the first and final drafts; which first assumptions were disproved; which components became more concrete; which conflicts were resolved; which conclusions depend on unavailable evidence; which decisions still need a human owner; and why another round is unlikely to improve the document with what is known now. Hand over only when the last answer is clear and defensible.

### 8. Hand over

- Always give the user a link they can click to open the document: a Markdown link to its full absolute path, such as `[investigation.md](<investigation_dir>/investigation.md)`.
- If they asked for a short format, write it to `<investigation>/<format>.md` (for example `exec-summary.md`), show it in the chat and link the full document under it. Otherwise, give a few lines on the headline: the current reality, the current milestone and the main open decision.
- Name every source that was unavailable, and what it leaves unverified.
- If they named a destination page in an enabled `documentation` source, show what you will write there and publish it only after they approve.
- If `temporary` is `true`, say the folder is temporary: offer to copy the document somewhere they choose, and mention that setting `output.root` in the config keeps investigations and examples.

### 9. Keep approved outputs as examples

When the user says they are happy with a document or summary this skill produced, copy it, exactly as approved and with its original filename, into `_examples/<YYYY-MM-DD>--<slug>--<format>/` in `<folder>`, where `format` is `long-analysis`, `exec-summary` or another short label for the shape they asked for (such as `slack-update`). Never overwrite an earlier example: if that folder exists, append `--2`, `--3`, and so on, choosing the first unused name. Copy its locally linked documents and images into that example folder too, preserving relative paths, so the approved version remains self-contained after the investigation changes. Use the shared writer for every copied file. Each approved version is kept separately, so the collection shows how the user's style has evolved. Then add one line for it at the top of the `## Index` list in `_examples/README.md`, writing the whole index again: its link and what makes it a good example. If `temporary` is `true`, say the example will be lost when the temporary folder is cleared.

## The document

This is the full document every investigation writes, whatever format the user asked for.

```markdown
# <Technical topic>

## Executive summary

The problem, the current reality, the current milestone, and why it matters.

## Status and evidence quality

Which parts are confirmed, in delivery, proposed, historical, conflicting or unverified, and which sources were unavailable.

## Current reality and current milestone

What is demonstrably implemented, what the work tracker shows is being delivered, and how both differ from the documented vision. Then the milestone that delivery is working towards: what it delivers and why it is the right next step, a numbered Mermaid sequence diagram, numbered commentary matching every interaction, and its boundaries and exclusions.

## Directional target architecture

Opens with the status legend (see [Component status](#component-status)), since the map, the target flow and the work table use it. Then the architecture map (see [The architecture map](#the-architecture-map)): every component, current and coming, grouped by where it runs. Then the target flow: a numbered Mermaid sequence diagram with matching commentary, and a clear line between it and committed delivery.

## Vision, delivery and implementation gaps

Vision with no ticket; tickets with no implementation found; implementation absent from the documented architecture; ticket statuses the code contradicts; components built differently from the design; legacy components current documents still name; open pull requests that change the current state; missing deployment evidence.

## Work required by component

For each component: name and status; type (service, library, repository, job, workflow, datastore, external system or logical capability); current state; where it runs; responsibility and interfaces; identity and credentials; owner, when evidenced; work required; dependencies and open decisions.

## Decisions and unknowns

Each open choice, the candidates the evidence supports, the evidence still needed, and the team or role that must decide.

## References

Every material document, ticket, repository and pull request, with historical, superseded or weaker sources labeled as such.
```

### Diagrams

A diagram is a verification tool, not decoration. In every diagram:

- Use concrete component names where known.
- In sequence diagrams, number the interactions in execution order, and give every number matching commentary. The architecture map labels connections by interface rather than execution order.
- Show loops, branches, blocked and error outcomes, and human decisions where material.
- Show a store only when something reads or writes it, and credential injection when it is what makes execution possible.
- Show data and trust boundaries where material.
- Draw no unexplained arrows, no participant that never interacts, and no arrow between components that don't actually communicate.
- Keep the current milestone's diagram simpler than the target one.

If a diagram is hard to follow, fix the model before the styling.

### The architecture map

One diagram of the whole system: what the components are, where each runs, and how they talk. The sequence diagrams show one flow over time; the map shows the structure they run on.

- Draw a Mermaid `flowchart TB` (top to bottom, so it fits a page). Every connection line may only be perfectly horizontal, perfectly vertical or at 45 degrees, and every change of direction is a rounded 90- or 45-degree corner: never a curve, never another angle. Mermaid can't draw 45-degree segments, so make the map's first line `%%{init: {"flowchart": {"curve": "rounded"}, "elk": {"lineHops": "gap"}}}%%`: it routes every connection horizontally and vertically with rounded corners, and breaks a line where another crosses it instead of drawing an arc over it. Never use another `curve` value, line hops other than `gap`, or a layout that draws curves or free diagonals. Give it one `subgraph` per place a component runs, named concretely: a person's machine (such as a CLI, desktop app or browser), each company runtime (such as a named cluster, account or network), managed cloud services, and third-party SaaS. Nest subgraphs where it matters, such as a namespace inside a cluster inside an account.
- One node per component from the [work required](#the-document) table, with its concrete name and its status emoji. Include current, current-milestone and target components on the same map, so it shows what exists and what is coming.
- One arrow per real connection, labelled with its interface (HTTP, Socket Mode, SDK, queue, SQL, MCP, OAuth) and, where it matters, the identity it uses. Draw an arrow with `-.->` when it doesn't exist yet.
- Show data stores only when a component reads or writes them, and mark the trust boundaries that data or credentials cross.
- Draw it from the [component inventory](#2-map-the-investigation), never from the flows alone: every component in the inventory and every connection it records. A component with a single arrow, or none, is a sign of a component not yet read in full: go back and read it before drawing. A client app's connections matter most: where it sends user data, and which model or account it uses, can bypass the system's own boundaries.
- Every component in the sequence diagrams appears on the map, in the same place, with the same name.
- Viewers draw Mermaid with their own versions and settings, so the document shows the map as an image. Only the map: the sequence diagrams stay as Mermaid blocks in the document. Render it with `output_diagram.py --theme dark` to `<investigation>/architecture-map.svg` (see [Saving files](#saving-files)), so it is drawn on a dark background with each place tinted in its own colour, embed it as `![Architecture map](architecture-map.svg)`, and keep its Mermaid source under it in a `<details><summary>Mermaid source</summary>` block, so it can be edited and rendered again. Render it again whenever the source changes. If Node.js isn't available (exit code `3`), show the Mermaid block itself instead, and tell the user the map is unchecked and may look different in their viewer.

### The current milestone

The milestone the team is delivering now: at the start of a project, its first iteration; later, the next step from where delivery stands. Take it from the work tracker (the active epic, milestone or sprint goal) and say so; if none is defined, propose one and label it as proposed.

It must state its single practical outcome; the first product or use case; the components reused, changed and newly built; the exact execution flow; credentials and execution identity; data classification and environment; the evidence it produces; the human decision point; and what it explicitly excludes.

Check for scope creeping in: more products, production data, release gates, pull-request automation, rewrites, new gateways, long-term governance, target-state credential systems or production infrastructure. A narrow milestone isn't incomplete when its exclusions are deliberate and visible.

### Writing style

- Lead with plain English, then introduce the technical terms.
- Stay high level but operationally concrete, with short, precise component names and concise diagram interactions.
- Explain why a component exists, not only what it is called.
- Avoid vague boxes such as "platform", "backend", "gateway" or "credential store" when the evidence supports a precise name.
- Make uncertainty explicit, link the sources of material claims, and never overstate completeness when a source was unavailable.

## Convergence criteria

The document is ready only when all of these hold.

**Evidence coverage**

- Every group has been investigated or explicitly marked unavailable.
- Every material linked source has been followed.
- Vision, delivery, implementation, security, identity and operations are covered.
- No known relevant document, ticket, repository or pull request is left unexamined.
- The component inventory is complete: every component from every repository tree, deployment manifest, document and ticket has been read in full, or recorded as a gap with the reason.
- Every component on the architecture map shows all the connections its code makes and receives; none is drawn from a search alone.
- Refined searches no longer change the architecture materially.

**Claims**

- Every material claim says what kind of evidence backs it.
- Current implementation claims rest on implementation evidence where it was accessible, delivery claims on the work tracker, vision and target claims on the documentation, clearly labeled.
- Conflicts are resolved or explicitly documented.
- Historical sources aren't presented as current, and no assumption is written as a fact.

**Components**

- Every component has one clear responsibility and a type.
- Generic names are replaced wherever concrete ones are known.
- Components with different responsibilities or security boundaries are separate.
- Every status is backed by evidence.
- Current, in-delivery, current-milestone and target components aren't mixed.
- The architecture map places every component where it runs, and agrees with the sequence diagrams.

**Flows**

- Every interaction has a real initiator and recipient.
- Every numbered arrow has matching commentary, and every commentary step is in the diagram.
- Inputs, outputs, versions and failure outcomes are shown.
- Credential and data boundaries are visible where material, and human decisions are explicit.
- Diagrams and prose tell the same story.

**Scope**

- The current milestone is practical and narrow, and its exclusions are explicit.
- Reused, changed and new components can be told apart.
- No target-state capability has leaked into the current milestone's commitments.
- Delivery status is kept apart from architectural ambition.

**Improvements**

- No Critical, High or Medium improvement is still actionable.
- Every Low improvement is applied or consciously rejected.
- Every blocked improvement says what evidence or decision is missing.
- Every open decision lists its candidate options where known.
- The final review raises no new material issue.

"No open issues" never means inventing answers to questions that need an outside decision. It means every issue found has been resolved by evidence, corrected in the document, rejected with a documented reason, marked as an evidence gap, marked as a decision with an owner, or classified as out of scope: no silent ambiguity, no unexamined contradiction, no unsupported certainty, no known relevant evidence ignored, no actionable quality issue left unapplied.

Don't iterate until the document has no questions. Iterate until every available source is exhausted, every material question is investigated, every resolvable ambiguity is resolved, and every remaining uncertainty is visible, precise and owned.
