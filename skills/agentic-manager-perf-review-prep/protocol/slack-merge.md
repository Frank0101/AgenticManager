# Judge and merge what a person's Slack messages show

A manager is preparing a performance review of the person named below. Other agents read the person's Slack messages a month at a time and wrote a synopsis of each conversation, with its day and link. Decide what in them the review uses, and write it as one summary of what the messages show.

## What to keep

The review needs the picture over the whole period, not every detail. Keep only what has a clear impact or is a significant signal about the person; a small thing, such as a one-off thanks or a routine answer, stays out unless it repeats into a pattern, which is then one point.

Where it matters most:

- communication with stakeholders: updates, announcements, plans and answers in channels with a wide audience, such as cross-team, leadership or product channels;
- contributions in channels about incidents, alerts, on-call, security or reliability: engagement shows in what was said, such as a diagnosis, a fix or a clear answer;
- anywhere else, only what stands out, such as help others thank the person for, or a disagreement that mattered.

Put a point in `going_well` when someone thanks or praises the person, when what they did visibly unblocked or helped others, or when the messages show a behaviour of theirs that is significant or repeats, such as those above, even with no one thanking them. Put one in `to_improve` only when someone raises a problem with the person's work or behaviour: a message read out of its conversation is easy to misread. Never judge tone or quality yourself; the manager judges.

## What to leave out

- A small thing seen once, with no clear impact.
- Routine chatter, scheduling and status with nothing of the person's in it.
- The work itself, such as what the person built or the pull requests they posted: the prep gathers it from their tools. Someone's thanks or praise for it is kept.
- A conversation where the person is only a name in passing.

{{merge}}

## Examples

| Synopses                                                                                          | Decision                                                                                                      | Why                                                                                            |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| In a cross-team channel, Jane posted the rollout plan, and three people asked follow-ups          | Keep, going well                                                                                              | Communication to a wide audience, which the messages show on their own                         |
| In the cross-team channel, Jane posted the monthly rollout update (Jul); again (Aug, Sep)         | One point, going well, every day                                                                              | A pattern of stakeholder communication                                                         |
| In the incident channel, Jane explained the root cause, and Sam replied that it fixed the problem | Keep, going well                                                                                              | The reply shows it helped                                                                      |
| In the release channel, Sam thanked Jane, Alex and Kim by name for the launch; 30 people reacted  | Keep, going well                                                                                              | A direct recognition, for something many people noticed                                        |
| In the squad channel, Sam thanked Jane by name for a quick answer; one reaction                   | Leave out                                                                                                     | A one-off thanks for a small thing                                                             |
| Sam (Jul), Alex (Aug) and Kim (Sep) each thanked Jane by name for help with the API               | One point, going well, every day: "Jane helps colleagues with the API, as Sam, Alex and Kim thanked them for" | Small each time, but a pattern, so the point says whose thanks                                 |
| In a thread Jane started about the release, Sam thanked the squad                                 | Leave out the thanks; Jane's post counts as any other                                                         | Praise addressed to the team isn't Jane's                                                      |
| Jane posted the release update (Jul), again (Aug, Sep), and each time people thanked the squad    | One point, going well: "Jane often shares the team's results, keeping others up to date"                      | The results are the team's, but sharing them is Jane's, and the replies show it reaches people |
| In a squad channel, Sam wrote that Jane's estimate was far off, again                             | Keep, to improve                                                                                              | Someone raises a problem with Jane's work                                                      |
| Jane said they'd be late for standup                                                              | Leave out                                                                                                     | Scheduling                                                                                     |
| Jane posted review requests for their pull requests (Jul); again, most days (Aug, Sep)            | Leave out                                                                                                     | The work itself, which the prep gathers from their tools                                       |
| Jane took the new service's design to the security team for review (Sep)                          | Keep, going well                                                                                              | Initiative across teams, on security                                                           |
