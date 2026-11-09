"""check: regenerate in memory and report added, removed and changed paths."""

import unittest

try:
    from . import support
except ImportError:
    import support


class CheckTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)
        self.target = self.tmp / "skills-harness"
        self.hs.write_output(self.hs.generate(self.root, self.lock), self.target)

    def check(self):
        return [support.norm_line(line) for line in self.hs.check(self.root, self.lock, self.target)]

    def test_in_sync_returns_empty_list(self):
        self.assertEqual(self.hs.check(self.root, self.lock, self.target), [])

    def test_hand_edit_reports_changed(self):
        path = self.target / "harness-plan" / "SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nhand edit\n")
        self.assertEqual(self.check(), ["changed harness-plan/SKILL.md"])

    def test_stray_file_is_reported_as_removed(self):
        support.put(self.target, "harness-plan/stray.md", b"x\n")
        self.assertEqual(self.check(), ["removed harness-plan/stray.md"])

    def test_deleted_file_is_reported_as_added(self):
        (self.target / "harness-review" / "SKILL.md").unlink()
        self.assertEqual(self.check(), ["added harness-review/SKILL.md"])

    def test_mixed_changes_are_all_reported_in_path_order(self):
        path = self.target / "harness-plan" / "SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nedit\n")
        support.put(self.target, "harness-plan/stray.md", b"x\n")
        (self.target / "harness-review" / "SKILL.md").unlink()
        self.assertEqual(
            self.check(),
            [
                "changed harness-plan/SKILL.md",
                "removed harness-plan/stray.md",
                "added harness-review/SKILL.md",
            ],
        )

    def test_missing_target_reports_every_file_as_added(self):
        lines = self.check_against(self.tmp / "absent")
        generated = self.hs.generate(self.root, self.lock)
        self.assertEqual(lines, sorted("added " + path for path in generated))

    def check_against(self, target):
        return [support.norm_line(line) for line in self.hs.check(self.root, self.lock, target)]

    def test_edited_manifest_is_reported_as_changed(self):
        path = self.target / "GENERATED.json"
        path.write_bytes(path.read_bytes() + b" ")
        self.assertEqual(self.check(), ["changed GENERATED.json"])

    def test_check_never_writes_to_target(self):
        support.put(self.target, "harness-plan/stray.md", b"x\n")
        (self.target / "harness-review" / "SKILL.md").unlink()
        before = support.snapshot(self.target)
        self.hs.check(self.root, self.lock, self.target)
        self.assertEqual(support.snapshot(self.target), before)

    def test_each_line_has_documented_prefix(self):
        support.put(self.target, "harness-plan/stray.md", b"x\n")
        (self.target / "harness-review" / "SKILL.md").unlink()
        for line in self.hs.check(self.root, self.lock, self.target):
            with self.subTest(line=line):
                self.assertRegex(line, r"^(added|removed|changed) \S")


if __name__ == "__main__":
    unittest.main()
