"""How a script's entry point stops on a service's failure, Jira's (JiraError)
or GitHub's (GhError): on stderr, with what to do, and a non-zero exit code.

One rule for every service: a thing it says isn't there, or none the account
can see, is an answer, returned with why for the skill to print and carry on;
no answer, such as a rate limit once retry.py gives up, is a failure that stops
the skill, as output with a gap in it is easy to read as whole. The library
only raises, so a skill can tell the two apart, and this one place words the
stop for every skill, in a module of its own, as it needs both clients' errors.
"""
from contextlib import contextmanager

from agentic_manager.github import GhError
from agentic_manager.jira import JiraError

# What a GitHub failure's line starts with, unless a script says what it
# cost, such as that no report was written.
GITHUB_FAILED = "GitHub couldn't be read"


@contextmanager
def stops_on_failure(github_lead=GITHUB_FAILED):
    """Runs the block, and stops the program on a JiraError, with its
    explanation, or a GhError, with `github_lead`, the gh command by its
    first words and its explanation: both on stderr, with exit code 1, as SystemExit does."""
    try:
        yield
    except JiraError as failed:
        raise SystemExit(failed.explanation)
    except GhError as failed:
        raise SystemExit(
            f"{github_lead}: {failed.name}: {failed.explanation}")
