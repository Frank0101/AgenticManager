"""A fake gh, run as a program from a test's PATH, and its answer to the
GraphQL call that github.pull_events() makes, built from each pull request's
own answer, so a test's fake gh answers it from answers by URL; shared by the
tests of every skill whose scripts run gh.

The program answers by the words of a command, so a test gives one answer
per kind of call. The GraphQL answer reads the query as
github._events_query() writes it, one repository a line, and answers as
GitHub does: the data of every alias, null for a pull request it can't
resolve with an error naming its path, and then, as gh does, the answer on
stdout, the first error on stderr and exit code 1.
"""
import json
import re

# A fake gh: prints the answer FAKE_GH_ANSWERS holds for the words of its
# command up to the first option; for none, or for {"fails": message}, it
# fails as gh does, its message on stderr. A GraphQL call, unless "api
# graphql" is answered as a whole, is answered from each pull request's "pr
# view <url>", as graphql_answer() builds it, imported from this folder,
# FAKE_GH_LIB. Each command's words go to FAKE_GH_LOG, one line each.
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
sys.path.insert(0, os.environ["FAKE_GH_LIB"])
from gh_fake import graphql_answer, is_graphql
with open(os.environ["FAKE_GH_ANSWERS"], encoding="utf-8") as f:
    answers = json.load(f)
if is_graphql(sys.argv[1:]) and "api graphql" not in answers:
    code, out, err = graphql_answer(sys.argv[1:], lambda url: answers.get(f"pr view {url}"))
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.exit(code)
words = []
for word in sys.argv[1:]:
    if word.startswith("-"):
        break
    words.append(word)
answer = answers.get(" ".join(words))
if answer is None or (isinstance(answer, dict) and "fails" in answer):
    sys.exit((answer or {}).get("fails") or "no answer")
print(json.dumps(answer))
"""

REPOSITORY = re.compile(
    r"(r\d+): repository\(owner: \$(o\d+), name: \$(n\d+)\)")
PULL = re.compile(r"(p\d+): pullRequest\(number: \$(p\d+)\)")


def is_graphql(command):
    """Whether `command`, gh's arguments after "gh", is a GraphQL call."""
    return command[:2] == ["api", "graphql"]


def graphql_answer(command, answer_of):
    """(exit code, stdout, stderr) of gh for the GraphQL call `command`, its
    arguments after "gh": `answer_of(url)` gives each pull request's fields,
    or None for one GitHub can't resolve."""
    fields, host = {}, "github.com"
    for flag, value in zip(command, command[1:]):
        if flag in ("-f", "-F"):
            key, _, text = value.partition("=")
            fields[key] = text
        elif flag == "--hostname":
            host = value
    data, errors = {}, []
    for line in fields["query"].splitlines():
        if not (repository := REPOSITORY.match(line)):
            continue
        nodes = data.setdefault(repository[1], {})
        for alias, number in PULL.findall(line):
            url = f"https://{host}/{fields[repository[2]]}/{fields[repository[3]]}/pull/{fields[number]}"
            nodes[alias] = answer_of(url)
            if nodes[alias] is None:
                errors.append({"type": "NOT_FOUND", "path": [repository[1], alias],
                               "message": f"Could not resolve to a PullRequest with the number of {fields[number]}."})
    if errors:
        return 1, json.dumps({"data": data, "errors": errors}), f"gh: {errors[0]['message']}\n"
    return 0, json.dumps({"data": data}), ""
