"""Command line entry point: exit codes 0, 1 and 2 and what each writes."""

import subprocess
import sys
import unittest

try:
    from . import support
except ImportError:
    import support


class CliTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.assertTrue(support.CLI_PATH.is_file(), "CLI entry point is missing")
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)
        self.lock_path = self.tmp / "upstream.lock"
        support.write_lock(self.lock_path, self.lock)
        self.out = self.tmp / "skills-harness"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(support.CLI_PATH), *args],
            cwd=str(self.tmp),
            env=support.isolated_env(),
            capture_output=True,
        )

    def cli(self, command, lock_path=None, out=None, source=None):
        args = [
            command,
            "--lock", str(lock_path or self.lock_path),
            "--out", str(out or self.out),
            "--source", str(source if source is not None else self.root),
        ]
        return self.run_cli(*args)

    @staticmethod
    def lines(proc):
        return [
            support.norm_line(line)
            for line in proc.stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]

    def test_sync_exits_zero_and_writes_generated_tree(self):
        proc = self.cli("sync")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", errors="replace"))
        self.assertTrue((self.out / "GENERATED.json").is_file())
        self.assertTrue((self.out / "harness-plan" / "SKILL.md").is_file())

    def test_sync_output_matches_generate_api(self):
        self.assertEqual(self.cli("sync").returncode, 0)
        expected = self.hs.generate(self.root, self.lock)
        self.assertEqual(support.snapshot(self.out), expected)

    def test_sync_twice_is_byte_identical(self):
        second = self.tmp / "second"
        self.assertEqual(self.cli("sync").returncode, 0)
        self.assertEqual(self.cli("sync", out=second).returncode, 0)
        self.assertEqual(support.snapshot(self.out), support.snapshot(second))

    def test_sync_removes_stale_files(self):
        support.put(self.out, "stale/old.md", b"stale\n")
        self.assertEqual(self.cli("sync").returncode, 0)
        self.assertNotIn("stale/old.md", support.snapshot(self.out))

    def test_check_after_sync_exits_zero(self):
        self.assertEqual(self.cli("sync").returncode, 0)
        self.assertEqual(self.cli("check").returncode, 0)

    def test_check_after_hand_edit_exits_one_with_diff_on_stdout(self):
        self.assertEqual(self.cli("sync").returncode, 0)
        path = self.out / "harness-plan" / "SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nhand edit\n")
        proc = self.cli("check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("changed harness-plan/SKILL.md", self.lines(proc))

    def test_check_after_removed_file_exits_one(self):
        self.assertEqual(self.cli("sync").returncode, 0)
        (self.out / "harness-review" / "SKILL.md").unlink()
        proc = self.cli("check")
        self.assertEqual(proc.returncode, 1)
        matches = [line for line in self.lines(proc) if line.endswith(" harness-review/SKILL.md")]
        self.assertEqual(len(matches), 1)
        self.assertIn(matches[0].split(" ", 1)[0], ("added", "removed"))

    def test_source_argument_overrides_lock_repo(self):
        lock = support.lock_for(self.tmp / "no-such-repo", self.tag, self.sha)
        lock_path = self.tmp / "other.lock"
        support.write_lock(lock_path, lock)
        self.assertEqual(self.cli("sync", lock_path=lock_path).returncode, 0)

    def test_wrong_sha_exits_two_and_writes_nothing(self):
        bad = support.lock_for(self.root, self.tag, support.UNRELATED_SHA)
        bad_path = self.tmp / "bad.lock"
        support.write_lock(bad_path, bad)
        proc = self.cli("sync", lock_path=bad_path)
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())
        self.assertFalse(self.out.exists())

    def test_wrong_sha_keeps_previous_output(self):
        support.put(self.out, "keep.md", b"keep\n")
        bad = support.lock_for(self.root, self.tag, support.UNRELATED_SHA)
        bad_path = self.tmp / "bad.lock"
        support.write_lock(bad_path, bad)
        self.assertEqual(self.cli("sync", lock_path=bad_path).returncode, 2)
        self.assertEqual(support.snapshot(self.out), {"keep.md": b"keep\n"})

    def test_check_with_wrong_sha_exits_two(self):
        bad = support.lock_for(self.root, self.tag, support.UNRELATED_SHA)
        bad_path = self.tmp / "bad.lock"
        support.write_lock(bad_path, bad)
        self.assertEqual(self.cli("check", lock_path=bad_path).returncode, 2)

    def test_missing_lock_exits_two(self):
        proc = self.cli("sync", lock_path=self.tmp / "absent.lock")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())
        self.assertFalse(self.out.exists())

    def test_malformed_lock_exits_two(self):
        bad_path = self.tmp / "malformed.lock"
        bad_path.write_text("{broken", encoding="utf-8")
        proc = self.cli("sync", lock_path=bad_path)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(self.out.exists())

    def test_unknown_subcommand_exits_two(self):
        self.assertEqual(self.run_cli("bogus").returncode, 2)

    def test_secret_pattern_exits_two_and_writes_nothing(self):
        base = support.fixture_files()["skills/harness-setup/SKILL.md"]
        for index, (label, sample) in enumerate(support.SECRET_POSITIVE):
            with self.subTest(pattern=label):
                overrides = {
                    "skills/harness-setup/SKILL.md": base + ("Leaked: " + sample + "\n").encode("utf-8"),
                }
                root, tag, sha = support.make_upstream(self.tmp / ("src-%d" % index), overrides)
                lock_path = self.tmp / ("lock-%d.lock" % index)
                support.write_lock(lock_path, support.lock_for(root, tag, sha))
                out = self.tmp / ("out-%d" % index)
                support.put(out, "keep.md", b"keep\n")
                proc = self.cli("sync", lock_path=lock_path, out=out, source=root)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(support.snapshot(out), {"keep.md": b"keep\n"})


if __name__ == "__main__":
    unittest.main()
