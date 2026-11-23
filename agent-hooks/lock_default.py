#!/usr/bin/env python3
"""Turn off every tool in this machine's default Hermes profile.

harness-guard ships only in the installed profile. The default profile is the
Hermes root and cannot be deleted, so a chat started there would run unguarded.
This adds every toolset Hermes knows to the default profile's
agent.disabled_toolsets. Run it after install, from the repo or from the
installed copy:

    python agent-hooks/lock_default.py
    python agent-hooks/lock_default.py --profile master
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from typing import Any, Optional

_ENABLED_COUNT = re.compile(r"\((\d+)/\d+\)")


def toolset_names(disabled: Optional[list], known: list[Optional[dict]], mcp_servers: Optional[dict]) -> list[str]:
    """Every toolset to disable: already disabled, known per platform, and MCP servers."""
    names = set(disabled or [])
    for per_platform in known:
        for platform_names in (per_platform or {}).values():
            names.update(platform_names)
    names.update(mcp_servers or {})
    return sorted(names)


def enabled_counts(summary: str) -> list[int]:
    """Enabled toolset count of each platform in `hermes tools --summary` output."""
    return [int(count) for count in _ENABLED_COUNT.findall(summary)]


def hermes(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["hermes", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SystemExit(f"could not run hermes: {exc}") from exc


def config_value(profile: str, key: str) -> Any:
    """Value of *key* in *profile*'s config, or None when the key or the profile does not exist."""
    result = hermes("-p", profile, "config", "get", key, "--json")
    if result.returncode == 0:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"hermes -p {profile} config get {key} is not valid JSON: {exc}") from exc
    if any(marker in result.stdout + result.stderr for marker in ("Config key not set", "does not exist")):
        return None
    raise SystemExit(f"hermes -p {profile} config get {key} failed: {result.stderr or result.stdout}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default="master", help="installed profile whose known toolsets are also read")
    args = parser.parse_args()
    names = toolset_names(
        disabled=config_value("default", "agent.disabled_toolsets"),
        known=[
            config_value(profile, key)
            for profile in ("default", args.profile)
            for key in ("known_builtin_toolsets", "known_plugin_toolsets")
        ],
        mcp_servers=config_value("default", "mcp_servers"),
    )
    result = hermes("-p", "default", "config", "set", "agent.disabled_toolsets", json.dumps(names))
    if result.returncode != 0:
        raise SystemExit(f"could not set agent.disabled_toolsets: {result.stderr or result.stdout}")
    summary = hermes("-p", "default", "tools", "--summary").stdout
    counts = enabled_counts(summary)
    if not counts or any(counts):
        raise SystemExit(f"default profile still has tools enabled:\n{summary}")
    print("default profile: no tools enabled")


if __name__ == "__main__":
    main()
