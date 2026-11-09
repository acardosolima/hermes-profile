"""The acceptance script must flag a config that enables the code_execution toolset."""

import unittest

import support

PLUGIN_DIR = support.PLUGIN_DIR
import acceptance  # noqa: E402

ENABLED = """\
known_builtin_toolsets:
  cli:
    - code_execution
platform_toolsets:
  cli:
    - clarify
    - code_execution
    - terminal
"""

DISABLED = """\
known_builtin_toolsets:
  cli:
    - code_execution
platform_toolsets:
  cli:
    - clarify
    - terminal
  discord:
    - clarify
"""


class CodeExecutionCheckTests(support.TempCase):
    def test_enabled_in_platform_toolsets_is_flagged(self):
        self.assertTrue(acceptance.code_execution_enabled(ENABLED))

    def test_listing_in_known_builtin_toolsets_alone_is_fine(self):
        self.assertFalse(acceptance.code_execution_enabled(DISABLED))

    def test_commented_out_entry_is_fine(self):
        text = "platform_toolsets:\n  cli:\n    # - code_execution\n    - terminal\n"
        self.assertFalse(acceptance.code_execution_enabled(text))

    def test_any_platform_under_platform_toolsets_is_flagged(self):
        text = "platform_toolsets:\n  cli:\n    - terminal\n  discord:\n    - code_execution\n"
        self.assertTrue(acceptance.code_execution_enabled(text))

    def test_entry_after_the_block_ends_is_not_counted(self):
        text = "platform_toolsets:\n  cli:\n    - terminal\nother:\n  - code_execution\n"
        self.assertFalse(acceptance.code_execution_enabled(text))

    def test_check_fails_when_enabled_and_passes_when_off(self):
        on = self.tmp / "on.yaml"
        off = self.tmp / "off.yaml"
        on.write_text(ENABLED, encoding="utf-8")
        off.write_text(DISABLED, encoding="utf-8")
        self.assertFalse(acceptance.config_check(on)[1])
        self.assertTrue(acceptance.config_check(off)[1])

    def test_check_fails_when_the_config_is_missing(self):
        self.assertFalse(acceptance.config_check(self.tmp / "missing.yaml")[1])

    def test_shipped_config_has_the_toolset_off(self):
        shipped = support.ROOT / "config.yaml"
        self.assertTrue(acceptance.config_check(shipped)[1])


if __name__ == "__main__":
    unittest.main()
