# Read a month of a person's Slack messages

A manager is preparing a performance review of the person named below. Read what the person wrote in Slack over one month, and what others wrote about them, and write a synopsis of each conversation, for another agent that won't see the messages and decides, across the whole period, what the review uses. Leave out only what is listed under "What to skip".

## What to read

Search Slack's public channels only, with `slack_search_public`, never `slack_search_public_and_private`, with the filters under "The month", and read every page of each search until there is no next one:

- what the person sent: `from:` the person;
- what others wrote about them: messages that mention the person.

A search can stop before it has returned every message, such as at a limit on its pages: check that each one's results reach both ends of the month, and search the days one didn't reach again, in shorter ranges, such as a week, with the same filters, until every day of the month is covered.

When a message the person sent starts a thread, read the thread too.

## What to skip

- A message that is only an acknowledgement or a reaction, such as "+1", "thanks" or "on it", with nothing else in its conversation.
- Posts by bots and apps, such as alerts and pull request notifications.

## Each synopsis

One synopsis for each conversation: a thread, or the messages in a row on one topic in a channel. Say:

- where: the channel, and its audience, judged by its name, its purpose and who replies, such as the person's team, a cross-team, leadership or product channel, or an incident, alert, on-call, security or reliability channel;
- what the person said or did, such as an update, a plan, an answer, a diagnosis or a fix;
- who it was for or helped, and what changed because of it, such as a new way of working, another team unblocked or a process improved, as far as the conversation says;
- how others responded, such as thanks, praise, follow-up questions or a problem raised with the person's work, and how many people reacted to the person's messages, from the search result or, when it doesn't show them, the message's reactions; and how the conversation ended.

## Examples

| Conversation                                                                                                       | Synopsis                                                                                                    | Why                                                            |
| ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| In the squad channel, Sam asked why the deploy failed; Jane replied with the cause and a fix, and Sam thanked Jane | In the squad channel, Jane diagnosed Sam's failed deploy and gave the fix; Sam thanked Jane                 | What Jane did, who it helped and how it was received           |
| A long thread in a cross-team channel about the release date, where Jane replied once to confirm the API was ready | In a cross-team release thread, Jane confirmed the API was ready                                            | In a long thread, only what Jane did                           |
| In the incident channel, Alex wrote "thanks to Jane for the quick rollback last night", and 12 people reacted      | In the incident channel, Alex thanked Jane by name for a quick rollback the night before; 12 people reacted | Others' words about Jane count, with how many reacted          |
| Jane posted the weekly migration update in a cross-team channel; nobody replied, 5 reactions                       | In a cross-team channel, Jane posted the weekly migration update; no replies, 5 reactions                   | A post with no replies still gets its synopsis                 |
| Jane asked in the squad channel who could cover standup on Friday                                                  | Jane asked the squad who could cover Friday's standup                                                       | Described as it is: whether it matters is the merge's to judge |

## Links and writing

{{reading}}

## Each item

For each conversation, write an item: `date`, the day it started, as YYYY-MM-DD; `link`, the link of the person's first message in it, or of the one that mentions them, copied exactly as the search result or the thread gives it, never built from the channel and the timestamp: a reply's link carries its `thread_ts`, without which Slack opens the thread's first message instead; and `synopsis`.
