"""fetch_upstream: clone at the locked sha, reject a sha mismatch with no output."""

import unittest
from pathlib import Path

try:
    from . import support
except ImportError:
    import support


class FetchUpstreamTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)

    def test_clones_checkout_at_locked_sha(self):
        dest = self.tmp / "checkout"
        result = Path(self.hs.fetch_upstream(self.lock, dest))
        self.assertTrue(result.is_dir())
        self.assertTrue((result / "skills" / "harness-plan" / "SKILL.md").is_file())
        self.assertEqual(support.git_output(["rev-parse", "HEAD"], result), self.sha)

    def test_clone_url_argument_overrides_lock_repo(self):
        lock = support.lock_for(self.tmp / "no-such-repo", self.tag, self.sha)
        dest = self.tmp / "checkout"
        result = Path(self.hs.fetch_upstream(lock, dest, clone_url=str(self.root)))
        self.assertTrue((result / "skills" / "harness-plan" / "SKILL.md").is_file())

    def test_sha_mismatch_raises_and_leaves_no_files(self):
        dest = self.tmp / "checkout"
        lock = support.lock_for(self.root, self.tag, support.UNRELATED_SHA)
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(lock, dest)
        self.assertFalse(dest.exists())
        leftovers = [p.name for p in self.tmp.iterdir()]
        self.assertEqual(leftovers, [])

    def test_existing_empty_dir_is_rejected_and_left_empty(self):
        dest = self.tmp / "existing"
        dest.mkdir()
        lock = support.lock_for(self.root, self.tag, support.UNRELATED_SHA)
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(lock, dest)
        self.assertEqual(list(dest.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
