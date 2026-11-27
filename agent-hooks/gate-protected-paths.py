#!/usr/bin/env python
"""pre_tool_call shell hook: block tool calls that touch protected identity files.

Hermes' built-in write denylist only guards the file tools (write_file/patch)
and does NOT cover the terminal tool, which runs as the same OS user and can
read/write anything via shell redirection (`cat > ~/.gitconfig`, `sed -i`,
`cp`, ...). This hook closes that gap for a fixed set of identity/credential
paths that steer git/SSH behavior:

    ~/.gitconfig , ~/.gitconfig.d/   (git identity + url.insteadOf SSH routing)
    ~/.ssh/                          (SSH keys and config)
    ~/.githooks/                     (shared hooks: secret scan, push confirm)

Also blocks terminal commands that substitute another credential for an SSH
key passphrase: printing a gh token, installing a git credential helper,
GIT_ASKPASS, Authorization headers, or an HTTPS git push.
A public HTTPS clone or fetch is allowed: it needs no passphrase.

Wire contract (agent/shell_hooks.py):
  stdin : {"hook_event_name","tool_name","tool_input":{...},"session_id","cwd","extra"}
          terminal -> tool_input.command ; write_file/patch -> tool_input.path
  block : exit code 2, plus canonical {"action":"block","message":...} on stdout
  allow : print "{}" and exit 0

This is defense-in-depth, NOT a security boundary: a hook runs as the same OS
user and a determined process can build the path from pieces to evade a literal
match, or disable the hook. It reliably stops the common, direct case (a plain
reference to a protected path) and forces the human to make these edits.
"""

from __future__ import annotations

import json
import sys
from typing import NoReturn

# Substring markers (matched case-insensitively). Each protected directory is a
# dotfile, so the leading dot keeps ordinary words from false-positiving:
# ".ssh" never matches `ssh -T ...` or `ssh-keygen`, only a `.ssh` path.
PROTECTED_TOKENS = (
    ".gitconfig",   # also covers ~/.gitconfig.d/
    ".githooks",
    ".ssh",
)

# Terminal-only. These are how an agent pushes without the SSH key passphrase
# by using a token gh already stored. Matched case-insensitively.
BYPASS_TOKENS = (
    "gh auth token",
    "auth git-credential",
    "gh auth setup-git",
    "git_askpass",
    "credential.helper",
    "extraheader",
    "x-access-token",
    "gh_token",
    "github_token",
)

# Only these tools carry a filesystem target worth inspecting. The matcher in
# config.yaml should already scope the hook to them; this is belt-and-suspenders.
TERMINAL_TOOLS = {"terminal"}
FILE_TOOLS = {"write_file", "patch"}


def allow() -> NoReturn:
    print("{}")
    sys.exit(0)


def block(reason: str) -> NoReturn:
    sys.stdout.write(json.dumps({"action": "block", "message": reason}))
    sys.stdout.flush()
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def subject_for(tool_name: str, tool_input: dict) -> str:
    """Return the text to scan for a protected path, or '' when nothing applies."""
    if tool_name in TERMINAL_TOOLS:
        value = tool_input.get("command")
        return value if isinstance(value, str) else ""
    if tool_name in FILE_TOOLS:
        value = tool_input.get("path")
        return value if isinstance(value, str) else ""
    return ""


def protected_hit(subject: str, tool_name: str = "") -> str:
    """Return the first blocked token found in *subject*, or '' when clean."""
    haystack = subject.replace("\\", "/").lower()
    tokens = PROTECTED_TOKENS
    if tool_name in TERMINAL_TOOLS:
        tokens = PROTECTED_TOKENS + BYPASS_TOKENS
    for token in tokens:
        if token in haystack:
            return token
    # Public clone/fetch over HTTPS needs no passphrase. Push must not switch
    # to HTTPS to avoid the SSH prompt.
    push = "git " + "push"
    if tool_name in TERMINAL_TOOLS and push in haystack and "https://github.com" in haystack:
        return "https github push"
    return ""


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Unparseable payload: don't break unrelated tools on a parse error.
        allow()

    if not isinstance(payload, dict):
        allow()

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        allow()

    subject = subject_for(tool_name, tool_input)
    if not subject:
        allow()

    token = protected_hit(subject, tool_name)
    if not token:
        allow()

    block(
        f"Blocked: this {tool_name} call references a protected identity path "
        f"('{token}'). Writes/reads to ~/.gitconfig, ~/.gitconfig.d, ~/.ssh and "
        f"~/.githooks are gated, and so is substituting a stored token or an "
        f"HTTPS URL for the SSH key passphrase. The user must type that "
        f"passphrase themselves. This hook is not an OS boundary: revoke the "
        f"other credential or a process that evades this match can still use it."
    )


if __name__ == "__main__":
    main()
