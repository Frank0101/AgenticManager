"""The user's AgenticManager config (~/.config/agentic-manager/config.json):
where it lives, how it's loaded and when a setting counts as filled in.

check_config.py validates the whole config with these rules, but never returns
setting values, which can be secrets such as tokens. A script that needs a
source's settings reads them with read_source(), so the values never reach the
agent or the chat. A company setting, such as the company values, holds no
secrets, so a skill may show what company_setting() reads. The folder a skill
writes its files to is in output_folder.py.
"""
import json
import os
import re
from typing import TypeGuard

CONFIG_PATH = os.path.join(os.path.expanduser(
    "~"), ".config", "agentic-manager", "config.json")

# A setting still holding its template placeholder, e.g. "<token>".
PLACEHOLDER = re.compile(r"^<.*>$")


def read_source(group, source, keys, lists=()):
    """The given settings of one source, trimmed, for a script that needs them
    itself: `keys` are text settings and `lists` lists of text, which may be
    left out and then are empty. Their shape is the config check's to enforce,
    which every skill's prerequisite runs. Exits if the source isn't
    enabled."""
    if not is_enabled(group, source):
        raise SystemExit(
            f"sources.{group}.{source} is not enabled in {CONFIG_PATH}. {_fix(source)}")
    settings = load_config()["sources"][group][source]
    return {**{k: settings[k].strip() for k in keys},
            **{k: [v.strip() for v in settings.get(k, [])] for k in lists}}


def _fix(need=None):
    """The hint for a problem with the config, by the check that names how to
    fix it; with a missing `need`, how to meet that one."""
    return f"Run agentic_manager/check_config.py{f' --needs {need}' if need else ''} to see how to fix it."


def company_setting(key):
    """The entries of the company setting `key`, such as values,
    each field trimmed, in the config's order, for a script that needs them.
    Exits, naming the setting, when it isn't set."""
    entries = load_config().get("company", {}).get(key, [])
    if not has_filled_entry(entries):
        raise SystemExit(
            f"company.{key} is not set in {CONFIG_PATH}. {_fix(f'company.{key}')}")
    return [{field: value.strip() for field, value in entry.items()} for entry in entries]


def is_enabled(group, source):
    """Whether a source is enabled in the user's config, for a script that
    uses a source's tool, such as a CLI, only when the user enabled it. Exits
    if the config can't be read."""
    return source in enabled_sources(group)


def enabled_sources(group):
    """The names of a group's enabled sources in the user's config, such as
    ["github-cli"], for a script that picks which to use. Exits if the config
    can't be read."""
    entries = load_config().get("sources", {}).get(group, {})
    return [name for name, settings in entries.items() if settings.get("enabled") is True]


def tool_channel(name):
    """(tool, channel) of a source named "<tool>-<channel>", such as
    ("notion", "mcp") for "notion-mcp": the one place a source's name is
    split."""
    tool, _, channel = name.rpartition("-")
    return tool, channel


def load_config():
    """The user's config, for a script. Exits if it can't be read."""
    try:
        return load_json(CONFIG_PATH)
    except (ValueError, OSError):
        raise SystemExit(f"could not read {CONFIG_PATH}. {_fix()}")


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


def has_filled_entry(entries):
    """Whether a list setting of entries, such as company.values, holds a
    value: one field of one entry is filled in. A list with none counts as
    not set."""
    return any(is_filled(value) for entry in entries if isinstance(entry, dict) for value in entry.values())


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
