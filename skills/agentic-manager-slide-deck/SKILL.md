---
name: agentic-manager-slide-deck
description: Turns a conversation into an HTML slide deck - infers the kind of presentation (pitch, business review, townhall, report, roadmap, status update), asks a few qualifying questions one at a time, then builds a deck of fixed-size slides with zoom and PDF export, from a reference the user gives, from a library of described slide layouts or from a blank skeleton, and iterates on it with the user. Use when the user asks for slides, a deck or a presentation, or to change the deck built in the same conversation.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/check_config.py) Bash(python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/init_deck.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/add_asset.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/make_deck.py *)
---

# Slide Deck

Turns a conversation into an HTML slide deck. You drive: work out what kind of presentation it is, choose where to start from, ask what's missing, write the slides, then iterate while the user reviews the deck in a browser.

The deck's files go to the `slide-decks` folder of the output root the user set in the config (`output.root`), or to a temporary folder if none is set. The scripts give you that folder and write in it; never choose a folder yourself, and never read the config.

You write only `slides.json`: the deck's title, its CSS, each slide's HTML and the data of its charts and rings. `make_deck.py` owns everything else: the page around the slides, the slide's fixed size, the toolbar with zoom and PDF export, the print rules, the scripts that draw charts and diagrams, the rings' geometry and the check. When a script refuses something, its message names the field and says what it accepts: fix the input, never work around the check.

A deck's folder holds only these files, and the check fails on any other; anything else you need goes in your own scratch folder.

```text
slide-decks/
├── _assets/                         add_asset.py writes, the user's images every deck links to
│   └── acme-logo.svg
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

**The type.** Infer the kind of presentation from what the user says (pitch, business review, townhall, report, roadmap, status update and so on). Don't present a list.

**The starting point.** If the user's message already makes it clear, don't ask. Otherwise ask, in your own words: "Do you have an example to start from, or should I draw from my own? We can also start completely blank."

- **A reference from the user** (a PDF, an image or a file): replicate it as the only structural and visual guide, and don't consult the examples.
- **No reference:** draw from the examples that `init_deck.py` lists (step 2), each with what it is good for. Read the ones whose use fits the deck, each a folder:
  - A built-in example is a real slide kept as a description (`description.md`: layout, style and density) and a wireframe (`wireframe.svg`) drawn at the deck's own slide size with the original's positions, shapes and colours, a line of text as a grey bar, a heading as a short placeholder word and a photo as a labelled box, so you can take a layout's measurements from it.
  - One of the user's is a slide of an earlier deck, kept as it was: its `slides.json` holds that slide, whose HTML and CSS you can reuse, and `slide.html` shows it.

  Use them for layout ideas, section structure, chart types and content density, never as strict templates, and tell the user briefly which you use: "I'm basing the layout on the Market Segmentation example."

- **Blank:** structure only, no colour or decoration: white background, dark text, the default sans-serif. Each slide gets a title and a layout skeleton, with placeholders for the content that is missing.

**Questions.** Ask qualifying questions one at a time, conversationally, and stop when you have enough for a coherent first draft. If the user gave a complete reference, ask nothing unless something specific is missing or ambiguous. What to ask depends on the type:

| Type            | Key questions                                       |
| --------------- | --------------------------------------------------- |
| Pitch           | audience, stage, key message                        |
| Business review | teams or workstreams, data available, time period   |
| Townhall        | company size, key announcements, tone               |
| Report          | scope, key findings, audience (exec, team, board)   |
| Roadmap/status  | product or project, time horizon, RAG status needed |

**Content.** Infer how it will arrive, without asking: when the user gives text, you handle structure and layout only; when they give a topic, you write the copy; when they give loose ideas, you write a full draft with real content.

## 2. Start the deck

When you have enough, say "I have enough for a first draft. Generating now — we can iterate from there." Choose a short `<Name>` for the deck, capitalised words joined by hyphens (honour a name the user gives), and run the command below. Call every script by exactly the path this skill shows, so it runs without a permission prompt:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/init_deck.py --name <Name>
```

It creates the deck's folder, `<Name>_<YY-MM-DD>`, replacing one of the same name and day, and prints the `slides_path` and the `examples`, each with its `source` (`built-in` or `yours`) and what it is good for. Every deck starts from scratch: never read or reuse another deck's folder, on this or another day; only `_assets`, the user's images, and `_examples`, the slides they kept, are shared. Run it once per deck, never to revise one.

## 3. Write slides.json

Write it through the shared writer, at the `slides_path` from step 2, the same way for every revision; never with your own file tools:

```bash
python3 ${CLAUDE_SKILL_DIR}/../agentic-manager-utils-lib/agentic_manager/output_file.py --name slide-decks --path '<slides_path>' <<'END_OF_FILE'
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

The fields:

- **`title`:** the deck's title, shown in the browser tab.
- **`style`:** the deck's CSS, as a list of lines. Each slide is a `.slide`, 1100×618 px with 48/56 px padding, and a slide's `class` adds class names to it, such as a dark title slide. The grey page and the slide's shadow are the page around the deck, never part of its design: don't restyle `body`, `.slides-wrapper` or `.toolbar`.
- **`slides`:** one object per slide, in order: `html`, the slide's content as a list of lines, and optionally `class`. Write attributes in single quotes, so nothing needs escaping in JSON. Close every tag you open. A slide can't hold `<script>`, `<style>`, `<link>` or frames, or load a file by its path or URL.
- **`charts`:** each chart by id (lowercase words joined by hyphens), as a Chart.js configuration: `type`, `data` and optionally `options`, plain JSON, so no functions. How its values read goes in `format`: `prefix`, `suffix` and `decimals`, such as `{"prefix": "£", "suffix": "m", "decimals": 1}` for £3.5m, applied to the value axis and the tooltips. Place it with `{{chart:<id>}}` inside an element with a set height: the chart fills it.
- **`rings`:** each donut or pie by id, drawn as SVG: `size` (the square's side in px), `outer` and `inner` radius (`inner` 0 makes a pie), `gap` (degrees between segments), `start` (degrees, clockwise from 12 o'clock, default 0) and `segments`, each a `color` and optionally a `value` (default 1, so equal segments). Place it with `{{ring:<id>}}`, and put its labels around it in HTML.

An image the user gives (a logo, a screenshot, a photo) goes in `_assets` with `python3 ${CLAUDE_SKILL_DIR}/scripts/add_asset.py --file <path>`, which prints its name, and is placed as `<img src='{{asset:<name>}}'>`; an image added for an earlier deck is already there. An image the user hasn't given is an `[IMAGE: …]` placeholder, and an icon is inline SVG.

Place every chart and ring exactly once. For a diagram (a flow, a sequence, a hierarchy), write `<pre class='mermaid'>` with Mermaid's syntax inside, writing `<` as `&lt;`. Charts and diagrams are drawn in the viewer's browser by Chart.js 4.4.1 and Mermaid.js 11.4.1, loaded from the internet when the deck opens, so use them only when a slide genuinely needs one; anything else is HTML and CSS.

**Design rules:**

- Design every slide to fit 1100×618: content that overflows is clipped, and the deck never scrolls inside a slide.
- Prefer structure to decoration in a first draft.
- Write real content, with a placeholder only where information is genuinely missing. A placeholder names what is missing, in one of these forms: `[CHART: revenue by quarter, bar]`, `[IMAGE: team photo]`, `[DIAGRAM: onboarding flow]`, `[TABLE: KPI summary, 4 rows]` or `[PLACEHOLDER: description]`.

## 4. Build

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/make_deck.py --deck <deck>
```

If `slides.json` is invalid, it writes nothing and lists every problem, by field. Once it is valid, it writes the deck, checks it and prints one line of JSON with the deck's `path`, whether its folder is `temporary`, `ok`, `errors` and the `placeholders` left in it. Fix `slides.json` and run it again until `ok` is true; never edit the deck itself.

## 5. Tell the user

Say the deck is ready, with a Markdown link to its full `path`, and that it opens in any browser, with zoom and PDF export on the toolbar. If it shows images, say they show only while the deck stays in its folder beside `_assets`, so to share it, export it to PDF. Don't recap the slides. List the placeholders still open, if any, as what you need from them; mention any doubt about your own judgment the deck doesn't show; and if `temporary` is true, say the folder is temporary and setting `output.root` in the config keeps decks. End by offering to keep a slide as an example for future decks.

## 6. Iterate

The user gives feedback and refreshes the browser. Be surgical: change only what they asked. To change a few fields, add `--patch` to the writer and send a JSON array of exact replacements, `[{"old": "unique text", "new": "fixed text"}]`, instead of the whole file; the JSON's escapes count as part of the text. Then run `make_deck.py` again, and confirm what changed in one line.

## 7. Keep a slide as an example

When the user says they're happy with a slide, keep it as an example: write a short title and one line on what the slide is good for, such as "a quarter's results: four headline figures over a trend chart", then run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/save_example.py --deck <deck> --slide <n> --title '<title>' --use-for '<what it is good for>'
```

`<n>` is the slide's number, 1 for the first. It saves the slide exactly as it is in its own folder in `_examples`, beside the decks, with its page, and every later deck lists it. Give the user the link to its `page`.
