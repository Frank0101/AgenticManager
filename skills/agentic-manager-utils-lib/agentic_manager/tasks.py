"""A task a script hands a subagent: its text in a file of its own, and the section that ends it, how to submit its answer.

A task holds everything needed to do it, so the main agent hands a fresh
subagent only its path. Each is task.md in the task's own folder, where its
agent keeps its files too. The answer goes in a quoted here-document, ended by
END_OF_INPUT as every script's --help shows one, so nothing in it needs
escaping.
"""
import os

TASK_FILE = "task.md"


def write_task(folder, task, text):
    """Writes `text`, the task `task`'s, to its file in its folder `folder`,
    created if missing; returns the line that hands it out, as task_line()
    gives it."""
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, TASK_FILE), "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n")
    return task_line(task, folder)


def task_line(task, folder):
    """The line that hands out the task `task`, whose folder is `folder`:
    'Task <name>: <path of its file>'."""
    return f"Task {task}: {os.path.join(folder, TASK_FILE)}"


def submit_section(command, answer):
    """The section that ends a task, how to submit its answer: the command
    `command` that takes it, and `answer`, its JSON's shape or an example, in
    a quoted here-document."""
    return (f"## Submit\n\nSubmit your answer, as JSON in a quoted here-document:\n\n```bash\n"
            f"{command} <<'END_OF_INPUT'\n{answer}\nEND_OF_INPUT\n```\n\nIf the script refuses it, fix every "
            "problem it names and submit again, until it is accepted.")
