#!/usr/bin/env python3
#
# Validates agentic-manager.json (in the git root, else the current directory) and
# prints one line of JSON:
#   success: {"ok": true, "path": ..., "sources": {...}, "warnings": [...]}
#   failure: {"ok": false, "path": ..., "error": "..."}   (exit code 1)
#
# "sources" maps each group to its enabled sources only. A source is named
# "<tool>-<channel>" (e.g. "notion-mcp"); it is already split into tool, channel and
# settings, so skills never have to parse the name.
import json
import os
import subprocess
import sys

FILE_NAME = "agentic-manager.json"

# Areas that can be configured; each group is an object of sources.
GROUPS = ("documentation", "source_control", "workflow", "messaging")

# The channel (the suffix of a source name) says how skills talk to the tool.
CHANNELS = ("mcp", "cli", "api")


def find_root():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.getcwd()


def load_config(path):
    if not os.path.isfile(path):
        raise ValueError(f"{FILE_NAME} not found")
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except ValueError as e:  # bad JSON or bad encoding
        raise ValueError(f"invalid JSON: {e}")
    if not isinstance(config, dict):
        raise ValueError("top level must be a JSON object, e.g. {}")
    return config


# Returns the resolved source, or None if it is disabled. Raises ValueError if invalid.
def resolve_source(name, settings):
    tool, _, channel = name.rpartition("-")  # "notion-mcp" -> "notion", "mcp"
    if not tool or channel not in CHANNELS:
        suffixes = " / ".join(f"-{c}" for c in CHANNELS)
        raise ValueError(f'name must end with {suffixes} (e.g. "notion-mcp")')
    enabled = settings.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError('missing required boolean key "enabled"')
    if enabled:
        extra = {k: v for k, v in settings.items() if k != "enabled"}
        return {"tool": tool, "channel": channel, "settings": extra}


# Returns (sources, warnings). Raises ValueError listing every problem found.
def resolve_config(config):
    sources, errors = {}, []

    # Unknown keys only warn, so a newer config doesn't break older skills.
    warnings = [f'unknown key "{key}" (known groups: {", ".join(GROUPS)})'
                for key in config if key not in GROUPS]

    for group in GROUPS:
        if group not in config:
            continue  # every group is optional
        entries = config[group]
        if not isinstance(entries, dict) or not all(isinstance(e, dict) for e in entries.values()):
            errors.append(
                f'{group} must be an object of sources, e.g. {{"notion-mcp": {{"enabled": true}}}}')
            continue
        sources[group] = []
        for name, settings in entries.items():
            try:
                entry = resolve_source(name, settings)
            except ValueError as e:
                errors.append(f"{group}.{name}: {e}")
                continue
            if entry:
                sources[group].append(entry)

    if errors:
        raise ValueError("invalid configuration: " + "; ".join(errors))
    return sources, warnings


def main():
    path = os.path.join(find_root(), FILE_NAME)
    try:
        sources, warnings = resolve_config(load_config(path))
    except ValueError as e:
        print(json.dumps({"ok": False, "path": path, "error": str(e)}))
        sys.exit(1)
    print(json.dumps({"ok": True, "path": path,
          "sources": sources, "warnings": warnings}))


if __name__ == "__main__":
    main()
