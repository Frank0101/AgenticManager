# Read a month of a person's Slack messages

A manager is preparing a performance review of the person named below. Read what the person wrote in Slack over one month, and what others wrote about them, and write a synopsis of each conversation, for another agent that won't see the messages and decides, across the whole period, what the review uses. Leave out only what is listed under "What to skip".

## What to read

Search Slack with its MCP's search across public and private channels, group DMs and DMs, with the filters under "The month", and read every page of each search until there is no next one:

- what the person sent: `from:` the person;
- what others wrote about them: messages that mention the person.

A search can stop before it has returned every message, such as at a limit on its pages: check that each one's results reach both ends of the month, and search the days one didn't reach again, in shorter ranges, such as a week, with the same filters, until every day of the month is covered.

When a message the person sent starts a thread, read the thread too.

## What to skip

- The direct messages between the manager and the person: the manager knows them already.
- A message that is only an acknowledgement or a reaction, such as "+1", "thanks" or "on it", with nothing else in its conversation.
- Posts by bots and apps, such as alerts and pull request notifications.

## Each synopsis

One synopsis for each conversation: a thread, or the messages in a row on one topic in a channel or a DM. Say:

- where: the channel, and its audience, judged by its name, its purpose and who replies, such as the person's team, a cross-team, leadership or product channel, or an incident, alert, on-call, security or reliability channel;
- what the person said or did, such as an update, a plan, an answer, a diagnosis or a fix;
- who it was for or helped, and what changed because of it, such as a new way of working, another team unblocked or a process improved, as far as the conversation says;
- how others responded, such as thanks, praise, follow-up questions or a problem raised with the person's work, and how the conversation ended.

## Links in a message

{{links}}

## Writing

{{synopsis}}

## Each item

For each conversation, write an item: `date`, the day it started, as YYYY-MM-DD; `link`, the link of the person's first message in it, or of the one that mentions them, from the search result; and `synopsis`.
