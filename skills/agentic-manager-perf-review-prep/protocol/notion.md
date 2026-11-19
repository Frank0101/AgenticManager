# Find the Notion pages a person created

A manager is preparing a performance review of the person named below. Find the pages the person created in the review's period, with the Notion MCP's search, so the review can count them: run one search for each week listed under "The searches", all at once, as none depends on another.

## How to search

Copy each week's arguments exactly as listed: they are what the check expects, so change or add none. The `query` stays empty and only the filters narrow the search, because any query text makes Notion silently drop pages, and the count would come out too low without anyone noticing. Empty means the empty string, no characters at all: two quotation marks are text, which Notion searches for and finds nothing, so every search comes back empty and looks like a person who created no pages.

A result's date is its last edit, not its creation, so a page belongs to the week whose search found it, whatever date it shows. Pages the person only edited aren't gathered: Notion knows only a page's last editor, so their count would miss what others edited after.

## When a search returns {{search_limit}} results

{{search_limit}} is the most a search returns, rows of databases included, so a week that returns {{search_limit}} may be missing pages. Search that week again in shorter ranges, such as halves, until each returns fewer than {{search_limit}}, and record those searches instead of the week's. A single day that still returns {{search_limit}} is recorded with `"full": true`, its results taken as all there are.

## Recording

Record every search, as the submit command shows: its range of days and its results exactly as the search returned them, databases and rows included, as the script keeps the pages of their own. It checks that the ranges cover the period day by day, and names the days that are missing.
