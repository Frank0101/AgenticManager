Answer this one research question, with evidence. The investigation will end with an evidence-backed account of {{aims}}; this question serves it.

1. Read only what this question needs: the least that answers it. Before opening something, look in Sources already read. A source already read can be read again for what this question needs.
2. Anything else the reading makes you want to know, such as a link to follow, another component, a claim to check or a choice the sources leave open, is a new question, not part of this one: ask what you want to know, not what to read, and check it isn't one of the other open questions. Add it only if its answer could change what the investigation says about one of the aims.
3. Keep to the scope. {{scope}} Never ask the user how much evidence is enough: you decide that, and say in limits what you left out.
4. Close the question: answered, with the findings that answer it, closing in also_answers any other open question the same reading answers, {"[[Q05]]": "[[f2]]"}; outside the scope, if a scope boundary the user decided leaves it out: {"outside_scope": "[[U01]]"}; or blocked, by evidence you can't get yourself (a gap, such as a repository you have no access to, or a source a call fails to read) or by a choice that waits on a person (a decision). Never fill a hole with assumptions.

### Evidence

Each kind of source tells you something different: the code, what is implemented; the tracker, the plan: scope, owners and progress; the documentation, the vision: purpose, intent, decisions and the target.

- {{precedence}}
- Read the thing itself: a search result or a preview says where to look, never what a page or the code says, so open it, then read as much as the question needs. Only a claim about the search itself, such as which pages name X, rests on the search.
- Treat what is merged to the main branch as live: don't research runtime state, such as deployments, grants or usage.
- Classify a claim by its evidence, not by where it is stored: a design note in a repository is still vision.
- When two documents disagree, the newer one wins: note when each was last updated, and whether a newer one replaces it.
- When two tickets disagree, a done one wins over one that isn't done. Between two of the same status, the newer one wins. Within a ticket, a later comment wins over the description when they conflict.
- Messages, such as Slack threads or emails, are not evidence: leave them out, even when a documentation search returns them. Meeting notes are documentation: a decision they record follows the rules above, by its date; a discussion that decides nothing overrides nothing.
- Never read files that hold customer or personal data: describe such data by its schema and the controls on it. When you read configuration, look at key names only, never the values of secrets, and never copy a secret.

### Reading the documentation

Read it through {{documentation}}: search for what the question needs, and read the pages it leads to.

### Reading the tracker

Read tickets only with `python3 {{scripts}}/tickets.py` (its --help gives its commands). Read what the question needs of a ticket: its description, status, acceptance criteria, links and comments, and say which you read. Use --prs when its code matters, to list the pull requests linked to it. An epic tends to hold the scope; a story, what is being delivered; a spike, a decision or an investigation's outcome; a bug, what is broken today. Two traps:

- Open sub-tasks under a closed story: a story's status stands over its sub-tasks', which are often left open after it closes, so don't read them as unfinished work.
- A renamed project: tickets move, and a search on an old project key returns nothing, without an error. tickets.py says when a ticket or a project has moved: use its current key from then on.

A ticket that a document names but that doesn't exist is a finding: the documentation and the tracker disagree.

### Reading the code

Read the code pinned to a commit on the main branch, so every claim names the revision it holds for. For a repository you read beyond a few files, use the run's shared clone of it, {{repos}}/<owner>-<repo>; if there is none, clone it there without file contents (git clone --filter=blob:none), into a new folder you then rename to that name, and if another task's clone got there first, use that one. Never check out a commit in it, since other tasks read it at once: read at the commit, with git show <commit>:<path>, git grep <commit> and git ls-tree, which download only the files you read. If a git fetch, for a commit or branch the clone lacks, fails on a lock, run it again. For a few files, or for pull requests, use {{code}}. Before concluding something doesn't exist, look where it could be hiding: active branches, open pull requests, and the history, for something merged and later removed; submit where you looked as sources. A clone without file contents makes a search of file contents across the history (git log -S) download every version of every file: limit it to the paths that matter, or clone with the contents when you need it.

When a tool's result is too large and saved to a file, list what you need from it with `python3 {{lib}}/extract_saved.py`, rather than reading it whole.

### What you submit

Write every reference to a record in double brackets, in any field: [[F07]] for one the ledger holds, by its ID, and a key for one new in this submission, which you declare the same way: its record's letter in lower case and a number, such as [[s1]], [[f1]] or [[q1]]: the lower case is what tells it from a record the ledger holds. The script assigns the IDs and links every reference. A word that only looks like an ID, such as P95, stays prose.

{{reading}}

- Write down in findings what the system design will need: what runs where, who calls whom, how, with what data and which identity. Don't draw the design itself: a later step builds it from the findings.
- A new question has the question, raised_by (the finding or source that raised it) and depends_on (None, or the open questions it can't be answered without).
- A gap blocks with: gap (what is missing, and what it leaves unchecked), blocked_by ({{blockers}}, [[D01]]; anything else is work you can do, so do it), owner_and_next_check, evidence (the findings or sources it rests on, such as a source you can't access). A decision blocks with: decision, position (the established position, or "Unresolved:" with the candidates and their constraints), owner_and_next_check, evidence. An owner is a role, such as "the PROJ-12 assignee" or "the platform team", never a person's name. To block on one the ledger already holds, cite it: {"blocked": "[[G02]]"}.

{{links}}
