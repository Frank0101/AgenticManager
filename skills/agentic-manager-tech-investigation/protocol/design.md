Build the system design from the findings below: enough to draw an accurate diagram of the system as it is today and as the target describes it. Submit the whole design every time: a row of the current design you leave out is removed. Keep a row by giving its ID as its key, [[C03]]; give a new row a new key, [[c1]]. Write every reference in double brackets, [[F07]] or [[c1]]. Each row rests on findings, or on the gap that explains it.

1. Components: every part that runs, stores or talks across a boundary, such as a service, job, library that calls out, store, queue or external product, and the people or roles that act on it. name_and_type is the name, then its type in brackets, such as "Search API (service)". Challenge a generic noun, such as "platform" or "gateway": what runs where, called by whom, and what proves it exists. code links its repository and paths at the pinned revision, or says None. status starts with one of: {{statuses}}. A component is in the state its strongest evidence shows. {{precedence}} 🟩 and 🟦 need a code source with coverage {{read_coverage}} of a path it links, a file under it or a folder above it. boundary is the boundary it sits in, or None.
2. Connections: who calls whom (from and to, one component each), how (HTTP, queue, file, SDK), with what data, whether the caller waits for a reply, with which identity (or None, or Unknown), and its state, as for components.
3. Boundaries: what groups components, such as a network, an environment, a trust zone or the team that owns them.
4. Identities: the credentials or accounts connections use, and what each can reach; several connections often share one.
5. Flows: for each entry point that matters, the connections it uses, in order.
6. Unknowns: a component or connection you can't establish is ⬜ Unverified, with the gap that explains it in evidence; a caller you can't identify is a component of unknown type. Never guess one.

Draw a topic the user decided as mention only as one component, with its connection to {{topic}} and nothing inside it; draw nothing the user excluded, even where a finding names a connection to it.

The findings name their sources, and each source's coverage names exactly what was read. When a finding is there but too thin to fill a row, re-open its source at that place first: that makes known evidence precise, it adds nothing new. Submit what you read with the design, as sources and findings the rows cite:

{{reading}}

Raise a question only for what no finding or source read so far establishes, and only if it could change what the report says about {{aims}}: a component the documents or tickets name whose code nobody read, a connection whose identity, data or direction no source gives, a step of a flow nobody traced, a boundary nothing establishes. Add it in new_questions, with raised_by naming the row or finding that raised it; research answers it before the design is updated. {{scope}} A scope question has "for": "user". Raise no question about a topic the user decided as mention only or exclude.

{{links}}
