"""Command-line entry point for the static tree builder."""

import argparse
from pathlib import Path

from .build import build
from .collect import collect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a local learning progress tree.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--hub", default="learning-hub")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        build(collect(args.root, args.hub), args.out, json_only=args.json_only)
    except (OSError, ValueError) as error:
        parser.exit(1, f"cognition-tree: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
