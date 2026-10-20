"""How a script's entry point stops on a service's failure: Jira's
(JiraError) or GitHub's (GhError), shown on stderr with what to do, and an
exit code that isn't zero.

One rule for every service: a thing asked for that isn't there is an
answer, and no answer from the service is a failure. The service saying it
has no such ticket, pull request, commit or repository, or none the account
can see, is returned with why, a line the skill prints where the thing would
have been, and the skill carries on with the rest. A failure, such as a
rate limit, a bad login or the service down once retry.py gives up, is
raised and stops the skill: output with a gap in it is easy to read as
whole.

The library raises and never stops the program itself, so a skill's code
can tell an answer from a failure; only a script's main stops, and this one
place words the stop, so every skill shows a failure alike. Its own module,
not batch.py's: it needs both clients' errors, and both clients import
batch.py.
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
