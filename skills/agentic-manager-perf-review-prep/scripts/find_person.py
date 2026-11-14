"""Looks a prep's person up in GitHub and the vault, read-only, and prints who they could be in each.

Who the person is in a source is the manager's to confirm, so the script lists
candidates and never chooses. A GitHub login can't be told from a name, so one
commit search by the email of the Jira account the manager confirmed finds
the accounts that authored its commits. The vault offers every page and link
with a word that starts a word of the manager's name for the person, or that
one starts, such as Al for Alan, and every alias such a page declares, as it
can differ. Notion and Slack are reached through their MCPs.
"""
import argparse
import json
import os
import subprocess

from common import (JIRA_SOURCE, PERSON, commit_authors, graph_path, links, name_words, notes,
                    page_aliases, prep_dir, profile_name, read_json, require_gh, stops_on_failure)

# The fewest letters a word of a link needs to be taken for a name, or a short
# form of one, such as Al for Alan.
SHORTEST = 2
OUTPUT = """Prints one line of JSON:
  person   the person's name, as the manager gave it
  email    the email of their Jira account, which the GitHub search used
  github   each GitHub account that authored commits with that email: login
           and name (as its profile gives it, or null)
  vault    each page or link of the vault with a word that starts a word of
           the name, or that one starts, such as Al for Alan, most
           mentioned first: link (as first written), mentions (how many times
           notes link it), page (whether it has a page of its own) and
           alias_of (the page that declares it as an alias, or null)
"""


def find(prep, run=subprocess.run):
    """{person, email, github, vault}: who the person of the prep `prep`
    could be in GitHub and the vault."""
    person = read_json(os.path.join(prep_dir(prep), PERSON))
    require_gh(run, "the person's GitHub account is found")
    email, name = person["sources"][JIRA_SOURCE]["email"], person["person"]
    return {"person": name, "email": email, "github": github_candidates(email, run),
            "vault": vault_candidates(graph_path(), name)}


def github_candidates(email, run=subprocess.run):
    """Each GitHub account that authored the commits a search by `email`
    found, with its profile's name."""
    return [{"login": login, "name": profile_name(login, run)}
            for login in commit_authors(f"author-email:{email}", run)]


def vault_candidates(path, person):
    """Each page or link of the graph at `path` that could name `person`, as
    could_name() tells, or that such a page declares as its alias, compared
    as Logseq does, whatever its case: how it was first written, how many
    times notes link it, whether it has a page and the page it is an alias
    of, most mentioned first."""
    words, found, aliases = name_words(person), {}, {}
    graph = list(notes(path))

    def entry(name):
        return found.setdefault(name.casefold(), {"link": name, "mentions": 0, "page": False,
                                                  "alias_of": aliases.get(name.casefold())})
    # The person's pages, by title, each with its aliases.
    pages = {title: page_aliases(text) for folder, title, text, _ in graph
             if folder == "pages" and could_name(title, words)}
    for title, names in pages.items():
        for alias in names:
            aliases.setdefault(alias.casefold(), title)
    for folder, title, text, _ in graph:
        if folder == "pages" and title in pages:
            entry(title)["page"] = True
            for alias in pages[title]:
                entry(alias)
        for link in links(text):
            if could_name(link, words) or link.casefold() in aliases:
                entry(link)["mentions"] += 1
    return sorted(found.values(), key=lambda entry: (-entry["mentions"], entry["link"].casefold()))


def could_name(link, words):
    """Whether the link or page title `link` could name a person whose name is
    `words`, as name_words() gives them: one of its words starts one of
    theirs, or one of theirs starts it, such as Al and Alan, each of at
    least SHORTEST letters, so a lone initial matches nothing."""
    return any(len(a) >= SHORTEST and len(b) >= SHORTEST and (a.startswith(b) or b.startswith(a))
               for a in name_words(link) for b in words)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Look the prep's person up in GitHub and the vault, and print who they could be in each. "
        "Notion and Slack aren't searched: search them through their MCPs.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    with stops_on_failure():
        print(json.dumps(find(args.prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
