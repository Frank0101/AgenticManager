"""Prints the rules a prep's summaries follow: their parts, the company's values and ratings, and the first day previous feedback may end on.

The values and ratings are read from the config here, so the agent learns
them from what this prints rather than from the config; they hold no
secrets. One command serves every step that summarises, so each links points
to the same values.
"""
import argparse
import json
import os

from common import (RATINGS, REQUEST, SUMMARY_PARTS, VALUED_PARTS, VALUES, company_setting, earliest_feedback_end,
                    prep_dir, read_json)

OUTPUT = """Prints one line of JSON:
  parts          each part of a summary, with what it holds
  valued_parts   the parts whose points each name the company values they show
  values         the company's values: value and meaning
  ratings        the company's ratings, lowest first: rating and meaning
  earliest_end   the first day dated previous feedback may end on,
                 YYYY-MM-DD, 2 years before the period starts: older feedback
                 is left out, and undated feedback is never checked
"""


def rules(prep):
    """{parts, valued_parts, values, ratings, earliest_end}: what the
    summaries of the prep `prep` follow."""
    request = read_json(os.path.join(prep_dir(prep), REQUEST))
    return {"parts": SUMMARY_PARTS, "valued_parts": list(VALUED_PARTS), "values": company_setting(VALUES),
            "ratings": company_setting(RATINGS), "earliest_end": earliest_feedback_end(request).isoformat()}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print the rules the prep's summaries follow: their parts, the company's values and ratings, "
        "and the first day previous feedback may end on.",
        epilog=OUTPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    print(json.dumps(rules(parser.parse_args(argv).prep), ensure_ascii=False))


if __name__ == "__main__":
    main()
