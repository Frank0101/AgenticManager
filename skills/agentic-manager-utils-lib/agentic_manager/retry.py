"""Trying a call to a service again when it fails in passing, the one rule
every client of the library follows.

Services drop connections, time out and answer "busy"; one such failure
shouldn't end a skill's run, so the call is tried again after each of
RETRY_WAITS, then fails. Each client says which of its failures are passing;
any other is final at once. A rate limit, of any service, is final, with the
advice to wait a minute: it doesn't lift within the waits, and the skills make
few calls, so waiting out its window isn't worth the machinery. Each wait is
said on stderr, so a run that recovered still shows the service struggled;
the client words it, so it says nothing a secret could be in.
"""
import sys
import time

# Seconds to wait before each new try of a call that failed in passing.
RETRY_WAITS = (1, 3, 9)


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
