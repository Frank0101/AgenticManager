"""The map of the code the skills share: every module of the library and of
each skill's scripts folder, what it is for, and the functions and classes
other code may use, each with what it is for.

It is generated from the code each time, read with ast and never run, so it
can't go stale: a module's purpose is the first sentence of its header
comment, a function's or class's that of its docstring. A skill's command, a
module with a `main`, lists only what the folder's other modules use from it,
and constants and a command's entry are left out, so the map stays quick.
"""
import argparse
import ast
import glob
import os
import re

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
