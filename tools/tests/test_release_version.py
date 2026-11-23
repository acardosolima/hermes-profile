import unittest

from release_version import parse_subject, plan_version, set_version_line


class PlanVersionTests(unittest.TestCase):
    def test_no_tags_publishes_current_without_increment(self):
        decision = plan_version("1.0.0", [], has_tags=False)
        self.assertEqual(decision, ("publish", "1.0.0"))

    def test_no_releasable_commits_does_nothing(self):
        commits = [("docs", "rewrite readme", ""), ("ci", "add workflow", "")]
        self.assertEqual(plan_version("1.0.0", commits, has_tags=True), ("none", "1.0.0"))

    def test_fix_bumps_patch(self):
        self.assertEqual(
            plan_version("1.0.0", [("fix", "keep search usable", "")], has_tags=True),
            ("bump", "1.0.1"),
        )

    def test_config_and_chore_bump_patch(self):
        commits = [("config", "add hook", ""), ("chore", "bump harness to v5.16.0", "")]
        self.assertEqual(plan_version("1.2.3", commits, has_tags=True), ("bump", "1.2.4"))

    def test_feat_bumps_minor_and_resets_patch(self):
        commits = [("fix", "a", ""), ("feat", "b", "")]
        self.assertEqual(plan_version("1.0.4", commits, has_tags=True), ("bump", "1.1.0"))

    def test_breaking_bumps_major(self):
        self.assertEqual(
            plan_version("1.4.2", [("feat", "drop field", "BREAKING CHANGE: gone")], has_tags=True),
            ("bump", "2.0.0"),
        )

    def test_release_commit_is_ignored(self):
        commits = [("chore", "release v1.0.1", "")]
        self.assertEqual(plan_version("1.0.1", commits, has_tags=True), ("none", "1.0.1"))

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            plan_version("1.0.0", [("wip", "stuff", "")], has_tags=True)

    def test_set_version_line_keeps_comments(self):
        text = "# Bumped by release workflow. Do not edit by hand.\nversion: 1.0.0\nname: hermes-profile\n"
        got = set_version_line(text, "1.0.1")
        self.assertIn("# Bumped by release workflow. Do not edit by hand.\n", got)
        self.assertIn("version: 1.0.1\n", got)
        self.assertNotIn("version: 1.0.0", got)

    def test_parse_subject_bang_is_breaking(self):
        ctype, subject, breaking = parse_subject("feat!: drop", "")
        self.assertEqual(ctype, "feat")
        self.assertEqual(subject, "drop")
        self.assertTrue(breaking)


if __name__ == "__main__":
    unittest.main()
