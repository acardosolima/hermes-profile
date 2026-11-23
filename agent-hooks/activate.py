#!/usr/bin/env python3
"""Point this machine's profile at the skill_manage hook.

The hook command is a literal path. Hermes does not expand variables, and
the profile directory is not the same on Linux, macOS, and Windows. Nothing
in git stores that path. Run this after install, from the repo or from the
installed copy:

    python agent-hooks/activate.py
    python agent-hooks/activate.py --profile master

On Windows, Hermes runs a .py hook with its own interpreter. On Linux and
macOS the script's shebang is used, so this also marks the hook executable.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from pathlib import Path

# (matcher, script filename). Each becomes one hooks.pre_tool_call entry.
HOOKS: tuple[tuple[str, str], ...] = (
    ("skill_manage", "gate-skill-manage.py"),
    ("terminal|write_file|patch", "gate-protected-paths.py"),
)
HOOK_NAMES = tuple(name for _, name in HOOKS)


def profile_dir(name: str) -> Path:
    """Directory Hermes uses for *name*. Asks Hermes; does not guess a home."""
    try:
        shown = subprocess.run(
            ["hermes", "profile", "show", name],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", None) or exc
        raise SystemExit(f"could not read profile {name!r} from hermes: {detail}") from exc
    for line in shown.stdout.splitlines():
        if line.startswith("Path:"):
            path = Path(line.split(":", 1)[1].strip())
            if path.is_dir():
                return path
            raise SystemExit(f"hermes reported {path}, which is not a directory")
    raise SystemExit("hermes profile show did not print a Path line")


def hook_command(script: Path) -> str:
    """Command Hermes can run on this OS, with no shell and no env expansion."""
    script = script.resolve()
    if not script.is_file():
        raise SystemExit(f"hook script is not installed at {script}")
    if os.name != "nt":
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    # Forward slashes: Windows accepts them, and a backslash would be eaten
    # if this string were ever parsed by a POSIX shell.
    return script.as_posix()


def write_allowlist(profile: Path, commands: list[str]) -> None:
    path = profile / "shell-hooks-allowlist.json"
    data = {"approvals": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} is not valid JSON ({exc})") from exc
        if isinstance(loaded, dict) and isinstance(loaded.get("approvals"), list):
            data = loaded
    kept = []
    for entry in data["approvals"]:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        existing = str(entry.get("command") or "")
        if entry.get("event") == "pre_tool_call" and existing.endswith(HOOK_NAMES):
            continue
        kept.append(entry)
    for command in commands:
        kept.append({"event": "pre_tool_call", "command": command})
    data["approvals"] = kept
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="master")
    args = parser.parse_args()
    profile = profile_dir(args.profile)
    specs = []
    commands = []
    for matcher, name in HOOKS:
        command = hook_command(profile / "agent-hooks" / name)
        commands.append(command)
        specs.append({"matcher": matcher, "command": command, "timeout": 5, "fail_closed": True})
    subprocess.run(
        ["hermes", "-p", args.profile, "config", "set", "hooks.pre_tool_call", json.dumps(specs)],
        check=True,
    )
    write_allowlist(profile, commands)
    for command in commands:
        print(f"hook command: {command}")
    print(f"allowlist:    {profile / 'shell-hooks-allowlist.json'}")


if __name__ == "__main__":
    main()
