# Data report

A skill that builds a document from data it fetches or reads, such as a sprint's tickets or a person's work and messages: summarising some of it with judgment, such as subagents reading notes a month at a time, doesn't make it research, as it keeps no ledger of sources and findings.

The rules in [AGENTS.md](../AGENTS.md) apply to it, among them [Model, views and checker](../AGENTS.md#model-views-and-checker); this file adds what a data report has on top.

## The steps

1. **Start:** when the run needs input settled with the user before its work, `init_<run>.py` creates the run's folder and records what the user settled, such as who the document is about.
2. **Fetch:** what the sources give goes to `_raw/`, as they gave it.
3. **Model:** `build_data.py` builds `data.json` from `_raw/`, with no network, so running it again rebuilds the model.
4. **Brief:** when the document has parts the agent writes, the brief holds only the material of each such part, taken from the model: the agent never reads the model whole, so its tokens go on judgment, and the facts it writes from are the model's, so its text can't contradict them. Here it is a file, `brief.json`, which `make_brief.py` writes from `data.json`. `prepare_report.py`, one command, then runs everything before the writing that a script does, from the fetch to the brief.
5. **Write:** the agent writes `content.json`, the text of each part, from the brief alone, following the schema and the rules the skill gives.
6. **Finish:** `finish_report.py`, one command, validates `content.json` field by field when there is one, writes the document with `make_report.py`, the view, and its charts into `_charts/` with `make_charts.py`, and runs `check_report.py`, which reads the document back and works its figures out again from `data.json`'s basic records.

## Checked

`tests/repo/` checks that a data report has `build_data.py`, `finish_report.py`, `make_report.py` and `check_report.py`, `make_charts.py` when its SKILL.md names `_charts/`, and `make_brief.py` and `prepare_report.py` when it names `brief.json`.
