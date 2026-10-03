# AGENTS.md

Before working in this repo, read [README.md](README.md) (what the skills do and how users install them) and [CONTRIBUTING.md](CONTRIBUTING.md) (how to write skills, test them and keep the repo clean).

Rules that always apply:

- **Work as a builder, never as a user.** Don't read, run scripts against or change the developer's own config (`~/.config/agentic-manager/config.json`) or their installed skills (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`). Test only in a sandbox: a temporary folder set as `HOME`, as `tests/run.py` does.
- **Never run `npx skills` from inside this repo.** A bug in the `skills` CLI makes uninstalling delete the skills' source here. Run it from another folder.
- **Never display secrets**, such as tokens from the user's config, in the chat, in output or in files.
- **Never put secrets or internal data in this repo.** When a skill is based on a real work case, keep real names, tickets, URLs, messages and credentials out of skills, examples, tests and commit messages. They belong in the user's config (`~/.config/agentic-manager/config.json`).
