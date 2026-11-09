"""Manifest and bundling behavior on constructs found in the real upstream."""

import json
import unittest

try:
    from . import support
except ImportError:
    import support


class EdgeCaseTests(support.TempCase):
    def setUp(self):
        super().setUp()
        root, tag, sha = support.shared_upstream()
        self.upstream = support.copy_upstream(root, self.tmp / "u")
        self.lock = support.lock_for(self.upstream, tag, sha)

    def append(self, rel, text):
        path = self.upstream / rel
        path.write_bytes(path.read_bytes() + text.encode("utf-8"))

    def manifest(self):
        files = self.hs.generate(self.upstream, self.lock)
        return json.loads(files["GENERATED.json"].decode("utf-8")), files

    def test_unresolved_records_expansions_with_default_suffix(self):
        self.append("skills/harness-work/SKILL.md", "\nUse ${CLAUDE_PLUGIN_ROOT:-} and ${CLAUDE_SKILL_DIR:-x}.\n")
        manifest, _ = self.manifest()
        unresolved = manifest["skills"]["harness-work"]["unresolved"]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", unresolved)
        self.assertIn("${CLAUDE_SKILL_DIR}", unresolved)

    def test_unresolved_has_no_duplicates(self):
        self.append("skills/harness-work/SKILL.md", "\n${CLAUDE_BAR} ${CLAUDE_BAR:-} ${CLAUDE_BAR}\n")
        manifest, _ = self.manifest()
        unresolved = manifest["skills"]["harness-work"]["unresolved"]
        self.assertEqual(unresolved.count("${CLAUDE_BAR}"), 1)
        self.assertEqual(unresolved, sorted(unresolved))

    def test_missing_script_token_is_recorded(self):
        self.append("skills/harness-work/SKILL.md", "\nRun scripts/no-such-file.sh next.\n")
        manifest, files = self.manifest()
        entry = manifest["skills"]["harness-work"]
        self.assertIn("scripts/no-such-file.sh", entry["missing_scripts"])
        self.assertNotIn("harness-work/scripts/no-such-file.sh", files)

    def test_missing_scripts_key_is_present_and_sorted_for_every_skill(self):
        manifest, _ = self.manifest()
        for name, entry in manifest["skills"].items():
            with self.subTest(skill=name):
                self.assertIsInstance(entry["missing_scripts"], list)
                self.assertEqual(entry["missing_scripts"], sorted(entry["missing_scripts"]))

    def test_directory_token_is_neither_bundled_nor_missing(self):
        support.put(self.upstream, "scripts/ci/run.sh", "echo ci\n")
        self.append("skills/harness-work/SKILL.md", "\nSee scripts/ci/ for details.\n")
        manifest, files = self.manifest()
        missing = manifest["skills"]["harness-work"]["missing_scripts"]
        self.assertNotIn("scripts/ci/", missing)
        self.assertNotIn("scripts/ci", missing)
        self.assertNotIn("harness-work/scripts/ci/run.sh", files)

    def test_sentence_ending_dot_does_not_hide_script(self):
        support.put(self.upstream, "scripts/dot-case.sh", "echo dot\n")
        self.append("skills/harness-work/SKILL.md", "\nSee scripts/dot-case.sh.\n")
        manifest, files = self.manifest()
        self.assertIn("harness-work/scripts/dot-case.sh", files)
        self.assertNotIn("scripts/dot-case.sh", manifest["skills"]["harness-work"]["missing_scripts"])

    def test_preamble_points_to_bundled_scripts_directory(self):
        _, files = self.manifest()
        text = files["harness-work/SKILL.md"].decode("utf-8")
        self.assertIn("scripts/ directory", text)


if __name__ == "__main__":
    unittest.main()
