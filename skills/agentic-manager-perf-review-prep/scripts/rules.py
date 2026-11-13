"""Prints the rules a prep's summaries follow: their parts, the company's values and ratings, and how to write a point.

The values and ratings are read from the config here, so the agent learns
them from what this prints rather than from the config; they hold no
secrets. How to write a point and pick its values is the protocol's, the
text the subagents' tasks hold too, so the agent and they follow one rule,
with the same examples. One command serves every step that summarises, so
every step's points name the same values.
"""
import argparse
import json

from common import PROTOCOL, RATINGS, SUMMARY_PARTS, VALUED_PARTS, VALUES, company_setting, fill_protocol, prep_dir

OUTPUT = """Prints one line of JSON:
  parts          each part of a summary, with what it holds
  valued_parts   the parts whose points each name the company values they show or call for
  values         the company's values: value and meaning
  ratings        the company's ratings, lowest first: rating and meaning
  rules          how to write a point and pick its values, with examples
"""


def rules(prep):
    """{parts, valued_parts, values, ratings, rules}: what the summaries of
    the prep `prep` follow."""
    prep_dir(prep)  # exits if the prep isn't there
    return {"parts": SUMMARY_PARTS, "valued_parts": list(VALUED_PARTS), "values": company_setting(VALUES),
            "ratings": company_setting(RATINGS), "rules": fill_protocol(PROTOCOL, "summary")}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print the rules the prep's summaries follow: their parts, the company's values and ratings, and how to "
        "write a point.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    print(json.dumps(rules(parser.parse_args(argv).prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
