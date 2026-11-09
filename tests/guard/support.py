"""Shared helpers for the harness-guard tests. Command text is data; nothing is executed."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = ROOT / "plugins" / "harness-guard"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import adapter  # noqa: E402,F401  (re-exported for the tests)
import binaries  # noqa: E402,F401  (re-exported for the tests)

REQUIRE_BINARY = os.environ.get("HARNESS_GUARD_REQUIRE_BINARY") == "1"


def load_json(name):
    base = PLUGIN_DIR if name == "cases.json" else Path(__file__).parent
    return json.loads((base / name).read_text(encoding="utf-8"))


def expected(case):
    """Expected label for this platform: `expect_windows` overrides `expect` on Windows."""
    return case.get("expect_windows", case["expect"]) if os.name == "nt" else case["expect"]


def real_lock():
    return binaries.load_lock(PLUGIN_DIR / binaries.LOCK_NAME)


_BINARY_CACHE = {}


def real_binary():
    """Path of the verified upstream binary, or None when it cannot be obtained."""
    if "path" not in _BINARY_CACHE:
        cache = Path(os.environ.get("HARNESS_GUARD_CACHE") or Path(tempfile.gettempdir()) / "harness-guard-test-cache")
        try:
            _BINARY_CACHE["path"] = binaries.ensure_binary(real_lock(), cache)
        except binaries.BinaryError as exc:
            _BINARY_CACHE["path"] = None
            _BINARY_CACHE["error"] = str(exc)
    return _BINARY_CACHE["path"]


def _remove_tree(path):
    shutil.rmtree(path, ignore_errors=True)


class TempCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="hg-guard-test-"))
        self.addCleanup(_remove_tree, self.tmp)

    def make_project(self):
        project = self.tmp / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        (project / "notes.txt").write_text("a\n", encoding="utf-8")
        return project
