"""Read local repositories into the tree data contract."""

import base64
from datetime import datetime
from pathlib import Path
import re
import tomllib


_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_TABLE_HEADER = re.compile(r"^\|\s*Branch\s*\|\s*Repository\s*\|")
_SECTION = re.compile(r"^##(?:\s+(.*))?$")
_LINE = re.compile(r"^###\s+(.+)$")
_ITEM = re.compile(r"^( *)- \[([ xX])\]\s*(.*)$")
_DASH = re.compile(r"\s*[—–]\s*|\s+-\s+")
_TITLE = re.compile(r"^#\s+(.+)$", re.M)
_DIGITS = re.compile(r"(\d+)")
_XP = re.compile(r"\s*\{\s*(\d+)\s*XP\s*\}", re.I)
# A step without an XP tag is worth the smallest mob.
DEFAULT_XP = 10
_PART_DEPTH = 4
_ICON_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
               ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_ICON_MAX_BYTES = 256 * 1024
_NOT_PARTS = {"node_modules"}


def _plain(text: str) -> str:
    """Remove the Markdown formatting named in the contract."""
    return _LINK.sub(r"\1", text).replace("`", "").replace("**", "").strip()


def _row(cells: list[str]) -> dict | None:
    link = _LINK.search(cells[1]) if len(cells) >= 2 else None
    if not link:
        return None
    repo = _plain(link[1])
    return {"id": repo, "title": _plain(cells[0]), "repo": repo, "url": link[2]}


def _branches(readme: Path) -> tuple[list[dict], list[dict]]:
    """The first hub table, and the table of completed branches if there is one.

    The completed table is the first `| Branch | Repository |` table under a `##`
    heading that contains "completed"; its third cell, if any, is kept as the date.
    """
    if not readme.is_file():
        raise ValueError(f"Hub table is missing: {readme}")
    active, completed = None, None
    table, heading = None, ""
    for line in readme.read_text(encoding="utf-8").splitlines():
        section = _SECTION.match(line.strip())
        if section:
            heading, table = (section[1] or "").lower(), None
            continue
        if table is None:
            if _TABLE_HEADER.match(line.strip()):
                if active is None:
                    table = active = []
                elif completed is None and "completed" in heading:
                    table = completed = []
            continue
        if not line.strip().startswith("|"):
            table = None
            continue
        cells = line.strip().strip("|").split("|")
        row = _row(cells)
        if row is None:
            continue
        if table is completed:
            row["completed"] = _plain(cells[2]) if len(cells) > 2 else ""
        table.append(row)
    if active is None:
        raise ValueError(f"Hub table is missing: {readme}")
    return active, completed or []


def _checklist_heading(heading: str) -> bool:
    heading = heading.lower()
    return ("checklist" in heading or "чек-лист" in heading) and "preserved" not in heading


def parse_progress(text: str) -> list[dict]:
    """Parse checklist sections, preserving line and item order.

    A milestone checklist is skipped when the file has a finer one, because
    milestones group the same steps.
    """
    headings = [m[1] or "" for m in map(_SECTION.match, text.splitlines()) if m]
    checklists = [h for h in headings if _checklist_heading(h)]
    skip_milestones = any("milestone" not in h.lower() for h in checklists)
    lines = []
    active = False
    title = None
    current_line = None
    stack = []
    group_counts = {}
    fallback_count = 0

    for raw in text.splitlines():
        section = _SECTION.match(raw)
        if section:
            heading = section[1] or ""
            active = _checklist_heading(heading) and not (
                skip_milestones and "milestone" in heading.lower()
            )
            title, current_line, stack = _plain(section[1] or "") or None, None, []
            continue
        if not active:
            continue
        heading = _LINE.match(raw)
        if heading:
            title, current_line, stack = _plain(heading[1]), None, []
            continue
        item = _ITEM.match(raw)
        if not item:
            continue
        if current_line is None:
            current_line = {"title": title, "steps": []}
            lines.append(current_line)
            fallback_count = 0

        text = _plain(item[3])
        tag = _XP.search(text)
        xp = int(tag[1]) if tag else DEFAULT_XP
        text = _XP.sub("", text).strip()
        group = None
        body = text
        if "·" in text:
            prefix, _, rest = text.partition("·")
            if prefix.strip() and rest.strip():
                group, body = prefix.strip(), rest.strip()
        parts = _DASH.split(body, maxsplit=1)
        if len(parts) == 2 and parts[0] and parts[1]:
            step_id, step_title = parts
        elif group:
            group_counts[group] = group_counts.get(group, 0) + 1
            step_id, step_title = f"{group}:{group_counts[group]}", body
        else:
            fallback_count += 1
            step_id, step_title = f"line-{len(lines)}:{fallback_count}", text
        step = {
            "id": step_id,
            "group": group,
            "title": step_title,
            "done": item[2].lower() == "x",
            "xp": xp,
            "current": False,
            "children": [],
        }
        indent = len(item[1]) if len(item[1]) >= 2 else 0
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(step)
        else:
            current_line["steps"].append(step)
        stack.append((indent, step))

    for line in lines:
        for step in line["steps"]:
            if not step["done"]:
                step["current"] = True
                break
    return lines


def _auto(step: dict) -> bool:
    """Whether the ID was numbered by the build, as `GROUP:n` or `line-k:n`."""
    group = step["group"]
    return bool(re.fullmatch(r"line-\d+:\d+", step["id"])
                or group and re.fullmatch(re.escape(group) + r":\d+", step["id"]))


def _key(step: dict) -> tuple:
    """What makes an archived item the same as a live one.

    A numbered ID shifts when an earlier item of its group leaves the progress
    file, so such an item is matched by its group and title instead.
    """
    return ("title", step["group"], step["title"]) if _auto(step) else ("id", step["id"])


def merge_archive(lines: list[dict], archived: list[dict]) -> list[dict]:
    """Put archived done items before the live items of the line with the same title."""
    live = {_key(step) for line in lines for step in _walk(line["steps"])}

    def keep(steps):
        kept = []
        for step in steps:
            if not step["done"] or _key(step) in live:
                continue
            step.update(current=False, archived=True, children=keep(step["children"]))
            kept.append(step)
        return kept

    merged = [dict(line, steps=list(line["steps"])) for line in lines]
    by_title = {line["title"]: line for line in merged}
    new_lines = []
    for line in archived:
        steps = keep(line["steps"])
        if not steps:
            continue
        target = by_title.get(line["title"])
        if target is None:
            target = {"title": line["title"], "steps": []}
            by_title[line["title"]] = target
            new_lines.append(target)
        target["steps"][:0] = steps
    result = new_lines + merged
    _renumber(result)
    return result


def _renumber(lines: list[dict]) -> None:
    """Number the items without an ID again, in the merged order, as one file would."""
    groups = {}
    for k, line in enumerate(lines, 1):
        count = 0
        for step in _walk(line["steps"]):
            if not _auto(step):
                continue
            if step["group"]:
                groups[step["group"]] = groups.get(step["group"], 0) + 1
                step["id"] = f"{step['group']}:{groups[step['group']]}"
            else:
                count += 1
                step["id"] = f"line-{k}:{count}"


def _walk(steps):
    for step in steps:
        yield step
        yield from _walk(step["children"])


def _has_part(parts: list[dict], path: str) -> bool:
    return any(part["path"] == path or _has_part(part["parts"], path) for part in parts)


def _tally(holder: dict) -> dict:
    """Step counts and XP of a repository or part, its nested parts included."""
    items = _items(holder)
    return {
        "done": sum(item["done"] for item in items),
        "total": len(items),
        "xp_done": sum(item["xp"] for item in items if item["done"]),
        "xp_total": sum(item["xp"] for item in items),
    }


def _items(repository: dict) -> list[dict]:
    """Every item of a repository or part, its nested parts included."""
    own = [step for line in repository["lines"] for step in _walk(line["steps"])]
    return own + [step for part in repository.get("parts", []) for step in _items(part)]


def _read_lines(directory: Path) -> list[dict]:
    lines = parse_progress((directory / "PROGRESS.md").read_text(encoding="utf-8"))
    archive = directory / "ARCHIVE.md"
    if archive.is_file():
        lines = merge_archive(lines, parse_progress(archive.read_text(encoding="utf-8")))
    return lines


def _natural(path: Path) -> list:
    """Sort key that puts lecture-2 before lecture-10."""
    return [int(piece) if piece.isdigit() else piece for piece in _DIGITS.split(path.name)]


def _part_title(directory: Path) -> str:
    """The file's `#` heading, unless it only names the progress file."""
    heading = _TITLE.search((directory / "PROGRESS.md").read_text(encoding="utf-8"))
    title = _plain(heading[1]) if heading else ""
    if not title or re.search(r"progress|прогресс", title, re.I):
        return directory.name
    return title


def _parts(directory: Path, base: Path, depth: int = 1) -> list[dict]:
    """Subdirectories with their own PROGRESS.md, in natural name order.

    A directory without one is passed through, so its parts belong to the
    nearest ancestor that has one. Hidden and underscored directories,
    node_modules and symbolic links are skipped.
    """
    if depth > _PART_DEPTH:
        return []
    parts = []
    subdirectories = [
        path for path in directory.iterdir()
        if path.is_dir() and not path.is_symlink()
        and not path.name.startswith((".", "_")) and path.name not in _NOT_PARTS
    ]
    for sub in sorted(subdirectories, key=_natural):
        if not (sub / "PROGRESS.md").is_file():
            parts.extend(_parts(sub, base, depth + 1))
            continue
        part = {
            "path": sub.relative_to(base).as_posix(),
            "title": _part_title(sub),
            "lines": _read_lines(sub),
            "parts": _parts(sub, base, depth + 1),
        }
        part.update(_tally(part))
        part["closed"] = 0 < part["total"] == part["done"]
        parts.append(part)
    return parts


def _requirement_status(requirement: dict, repository: dict) -> str:
    if "met" in requirement:
        return "met"
    items = _items(repository)
    matches = [item for item in items if item["id"] == requirement["step"]]
    group = [item for item in items if item["group"] == requirement["step"]]
    if any(item["done"] for item in matches) or (
        group and all(item["done"] for item in group)
    ):
        return "met"
    return "open" if matches or group else "unknown"


def _icons(directory: Path) -> dict[str, str]:
    """Map each icon's file name, without extension, to a data URI.

    Files that are too large or of another type are skipped, so a stray file
    never breaks the page.
    """
    icons = {}
    if not directory.is_dir():
        return icons
    for path in sorted(directory.iterdir()):
        kind = _ICON_TYPES.get(path.suffix.lower())
        if kind is None or not path.is_file() or path.stat().st_size > _ICON_MAX_BYTES:
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        icons.setdefault(path.stem, f"data:{kind};base64,{encoded}")
    return icons


def _icon_tree(directory: Path) -> dict[str, str]:
    """Icons below a branch's folder, keyed by their path without extension."""
    icons = {}
    if not directory.is_dir():
        return icons
    for sub in sorted(p for p in directory.rglob("*") if p.is_dir()):
        prefix = sub.relative_to(directory).as_posix() + "/"
        icons.update({prefix + k: v for k, v in _icons(sub).items() if prefix + k not in icons})
    for name, uri in _icons(directory).items():
        icons.setdefault(name, uri)
    return icons


def _mark_icons(branch: dict, icons: dict[str, str]) -> None:
    """Give parts, the milestones of a branch, their icon by folder path."""
    def parts(items):
        for part in items:
            if part["path"] in icons:
                part["icon"] = icons[part["path"]]
            parts(part.get("parts", []))

    parts(branch["parts"])


def collect(root: str | Path, hub: str = "learning-hub") -> dict:
    """Collect branches and evaluate locks against local progress."""
    root = Path(root).expanduser()
    if not root.is_dir():
        raise ValueError(f"Root directory is missing or is not a directory: {root}")
    hub_path = root / hub
    branches, completed = _branches(hub_path / "README.md")
    listed = {branch["repo"] for branch in branches}
    branches += [row for row in completed if row["repo"] not in listed]
    cache = {}

    def repository(repo: str) -> dict:
        if repo not in cache:
            directory = root / repo
            found = directory.is_dir() and (directory / "PROGRESS.md").is_file()
            data = {
                "found": found,
                "lines": _read_lines(directory) if found else [],
                "parts": _parts(directory, directory) if found else [],
            }
            data.update(_tally(data))
            cache[repo] = data
        return cache[repo]

    config = hub_path / "tree.toml"
    locks = tomllib.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}

    by_repo = {branch["repo"]: branch for branch in branches}
    for entry in locks.get("book", []):
        book = {"title": _plain(entry["title"]), "emblem": entry.get("emblem", "")}
        branch = by_repo.get(entry["repo"])
        if branch is None:
            branch = {
                "id": entry["repo"],
                "title": _plain(entry.get("short", entry["title"])),
                "repo": entry["repo"],
                "url": entry.get("url"),
            }
            branches.append(branch)
            by_repo[entry["repo"]] = branch
        branch["book"] = book

    icons = _icons(hub_path / "icons")
    for branch in branches:
        branch.update(repository(branch["repo"]))
        if branch["repo"] in icons:
            branch["icon"] = icons[branch["repo"]]
        _mark_icons(branch, _icon_tree(hub_path / "icons" / branch["repo"]))
        if "completed" in branch:
            # In the sky only while nothing is open: a new step brings it back as a branch.
            branch["sky"] = branch["found"] and 0 < branch["total"] == branch["done"]
    def _grown(becomes: str | None) -> bool:
        """True once the branch it becomes is drawn: a found branch, or a part of one."""
        if not becomes:
            return False
        repo, _, path = becomes.partition("/")
        branch = by_repo.get(repo)
        if branch is None or not branch["found"]:
            return False
        return not path or _has_part(branch["parts"], path)

    locked = []
    for entry in locks.get("locked", []):
        requirements = []
        for requirement in entry.get("requires", []):
            requirements.append({
                "repo": requirement["repo"],
                "step": requirement["step"],
                "label": _plain(requirement.get("label", requirement["step"])),
                "status": _requirement_status(
                    requirement, repository(requirement["repo"])
                ),
            })
        branch = {
            "id": entry["id"],
            "title": _plain(entry["title"]),
            "hidden": entry.get("hidden", False),
        }
        if "source" in entry:
            branch["source"] = {
                "title": _plain(entry["source"]["title"]),
                "url": entry["source"]["url"],
            }
        if "note" in entry:
            branch["note"] = _plain(entry["note"])
        if entry["id"] in icons:
            branch["icon"] = icons[entry["id"]]
        if "becomes" in entry:
            branch["becomes"] = entry["becomes"].strip("/")
        met = sum(item["status"] == "met" for item in requirements)
        branch.update(
            requires=requirements, met=met, total=len(requirements),
            open=met == len(requirements), grown=_grown(branch.get("becomes")),
        )
        locked.append(branch)

    return {
        "schema": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "branches": branches,
        "locked": locked,
    }
