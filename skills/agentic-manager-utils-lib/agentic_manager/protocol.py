"""Fills a skill's protocol: the prose instructions a task hands to an agent, kept as Markdown files in a folder of the skill.

A {{name}} in a file is filled with a value the skill's scripts own, such as
the values a field accepts, or with a shared part, the file _name.md beside
it, so a rule several tasks follow is written once. A value given wins over a
part of the same name. A placeholder nothing fills stops the script, so an
agent is never handed one.
"""
import os
import re

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def fill(folder, name, values=None):
    """The protocol file `name`.md of `folder`, each {{key}} filled from
    `values`, or else from the shared part _key.md of the same folder, whose
    own placeholders are filled the same way; exits on one nothing fills."""
    values = values or {}

    def one(match):
        key = match[1]
        if key in values:
            return str(values[key])
        if os.path.isfile(part := os.path.join(folder, f"_{key}.md")):
            return PLACEHOLDER.sub(one, read(part).strip())
        raise SystemExit(
            f"protocol/{name}.md names {{{{{key}}}}}, which nothing fills")
    return PLACEHOLDER.sub(one, read(os.path.join(folder, f"{name}.md"))).strip()


def read(path):
    """The text of the file `path`."""
    with open(path, encoding="utf-8") as f:
        return f.read()
