"""Looks a prep's person up in Jira, GitHub and the vault, read-only, and prints who they could be in each, and how each was found.

Who the person is in a source is the manager's to confirm, so the script lists
candidates and never chooses. Jira comes first, as its accounts often show the
work email. A GitHub login can't be told from a name, so commits are searched,
only in the organisations the user's gh belongs to, by each email Jira shows
and by the full name. The vault offers every page and link with a word that
starts a word of the name, or that one starts, so a short name, such as Al for
Alan, is offered too. Notion and Slack are reached through their MCPs.
"""
import argparse
import json
import os
import subprocess

from common import (REQUEST, JiraClient, as_name, commit_authors, gh_available, gh_orgs, gh_signed_in, graph_path,
                    links, notes, prep_dir, profile_name, read_json, stops_on_failure)

# The fewest letters a word of a link needs to be taken for a name, or a short
# form of one, such as Al for Alan.
SHORTEST = 2
OUTPUT = """Prints one line of JSON:
  person   the person's name, as the request holds it
  jira     each Jira account found by their name, or by each word of it when
           the full name finds none: accountId, displayName, emailAddress
           (null when the site hides it) and active
  github   each GitHub account whose commits a search found, those found by
           an email first: login, name (as its profile gives it, or null) and
           found_by, the searches that found it, such as
           author-email:jane@acme.test
  vault    each page or link of the vault with a word that starts a word of
           the name, or that one starts, such as Al for Alan, most
           mentioned first: link (as first written), mentions (how many times
           notes link it) and page (whether it has a page of its own)
"""


def find(prep, client=None, run=subprocess.run):
    """{person, jira, github, vault}: who the person of the prep `prep` could
    be in each source."""
    person = read_json(os.path.join(prep_dir(prep), REQUEST))["person"]
    if not gh_available():
        raise SystemExit("gh isn't installed or the github-cli source isn't enabled: the person's GitHub account "
                         "is found with it")
    if not gh_signed_in(run):
        raise SystemExit(
            "gh isn't signed in: run gh auth login, then run this again")
    jira = jira_candidates(client or JiraClient(), person)
    emails = [user["emailAddress"] for user in jira if user["emailAddress"]]
    return {"person": person, "jira": jira, "github": github_candidates(person, emails, run),
            "vault": vault_candidates(graph_path(), person)}


def jira_candidates(client, person):
    """The Jira accounts found for `person`'s full name or, when it finds none,
    for each word of it, each account once, in the order found."""
    found = client.users(person)
    if not found:
        found = [user for word in name_words(person)
                 for user in client.users(word)]
    return list({user["accountId"]: user for user in found}.values())


def github_candidates(person, emails, run=subprocess.run):
    """Each GitHub account whose commits, in the organisations gh belongs to,
    a search by each of `emails` or by `person`'s full name found, with its
    profile's name and how it was found, those found by an email first, as an
    email is surer than a name."""
    searches = [f"author-email:{email}" for email in emails]
    searches.append(f'author-name:"{person.replace(chr(34), "")}"')
    found = {}
    for org in gh_orgs(run):
        for search in searches:
            for login in commit_authors(f"{search} org:{org}", run):
                entry = found.setdefault(
                    login, {"login": login, "found_by": []})
                if search not in entry["found_by"]:
                    entry["found_by"].append(search)
    for entry in found.values():
        entry["name"] = profile_name(entry["login"], run)
    return sorted(found.values(), key=lambda entry: (not entry["found_by"][0].startswith("author-email:"),
                                                     entry["login"].casefold()))


def vault_candidates(path, person):
    """Each page or link of the graph at `path` that could name `person`, as
    could_name() tells, compared as Logseq does, whatever its case: how it was
    first written, how many times notes link it and whether it has a page,
    most mentioned first."""
    words = name_words(person)
    found = {}

    def entry(name):
        return found.setdefault(name.casefold(), {"link": name, "mentions": 0, "page": False})
    for folder, title, text in notes(path):
        if folder == "pages" and could_name(title, words):
            entry(title)["page"] = True
        for link in links(text):
            if could_name(link, words):
                entry(link)["mentions"] += 1
    return sorted(found.values(), key=lambda entry: (-entry["mentions"], entry["link"].casefold()))


def could_name(link, words):
    """Whether the link or page title `link` could name a person whose name is
    `words`, as name_words() gives them: one of its words starts one of
    theirs, or one of theirs starts it, such as Al and Alan, each of at
    least SHORTEST letters, so a lone initial matches nothing."""
    return any(len(a) >= SHORTEST and len(b) >= SHORTEST and (a.startswith(b) or b.startswith(a))
               for a in name_words(link) for b in words)


def name_words(text):
    """The words of a name, accents dropped and case folded, so José and jose
    are one word."""
    return [word for word in as_name(text).casefold().split("-") if word]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Look the prep's person up in Jira, GitHub and the vault, and print who they could be in "
        "each. Notion and Slack aren't searched: search them through their MCPs.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps(find(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
