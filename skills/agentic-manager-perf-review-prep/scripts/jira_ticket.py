"""Reads one Jira ticket a note or a message links to: its summary, status, assignee, description and comments, as plain text.

A note or a message that points at a ticket is judged by what the ticket
says, so this prints what a reader needs to understand it, nothing more. Jira
is reached through the jira-api source, whose token a subagent never sees. A ticket Jira
has none of, or of a project the user excludes, is answered with why.
"""
import argparse

from common import JiraClient, plain_text, stops_on_failure

FIELDS = ["summary", "status", "assignee", "description"]


def ticket_text(client, key):
    """The ticket `key` as plain text: its summary, status, assignee,
    description and comments, each with its author and day; or why it can't
    be read."""
    issue, why = client.issue(key, FIELDS)
    if issue is None:
        return why
    fields = issue["fields"]
    lines = [f"{issue['key']}: {fields.get('summary') or ''}",
             f"Status: {(fields.get('status') or {}).get('name', '')}",
             f"Assignee: {(fields.get('assignee') or {}).get('displayName', 'none')}",
             "", "Description:", plain_text(fields.get("description")) or "none"]
    for comment in client.comments(issue["key"]):
        lines += ["", f"Comment by {(comment.get('author') or {}).get('displayName', 'someone')}, "
                  f"{str(comment.get('created', ''))[:10]}:", plain_text(comment.get("body"))]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print one Jira ticket a note or a message links to, as plain text: its summary, status, assignee, "
        "description and comments.")
    parser.add_argument("--key", required=True,
                        help="the ticket's key, such as PROJ-123")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(ticket_text(JiraClient(), args.key))


if __name__ == "__main__":
    main()
