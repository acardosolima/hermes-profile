import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

AGENT_HOOKS = Path(__file__).resolve().parents[2] / "agent-hooks"
if str(AGENT_HOOKS) not in sys.path:
    sys.path.insert(0, str(AGENT_HOOKS))

import lock_default  # noqa: E402
from lock_default import enabled_counts, toolset_names  # noqa: E402


def hermes_output(returncode, stdout="", stderr=""):
    return mock.patch.object(
        lock_default, "hermes", return_value=subprocess.CompletedProcess([], returncode, stdout, stderr)
    )


class ToolsetNamesTests(unittest.TestCase):
    def test_merges_every_source_without_duplicates(self):
        names = toolset_names(
            disabled=["browser"],
            known=[{"cli": ["terminal", "browser"]}, {"cli": ["file"], "acp": ["homeassistant"]}],
            mcp_servers={"agu": {"command": "npx"}},
        )
        self.assertEqual(names, ["agu", "browser", "file", "homeassistant", "terminal"])

    def test_unset_sources_are_skipped(self):
        self.assertEqual(toolset_names(disabled=None, known=[None, {"cli": ["web"]}], mcp_servers=None), ["web"])


class EnabledCountsTests(unittest.TestCase):
    def test_reads_the_enabled_count_of_every_platform(self):
        summary = "Tool Summary\n\n  CLI  (0/27)\n    (none enabled)\n  Slack  (2/27)\n    x clarify\n"
        self.assertEqual(enabled_counts(summary), [0, 2])


class ConfigValueTests(unittest.TestCase):
    def test_malformed_json_exits_with_a_message(self):
        with hermes_output(0, stdout="not json"), self.assertRaises(SystemExit) as raised:
            lock_default.config_value("default", "mcp_servers")
        self.assertIn("not valid JSON", str(raised.exception))

    def test_missing_profile_reads_as_unset(self):
        with hermes_output(1, stdout="Error: Profile 'work' does not exist. Create it with: hermes profile create work"):
            self.assertIsNone(lock_default.config_value("work", "known_builtin_toolsets"))


if __name__ == "__main__":
    unittest.main()
