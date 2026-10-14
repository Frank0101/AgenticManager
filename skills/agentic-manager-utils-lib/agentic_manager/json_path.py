"""Reads a value at a path in nested JSON, such as a tool's result, shared by every skill.

Tools nest what a skill needs several levels deep, with optional steps that may
be missing or null, so one helper walks the path and falls back to a default
instead of each caller chaining lookups and checks. A step into a list is its
position, as a number or digits, so a path read from text, such as
fields.fixVersions.0.name, works as it is.
"""


def nested(node, path, default=None):
    """The value at `path` in nested JSON objects and lists, or `default` if
    any step is missing or null. A step into a list is its position, as a
    number or digits; `node` itself may be None."""
    for step in path:
        if isinstance(node, dict):
            node = node.get(step)
        elif isinstance(node, list) and str(step).isdigit() and int(step) < len(node):
            node = node[int(step)]
        else:
            return default
    return node if node is not None else default
