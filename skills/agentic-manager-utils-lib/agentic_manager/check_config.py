#!/usr/bin/env python3
"""Validates the user's AgenticManager config (~/.config/agentic-manager/config.json)
against config-template.json, which lists every supported key, and checks it
gives what the calling skill needs.

The config may hold only what the template lists, but may leave things out, so
configs keep working when the template gains new ones. It is only ever written
by --init, never overwritten. "next_steps" always tells the agent what to do,
so no skill explains the result. Needs are judged by enabled and set, never by
a setting's value: those can be secrets, which a script reads itself.
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

Usage: check_config.py [--init] [--needs NEED ...] [--sensitive]
  --init       copies the template to the config path first, if no config
               exists yet.
  --needs      what the skill needs, each one of:
                 a group, such as workflow: any enabled source of it
                 a source, such as jira-api: that source, enabled
                 a company setting, such as company.values: set
  --sensitive  the skill reads sensitive data: adds "notice", the warning the
               user must accept before the skill reads anything.
  --help       prints this.

Prints one line of JSON, always with "next_steps", what the agent does next:
  ready:   {"ok": true, "path": ..., "template": ..., "created": bool,
            "sources": {group: {source: {"tool", "channel", "enabled",
                                         "setup" when disabled}}},
            "company": {setting: {"set", "setup" when not set}},
            "notice" with --sensitive, "next_steps": ...}
  missing: {"ok": false, "path": ..., "template": ..., "created": bool,
            "missing": {need: setup}, "next_steps": ...} (exit code 1)
  invalid: {"ok": false, "path": ..., "template": ..., "created": bool,
            "errors": ["...", ...], "next_steps": ...} (exit code 1)"""

# What the user does to the config once it exists.
EDIT = ("edit the config at `path`: enable the sources they use, fill in their "
        "settings, and optionally set output.root and the company settings")
CREATE = ("The config doesn't exist. Ask the user whether to create it from the "
          "template. Only if they explicitly agree, run the same command again with "
          "--init added, then tell them to " + EDIT + ".")
CREATED = ("The config was created from the template, with every source disabled: "
           "tell the user to " + EDIT + ".")
REINSTALL = ("The skill and the library don't match: tell the user to reinstall every skill, "
             "then run the skill again.")
MISSING = ("Stop here: the config lacks what the skill needs. For each entry of `missing`, "
           "tell the user how to fix it, showing its setup and the config's `path`.")
READY = ("Go on with the skill. Its scripts read the config's settings themselves: never read "
         "the config file, or pass or show a setting a script hasn't printed for you.")
SENSITIVE = ("Before you ask the user anything else, show them `notice`, word for word, in a "
             "message of its own, and wait for their answer. Go on only on an explicit yes; on "
             "anything else, stop. Once they say yes: ")
# The warning of a skill that reads sensitive data, kept here so every such
# skill warns in the same words. No tool can tell from inside whether the AI
# running it keeps what it reads, so it is a question for the user, not a check.
NOTICE = ("This skill reads sensitive data and should only run from an AI tool with zero data "
          "retention (ZDR). Proceed?")
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
# setting, such as the company's values, a list of entries with the
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


def missing_needs(needs, sources, company):
    """What of `needs` the config doesn't give, {need: how to fix it}, from
    the sources and company settings listed for a valid config: a group with
    no source enabled, a source not enabled, a company setting not set."""
    missing = {}
    for need in needs:
        if need.startswith("company."):
            setting = company[need.removeprefix("company.")]
            if not setting["set"]:
                missing[need] = setting["setup"]
        elif need in sources:
            if not any(source["enabled"] for source in sources[need].values()):
                missing[need] = "enable one of its sources: " + "; or ".join(
                    f"{name}: {source['setup']}" for name, source in sources[need].items())
        else:
            source = next(group[need]
                          for group in sources.values() if need in group)
            if not source["enabled"]:
                missing[need] = source["setup"]
    return missing


def argument_errors(args, template):
    """Why `args`, a skill's command line for this check, aren't ones it
    takes, empty when they are: an unknown option or word, or a need the
    template has no group, source or company setting for."""
    needs = needs_of(args)
    known = {*template["sources"], *(source for group in template["sources"].values() for source in group),
             *(f"company.{key}" for key in template["company"])}
    return ([f'unknown argument "{a}" (usage: check_config.py [--init] [--needs NEED ...] [--sensitive])'
             for a in args if a not in ("--init", "--needs", "--sensitive", *needs)]
            + [f"the skill needs {need}, which the template doesn't have" for need in needs if need not in known])


def needs_of(args):
    """What a skill needs, the words of `args`, its command line, after
    --needs, up to the next option."""
    if "--needs" not in args:
        return []
    rest = args[args.index("--needs") + 1:]
    return rest[:next((i for i, word in enumerate(rest) if word.startswith("-")), len(rest))]


def main():
    args = sys.argv[1:]
    if args in (["-h"], ["--help"]):
        print(HELP)
        return
    init, sensitive = "--init" in args, "--sensitive" in args
    needs = needs_of(args)
    result = {"path": CONFIG_PATH, "template": TEMPLATE_PATH}
    created, sources, company, mismatch = False, {}, {}, []
    try:
        template = load_json(TEMPLATE_PATH)
        errors = mismatch = argument_errors(args, template)
        if not errors:
            if init and not os.path.lexists(CONFIG_PATH):
                os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                with open(CONFIG_PATH, "xb") as destination:
                    with open(TEMPLATE_PATH, "rb") as source:
                        shutil.copyfileobj(source, destination)
                created = True
            config = load_json(CONFIG_PATH)
            errors = check_config(config, template)
            if not errors:
                sources = _list_sources(config, template)
                company = _list_company(config, template)
    except (ValueError, OSError) as e:
        errors = [str(e)]
    if errors:
        steps = REINSTALL if mismatch else CREATE if not os.path.lexists(
            CONFIG_PATH) else FIX_STEPS
        print(json.dumps({"ok": False, **result, "created": created,
                          "errors": errors, "next_steps": steps}))
        sys.exit(1)
    created_steps = CREATED + " " if created else ""
    if missing := missing_needs(needs, sources, company):
        print(json.dumps({"ok": False, **result, "created": created, "missing": missing,
                          "next_steps": created_steps + MISSING}))
        sys.exit(1)
    result = {"ok": True, **result, "created": created,
              "sources": sources, "company": company}
    if sensitive:
        result["notice"] = NOTICE
    result["next_steps"] = created_steps + \
        (SENSITIVE if sensitive else "") + READY
    print(json.dumps(result))


if __name__ == "__main__":
    main()
