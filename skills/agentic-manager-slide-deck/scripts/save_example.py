"""Keeps a slide of a deck the user is happy with as an example for later
decks, exactly as it is.

    python3 save_example.py --deck <Name>_<YY-MM-DD> --slide <n> --title "<title>" --use-for "<what it is good for>"

Writes the example's folder, _examples/<name>/, beside the decks: slides.json,
holding only that slide (1 for the first) with the deck's CSS and the charts
and rings it places; slide.html, its page, built as make_deck.py builds a
deck; and description.md, which the example list reads, with the title and
what it is good for, which the agent writes. <name> comes from the title, with
-2, -3... when it is taken, never overwriting an earlier example. Its images
stay in _assets, which the page links as a deck does.

The user's examples are their real slides, content included, kept in their own
output folder; the skill's built-in examples are layout-only wireframes.

Prints one line of JSON: the example's name, its folder, its page and whether
the output folder is temporary.
"""
import argparse
import json
import os

from common import (EXAMPLE_DESCRIPTION, EXAMPLE_PAGE, FOLDER_NAME, SLIDES, TOKEN, USER_EXAMPLES, asset_names, credits,
                    deck_dir, free_name, read_json, slug, user_examples_dir, write_output_file)
from make_deck import build, problems


def save(deck, number, title, use_for):
    title, use_for = " ".join(title.split()), " ".join(use_for.split())
    if not title or not use_for:
        raise SystemExit("--title and --use-for must not be empty")
    content = one_slide(read_json(os.path.join(
        deck_dir(deck), SLIDES)), number, title)
    errors, texts, mermaid = problems(content, asset_names())
    if errors:
        raise SystemExit("the slide has problems, so nothing was written; run make_deck.py on the deck "
                         "first:\n  - " + "\n  - ".join(errors))
    name = example_name(user_examples_dir(), title)
    files = {SLIDES: json.dumps(content, ensure_ascii=False, indent=2) + "\n",
             EXAMPLE_PAGE: build(content, texts, mermaid, credits(), depth=2),
             EXAMPLE_DESCRIPTION: f"# {title}\n\n**Use for:** {use_for}\n\nThe slide: [{SLIDES}]({SLIDES}), "
             f"shown in [{EXAMPLE_PAGE}]({EXAMPLE_PAGE}).\n"}
    paths, temporary = {}, False
    for file, text in files.items():
        paths[file], temporary = write_output_file(
            FOLDER_NAME, f"{USER_EXAMPLES}/{name}/{file}", text.encode("utf-8"))
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
        description="Keep a deck's slide as an example.")
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
