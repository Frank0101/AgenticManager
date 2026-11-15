"""How a skill's scripts talk to the agent: the commands they name for it to run next, and the JSON it sends them on stdin.

A command a script names is built from the path the agent ran the skill's
script by, not the file's real one: the skill pre-approves its scripts by
that path, which can be a symlink to the installed skill, so a command by
the real path would ask the user's permission.
"""
import json
import os
import sys


def script_command(module_file, script):
    """The command that runs the skill's script `script`, by the folder the
    agent ran one of the skill's scripts from; `module_file` is the
    `__file__` of a module in the skill's scripts folder."""
    return f"python3 {os.path.join(scripts_folder(module_file), script)}"


def library_command(module_file, module):
    """The command that runs the library's module `module`, such as
    "extract_saved.py", beside the skill's folder as script_command() finds
    it."""
    return f"python3 {os.path.join(os.path.dirname(scripts_folder(module_file)), '..', 'agentic-manager-utils-lib', 'agentic_manager', module)}"


def scripts_folder(module_file):
    """The skill's scripts folder, holding `module_file`, by the path the
    agent ran one of its scripts from, or its own when the agent ran none."""
    # abspath, not realpath: the path the agent ran, which the skill
    # pre-approves.
    ran = os.path.dirname(os.path.abspath(sys.argv[0]))
    here = os.path.dirname(os.path.realpath(module_file))
    return ran if os.path.realpath(ran) == here else here


def stdin_json(usage):
    """The JSON the agent wrote on stdin. Exits, showing `usage`, the input
    to send, when it isn't JSON."""
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise SystemExit(f"the input isn't JSON: {error}\n\n{usage}")
