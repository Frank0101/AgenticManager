---
name: agentic-manager-utils-lib
disable-model-invocation: true
description: Python code shared by the other AgenticManager skills, such as reading the config, the Jira client and writing to the output folder. Not a task to run; never invoke it.
---

# Shared code

This skill holds no instructions. Its `agentic_manager` Python package is shared by the other AgenticManager skills' scripts, which find it next to their own folder. It must be installed alongside them.

Two of its modules handle the folder each skill writes its files to. A skill's scripts import them; when the agent writes a skill's files itself, it runs them:

- `agentic_manager/output_folder.py --name <folder name>` prints `{"folder": ..., "temporary": ...}`, the folder, created if missing.
- `agentic_manager/output_file.py --name <folder name> --path <relative path>` writes its standard input to that file inside the folder, and never outside it.

Add `--patch` to the file writer to apply a JSON array of exact `old`/`new` replacements to an existing UTF-8 file. Each nonempty `old` must match once; all replacements are validated before writing. The same output-folder restriction applies.
