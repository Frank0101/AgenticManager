"""A fake gh's answer to the GraphQL call that github.pull_events() makes,
built from each pull request's own answer, so a test's fake gh answers it
from answers by URL; shared by the tests of every skill that reads pull
requests' events, including a fake gh run as a program.

It reads the query as github._events_query() writes it, one repository a line,
and answers as GitHub does: the data of every alias, null for a pull request
it can't resolve with an error naming its path, and then, as gh does, the
answer on stdout, the first error on stderr and exit code 1.
"""
import json
import re

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
