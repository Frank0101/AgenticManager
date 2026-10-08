"""Finds the mechanical leads of a refactoring review, so none depends on being
spotted by eye. It changes nothing: each lead is for a reviewer to judge, as a
finding or as considered, with the reason.

    python3 precheck.py [--root <repo>]

--root is the repository, by default the git repository of the current folder.
It checks every tracked file, and new ones git doesn't ignore. In Python
files, it looks for references only in comments and docstrings, as the code's
own strings are data:

- similar-tests: tests in one class or module whose names suggest they check
  the same thing: one name starts the other, or they differ only in words
  naming the outcome, such as valid and invalid. They may become one test over
  a table of cases.
- unknown-test: a name starting with test_ that the repo defines nowhere, as a
  test, a module or any other Python name.
- missing-file: a local Markdown link, or a script named in backticks, that
  doesn't exist.
- unknown-flag: a flag given to one of the repo's scripts, on the same line,
  that the script never mentions.
- unused-import and unused-definition: an import a module never uses, and a
  module-level function, class or constant nothing in the repo refers to.
- long-comment: a comment line longer than COMMENT_WIDTH characters, which
  formatters don't wrap.
- type: an error or warning from pyright, the checker Pylance runs in VS Code,
  with the repo's own pyright settings. It runs through npx; without npx, the
  check is skipped.

Prints one line of JSON: {"leads": [{"check", "file", "line", "message"}],
"tests": {file: [[line, name], ...]}, "skipped": [why, ...]}, the leads sorted
by file and line, and every test with its class, so a reviewer sees what each
test file checks.
"""
import argparse
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
from itertools import combinations

COMMENT_WIDTH = 90
PYRIGHT = "1.1.414"
TEXT_SUFFIXES = (".py", ".md", ".json", ".toml",
                 ".txt", ".yml", ".yaml", ".sh")
# Words that name a test's outcome rather than what it tests.
OUTCOME_WORDS = {"valid", "invalid", "error", "errors", "failure", "failures", "fails", "passes",
                 "problems", "refusals", "rejected", "accepted", "success", "ok"}
TEST_NAME = re.compile(r"\btest_[a-z0-9_]*[a-z0-9]\b")
LOCAL_LINK = re.compile(r"\]\(<?([^)\s>]+)>?\)")
SCRIPT_IN_BACKTICKS = re.compile(r"`([\w./-]+\.py)\b")
FLAG = re.compile(r"(?<![\w-])--[a-z][\w-]*")


def repo_files(root):
    """The repo's text files, relative to `root`: tracked ones and new ones
    git doesn't ignore, without deleted files or symbolic links."""
    listed = []
    for extra in ([], ["--others", "--exclude-standard"]):
        out = subprocess.run(["git", "ls-files", "-z", *extra], cwd=root, capture_output=True, text=True,
                             check=True).stdout
        listed += [p for p in out.split("\0") if p]
    return sorted({p for p in listed if p.endswith(TEXT_SUFFIXES)
                   and os.path.isfile(os.path.join(root, p)) and not os.path.islink(os.path.join(root, p))})


def read_texts(root, files):
    """{file: its text}, leaving out files that aren't UTF-8."""
    texts = {}
    for path in files:
        try:
            with open(os.path.join(root, path), encoding="utf-8") as f:
                texts[path] = f.read()
        except UnicodeDecodeError:
            pass
    return texts


def parse(text):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def prose(path, text):
    """[(line number, text)] where references are read: every line of a
    document, but only the comments and docstrings of Python code."""
    if not path.endswith(".py"):
        return list(enumerate(text.splitlines(), 1))
    lines = text.splitlines()
    found = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                found.append((token.start[0], token.string))
    except (tokenize.TokenError, SyntaxError):
        return list(enumerate(lines, 1))
    tree = parse(text)
    for node in ast.walk(tree) if tree else []:
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str) and first.end_lineno):
                found += [(n, lines[n - 1])
                          for n in range(first.lineno, first.end_lineno + 1)]
    return sorted(found)


def lead(check, file, line, message):
    return {"check": check, "file": file, "line": line, "message": message}


def is_test_file(path):
    return os.path.basename(path).startswith("test_") and path.endswith(".py")


def test_functions(tree):
    """[(line, class name or "", test name)] of a test module, in order."""
    found = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            found += [(item.lineno, node.name, item.name) for item in node.body
                      if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_")]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            found.append((node.lineno, "", node.name))
    return found


def similar(a, b):
    """Whether two test names suggest the same thing tested: one's words start
    the other's, or they differ only in words naming the outcome."""
    words_a, words_b = a[len("test_"):].split("_"), b[len("test_"):].split("_")
    short, long_ = sorted((words_a, words_b), key=len)
    if long_[:len(short)] == short:
        return True
    return [w for w in words_a if w not in OUTCOME_WORDS] == [w for w in words_b if w not in OUTCOME_WORDS]


def check_tests(trees):
    """(leads, {file: [[line, its class and name]]}) for every test file."""
    leads, listing = [], {}
    for path, tree in trees.items():
        if not is_test_file(path):
            continue
        functions = test_functions(tree)
        listing[path] = [[line, f"{cls}.{name}" if cls else name]
                         for line, cls, name in functions]
        for (line_a, cls_a, a), (line_b, cls_b, b) in combinations(functions, 2):
            if cls_a == cls_b and similar(a, b):
                leads.append(lead("similar-tests", path, line_b,
                                  f"{b} may check the same thing as {a} (line {line_a})"))
    return leads, listing


def check_test_names(texts, trees):
    """Names starting with test_ that the repo defines nowhere."""
    defined = {os.path.splitext(os.path.basename(path))[0] for path in texts}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
    leads = []
    for path, text in texts.items():
        for number, line in prose(path, text):
            for match in TEST_NAME.finditer(line):
                name = match.group()
                if name not in defined and not line[match.end():].startswith((".py", "<", "*")):
                    leads.append(lead("unknown-test", path, number,
                                 f"{name} is defined nowhere"))
    return leads


def check_files(root, texts):
    """Local Markdown links that lead nowhere, and scripts named in backticks
    that no file in the repo is."""
    scripts = {os.path.basename(path)
               for path in texts if path.endswith(".py")}
    leads = []
    for path, text in texts.items():
        for number, line in prose(path, text):
            if path.endswith(".md"):
                for target in LOCAL_LINK.findall(line):
                    target = target.split("#")[0]
                    if (target and not re.match(r"[a-z]+:", target) and not re.search(r"[$<{]", target)
                            and not os.path.exists(os.path.join(root, os.path.dirname(path), target))):
                        leads.append(
                            lead("missing-file", path, number, f"the link to {target} leads nowhere"))
            for script in SCRIPT_IN_BACKTICKS.findall(line):
                if os.path.basename(script) not in scripts and not re.search(r"[<*]", script):
                    leads.append(lead("missing-file", path, number,
                                 f"{script} is no file in the repo"))
    return leads


def check_flags(texts):
    """Flags given to a repo script, on the same line as its name, that the
    script's source never mentions."""
    sources = {}
    for path, text in texts.items():
        if path.endswith(".py"):
            sources.setdefault(os.path.basename(path), []).append(text)
    leads = []
    for path, text in texts.items():
        for number, line in prose(path, text):
            for match in re.finditer(r"([\w-]+\.py)\b", line):
                script = match.group(1)
                if script not in sources or os.path.basename(path) == script:
                    continue
                rest = re.split(r"`|\.py\b", line[match.end():])[0]
                for flag in FLAG.findall(rest):
                    if not any(f'"{flag}"' in source or f"'{flag}'" in source for source in sources[script]):
                        leads.append(lead("unknown-flag", path,
                                     number, f"{script} has no {flag}"))
    return leads


def check_imports(texts, trees):
    """Imports a module never uses, unless marked noqa."""
    leads = []
    for path, tree in trees.items():
        if os.path.basename(path) == "__init__.py":
            continue
        lines = texts[path].splitlines()
        used = {node.id for node in ast.walk(
            tree) if isinstance(node, ast.Name)}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and "noqa" not in lines[node.lineno - 1]:
                for alias in node.names:
                    name = (alias.asname or alias.name).split(".")[0]
                    if name != "*" and name not in used:
                        leads.append(
                            lead("unused-import", path, node.lineno, f"{name} is imported but never used"))
    return leads


def check_definitions(texts, trees):
    """Module-level functions, classes and constants of the repo's code (not
    its tests) that no Python file refers to."""
    words = {}
    for path, text in texts.items():
        if path.endswith(".py"):
            for word in re.findall(r"\w+", text):
                words[word] = words.get(word, 0) + 1
    leads = []
    for path, tree in trees.items():
        if is_test_file(path) or path.startswith("tests/"):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            else:
                continue
            for name in names:
                if name != "main" and not name.startswith("__") and words.get(name, 0) <= 1:
                    leads.append(lead("unused-definition", path,
                                 node.lineno, f"nothing refers to {name}"))
    return leads


def check_comments(texts):
    leads = []
    for path, text in texts.items():
        if path.endswith(".py"):
            for number, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#") and not line.startswith("#!") and len(line) > COMMENT_WIDTH:
                    leads.append(lead("long-comment", path, number,
                                      f"a {len(line)}-character comment line, over {COMMENT_WIDTH}"))
    return leads


def check_types(root, texts):
    """(leads, skipped): pyright's errors and warnings, or why it didn't run."""
    if not any(path.endswith(".py") for path in texts):
        return [], []
    npx = shutil.which("npx")
    if not npx:
        return [], ["type: npx (Node.js) is not available, so pyright didn't run"]
    try:
        proc = subprocess.run([npx, "-y", f"pyright@{PYRIGHT}", "--outputjson"], cwd=root,
                              capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return [], ["type: pyright took more than 10 minutes"]
    try:
        diagnostics = json.loads(proc.stdout)["generalDiagnostics"]
    except (ValueError, KeyError):
        problem = (proc.stderr.strip() or proc.stdout.strip()
                   or "no output").splitlines()[0]
        return [], [f"type: pyright didn't run: {problem}"]
    leads = []
    for d in diagnostics:
        if d.get("severity") in ("error", "warning"):
            rule = f" ({d['rule']})" if d.get("rule") else ""
            leads.append(lead("type", os.path.relpath(d["file"], root), d["range"]["start"]["line"] + 1,
                              f"{d['severity']}: {d['message'].splitlines()[0]}{rule}"))
    return leads, []


def precheck(root):
    texts = read_texts(root, repo_files(root))
    trees = {path: tree for path, text in texts.items(
    ) if path.endswith(".py") and (tree := parse(text))}
    leads, tests = check_tests(trees)
    leads += check_test_names(texts, trees) + \
        check_files(root, texts) + check_flags(texts)
    leads += check_imports(texts, trees) + \
        check_definitions(texts, trees) + check_comments(texts)
    types, skipped = check_types(root, texts)
    leads += types
    leads.sort(key=lambda found: (
        found["file"], found["line"], found["check"]))
    return {"leads": leads, "tests": tests, "skipped": skipped}


def default_root():
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("not in a git repository: pass --root")
    return proc.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="List the mechanical leads of a refactoring review.")
    parser.add_argument(
        "--root", help="the repository, by default the one of the current folder")
    args = parser.parse_args(argv)
    root = os.path.realpath(args.root or default_root())
    print(json.dumps(precheck(root)))


if __name__ == "__main__":
    sys.exit(main())
