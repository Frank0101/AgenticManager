Write the report's text from the brief below, which holds everything the report rests on. The report has two layers, which don't repeat each other. The executive layer, for a technical leader, says what the system is for, where it stands, where it is going and what needs deciding, with no configuration detail. The architect layer, for engineers, says how it works and how it will change, with no ticket status or plan.

Link each claim to the ledger, such as [F03](ledger:F03); the script writes the title, the evidence date and the references. Report, don't recommend: describe what the evidence shows, never your own recommendations, preferred options, plans or owners; what the sources don't settle is reported as open. Name roles, never people: "the platform team", "the feature's owner". Approximate lengths are room to explain, not quotas: write less when the point is simple or the evidence thin.

The executive layer:

- purpose (about 150 words): the problem, who it affects, why it matters and the intended outcome, in plain language. End with each topic the brief's Boundary section marks mention only, in one line on how it connects.
- current_status (about 200 words): what is done, what is in progress, and the gap between them, keeping implemented, in development and planned apart. Name the evidence limits that matter, such as a source that couldn't be read.
- direction (about 200 words): what comes next, in the order the sources give, separating what the tracker plans from what only the documentation proposes. Give timing only where a source commits to it.
- key_decisions: only the decisions, blockers and risks that need a leader's attention, each with why it matters and its evidence. An empty list is fine.

The architect layer cites the system design's rows, such as a component (C03) or a connection (E05), as well as findings, so an engineer can go from a sentence to what it describes:

- architecture.today (about 300 words): the system design as the ledger records it, saying why each main component exists, not only its name. Cover the entry points, the boundaries of trust, data and identity, and the technical limits, and mark what is only in development.
- architecture.target (about 300 words): what the target keeps, adds, changes or removes compared with today, and why. Keep what the tracker plans apart from what only the documentation proposes, and name the technical choices still open.
- open_choices_and_gaps: the choices and evidence gaps that matter to the target, each with why it matters and its evidence. Look where the sources disagree: vision with no ticket, a ticket with no code, code the design doesn't mention, and a ticket status the code contradicts.

Submit the whole text every time; keep it in a file in your scratch folder and pass it with --input, so a revision changes the file and submits it again.
