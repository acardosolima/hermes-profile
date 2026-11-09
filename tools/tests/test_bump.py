"""Release resolution and lock bumping against local git fixtures."""

import json
import subprocess
import sys
import unittest

try:
    from . import support
except ImportError:
    import support


class BumpCase(support.TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "remote"
        self.repo.mkdir()
        support.git_run(["init", "-q"], self.repo)
        self.shas = {}
        self.commit("one")
        self.tag("v1.0.0", annotated=True)
        self.commit("two")
        self.tag("v1.2.0", annotated=False)
        self.commit("three")
        self.tag("v1.10.0", annotated=True)
        self.commit("four")
        self.tag("v2.0.0-rc1", annotated=True)
        self.tag("latest", annotated=False)
        self.lock_path = self.tmp / "upstream.lock"

    def commit(self, name):
        support.put(self.repo, "f.txt", name + "\n")
        support.git_run(["add", "-A"], self.repo)
        support.git_run(["commit", "-q", "-m", name], self.repo, identity=True)
        self.last = support.git_output(["rev-parse", "HEAD"], self.repo)

    def tag(self, name, annotated):
        if annotated:
            support.git_run(["tag", "-a", name, "-m", name], self.repo, identity=True)
        else:
            support.git_run(["tag", name], self.repo, identity=True)
        self.shas[name] = self.last

    def write_lock(self, tag, sha=None):
        data = {"repo": str(self.repo), "tag": tag, "sha": sha or self.shas[tag]}
        self.lock_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def read_lock(self):
        return json.loads(self.lock_path.read_text(encoding="utf-8"))


class ResolveReleaseTests(BumpCase):
    def test_highest_numeric_release_wins_over_lexical_order(self):
        tag, _ = self.hs.resolve_release(str(self.repo))
        self.assertEqual(tag, "v1.10.0")

    def test_prerelease_and_non_version_tags_are_ignored(self):
        tag, _ = self.hs.resolve_release(str(self.repo))
        self.assertNotIn(tag, ("v2.0.0-rc1", "latest"))

    def test_annotated_tag_resolves_to_commit_sha(self):
        tag, sha = self.hs.resolve_release(str(self.repo))
        self.assertEqual(sha, self.shas[tag])
        tag_object = support.git_output(["rev-parse", "v1.10.0"], self.repo)
        self.assertNotEqual(tag_object, sha)

    def test_lightweight_tag_can_be_selected(self):
        self.assertEqual(self.hs.resolve_release(str(self.repo), "v1.2.0"), ("v1.2.0", self.shas["v1.2.0"]))

    def test_unknown_tag_raises(self):
        with self.assertRaises(self.hs.FetchError):
            self.hs.resolve_release(str(self.repo), "v9.9.9")

    def test_repo_without_release_tags_raises(self):
        other = self.tmp / "other"
        other.mkdir()
        support.git_run(["init", "-q"], other)
        support.put(other, "f.txt", "x\n")
        support.git_run(["add", "-A"], other)
        support.git_run(["commit", "-q", "-m", "x"], other, identity=True)
        support.git_run(["tag", "latest"], other, identity=True)
        with self.assertRaises(self.hs.FetchError):
            self.hs.resolve_release(str(other))

    def test_unreachable_repo_and_option_like_repo_raise(self):
        for repo in (str(self.tmp / "missing"), "--upload-pack=evil"):
            with self.subTest(repo=repo):
                with self.assertRaises(self.hs.FetchError):
                    self.hs.resolve_release(repo)


class BumpTests(BumpCase):
    def test_moves_forward_and_keeps_repo(self):
        self.write_lock("v1.0.0")
        self.assertEqual(self.hs.bump(self.lock_path), ("v1.0.0", "v1.10.0"))
        lock = self.read_lock()
        self.assertEqual(lock, {"repo": str(self.repo), "tag": "v1.10.0", "sha": self.shas["v1.10.0"]})
        self.assertEqual(
            self.lock_path.read_text(encoding="utf-8"),
            json.dumps(lock, indent=2, sort_keys=True) + "\n",
        )

    def test_at_latest_leaves_file_untouched(self):
        self.write_lock("v1.10.0")
        before = self.lock_path.read_bytes()
        self.assertEqual(self.hs.bump(self.lock_path), ("v1.10.0", "v1.10.0"))
        self.assertEqual(self.lock_path.read_bytes(), before)

    def test_never_downgrades_without_explicit_tag(self):
        self.commit("five")
        self.tag("v3.0.0", annotated=True)
        self.write_lock("v3.0.0")
        support.git_run(["tag", "-d", "v3.0.0"], self.repo)
        before = self.lock_path.read_bytes()
        self.assertEqual(self.hs.bump(self.lock_path), ("v3.0.0", "v3.0.0"))
        self.assertEqual(self.lock_path.read_bytes(), before)

    def test_explicit_older_tag_is_honored(self):
        self.write_lock("v1.10.0")
        self.assertEqual(self.hs.bump(self.lock_path, tag="v1.0.0"), ("v1.10.0", "v1.0.0"))
        self.assertEqual(self.read_lock()["sha"], self.shas["v1.0.0"])

    def test_moved_tag_raises_and_keeps_lock(self):
        self.write_lock("v1.10.0", sha="a" * 40)
        before = self.lock_path.read_bytes()
        with self.assertRaises(self.hs.FetchError):
            self.hs.bump(self.lock_path)
        self.assertEqual(self.lock_path.read_bytes(), before)

    def test_source_overrides_lock_repo_without_rewriting_it(self):
        data = {"repo": "https://example.invalid/x.git", "tag": "v1.0.0", "sha": self.shas["v1.0.0"]}
        self.lock_path.write_text(json.dumps(data), encoding="utf-8")
        self.hs.bump(self.lock_path, repo=str(self.repo))
        self.assertEqual(self.read_lock()["repo"], "https://example.invalid/x.git")


class BumpCliTests(BumpCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(support.CLI_PATH), "bump", "--lock", str(self.lock_path), *args],
            cwd=str(self.tmp),
            env=support.isolated_env(),
            capture_output=True,
        )

    def test_reports_bump_then_unchanged(self):
        self.write_lock("v1.0.0")
        first = self.run_cli()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.decode().strip(), "bumped v1.0.0 v1.10.0")
        second = self.run_cli()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.decode().strip(), "unchanged v1.10.0")

    def test_unreachable_source_exits_two_and_keeps_lock(self):
        self.write_lock("v1.0.0")
        before = self.lock_path.read_bytes()
        proc = self.run_cli("--source", str(self.tmp / "missing"))
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(b"Traceback", proc.stderr)
        self.assertEqual(self.lock_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
