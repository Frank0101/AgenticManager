"""Writes a short output of the investigation, such as an exec summary, from
<investigation>/<format>.json.

    python3 make_summary.py --investigation <Topic>_<YY-MM-DD> --format <format>

Short outputs take whatever shape the question needs, so only their frame is
fixed here: the file <format>.md next to the report, the link to the full
report at its end, ledger links resolved as in the report, and the word limit
the user asked for, which is a maximum. The body is the agent's:

{
  "title": "Optional heading",
  "max_words": 100,
  "body": ["Markdown blocks: paragraphs, bullet lists, ## headings, tables..."]
}

max_words is left out when the user set no limit. Words are counted as in the
report, without link targets.

Prints one line of JSON: the file's path, its word count and whether the
output folder is temporary. Exits 1, writing nothing, if the body is invalid or
over the limit.
"""
import argparse
import json
import os
import re

from common import (FOLDER_NAME, LEDGER, REPORT_SUFFIX, investigation_dir, load_json,
                    topic_of, write_output_file)
from make_report import Content, Ledger, words

FORMAT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def build(content, report):
    """The short output's text and its word count."""
    data = content.data
    body = data.get("body")
    if not isinstance(body, list) or not body or not all(isinstance(p, str) and p.strip() for p in body):
        content.errors.append("body: needs a list of nonempty Markdown blocks")
        body = []
    # Any Markdown fits a short output; only the title's level is the script's.
    if any(re.search(r"^ {0,3}#\s", p, re.M) for p in body):
        content.errors.append("body: no # heading; set title instead (## and below are fine)")
    body = [content.links(p.strip(), "body") for p in body]
    count = sum(words(paragraph) for paragraph in body)
    limit = data.get("max_words")
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            content.errors.append("max_words: a positive whole number, or left out without a limit")
        elif count > limit:
            content.errors.append(f"body: {count} words, over the {limit} asked for")
    parts = []
    if data.get("title") is not None:
        parts.append("# " + content.text(data.get("title"), "title", inline=True))
    parts += body
    parts.append(f"Full report: [{report}]({report})")
    return "\n\n".join(parts) + "\n", count


def make_summary(relative, wanted):
    if not FORMAT.fullmatch(wanted):
        raise SystemExit(f"{wanted!r}: the format is a short lower-case label, such as exec-summary")
    folder, _, temporary = investigation_dir(relative)
    report = topic_of(folder) + REPORT_SUFFIX
    if not os.path.isfile(os.path.join(folder, report)):
        raise SystemExit(f"{report} is missing: a short output is made from the full report, so write it first")
    content = Content(load_json(os.path.join(folder, f"{wanted}.json")), Ledger(os.path.join(folder, LEDGER)))
    text, count = build(content, report)
    if content.errors:
        raise SystemExit(f"{wanted}.json has problems, so nothing was written:\n  - "
                         + "\n  - ".join(content.errors))
    path, _ = write_output_file(FOLDER_NAME, f"{relative}/{wanted}.md", text.encode("utf-8"))
    return {"path": path, "words": count, "temporary": temporary}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write a short output from <format>.json.")
    parser.add_argument("--investigation", required=True, help="<Topic>_<YY-MM-DD>")
    parser.add_argument("--format", required=True, help="exec-summary, slack-update or another short label")
    args = parser.parse_args(argv)
    print(json.dumps(make_summary(args.investigation, args.format)))


if __name__ == "__main__":
    main()
