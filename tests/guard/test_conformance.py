"""Guard decisions for known cases, from the real pinned upstream binary.

Command text is passed to the binary as data. Nothing in the cases is executed.
Set HARNESS_GUARD_REQUIRE_BINARY=1 to fail instead of skip when the binary is missing.
"""

import unittest

import support

adapter = support.adapter


class ConformanceTests(support.TempCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = support.real_binary()

    def setUp(self):
        super().setUp()
        if self.binary is None:
            message = "policy binary unavailable: " + support._BINARY_CACHE.get("error", "unknown")
            if support.REQUIRE_BINARY:
                self.fail(message)
            self.skipTest(message)
        self.project = self.make_project()

    def decide(self, case):
        args = {
            key: value.replace("{project}", self.project.as_posix()) if isinstance(value, str) else value
            for key, value in case["args"].items()
        }
        return adapter.decide(
            case["tool"], args, str(self.project), "conformance",
            lambda payloads: adapter.judge(payloads, self.binary, self.tmp / "state"),
        )

    def test_cases(self):
        for case in support.load_json("cases.json"):
            with self.subTest(case["name"]):
                decision = self.decide(case)
                self.assertEqual(decision.label, support.expected(case), decision)

    def test_blocks_and_refusals_carry_a_reason(self):
        for case in support.load_json("cases.json"):
            if support.expected(case) in ("block", "unjudgeable", "refused"):
                with self.subTest(case["name"]):
                    directive = adapter.directive_for(self.decide(case))
                    self.assertEqual(directive["action"], "block")
                    self.assertTrue(directive["message"])

    def test_every_ask_becomes_a_block_for_the_agent(self):
        for case in support.load_json("cases.json"):
            if support.expected(case) == "ask":
                with self.subTest(case["name"]):
                    directive = adapter.directive_for(self.decide(case))
                    self.assertEqual(directive["action"], "block")
                    self.assertIn("ask the user", directive["message"])


if __name__ == "__main__":
    unittest.main()
