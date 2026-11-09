"""load_lock: valid lock files and the LockError cases."""

import json
import unittest

try:
    from . import support
except ImportError:
    import support


class LoadLockTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.path = self.tmp / "upstream.lock"
        self.good = support.lock_for("https://example.invalid/harness.git", support.TAG, "a" * 40)

    def write_obj(self, obj):
        self.path.write_text(json.dumps(obj), encoding="utf-8")

    def test_valid_lock_returns_repo_tag_and_sha(self):
        self.write_obj(self.good)
        loaded = self.hs.load_lock(self.path)
        for key, value in self.good.items():
            self.assertEqual(loaded[key], value)

    def test_missing_file_raises_lock_error(self):
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(self.tmp / "absent.lock")

    def test_bad_json_raises_lock_error(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(self.path)

    def test_missing_key_raises_lock_error(self):
        for key in ("repo", "tag", "sha"):
            with self.subTest(missing=key):
                obj = dict(self.good)
                del obj[key]
                self.write_obj(obj)
                with self.assertRaises(self.hs.LockError):
                    self.hs.load_lock(self.path)

    def test_sha_must_be_forty_lowercase_hex(self):
        bad_shas = [
            "a" * 39,
            "a" * 41,
            "A" * 40,
            "G" * 40,
            "z" * 40,
            "",
            "a" * 39 + " ",
        ]
        for sha in bad_shas:
            with self.subTest(sha=sha):
                obj = dict(self.good)
                obj["sha"] = sha
                self.write_obj(obj)
                with self.assertRaises(self.hs.LockError):
                    self.hs.load_lock(self.path)

    def test_sha_of_forty_lowercase_hex_is_accepted(self):
        obj = dict(self.good)
        obj["sha"] = "0123456789abcdef0123456789abcdef01234567"
        self.write_obj(obj)
        self.assertEqual(self.hs.load_lock(self.path)["sha"], obj["sha"])


if __name__ == "__main__":
    unittest.main()
