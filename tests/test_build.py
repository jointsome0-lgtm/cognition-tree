"""Check page embedding without touching the frontend template."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from cognition_tree.build import build
from cognition_tree.collect import collect


FIXTURES = Path(__file__).parent / "fixtures"


class BuildTests(unittest.TestCase):
    def test_json_and_html_round_trip_with_less_than_escaping(self):
        tree = collect(FIXTURES / "root")
        tree["branches"][0]["title"] = '</script><script>fixture("△")</script> & <shape>'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "nested" / "out"
            with patch("cognition_tree.build.TEMPLATE_PATH", FIXTURES / "template.html"):
                build(tree, out)
            payload = (out / "tree.json").read_text(encoding="utf-8")
            page = (out / "index.html").read_text(encoding="utf-8")
        self.assertEqual(json.loads(payload), tree)
        self.assertIn("<shape>", payload)
        match = re.search(
            r'<script id="tree-data" type="application/json">(.*?)</script>', page, re.S
        )
        self.assertIsNotNone(match)
        embedded = match[1]
        self.assertNotIn("<", embedded)
        self.assertIn("\\u003c/script>", embedded)
        self.assertEqual(json.loads(embedded), tree)
        self.assertEqual(page.count("<script"), 1)
        self.assertNotIn("__TREE_DATA__", page)

    def test_json_only_does_not_need_a_template(self):
        tree = collect(FIXTURES / "root")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            with patch("cognition_tree.build.TEMPLATE_PATH", Path(directory) / "missing.html"):
                build(tree, out, json_only=True)
            self.assertEqual(json.loads((out / "tree.json").read_text(encoding="utf-8")), tree)
            self.assertFalse((out / "index.html").exists())

    def test_missing_template_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            with patch("cognition_tree.build.TEMPLATE_PATH", Path(directory) / "missing.html"):
                with self.assertRaisesRegex(ValueError, "Template is missing.*--json-only"):
                    build(collect(FIXTURES / "root"), out)
            self.assertFalse(out.exists())

    def test_template_requires_exactly_one_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "template.html"
            with patch("cognition_tree.build.TEMPLATE_PATH", template):
                for content in ("no placeholder", "__TREE_DATA__ __TREE_DATA__"):
                    with self.subTest(content=content):
                        template.write_text(content, encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, "exactly one"):
                            build(collect(FIXTURES / "root"), Path(directory) / "out")
