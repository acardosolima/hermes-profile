"""Every upstream rule must be classified. A bump that adds a rule fails here until it is."""

import unittest

import support

VALID = {"enforced", "warn-only", "not-applicable"}


class RuleClassificationTests(unittest.TestCase):
    def test_every_upstream_rule_is_classified(self):
        upstream = set(support.real_lock()["rules"])
        classified = set(support.load_json("rules.json"))
        self.assertEqual(sorted(upstream - classified), [], "upstream rules without a classification")
        self.assertEqual(sorted(classified - upstream), [], "classified rules that upstream no longer has")

    def test_classifications_use_known_values(self):
        for rule, value in support.load_json("rules.json").items():
            with self.subTest(rule=rule):
                self.assertIn(value, VALID)

    def test_lock_lists_rules(self):
        self.assertGreaterEqual(len(support.real_lock()["rules"]), 10)


if __name__ == "__main__":
    unittest.main()
