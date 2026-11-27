"""Tests for the gate-protected-paths pre_tool_call hook.

The hook blocks terminal/write_file/patch tool calls that touch protected
identity/credential files (~/.gitconfig*, ~/.ssh, ~/.githooks). Command text
here is DATA fed on stdin; nothing in these payloads is ever executed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "agent-hooks" / "gate-protected-paths.py"


def run_hook(payload: dict) -> subprocess.CompletedProcess:
    """Invoke the hook as Hermes would: JSON on stdin, inspect exit code/stdout."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def terminal(command: str) -> dict:
    return {"hook_event_name": "pre_tool_call", "tool_name": "terminal", "tool_input": {"command": command}}


def file_tool(tool_name: str, path: str) -> dict:
    return {"hook_event_name": "pre_tool_call", "tool_name": tool_name, "tool_input": {"path": path}}


class BlocksProtectedWrites(unittest.TestCase):
    def assert_blocked(self, payload: dict) -> None:
        result = run_hook(payload)
        self.assertEqual(result.returncode, 2, f"expected block (exit 2), got {result.returncode}: {result.stderr}")
        # Canonical block JSON on stdout so the reason reaches the model.
        data = json.loads(result.stdout)
        self.assertEqual(data.get("action"), "block")
        self.assertTrue(data.get("message"), "block message must be non-empty")

    def assert_allowed(self, payload: dict) -> None:
        result = run_hook(payload)
        self.assertEqual(result.returncode, 0, f"expected allow (exit 0), got {result.returncode}: {result.stderr}")

    # --- terminal: protected paths are blocked regardless of read/write ---
    def test_heredoc_overwrite_gitconfig_blocked(self):
        self.assert_blocked(terminal("cat > ~/.gitconfig <<'EOF'\n[user]\nEOF"))

    def test_gitconfig_d_blocked(self):
        self.assert_blocked(terminal('cp x "C:/Users/Adriano/.gitconfig.d/personal"'))

    def test_home_var_gitconfig_blocked(self):
        self.assert_blocked(terminal("echo x > $HOME/.gitconfig"))

    def test_ssh_dir_blocked(self):
        self.assert_blocked(terminal("cat ~/.ssh/id_ed25519_personal_auth"))

    def test_githooks_blocked(self):
        self.assert_blocked(terminal('rm -f "C:/Users/Adriano/.githooks/pre-push"'))

    def test_sed_inplace_gitconfig_blocked(self):
        self.assert_blocked(terminal("sed -i 's/a/b/' ~/.gitconfig"))

    # --- terminal: ordinary commands pass through ---
    def test_plain_git_command_allowed(self):
        self.assert_allowed(terminal("git remote -v"))

    def test_ssh_connect_not_dotssh_allowed(self):
        # `ssh`/`ssh-keygen` without the .ssh path must not false-positive.
        self.assert_allowed(terminal("ssh -T git@github.com-personal"))


    def test_gh_auth_token_blocked(self):
        self.assert_blocked(terminal("gh auth token"))

    def test_askpass_https_push_blocked(self):
        self.assert_blocked(terminal("GIT_ASKPASS=./askpass.cmd git push https://github.com/acardosolima/hermes-profile.git HEAD"))

    def test_credential_helper_override_blocked(self):
        self.assert_blocked(terminal("git -c credential.helper='!gh auth git-credential' push https://github.com/acardosolima/hermes-profile.git HEAD"))

    def test_bearer_header_push_blocked(self):
        self.assert_blocked(terminal("git -c http.extraHeader='Authorization: Bearer x' push https://github.com/acardosolima/hermes-profile.git HEAD"))


    def test_https_clone_allowed(self):
        self.assert_allowed(terminal('git clone https://github.com/NousResearch/hermes-agent.git'))

    def test_https_push_blocked(self):
        self.assert_blocked(terminal('git push https://github.com/acardosolima/hermes-profile.git HEAD'))

    def test_ssh_push_still_allowed(self):
        self.assert_allowed(terminal("git push git@github.com:acardosolima/hermes-profile.git HEAD:feat/lock-default-profile"))

    def test_gh_pr_view_still_allowed(self):
        self.assert_allowed(terminal("gh pr view 20"))

    def test_unrelated_command_allowed(self):
        self.assert_allowed(terminal("ls -la && echo done"))

    # --- write_file / patch: protected target paths are blocked ---
    def test_write_file_gitconfig_blocked(self):
        self.assert_blocked(file_tool("write_file", "C:/Users/Adriano/.gitconfig"))

    def test_write_file_tilde_gitconfig_blocked(self):
        self.assert_blocked(file_tool("write_file", "~/.gitconfig.d/personal-url-rewrite"))

    def test_patch_ssh_config_blocked(self):
        self.assert_blocked(file_tool("patch", "C:/Users/Adriano/.ssh/config"))

    def test_write_file_project_path_allowed(self):
        self.assert_allowed(file_tool("write_file", "C:/Users/Adriano/Documents/repositories/personal/x/app.py"))

    # --- robustness ---
    def test_unparseable_stdin_allows(self):
        result = subprocess.run(
            [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_unknown_tool_allowed(self):
        self.assert_allowed({"hook_event_name": "pre_tool_call", "tool_name": "web_search", "tool_input": {"query": "~/.ssh"}})


if __name__ == "__main__":
    unittest.main()
