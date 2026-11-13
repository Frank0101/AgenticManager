"""Trying a call to a service again when it fails in passing or hits a short
rate limit, the one rule every client of the library follows.

Services drop connections, time out and answer "busy", and one such failure
shouldn't end a run; each client says which of its failures are passing. A
rate limit is each service's own, so its client says how long to wait: a
short one is waited out, as a stopped run would only be run again; a long
one, or one past the caps here, which keep a run bearable, is final. Each
wait is said on stderr in the client's words, which hold no secret.
"""
import sys
import time

# Seconds to wait before each new try of a call that failed in passing.
RETRY_WAITS = (1, 3, 9)
# The longest wait for a rate limit worth making, in seconds, and the most
# such waits for one call: past either, the limit is final.
LONGEST_RATE_WAIT = 300
RATE_WAITS_AT_MOST = 3
# What the user does about a rate limit that is final, of any service.
RATE_LIMITED = "Run it again later: the limit can take up to an hour to lift."


def retried(attempt, passing, note, rate_wait=None):
    """attempt()'s answer, trying it again after each of RETRY_WAITS while it
    fails in passing, and after the wait `rate_wait` gives while it hits a
    short rate limit. `passing(error)` says whether an error attempt() raised
    is passing; `rate_wait(error, tries)`, when given, the seconds to wait
    before trying again after a rate limit, `tries` being how many such waits
    this call already made, or None when the error isn't one to wait out;
    `note(error)` says what failed, for the line each wait prints. A final
    error, a rate-limit wait over LONGEST_RATE_WAIT or past
    RATE_WAITS_AT_MOST, or the last error once the tries run out, is raised."""
    waits, rate_tries = iter(RETRY_WAITS), 0
    while True:
        try:
            return attempt()
        except Exception as error:
            if passing(error):
                wait = next(waits, None)
            elif rate_wait and rate_tries < RATE_WAITS_AT_MOST:
                wait, rate_tries = rate_wait(error, rate_tries), rate_tries + 1
            else:
                wait = None
            if wait is None or wait > LONGEST_RATE_WAIT:
                raise
            wait_out(note(error), wait)


def wait_out(what, seconds):
    """Says on stderr what failed and how long the call waits, then waits."""
    print(f"{what}, trying again in {seconds} s", file=sys.stderr)
    time.sleep(seconds)
