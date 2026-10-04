"""The user's AgenticManager config (~/.config/agentic-manager/config.json):
where it lives, how it's loaded and when a setting counts as filled in.

agentic-manager-utils-check-config validates the whole config with these rules,
but never returns setting values, which can be secrets such as tokens. A script
that needs a source's settings reads them with read_source(), and the folder
to write its files to with output_folder(), so the values never reach the agent
or the chat.
"""
import json
import os
import re
import tempfile

CONFIG_PATH = os.path.join(os.path.expanduser(
    "~"), ".config", "agentic-manager", "config.json")

# A setting still holding its template placeholder, e.g. "<token>".
PLACEHOLDER = re.compile(r"^<.*>$")

FIX = "Run agentic-manager-utils-check-config to see how to fix it."

# Where skills write their files when the config sets no output root.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "agentic-manager")


def reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f'duplicate key "{key}"')
        seen[key] = value
    return seen


def load_json(path):
    """Loads a JSON object, rejecting duplicate keys. Raises ValueError with a
    message for the user."""
    if not os.path.exists(path):
        raise ValueError(f"{path} not found")
    if not os.path.isfile(path):
        raise ValueError(f"{path} is not a file")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=reject_duplicates)
    except ValueError as e:  # bad JSON, bad encoding or a duplicate key
        raise ValueError(f"invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"top level of {path} must be a JSON object")
    return data


def is_filled(value):
    if isinstance(value, str):
        return bool(value.strip()) and not PLACEHOLDER.match(value)
    return value is not None


def load_config():
    """The user's config, for a script. Exits if it can't be read."""
    try:
        return load_json(CONFIG_PATH)
    except (ValueError, OSError):
        raise SystemExit(f"could not read {CONFIG_PATH}. {FIX}")


def read_source(group, source, keys):
    """The given settings of one source, for a script that needs them itself.
    Exits with a message that names what's wrong, never a value."""
    where = f"sources.{group}.{source}"
    config = load_config()
    groups = config.get("sources")
    entries = groups.get(group) if isinstance(groups, dict) else None
    settings = entries.get(source) if isinstance(entries, dict) else None
    if not isinstance(settings, dict) or settings.get("enabled") is not True:
        raise SystemExit(f"{where} is not enabled in {CONFIG_PATH}. {FIX}")
    missing = [k for k in keys
               if not isinstance(settings.get(k), str) or not is_filled(settings[k])]
    if missing:
        raise SystemExit(
            f"{where} setting(s) not filled in: {', '.join(missing)}. {FIX}")
    return {k: settings[k].strip() for k in keys}


def output_root():
    """The folder where skills write their files, with ~ expanded, or None if
    the config doesn't set one. Exits if the config can't be read."""
    output = load_config().get("output")
    root = output.get("root") if isinstance(output, dict) else None
    if not isinstance(root, str) or not is_filled(root):
        return None
    return os.path.expanduser(root.strip())


def output_folder(name):
    """(folder, temporary): the folder a skill writes its files to, `name` in the
    user's output root, or in TEMP_ROOT if the config doesn't set one, and
    whether it is that temporary one. Exits if the config can't be read."""
    root = output_root()
    if root:
        return os.path.join(root, name), False
    return os.path.join(TEMP_ROOT, name), True
