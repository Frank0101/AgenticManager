# Write the step change from the latest previous review

A manager is preparing a performance review of the person named below. Other agents read the manager's notes, the person's Slack messages and the feedback and reviews the person received in the period, and turned them into points: what is going well, what to improve and the context. Write the step change: how the period compares with the person's latest previous review, so the manager sees at a glance what improved, what is still to improve, what worsened, what held and how the context changed. The report shows a table of its rows, folded below the summary you write of them: the manager reads the summary first.

## What to read

The brief, at the path below, holds all you need: the person, each of the period's tables, going well, to improve and context, its points in its order, each with its id, its values, its source and when it was seen, and `reviews`, the person's previous reviews: the latest, with its points' ids, and the earlier ones. Read nothing else.

## Citing and writing

{{compare}}

## How to write the rows

The latest previous review, `reviews.latest`, is the baseline: give its points rows as the table and the rules below say, citing the period's points that show each.

| Change             | What it means                                                                                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `improved`         | A to-improve point the period shows resolved, citing what shows it, or no longer raises, citing nothing: the report then says it isn't raised again, not that it improved |
| `still_to_improve` | A to-improve point the period still raises                                                                                                                                |
| `worsened`         | A to-improve point the period raises more, or more often; or a going-well point the period contradicts                                                                    |
| `held`             | A going-well point the period shows still holds: less telling than a change, so give it only where it adds something                                                      |
| `context_change`   | A context point of the review that changed in the period, such as the team it names                                                                                       |
| `new_context`      | With `review_point` null, a period context point the review didn't have, such as a new role                                                                               |

Every to-improve point of the review has one row: `improved`, `still_to_improve` or `worsened`. A going-well point has a row only when the period shows it held or worsened, and context only for a significant change; a `new_context` row cites the period context point it stands for. Every change but `improved` cites at least one period point. Read the earlier reviews only to weigh a point: one raised in several reviews weighs more, and the summary says so. A point of an earlier review that the latest doesn't repeat is closed: don't reopen it.

## How to write the summary

Say what changed most first, a step change on a long-standing point before the rest, then what still needs work, in about {{step_change_words}} words, fewer when little changed.

## Examples

| Case                                                                                                                                                                  | Decision                                                                                                                                                      | Why                                                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| The latest review and the one before both raised Jane flagging delays only when asked (R-I1); the period's points I3 and I4 show Jane raising risks at every planning | Improved, citing I3 and I4; the summary opens with it: "Jane has turned round a point both previous reviews raised: Jane now raises risks at every planning." | A step change on a long-standing point, said first                           |
| The latest review's to improve, leading a design review alone (R-I2), which no period point mentions                                                                  | Improved, citing nothing; the summary says, at most in a clause, that it is no longer raised                                                                  | Not raised again isn't shown improved: the report says it isn't raised again |
| The latest review's going well, steady reviews for the squad (R-G1); a period to improve point, I2, says Jane's reviews now take a week                               | Worsened, citing I2                                                                                                                                           | A going-well point the period contradicts has worsened                       |
