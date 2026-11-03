"""List the closed milestones that have no badge yet.

A milestone is a part: a folder with its own PROGRESS.md, such as a stage of a
course. Once every step in it is done, it is due a badge: an image in the hub's
icons folder, named after the part's path, so it travels through Git with the
hub. Until it has one, the map draws the part as a generated star.

    python3 -m cognition_tree.badges --root ~/learn
"""

import argparse
from pathlib import Path

from .collect import _ICON_TYPES, collect


def closed_milestones(tree: dict):
    """Yield (branch, part) for every closed part, nested ones too."""
    def walk(branch, parts):
        for part in parts:
            if part.get("closed"):
                yield branch, part
            yield from walk(branch, part.get("parts", []))

    for branch in tree["branches"]:
        yield from walk(branch, branch.get("parts", []))


def missing(root: Path, hub: str = "learning-hub"):
    """Yield (branch, part, base path without extension) for each closed part without a badge."""
    icons = root / hub / "icons"
    for branch, part in closed_milestones(collect(root, hub)):
        base = icons / branch["repo"] / part["path"]
        if not any(base.with_name(base.name + suffix).is_file() for suffix in _ICON_TYPES):
            yield branch, part, base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List closed milestones without a badge.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--hub", default="learning-hub")
    args = parser.parse_args(argv)
    todo = list(missing(args.root.expanduser(), args.hub))
    for branch, part, base in todo:
        print(f"{branch['title']} / {part['title']}: {base}.svg")
    if not todo:
        print("Every closed milestone has its badge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
