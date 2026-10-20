"""Contract checks using invented learning repositories."""

from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import unittest

from cognition_tree.collect import collect, merge_archive, parse_progress


ROOT = Path(__file__).parent / "fixtures" / "root"


def all_steps(lines):
    def walk(steps):
        for step in steps:
            yield step
            yield from walk(step["children"])

    return [step for line in lines for step in walk(line["steps"])]


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tree = collect(ROOT)
        self.paper, self.gears, self.quiet, self.missing = self.tree["branches"]

    def test_schema_and_hub_table_order(self):
        self.assertEqual(set(self.tree), {"schema", "generated_at", "branches", "locked"})
        self.assertEqual(self.tree["schema"], 1)
        self.assertIsNotNone(datetime.fromisoformat(self.tree["generated_at"]).tzinfo)
        self.assertEqual(
            [branch["title"] for branch in self.tree["branches"]],
            ["Paper", "Gears", "Quiet", "Missing"],
        )
        for branch in self.tree["branches"]:
            self.assertEqual(set(branch), {
                "id", "title", "repo", "url", "found", "lines", "done", "total",
            })
            self.assertEqual(branch["id"], branch["repo"])
            self.assertEqual(branch["url"], f"https://example.invalid/{branch['repo']}")

    def test_all_item_forms_and_markdown_cleanup(self):
        items = all_steps(self.paper["lines"])
        self.assertEqual([item["id"] for item in items], [
            "P01", "P01a", "P01b", "A0:1", "A0:2", "line-1:1",
            "P02", "P03", "P03a", "A2:1", "A0:3", "line-2:1", "P04", "P05",
        ])
        by_id = {item["id"]: item for item in items}
        self.assertEqual(by_id["P01"]["title"], "Fold a square (draft)")
        self.assertEqual(by_id["P01a"]["title"], "Inspect the crease")
        self.assertEqual(by_id["P01b"]["title"], "Record the angle")
        self.assertTrue(by_id["P01b"]["done"])
        self.assertEqual(by_id["P02"]["group"], "A1")
        self.assertEqual(by_id["P02"]["title"], "Make a triangle")
        self.assertEqual(by_id["P03"]["title"], "Align the edges (twice)")
        self.assertEqual(by_id["P04"]["title"], "Pack the result")
        self.assertEqual(by_id["A0:1"]["group"], "A0")
        self.assertEqual(by_id["A0:1"]["title"], "Introductory folding")
        self.assertEqual(by_id["A0:3"]["title"], "Reuse the paper")
        self.assertEqual(by_id["line-1:1"]["title"], "text without a coded prefix")
        self.assertIsNone(by_id["line-1:1"]["group"])
        for item in items:
            self.assertEqual(set(item), {
                "id", "group", "title", "done", "current", "children",
            })

    def test_indentation_current_marking_and_counts(self):
        first = self.paper["lines"][0]["steps"]
        self.assertEqual([item["id"] for item in first], [
            "P01", "A0:1", "A0:2", "line-1:1",
        ])
        child = first[0]["children"][0]
        self.assertEqual(child["id"], "P01a")
        self.assertEqual(child["children"][0]["id"], "P01b")
        self.assertEqual(
            [item["id"] for item in all_steps(self.paper["lines"]) if item["current"]],
            ["A0:1", "P03", "P05"],
        )
        self.assertEqual((self.paper["done"], self.paper["total"]), (5, 14))
        self.assertEqual((self.gears["done"], self.gears["total"]), (4, 4))
        self.assertFalse(any(item["current"] for item in all_steps(self.gears["lines"])))

    def test_section_boundaries_and_empty_headings(self):
        self.assertEqual(
            [line["title"] for line in self.paper["lines"]],
            ["Practice CHECKLIST", "Paper shapes", "New batch"],
        )
        self.assertTrue(self.quiet["found"])
        self.assertEqual(self.quiet["lines"], [])
        self.assertEqual((self.quiet["done"], self.quiet["total"]), (0, 0))

    def test_fallback_numbering_and_less_indented_parents(self):
        lines = parse_progress(
            "## Checklist\n"
            "### Empty heading\n"
            "### Tasks\n"
            "- [x] completed parent\n"
            "    - [ ] deep child\n"
            "  - [ ] shallower child\n"
            " - [ ] next root\n"
            "## More checklist\n"
            "- [ ] final root\n"
        )
        self.assertEqual(
            [item["id"] for item in all_steps(lines)],
            ["line-1:1", "line-1:2", "line-1:3", "line-1:4", "line-2:1"],
        )
        self.assertEqual(len(lines[0]["steps"][0]["children"]), 2)
        self.assertEqual(
            [item["title"] for item in all_steps(lines) if item["current"]],
            ["next root", "final root"],
        )
        self.assertEqual(lines[1]["title"], "More checklist")

    def test_missing_repository(self):
        self.assertEqual(self.missing, {
            "id": "absent-lab",
            "title": "Missing",
            "repo": "absent-lab",
            "url": "https://example.invalid/absent-lab",
            "found": False,
            "lines": [],
            "done": 0,
            "total": 0,
        })

    def test_requirement_statuses_and_groups(self):
        gate = self.tree["locked"][0]
        self.assertEqual([item["status"] for item in gate["requires"]], [
            "met", "open", "unknown", "met", "open", "unknown", "unknown",
        ])
        self.assertEqual((gate["met"], gate["total"], gate["open"]), (2, 7, False))
        self.assertFalse(gate["hidden"])
        self.assertEqual(gate["title"], "Paper machine")
        self.assertEqual(gate["source"], {
            "title": "Paper machine", "url": "https://example.invalid/source",
        })
        self.assertEqual(gate["note"], "Keep small parts in the tray.")
        self.assertEqual(gate["requires"][0]["label"], "Recorded angle")
        for item in gate["requires"]:
            self.assertEqual(set(item), {"repo", "step", "label", "status"})

    def test_nonbranch_repository_and_manual_overrides(self):
        gate = self.tree["locked"][1]
        self.assertNotIn("side-lab", [branch["repo"] for branch in self.tree["branches"]])
        self.assertEqual([item["status"] for item in gate["requires"]], ["met"] * 3)
        self.assertEqual(gate["requires"][0]["label"], "Side task")
        self.assertEqual((gate["met"], gate["total"], gate["open"]), (3, 3, True))
        self.assertTrue(gate["hidden"])
        self.assertNotIn("note", gate)

    def test_zero_requirements_is_open(self):
        gate = self.tree["locked"][2]
        self.assertEqual(gate["requires"], [])
        self.assertEqual((gate["met"], gate["total"], gate["open"]), (0, 0, True))

    def test_group_requires_every_child_to_be_done(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            shutil.copytree(ROOT, root)
            progress = root / "gear-lab" / "PROGRESS.md"
            progress.write_text(
                progress.read_text(encoding="utf-8").replace("[X] G1 · G02", "[ ] G1 · G02"),
                encoding="utf-8",
            )
            gate = collect(root)["locked"][0]
            self.assertEqual(gate["requires"][3]["status"], "open")
            self.assertEqual(gate["met"], 1)

    def test_missing_progress_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            shutil.copytree(ROOT, root)
            (root / "gear-lab" / "PROGRESS.md").unlink()
            tree = collect(root)
            gears = tree["branches"][1]
            self.assertFalse(gears["found"])
            self.assertEqual(gears["lines"], [])
            self.assertEqual((gears["done"], gears["total"]), (0, 0))
            self.assertEqual(tree["locked"][0]["requires"][3]["status"], "unknown")

    def test_optional_locks_and_custom_hub(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            shutil.copytree(ROOT, root)
            (root / "learning-hub").rename(root / "custom-hub")
            (root / "custom-hub" / "tree.toml").unlink()
            tree = collect(root, "custom-hub")
            self.assertEqual(tree["locked"], [])
            self.assertEqual(tree["branches"], self.tree["branches"])


class ArchiveTests(unittest.TestCase):
    LIVE = (
        "## Checklist\n"
        "### Knots\n"
        "- [ ] K03 — Bowline\n"
        "- [ ] K04 — Sheet bend\n"
    )
    ARCHIVE = (
        "## Archived checklist\n"
        "### Knots\n"
        "- [x] K01 — Overhand (archived 2027-01-02)\n"
        "  - [x] K01a — Tied behind the back\n"
        "- [x] K02 — Figure eight\n"
        "- [ ] K00 — Dropped before done\n"
        "- [x] K03 — Bowline\n"
        "### Old splices\n"
        "- [x] S01 — Eye splice\n"
    )

    def test_archived_items_lead_their_line(self):
        lines = merge_archive(parse_progress(self.LIVE), parse_progress(self.ARCHIVE))
        self.assertEqual([line["title"] for line in lines], ["Old splices", "Knots"])
        knots = lines[1]["steps"]
        self.assertEqual([s["id"] for s in knots], ["K01", "K02", "K03", "K04"])
        self.assertEqual([s.get("archived", False) for s in knots], [True, True, False, False])
        self.assertTrue(knots[0]["children"][0]["archived"])
        self.assertEqual([s["id"] for s in knots if s["current"]], ["K03"])

    def test_collect_reads_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            shutil.copytree(ROOT, root)
            (root / "paper-lab" / "PROGRESS.md").write_text(self.LIVE, encoding="utf-8")
            (root / "paper-lab" / "ARCHIVE.md").write_text(self.ARCHIVE, encoding="utf-8")
            paper = collect(root)["branches"][0]
        self.assertEqual((paper["done"], paper["total"]), (4, 6))
