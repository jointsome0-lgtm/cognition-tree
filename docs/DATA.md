# Data contract

cognition-tree reads a directory of learning repositories and renders one static HTML page. The backend (`cognition_tree/collect.py`, `cognition_tree/build.py`) produces the tree described here; the frontend (`cognition_tree/web/template.html`) only reads it.

## Inputs

All inputs are local files. Nothing is fetched from the network.

- **Root:** a directory that holds the repositories side by side, for example `~/learn`.
- **Hub:** one repository in the root, `learning-hub` by default. Its `README.md` holds a Markdown table whose header row starts with `| Branch | Repository |`. Each row gives a branch title in the first cell and a link `[repo-name](url)` in the second; the order of rows is the order of branches. Other cells are ignored.
- **Locks:** `tree.toml` in the hub, optional. See [Locks](#locks).
- **Archive:** `ARCHIVE.md` in each repository, optional. See [Archive](#archive).
- **Parts:** subdirectories of a repository with their own `PROGRESS.md`, optional. See [Parts](#parts).
- **Progress:** `PROGRESS.md` in each repository. Only the checklist sections are read: a `##` heading whose text contains `checklist` (case-insensitive), except one whose text also contains `preserved`, and except one whose text contains `milestone` when the file has another checklist section, since milestones group the same steps. A section ends at the next `##` heading.

### Checklist lines

Inside a checklist section:

- A `###` heading starts a new line of the branch, titled with the heading text. Items before any `###` belong to a line titled with the `##` section heading. A `###` heading that has no items under it (such as "How the lists are used") produces no line.
- An item is `- [ ] ...` or `- [x] ...` (also `X`). Indentation by two or more spaces makes it a child of the previous less-indented item.
- Item text forms, after the box:
  - `ID — Title`, for example `K01 — Overhand knot`.
  - `GROUP · ID — Title`, for example `B1 · K04 — Bowline`.
  - `GROUP · Title` with no ID, for example `B0 · Delivery Framework`. The ID is then `GROUP:n`, n counting such items in that group from 1.
  - Anything else: ID is `line-k:n`, the whole text is the title.
  - The dash may be `—`, `–` or ` - `. Text after the title in parentheses stays part of the title.

## Output: `tree.json`

The build also embeds this object in the page.

```json
{
  "schema": 1,
  "generated_at": "2026-10-20T21:00:00+03:00",
  "branches": [
    {
      "id": "learn-sailing",
      "title": "Sailing",
      "repo": "learn-sailing",
      "url": "https://github.com/owner/learn-sailing",
      "found": true,
      "lines": [
        {
          "title": "Knots (B1–B2)",
          "steps": [
            {"id": "K04", "group": "B1", "title": "Bowline", "done": false, "current": true, "children": []}
          ]
        }
      ],
      "parts": [],
      "done": 0,
      "total": 12
    }
  ],
  "locked": [
    {
      "id": "celestial-navigation",
      "title": "Celestial navigation",
      "hidden": false,
      "source": {"title": "A free course", "url": "https://example.com/course"},
      "note": "Lessons 1-3 first.",
      "requires": [
        {"repo": "learn-astronomy", "step": "A06", "label": "Star sights", "status": "open"}
      ],
      "met": 0,
      "total": 5,
      "open": false
    }
  ]
}
```

- `found` is false when the repository directory or its `PROGRESS.md` is missing; `lines` is then empty.
- `done` and `total` count all items, children and parts included.
- `archived` is present and true only on items that come from `ARCHIVE.md`.
- `current` is true on the first item, in document order, that is not done, once per line. Children are not marked current.
- Strings are copied from the files without Markdown links: `[text](url)` becomes `text`; backticks and `**` are removed.

## Archive

A progress file may be shortened as the learner advances. A done item is then moved, not deleted, into `ARCHIVE.md` of the same repository, which is only appended to. The archive uses the same checklist format, for example:

```markdown
## Archived checklist

### Atomic checklist
- [x] K01 — Overhand knot (archived 2026-11-02)
```

The build reads the archive like a progress file and keeps only done items whose ID is not in `PROGRESS.md`. Each is marked `archived`, children included, and is never `current`. The archived items of a line go before its live items, in archive order; a line found only in the archive goes before all live lines. An item that is not done in the archive is ignored.

## Parts

A repository may grow by folders: a closed stage moves into one folder, and the next stage keeps one folder per topic, each with its own `PROGRESS.md`, while the root `PROGRESS.md` keeps only an overview. For example:

```
learn-sailing/
  PROGRESS.md                  overview, may have no checklist
  basics/PROGRESS.md           every item done: a closed part
  coastal/PROGRESS.md          overview of the topics below
  coastal/02-tides/PROGRESS.md
  coastal/10-pilotage/PROGRESS.md
```

Every subdirectory, to a depth of four, that has a `PROGRESS.md` is a part, read like the root file, with its own `ARCHIVE.md` if there is one. A directory without one is passed through: its parts belong to the nearest ancestor that has one. Hidden and underscored directories, `node_modules` and symbolic links are skipped. Parts are listed in natural name order, so `02-tides` comes before `10-pilotage`.

Each branch has `parts`, empty when there are none, and each part has:

```json
{
  "path": "coastal/02-tides",
  "title": "Tides",
  "lines": [],
  "parts": [],
  "done": 3,
  "total": 5,
  "closed": false
}
```

- `path` is relative to the repository, with `/` separators.
- `title` is the file's `#` heading, unless the heading is missing or contains "progress" or "прогресс"; then it is the directory name.
- `closed` is true when the part, its own parts included, has at least one item and every item is done.
- A lock's `step` is looked up in every part as well, so a step moved into a folder still meets its requirement. When two parts use the same ID, the requirement is met if either is done.

The page draws an open part as a node from which its own lines fan out, and a closed part as one star whose shape and tint come from its path, so it never changes. At the end of a trunk, the only closed part sits on it and several take slots in the fan. Inside a part, closed parts orbit its node in name order, six on the first ring, twelve on the second and so on, and the node becomes a sun: the star the part will be once closed. Closed topics therefore take no room in the fan however many there are.

## Books

`tree.toml` may list books that have a practice repository:

```toml
[[book]]
repo = "learn-knots"
title = "The Ashley Book of Knots"
short = "Ashley"      # optional; the branch title when the book is not in the hub table
emblem = "🪢"         # optional
```

A book whose repository is a branch in the hub table marks that branch; any other book is added after the hub branches, with `url` from the entry or null. Either way the branch gets `"book": {"title": ..., "emblem": ...}`, with `emblem` an empty string when not given. Branches that are not books have no `book` key. A `##` heading containing `чек-лист` also counts as a checklist section.

## Locks

`tree.toml` in the hub:

```toml
schema = 1

[[locked]]
id = "celestial-navigation"
title = "Celestial navigation"
hidden = false            # optional, default false
note = "Lessons 1-3 first."   # optional
source = { title = "A free course", url = "https://example.com/course" }

[[locked.requires]]
repo = "learn-astronomy"
step = "A06"
label = "Star sights"   # optional, defaults to the step

[[locked.requires]]
repo = "learn-sailing"
step = "B3"
label = "Dead reckoning"
met = "2026-12-01"        # optional manual override: a date, recorded by the owner
```

A requirement's `status`:

- `met` when `met` is set in the file, or when an item with ID `step` in that repository is done, or when `step` equals a group and every item of that group is done (at least one item).
- `open` when the step or group exists and is not done.
- `unknown` when the repository, its progress file or the step is not found. The page shows it as not yet on the map.

A requirement may name any repository in the root, also one that is not a branch in the hub table. `met` counts requirements with status `met`; `open` on the locked branch is true when `met == total`.

## Embedding

`template.html` contains exactly one placeholder:

```html
<script id="tree-data" type="application/json">__TREE_DATA__</script>
```

The build replaces `__TREE_DATA__` with the JSON, after replacing every `<` with `<`, and writes `index.html` and `tree.json` into the output directory.

## Privacy

The output holds the owner's learning progress. It is written to `out/`, which Git ignores, and is never published. Tests use only the synthetic fixtures in `tests/fixtures/`.
