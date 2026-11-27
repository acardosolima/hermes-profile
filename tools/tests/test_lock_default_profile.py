"""activate keeps the protected-paths hook, and the lock script turns tool search off."""

import importlib.util
import sys
import unittest
from pathlib import Path

AGENT_HOOKS = Path(__file__).resolve().parents[2] / "agent-hooks"
if str(AGENT_HOOKS) not in sys.path:
    sys.path.insert(0, str(AGENT_HOOKS))

import activate  # noqa: E402


def load_lock_script():
    path = AGENT_HOOKS / "lock-default-profile.py"
    spec = importlib.util.spec_from_file_location("lock_default_profile_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ActivateKeepsExistingHooks(unittest.TestCase):
    def test_both_hooks_stay_registered(self):
        self.assertEqual(
            [name for _, name in activate.HOOKS],
            ["gate-skill-manage.py", "gate-protected-paths.py"],
        )

    def test_activate_points_at_the_lock_script(self):
        self.assertEqual(activate.LOCK_DEFAULT, "lock-default-profile.py")


class LockScriptSettings(unittest.TestCase):
    def test_tool_search_uses_the_off_enum(self):
        text = (AGENT_HOOKS / "lock-default-profile.py").read_text(encoding="utf-8")
        line = next(item for item in text.splitlines() if "tool_search.enabled" in item)
        self.assertIn('tool_search.enabled", "off"', line)

    def test_soul_names_the_profile(self):
        text = load_lock_script().SOUL_TEXT.format(profile="master")
        self.assertIn("Switch to **master**", text)
        self.assertNotIn("{profile}", text)


if __name__ == "__main__":
    unittest.main()
