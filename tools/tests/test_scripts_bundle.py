"""Rule 6: bundling of upstream helper scripts referenced by skills."""

import re
import unittest

try:
    from . import support
except ImportError:
    import support

SCRIPT_TOKEN = re.compile(r"scripts/[A-Za-z0-9_.\-]*[A-Za-z0-9_]")


class ScriptBundleTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)
        self.fixture = support.fixture_files()

    def translate(self, name, root=None):
        return self.hs.translate_skill(name, root or self.root, self.lock)

    def test_referenced_script_copied_byte_for_byte(self):
        out = self.translate("harness-plan")
        self.assertEqual(out["scripts/plan-check.sh"], self.fixture["scripts/plan-check.sh"])

    def test_transitively_referenced_scripts_are_followed(self):
        out = self.translate("harness-work")
        for rel in (
            "scripts/run-tasks.sh",
            "scripts/common.sh",
            "scripts/render.py",
            "scripts/format-util.sh",
        ):
            with self.subTest(script=rel):
                self.assertIn(rel, out)
                self.assertEqual(out[rel], self.fixture[rel])

    def test_unreferenced_script_is_never_copied(self):
        files = self.hs.generate(self.root, self.lock)
        self.assertFalse(any("unused-helper" in key for key in files))
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                self.assertFalse(any("unused-helper" in rel for rel in self.translate(name)))

    def test_script_of_non_allowlisted_skill_is_never_copied(self):
        files = self.hs.generate(self.root, self.lock)
        self.assertFalse(any("cursor-only" in key for key in files))

    def test_scripts_are_bundled_per_skill(self):
        out = self.translate("harness-plan")
        self.assertNotIn("scripts/common.sh", out)
        self.assertNotIn("scripts/render.py", out)
        self.assertNotIn("scripts/format-util.sh", out)

    def test_every_script_referenced_by_a_generated_skill_exists_in_output(self):
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                out = self.translate(name)
                for rel, data in out.items():
                    if not (rel == "SKILL.md" or (rel.startswith("references/") and rel.endswith(".md"))):
                        continue
                    text = data.decode("utf-8")
                    if support.PREAMBLE_END in text:
                        text = text.split(support.PREAMBLE_END, 1)[1]
                    for token in SCRIPT_TOKEN.findall(text):
                        self.assertIn(token, out, "%s in %s is missing from output" % (token, rel))

    def test_token_matching_no_upstream_file_is_tolerated(self):
        root = support.copy_upstream(self.root, self.tmp / "copy")
        plan = self.fixture["skills/harness-plan/SKILL.md"] + b"Unknown helper scripts/does-not-exist.sh here.\n"
        support.put(root, "skills/harness-plan/SKILL.md", plan)
        out = self.translate("harness-plan", root)
        self.assertFalse(any("does-not-exist" in rel for rel in out))
        self.assertIn("SKILL.md", out)


if __name__ == "__main__":
    unittest.main()
