#!/usr/bin/env python
"""pre_tool_call shell hook: block skill_manage unless explicitly authorized.

Reads the hook's JSON payload from stdin, blocks (exit 2) if the tool being
called is skill_manage, otherwise emits '{}' (no-op) so other tools pass
through untouched. Does NOT affect skill_view / skills_list (read-only).
"""
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    # Unparseable payload: don't block unrelated tools on a parse error.
    print("{}")
    sys.exit(0)

tool_name = payload.get("tool_name") or ""

if tool_name == "skill_manage":
    sys.stderr.write(
        "skill_manage (create/patch/delete skills) requires explicit user "
        "authorization. Ask the user before retrying.\n"
    )
    sys.exit(2)

print("{}")
sys.exit(0)
