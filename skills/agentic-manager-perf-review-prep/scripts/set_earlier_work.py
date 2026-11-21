"""Records the work a prep's person did before the period, as the previous feedback says it, in its earlier_work_content.json, which the report lists at the end of its work and impact.

It is a reminder for a review that looks back over the whole year, so it
cites nothing, and is checked only for its shape and length and that it
names no id, by the rule
the final check applies, before anything is written. It is null when there
is no previous feedback, which prepare_report.py records with no agent. It
is written whole each time, so a correction is one more call with every
bullet.
"""
import argparse
import json
import os

from common import (DATA, EARLIER_WORK_CONTENT, MAX_EARLIER_BULLETS, WORDS, earlier_work_content_problems,
                    prep_dir, read_json, stdin_json, write_prep_file)

INPUT = f"""Input, on stdin: the work before the period, such as:

  python3 set_earlier_work.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {{"bullets": ["Built the first version of the billing service, which the previous feedback credited for a smooth launch."]}}
  END_OF_INPUT

  bullets   one to {MAX_EARLIER_BULLETS}, each a sentence of about {WORDS["earlier_work"]} words on what the
            person worked on before the period and with what result, as the
            previous feedback says it, naming no id

Prints one line of JSON: path, {EARLIER_WORK_CONTENT}'s path."""


def set_earlier_work(prep, value):
    """Write `value`, the work before the period, or null with no previous
    feedback, to the prep `prep`'s earlier_work_content.json, after checking
    it against its data.json; returns the file's path. Exits, writing
    nothing, with every problem and the input."""
    data = read_json(os.path.join(prep_dir(prep), DATA))
    if problems := earlier_work_content_problems(value, data):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, EARLIER_WORK_CONTENT, value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the work before the period, from the previous feedback, in the prep's "
        "earlier_work_content.json.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    value = stdin_json(INPUT)
    print(json.dumps({"path": set_earlier_work(
        args.prep, value)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
