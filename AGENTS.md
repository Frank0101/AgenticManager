# AGENTS.md

Before working in this repo, read [README.md](README.md) (what the skills do and how users install them) and [CONTRIBUTING.md](CONTRIBUTING.md) (how to write skills, test them and keep the repo clean).

Rules that always apply:

- **Never change the developer's config without their approval, and keep it out of the repo.** Skills run here read the developer's config (`~/.config/agentic-manager/config.json`), as they do anywhere else. If it's missing, you may ask whether to create it from the template. For any other problem, show how to fix it and you may ask whether to make the change. Change the file only after the developer explicitly approves. Never change their installed skills (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`). Nothing from their config may end up in the repo: not in tests, examples or code, and not as assumptions about which sources are enabled. Tests use their own config in a temporary `HOME`, as `tests/run.py` does.
- **Never run `npx skills` from inside this repo.** A bug in the `skills` CLI makes uninstalling delete the skills' source here. Run it from another folder.
- **Never display secrets**, such as tokens from the user's config, in the chat, in output or in files.
- **Never put secrets or internal data in this repo.** When a skill is based on a real work case, keep real names, tickets, URLs, messages and credentials out of skills, examples, tests and commit messages. They belong in the user's config (`~/.config/agentic-manager/config.json`).
