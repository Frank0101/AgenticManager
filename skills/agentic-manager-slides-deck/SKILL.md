---
name: agentic-manager-slides-deck
description: Turns a conversation into an HTML slide deck - infers the kind of presentation (pitch, business review, townhall, report, roadmap, status update), asks a few qualifying questions one at a time, then builds a deck of fixed-size slides with zoom and PDF export, from a reference the user gives, from a library of described slide layouts or from a blank skeleton, and iterates on it with the user. Use when the user asks for slides, a deck or a presentation, or to change the deck built in the same conversation.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_deck.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/add_asset.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_deck.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/snap_deck.py *)
---

# Slide Deck

Turns a conversation into an HTML slide deck. You drive: work out the kind of presentation, choose where to start from, ask what's missing, write the slides, then iterate while the user reviews the deck in a browser.

The files go to the `slides-decks` folder of the config's `output.root`, or to a temporary folder if none is set. The scripts choose and write that folder; never choose one yourself, and never read the config.

You write only `slides.json`: the title, the CSS, each slide's HTML and the data of charts and rings. `make_deck.py` owns the rest, from the page around the slides to the check. When a script refuses something, its message says what to fix: fix the input, never work around the check.

A deck's folder holds only these files, and the check fails on any other; your own working files go in your scratch folder.

```text
slides-decks/
├── _assets/                         add_asset.py writes, the images every deck links to
│   └── acme-logo/
│       ├── image.svg
│       └── description.md           what it shows and, if downloaded, its credit
├── _examples/                       save_example.py writes, the slides the user kept
│   └── quarter-at-a-glance/
│       ├── description.md
│       ├── slides.json
│       └── slide.html
└── Acme-Q3-Review_26-10-12/
    ├── slides.json                  you write
    └── Acme-Q3-Review_Slides.html   make_deck.py writes
```

## Prerequisite

Run the config check, `python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py`, pre-approved in the frontmatter. If it fails, stop here and follow its `next_steps`. If `python3` is unavailable, tell the user AgenticManager needs Python 3.14+ as `python3`; if the script is missing, tell them to reinstall every skill.

This skill needs no source: its material is the conversation and any file the user gives you.

## 1. Understand the request

Drive the conversation: don't wait for the user to know what to ask for.

**The type.** Infer it from what the user says (pitch, business review, townhall, report, roadmap, status update and so on); don't present a list.

**The starting point.** Unless the user's message makes it clear, ask, in your own words: "Do you have an example to start from, or should I draw from my own? We can also start completely blank."

- **A reference from the user** (a PDF, an image or a file): replicate it as the only structural and visual guide, and don't consult the examples.
- **No reference:** draw from the examples `init_deck.py` lists (step 2), reading those whose use fits the deck:
  - A built-in one is a real slide kept as a `description.md` (layout, style, density) and a `wireframe.svg` at the deck's slide size, with the original's positions, shapes and colours (text as grey bars, headings as placeholder words, photos as labelled boxes), so you can take its measurements.
  - One of the user's is a slide of an earlier deck: `slides.json` holds its HTML, which you can reuse, and its CSS, reusable when its look is the deck's; `slide.html` shows it.

  Take layout, section structure, chart types and density from them, never the look (see [Consistency](#consistency)), and tell the user briefly which you use: "I'm basing the layout on the Market Segmentation example."

- **Blank:** a plain look and your own structure, without the examples: white background, dark text, the default sans-serif, and on each slide a title and a layout skeleton. The content is written as usual, with placeholders only for what is missing.

**Questions.** Ask one at a time, conversationally, and stop when you have enough for a coherent first draft; after a complete reference, ask only about what is missing or ambiguous. What to ask depends on the type:

| Type            | Key questions                                       |
| --------------- | --------------------------------------------------- |
| Pitch           | audience, stage, key message                        |
| Business review | teams or workstreams, data available, time period   |
| Townhall        | company size, key announcements, tone               |
| Report          | scope, key findings, audience (exec, team, board)   |
| Roadmap/status  | product or project, time horizon, RAG status needed |

**Content.** Infer it without asking: given text, you handle structure and layout only; given a topic, you write the copy; given loose ideas, you write a full draft with real content.

## 2. Start the deck

When you have enough, say "I have enough for a first draft. Generating now — we can iterate from there." Choose a short `<Name>`, capitalised words joined by hyphens (or the user's), and run the command below. Call every script by exactly the path this skill shows, so it runs without a permission prompt; a script's `--help` gives its commands and arguments:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/init_deck.py --name <Name>
```

It creates the deck's folder, replacing one of the same name and day, and prints its name (`deck`, the `<deck>` later steps pass) and the `slides_path` step 3 writes to, then lists the `examples` and the `assets` (images earlier decks added) with what each is for or shows. Run it once per deck, never to revise one. Every deck starts from scratch: never read or reuse another deck's folder; only `_assets` and `_examples` are shared.

## 3. Write slides.json

Decide the deck's look first (see [Consistency](#consistency)). Write the file, and every revision of it, through the shared writer at the `slides_path` from step 2, never with your own file tools:

```bash
python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py --name slides-decks --path '<slides_path>' <<'END_OF_FILE'
{
  "title": "Acme Q3 Review",
  "style": [
    ".title { font-size: 40px; font-weight: 800; }",
    ".slide.dark { background: #1d2433; color: #fff; }",
    ".panel { height: 380px; margin-top: 32px; }"
  ],
  "slides": [
    { "class": "dark", "html": ["<h1 class='title'>Acme Q3 Review</h1>", "<p>Platform team</p>"] },
    {
      "html": [
        "<h2 class='title'>Revenue</h2>",
        "<div class='panel'>{{chart:revenue}}</div>"
      ]
    }
  ],
  "charts": {
    "revenue": {
      "type": "bar",
      "data": { "labels": ["Q1", "Q2", "Q3"], "datasets": [{ "label": "Revenue", "data": [3, 5, 8] }] }
    }
  },
  "rings": {}
}
END_OF_FILE
```

### Consistency

Many examples make it easy to build a deck that looks like several. Keep it one:

- **One look, set before the first slide.** Define the palette, fonts and type sizes, margins, where titles sit and the frame (page number, footer, logo) once, at the top of `style`: colours and fonts as CSS variables in `:root`, shared parts as classes. Slides take their look from these, never from values of their own, and every content slide has the same frame; only the cover and section dividers may differ.
- **One source for the look, layout from the rest.** The look comes from the user's reference; otherwise from their kept example, when they want an earlier deck's look; otherwise from the one example you choose as the anchor for the deck's type and audience; on a blank start, from the blank style. Tell the user which. Every other example gives only its layout: keep its positions and proportions and redraw it in the deck's look, its main colour as the deck's main colour, its other colours as accents. If a layout doesn't survive the change, such as one needing a contrast the palette lacks, pick another rather than inventing a hybrid.
- **Graphics and colours keep a meaning.** A pictorial element stands for one idea: a road or timeline for a journey through steps, a funnel for narrowing stages, a pyramid for levels, a wheel for parts of a whole, an arrow for a direction or a cause. Use it only for content with that shape, never stretched, cut or repeated into something else, such as a road drawn as a bar in a chart: figures go in a chart or table, with plain marks. When the content lacks the shape, keep the example's arrangement without the element, or choose another example. Prefer giving each accent colour one meaning across the deck, such as a team or a status, over using it as decoration.
- **The same layout for slides of the same kind.** Once a kind of slide, such as a workstream's detail or a section divider, has a layout, every slide of that kind uses it at a similar density, and a change applies to all of them.
- **Try what fits.** When choosing a kind of slide's layout, don't fall back on the same few: use an example you haven't used when it fits well. When two layouts fit an important slide equally well, such as the one carrying the main message, build both, one after the other, for the user to choose; do this for a slide or two per draft, and delete the one they don't choose.

### The fields

- **`title`:** the deck's title, shown in the browser tab.
- **`style`:** the deck's CSS, as a list of lines. Each slide is a `.slide`, 1100×618 px, with a default padding of 48/56 px the deck may change; an absolutely positioned element is placed from the slide's edge, as in a wireframe. Never restyle `body`, `.slides-wrapper` or `.toolbar`: they are the page around the deck.
- **`slides`:** one object per slide, in order: `html`, its content as a list of lines, and optionally `class`, class names added to its `.slide`, such as `dark`. Write attributes in single quotes, so nothing needs escaping in JSON, and close every tag you open. A slide can't hold `<script>`, `<style>`, `<link>` or frames, or load a file by its path or URL.
- **`charts`:** each chart by id (lowercase words joined by hyphens), as a Chart.js configuration in plain JSON, so no functions: `type`, `data`, optionally `options`, and `format` for how its values read, such as `{"prefix": "£", "suffix": "m", "decimals": 1}` for £3.5m. Place it once, as `{{chart:<id>}}` inside an element with a set height, which it fills.
- **`rings`:** each donut or pie by id, drawn as SVG: `size` (the square's side in px), `outer` and `inner` radius (`inner` 0 makes a pie), `gap` (degrees between segments), `start` (degrees clockwise from 12 o'clock, default 0) and `segments`, each a `color` and optionally a `value` (default 1). Place it once, as `{{ring:<id>}}`, with its labels around it in HTML.

### What goes on a slide

- **Fit.** Every slide fits 1100×618: overflow is clipped, never scrolled. Prefer structure to decoration in a first draft.
- **Page numbers.** Write `{{page}}`, never the number, so adding or removing a slide renumbers the rest.
- **Text.** Write real content, with a placeholder only where information is genuinely missing, naming it in one of these forms: `[CHART: revenue by quarter, bar]`, `[IMAGE: team photo]`, `[DIAGRAM: onboarding flow]`, `[TABLE: KPI summary, 4 rows]` or `[PLACEHOLDER: description]`.
- **Charts and diagrams.** A chart is for real data: Chart.js 4.4.1 draws it, loaded from the internet when the deck opens. A diagram (a flow, a sequence, a hierarchy) is inline SVG in the deck's look. Anything else is HTML and CSS.
- **Images.** An image is `<img src='{{asset:<name>}}'>`. Reuse one from `assets` when it shows what the slide needs. An image the user gives (a logo, a screenshot, a photo) goes in `_assets` with `python3 ${CLAUDE_SKILL_DIR}/scripts/add_asset.py`; one only they can give, such as their team's photo, is an `[IMAGE: …]` placeholder until they do. Write what an image `shows` after looking at it, in one line on its subject, background and shape, so a later deck can tell whether it fits without opening it. An image in `assets` with nothing in `shows` was put there by hand: when its name suggests it may fit, look at it and describe it, whether or not you use it.
- **Drawings.** Icons, arrows, badges and diagrams belong to the design: inline SVG, for good. A picture of something anyone could photograph, such as the Earth, a car or a banana, is an SVG drawing wrapped in `<figure data-image='<what the real image should show>'>`, unless an image in `assets` already shows it: a stand-in, which step 7 can swap for a real image.
- **Depth.** Never use a blurred shadow, such as `box-shadow`: the PDF export draws it as a dark rectangle around the element, though the browser shows it fine. To lift a panel or an image off the slide, use solid shapes instead: a fill lighter or brighter than what's behind it, a 1px border in a lighter tone of the background or a coloured top edge, or a backing shape in a darker tone, offset a few pixels behind it with no blur.

## 4. Build, look and open

1. **Build.** `python3 ${CLAUDE_SKILL_DIR}/scripts/make_deck.py --deck <deck>` writes the deck and checks it. Fix `slides.json` and run it again until `ok` is true; never edit the deck itself.
2. **Look.** `python3 ${CLAUDE_SKILL_DIR}/scripts/snap_deck.py --deck <deck>` pictures the slides with headless Chrome. Look at its `sheet`, the whole deck in one image, opening a slide's own picture only where something looks wrong. Fix overflowing or clipped text, overlaps and fonts that don't render as intended, then build and look again. Without Chrome, skip this; never ask the user to install it.
3. **Open.** Build with `--open` to open the deck in the user's browser, on every build until it has `opened` once in the conversation and never after: the user refreshes the page already open.

## 5. Tell the user

Say the deck is ready (and open, if it `opened`), with a Markdown link to its full `path`, and that it opens in any browser, with zoom and PDF export on the toolbar. Don't recap the slides. Add only what applies:

- **Images:** they show only while the deck stays beside `_assets`, so share it as a PDF.
- **Downloaded images:** each one in `credits`, with its license and a link to its page, for the user to check before sharing.
- **Placeholders** still open, as what you need from them.
- **Doubts** about your own judgment that the deck doesn't show.
- **A temporary folder**, if `temporary` is true: setting `output.root` in the config keeps decks.

End with one question, the first that applies, so it isn't lost among the rest:

1. When slides were built in two versions, which of each pair to keep, naming the slides.
2. When the deck has `stand_ins`, whether to swap them for real images (step 7) once the draft is right.
3. Otherwise, whether to keep a slide as an example for future decks (step 8).

## 6. Iterate

The user gives feedback and refreshes the browser. Change only what they asked, through the writer as its `--help` shows, not by rewriting the whole file. Build again, and confirm what changed in one line.

## 7. Swap the stand-ins for real images (optional)

Only when the user asks, or says yes when the handover offers it: a deck with its drawings is finished as it is. Swap each stand-in in `stand_ins`, with tools that search and read web pages; without them, say the deck keeps its drawings until an agent that can browse swaps them.

For each, reuse an image in `assets` that shows what its `data-image` says, or find one wherever suits the topic. Repositories that state each image's license are a good start, such as Openverse, Wikimedia Commons, NASA's image library, Unsplash or Pexels; for a specialised subject look further, such as a manufacturer's press kit, a museum's open-access collection or a government archive.

- **License.** Use an image only if its own page states a license allowing reuse in a presentation, never one from search results whose page you haven't opened. Record the license and credit exactly as the page states them, never from memory: prefer structured data where a site has it, such as Wikimedia Commons' file information, and if your tool summarises pages, ask it to quote those lines word for word.
- **Fit.** Choose for fit, quality and the audience, keeping [Consistency](#consistency): the image shows what the drawing did, in its place and size. When the subject must be cut out, choose an image that already is, since the skill can't remove a background: a PNG with a transparent background, or a plain background CSS can hide (`mix-blend-mode: multiply` for white on a light slide, `screen` for black on a dark one, a round frame for a round subject).

Add it with `python3 ${CLAUDE_SKILL_DIR}/scripts/add_asset.py --url`, describing what you saw in it, and replace the whole `<figure>` with `<img src='{{asset:<name>}}'>`, cropped (`object-fit: cover`) to the drawing's box. Each slide credits its downloaded images at the bottom right: restyle `.asset-credit` when a slide needs it, such as a dark one, but never hide it. Then build and hand over as in steps 4 and 5.

## 8. Keep a slide as an example (optional)

Only when the user asks, or says yes when the handover offers it. Give the slide a short title and one line on what it is good for, such as "a quarter's results: four headline figures over a trend chart", and run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py --deck <deck> --slide <n> --title '<title>' --use-for '<what it is good for>'
```

It saves the slide as it is in `_examples`, where every later deck finds it. Give the user the link to its `page`.
