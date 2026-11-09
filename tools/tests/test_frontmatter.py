"""split_frontmatter: leading key/value block, quoting, BOM and CRLF handling."""

import unittest

try:
    from . import support
except ImportError:
    import support


class SplitFrontmatterTests(unittest.TestCase):
    def setUp(self):
        self.hs = support.harness_sync()

    def test_bare_quoted_and_hyphenated_scalars(self):
        text = (
            "---\n"
            "name: alpha\n"
            'description: "Review: diffs"\n'
            "other: 'single quoted'\n"
            "description-en: Hello there\n"
            "---\n"
            "Body line\n"
        )
        meta, body = self.hs.split_frontmatter(text)
        self.assertEqual(meta["name"], "alpha")
        self.assertEqual(meta["description"], "Review: diffs")
        self.assertEqual(meta["other"], "single quoted")
        self.assertEqual(meta["description-en"], "Hello there")
        self.assertEqual(body.strip(), "Body line")

    def test_body_excludes_frontmatter_lines(self):
        text = "---\nname: alpha\n---\nBody line\n"
        _, body = self.hs.split_frontmatter(text)
        self.assertNotIn("name:", body)

    def test_no_frontmatter_returns_empty_dict_and_whole_text(self):
        text = "# Title\n\nBody\n"
        meta, body = self.hs.split_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_utf8_bom_is_accepted(self):
        meta, _ = self.hs.split_frontmatter("﻿---\nname: alpha\n---\nBody\n")
        self.assertEqual(meta["name"], "alpha")

    def test_crlf_newlines_are_accepted(self):
        text = "---\r\nname: alpha\r\ndescription: Beta\r\n---\r\nBody\r\n"
        meta, body = self.hs.split_frontmatter(text)
        self.assertEqual(meta["name"], "alpha")
        self.assertEqual(meta["description"], "Beta")
        for value in meta.values():
            self.assertNotIn("\r", value)
        self.assertEqual(body.strip(), "Body")


if __name__ == "__main__":
    unittest.main()
