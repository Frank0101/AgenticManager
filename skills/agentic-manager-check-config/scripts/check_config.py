#!/usr/bin/env python3
#
# Validates the user's AgenticManager config (~/.config/agentic-manager/config.json)
# against config-template.json, which lists every supported group and source.
# Prints one line of JSON:
#   success: {"ok": true, "path": ..., "template": ..., "created": bool, "sources": {...}}
#   failure: {"ok": false, "path": ..., "template": ..., "error": "..."}   (exit code 1)
#
# --init copies the template to the config path first, if no config exists yet.
#
# "sources" maps each group to its enabled sources only. A source is named
# "<tool>-<channel>" (e.g. "notion-mcp"); it is already split into tool, channel and
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


def load_json(path):
    if not os.path.isfile(path):
        raise ValueError(f"{path} not found")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:  # bad JSON or bad encoding
        raise ValueError(f"invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"top level of {path} must be a JSON object")
    return data


def names(keys):
    return ", ".join(keys)


# Returns the list of problems with one source; empty if it is valid.
def check_source(where, settings, template_settings):
    if not isinstance(settings, dict):
        return [f'{where} must be an object, e.g. {{"enabled": false}}']
    errors = []
    enabled = settings.get("enabled")
    if not isinstance(enabled, bool):
        errors.append(f'{where}: "enabled" must be true or false')
    for key in settings:
        if key not in template_settings:
            errors.append(
                f'{where}: unknown setting "{key}" (supported: {names(template_settings)})')
    if enabled is True:
        for key, default in template_settings.items():
            if key == "enabled":
                continue
            value = settings.get(key, default)
            if isinstance(value, str) and PLACEHOLDER.match(value):
                errors.append(f'{where}: fill in "{key}"')
    return errors


# Returns the enabled sources per group. Raises ValueError listing every problem found.
# Groups and sources missing from the config count as disabled.
def resolve_config(config, template):
    errors = []
    for group in config:
        if group not in template:
            errors.append(
                f'unknown group "{group}" (supported: {names(template)})')

    sources = {}
    for group, template_sources in template.items():
        sources[group] = []
        entries = config.get(group, {})
        if not isinstance(entries, dict):
            errors.append(f"{group} must be an object of sources")
            continue
        for name, settings in entries.items():
            where = f"{group}.{name}"
            if name not in template_sources:
                errors.append(
                    f'{where} is not supported (supported in {group}: {names(template_sources)})')
                continue
            problems = check_source(where, settings, template_sources[name])
            if problems:
                errors.extend(problems)
            elif settings["enabled"]:
                # "notion-mcp" -> "notion", "mcp"
                tool, _, channel = name.rpartition("-")
                extra = {k: v for k, v in settings.items() if k != "enabled"}
                sources[group].append(
                    {"tool": tool, "channel": channel, "settings": extra})

    if errors:
        raise ValueError("invalid configuration: " + "; ".join(errors))
    return sources


def main():
    result = {"path": CONFIG_PATH, "template": TEMPLATE_PATH}
    try:
        template = load_json(TEMPLATE_PATH)
        created = False
        if "--init" in sys.argv[1:] and not os.path.exists(CONFIG_PATH):
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            shutil.copyfile(TEMPLATE_PATH, CONFIG_PATH)
            created = True
        sources = resolve_config(load_json(CONFIG_PATH), template)
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, **result, "error": str(e)}))
        sys.exit(1)
    print(json.dumps({"ok": True, **result,
          "created": created, "sources": sources}))


if __name__ == "__main__":
    main()
