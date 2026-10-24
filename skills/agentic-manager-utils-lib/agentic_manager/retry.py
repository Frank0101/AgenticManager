"""Trying a call to a service again when it fails in passing, the one rule
every client of the library follows.

Services drop connections, time out and answer "busy", and one such failure
shouldn't end a run; each client says which of its failures are passing. A
rate limit, of any service, is final, with the advice to wait a minute: it
doesn't lift within the waits, and the skills make too few calls to wait out
its window. Each wait is said on stderr in the client's words, which hold no
secret, so a run that recovered still shows the service struggled.
"""
import sys
import time

# Seconds to wait before each new try of a call that failed in passing.
RETRY_WAITS = (1, 3, 9)
# What the user does about a rate limit, of any service.
RATE_LIMITED = "Wait a minute and run it again."


def retried(attempt, passing, note):
    """attempt()'s answer, trying it again after each of RETRY_WAITS while it
    fails in passing. `passing(error)` says whether an error attempt() raised
    is passing; `note(error)` says what failed, for the line each wait
    prints. A final error, or the last once the tries run out, is raised."""
    waits = iter(RETRY_WAITS)
    while True:
        try:
            return attempt()
        except Exception as error:
            if not passing(error) or (wait := next(waits, None)) is None:
                raise
            wait_out(note(error), wait)


def wait_out(what, seconds):
    """Says on stderr what failed and how long the call waits, then waits."""
    print(f"{what}, trying again in {seconds} s", file=sys.stderr)
    time.sleep(seconds)
