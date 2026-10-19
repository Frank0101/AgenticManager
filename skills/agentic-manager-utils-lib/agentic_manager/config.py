"""The user's AgenticManager config (~/.config/agentic-manager/config.json):
where it lives, how it's loaded and when a setting counts as filled in.

check_config.py validates the whole config with these rules,
but never returns setting values, which can be secrets such as tokens. A script
that needs a source's settings reads them with read_source(), so the values
never reach the agent or the chat. The folder a skill writes its files to is in
output_folder.py.
"""
import json
import os
import re
from typing import TypeGuard

CONFIG_PATH = os.path.join(os.path.expanduser(
    "~"), ".config", "agentic-manager", "config.json")

# A setting still holding its template placeholder, e.g. "<token>".
PLACEHOLDER = re.compile(r"^<.*>$")

FIX = "Run agentic_manager/check_config.py to see how to fix it."


def read_source(group, source, keys, lists=()):
    """The given settings of one source, for a script that needs them itself:
    `keys` are text settings, which must be filled in, and `lists` lists of
    text, which may be left out and then are empty. Exits with a message that
    names what's wrong, never a value."""
    where = f"sources.{group}.{source}"
    if not is_enabled(group, source):
        raise SystemExit(f"{where} is not enabled in {CONFIG_PATH}. {FIX}")
    settings = load_config()["sources"][group][source]
    missing = [k for k in keys if not is_filled(settings.get(k))]
    if missing:
        raise SystemExit(
            f"{where} setting(s) not filled in: {', '.join(missing)}. {FIX}")
    wrong = [k for k in lists if not is_text_list(settings.get(k, []))]
    if wrong:
        raise SystemExit(
            f"{where} setting(s) not a list of strings: {', '.join(wrong)}. {FIX}")
    return {**{k: settings[k].strip() for k in keys},
            **{k: [v.strip() for v in settings.get(k, [])] for k in lists}}


def is_enabled(group, source):
    """Whether a source is enabled in the user's config, for a script that
    uses a source's tool, such as a CLI, only when the user enabled it. Exits
    if the config can't be read."""
    return source in enabled_sources(group)


def enabled_sources(group):
    """The names of a group's enabled sources in the user's config, such as
    ["github-cli"], for a script that picks which to use. Exits if the config
    can't be read."""
    groups = load_config().get("sources")
    entries = groups.get(group) if isinstance(groups, dict) else None
    return [name for name, settings in (entries.items() if isinstance(entries, dict) else ())
            if isinstance(settings, dict) and settings.get("enabled") is True]


def load_config():
    """The user's config, for a script. Exits if it can't be read."""
    try:
        return load_json(CONFIG_PATH)
    except (ValueError, OSError):
        raise SystemExit(f"could not read {CONFIG_PATH}. {FIX}")


def load_json(path):
    """Loads a JSON object, rejecting duplicate keys. Raises ValueError with a
    message for the user, or OSError if the file can't be opened."""
    if not os.path.exists(path):
        raise ValueError(f"{path} not found")
    if not os.path.isfile(path):
        raise ValueError(f"{path} is not a file")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=_reject_duplicates)
    except ValueError as e:  # bad JSON, bad encoding or a duplicate key
        raise ValueError(f"invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"top level of {path} must be a JSON object")
    return data


def _reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f'duplicate key "{key}"')
        seen[key] = value
    return seen


def is_filled(value) -> TypeGuard[str]:
    """Whether `value` is a string holding a value, not a blank or a
    placeholder."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    return bool(value) and not PLACEHOLDER.match(value)


def is_text_list(value) -> TypeGuard[list[str]]:
    """Whether `value` is a list of strings, as a list setting must be; an
    empty list is one."""
    return isinstance(value, list) and all(isinstance(v, str) for v in value)
