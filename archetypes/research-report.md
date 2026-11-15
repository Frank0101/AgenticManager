# Research report

A skill that builds a document from research: the agent looks for its sources, reads them and draws conclusions, and the question of what to read next is part of the work. Its model is a ledger of what the research found, not data fetched up front.

The rules in [AGENTS.md](../AGENTS.md) apply to it, among them [Model, views and checker](../AGENTS.md#model-views-and-checker); this file adds what a research report has on top.

## The steps

1. **Start:** `init_<run>.py` creates the run's folder and records what the user settled, such as the topic, with the ledger's skeleton. The task script runs it through its `start` command, which prints what the agent does next.
2. **Research:** the task script hands out the work as tasks, one at a time or a few in parallel, each to a fresh subagent, with only what the task holds. Each task's instructions are a protocol file of the skill. The script takes each answer, checks it against the ledger's rules and records it in the ledger: sources, findings, open questions, decisions. When the research reaches something only the user can put in or out of scope, the script asks it through the main agent, and records the answer as a scope decision. The ledger is the research's model: every claim cites the records it rests on.
3. **Brief:** the brief holds only the material of each part the document's writer writes, taken from the model: the writer never reads the model whole, so its tokens go on judgment, and the facts it writes from are the model's, so its text can't contradict them. Here the task script prints it from the ledger into the writing task.
4. **Write:** a last task writes `content.json`, the document's text, from the brief alone.
5. **Finish:** `finish_report.py`, which the task script runs when the write task's text is submitted, validates `content.json` field by field, writes the document from the ledger and `content.json` with `make_report.py`, the view, and runs `check_report.py`, which reads the document back against the ledger: every claim cited, every citation a record that exists, nothing in scope left open.

## Checked

`tests/repo/` checks that a research report has `finish_report.py`, `make_report.py` and `check_report.py`. Checks of what only a research report has, such as its ledger and protocols, come with its second skill.
