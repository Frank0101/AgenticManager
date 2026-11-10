#!/usr/bin/env python3
"""Validates the user's AgenticManager config (~/.config/agentic-manager/config.json)
against config-template.json, which lists every supported key.

The config may hold only what the template lists, but may leave things out, so
configs keep working when the template gains new ones. It is only ever written
by --init, never overwritten; "next_steps" tells the agent what to do about it,
so no skill repeats it. Every source comes by group, enabled or not, and every
company setting, set or not, so the calling skill decides what it needs, never
with a setting's value: those can be secrets, which a script reads itself.
"""

import json
import os
import shutil
import sys

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.config import CONFIG_PATH, has_filled_entry, is_filled, is_text_list, load_json, tool_channel  # noqa: E402

TEMPLATE_PATH = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "config-template.json")

HELP = """Validates the user's AgenticManager config against its template.

Usage: check_config.py [--init]
  --init  copies the template to the config path first, if no config exists yet.
  --help  prints this.

Prints one line of JSON:
  success: {"ok": true, "path": ..., "template": ..., "created": bool,
            "sources": {group: {source: {"tool", "channel", "enabled",
                                         "setup" when disabled}}},
            "company": {setting: {"set", "setup" when not set}}},
           plus "next_steps" if the config was just created
  failure: {"ok": false, "path": ..., "template": ..., "created": bool,
            "errors": ["...", ...], "next_steps": "..."}
           (exit code 1)"""

# What the user does to the config once it exists.
EDIT = ("edit the config at `path`: enable the sources they use, fill in their "
        "settings, and optionally set output.root and the company settings")
CREATE = ("The config doesn't exist. Ask the user whether to create it from the "
          "template. Only if they explicitly agree, run this script again with "
          "--init, then tell them to " + EDIT + ".")
CREATED = ("The config was created from the template, with every source disabled. "
           "Tell the user to " + EDIT + ".")
FIX_STEPS = ("Show the user every error and the config's `path`, and explain how to fix "
             "each one. Never edit the config yourself.")


def check_config(config, template):
    """Every problem with the config; empty if it is valid."""
    return (_check_unknown("", config, template, "key")
            + _check_sources(config.get("sources", {}), template["sources"])
            + [error for name in template if name != "sources"
               for error in _check_settings(name, config.get(name, {}), template[name])])


# Reports keys of a config object that the template doesn't have. Keys the template
# has but the config leaves out are allowed.
def _check_unknown(where, actual, expected, kind):
    prefix = f"{where}." if where else ""
    return [f'unknown {kind} "{prefix}{k}" (supported: {", ".join(expected)})'
            for k in actual if k not in expected]


# Returns the problems with the "sources" object. Groups and sources missing from
# it count as disabled.
def _check_sources(groups, template_groups):
    if not isinstance(groups, dict):
        return ["sources must be an object of groups"]
    errors = _check_unknown("sources", groups, template_groups, "group")
    for group, template_sources in template_groups.items():
        where = f"sources.{group}"
        entries = groups.get(group, {})
        if not isinstance(entries, dict):
            errors.append(f"{where} must be an object of sources")
            continue
        errors += _check_unknown(where, entries, template_sources, "source")
        for name, settings in entries.items():
            if name in template_sources:  # unknown ones are already reported
                errors += _check_source(f"{where}.{name}",
                                        settings, template_sources[name])
    return errors


# Returns the problems with one source; empty if it is valid. Each setting has
# the template's type; an enabled source must fill in every text setting, while
# a list setting, which the template holds as an empty list, is optional.
def _check_source(where, settings, template_settings):
    if not isinstance(settings, dict):
        return [f"{where} must be an object"]
    errors = _check_unknown(where, settings, template_settings, "setting")
    if "enabled" not in settings:
        errors.append(f'{where}.enabled is missing: set it to true or false')
    enabled = settings.get("enabled")
    for key, default in template_settings.items():
        value = settings.get(key)
        if key in settings and (type(value) is not type(default)
                                or isinstance(default, list) and not is_text_list(value)):
            errors.append(f"{where}.{key} must be {_type_name(default)}")
        elif isinstance(default, str) and enabled is True and not is_filled(value):
            errors.append(
                f'{where}.{key} is not filled in: fill it in, or disable "{where}"')
    return errors


# The template only holds "enabled" (true or false), string placeholders and
# empty lists.
def _type_name(value):
    return {bool: "true or false", str: "a string", list: "a list of strings"}[type(value)]


# Returns the problems with a top-level object of settings that aren't sources,
# such as "output" or "company". Each setting is optional: left out, blank or
# still a placeholder, it counts as not set. A text setting must be text; a list
# setting, such as the company's review ratings, a list of entries with the
# fields of the template's one entry. Once one entry is filled in, every entry
# fills in every field, and no two share their first one.
def _check_settings(name, section, template_section):
    if not isinstance(section, dict):
        return [f"{name} must be an object of settings"]
    errors = _check_unknown(name, section, template_section, "setting")
    for key, default in template_section.items():
        if key not in section:
            continue
        if isinstance(default, list):
            errors += _check_entries(f"{name}.{key}",
                                     section[key], list(default[0]))
        elif type(section[key]) is not type(default):
            errors.append(f"{name}.{key} must be {_type_name(default)}")
    return errors


def _check_entries(where, entries, fields):
    if not (isinstance(entries, list) and all(
            isinstance(entry, dict) and sorted(entry) == sorted(fields)
            and all(isinstance(entry[field], str) for field in fields) for entry in entries)):
        shape = ", ".join(f'"{field}": "..."' for field in fields)
        return [f"{where} must be a list of {{{shape}}}"]
    if not has_filled_entry(entries):
        return []
    errors = [f"{where}, entry {number}: {field} is not filled in: fill it in, or remove the entry"
              for number, entry in enumerate(entries, 1) for field in fields if not is_filled(entry[field])]
    firsts = [entry[fields[0]].strip() for entry in entries]
    errors += [f'{where} lists "{first}" more than once: list each once'
               for first in sorted(set(firsts)) if is_filled(first) and firsts.count(first) > 1]
    return errors


# Every source of the template by group, from a valid config: its tool, channel,
# whether it is enabled and, if not, how to enable it.
def _list_sources(config, template):
    sources = {}
    for group, template_sources in template["sources"].items():
        sources[group] = {}
        for name, template_settings in template_sources.items():
            settings = config.get("sources", {}).get(group, {}).get(name, {})
            tool, channel = tool_channel(name)
            entry = {"tool": tool, "channel": channel,
                     "enabled": settings.get("enabled") is True}
            if not entry["enabled"]:
                entry["setup"] = _setup_steps(
                    group, name, template_settings, config)
            sources[group][name] = entry
    return sources


# Explains how to enable one source, starting from the user's config, which must
# be valid. Names the settings to fill in, never their values.
def _setup_steps(group, name, template_settings, config):
    entry = dict(template_settings, enabled=True)
    settings = [k for k, v in template_settings.items() if isinstance(v, str)]
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
        step += f", then fill in {_quoted(settings)}"
    return step


def _quoted(keys):
    return ", ".join(f'"{k}"' for k in keys)


# Every company setting of the template, from a valid config: whether it is set
# and, if not, how to set it. Names the setting, never its entries.
def _list_company(config, template):
    company = config.get("company", {})
    listed = {}
    for key, template_entries in template["company"].items():
        if has_filled_entry(company.get(key, [])):
            listed[key] = {"set": True}
            continue
        shape = json.dumps(template_entries)
        if "company" not in config:
            step = f'add "{key}": {shape} inside "company", an object you add at the top level'
        elif key not in company:
            step = f'add "{key}": {shape} inside "company"'
        else:
            step = f'fill in "company.{key}"'
        listed[key] = {"set": False,
                       "setup": f"{step}, with an entry for each {list(template_entries[0])[0]}"}
    return listed


def main():
    args = sys.argv[1:]
    if args in (["-h"], ["--help"]):
        print(HELP)
        return
    init = "--init" in args
    result = {"path": CONFIG_PATH, "template": TEMPLATE_PATH}
    created, sources, company = False, {}, {}
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
                sources = _list_sources(config, template)
                company = _list_company(config, template)
        except (ValueError, OSError) as e:
            errors = [str(e)]
    if errors:
        missing = not os.path.lexists(CONFIG_PATH)
        print(json.dumps({"ok": False, **result, "created": created,
                          "errors": errors, "next_steps": CREATE if missing else FIX_STEPS}))
        sys.exit(1)
    result = {"ok": True, **result, "created": created,
              "sources": sources, "company": company}
    if created:
        result["next_steps"] = CREATED
    print(json.dumps(result))


if __name__ == "__main__":
    main()
