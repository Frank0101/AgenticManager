# Conversation document

A skill that builds a document from what the user gives in the conversation: what they ask for, and the material, documents or data they share on the fly, such as a slide deck from a discussion. It fetches nothing of its own, and the user shapes the document with it, so it is built and rebuilt as the conversation goes.

The rules in [AGENTS.md](../AGENTS.md) apply to it; this file adds what a conversation document has on top.

## The steps

1. **Understand the request:** the agent works out what kind of document it is and asks the few questions it can't answer from the conversation, one at a time.
2. **Start:** `init_<run>.py` creates the run's folder and records what the user settled, such as the document's name, and prints what the document can draw on, such as the examples and assets kept beside the runs.
3. **Write:** the agent writes the document's content as a JSON file, such as `slides.json`, in the schema the skill gives: its judgment goes there, and the page around it stays fixed in the script.
4. **Finish:** `finish_<kind>.py`, one command, validates the JSON field by field, writes the document from it with `make_<kind>.py`, the view, and runs `check_<kind>.py`, which reads the document back against the JSON.
5. **Iterate:** each change the user asks for is an edit of the JSON and Finish again, never an edit of the generated document.

## Checked

`tests/repo/` checks that a conversation document has `finish_<kind>.py`, `make_<kind>.py` and `check_<kind>.py`, for one kind. Checks of what only a conversation document has come with its second skill.
