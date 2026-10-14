# Built-in examples

The skill's built-in examples are real slides kept for their layout, never their content, since everyone who installs the skill gets them. Each is a folder of two files, and the list the skill shows is read from them, so adding an example is adding its folder, and removing one is deleting it:

- `description.md`: a `# Title`, then `**Use for:**` (what the slide is good for, in one line), `**Layout.**`, `**Style.**` and `**Density.**`, in that order, and last the wireframe's image link, `![Layout of the slide](wireframe.svg)`.
- `wireframe.svg`, drawn at 1100×618 with the original's positions, shapes and colours: a line of text is a grey bar, a heading a short placeholder word, and a photo or illustration a labelled box. No real names, figures or text.

To make one from a slide, build it with the skill first (give it the slide's image as a reference), then ask the agent to write its description and wireframe from the deck's slide into a new folder here, layout only. Open the wireframe in a browser next to the original to check it, then run `python3 tests/run.py agentic-manager-slide-deck`, which checks every example's parts.

A name here that starts with `_`, like this file's, is a note, not an example.
