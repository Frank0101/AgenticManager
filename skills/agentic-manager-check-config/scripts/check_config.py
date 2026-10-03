#!/usr/bin/env python3
#
# Validates the user's AgenticManager config (~/.config/agentic-manager/config.json)
# against config-template.json, which lists every supported group and source.
# The config must have exactly the template's shape: the same groups, sources and
# settings, nothing missing or added. The user may only switch "enabled" between
# true and false and fill in settings; an enabled source must have every setting
# filled in, with a value of the same type as in the template.
#
# Usage: check_config.py [--init] [group ...]
#   group   the groups the calling skill needs (e.g. workflow source_control). Each one
#           must have at least one enabled source. With no groups, all are returned
#           and none is required.
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


# Compares the keys of a config object with the template's. Returns the problems found.
def check_keys(where, actual, expected, kind):
    prefix = f"{where}." if where else ""
    missing = [f'missing {kind} "{prefix}{k}"' for k in expected if k not in actual]
    unknown = [f'unknown {kind} "{prefix}{k}" (supported: {", ".join(expected)})'
               for k in actual if k not in expected]
    return missing + unknown


# Returns the problems with one source; empty if it is valid.
def check_source(where, settings, template_settings):
    if not isinstance(settings, dict):
        return [f"{where} must be an object"]
    errors = check_keys(where, settings, template_settings, "setting")
    enabled = settings.get("enabled")
    if not isinstance(enabled, bool):
        errors.append(f'{where}: "enabled" must be true or false')
    for key in settings:
        if key not in template_settings:
            errors.append(
                f'{where}: unknown setting "{key}" (supported: {names(template_settings)})')
    for key, default in template_settings.items():
        if key not in settings:
            continue
        value = settings[key]
        if type(value) is not type(default):  # "is", so true is not accepted as a number
            errors.append(f"{where}.{key} must be {type_name(default)}")
        elif key != "enabled" and enabled is True:
            if isinstance(value, str):
                if not value.strip() or PLACEHOLDER.match(value):
                    errors.append(f'{where}.{key} is not filled in: fill it in, or disable "{where}"')
    if enabled is True:
        for key, default in template_settings.items():
            if key == "enabled":
                continue
            value = settings.get(key, default)
            if isinstance(value, str) and PLACEHOLDER.match(value):
                errors.append(f'{where}: fill in "{key}"')
    return errors


# Returns (sources, errors): the enabled sources per group, and every problem found.
def resolve_config(config, template):
    errors = check_keys("", config, template, "group")
    sources = {}
    for group, template_sources in template.items():
        sources[group] = []
        entries = config.get(group)
        if entries is None:
            continue  # already reported as missing
        if not isinstance(entries, dict):
            errors.append(f"{group} must be an object of sources")
            continue
        errors += check_keys(group, entries, template_sources, "source")
        for name, settings in entries.items():
            where = f"{group}.{name}"
            if name not in template_sources:
                errors.append(
                    f'{where} is not supported (supported in {group}: {names(template_sources)})')
                continue
            where = f"{group}.{name}"
            problems = check_source(where, entries[name], template_settings)
            if problems:
                errors.extend(problems)
            elif settings["enabled"]:
                # "notion-mcp" -> "notion", "mcp"
                tool, _, channel = name.rpartition("-")
                extra = {k: v for k, v in settings.items() if k != "enabled"}
                sources[group].append(
                    {"source": name, "tool": tool, "channel": channel, "settings": extra})


# Returns (sources limited to the requested groups, errors). With no groups, returns all.
def select_groups(sources, requested, template):
    errors = [f'unknown group "{g}" requested (supported: {", ".join(template)})'
              for g in requested if g not in template]
    if errors:
        return {}, errors
    for group in requested:
        if not sources[group]:
            options = ", ".join(f'"{group}.{name}"' for name in template[group])
            errors.append(f'no enabled source for "{group}": enable {options} in {CONFIG_PATH}')
    return {g: sources[g] for g in (requested or template)}, errors


def main():
    args = sys.argv[1:]
    init = "--init" in args
    requested = list(dict.fromkeys(a for a in args if a != "--init"))  # dedupe, keep order
    result = {"path": CONFIG_PATH, "template": TEMPLATE_PATH}
    created = False
    try:
        template = load_json(TEMPLATE_PATH)
        if init and not os.path.exists(CONFIG_PATH):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            shutil.copyfile(TEMPLATE_PATH, CONFIG_PATH)
            created = True
        sources, errors = resolve_config(load_json(CONFIG_PATH), template)
        if not errors:
            sources, errors = select_groups(sources, requested, template)
    except (ValueError, OSError) as e:
        errors = [str(e)]
    if errors:
        print(json.dumps({"ok": False, **result, "created": created, "errors": errors}))
        sys.exit(1)
    print(json.dumps({"ok": True, **result,
          "created": created, "sources": sources}))


if __name__ == "__main__":
    main()
