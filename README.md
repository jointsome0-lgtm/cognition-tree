# cognition-tree

A skill tree for self-directed learning, drawn from plain Markdown progress files.

Each learning topic lives in its own repository with a `PROGRESS.md` checklist. A hub repository lists the topics in a table. cognition-tree reads them from local clones and draws one page: topics grow as branches from a common core, steps are nodes, done steps fill in, and the current step of each line is ringed. Some branches are locked like a game subclass and open only after steps in other branches are done.

## Run

Python 3.11 or newer, standard library only.

```sh
python3 -m cognition_tree --root ~/learn --hub learning-hub --out out
xdg-open out/index.html
```

`--root` is the directory that holds the repositories side by side. The page is self-contained and works offline.

## What it reads

- The hub's `README.md`: a table whose header starts with `| Branch | Repository |`, one row per branch.
- Each branch repository's `PROGRESS.md`: the checklist sections, `- [ ]` and `- [x]` items with optional `###` lines.
- `tree.toml` in the hub, optional: locked branches and their prerequisites.
- Subfolders with their own `PROGRESS.md`, optional: parts of a branch. A finished part shrinks into a cluster of stars near the trunk, and an open part forks into its own lines.

The exact formats are in [docs/DATA.md](docs/DATA.md).

## Locked branches

A locked branch is drawn as a seed beyond the rim, with roots to the steps it waits for. Two modes, switched on the page:

- **Show as silhouettes:** every locked branch is visible with a count such as "2 of 5". A branch marked `hidden` shows as "???" until it opens.
- **Keep as a surprise:** locked branches are not drawn at all. A branch appears, with a short bloom, the first time it opens.

## Theme

**Day** or **Night sky**, switched on the page and remembered. Night sky draws done steps as glowing stars on a starfield. Until a theme is chosen, the page follows the system's dark-mode setting; `?theme=night` or `?theme=day` in the address overrides both.

## Privacy

The generated page contains your progress. It is written to `out/`, which Git ignores. Keep it local, or publish it on purpose.

## License

[MIT](LICENSE).
