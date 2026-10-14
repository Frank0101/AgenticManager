"""Copies an image the user gave into _assets, the folder of images every deck
shares, so a slide can show it as {{asset:<name>}}.

    python3 add_asset.py --file <path> [--name <name>]

<name> is the file's name in _assets: lowercase words joined by hyphens and
the image's type, such as acme-logo.svg. Without --name it comes from the
file's own name, lowercased with anything else turned into hyphens. An image
of the same name is replaced: the user gave a newer one, and every deck that
links it shows the new one from then on.

_assets is never deleted by a new deck, so an image added once serves every
later deck.

Prints one line of JSON: the image's `asset` name, its `path` and whether it
`replaced` one of the same name.
"""
import argparse
import json
import os
import shutil

from common import ASSET_NAME, IMAGE_TYPES, assets_dir, slug


def add_asset(path, name=None):
    if not os.path.isfile(path):
        raise SystemExit(f"{path!r} is not a file")
    name = name or asset_name(path)
    if not ASSET_NAME.fullmatch(name):
        raise SystemExit(f"{name!r} must be lowercase words joined by hyphens, then ."
                         + ", .".join(IMAGE_TYPES[:-1]) + f" or .{IMAGE_TYPES[-1]}, such as acme-logo.svg: "
                         "give another with --name")
    folder = assets_dir()
    destination = os.path.join(folder, name)
    replaced = os.path.lexists(destination)
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(path, destination)
    return {"asset": name, "path": destination, "replaced": replaced}


def asset_name(path):
    """The name in _assets an image at `path` gets by default."""
    stem, extension = os.path.splitext(os.path.basename(path))
    return slug(stem) + extension.lower()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Copy an image into the decks' shared _assets folder.")
    parser.add_argument("--file", required=True, help="the image to copy")
    parser.add_argument(
        "--name", help="its name in _assets, such as acme-logo.svg")
    args = parser.parse_args(argv)
    print(json.dumps(add_asset(args.file, args.name)))


if __name__ == "__main__":
    main()
