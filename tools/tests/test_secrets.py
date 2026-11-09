"""scan_secrets: each token-shaped pattern fails, boundary lengths pass."""

import unittest

try:
    from . import support
except ImportError:
    import support


class ScanSecretsTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)

    def test_each_secret_pattern_raises_and_names_the_path(self):
        for label, sample in support.SECRET_POSITIVE:
            with self.subTest(pattern=label):
                files = {"skills/harness-plan/references/leak.md": ("text " + sample + " more\n").encode("utf-8")}
                with self.assertRaises(self.hs.SecretFoundError) as caught:
                    self.hs.scan_secrets(files)
                self.assertIn("leak.md", str(caught.exception))

    def test_each_near_miss_passes(self):
        for label, sample in support.SECRET_NEGATIVE:
            with self.subTest(case=label):
                files = {"skills/harness-plan/references/notes.md": ("text " + sample + " more\n").encode("utf-8")}
                self.assertIsNone(self.hs.scan_secrets(files))

    def test_secret_in_skill_md_is_detected(self):
        files = {"harness-plan/SKILL.md": b"token sk-ant-abcdefghij here\n"}
        with self.assertRaises(self.hs.SecretFoundError):
            self.hs.scan_secrets(files)

    def test_clean_generated_output_passes(self):
        files = self.hs.generate(self.root, self.lock)
        self.assertIsNone(self.hs.scan_secrets(files))


if __name__ == "__main__":
    unittest.main()
