"""Smoke: the module imports, exposes the public API, and ALLOWLIST is correct."""

import unittest

try:
    from . import support
except ImportError:
    import support

PUBLIC_NAMES = (
    "ALLOWLIST",
    "LockError",
    "FetchError",
    "TranslateError",
    "SecretFoundError",
    "load_lock",
    "fetch_upstream",
    "split_frontmatter",
    "translate_skill",
    "generate",
    "write_output",
    "check",
    "scan_secrets",
    "main",
)


class SmokeTests(support.TempCase):
    def test_module_imports(self):
        self.assertTrue(hasattr(self.hs, "__file__"))

    def test_allowlist_has_the_eight_skill_names(self):
        self.assertEqual(set(self.hs.ALLOWLIST), set(support.ALLOWLIST_NAMES))
        self.assertEqual(len(self.hs.ALLOWLIST), 8)

    def test_allowlist_is_a_tuple(self):
        self.assertIsInstance(self.hs.ALLOWLIST, tuple)

    def test_public_api_is_defined(self):
        for name in PUBLIC_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(self.hs, name))

    def test_shared_fixture_contains_every_allowlisted_skill(self):
        root, _, _ = support.shared_upstream()
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                self.assertTrue((root / "skills" / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
