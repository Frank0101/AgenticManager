#!/usr/bin/env python3
#
# Validates the user's AgenticManager config (~/.config/agentic-manager/config.json)
# against config-template.json, which lists every supported group and source.
# The config may only contain groups, sources and settings from the template; nothing
# can be added. It may leave some out: a missing group or source counts as disabled,
# so configs keep working when the template gains new ones. The user may only switch
# "enabled" between true and false and fill in settings; an enabled source must have
# every setting filled in, with a value of the same type as in the template.
#
# Usage: check_config.py [--init] [group ...]
#   group   the groups the calling skill needs (e.g. workflow source_control). Each one
#           must have at least one enabled source; if not, the error explains how to
#           set one up. With no groups, all are returned and none is required.
#   --init  copies the template to the config path first, if no config exists yet.
#
# Prints one line of JSON:
#   success: {"ok": true, "path": ..., "template": ..., "created": bool, "sources": {...}}
#   failure: {"ok": false, "path": ..., "template": ..., "errors": ["...", ...]}  (exit code 1)
#
# "sources" maps each returned group to its enabled sources only. A source is named
# "<tool>-<channel>" (e.g. "jira-api"); it is already split into tool, channel and
# settings, so skills never have to parse the name.
import json
import os
import re
import shutil
import sys

CONFIG_PATH = os.path.join(os.path.expanduser(
    "~"), ".config", "agentic-manager", "config.json")
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "config-template.json")

# A setting still holding its template placeholder, e.g. "<token>".
PLACEHOLDER = re.compile(r"^<.*>$")


def reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f'duplicate key "{key}"')
        seen[key] = value
    return seen


def load_json(path):
    if not os.path.isfile(path):
        raise ValueError(f"{path} not found")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=reject_duplicates)
    except ValueError as e:  # bad JSON, bad encoding or a duplicate key
        raise ValueError(f"invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"top level of {path} must be a JSON object")
    return data


def type_name(value):
    return {bool: "true or false", str: "a string", int: "a number", float: "a number",
            list: "a list", dict: "an object"}.get(type(value), type(value).__name__)


def is_filled(value):
    if isinstance(value, str):
        return bool(value.strip()) and not PLACEHOLDER.match(value)
    return value is not None


def quoted(keys):
    return ", ".join(f'"{k}"' for k in keys)


# Reports keys of a config object that the template doesn't have. Keys the template
# has but the config leaves out are allowed.
def check_unknown(where, actual, expected, kind):
    prefix = f"{where}." if where else ""
    return [f'unknown {kind} "{prefix}{k}" (supported: {", ".join(expected)})'
            for k in actual if k not in expected]


# Returns the problems with one source; empty if it is valid.
def check_source(where, settings, template_settings):
    if not isinstance(settings, dict):
        return [f"{where} must be an object"]
    errors = check_unknown(where, settings, template_settings, "setting")
    if "enabled" not in settings:
        errors.append(f'{where}.enabled is missing: set it to true or false')
    enabled = settings.get("enabled")
    for key, default in template_settings.items():
        value = settings.get(key)
        if key in settings and type(value) is not type(default):  # "is": true is not a number
            errors.append(f"{where}.{key} must be {type_name(default)}")
        elif key != "enabled" and enabled is True and not is_filled(value):
            errors.append(f'{where}.{key} is not filled in: fill it in, or disable "{where}"')
    return errors


# Returns (sources, errors): the enabled sources per group, and every problem found.
# Groups and sources missing from the config count as disabled.
def resolve_config(config, template):
    errors = check_unknown("", config, template, "group")
    sources = {}
    for group, template_sources in template.items():
        sources[group] = []
        entries = config.get(group, {})
        if not isinstance(entries, dict):
            errors.append(f"{group} must be an object of sources")
            continue
        errors += check_unknown(group, entries, template_sources, "source")
        for name, settings in entries.items():
            if name not in template_sources:
                continue  # already reported as unknown
            problems = check_source(
                f"{group}.{name}", settings, template_sources[name])
            if problems:
                errors.extend(problems)
            elif settings["enabled"]:
                # "notion-mcp" -> "notion", "mcp"
                tool, _, channel = name.rpartition("-")
                extra = {k: v for k, v in settings.items() if k != "enabled"}
                sources[group].append(
                    {"source": name, "tool": tool, "channel": channel, "settings": extra})
    return sources, errors


# Explains how to set up one source of a group, starting from the user's config.
def setup_steps(group, name, template_settings, config):
    entry = dict(template_settings, enabled=True)
    settings = [k for k in template_settings if k != "enabled"]
    if group not in config:
        step = f'add "{group}": {json.dumps({name: entry})} at the top level'
    elif name not in config[group]:
        step = f'add "{name}": {json.dumps(entry)} inside "{group}"'
    else:
        step = f'set "{group}.{name}.enabled" to true'
        settings = [k for k in settings if not is_filled(config[group][name].get(k))]
    if settings:
        step += f", then fill in {quoted(settings)}"
    tool, _, channel = name.rpartition("-")
    return f'"{name}" ({tool} via {channel.upper()}): {step}'


# Returns (sources limited to the requested groups, errors). With no groups, returns all.
def select_groups(sources, requested, config, template):
    errors = [f'unknown group "{g}" requested (supported: {", ".join(template)})'
              for g in requested if g not in template]
    if errors:
        return {}, errors
    for group in requested:
        if not sources[group]:
            options = "; or ".join(setup_steps(group, name, settings, config)
                                   for name, settings in template[group].items())
            errors.append(f'no enabled source for "{group}". To use {options}. '
                          f"Edit {CONFIG_PATH}.")
    return {g: sources[g] for g in (requested or template)}, errors


def main():
    args = sys.argv[1:]
    init = "--init" in args
    # dedupe, keep order
    requested = list(dict.fromkeys(a for a in args if a != "--init"))
    result = {"path": CONFIG_PATH, "template": TEMPLATE_PATH}
    created = False
    try:
        template = load_json(TEMPLATE_PATH)
        if init and not os.path.exists(CONFIG_PATH):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            shutil.copyfile(TEMPLATE_PATH, CONFIG_PATH)
            created = True
        config = load_json(CONFIG_PATH)
        sources, errors = resolve_config(config, template)
        if not errors:
            sources, errors = select_groups(sources, requested, config, template)
    except (ValueError, OSError) as e:
        errors = [str(e)]
    if errors:
        print(json.dumps({"ok": False, **result,
              "created": created, "errors": errors}))
        sys.exit(1)
    print(json.dumps({"ok": True, **result,
          "created": created, "sources": sources}))


if __name__ == "__main__":
    main()
