"""Reads the investigation's protocol: the instructions each task carries, and its worked answer.

The protocol is prose, kept as Markdown in the skill's protocol folder, one file
per task, so it reads and changes apart from the code. A {{name}} in it is filled
here: a value the scripts own, such as the coverage values a source accepts, or
a shared part, _name.md, so each rule is written once. The worked answers are
JSON files the tests submit, so an example the script would refuse can't be
printed; they are printed one record per line, which costs fewer tokens.
"""
import json
import os
import re

from common import BLOCKERS, COVERAGE, GROUPS, READ_COVERAGE, STATUSES

FOLDER = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "..", "protocol")
# After this many review rounds the user decides whether the review goes on.
REVIEW_ROUNDS = 3
# The values the protocol's files name, as the scripts define them.
VALUES = {
    "groups": ", ".join(GROUPS.values()),
    "coverage": ", ".join(COVERAGE),
    "read_coverage": " or ".join(READ_COVERAGE),
    "blockers": "; ".join(BLOCKERS),
    "statuses": "; ".join(f"{label} ({meaning})" for label, meaning in STATUSES),
}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def text(name, **values):
    """The protocol file `name`, its placeholders filled from `values`, VALUES
    and the shared parts; exits on one it can't fill."""
    def fill(match):
        key = match[1]
        if key in values:
            return str(values[key])
        if key in VALUES:
            return VALUES[key]
        if os.path.isfile(part := os.path.join(FOLDER, f"_{key}.md")):
            return read(part).strip()
        raise SystemExit(
            f"protocol/{name}.md names {{{{{key}}}}}, which nothing fills")
    return PLACEHOLDER.sub(fill, read(os.path.join(FOLDER, f"{name}.md"))).strip()


def example(name):
    """The worked answer of the task `name`, as data."""
    with open(os.path.join(FOLDER, "examples", f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def compact(data):
    """`data` as JSON with each field, and each record of a list, on a line of its own."""
    def one(value):
        return json.dumps(value, ensure_ascii=False)
    if not isinstance(data, dict):
        return one(data)
    lines = []
    for key, value in data.items():
        if isinstance(value, list) and value:
            lines += [f"  {one(key)}: ["] + \
                [f"    {one(item)}," for item in value]
            lines[-1] = lines[-1].rstrip(",")
            lines.append("  ],")
        else:
            lines.append(f"  {one(key)}: {one(value)},")
    lines[-1] = lines[-1].rstrip(",")
    return "\n".join(["{", *lines, "}"])


def read(path):
    """The text of the file `path`."""
    with open(path, encoding="utf-8") as f:
        return f.read()
