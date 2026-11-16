# Check the manager's view against the period's evidence

A manager is preparing a performance review of the person named below. Before the evidence was gathered, the manager gave their overall view of the person, recorded as points: what is going well, what to improve and the context. Other agents then read the manager's notes, the person's Slack messages and the feedback and reviews the person received in the period, and turned them into points of their own. Compare the manager's view with that evidence, so the manager can revisit it: what the evidence confirms, what it gives little support, what it contradicts, and the strong themes of the evidence the view doesn't mention. The report shows a table of its rows, folded below the summary you write of them: the manager reads the summary first.

## What to read

The brief, at the path below, holds all you need: the person, each of the period's tables, going well, to improve and context, its points in its order, each with its id, its values, its source and when it was seen, and `view`, the manager's view, its points with their ids, such as V-I1. Read nothing else.

## Citing and writing

{{compare}}

## How to write the rows

Give every point of the view, in every part, context too, one row, citing the period's points that show it.

| Check            | What it means                                                                                                                                       |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `confirmed`      | A point of the view the period's points bear out, citing them                                                                                       |
| `little_support` | A point of the view the period's points barely show, citing the little there is, or nothing: the report then says there is no support in the period |
| `contradicted`   | A point of the view the period's points go against, citing them                                                                                     |
| `not_in_view`    | With `view_point` null, a strong theme of the period the view doesn't mention, citing the points that make it                                       |

Give `not_in_view` only to a strong theme: one several points come back to, or one point weighty for the review, such as a serious incident. A one-off minor point, such as a remark made once in a 1:1, isn't a theme, however much it might matter to the person. A point of the period the view doesn't mention is not a row of its own: most aren't, and the table would bury the view's rows.

## How to write the summary

Say first what the evidence confirms and what it contradicts, then the view's blind spots, the strong themes it doesn't mention, and what has little support only where it matters, in about {{view_check_words}} words, fewer when there is little to say. Never address the manager as "you": write "the manager's view", such as "The manager's view that Jane leads the migration well is confirmed by …".

## Examples

| Case                                                                                                                                                       | Decision                                    | Why                                                                               |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------- |
| The view says Jane owns the billing migration well (V-G1); the period's points G2 and G3 show Jane presenting it to the wider team and keeping to its plan | Confirmed, citing G2 and G3                 | Several points of the period bear the view out                                    |
| The view says Jane needs support to plan releases (V-I2), which no period point mentions                                                                   | Little support, citing nothing              | Nothing in the period shows it: the report says there is no support in the period |
| The view says nothing of how Jane flags delays; the period's points I1 and I2 show Jane flagging them only when asked, many times                          | Not in the manager's view, citing I1 and I2 | A theme several points come back to, which the view misses                        |
| The view says nothing of how Jane feels; one 1:1 point, C4, says Jane felt tired that week                                                                 | No row                                      | One remark made once, not a theme: a row would give it a weight it doesn't have   |
