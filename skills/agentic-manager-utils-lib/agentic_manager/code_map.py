"""The map of the code the skills share: every module of the library and of
each skill's scripts folder, and the functions and classes other code may use.

It is read with ast and never run, so it can't go stale; a skill's command, a
module with a `main`, lists only what its folder's other modules use, so it
stays quick; the library lists every public name. A skill's protocols also get
where each shared part lands, found from the files: a part is used where a file names {{name}}, by protocol.py's regex.
A script is matched by name only where that can't be mistaken, as a plain
word is also a key or a phase; what can't be seen is said in the map.
"""
import argparse
import ast
import glob
import os
import re
import sys

if not __package__:
    # Run as a script: import the package from the folder that holds it.
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))))
from agentic_manager.protocol import PLACEHOLDER  # noqa: E402

LIBRARY = os.path.dirname(os.path.realpath(__file__))
SKILLS = os.path.dirname(os.path.dirname(LIBRARY))
ENTRY = {"main", "parse_args"}


def code_map(skill=None):
    """The map as Markdown: of one skill (or the library) by name, or of all."""
    chosen = folders()
    if skill:
        if skill not in chosen:
            raise SystemExit(
                f"no skill {skill!r} with code; there are: {', '.join(chosen)}")
        chosen = {skill: chosen[skill]}
    out = []
    for name, folder in chosen.items():
        out.append(f"# {name}")
        for entry in modules(folder):
            out += ["", f"## `{entry['module']}.py`", "",
                    entry["about"] or "(no header comment)"]
            if entry["names"]:
                out.append("")
                out += [f"- `{n}`: {about or '(no docstring)'}" for n,
                        about in entry["names"]]
        out += parts_section(os.path.dirname(folder))
        out.append("")
    return "\n".join(out)


def modules(folder):
    """[{module, about, names: [(name, about)]}] of a code folder, by module
    name, holding the names other code may use."""
    trees = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
        with open(path, encoding="utf-8") as f:
            trees[os.path.basename(path)[:-3]] = ast.parse(f.read())
    used = imported_names(trees)
    found = []
    for module, tree in trees.items():
        listed = public_names(tree)
        if folder != LIBRARY and is_command(tree):
            listed &= used[module]
        nodes = [node for node in tree.body if getattr(
            node, "name", None) in listed]
        found.append({"module": module, "about": first_sentence(ast.get_docstring(tree)),
                      "names": [(node.name, first_sentence(ast.get_docstring(node))) for node in nodes]})
    return found


def parts_section(skill_dir):
    """The map's lines for the shared protocol parts of the skill folder
    `skill_dir`: a note on how they were found, then a line for each part
    with where it lands, as parts_of() works it out; none without parts."""
    parts = parts_of(skill_dir)
    if not parts:
        return []
    out = ["", "## Protocol parts", "",
           "*A part is a `_name.md` beside the protocols, filled wherever a file names `{{name}}` and no value of "
           "that name is given. A script is listed when it passes the name to a call that mentions protocol, or "
           "holds a part's or a hyphenated protocol's name as a string; a plain-word protocol filled any other "
           "way isn't seen, nor a value a script passes under a part's name, which wins.*", ""]
    for part in parts:
        users = ", ".join(f"`{user}.md`" + (f" (in {', '.join(f'`{f}.md`' for f in via)})" if via else "")
                          for user, via in part["users"]) or "no protocol file"
        scripts = f"; filled by {', '.join(f'`{s}.py`' for s in part['scripts'])
                                 }" if part["scripts"] else ""
        out.append(f"- `{part['part']}.md`: used in {users}{scripts}")
    return out


def parts_of(skill_dir):
    """[{part, users, scripts}] of the shared parts of the skill folder
    `skill_dir`'s protocol folder, by name: `users`, the files that name it,
    each a part with the protocol files that reach it through that part; and
    `scripts`, those that fill it by name, or any file it reaches the
    scripts through. Empty without a protocol folder or parts."""
    folder = os.path.join(skill_dir, "protocol")
    stems = sorted(os.path.basename(path)[:-3]
                   for path in glob.glob(os.path.join(folder, "*.md")))
    parts = {stem for stem in stems if stem.startswith("_")}
    named = {}
    for stem in stems:
        with open(os.path.join(folder, f"{stem}.md"), encoding="utf-8") as f:
            named[stem] = {f"_{match[1]}" for match in PLACEHOLDER.finditer(
                f.read()) if f"_{match[1]}" in parts}
    filled = filled_by(os.path.join(skill_dir, "scripts"), set(stems))

    def reaching(part, seen=()):
        """Every file, part or protocol, that names `part`, directly or
        through other parts."""
        direct = {stem for stem in stems if part in named[stem]}
        return direct | {stem for user in direct if user in parts and user not in seen
                         for stem in reaching(user, (*seen, part))}
    found = []
    for part in sorted(parts):
        users = [(stem, sorted(file for file in reaching(stem) if file not in parts) if stem in parts else [])
                 for stem in stems if part in named[stem]]
        scripts = sorted({script for stem in {part} | reaching(part)
                         for script in filled.get(stem, ())})
        found.append({"part": part, "users": users, "scripts": scripts})
    return found


def filled_by(scripts_dir, stems):
    """{stem: the scripts that fill it by name}, for the protocol files and
    parts `stems` and the folder `scripts_dir`'s modules: a script fills a
    stem when it passes it to a call whose name mentions protocol, or, for a
    part, or a stem with a hyphen, holds it as a string anywhere; a plain word
    is also a key or a phase, so it counts only as a call's argument."""
    found = {}
    for path in sorted(glob.glob(os.path.join(scripts_dir, "*.py"))):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        module = os.path.basename(path)[:-3]
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and "protocol" in dotted(node.func).lower():
                names = [arg.value for arg in node.args if isinstance(
                    arg, ast.Constant) and isinstance(arg.value, str)]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names = [node.value] if node.value.startswith(
                    "_") or "-" in node.value else []
            else:
                continue
            for name in names:
                if (stem := name.removesuffix(".md")) in stems:
                    found.setdefault(stem, set()).add(module)
    return {stem: sorted(modules) for stem, modules in found.items()}


def dotted(node):
    """The name a call's function is reached by, such as protocol.text, or ""
    for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    return ""


def folders():
    """{skill name: its code folder}: the library first, then each skill's
    scripts folder."""
    found = {os.path.basename(os.path.dirname(LIBRARY)): LIBRARY}
    for path in sorted(glob.glob(os.path.join(SKILLS, "*", "scripts"))):
        found[os.path.basename(os.path.dirname(path))] = path
    return found


def is_command(tree):
    """Whether a module is a command: it has a `main`."""
    return any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body)


def public_names(tree):
    """The top-level functions and classes of a module without a leading underscore."""
    return {node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")} - ENTRY


def imported_names(trees):
    """{module: the names the folder's other modules use from it}, whether
    imported by name or reached as module.name."""
    used = {module: set() for module in trees}
    for module, tree in trees.items():
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in trees and node.module != module:
                used[node.module] |= {alias.name for alias in node.names}
            elif isinstance(node, ast.Import):
                aliases |= {alias.asname or alias.name: alias.name for alias in node.names
                            if alias.name in trees and alias.name != module}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                used[aliases[node.value.id]].add(node.attr)
    return used


def first_sentence(text):
    """The first sentence of a docstring or header, on one line, or "" if
    there is none."""
    paragraph = " ".join((text or "").strip().split("\n\n")[0].split())
    return re.split(r"(?<=[.!?])\s+(?=[A-Z`\"(])", paragraph)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print the map of the skills' code, generated from the code, as Markdown: "
        "the library, then every skill.")
    parser.add_argument(
        "--skill", help="only this skill's scripts, or the library by its name")
    print(code_map(parser.parse_args(argv).skill), end="")


if __name__ == "__main__":
    main()
