"""How many things a client asks a service about in one call, the one size
every client of the library shares.

A batch is what a call sends, such as the tickets whose changelogs it asks for
or the pull requests whose times it reads; a page is how a service splits its
answer, and each client asks for the largest page its service allows, since a
smaller one only adds calls for the same answer. A batch keeps each call light
and limits what one failed call takes down, and one size for every client
keeps the rule simple.
"""

# Things asked about in one call.
BATCH_SIZE = 100


def batches(items):
    """`items` in consecutive lists of at most BATCH_SIZE, in order."""
    items = list(items)
    return [items[start:start + BATCH_SIZE] for start in range(0, len(items), BATCH_SIZE)]
