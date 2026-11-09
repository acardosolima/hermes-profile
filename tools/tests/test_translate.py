"""Translation rules 1 to 8 and 11 for translate_skill and generate."""

import shutil
import unittest

try:
    from . import support
except ImportError:
    import support


class TranslateBase(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)

    def translate(self, name, root=None):
        return self.hs.translate_skill(name, root or self.root, self.lock)

    def text(self, name, rel="SKILL.md", root=None):
        return self.translate(name, root)[rel].decode("utf-8")

    def frontmatter(self, name, root=None):
        pairs, _ = support.parse_frontmatter(self.translate(name, root)["SKILL.md"])
        return dict(pairs)

    def copy_root(self):
        return support.copy_upstream(self.root, self.tmp / "copy")


class Rule1FrontmatterTests(TranslateBase):
    def test_output_keys_are_exact_and_ordered_for_every_allowlisted_skill(self):
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                pairs, _ = support.parse_frontmatter(self.translate(name)["SKILL.md"])
                self.assertEqual(
                    [key for key, _ in pairs],
                    ["name", "description", "version", "platforms"],
                )

    def test_name_version_and_platforms_values(self):
        values = self.frontmatter("harness-plan")
        self.assertEqual(values["name"], "harness-plan")
        self.assertEqual(values["version"], self.tag)
        platforms = [
            item.strip().strip("\"'")
            for item in values["platforms"].strip().strip("[]").split(",")
        ]
        self.assertEqual(platforms, ["linux", "macos", "windows"])

    def test_description_en_is_preferred(self):
        self.assertEqual(self.frontmatter("harness-plan")["description"], "Plan tasks in English.")

    def test_description_used_when_description_en_absent(self):
        self.assertEqual(self.frontmatter("harness-work")["description"], "Work through tasks")

    def test_quoted_description_is_unwrapped(self):
        self.assertEqual(self.frontmatter("harness-review")["description"], "Review: diffs")

    def test_description_en_alone_is_accepted(self):
        root = self.copy_root()
        support.put(
            root,
            "skills/harness-setup/SKILL.md",
            "---\nname: harness-setup\ndescription-en: English only\nkind: skill\n---\n# Body\n",
        )
        self.assertEqual(self.frontmatter("harness-setup", root)["description"], "English only")

    def test_description_truncated_to_1024_characters(self):
        expected = support.LONG_DESCRIPTION[:1024]
        value = self.frontmatter("harness-loop")["description"]
        self.assertEqual(len(value), 1024)
        self.assertEqual(value, expected)

    def test_truncation_counts_characters_not_bytes(self):
        root = self.copy_root()
        support.put(
            root,
            "skills/harness-loop/SKILL.md",
            "---\nname: harness-loop\ndescription-en: " + "あ" * 1500 + "\nkind: skill\n---\n# Loop\n",
        )
        value = self.frontmatter("harness-loop", root)["description"]
        self.assertEqual(value, "あ" * 1024)

    def test_upstream_only_keys_are_dropped(self):
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                keys = {key for key, _ in support.parse_frontmatter(self.translate(name)["SKILL.md"])[0]}
                self.assertNotIn("allowed-tools", keys)
                self.assertNotIn("kind", keys)
                self.assertNotIn("description-ja", keys)

    def test_missing_name_raises_translate_error(self):
        root = self.copy_root()
        support.put(
            root,
            "skills/harness-setup/SKILL.md",
            "---\ndescription: Set up the harness\n---\n# Body\n",
        )
        with self.assertRaises(self.hs.TranslateError):
            self.translate("harness-setup", root)

    def test_missing_description_raises_translate_error(self):
        root = self.copy_root()
        support.put(
            root,
            "skills/harness-setup/SKILL.md",
            "---\nname: harness-setup\nkind: skill\n---\n# Body\n",
        )
        with self.assertRaises(self.hs.TranslateError):
            self.translate("harness-setup", root)


class Rule2SkillDirTests(TranslateBase):
    def test_prefix_removed_from_skill_md(self):
        text = self.text("harness-plan")
        self.assertIn("Read the procedure in references/plan.md first.", text)
        self.assertNotIn("${CLAUDE_SKILL_DIR}", text)

    def test_bare_token_becomes_dot(self):
        self.assertIn("Skill root is . here.", self.text("harness-plan"))

    def test_prefix_removed_in_references_markdown(self):
        self.assertIn(
            "Follow the steps in references/detail.md.",
            self.text("harness-plan", "references/plan.md"),
        )


class Rule3PluginRootTests(TranslateBase):
    def test_claude_plugin_root_scripts_prefix_rewritten(self):
        text = self.text("harness-work")
        self.assertIn("Run scripts/run-tasks.sh to start the loop.", text)
        self.assertNotIn("PLUGIN_ROOT", text)

    def test_harness_plugin_root_scripts_prefix_rewritten(self):
        text = self.text("harness-plan")
        self.assertIn("Run the checker with scripts/plan-check.sh before writing.", text)
        self.assertNotIn("HARNESS_PLUGIN_ROOT", text)

    def test_rewrite_applies_in_references_markdown(self):
        self.assertIn(
            "Render with scripts/plan-check.sh when needed.",
            self.text("harness-plan", "references/plan.md"),
        )
        self.assertIn(
            "Batch rendering: scripts/render.py --all",
            self.text("harness-work", "references/work-detail.md"),
        )


class Rule4PreambleTests(TranslateBase):
    def test_preamble_directly_follows_frontmatter(self):
        for name in ("harness-plan", "harness-review"):
            with self.subTest(skill=name):
                _, body = support.parse_frontmatter(self.translate(name)["SKILL.md"])
                self.assertTrue(body.lstrip("\r\n").startswith(support.PREAMBLE_START))

    def test_preamble_appears_exactly_once_per_skill(self):
        for name in support.ALLOWLIST_NAMES:
            with self.subTest(skill=name):
                text = self.text(name)
                self.assertEqual(text.count(support.PREAMBLE_START), 1)
                self.assertEqual(text.count(support.PREAMBLE_END), 1)

    def test_preamble_is_identical_across_skills(self):
        blocks = {support.preamble_block(self.text(name)) for name in support.ALLOWLIST_NAMES}
        self.assertEqual(len(blocks), 1)

    def test_preamble_names_mapping_and_guardrail_status(self):
        block = support.preamble_block(self.text("harness-plan"))
        self.assertIn("Claude Code", block)
        self.assertIn("Hermes", block)
        self.assertRegex(block, r"(?i)guardrail")
        self.assertRegex(block, r"(?i)not\s+enforced")

    def test_original_body_follows_preamble(self):
        after = self.text("harness-plan").split(support.PREAMBLE_END, 1)[1]
        self.assertIn("# Harness plan", after)
        self.assertIn("Skill root is . here.", after)


class Rule5ReferencesTests(TranslateBase):
    def test_non_markdown_reference_copied_byte_for_byte(self):
        original = support.fixture_files()["skills/harness-plan/references/data.json"]
        self.assertEqual(self.translate("harness-plan")["references/data.json"], original)

    def test_every_reference_file_is_emitted(self):
        keys = set(self.translate("harness-plan"))
        self.assertTrue(
            {"SKILL.md", "references/plan.md", "references/detail.md", "references/data.json"} <= keys
        )


class Rule7LfAndBomTests(TranslateBase):
    def test_text_outputs_use_lf_newlines_only(self):
        for name in support.ALLOWLIST_NAMES:
            for rel, data in self.translate(name).items():
                if rel.endswith((".md", ".json")):
                    with self.subTest(skill=name, file=rel):
                        self.assertNotIn(b"\r", data)

    def test_no_output_starts_with_bom(self):
        for name in support.ALLOWLIST_NAMES:
            for rel, data in self.translate(name).items():
                with self.subTest(skill=name, file=rel):
                    self.assertFalse(data.startswith(support.UTF8_BOM))

    def test_bom_input_is_translated(self):
        self.assertEqual(self.frontmatter("harness-review")["name"], "harness-review")

    def test_crlf_input_is_translated(self):
        values = self.frontmatter("harness-sync")
        self.assertEqual(values["name"], "harness-sync")
        self.assertEqual(values["description"], "Sync the harness")


class Rule8UnresolvedTests(TranslateBase):
    def test_unresolved_token_is_kept_in_text(self):
        self.assertIn("${CLAUDE_FOO}", self.text("harness-plan"))

    def test_resolved_claude_tokens_are_not_left_behind(self):
        for name in ("harness-plan", "harness-work"):
            with self.subTest(skill=name):
                text = self.text(name)
                self.assertNotIn("${CLAUDE_SKILL_DIR}", text)
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", text)


class Rule11AllowlistTests(TranslateBase):
    def test_non_allowlisted_skill_is_never_read(self):
        root = self.copy_root()
        support.put(root, "skills/cursor-ask/SKILL.md", b"\xff\xfe\x00 not a parseable skill")
        files = self.hs.generate(root, self.lock)
        self.assertFalse(any("cursor-ask" in key for key in files))

    def test_non_allowlisted_skill_and_its_script_absent_from_output(self):
        files = self.hs.generate(self.root, self.lock)
        self.assertFalse(any("cursor-ask" in key for key in files))
        self.assertFalse(any("cursor-only" in key for key in files))

    def test_missing_allowlisted_skill_raises_translate_error(self):
        root = self.copy_root()
        shutil.rmtree(str(root / "skills" / "harness-setup"))
        with self.assertRaises(self.hs.TranslateError):
            self.hs.generate(root, self.lock)
        with self.assertRaises(self.hs.TranslateError):
            self.translate("harness-setup", root)

    def test_generate_honours_custom_allowlist(self):
        files = self.hs.generate(self.root, self.lock, allowlist=("harness-plan",))
        self.assertIn("harness-plan/SKILL.md", files)
        for key in files:
            self.assertTrue(
                key == "GENERATED.json" or key.startswith("harness-plan/"),
                "unexpected key: %s" % key,
            )


if __name__ == "__main__":
    unittest.main()
