"""Print one chunk of a ticket's or an epic's description, from data.json.

The brief gives each description as its first chunk, and says how many there
are when there are more. Reading the others costs tokens only when the agent
asks, so its reading stays bounded and nothing is cut off. common.chunks cuts
the pieces, as it does for the brief.
"""
import argparse
import os

from common import DATA_FILE, chunks, read_json


def descriptions(data):
    """{key: description} of the tickets and the epics."""
    found = {s["key"]: s["description"] for s in data["spells"]}
    found.update({e["key"]: e["description"] for e in data["epics"]})
    return found


def main():
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--report-dir", required=True,
                        help="report folder holding data.json")
    parser.add_argument("--key", required=True, help="a ticket or epic key")
    parser.add_argument("--chunk", type=int, default=1,
                        help="which chunk, from 1")
    args = parser.parse_args()
    found = descriptions(read_json(os.path.join(args.report_dir, DATA_FILE)))
    if args.key not in found:
        raise SystemExit(f"no ticket or epic {args.key} in the report")
    pieces = chunks(found[args.key])
    if not 1 <= args.chunk <= len(pieces):
        raise SystemExit(
            f"{args.key} has {len(pieces)} chunk(s); --chunk is 1 to {len(pieces)}")
    print(
        f"{args.key}, chunk {args.chunk} of {len(pieces)}\n\n{pieces[args.chunk - 1]}")


if __name__ == "__main__":
    main()
