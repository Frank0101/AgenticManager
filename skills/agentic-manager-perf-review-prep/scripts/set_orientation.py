"""Records the summary of the manager's overall view of a prep's person in orientation.json.

The agent writes the summary as JSON on stdin, a quoted here-document, so
nothing in it needs escaping. It is checked before anything is written, by
the rule the final check applies, and written whole each time, so a
correction from the manager is one more call.
"""
import argparse
import json

from common import ORIENTATION, SUMMARY_PARTS, orientation_problems, prep_dir, stdin_json, write_prep_file

INPUT = """Input, on stdin: the manager's view, summarised in its parts, such as:

  python3 set_orientation.py --prep Jane-Doe_26-11-10 <<'END_OF_INPUT'
  {
    "going_well": ["Has led the billing migration well since May"],
    "to_improve": ["Could share progress with the wider team more often"],
    "context": ["Came back from a long leave in May"]
  }
  END_OF_INPUT

""" + "\n".join(f"  {part:<11} {meaning}" for part, meaning in SUMMARY_PARTS.items()) + """

Each part is a list of points, [] when the manager said nothing of it.

Prints one line of JSON: path, the file written, and orientation.
"""


def set_orientation(prep, orientation):
    """Write the summary `orientation` to the prep `prep`'s orientation.json,
    after checking it; returns the file's path. Exits, writing nothing, with
    every problem."""
    prep_dir(prep)  # exits if the prep isn't there
    if problems := orientation_problems(orientation):
        raise SystemExit("; ".join(problems) + "\n\n" + INPUT)
    return write_prep_file(prep, ORIENTATION, orientation)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the summary of the manager's overall view of the prep's person.",
        epilog=INPUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prep", required=True,
                        help="the prep's folder, <Person>_<YY-MM-DD>, as init_prep.py printed it")
    args = parser.parse_args(argv)
    orientation = stdin_json(INPUT)
    path = set_orientation(args.prep, orientation)
    print(json.dumps(
        {"path": path, "orientation": orientation}, ensure_ascii=False))


if __name__ == "__main__":
    main()
