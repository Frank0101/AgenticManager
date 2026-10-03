# Contributing

How to work on AgenticManager and add skills to it. For installing and using the skills, see the [README](README.md).

## Layout

```text
skills/<skill>/          one folder per skill
  SKILL.md               instructions the agent follows
  scripts/               optional helper scripts
tests/<skill>/           tests for that skill, mirroring skills/
tests/run.py             runs every skill's tests
.claude/skills  ─┐       symlinks to skills/, so the skills load when you run
.agents/skills  ─┘       Claude Code or Codex inside this repo
```

Edits to a skill apply to the next agent session. A running session keeps the instructions it already loaded.

## Writing a skill

1. Create `skills/agentic-manager-<name>/SKILL.md`. Every skill uses the `agentic-manager-` prefix, so users can find them among skills from other sources. The folder name and the frontmatter `name` must match.
2. Write a `description` that says what the skill does and when to use it. Agents use it to decide when to load the skill.
3. Start the instructions with the prerequisite, naming the groups the skill needs:

   ```markdown
   ## Prerequisite

   Run `agentic-manager-check-config` for `workflow` and `source_control`. If it fails, stop here.
   ```

4. Refer to groups, not tools. Use the sources `agentic-manager-check-config` returns, reaching each tool through its channel (`mcp`, `cli` or `api`) and using its settings for credentials. Never hard-code a tool, URL or credential.
5. The skill must never change the user's config on its own. If something in it needs to change, the skill stops and tells the user what to change. It may offer to make the change, but makes it only after the user explicitly approves.
6. Write scripts in Python 3.8+ using only the standard library, so users install nothing extra.
7. Add tests in `tests/<skill>/test_*.py`.

## Adding a source

[config-template.json](skills/agentic-manager-check-config/config-template.json) is the only definition of what's supported. To add a source:

1. Add it to the template under its group, named `<tool>-<channel>`, with `"enabled": false`. The channel is `mcp`, `cli` or `api`.
2. Give each setting a placeholder in angle brackets, such as `"<token>"`. The check reports a placeholder as not filled in when the source is enabled.
3. Add tests for any new behavior it needs. The existing tests already check that every template entry follows the rules above.

To add a group, also add it to the groups table in the check-config [SKILL.md](skills/agentic-manager-check-config/SKILL.md). A test checks that they match.

Users' existing configs keep working: a source they don't list counts as disabled. When a skill requests its group and nothing in it is enabled, the check tells the user exactly how to set it up: which JSON to add, or which source to enable.

## Testing

```bash
python3 tests/run.py       # add -v to list each test
```

Tests run scripts with `HOME` pointed at a temporary folder. The config is part of each test's setup, so every test gets one it is free to change for its own purposes. Skill names contain hyphens, so `python3 -m unittest discover` doesn't find the tests; use `run.py`.

## Secrets and internal data

Skills will often be written from real cases at work. Nothing from those cases may end up in this repo.

- **No secrets in the repo.** Tokens, passwords and keys only go in the user's own config, `~/.config/agentic-manager/config.json`. The template holds placeholders only.
- **No internal data in the repo.** No real names, ticket numbers, project keys, URLs, channel names, messages or documents, in skills, examples, tests or commit messages. Use made-up examples such as `PROJ-123` or `acme`. Anything specific to a team belongs in the user's config, as a setting.
- **Never show secrets.** Skills must never display a setting's value, such as a token, in the chat, in output or in files they write. Refer to it by name instead (for example "using your `personal-access-token`").

Before committing, check the diff for anything that came from a real case.

## Documentation

- The [README](README.md) is for people installing and using the skills. Keep it short; contributor details go here.
- When you add a skill, add it to the README's Available skills table.

## Pitfalls

- **Never run `npx skills` from inside this repo.** The `skills` CLI has a bug: `remove -g` also deletes `<current folder>/.agents/skills/<skill>`, and here that's a symlink to `skills/`, so it deletes the skill's source. Run install, update and uninstall from another folder. Don't add `--agent` to the README's uninstall command to work around it: the CLI then keeps the shared `~/.agents/skills` copy whenever another installed agent uses that folder.
- **Reinstall, then start a new session.** After pushing, run the README's install command from outside the repo, then start a new agent session to pick up the changes.

## Releasing

Push to `master`. Users get the changes by running the install command again.
