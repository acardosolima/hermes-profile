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


def protected_hit(subject: str) -> str:
    """Return the first protected token found in *subject*, or '' when clean."""
    haystack = subject.replace("\\", "/").lower()
    for token in PROTECTED_TOKENS:
        if token in haystack:
            return token
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

    token = protected_hit(subject)
    if not token:
        allow()

    block(
        f"Blocked: this {tool_name} call references a protected identity path "
        f"('{token}'). Writes/reads to ~/.gitconfig, ~/.gitconfig.d, ~/.ssh and "
        f"~/.githooks are gated by the harness so the agent cannot alter git "
        f"identity or SSH controls. The user must make this change themselves."
    )


if __name__ == "__main__":
    main()
