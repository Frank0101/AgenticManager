# AGENTS.md

Each document has one reader: [README.md](README.md) is for the user (installing, configuring and using the skills), [CONTRIBUTING.md](CONTRIBUTING.md) for the developer (the design choices, not procedures), and this file for you (how to do things). Read the first two before working here, and keep new content in the right one.

## Rules that always apply

- **Never change the developer's config without their approval, and keep it out of the repo.** Skills run here read the developer's config (`~/.config/agentic-manager/config.json`), as they do anywhere else. If it's missing, you may ask whether to create it from the template. For any other problem, show how to fix it; you may ask whether to make the change. Change the file only after the developer explicitly approves. Nothing from their config may end up in the repo: not in tests, examples or code, and not as assumptions about which sources are enabled.
- **Never change the developer's installed skills** (`~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`).
- **Never run `npx skills` from inside this repo.** A bug in the `skills` CLI makes uninstalling delete the skills' source here (see CONTRIBUTING). Run it from another folder.
- **Never display secrets**, such as tokens from the user's config, in the chat, in output or in files. Skills must refer to a setting by name instead, for example "using your `api-token`".
- **Never put secrets or internal data in this repo.** Skills are often based on real work cases. Keep real names, ticket numbers, project keys, URLs, channel names, messages, documents and credentials out of skills, examples, tests and commit messages; use made-up examples such as `PROJ-123` or `acme`. Anything specific to a team belongs in the user's config, as a setting. Before committing, check the diff for anything that came from a real case.

## Writing a skill

- Put it in `skills/agentic-manager-<name>/SKILL.md`. The folder name and the frontmatter `name` must match.
- Unless it's a utility (`agentic-manager-utils-*`), start the instructions with the prerequisite: run the check, stop if it fails, then name what the skill needs from the sources it returns, either specific sources or any source of a group, and what it does if they aren't enabled (usually stop and show their `setup`):

  ```markdown
  ## Prerequisite

  Run `agentic-manager-utils-check-config`. If it fails, stop here.

  This skill needs any enabled source of `workflow`, and the `github-cli` source. If one is missing, stop and tell the user how to enable it, showing its `setup` and the config `path`.
  ```

- If the skill runs its own scripts, pre-approve them in the frontmatter so Claude Code doesn't ask permission for each step, and tell the agent to call them by that same path: `allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/<script>.py *)`, one per script, separated by spaces. Never pre-approve a command that changes the user's config or anything outside the skill's own output; without the ` *`, a rule approves only the command with no arguments, as check-config's does, so its `--init` still asks.
- Reach each enabled source's tool through its channel (`mcp`, `cli`, `api` or `fs`). Never hard-code a tool, URL or credential.
- The check never returns setting values. Reach an `api` or `fs` source through a script that reads its settings with `agentic_manager.config.read_source()`. Never read the config from the skill's instructions, and never pass a setting to a script on its command line.
- A skill that writes files gets its output folder from the library's `agentic_manager/output_folder.py`, never from code of its own: a folder of its own in the user's output root, or in the system temp folder if the config sets none, created if missing, and whether it is temporary, so the skill can tell the user. A script imports its `output_folder()`, as the jira-sprint-report skill's `fetch_sprint.py` does. When the agent writes a skill's files itself, it runs the file, which prints the same, and writes every file through the library's `agentic_manager/output_file.py`, never with its own file tools, as the tech-investigation skill does. The writer only writes inside the skill's output folder, so pre-approve both in the frontmatter: `Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_folder.py *)` and the same for `output_file.py`. State this in the skill's instructions, near the top: that its files go to the user's configured output root, or to a temporary folder if none is set.
- Give the agent only the work that needs judgment: research, classification, conclusions and prose. Anything deterministic belongs in a script: fixed templates and formats, headings, table structure, links and anchors, file layout, diagram mechanics and checks. The agent fills the content in a JSON file that a generator reads, and never edits the generated output by hand, as the jira-sprint-report skill does with `content.json` and `make_report.py` (see CONTRIBUTING's Script-owned skills). When you move work from a skill's instructions into a script, the output must stay the same and keep its quality: compare the script's output with what the skill produced before.
- When changing a report rule, update its generator, checker and relevant tests together.
- Add the skill to the README's Available skills section. A utility goes in CONTRIBUTING's Utilities table instead; the README never mentions utilities.

## Sharing code between skills

- Put code that more than one skill needs in `skills/agentic-manager-utils-lib/agentic_manager/`, not in a copy per skill.
- In a script that uses it, add the library to the path before importing, as `check_config.py` does:

  ```python
  LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         "..", "..", "agentic-manager-utils-lib")
  sys.path.insert(0, LIB_DIR)
  from agentic_manager import config
  ```

- Use `realpath`, not `abspath`: Claude Code installs skills as symlinks to `~/.agents/skills`.
- In a skill with several scripts, do this once in the skill's shared module and import the library's names from there, as sprint-report's `common.py` does. The scripts then don't depend on the order of their imports.
- Keep in the library only what any skill using the same tool or the config would need, such as the Jira client and helpers for Jira keys and timestamps. Choices that belong to one skill, such as which issue fields it fetches, stay in that skill.

## Adding a source or a group

- Add the source to [config-template.json](skills/agentic-manager-utils-check-config/config-template.json) under its group in `sources`, named `<tool>-<channel>` (channel `mcp`, `cli`, `api` or `fs`), with `"enabled": false`.
- Give each setting a placeholder in angle brackets, such as `"<token>"`. The check reports a placeholder as not filled in when the source is enabled.
- For a new group, also add it to the groups table in the check-config [SKILL.md](skills/agentic-manager-utils-check-config/SKILL.md), and for a new channel, to its channels table. Tests check that both match the template.

## Testing

```bash
python3 tests/run.py                   # every skill; add -v to list each test
python3 tests/run.py <skill> ...       # only those skills
```

- Every script or module gets unit tests in `tests/<skill>/test_<module>.py`, calling its functions directly. The shared library is a skill too: its tests go in `tests/agentic-manager-utils-lib/`.
- Tests that run a whole script, or several in a row, are end-to-end tests: name them `test_e2e_<what>.py`. Add them where a script's command line or output is a contract, or where scripts must fit together.
- Put data shared by several test files in a module not named `test_*`, such as `sprint_fixture.py`.
- Skill names contain hyphens, so `python3 -m unittest discover` doesn't find the tests; use `run.py`. It runs each skill's tests in their own Python process, so modules with the same name in different skills don't clash.
- Run scripts with `HOME` pointed at a temporary folder holding the test's own config, and `TMPDIR` too when a script may fall back to the system temp folder, as the existing tests do.
- Write cases that check the same thing the same way as one test over a table of cases, each in a `subTest`, rather than one test per case.
- When you add a skill with scripts, add its test folder to `executionEnvironments` in `pyrightconfig.json`, with the skill's `scripts` folder in `extraPaths`, so editors resolve the tests' imports.
