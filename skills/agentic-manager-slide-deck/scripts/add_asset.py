"""Puts an image into _assets, the images every deck shares, as a folder of
its own holding the image and its description, so a slide can show it as
{{asset:<name>}} and a later deck can find and reuse it: an image the user
gave, one downloaded from the internet with its credit, or a description for
an image already there.

    python3 add_asset.py --file <path> --title <title> --shows <what it shows> [--name <name>]
    python3 add_asset.py --url <image> --page <page> --license <license> --credit <credit> \
        --title <title> --shows <what it shows> [--name <name>]
    python3 add_asset.py --name <name> --title <title> --shows <what it shows>

<name> is the folder's name: lowercase words joined by hyphens, such as
acme-logo. Without --name it comes from the file's or the address's own name.
An image of the same name is replaced, folder and all: every deck that links
it shows the new one from then on. The image inside is always image.<type>,
so the name says what the image is and nothing else.

Every image has a description, since an agent can't tell what an image shows
from its name: a title, and one line on what it shows and how it looks. A
downloaded image's description also holds its credit line, its license, the
page that states the license and its own address, so every slide that shows
it credits it. Its type is read from its first bytes, not from the address,
so a page that isn't an image is refused rather than saved. An image the user
gave has no credit: it is theirs.

_assets is never deleted by a new deck, so an image added once serves every
later deck.

Prints one line of JSON: the image's `asset` name, its `path` and whether it
`replaced` one of the same name.
"""
import argparse
import json
import os
import shutil
import urllib.request
from urllib.parse import unquote, urlparse

from common import (ASSETS, EXAMPLE_DESCRIPTION, FOLDER_NAME, SLUG, asset_image, assets_dir, describe_asset,
                    read_asset, slug, ssl_context, write_output_file)

# Image hosts often refuse requests without one.
USER_AGENT = "AgenticManager-slide-deck/1.0 (an image for a slide deck)"
MAX_BYTES = 20 * 1024 * 1024
# An image's type by its first bytes; SVG is text, found by its root element.
SIGNATURES = [(b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"),
              (b"GIF89a", "gif")]


def add_asset(path, title, shows, name=None):
    """Copies the user's image at `path` into _assets as `name`, described by
    `title` and `shows`."""
    if not os.path.isfile(path):
        raise SystemExit(f"{path!r} is not a file")
    text = describe(title, shows)
    name = checked_name(name or slug(
        os.path.splitext(os.path.basename(path))[0]))
    with open(path, "rb") as f:
        data = f.read()
    kind = image_type(data)
    if not kind:
        raise SystemExit(
            f"{path!r} is not a PNG, JPEG, GIF, WebP or SVG image")
    return save(name, data, kind, text)


def add_download(url, page, license, credit, title, shows, name=None):
    """Downloads the image at `url` into _assets as `name`, described by
    `title` and `shows`, with the credit the page `page` states for it."""
    for flag, value in (("--url", url), ("--page", page)):
        if urlparse(value).scheme not in ("http", "https"):
            raise SystemExit(f"{flag} must be an http or https address")
    for flag, value in (("--license", license), ("--credit", credit)):
        if not value.strip():
            raise SystemExit(f"{flag} must say what the image's page states")
    text = describe(title, shows, {"credit": credit.strip(), "license": license.strip(),
                                   "source": page, "image": url})
    stem = os.path.splitext(os.path.basename(unquote(urlparse(url).path)))[0]
    name = checked_name(name or slug(stem) or "image")
    data = download(url)
    kind = image_type(data)
    if not kind:
        raise SystemExit(f"{url} is not a PNG, JPEG, GIF, WebP or SVG image: give the image's own "
                         "address, not the page that shows it")
    return save(name, data, kind, text)


def redescribe(name, title, shows):
    """Writes the description of the image `name` already in _assets, keeping
    its credit."""
    image = asset_image(name) if SLUG.fullmatch(name) else None
    if not image:
        raise SystemExit(
            f"_assets has no image {name!r}: add it with --file or --url")
    text = describe(title, shows, read_asset(name)["credit"])
    write_output_file(
        FOLDER_NAME, f"{ASSETS}/{name}/{EXAMPLE_DESCRIPTION}", text.encode("utf-8"))
    return {"asset": name, "path": os.path.join(assets_dir(), name, image), "replaced": False}


def describe(title, shows, credit=None):
    title, shows = " ".join(title.split()), " ".join(shows.split())
    if not title or not shows:
        raise SystemExit(
            "--title and --shows must say what the image is and what it shows")
    return describe_asset(title, shows, credit)


def save(name, data, kind, description):
    folder = os.path.join(assets_dir(), name)
    replaced = os.path.isdir(folder)
    if replaced:
        shutil.rmtree(folder)
    # The description goes through the shared writer; the image, not text, is
    # written beside it, in the folder the writer has just checked and made.
    write_output_file(
        FOLDER_NAME, f"{ASSETS}/{name}/{EXAMPLE_DESCRIPTION}", description.encode("utf-8"))
    path = os.path.join(folder, f"image.{kind}")
    with open(path, "wb") as f:
        f.write(data)
    return {"asset": name, "path": path, "replaced": replaced}


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            data = response.read(MAX_BYTES + 1)
    except OSError as error:
        raise SystemExit(f"couldn't download {url}: {error}")
    if len(data) > MAX_BYTES:
        raise SystemExit(
            f"{url} is over {MAX_BYTES // 1024 // 1024} MB: choose a smaller size of it")
    return data


def image_type(data):
    """The type of the image whose bytes are `data`, as an extension, or None
    if they aren't an image a deck shows."""
    for signature, kind in SIGNATURES:
        if data.startswith(signature):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if b"<svg" in data[:2048].lower():
        return "svg"
    return None


def checked_name(name):
    if not SLUG.fullmatch(name):
        raise SystemExit(f"{name!r} must be lowercase words joined by hyphens, such as acme-logo: "
                         "give another with --name")
    return name


EXAMPLES = """
add an image the user gave:
  python3 add_asset.py --file ~/Downloads/acme-logo.svg --title 'Acme logo' \\
    --shows 'the Acme logo, dark blue lettering on a transparent background, wide'

add an image from the internet, with what its page states:
  python3 add_asset.py --url 'https://example.org/files/earth.jpg' \\
    --page 'https://example.org/wiki/File:Earth.jpg' --license 'Public domain' \\
    --credit 'Example Agency' --title 'The Earth from space' \\
    --shows 'the whole Earth on a black background, a square photo' --name earth-from-space

describe an image already in _assets:
  python3 add_asset.py --name acme-logo --title 'Acme logo' --shows '...'
"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Put an image, with its description, into the decks' shared _assets folder.",
        epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", help="an image the user gave, to copy")
    source.add_argument(
        "--url", help="an image's own address on the internet, to download")
    parser.add_argument(
        "--page", help="with --url: the page that states the image's license")
    parser.add_argument(
        "--license", help="with --url: the license, as its page states it")
    parser.add_argument(
        "--credit", help="with --url: the credit line its page asks for, such as the author")
    parser.add_argument("--title", required=True,
                        help="a short title for the image")
    parser.add_argument("--shows", required=True,
                        help="one line on what the image shows and how it looks: subject, background, shape")
    parser.add_argument(
        "--name", help="its folder's name in _assets, such as acme-logo")
    args = parser.parse_args(argv)
    if (args.page or args.license or args.credit) and not args.url:
        parser.error("--page, --license and --credit go with --url")
    if args.file:
        result = add_asset(args.file, args.title, args.shows, args.name)
    elif args.url:
        if not (args.page and args.license and args.credit):
            parser.error("--url needs --page, --license and --credit")
        result = add_download(args.url, args.page, args.license, args.credit, args.title, args.shows,
                              args.name)
    elif args.name:
        result = redescribe(args.name, args.title, args.shows)
    else:
        parser.error(
            "give --file or --url to add an image, or --name to describe one already in _assets")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
