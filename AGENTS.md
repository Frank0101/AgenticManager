# AGENTS.md

Before working in this repo, read [README.md](README.md) (what the skills do and how users install them) and [CONTRIBUTING.md](CONTRIBUTING.md) (the design choices behind the repo).

Each document has one reader: the README is for the user, CONTRIBUTING for the developer (design, not procedures), and this file for you (how to do things). Keep new content in the right one.

## Rules that always apply

- **Never change the developer's config without their approval, and keep it out of the repo.** Skills run here read the developer's config (`~/.config/agentic-manager/config.json`), as they do anywhere else. If it's missing, you may ask whether to create it from the template. For any other problem, show how to fix it; you may ask whether to make the change. Change the file only after the developer explicitly approves. Nothing from their config may end up in the repo: not in tests, examples or code, and not as assumptions about which sources are enabled.
- **Never change the developer's installed skills** (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`).
- **Never run `npx skills` from inside this repo.** A bug in the `skills` CLI makes uninstalling delete the skills' source here (see CONTRIBUTING). Run it from another folder.
- **Never display secrets**, such as tokens from the user's config, in the chat, in output or in files. Skills must refer to a setting by name instead, for example "using your `personal-access-token`".
- **Never put secrets or internal data in this repo.** Skills are often based on real work cases. Keep real names, ticket numbers, project keys, URLs, channel names, messages, documents and credentials out of skills, examples, tests and commit messages; use made-up examples such as `PROJ-123` or `acme`. Anything specific to a team belongs in the user's config, as a setting. Before committing, check the diff for anything that came from a real case.

## Writing a skill

- Put it in `skills/agentic-manager-<name>/SKILL.md`. The folder name and the frontmatter `name` must match.
- Start the instructions with the prerequisite, naming the groups the skill needs and saying what the skill does if the check fails (usually stop):

  ```markdown
  ## Prerequisite

  Run `agentic-manager-check-config` for `workflow` and `source_control`. If it fails, stop here.
  ```

- Use the sources the check returns, reaching each tool through its channel (`mcp`, `cli` or `api`) and using the source's settings for credentials. Never hard-code a tool, URL or credential.
- Add the skill to the README's Available skills table.

## Adding a source or a group

- Add the source to [config-template.json](skills/agentic-manager-check-config/config-template.json) under its group, named `<tool>-<channel>` (channel `mcp`, `cli` or `api`), with `"enabled": false`.
- Give each setting a placeholder in angle brackets, such as `"<token>"`. The check reports a placeholder as not filled in when the source is enabled.
- For a new group, also add it to the groups table in the check-config [SKILL.md](skills/agentic-manager-check-config/SKILL.md). A test checks that they match.

## Testing

```bash
python3 tests/run.py       # add -v to list each test
```

- Put a skill's tests in `tests/<skill>/test_*.py`. Skill names contain hyphens, so `python3 -m unittest discover` doesn't find them; use `run.py`.
- Run scripts with `HOME` pointed at a temporary folder holding the test's own config, as the existing tests do.
