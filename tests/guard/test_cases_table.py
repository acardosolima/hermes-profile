"""The case table is the spec for the guard, so it must not shrink or soften unnoticed."""

import unittest

import support

LABELS = {"allow", "block", "ask", "unguarded", "unjudgeable", "refused"}


class CaseTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = support.load_json("cases.json")
        cls.rules = support.load_json("rules.json")

    def count(self, label):
        return sum(1 for case in self.cases if case["expect"] == label)

    def test_every_case_is_complete_and_named_once(self):
        names = [case["name"] for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        for case in self.cases:
            with self.subTest(case["name"]):
                for key in ("name", "rule", "tool", "args", "expect"):
                    self.assertIn(key, case)

    def test_every_expectation_is_an_exact_label(self):
        for case in self.cases:
            with self.subTest(case["name"]):
                self.assertIn(case["expect"], LABELS)

    def test_platform_overrides_are_exact_and_explained(self):
        for case in self.cases:
            if "expect_windows" in case:
                with self.subTest(case["name"]):
                    self.assertIn(case["expect_windows"], LABELS)
                    self.assertTrue(case.get("windows_note"))

    def test_only_documented_windows_gaps_exist(self):
        gaps = sorted(case["name"] for case in self.cases if "expect_windows" in case)
        self.assertEqual(gaps, ["stage a dotenv file"])

    def test_every_enforced_rule_has_an_exact_block_or_ask_case(self):
        covered = {case["rule"] for case in self.cases if case["expect"] in ("block", "ask")}
        for rule_id, classification in self.rules.items():
            if classification == "enforced":
                with self.subTest(rule_id):
                    self.assertIn(rule_id.split(":", 1)[0], covered)

    def test_runtime_floor_is_covered(self):
        floors = [c for c in self.cases if c["rule"] == "RUNTIME_FLOOR" and c["expect"] == "block"]
        self.assertGreaterEqual(len(floors), 4)

    def test_table_keeps_a_minimum_size_and_mix(self):
        self.assertGreaterEqual(len(self.cases), 40)
        self.assertGreaterEqual(self.count("block"), 16)
        self.assertGreaterEqual(self.count("ask"), 5)
        self.assertGreaterEqual(self.count("allow"), 7)
        self.assertGreaterEqual(self.count("unjudgeable"), 8)
        self.assertGreaterEqual(self.count("refused"), 4)

    def test_every_guarded_tool_appears_in_the_table(self):
        tools = {case["tool"] for case in self.cases}
        for tool in support.adapter.GUARDED_TOOLS:
            with self.subTest(tool):
                self.assertIn(tool, tools)

    def test_the_bypasses_found_in_review_stay_covered(self):
        names = {case["name"] for case in self.cases}
        for required in (
            "patch mode names git internals", "patch mode adds a file outside the project", "write to a home path",
            "relative delete from the filesystem root", "tilde user path", "patch that names no file",
            "edit the project policy file", "switch the guard off with the hermes cli", "process input is judged",
        ):
            with self.subTest(required):
                self.assertIn(required, names)

    def test_warn_only_secret_read_is_documented_as_allowed(self):
        warn = [case for case in self.cases if case["rule"] == "R09"]
        self.assertTrue(warn)
        self.assertTrue(all(case["expect"] == "allow" for case in warn))


if __name__ == "__main__":
    unittest.main()
