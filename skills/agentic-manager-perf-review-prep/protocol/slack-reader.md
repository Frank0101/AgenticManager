# Read a month of a person's Slack messages

A manager is preparing a performance review of the person named below. Read what the person wrote in Slack over one month, and what others wrote about them, and list every conversation, for another agent that sees all the months and alone decides what the review uses. You can't see the other months, so be inclusive: list every conversation that could be part of a pattern, even a small one, such as a thanks, a quick help, a missed update or a disagreement, and skip only what is listed under "What to skip". Whether it matters, and whether it is a pattern, isn't yours to decide: describe, don't judge.

## What to read

Search Slack's public channels only, with `slack_search_public`, never `slack_search_public_and_private`, with the filters under "The month", and read every page of each search until there is no next one:

- what the person sent: `from:` the person;
- what others wrote about them: messages that mention the person.

A busy month can still mean many pages: read them all, never sample and never stop at the newest page, and a page of results from one day only means the rest of the month is still to read. A search can stop before it has returned every message, such as at a limit on its pages: check that each one's results reach both ends of the month, and search the days one didn't reach again, in shorter ranges, such as a week, with the same filters, until every day is covered.

A thread means there is more to the conversation than its first message, so never assume it doesn't matter, or that the search results already show it: read every thread that has replies to the end, with `slack_read_thread`, yourself and not through other agents, whoever started it. The end is often where the conversation's outcome is, even when what you see seems clear.

Declare in `searched` every range of days you searched, one entry for each range of each of the two searches, with the pages you read: for each search, together they cover every day of the month.

## What to skip

- A message that is only an acknowledgement or a reaction, such as "+1", "thanks" or "on it", with nothing else in its conversation.
- Posts by bots and apps, such as alerts and pull request notifications.
- Routine chatter, such as scheduling or status, with nothing of the person's in it.
- Conversations that are purely social or personal, with nothing of the work in them, such as hobbies, office logistics, food, health or celebrations: not even as a neutral line, as they say nothing about the review.

## Each item

List in `items` one for each conversation, a thread or the messages in a row on one topic in a channel: its `date`, the day, within this month, of the message you found in it, the person's or the one that mentions them, as YYYY-MM-DD, not the day its thread started; its `link`, the link of the person's first message in it, or of the one that mentions them, copied exactly as the search result or the thread gives it, never built from the channel and the timestamp: a reply's link carries its `thread_ts`, without which Slack opens the thread's first message instead; and its `description`, up to {{description_words}} words, fewer when the conversation is simple, of that message or thread only, never of something another message says. It starts from who opened the conversation and what they raised, then gives each person's part, so no one is credited with what another did. It says where, in which channel and for what audience, who it was for or helped, what the person said or did, how others responded and how the conversation ended: whether the people it affected said they had not been informed or involved, and who clarified, stopped or closed it. When others raise doubts, objections or questions, it says what they were and how the person answered, in particular if the person says someone was not told, asked or involved beforehand: the judge sees only these lines, and what was said is what it weighs. The person's own message with no reply is listed only if it is itself a request, a question or an announcement that could be part of a pattern, never one that is vague or trivial on its own.

{{people}}

## Links

{{reading}}

## Examples

| Conversation                                                                                                                                                                            | Decision                                                                                                                                                                       | Why                                                                                      |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| In the incident channel, Jane gave the root cause of a failed deploy and Sam thanked Jane                                                                                               | List: "In the incident channel, Jane explained a failed deploy's root cause to the engineers affected; Sam thanked Jane and the thread ended there"                            | What Jane did, who it helped, how it was received and how it ended                       |
| In the squad channel, Sam thanked Jane for a quick answer                                                                                                                               | List, as it is                                                                                                                                                                 | Small, but only the judge sees whether it repeats                                        |
| In a cross-team channel, Jane announced a change to the release process; Sam and Kim wrote they had not been told; Alex, the team lead, paused the change until the squads discussed it | List: "In a cross-team channel, Jane announced a release process change for the squads; Sam and Kim said they had not been told; Alex paused it until the squads discussed it" | The ending says who was not informed and who stopped it: the judge decides what it means |
| In the squad channel, Sam wrote that the squad had to chase Jane for the rollout status; Jane answered that the status was in the tracker                                               | List: "In the squad channel, Sam wrote the squad had to chase Jane for the rollout status; Jane answered that it was in the tracker"                                           | Someone raises a problem: what was said and how Jane answered, as it is                  |
| Jane asked in the squad channel who could review the migration plan this week; no reply                                                                                                 | List: "In the squad channel, Jane asked who could review the migration plan this week; no one replied"                                                                         | Jane's own request, which could be part of a pattern                                     |
| Jane wrote "anyone around?" in a channel, with no reply                                                                                                                                 | Skip                                                                                                                                                                           | Vague and trivial on its own                                                             |
| Jane wrote "on it" under a request, with nothing else; a pull request notification posted by a bot; a thread about where to eat on Friday                                               | Skip all                                                                                                                                                                       | A bare acknowledgement; a post by a bot; social, with nothing of the work                |
