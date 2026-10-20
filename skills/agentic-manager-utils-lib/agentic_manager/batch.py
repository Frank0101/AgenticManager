"""How much a client asks a service at once, the sizes every client of the
library shares: how many things in one call, and how many calls at a time.

A batch is what a call sends, such as the tickets whose changelogs it asks for
or the pull requests whose times it reads; a page is how a service splits its
answer, and each client asks for the largest page its service allows, since a
smaller one only adds calls for the same answer. A batch keeps each call light
and limits what one failed call takes down, and one size for every client
keeps the rule simple.

Calls run WORKERS at a time: Jira's internal Development-panel endpoint drops
connections under more, and GitHub discourages concurrent requests (its
secondary rate limit), while batches leave few calls to make.
"""

# Things asked about in one call.
BATCH_SIZE = 100
# Calls to one service made at a time.
WORKERS = 4


def batches(items):
    """`items` in consecutive lists of at most BATCH_SIZE, in order."""
    items = list(items)
    return [items[start:start + BATCH_SIZE] for start in range(0, len(items), BATCH_SIZE)]
