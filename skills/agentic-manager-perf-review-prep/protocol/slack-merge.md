# Judge and merge what a person's Slack messages show

A manager is preparing a performance review of the person named below. Other agents read the person's Slack messages a month at a time and wrote a synopsis of each conversation, with its day and link. Decide what in them the review uses, and write it as one summary of what the messages show.

## What to keep

The review needs the picture over the whole period, not every detail. Keep only what has a clear impact or is a significant signal about the person; a small thing, such as a one-off thanks or a routine answer, stays out unless it repeats into a pattern, which is then one point.

Where it matters most:

- communication with stakeholders: updates, announcements, plans and answers in channels with a wide audience, such as cross-team, leadership or product channels;
- contributions in channels about incidents, alerts, on-call, security or reliability: engagement shows in what was said, such as a diagnosis, a fix or a clear answer;
- anywhere else, only what stands out, such as help others thank the person for, or a disagreement that mattered.

Put a point in `going_well` only when the messages themselves show it: someone thanks or praises the person, or what they did visibly unblocked or helped others; in `to_improve` only when someone raises a problem with the person's work or behaviour; and in `context` the rest worth keeping, such as what the person shared, led, explained or answered, with no judgment of it. Never judge tone or quality yourself: a message read out of its conversation is easy to misread, and the manager judges.

## What to leave out

- A small thing seen once, with no clear impact.
- Routine chatter, scheduling and status with nothing of the person's in it.
- A conversation where the person is only a name in passing.

When you're in doubt whether a conversation should be a point, leave it out, and list it in `in_doubt` with its day, what it says and why, so the manager can see it.

## How to merge

- Conversations about the same behaviour or outcome become one point, with every day in `dates`, oldest first, and every link in `links`. Write a pattern as one: "Answered alerts in the on-call channel, many times", not one point per day. Keep apart points that are about different things, even when they share a value.
- When conversations about the same thing disagree, keep both as points, or say how it changed.
- `context` points have `dates` and `links` too. Merge context that says the same thing into one.
- When nothing is worth keeping, submit every part empty.

## Examples

| Synopses                                                                                          | Decision           | Why                                                |
| ------------------------------------------------------------------------------------------------- | ------------------ | -------------------------------------------------- |
| In a cross-team channel, Jane posted the rollout plan, and three people asked follow-ups          | Keep, context      | Communication to a wide audience; no one judged it |
| In the cross-team channel, Jane posted the monthly rollout update (Jul); again (Aug, Sep)         | One point, context | A pattern of stakeholder communication             |
| In the incident channel, Jane explained the root cause, and Sam replied that it fixed the problem | Keep, going well   | The reply shows it helped                          |
| In a squad channel, Sam wrote that Jane's estimate was far off, again                             | Keep, to improve   | Someone raises a problem with Jane's work          |
| In the squad channel, Jane answered a question about a config flag, and Sam thanked them          | Leave out          | A small thing seen once                            |
| Jane said they'd be late for standup                                                              | Leave out          | Scheduling                                         |

## Writing

{{point}}

Each line of `in_doubt` is written as a point is.
