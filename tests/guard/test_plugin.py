"""The pre_tool_call hook: fail-closed behavior, protections and the real assembled path."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import support

adapter = support.adapter
binaries = support.binaries


def load_plugin():
    name = "harness_guard_under_test"
    spec = importlib.util.spec_from_file_location(
        name, support.PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(support.PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PluginCase(support.TempCase):
    def setUp(self):
        super().setUp()
        self.plugin = load_plugin()
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.tmp / "home")}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project().as_posix()
        lookups = mock.patch.object(self.plugin, "_cwd_lookups", return_value=(lambda task: self.project,))
        lookups.start()
        self.addCleanup(lookups.stop)

    def call(self, tool="terminal", args=None):
        args = {"command": "ls"} if args is None else args
        return self.plugin.on_pre_tool_call(tool_name=tool, args=args, task_id="t1", session_id="s1")

    def with_policy(self, verdict):
        return mock.patch.object(self.plugin.adapter, "judge", return_value=verdict)

    def with_binary(self):
        return mock.patch.object(self.plugin, "_binary", return_value=Path("/fake/binary"))


class HookBehaviorTests(PluginCase):
    def test_register_adds_the_pre_tool_call_hook(self):
        ctx = mock.Mock()
        with mock.patch.object(self.plugin.threading, "Thread"):
            self.plugin.register(ctx)
        ctx.register_hook.assert_called_once_with("pre_tool_call", self.plugin.on_pre_tool_call)

    def test_register_prefetches_the_binary_in_a_daemon_thread(self):
        with mock.patch.object(self.plugin.threading, "Thread") as thread:
            self.plugin.register(mock.Mock())
        self.assertTrue(thread.call_args.kwargs["daemon"])
        thread.return_value.start.assert_called_once()

    def test_unguarded_tool_never_touches_the_binary(self):
        with mock.patch.object(self.plugin, "_binary", side_effect=AssertionError("must not run")):
            self.assertIsNone(self.call("todo", {"items": []}))
            self.assertIsNone(self.call("process_manage", {"action": "list"}))

    def test_block_verdict_becomes_block_directive(self):
        with self.with_binary(), self.with_policy(adapter.Verdict("block", "no sudo")):
            self.assertEqual(self.call(), {"action": "block", "message": "no sudo"})

    def test_ask_verdict_blocks_and_never_reaches_the_approval_gate(self):
        with self.with_binary(), self.with_policy(adapter.Verdict("ask", "sure?")):
            directive = self.call()
        self.assertEqual(directive["action"], "block")
        self.assertIn("ask the user", directive["message"])

    def test_allow_verdict_proceeds(self):
        with self.with_binary(), self.with_policy(adapter.Verdict("allow")):
            self.assertIsNone(self.call())

    def test_unavailable_binary_blocks_guarded_tools_with_a_readable_reason(self):
        error = self.plugin.binaries.BinaryError("offline")
        with mock.patch.object(self.plugin.binaries, "ensure_binary", side_effect=error):
            directive = self.call()
        self.assertEqual(directive["action"], "block")
        self.assertIn("offline", directive["message"])
        self.assertIn("hermes plugins disable harness-guard", directive["message"])

    def test_the_binary_is_verified_on_every_guarded_call(self):
        with mock.patch.object(self.plugin.binaries, "ensure_binary", return_value=Path("/fake/binary")) as ensure:
            with self.with_policy(adapter.Verdict("allow")):
                self.call()
                self.call()
        self.assertEqual(ensure.call_count, 2)

    def test_unavailable_binary_does_not_block_unguarded_tools(self):
        error = self.plugin.binaries.BinaryError("offline")
        with mock.patch.object(self.plugin.binaries, "ensure_binary", side_effect=error):
            self.assertIsNone(self.call("todo", {}))

    def test_an_internal_error_blocks_with_a_designed_message(self):
        with mock.patch.object(self.plugin.adapter, "decide", side_effect=ValueError("boom")):
            directive = self.call()
        self.assertEqual(directive["action"], "block")
        self.assertIn("ValueError", directive["message"])
        self.assertIn("blocked", directive["message"])

    def test_unknown_working_directory_blocks(self):
        with mock.patch.object(self.plugin, "_cwd_lookups", return_value=()):
            with self.with_binary(), self.with_policy(adapter.Verdict("allow")):
                directive = self.call()
        self.assertEqual(directive["action"], "block")
        self.assertIn("working directory", directive["message"])

    def test_malformed_arguments_block(self):
        with self.with_binary(), self.with_policy(adapter.Verdict("allow")):
            for args in (None, {}, {"command": None}, "not a dict", {"command": 5}):
                with self.subTest(args=args):
                    result = self.plugin.on_pre_tool_call(tool_name="terminal", args=args, task_id="t1", session_id="s1")
                    self.assertEqual(result["action"], "block")

    def test_environment_settings_cannot_switch_the_guard_off_or_relax_asks(self):
        env = {"HARNESS_GUARD_DISABLE": "1", "HARNESS_GUARD_ASK_MODE": "approve", "HARNESS_GUARD_LOG": "/tmp/x"}
        with mock.patch.dict(os.environ, env):
            with self.with_binary(), self.with_policy(adapter.Verdict("ask", "q")):
                self.assertEqual(self.call()["action"], "block")
            with self.with_binary(), self.with_policy(adapter.Verdict("block", "no")):
                self.assertEqual(self.call()["action"], "block")

    def test_the_plugin_has_no_settings_reader(self):
        for name in ("_setting", "_debug"):
            self.assertFalse(hasattr(self.plugin, name), name)


class CwdLookupTests(support.TempCase):
    """The guard finds the directory the way the terminal tool does: recorded, live env, scoped default."""

    def fake_terminal_tool(self, session=None, envs=None, scoped="/scoped", config="/cfg"):
        module = mock.Mock()
        module.get_session_cwd = lambda task: None
        module._session_cwd = session or {}
        module._active_environments = envs or {}
        module._tenv = lambda name: scoped
        module._get_env_config = lambda: {"cwd": config}
        return module

    def lookups(self, module):
        plugin = load_plugin()
        tools = mock.Mock(terminal_tool=module)
        with mock.patch.dict("sys.modules", {"tools": tools, "tools.terminal_tool": module}):
            return plugin, plugin._cwd_lookups()

    def test_recorded_session_directory_wins_and_follows_cd(self):
        module = self.fake_terminal_tool(session={"profile:p:agent:p:local:dm:T1": "/work/sub"})
        plugin, lookups = self.lookups(module)
        self.assertEqual(adapter.resolve_cwd("T1", lookups), "/work/sub")

    def test_keys_match_only_on_a_colon_boundary(self):
        module = self.fake_terminal_tool(session={"profile:p:XT1": "/wrong"}, scoped="/scoped")
        plugin, lookups = self.lookups(module)
        self.assertEqual(adapter.resolve_cwd("T1", lookups), "/scoped")

    def test_live_environment_directory_is_not_used_because_it_may_belong_to_another_session(self):
        env = mock.Mock(cwd="/env/dir")
        module = self.fake_terminal_tool(envs={"profile:p:T1": env}, scoped="/scoped")
        plugin, lookups = self.lookups(module)
        self.assertEqual(adapter.resolve_cwd("T1", lookups), "/scoped")

    def test_first_call_uses_the_scoped_default_then_the_configured_one(self):
        plugin, lookups = self.lookups(self.fake_terminal_tool(scoped="/scoped", config="/cfg"))
        self.assertEqual(adapter.resolve_cwd("T1", lookups), "/scoped")
        plugin, lookups = self.lookups(self.fake_terminal_tool(scoped=None, config="/cfg"))
        self.assertEqual(adapter.resolve_cwd("T1", lookups), "/cfg")

    def test_relative_defaults_are_not_a_directory(self):
        plugin, lookups = self.lookups(self.fake_terminal_tool(scoped=".", config="."))
        self.assertIsNone(adapter.resolve_cwd("T1", lookups))

    def test_without_the_terminal_tool_nothing_is_known(self):
        plugin = load_plugin()
        with mock.patch.dict("sys.modules", {"tools": None, "tools.terminal_tool": None}):
            self.assertEqual(plugin._cwd_lookups(), ())


class ProtectionTests(PluginCase):
    def judge_text(self, command):
        with self.with_binary(), self.with_policy(adapter.Verdict("allow")):
            return self.call("terminal", {"command": command})

    def test_commands_that_touch_the_guard_are_refused_before_the_policy_runs(self):
        for command in (
            "echo x >> plugins/harness-guard/adapter.py", "hermes plugins disable harness-guard",
            "hermes config set approvals.mode off", "cp evil binaries.lock.json x",
        ):
            with self.subTest(command=command):
                result = self.judge_text(command)
                self.assertEqual(result["action"], "block")
                self.assertIn("harness guard", result["message"])

    def test_edits_to_the_plugin_directory_are_refused(self):
        installed = (support.PLUGIN_DIR / "adapter.py").as_posix()
        with self.with_binary(), self.with_policy(adapter.Verdict("allow")):
            result = self.call("write_file", {"path": installed, "content": "x"})
        self.assertEqual(result["action"], "block")

    def test_ordinary_commands_are_not_refused(self):
        self.assertIsNone(self.judge_text("git status"))


class PayloadForwardingTests(PluginCase):
    """The hook must hand the tool arguments to the policy, not just the directory."""

    def captured(self, tool, args):
        seen = []

        def fake_judge(payloads, binary, state_dir, runner=None):
            seen.extend(payloads)
            return adapter.Verdict("allow")

        with self.with_binary(), mock.patch.object(self.plugin.adapter, "judge", side_effect=fake_judge):
            self.plugin.on_pre_tool_call(tool_name=tool, args=args, task_id="t1", session_id="s1")
        return seen

    def test_terminal_command_and_session_reach_the_policy(self):
        (seen,) = self.captured("terminal", {"command": "ls -la", "timeout": 5})
        self.assertEqual((seen["tool_name"], seen["tool_input"]), ("Bash", {"command": "ls -la"}))
        self.assertEqual((seen["cwd"], seen["session_id"]), (self.project, "s1"))

    def test_write_file_arguments_reach_the_policy(self):
        (seen,) = self.captured("write_file", {"path": "a.txt", "content": "x"})
        self.assertEqual(seen["tool_name"], "Write")
        self.assertEqual(seen["tool_input"], {"file_path": f"{self.project}/a.txt", "content": "x"})

    def test_patch_mode_paths_reach_the_policy(self):
        text = "*** Begin Patch\n*** Update File: a.txt\n*** Add File: b.txt\n+x\n*** End Patch"
        seen = self.captured("patch", {"mode": "patch", "patch": text})
        self.assertEqual(sorted(p["tool_input"]["file_path"] for p in seen), [f"{self.project}/a.txt", f"{self.project}/b.txt"])


class RealBinaryHookTests(PluginCase):
    """The assembled hook (mapping, real policy binary, Hermes directive). Text only is judged."""

    @classmethod
    def setUpClass(cls):
        cls.binary = support.real_binary()

    def setUp(self):
        super().setUp()
        if self.binary is None:
            if support.REQUIRE_BINARY:
                self.fail("policy binary unavailable")
            self.skipTest("policy binary unavailable")
        patcher = mock.patch.object(self.plugin, "_binary", return_value=self.binary)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_denied_command_becomes_a_block_with_the_upstream_reason(self):
        directive = self.call("terminal", {"command": "sudo apt update"})
        self.assertEqual(directive["action"], "block")
        self.assertIn("sudo is not allowed", directive["message"])

    def test_ask_becomes_a_block_that_tells_the_agent_to_ask_the_user(self):
        directive = self.call("terminal", {"command": "git push origin main"})
        self.assertEqual(directive["action"], "block")
        self.assertIn("ask the user", directive["message"])

    def test_safe_command_proceeds(self):
        self.assertIsNone(self.call("terminal", {"command": "echo hello"}))

    def test_write_outside_the_project_is_blocked_and_inside_proceeds(self):
        self.assertEqual(self.call("write_file", {"path": "/etc/hosts", "content": "x"})["action"], "block")
        self.assertIsNone(self.call("write_file", {"path": f"{self.project}/notes.txt", "content": "x"}))

    def test_patch_mode_cannot_bypass_the_protected_path_rule(self):
        text = f"*** Begin Patch\n*** Update File: {self.project}/.git/config\n@@\n-a\n+b\n*** End Patch"
        self.assertEqual(self.call("patch", {"mode": "patch", "patch": text})["action"], "block")

    def test_home_path_cannot_bypass_the_outside_project_rule(self):
        self.assertEqual(self.call("write_file", {"path": "~/hg-guard-test-outside.txt", "content": "x"})["action"], "block")

    def test_workdir_at_the_root_cannot_bypass_the_delete_rules(self):
        directive = self.call("terminal", {"command": "rm -rf home", "workdir": "/"})
        self.assertEqual(directive["action"], "block")


if __name__ == "__main__":
    unittest.main()
