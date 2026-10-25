"""Keeps a slide of a deck the user is happy with as an example for later
decks, exactly as it is, in _examples/<name>/ beside the decks.

The user's examples are their real slides, content included, kept in their own
output folder; the skill's built-in examples are layout-only wireframes. The
example's slides.json holds only that slide, with the deck's CSS and the charts
and rings it places, and its page is built as make_deck.py builds a deck, its
images still linked in _assets. A taken name gets the next number, so an
earlier example is never overwritten.
"""
import argparse
import json
import os

from common import (EXAMPLE_DESCRIPTION, EXAMPLE_PAGE, FOLDER_NAME, SLIDES, TOKEN, USE_FOR, KEPT_EXAMPLES, asset_names, credits,
                    deck_dir, description, free_name, read_json, slug, user_examples_dir, write_output_file)
from make_deck import build, problems


def save(deck, number, title, use_for):
    title, use_for = " ".join(title.split()), " ".join(use_for.split())
    if not title or not use_for:
        raise SystemExit("--title and --use-for must not be empty")
    content = one_slide(read_json(os.path.join(
        deck_dir(deck), SLIDES)), number, title)
    errors, texts = problems(content, asset_names())
    if errors:
        raise SystemExit("the slide has problems, so nothing was written; run make_deck.py on the deck "
                         "first:\n  - " + "\n  - ".join(errors))
    name = example_name(user_examples_dir(), title)
    files = {SLIDES: json.dumps(content, ensure_ascii=False, indent=2) + "\n",
             EXAMPLE_PAGE: build(content, texts, credits(), depth=2),
             EXAMPLE_DESCRIPTION: description(title, {USE_FOR: use_for}, f"The slide: [{SLIDES}]({SLIDES}), "
                                              f"shown in [{EXAMPLE_PAGE}]({EXAMPLE_PAGE}).")}
    paths, temporary = {}, False
    for file, text in files.items():
        paths[file], temporary = write_output_file(
            FOLDER_NAME, f"{KEPT_EXAMPLES}/{name}/{file}", text.encode("utf-8"))
    page = paths[EXAMPLE_PAGE]
    return {"example": name, "folder": os.path.dirname(page), "page": page, "temporary": temporary}


def one_slide(content, number, title):
    """The slides.json of slide `number` alone, titled `title`."""
    slides = content.get("slides", [])
    if not 1 <= number <= len(slides):
        raise SystemExit(
            f"--slide must be from 1 to {len(slides)}, the deck's slides")
    slide = slides[number - 1]
    placed = {(match[1], match[2])
              for match in TOKEN.finditer("\n".join(slide.get("html", [])))}
    return {"title": title, "style": content.get("style", []), "slides": [slide],
            "charts": {k: v for k, v in content.get("charts", {}).items() if ("chart", k) in placed},
            "rings": {k: v for k, v in content.get("rings", {}).items() if ("ring", k) in placed}}


def example_name(folder, title):
    """A name for the example from its title, not taken by another."""
    base = slug(title)
    if not base:
        raise SystemExit("--title must hold letters or digits")
    return free_name(base, lambda name: os.path.lexists(os.path.join(folder, name)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Keep a deck's slide as an example: writes _examples/<name>/ with its slides.json, "
        "its page, slide.html, and description.md, <name> coming from the title. Prints one line of "
        "JSON: the example's name, its folder, its page and whether the output folder is temporary.")
    parser.add_argument("--deck", required=True,
                        help="the deck's folder, <Name>_<YY-MM-DD>")
    parser.add_argument("--slide", required=True, type=int,
                        help="the slide's number, 1 for the first")
    parser.add_argument("--title", required=True,
                        help="the example's title, such as Quarter at a glance")
    parser.add_argument("--use-for", required=True,
                        help="what the slide is good for, in one line")
    args = parser.parse_args(argv)
    print(json.dumps(save(args.deck, args.slide, args.title, args.use_for)))


if __name__ == "__main__":
    main()
