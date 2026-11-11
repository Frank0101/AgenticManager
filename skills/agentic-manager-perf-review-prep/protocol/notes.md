# Read a month of a manager's notes

A manager is preparing a performance review of the person named below. These are the notes from the manager's journal over one month that mention the person, each with the day it was written, shown inside the block it sits in, so the lines around it give its context: the lines that mention the person start with →. Find in them what can serve as feedback, and leave out the rest.

## What to keep

Keep a note only when the person is the one acting or the one judged in it, including when they're compared with others or held up as a model. Keep:

- a behaviour the manager noticed: something the person did or didn't do;
- an outcome tied to the person: a delivery, an incident they handled, or praise or a complaint from someone else;
- an implicit recognition: the person held up as a model, even in notes about someone else;
- context: a fact that is neither good nor bad, such as leave, a change of team or a promotion conversation.

Judge a note by how it ends: a later line, nested under it or further down the same day, can settle an earlier one, such as a concern followed by "all fine", or a missing task followed by "done". Keep what the note ends up saying, not the first line alone.

The same behaviour in several notes is kept each time, with each note's day: a later step merges them into a pattern.

## What to leave out

- A reminder or a to-do for the manager.
- A note where the person is only a name in passing, or a reference for something else.
- The status of the work, with no behaviour of the person in it.

When you're in doubt whether a note is feedback, leave it out, and list it in `in_doubt` with its day and why, so the manager can see it.

## Examples

| Note                                                                                                                   | Decision                              | Why                                                                                          |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------- |
| "Jane presented the migration to the wider team, great reception"                                                      | Keep, going well                      | A behaviour of Jane's                                                                        |
| "Jane didn't flag the delay until asked"                                                                               | Keep, to improve                      | A behaviour of Jane's                                                                        |
| "Sam said Jane's review saved the release"                                                                             | Keep, going well                      | Praise of Jane from someone else                                                             |
| "Sam could learn from how Jane works with agents", in notes about Sam                                                  | Keep, going well                      | An implicit recognition: Jane is held up as a model                                          |
| "Jane has already done it instead - well done!", under a line saying Sam set personal objectives unprompted            | Keep, going well                      | The line above says what was done: Jane set personal objectives without being asked          |
| "Jane got 'Exceeds' at the mid-year review"                                                                            | Keep, context                         | A past review's rating or verdict is a fact about that review, not a behaviour in the period |
| "Ask Jane about the rollout"                                                                                           | Leave out                             | A to-do for the manager                                                                      |
| "Jane, Sam and Alex in the planning sync"                                                                              | Leave out                             | A name in passing                                                                            |
| "I took Jane's plan as the starting point for Sam's"                                                                   | Leave out                             | Jane is only a template for Sam's plan: it says nothing about what Jane did                  |
| "Jane: migration API done, UI next"                                                                                    | Leave out                             | The status of Jane's work, with no behaviour of Jane's in it                                 |
| "Jane said in Slack 'on it', but didn't move the ticket - to check", with "-> all fine, in progress" nested under it   | Leave out                             | The line under it settles the concern: nothing to improve                                    |
| "Asked Jane for the docs, not done" in the morning, "Chat with Jane - Jane wrote the docs here: <link>" later that day | Keep, going well: Jane wrote the docs | The later note settles the earlier one: keep what the day ends with, not the missing docs    |

## Links in a note

{{links}}

## Each item

For each note you keep, write an item:

- `part`: `going_well` for what is going well or exceeding, `to_improve` for an improvement or stretch area, `context` for a fact that is neither;
- `point`: what the note says about the person;
- `value`: the company value it shows, or null;
- `date`: the day of the note, as YYYY-MM-DD.

A note can give several items, such as one going well and one to improve, and most notes give none.

{{point}}

{{value}}
