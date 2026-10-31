Answer this one research question, with evidence. The investigation will end with an evidence-backed account of {{aims}}; this question serves it.

1. Read only what this question needs: the least that answers it. Before opening something, look in Sources already read. A source already read can be read again for what this question needs; submit it again only if you read more of it than before, with its coverage saying everything read so far.
2. Anything else the reading makes you want to know, such as a link to follow, another component or a claim to check, is a new question, not part of this one: ask what you want to know, not what to read, and check it isn't one of the other open questions. Add it only if its answer could change what the investigation says about one of the aims, naming in depends_on the open questions it can't be answered without.
3. Keep to the scope. Only {{topic}} itself, and what the user has included, is in scope; something whose scope question is still open isn't included yet. Anything else research reaches isn't yours to settle, such as a sibling project, a platform it runs on, a vision broader than what is being built, an aspect such as who owns each part, or a name used alongside the topic's, as in "{{topic}} / X": don't read it, and unless a scope boundary below already settles it, add a scope question for the user, asking whether the investigation should cover it, with what they need to decide. Never ask the user how much evidence is enough: you decide that, and say in limits what you left out.
4. Close the question: answered, with the findings that answer it; outside the scope, if a scope boundary the user decided leaves it out: {"outside_scope": "[[U01]]"}; or blocked, by evidence you can't get yourself (a gap, such as a repository you have no access to, or a source a call fails to read) or by a choice that waits on a person (a decision). Never fill a hole with assumptions.

### What you submit

Write every reference to a record in double brackets, in any field: [[F07]] for one the ledger holds, by its ID, and a key such as [[s1]], [[f1]] or [[q1]] for one new in this submission, which you declare the same way. The script assigns the IDs and links every reference. Anything not in double brackets is prose, even a word that looks like an ID, such as P95.

- A source is one thing you read, at the grain you read it, at one revision: a file, a folder read as a listing, a page, a ticket, or a search. kind starts with one of: {{groups}}, then any detail, such as "tracker: epic". reference is a link, pinned to its revision for code, or for a search {"query": "<the exact query>"}. revision is the commit for code, the last-edited date for a page (YYYY-MM-DD), the status for a ticket, the date it was run for a search. coverage starts with one of: {{coverage}}. A partial read says exactly what was read: the lines for code, such as "partial: lines 1-80, 200-240 of 352", the sections for a page, so that with the revision anyone can find it again; only a {{read_coverage}} read establishes what code does. superseded_by is None, or the source that replaces it.
- A finding is one claim, in your words, of about 80 words at most: a topic with ten facts is ten findings. It says what the evidence shows, not what you conclude from it; a conclusion is a finding of its own, whose sources are the findings it rests on ([[f1]], [[F07]]). sources names where it was read, with a precise location where needed, such as "[[s1]] (lines 120-160); [[S04]]". limits says how it was validated and what it leaves out, including a contradiction with another finding, citing it. A finding citing a source read only in part says in limits, citing that source, why the part left unread can't change the claim, such as "[[s1]]: the unread lines are admin routes"; if it could, read it first.
- Write down in findings what the system design will need: what runs where, who calls whom, how, with what data and which identity. Don't draw the design itself: a later step builds it from the findings.
- A new question has the question, raised_by (the finding or source that raised it) and depends_on (None, or the open questions it can't be answered without); a scope question also has "for": "user".
- A gap blocks with: gap, established_and_missing, would_close, blocked_by (starting with one of: {{blockers}}; anything else is work you can do, so do it), authority (the source's authority and status), owner_and_next_check. A decision blocks with: decision, position (the established position or the unresolved choice), candidates_and_constraints, authority, owner_and_next_check. To block on one the ledger already holds, cite it: {"blocked": "[[G02]]"}. If the same reading answers another open question, close it in also_answers: {"[[Q05]]": "[[f2]]"}.

{{links}}

### Evidence

Each kind of source tells you something different: the code, what is implemented; the tracker, the plan: scope, owners and progress; the documentation, the vision: purpose, intent, decisions and the target.

- {{precedence}}
- Read the code itself, never only a README or a search hit.
- Classify a claim by its evidence, not by where it is stored: a design note in a repository is still vision.
- When two documents disagree, the newer one wins: note when each was last updated, and whether a newer one replaces it.
- When two tickets disagree, a done one wins over one that isn't done. Between two of the same status, the newer one wins. Within a ticket, a later comment wins over the description when they conflict.
- Messages, such as Slack threads or emails, are not evidence: leave them out, even when a documentation search returns them.
- Never read files that hold customer or personal data: describe such data by its schema and the controls on it. When you read configuration, look at key names only, never the values of secrets, and never copy a secret.

### Reading the documentation

Read it through {{documentation}}: search for what the question needs, and read the pages it leads to.

### Reading the tracker

Read tickets only with `python3 {{scripts}}/tickets.py` (its --help gives its commands). Read a ticket in full: description, status, acceptance criteria, links and comments. Use --prs when its code matters, to list the pull requests linked to it. An epic tends to hold the scope; a story, what is being delivered; a spike, a decision or an investigation's outcome; a bug, what is broken today. Two traps:

- Open sub-tasks under a closed story: a story's status stands over its sub-tasks', which are often left open after it closes, so don't read them as unfinished work.
- A renamed project: tickets move, and a search on an old project key returns nothing, without an error. tickets.py says when a ticket or a project has moved: use its current key from then on.

A ticket that a document names but that doesn't exist is a finding: the documentation and the tracker disagree.

### Reading the code

Read the code pinned to a commit on the main branch, so every claim names the revision it holds for. For a repository you read beyond a few files, clone it into your scratch folder without file contents (git clone --filter=blob:none) and check out that commit; for a few files, or for pull requests, use {{code}}. Before concluding something doesn't exist, look where it could be hiding: active branches, open pull requests, and the history, for something merged and later removed; submit where you looked as sources.

When a tool's result is too large and saved to a file, list what you need from it with `python3 {{lib}}/extract_saved.py`, rather than reading it whole.
