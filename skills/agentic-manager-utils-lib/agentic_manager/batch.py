"""How much a client asks a service at once, the sizes every client of the
library shares: how many things in one call, and how many calls at a time,
and gather(), which makes many calls that way.

A batch is what a call sends, such as the tickets whose changelogs it asks for
or the pull requests whose times it reads; a page is how a service splits its
answer, and each client asks for the largest page its service allows, since a
smaller one only adds calls for the same answer. A batch keeps each call light
and limits what one failed call takes down, and one size for every client
keeps the rule simple.

Calls run WORKERS at a time: Jira's internal Development-panel endpoint drops
connections under more, and GitHub discourages concurrent requests (its
secondary rate limit), while batches leave few calls to make.

A call that still fails once retry.py's rule gives up stops gather(), and the
skill's script with it, for Jira and GitHub alike: a partial answer is easy
to take for a whole one, such as a pull request it couldn't read for work
without times, so no call starts after a failure and the failure is raised.
A thing the service says isn't there is an answer, not a failure
(failures.py).
"""
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

# Things asked about in one call.
BATCH_SIZE = 100
# Calls to one service made at a time.
WORKERS = 4


def batches(items):
    """`items` in consecutive lists of at most BATCH_SIZE, in order."""
    items = list(items)
    return [items[start:start + BATCH_SIZE] for start in range(0, len(items), BATCH_SIZE)]


def gather[T, R](items: Iterable[T], call: Callable[[T], R], workers=WORKERS) -> list[R]:
    """call(item)'s answer for each of `items`, in their order, made `workers`
    at a time. The first call to fail stops the rest: none starts after it,
    and its error is raised once those running have ended."""
    failures: list[BaseException] = []

    def attempt(item: T) -> R:
        if failures:
            raise _Skipped
        try:
            return call(item)
        except BaseException as error:
            failures.append(error)
            raise
    with ThreadPoolExecutor(max_workers=workers) as pool:
        running = [pool.submit(attempt, item) for item in items]
    if failures:
        raise failures[0]
    return [done.result() for done in running]


class _Skipped(Exception):
    """A call gather() didn't make, as another had failed."""
