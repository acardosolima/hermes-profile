"""The guard lock: pinned binary hashes and upstream rule ids written by sync and verified by check."""

import hashlib
import json
import os
import subprocess
import sys
import unittest

try:
    from . import support
except ImportError:
    import support

RULES_GO = """package policy

var Rules = []GuardRule{
	{
		ID:          "R02:no-write-protected-paths",
	},
	{
		ID:          "R01:no-sudo",
	},
	{
		ID:          "R01:no-sudo",
	},
}
"""


class GuardLockCase(support.TempCase):
    def setUp(self):
        super().setUp()
        root, tag, sha = support.shared_upstream()
        self.upstream = support.copy_upstream(root, self.tmp / "u")
        self.lock = support.lock_for(self.upstream, tag, sha)
        support.put(self.upstream, "bin/harness-linux-amd64", b"linux-bytes")
        support.put(self.upstream, "bin/harness-darwin-arm64", b"darwin-bytes")
        support.put(self.upstream, "bin/harness-windows-amd64.exe", b"windows-bytes")
        support.put(self.upstream, "bin/harness", b"#!/bin/sh\nexec wrapper\n")
        support.put(self.upstream, "bin/readme.txt", b"not a binary")
        support.put(self.upstream, "go/internal/policy/rules.go", RULES_GO)

    def build(self):
        return json.loads(self.hs.guard_lock(self.upstream, self.lock).decode("utf-8"))


class GuardLockContentTests(GuardLockCase):
    def test_binaries_are_keyed_by_platform_with_their_hash(self):
        entries = self.build()["binaries"]
        self.assertEqual(sorted(entries), ["darwin-arm64", "linux-amd64", "windows-amd64"])
        self.assertEqual(entries["linux-amd64"]["sha256"], hashlib.sha256(b"linux-bytes").hexdigest())
        self.assertEqual(entries["linux-amd64"]["file"], "bin/harness-linux-amd64")
        self.assertEqual(entries["windows-amd64"]["file"], "bin/harness-windows-amd64.exe")

    def test_wrapper_script_and_other_files_are_ignored(self):
        files = {entry["file"] for entry in self.build()["binaries"].values()}
        self.assertNotIn("bin/harness", files)
        self.assertNotIn("bin/readme.txt", files)

    def test_rules_are_sorted_and_unique(self):
        self.assertEqual(self.build()["rules"], ["R01:no-sudo", "R02:no-write-protected-paths"])

    def test_release_identity_is_recorded(self):
        built = self.build()
        self.assertEqual((built["tag"], built["sha"], built["repo"]), (self.lock["tag"], self.lock["sha"], self.lock["repo"]))

    def test_serialization_is_stable(self):
        first = self.hs.guard_lock(self.upstream, self.lock)
        self.assertEqual(first, self.hs.guard_lock(self.upstream, self.lock))
        self.assertEqual(first.decode("utf-8"), json.dumps(json.loads(first), indent=2, sort_keys=True) + "\n")

    def test_missing_bin_directory_and_rules_file_give_empty_tables(self):
        bare = support.copy_upstream(support.shared_upstream()[0], self.tmp / "bare")
        built = json.loads(self.hs.guard_lock(bare, self.lock).decode("utf-8"))
        self.assertEqual((built["binaries"], built["rules"]), ({}, []))

    def test_symlinked_binary_is_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        link = self.upstream / "bin/harness-darwin-amd64"
        try:
            os.symlink(str(self.upstream / "bin/harness-linux-amd64"), str(link))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(self.hs.TranslateError):
            self.hs.guard_lock(self.upstream, self.lock)


class GuardLockFileTests(GuardLockCase):
    def test_write_then_check_is_clean(self):
        path = self.tmp / "out" / "plugins" / "binaries.lock.json"
        self.hs.write_guard_lock(self.hs.guard_lock(self.upstream, self.lock), path)
        self.assertEqual(self.hs.check_guard_lock(self.upstream, self.lock, path), [])

    def test_missing_file_is_reported_as_added(self):
        path = self.tmp / "absent.json"
        self.assertEqual(self.hs.check_guard_lock(self.upstream, self.lock, path), [f"added {path.as_posix()}"])

    def test_edited_file_is_reported_as_changed(self):
        path = self.tmp / "lock.json"
        self.hs.write_guard_lock(self.hs.guard_lock(self.upstream, self.lock), path)
        path.write_bytes(path.read_bytes() + b" ")
        self.assertEqual(self.hs.check_guard_lock(self.upstream, self.lock, path), [f"changed {path.as_posix()}"])

    def test_a_new_upstream_rule_makes_the_lock_stale(self):
        path = self.tmp / "lock.json"
        self.hs.write_guard_lock(self.hs.guard_lock(self.upstream, self.lock), path)
        rules = self.upstream / "go/internal/policy/rules.go"
        rules.write_text(RULES_GO + '\n\t{\n\t\tID:          "R99:brand-new",\n\t},\n', encoding="utf-8")
        self.assertEqual(self.hs.check_guard_lock(self.upstream, self.lock, path), [f"changed {path.as_posix()}"])

    def test_write_replaces_an_existing_file_without_leftovers(self):
        path = self.tmp / "lock.json"
        path.write_text("old", encoding="utf-8")
        self.hs.write_guard_lock(b"new\n", path)
        self.assertEqual(path.read_bytes(), b"new\n")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir() if p.name.startswith("lock")), ["lock.json"])


class GuardLockCliTests(support.TempCase):
    def setUp(self):
        super().setUp()
        root, tag, sha = support.make_upstream(
            self.tmp / "x",
            overrides={
                "bin/harness-linux-amd64": b"linux-bytes",
                "go/internal/policy/rules.go": RULES_GO,
            },
        )
        self.root = root
        self.lock_path = self.tmp / "upstream.lock"
        support.write_lock(self.lock_path, support.lock_for(root, tag, sha))
        self.out = self.tmp / "skills"
        self.guard = self.tmp / "guard" / "binaries.lock.json"

    def run_cli(self, command):
        return subprocess.run(
            [sys.executable, str(support.CLI_PATH), command, "--lock", str(self.lock_path), "--out", str(self.out),
             "--source", str(self.root), "--guard-lock", str(self.guard)],
            cwd=str(self.tmp), env=support.isolated_env(), capture_output=True,
        )

    def test_sync_writes_the_guard_lock_and_check_accepts_it(self):
        self.assertEqual(self.run_cli("sync").returncode, 0)
        self.assertTrue(self.guard.is_file())
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_check_fails_on_a_hand_edited_guard_lock(self):
        self.run_cli("sync")
        self.guard.write_bytes(self.guard.read_bytes().replace(b"linux-amd64", b"linux-arm64"))
        proc = self.run_cli("check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("changed", proc.stdout.decode("utf-8"))

    def test_check_fails_when_the_guard_lock_is_missing(self):
        self.run_cli("sync")
        os.remove(str(self.guard))
        proc = self.run_cli("check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("added", proc.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
