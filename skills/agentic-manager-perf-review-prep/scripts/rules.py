"""Prints the rules a prep's summaries follow: their parts, the company's values and how to write a point.

The values are read from the config here, so the agent learns them from
what this prints rather than from the config; they hold no secrets. How to
write a point and pick its values is the protocol's, feedback.md, which
holds the same shared part the subagents' tasks do, so the agent and they
follow one rule, with the same examples. One command serves every step that
summarises, so every step's points name the same values.
"""
import argparse
import json

from common import POINT_LIMITS, PROTOCOL, SUMMARY_PARTS, VALUED_PARTS, VALUES, company_setting, fill_protocol

OUTPUT = """Prints one line of JSON:
  parts          each part of a summary, with what it holds
  valued_parts   the parts whose points each name the company values they show or call for
  values         the company's values: value and meaning
  rules          how to write a point and pick its values, with examples
"""


def rules():
    """{parts, valued_parts, values, rules}: what a prep's summaries follow."""
    return {"parts": SUMMARY_PARTS, "valued_parts": list(VALUED_PARTS), "values": company_setting(VALUES),
            "rules": fill_protocol(PROTOCOL, "feedback", POINT_LIMITS)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print the rules the prep's summaries follow: their parts, the company's values and how to "
        "write a point.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)
    print(json.dumps(rules(), ensure_ascii=False))


if __name__ == "__main__":
    main()
