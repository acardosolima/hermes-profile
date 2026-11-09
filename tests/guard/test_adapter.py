"""Mapping, verdict parsing, the decision pipeline and failure handling. No real binary is involved."""

import json
import subprocess
import unittest
from pathlib import Path

import support

adapter = support.adapter
HOME = "/home/tester"
PROJECT = "/work/project"


def run_result(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def verdict_json(decision, reason=""):
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}
    )


def payloads(tool, args, cwd=PROJECT):
    return adapter.to_payloads(tool, args, cwd, "s1", HOME)


class ToPayloadsTests(unittest.TestCase):
    def test_terminal_maps_to_bash_and_drops_other_arguments(self):
        (payload,) = payloads("terminal", {"command": "ls", "timeout": 5})
        self.assertEqual((payload["tool_name"], payload["tool_input"]), ("Bash", {"command": "ls"}))
        self.assertEqual((payload["cwd"], payload["session_id"], payload["hook_event_name"]), (PROJECT, "s1", "PreToolUse"))

    def test_workdir_replaces_the_session_directory(self):
        (payload,) = payloads("terminal", {"command": "ls", "workdir": "/work/other"})
        self.assertEqual(payload["cwd"], "/work/other")

    def test_relative_workdir_is_joined_to_the_session_directory(self):
        (payload,) = payloads("terminal", {"command": "ls", "workdir": "sub"})
        self.assertEqual(payload["cwd"], "/work/project/sub")

    def test_workdir_at_a_system_location_cannot_be_judged(self):
        for workdir in ("/", "/etc", "/usr/local", HOME, "~"):
            with self.subTest(workdir=workdir):
                with self.assertRaises(adapter.Unjudgeable):
                    payloads("terminal", {"command": "rm -rf x", "workdir": workdir})

    def test_file_tools_map_paths_to_absolute_file_path(self):
        (read,) = payloads("read_file", {"path": "a.txt", "offset": 1})
        (write,) = payloads("write_file", {"path": "/abs/a.txt", "content": "x"})
        (edit,) = payloads("patch", {"path": "a.txt", "old_string": "o", "new_string": "n"})
        self.assertEqual((read["tool_name"], read["tool_input"]), ("Read", {"file_path": "/work/project/a.txt"}))
        self.assertEqual((write["tool_name"], write["tool_input"]), ("Write", {"file_path": "/abs/a.txt", "content": "x"}))
        self.assertEqual(edit["tool_input"], {"file_path": "/work/project/a.txt", "old_string": "o", "new_string": "n"})

    def test_home_paths_are_expanded(self):
        (payload,) = payloads("write_file", {"path": "~/notes.txt", "content": "x"})
        self.assertEqual(payload["tool_input"]["file_path"], "/home/tester/notes.txt")

    def test_other_users_home_paths_cannot_be_judged(self):
        with self.assertRaises(adapter.Unjudgeable):
            payloads("write_file", {"path": "~root/x", "content": "x"})

    def test_patch_mode_yields_one_payload_per_named_file(self):
        text = (
            "*** Begin Patch\n*** Update File: a.txt\n@@\n-a\n+b\n*** Add File: new/b.txt\n+x\n"
            "*** Delete File: old.txt\n*** Move File: from.txt -> to.txt\n*** End Patch"
        )
        result = payloads("patch", {"mode": "patch", "patch": text})
        seen = sorted((p["tool_name"], p["tool_input"]["file_path"]) for p in result)
        self.assertEqual(
            seen,
            sorted([
                ("Edit", "/work/project/a.txt"), ("Write", "/work/project/new/b.txt"), ("Edit", "/work/project/old.txt"),
                ("Edit", "/work/project/from.txt"), ("Write", "/work/project/to.txt"),
            ]),
        )

    def test_patch_with_both_path_and_patch_text_judges_both(self):
        text = "*** Begin Patch\n*** Update File: /etc/hosts\n*** End Patch"
        result = payloads("patch", {"path": "a.txt", "old_string": "a", "new_string": "b", "patch": text})
        self.assertEqual(sorted(p["tool_input"]["file_path"] for p in result), ["/etc/hosts", "/work/project/a.txt"])

    def test_unguarded_tools_have_no_payloads(self):
        for tool in ("todo", "delegate_task", "search_files", "skill_manage", "clarify"):
            with self.subTest(tool=tool):
                self.assertIsNone(payloads(tool, {}))

    def test_process_input_is_guarded_but_listing_is_not(self):
        (payload,) = payloads("process_manage", {"action": "submit", "data": "sudo ls"})
        self.assertEqual((payload["tool_name"], payload["tool_input"]), ("Bash", {"command": "sudo ls"}))
        self.assertIsNone(payloads("process_manage", {"action": "list"}))
        self.assertIsNone(payloads("process_manage", {"action": "kill", "session_id": "x"}))

    def test_malformed_guarded_calls_cannot_be_judged(self):
        bad = [
            ("terminal", None), ("terminal", "ls"), ("terminal", {}), ("terminal", {"command": 5}),
            ("terminal", {"command": "  "}), ("terminal", {"command": "ls", "workdir": 5}),
            ("read_file", {}), ("read_file", {"path": ["a"]}), ("write_file", {"path": "a"}),
            ("write_file", {"content": "x"}), ("patch", {}), ("patch", {"mode": "weird", "path": "a"}),
            ("patch", {"mode": "patch", "patch": "no headers here"}), ("patch", {"patch": 5}),
            ("process_manage", {"action": "write", "data": 5}),
        ]
        for tool, args in bad:
            with self.subTest(tool=tool, args=args):
                with self.assertRaises(adapter.Unjudgeable):
                    payloads(tool, args)

    def test_unknown_working_directory_cannot_be_judged(self):
        for cwd in (None, "", "/", "/etc/ssl", HOME):
            with self.subTest(cwd=cwd):
                with self.assertRaises(adapter.Unjudgeable):
                    adapter.to_payloads("terminal", {"command": "ls"}, cwd, "s", HOME)

    def test_nul_bytes_cannot_be_judged(self):
        with self.assertRaises(adapter.Unjudgeable):
            payloads("terminal", {"command": "ls\x00"})
        with self.assertRaises(adapter.Unjudgeable):
            payloads("read_file", {"path": "a\x00b"})

    def test_missing_session_id_gets_a_default(self):
        (payload,) = adapter.to_payloads("terminal", {"command": "ls"}, PROJECT, "", HOME)
        self.assertTrue(payload["session_id"])


class GuardReferenceTests(unittest.TestCase):
    def check(self, command):
        return adapter.guard_reference(payloads("terminal", {"command": command}), ("/home/tester/.hermes/plugins",))

    def test_references_to_the_guard_are_found(self):
        for command in (
            "echo x >> plugins/harness-guard/adapter.py", "cat ./Harness-Guard/x", "sed -i s/a/b/ binaries.lock.json",
            "echo hi > harness.toml", "ls /home/tester/.hermes/plugins/homeassistant",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.check(command))

    def test_hermes_administration_commands_are_found(self):
        for command in (
            "hermes plugins disable something", "hermes config set a b", "hermes -p work profile delete x",
            "HERMES gateway stop", "hermes hooks revoke",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.check(command), "hermes administration command")

    def test_ordinary_commands_are_left_alone(self):
        for command in ("ls -la", "git status", "python3 script.py", "hermes --version", "echo hermes plugin"):
            with self.subTest(command=command):
                self.assertIsNone(self.check(command))

    def test_file_paths_are_checked_too(self):
        result = payloads("write_file", {"path": "plugins/harness-guard/x.py", "content": "x"})
        self.assertTrue(adapter.guard_reference(result))


class ReviewRoundTwoTests(unittest.TestCase):
    """Parity with Hermes' patch parser, shell expansions, workdir order and non-project directories."""

    def check(self, command, **kw):
        return adapter.guard_reference(
            payloads("terminal", {"command": command}), (), HOME, kw.get("hermes_home", HOME + "/.hermes")
        )

    def test_patch_headers_without_a_space_are_still_read(self):
        text = "*** Begin Patch\n***Update File: a.txt\n***Add File:b.txt\n+x\n***Move File: c.txt->d.txt\n*** End Patch"
        seen = sorted(p["tool_input"]["file_path"] for p in payloads("patch", {"mode": "patch", "patch": text}))
        self.assertEqual(seen, sorted([f"{PROJECT}/{n}" for n in ("a.txt", "b.txt", "c.txt", "d.txt")]))

    def test_indented_patch_headers_are_read(self):
        text = "*** Begin Patch\n   *** Update File: a.txt\n*** End Patch"
        self.assertEqual(len(payloads("patch", {"mode": "patch", "patch": text})), 1)

    def test_a_header_the_guard_does_not_understand_blocks_the_whole_patch(self):
        text = "*** Begin Patch\n*** Update File: a.txt\n*** Frobnicate File: /etc/hosts\n*** End Patch"
        with self.assertRaises(adapter.Unjudgeable):
            payloads("patch", {"mode": "patch", "patch": text})

    def test_shell_spellings_of_the_hermes_home_are_resolved_before_matching(self):
        for command in (
            "cat ~/.hermes/config.yaml", "echo x >> $HOME/.hermes/plugins/a.py", "sed -i s/a/b/ ${HERMES_HOME}/plugins/a",
            "cp x $HERMES_HOME/config.yaml", "cat '~/.hermes/config.yaml'", "less ./.hermes/plugins/p/__init__.py",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.check(command, hermes_home="/home/tester/.hermes"), command)

    def test_skill_scripts_under_the_hermes_home_are_not_refused(self):
        home = "/home/tester/.hermes/profiles/p"
        for command in (f"bash {home}/skills/harness/harness-work/scripts/log-tdd-red.sh", "ls ~/.hermes/skills"):
            with self.subTest(command=command):
                self.assertIsNone(self.check(command, hermes_home=home))

    def test_hermes_administration_with_flags_is_found(self):
        for command in (
            "hermes --profile=work config show", "hermes --yolo plugins list", "hermes -p work -v profile delete x",
            "FOO=1 hermes config get a", "ls && hermes gateway stop",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.check(command), "hermes administration command")

    def test_only_names_and_commands_are_checked_not_file_contents(self):
        result = payloads("write_file", {"path": "notes.txt", "content": "see plugins/harness-guard and harness.toml"})
        self.assertIsNone(adapter.guard_reference(result))
        edit = payloads("patch", {"path": "notes.txt", "old_string": "harness-guard", "new_string": "harness.toml"})
        self.assertIsNone(adapter.guard_reference(edit))

    def test_absolute_workdir_is_judged_even_when_the_session_directory_is_the_home(self):
        (payload,) = adapter.to_payloads("terminal", {"command": "ls", "workdir": "/work/ok"}, HOME, "s", HOME)
        self.assertEqual(payload["cwd"], "/work/ok")
        with self.assertRaises(adapter.Unjudgeable):
            adapter.to_payloads("terminal", {"command": "ls"}, HOME, "s", HOME)

    def test_a_relative_workdir_still_needs_a_known_session_directory(self):
        with self.assertRaises(adapter.Unjudgeable):
            adapter.to_payloads("terminal", {"command": "ls", "workdir": "sub"}, None, "s", HOME)

    def test_projects_in_opt_and_srv_are_allowed(self):
        for cwd in ("/opt/app", "/srv/site"):
            with self.subTest(cwd=cwd):
                self.assertEqual(adapter.check_cwd(cwd, HOME), cwd)

    def test_credential_and_tool_directories_under_home_are_not_projects(self):
        for name in (".ssh", ".aws", ".gnupg", ".hermes", ".config"):
            for cwd in (f"{HOME}/{name}", f"{HOME}/{name}/sub"):
                with self.subTest(cwd=cwd):
                    with self.assertRaises(adapter.Unjudgeable):
                        adapter.check_cwd(cwd, HOME)
        self.assertEqual(adapter.check_cwd(f"{HOME}/code/app", HOME), f"{HOME}/code/app")


class ParseVerdictTests(unittest.TestCase):
    def test_empty_success_allows(self):
        self.assertEqual(adapter.parse_verdict("", 0).action, "allow")

    def test_explicit_allow_allows(self):
        self.assertEqual(adapter.parse_verdict(verdict_json("allow", ""), 0).action, "allow")

    def test_deny_blocks_with_reason(self):
        verdict = adapter.parse_verdict(verdict_json("deny", "no sudo"), 2)
        self.assertEqual((verdict.action, verdict.message), ("block", "no sudo"))

    def test_deny_wins_even_with_exit_zero_and_mixed_case(self):
        self.assertEqual(adapter.parse_verdict(verdict_json("DENY", "x"), 0).action, "block")

    def test_ask_asks(self):
        verdict = adapter.parse_verdict(verdict_json("ask", "confirm?"), 0)
        self.assertEqual((verdict.action, verdict.message), ("ask", "confirm?"))

    def test_exit_two_blocks_even_without_json(self):
        self.assertEqual(adapter.parse_verdict("", 2).action, "block")

    def test_unparseable_output_blocks(self):
        self.assertEqual(adapter.parse_verdict("not json", 0).action, "block")

    def test_unexpected_failure_exit_blocks(self):
        self.assertEqual(adapter.parse_verdict("", 1).action, "block")

    def test_unrecognised_answers_block(self):
        answers = [
            verdict_json("defer", "later"), verdict_json("approve", ""), verdict_json("", ""), "null", "[]", "{}",
            json.dumps({"decision": "approve", "reason": "Core engine error (safe fallback)"}),
            json.dumps({"hookSpecificOutput": "oops"}),
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertEqual(adapter.parse_verdict(answer, 0).action, "block")

    def test_runtime_floor_rule_is_extracted(self):
        verdict = adapter.parse_verdict(verdict_json("deny", "RUNTIME_FLOOR:secret-read: needs approval"), 2)
        self.assertEqual(verdict.rule, "RUNTIME_FLOOR")


class EvaluateTests(support.TempCase):
    def evaluate(self, runner):
        return adapter.evaluate({"x": 1}, Path("/no/such/binary"), self.tmp / "state", runner=runner)

    def test_runner_receives_payload_on_stdin_and_runs_in_state_dir(self):
        seen = {}

        def runner(cmd, **kwargs):
            seen.update(cmd=cmd, **kwargs)
            return run_result("", 0)

        self.assertEqual(self.evaluate(runner).action, "allow")
        self.assertEqual(seen["cmd"][1:], ["hook", "pre-tool"])
        self.assertEqual(json.loads(seen["input"]), {"x": 1})
        self.assertEqual(seen["cwd"], str(self.tmp / "state"))
        self.assertTrue((self.tmp / "state").is_dir())

    def test_runner_is_called_with_a_timeout(self):
        seen = {}

        def runner(cmd, **kwargs):
            seen.update(kwargs)
            return run_result("", 0)

        self.evaluate(runner)
        self.assertEqual(seen["timeout"], adapter.BINARY_TIMEOUT_SECONDS)
        self.assertGreater(adapter.BINARY_TIMEOUT_SECONDS, 0)

    def test_binary_runs_with_a_scrubbed_environment_and_strict_policy(self):
        seen = {}

        def runner(cmd, **kwargs):
            seen.update(kwargs)
            return run_result("", 0)

        self.evaluate(runner)
        env = seen["env"]
        self.assertEqual(env["HARNESS_DESTRUCTIVE_DELETE_POLICY"], "ask")
        self.assertEqual(env["HARNESS_PROTECTED_BRANCH_PUSH_POLICY"], "ask")
        self.assertEqual(env["HARNESS_DIRECT_PUSH_POLICY"], "ask")

    def test_clean_env_drops_variables_that_change_policy(self):
        env = adapter.clean_env({
            "PATH": "/bin", "HOME": "/h", "HARNESS_WORK_MODE": "1", "ULTRAWORK_MODE": "1",
            "HARNESS_PROJECT_ROOT": "/", "HARNESS_DESTRUCTIVE_DELETE_POLICY": "allow", "SECRET_TOKEN": "x",
        })
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(env["HARNESS_DESTRUCTIVE_DELETE_POLICY"], "ask")
        for name in ("HARNESS_WORK_MODE", "ULTRAWORK_MODE", "HARNESS_PROJECT_ROOT", "SECRET_TOKEN"):
            self.assertNotIn(name, env)

    def test_any_runner_failure_blocks(self):
        for exc in (FileNotFoundError("gone"), subprocess.TimeoutExpired("x", 1), TypeError("bad"), PermissionError("no")):
            with self.subTest(exc=type(exc).__name__):
                def runner(cmd, exc=exc, **kwargs):
                    raise exc

                self.assertEqual(self.evaluate(runner).action, "block")

    def test_deny_verdict_round_trips(self):
        verdict = self.evaluate(lambda cmd, **kw: run_result(verdict_json("deny", "nope"), 2))
        self.assertEqual((verdict.action, verdict.message), ("block", "nope"))


class JudgeTests(support.TempCase):
    def run_with(self, answers):
        calls = iter(answers)
        return adapter.judge([{"i": 1}, {"i": 2}, {"i": 3}], Path("/x"), self.tmp / "s", runner=lambda c, **k: next(calls))

    def test_all_allow_is_allow(self):
        self.assertEqual(self.run_with([run_result()] * 3).action, "allow")

    def test_one_block_among_allows_blocks(self):
        answers = [run_result(), run_result(verdict_json("deny", "stop"), 2), run_result()]
        self.assertEqual(self.run_with(answers).action, "block")

    def test_ask_beats_allow_and_block_beats_ask(self):
        self.assertEqual(self.run_with([run_result(), run_result(verdict_json("ask", "q")), run_result()]).action, "ask")
        answers = [run_result(verdict_json("ask", "q")), run_result(verdict_json("deny", "d"), 2), run_result()]
        self.assertEqual(self.run_with(answers).action, "block")


class DecisionTests(unittest.TestCase):
    def decide(self, tool, args, policy=None, cwd=PROJECT, terms=()):
        policy = policy or (lambda payloads: adapter.Verdict("allow"))
        return adapter.decide(tool, args, cwd, "s", policy, terms, HOME)

    def test_unguarded_tool_skips_the_policy(self):
        def never(payloads):
            raise AssertionError("must not run")

        self.assertEqual(self.decide("todo", {}, never).label, "unguarded")

    def test_unjudgeable_call_skips_the_policy_and_blocks(self):
        def never(payloads):
            raise AssertionError("must not run")

        decision = self.decide("terminal", {}, never)
        self.assertEqual(decision.label, "unjudgeable")
        self.assertEqual(adapter.directive_for(decision)["action"], "block")

    def test_protected_reference_skips_the_policy_and_blocks(self):
        def never(payloads):
            raise AssertionError("must not run")

        decision = self.decide("terminal", {"command": "hermes plugins disable x"}, never)
        self.assertEqual(decision.label, "refused")
        self.assertEqual(adapter.directive_for(decision)["action"], "block")

    def test_policy_verdict_is_passed_through(self):
        decision = self.decide("terminal", {"command": "ls"}, lambda p: adapter.Verdict("ask", "q"))
        self.assertEqual(decision.label, "ask")


class DirectiveTests(unittest.TestCase):
    def test_block_becomes_block_directive(self):
        self.assertEqual(adapter.to_hermes_directive(adapter.Verdict("block", "stop")), {"action": "block", "message": "stop"})

    def test_ask_is_always_a_block_that_tells_the_agent_to_ask_the_user(self):
        directive = adapter.to_hermes_directive(adapter.Verdict("ask", "sure?"))
        self.assertEqual(directive["action"], "block")
        self.assertIn("sure?", directive["message"])
        self.assertIn("ask the user", directive["message"])

    def test_allow_proceeds(self):
        self.assertIsNone(adapter.to_hermes_directive(adapter.Verdict("allow")))

    def test_block_always_carries_a_message(self):
        self.assertTrue(adapter.to_hermes_directive(adapter.Verdict("block"))["message"])


class ResolveCwdTests(unittest.TestCase):
    def test_first_non_empty_lookup_wins(self):
        self.assertEqual(adapter.resolve_cwd("t", (lambda t: None, lambda t: "/a", lambda t: "/b")), "/a")

    def test_failing_lookup_is_skipped(self):
        def boom(task):
            raise RuntimeError("x")

        self.assertEqual(adapter.resolve_cwd("t", (boom, lambda t: "/b")), "/b")

    def test_unknown_stays_unknown(self):
        self.assertIsNone(adapter.resolve_cwd("t", (lambda t: "",)))
        self.assertIsNone(adapter.resolve_cwd("t", ()))
        self.assertIsNone(adapter.resolve_cwd("t", (lambda t: None, lambda t: 5)))

    def test_relative_directories_are_not_accepted(self):
        self.assertEqual(adapter.resolve_cwd("t", (lambda t: ".", lambda t: "sub", lambda t: "/abs")), "/abs")
        self.assertIsNone(adapter.resolve_cwd("t", (lambda t: ".",)))

    def test_lookups_run_without_a_task_id(self):
        self.assertEqual(adapter.resolve_cwd(None, (lambda t: "/a",)), "/a")


if __name__ == "__main__":
    unittest.main()
