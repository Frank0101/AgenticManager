# Write the step change from the previous feedback

{{opening}}

It holds the person, each of the period's tables, going well, to improve and context, its points in its order, each with its id, its values, its source and when it was seen, and `previous`, the person's previous feedback, its points with their ids, such as P-I1.

## What to write

Write the step change: how the period compares with the person's previous feedback, so the manager sees at a glance what improved, what is still to improve, what worsened, what held and how the context changed. The report shows it as a table of its rows, under the summary you write of them.

## How to write the rows

The previous feedback, `previous`, is the baseline: give its points rows as the table and the rules below say, citing the period's points that show each. In the rows' evidence, cite the period's points by their ids, such as I2, never retyping them: the report shows each with its text and references.

| Change             | What it means                                                                                                                                                                                                         |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `improved`         | A to-improve point the period shows resolved, citing what shows it, or no longer raises, citing nothing: the report then says it isn't raised again, not that it improved                                             |
| `still_to_improve` | A to-improve point the period still raises                                                                                                                                                                            |
| `worsened`         | A to-improve point the period raises more, or more often than before, the evidence showing the difference: the same thing seen again is `still_to_improve`; or a going-well point the period contradicts              |
| `held`             | A going-well point the period shows still holds, and no more: less telling than a change, so give it only where it adds something, and the summary doesn't say it has grown or improved unless a period point says so |
| `context_change`   | A context point of the previous feedback that changed in the period, such as the team it names                                                                                                                        |
| `new_context`      | With `previous_point` null, a period context point the previous feedback didn't have, such as a new role                                                                                                              |

Every to-improve point of the previous feedback has at least one row, `improved`, `still_to_improve` or `worsened`; when its aspects went differently, one row per aspect, each with its own evidence. Rows of one point may conflict: the summary says what they add up to, such as a partial improvement or an attempt with problems still there. A going-well point has a row only when the period shows it held or worsened, and context only for a significant change; a `new_context` row cites the period context point it stands for. Every change but `improved` cites at least one period point. A period point that matches no point of the previous feedback, such as a new thing to improve, has no row, and is never attached to an older point: the observations show it.

## How to write the summary

Say what changed most first, a step change on a point the previous feedback raised before the rest, then what still needs work, in about {{step_change_words}} words, fewer when little changed. The summary weighs the rows, never lists them. The summary names no id, as the reader never sees them: say in words what the points show.

{{style}}

## Examples

| Case                                                                                                                                                                                                                                              | Decision                                                                                                                                                      | Why                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| The previous feedback raised Jane flagging delays only when asked (P-I1); the period's points I3 and I4 show Jane raising risks at every planning                                                                                                 | Improved, citing I3 and I4; the summary opens with it: "Jane has turned round a point the previous feedback raised: Jane now raises risks at every planning." | A step change on a point already raised, said first                                                              |
| The previous feedback's to improve, leading a design review alone (P-I2), which no period point mentions                                                                                                                                          | Improved, citing nothing; the summary says, at most in a clause, that it is no longer raised                                                                  | Not raised again isn't shown improved: the report says it isn't raised again                                     |
| The previous feedback's going well, steady reviews for the squad (P-G1); a period to improve point, I2, says Jane's reviews now take a week                                                                                                       | Worsened, citing I2                                                                                                                                           | A going-well point the period contradicts has worsened                                                           |
| The previous feedback raised Jane taking on too much and doing it alone rather than showing others (P-I1); the period's G5 shows Jane offering to walk colleagues through the work, but I2 shows Jane again taking work outside agreed priorities | Two rows: P-I1 improved, citing G5; P-I1 still_to_improve, citing I2; the summary says Jane now shows others how but still takes on too much                  | Aspects of one point that went differently are both said, never one hidden                                       |
| The previous feedback raised estimates that ran over (P-I3); the period's I5 says they ran over again in September and October                                                                                                                    | Still to improve, citing I5, not worsened                                                                                                                     | The same thing seen again isn't more of it                                                                       |
| The previous feedback raised nothing about sharing with the community; the period's I4 says Jane should share more there                                                                                                                          | No row                                                                                                                                                        | A new point isn't a change of an old one: attached to one, it would be misreported, and the observations show it |
