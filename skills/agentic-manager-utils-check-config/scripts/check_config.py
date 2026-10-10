#!/usr/bin/env python3
"""Validates the user's AgenticManager config (~/.config/agentic-manager/config.json)
against config-template.json, which lists every supported key. Its "sources" object
holds every supported group and source; its "output" object, the settings for where
skills write files. The config may only contain keys, groups, sources and settings
from the template; nothing can be added. It may leave some out: a missing group or
source counts as disabled, and a missing output setting as not set, so configs keep
working when the template gains new ones. The user may only switch "enabled" between
true and false and fill in settings. Every value must have the same type as in the
template, and an enabled source must have every setting filled in. Output settings
are optional.

Usage: check_config.py [--init]
  --init  copies the template to the config path first, if no config exists yet.

Prints one line of JSON:
  success: {"ok": true, "path": ..., "template": ..., "created": bool, "sources": {...}}
  failure: {"ok": false, "path": ..., "template": ..., "created": bool,
            "errors": ["...", ...]}
           (exit code 1)

The config is only ever written by --init, and never overwritten.

"sources" lists every source of the template by group, enabled or not, so the
calling skill decides what it needs. A source is named "<tool>-<channel>" (e.g.
"jira-api"); it is already split into tool and channel, so skills never have to
parse the name. A disabled source has "setup": how to enable it. Setting values
are never returned: they can hold secrets, which a script reads from the config
itself.
"""

import json
import os
import shutil
import sys

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))), "config-template.json")
# The agentic-manager-utils-lib skill, installed next to this one.
LIB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "..", "..", "agentic-manager-utils-lib")
sys.path.insert(0, LIB_DIR)
try:
    from agentic_manager.config import CONFIG_PATH, is_filled, load_json
except ImportError:
    print(json.dumps({"ok": False, "path": None, "template": TEMPLATE_PATH, "created": False,
                      "errors": ["agentic-manager-utils-lib is not installed next to this skill. "
                                 "Reinstall AgenticManager with --skill '*' to install every skill."]}))
    sys.exit(1)


# The template only holds "enabled" (true or false) and string placeholders.
def type_name(value):
    return {bool: "true or false", str: "a string"}[type(value)]


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
        if key in settings and type(value) is not type(default):
            errors.append(f"{where}.{key} must be {type_name(default)}")
        elif key != "enabled" and enabled is True and not is_filled(value):
            errors.append(
                f'{where}.{key} is not filled in: fill it in, or disable "{where}"')
    return errors


# Returns every problem with the config; empty if it is valid.
def check_config(config, template):
    return (check_unknown("", config, template, "key")
            + check_sources(config.get("sources", {}), template["sources"])
            + check_output(config.get("output", {}), template["output"]))


# Returns the problems with the "sources" object. Groups and sources missing from
# it count as disabled.
def check_sources(groups, template_groups):
    if not isinstance(groups, dict):
        return ["sources must be an object of groups"]
    errors = check_unknown("sources", groups, template_groups, "group")
    for group, template_sources in template_groups.items():
        where = f"sources.{group}"
        entries = groups.get(group, {})
        if not isinstance(entries, dict):
            errors.append(f"{where} must be an object of sources")
            continue
        errors += check_unknown(where, entries, template_sources, "source")
        for name, settings in entries.items():
            if name in template_sources:  # unknown ones are already reported
                errors += check_source(f"{where}.{name}",
                                       settings, template_sources[name])
    return errors


# Returns the problems with the "output" object. Its settings are optional: one left
# out, blank or still a placeholder counts as not set.
def check_output(output, template_output):
    if not isinstance(output, dict):
        return ["output must be an object of settings"]
    errors = check_unknown("output", output, template_output, "setting")
    for key, default in template_output.items():
        if key in output and type(output[key]) is not type(default):
            errors.append(f"output.{key} must be {type_name(default)}")
    return errors


# Explains how to enable one source, starting from the user's config, which must
# be valid. Names the settings to fill in, never their values.
def setup_steps(group, name, template_settings, config):
    entry = dict(template_settings, enabled=True)
    settings = [k for k in template_settings if k != "enabled"]
    groups = config.get("sources", {})
    if "sources" not in config:
        step = f'add "sources": {json.dumps({group: {name: entry}})} at the top level'
    elif group not in groups:
        step = f'add "{group}": {json.dumps({name: entry})} inside "sources"'
    elif name not in groups[group]:
        step = f'add "{name}": {json.dumps(entry)} inside "sources.{group}"'
    else:
        step = f'set "sources.{group}.{name}.enabled" to true'
        settings = [k for k in settings if not is_filled(
            groups[group][name].get(k))]
    if settings:
        step += f", then fill in {quoted(settings)}"
    return step


# Every source of the template by group, from a valid config: its tool, channel,
# whether it is enabled and, if not, how to enable it.
def list_sources(config, template):
    sources = {}
    for group, template_sources in template["sources"].items():
        sources[group] = {}
        for name, template_settings in template_sources.items():
            settings = config.get("sources", {}).get(group, {}).get(name, {})
            # "notion-mcp" -> "notion", "mcp"
            tool, _, channel = name.rpartition("-")
            entry = {"tool": tool, "channel": channel,
                     "enabled": settings.get("enabled") is True}
            if not entry["enabled"]:
                entry["setup"] = setup_steps(
                    group, name, template_settings, config)
            sources[group][name] = entry
    return sources


def main():
    args = sys.argv[1:]
    init = "--init" in args
    result = {"path": CONFIG_PATH, "template": TEMPLATE_PATH}
    created, sources = False, {}
    errors = [f'unknown argument "{a}" (usage: check_config.py [--init])'
              for a in args if a != "--init"]
    if not errors:
        try:
            template = load_json(TEMPLATE_PATH)
            if init and not os.path.lexists(CONFIG_PATH):
                os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                try:
                    with open(CONFIG_PATH, "xb") as destination:
                        with open(TEMPLATE_PATH, "rb") as source:
                            shutil.copyfileobj(source, destination)
                    created = True
                except FileExistsError:
                    # Another process created it; validate without overwriting.
                    pass
            config = load_json(CONFIG_PATH)
            errors = check_config(config, template)
            if not errors:
                sources = list_sources(config, template)
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
