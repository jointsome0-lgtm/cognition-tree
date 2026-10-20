"""Exercise command-line success and readable failures."""

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_tree.__main__ import main


PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "tests" / "fixtures" / "root"


class CliTests(unittest.TestCase):
    def error_message(self, arguments):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            main(arguments)
        self.assertNotEqual(error.exception.code, 0)
        self.assertNotIn("Traceback", stderr.getvalue())
        return stderr.getvalue()

    def test_missing_or_nondirectory_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            message = self.error_message(["--root", str(root), "--json-only"])
            self.assertIn("Root directory is missing", message)
            root.write_text("An ordinary file.", encoding="utf-8")
            message = self.error_message(["--root", str(root), "--json-only"])
            self.assertIn("not a directory", message)

    def test_missing_hub_readme_or_table(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = ["--root", directory, "--hub", "custom-hub", "--json-only"]
            message = self.error_message(arguments)
            self.assertIn("Hub table is missing", message)
            self.assertIn("custom-hub", message)
            hub = Path(directory) / "custom-hub"
            hub.mkdir()
            (hub / "README.md").write_text("# No branch table here.\n", encoding="utf-8")
            self.assertIn("Hub table is missing", self.error_message(arguments))

    def test_template_failure_and_json_only_success(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            arguments = ["--root", str(ROOT), "--out", str(out)]
            with patch("cognition_tree.build.TEMPLATE_PATH", Path(directory) / "absent.html"):
                self.assertIn("Template is missing", self.error_message(arguments))
                self.assertEqual(main(arguments + ["--json-only"]), 0)
            self.assertTrue((out / "tree.json").is_file())
            self.assertFalse((out / "index.html").exists())

    def test_module_entry_point(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "nested" / "out"
            result = subprocess.run(
                [
                    sys.executable, "-m", "cognition_tree",
                    "--root", str(ROOT), "--hub", "learning-hub",
                    "--out", str(out), "--json-only",
                ],
                cwd=PROJECT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            tree = json.loads((out / "tree.json").read_text(encoding="utf-8"))
            self.assertEqual(len(tree["branches"]), 4)
            self.assertFalse(tree["branches"][-1]["found"])
