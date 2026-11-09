#!/usr/bin/env bash
# night-watch-install.sh — opt-in Night Watch cron marker install (Phase 99.1)
#
# Writes NIGHT_WATCH_ENABLED=true into a target settings fixture only.
# Never touches real ~/.claude/settings.json unless HARNESS_NIGHT_WATCH_INSTALL_TARGET is set
# explicitly (tests use tempdir fixtures).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT}/templates/night-watch-cron.template"

usage() {
  echo "Usage: night-watch-install.sh [--target <settings.json>] [--enable|--disable]" >&2
}

target="${HARNESS_NIGHT_WATCH_INSTALL_TARGET:-}"
enabled=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      target="${2:-}"
      shift 2
      ;;
    --enable)
      enabled=true
      shift
      ;;
    --disable)
      enabled=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$target" ]]; then
  echo "install target required (set --target or HARNESS_NIGHT_WATCH_INSTALL_TARGET)" >&2
  exit 1
fi

real_home="$(python3 - <<'PY'
import os
print(os.path.realpath(os.path.expanduser("~/.claude/settings.json")))
PY
)"
real_target="$(python3 - "$target" <<'PY'
import os, sys
print(os.path.realpath(os.path.expanduser(sys.argv[1])))
PY
)"

if [[ "$real_target" == "$real_home" && -z "${HARNESS_NIGHT_WATCH_ALLOW_REAL_INSTALL:-}" ]]; then
  echo "refusing to modify real ~/.claude/settings.json (use fixture/tempdir target)" >&2
  exit 1
fi

mkdir -p "$(dirname "$target")"
if [[ ! -f "$target" ]]; then
  echo '{}' >"$target"
fi

python3 - "$target" "$enabled" "$TEMPLATE" <<'PY'
import json
import os
import sys

target, enabled_raw, template_path = sys.argv[1:4]
enabled = enabled_raw.lower() == "true"

with open(target, encoding="utf-8") as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError:
        data = {}
if not isinstance(data, dict):
    data = {}

env = data.setdefault("env", {})
if not isinstance(env, dict):
    env = {}
    data["env"] = env

env["NIGHT_WATCH_ENABLED"] = "true" if enabled else "false"
env["HARNESS_NIGHT_WATCH_CRON_TEMPLATE"] = template_path

with open(target, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

echo "night-watch install: target=$target NIGHT_WATCH_ENABLED=$([[ "$enabled" == true ]] && echo true || echo false)"
