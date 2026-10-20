"""Write the tree JSON and its static HTML page."""

import json
from pathlib import Path


TEMPLATE_PATH = Path(__file__).parent / "web" / "template.html"
_PLACEHOLDER = "__TREE_DATA__"


def build(tree: dict, out: str | Path, *, json_only: bool = False) -> None:
    """Write outputs, escaping less-than signs inside the data script."""
    payload = json.dumps(tree, ensure_ascii=False, indent=2) + "\n"
    page = None
    if not json_only:
        if not TEMPLATE_PATH.is_file():
            raise ValueError(
                f"Template is missing: {TEMPLATE_PATH}; use --json-only to write tree.json"
            )
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        if template.count(_PLACEHOLDER) != 1:
            raise ValueError("Template must contain exactly one __TREE_DATA__ placeholder")
        page = template.replace(_PLACEHOLDER, payload.replace("<", "\\u003c"))

    out = Path(out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    (out / "tree.json").write_text(payload, encoding="utf-8")
    if page is not None:
        (out / "index.html").write_text(page, encoding="utf-8")
