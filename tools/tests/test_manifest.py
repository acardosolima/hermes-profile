"""GENERATED.json contents, determinism, and write_output semantics."""

import hashlib
import json
import unittest

try:
    from . import support
except ImportError:
    import support


class ManifestBase(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)
        self.files = self.hs.generate(self.root, self.lock)
        self.text = self.files["GENERATED.json"].decode("utf-8")
        self.manifest = json.loads(self.text)


class GeneratedJsonTests(ManifestBase):
    def test_sorted_keys_two_space_indent_and_trailing_newline(self):
        expected = json.dumps(self.manifest, indent=2, sort_keys=True) + "\n"
        self.assertEqual(self.text, expected)

    def test_top_level_fields(self):
        self.assertEqual(self.manifest["generator_version"], "1")
        self.assertEqual(
            self.manifest["upstream"],
            {"repo": str(self.root), "sha": self.sha, "tag": self.tag},
        )

    def test_lists_allowlisted_skills_only(self):
        self.assertEqual(set(self.manifest["skills"]), set(support.ALLOWLIST_NAMES))

    def test_lists_every_generated_file_except_itself(self):
        listed = {
            "%s/%s" % (name, rel)
            for name, entry in self.manifest["skills"].items()
            for rel in entry["files"]
        }
        self.assertEqual(listed, set(self.files) - {"GENERATED.json"})

    def test_hashes_match_generated_content(self):
        for name, entry in self.manifest["skills"].items():
            for rel, digest in entry["files"].items():
                with self.subTest(file="%s/%s" % (name, rel)):
                    content = self.files["%s/%s" % (name, rel)]
                    self.assertEqual(digest, hashlib.sha256(content).hexdigest())

    def test_every_skill_has_unresolved_list(self):
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                self.assertIsInstance(self.manifest["skills"][name]["unresolved"], list)

    def test_unresolved_token_recorded(self):
        unresolved = self.manifest["skills"]["harness-plan"]["unresolved"]
        self.assertTrue(any("CLAUDE_FOO" in token for token in unresolved), unresolved)

    def test_resolved_tokens_not_recorded(self):
        self.assertEqual(self.manifest["skills"]["harness-work"]["unresolved"], [])
        for token in self.manifest["skills"]["harness-plan"]["unresolved"]:
            self.assertNotIn("CLAUDE_SKILL_DIR", token)
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", token)

    def test_manifest_is_named_without_leading_dot(self):
        self.assertIn("GENERATED.json", self.files)
        self.assertFalse(any(key.endswith(".GENERATED.json") for key in self.files))


class DeterminismTests(ManifestBase):
    def test_two_runs_are_byte_identical(self):
        second = self.hs.generate(self.root, self.lock)
        self.assertEqual(set(second), set(self.files))
        for key in self.files:
            with self.subTest(file=key):
                self.assertEqual(second[key], self.files[key])

    def test_output_does_not_depend_on_upstream_location(self):
        copy = support.copy_upstream(self.root, self.tmp / "elsewhere")
        self.assertEqual(self.hs.generate(copy, self.lock), self.files)

    def test_values_are_bytes_and_paths_are_relative(self):
        for key, value in self.files.items():
            with self.subTest(file=key):
                self.assertIsInstance(value, bytes)
                self.assertFalse(key.startswith("/"))
                self.assertNotIn("..", key.replace("\\", "/").split("/"))


class WriteOutputTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.target = self.tmp / "skills-harness"

    def test_writes_exact_bytes_and_creates_missing_target(self):
        files = {"a/SKILL.md": b"A\n", "GENERATED.json": b"{}\n"}
        target = self.tmp / "nested" / "out"
        self.hs.write_output(files, target)
        self.assertEqual(support.snapshot(target), files)

    def test_removes_files_absent_from_new_output(self):
        self.target.mkdir()
        support.put(self.target, "old/stale.md", b"stale")
        support.put(self.target, "a/SKILL.md", b"old")
        self.hs.write_output({"a/SKILL.md": b"new\n"}, self.target)
        self.assertEqual(support.snapshot(self.target), {"a/SKILL.md": b"new\n"})

    def test_failure_keeps_previous_contents(self):
        support.put(self.target, "a/SKILL.md", b"old\n")
        support.put(self.target, "keep.md", b"keep\n")
        before = support.snapshot(self.target)
        files = {"a/SKILL.md": b"new\n", "broken.md": None}
        with self.assertRaises((TypeError, AttributeError, OSError)):
            self.hs.write_output(files, self.target)
        self.assertEqual(support.snapshot(self.target), before)


if __name__ == "__main__":
    unittest.main()
