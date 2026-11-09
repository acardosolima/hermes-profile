#!/usr/bin/env bash
# skill-mirror-drift.sh — PostToolUse warning when skills/ SSOT edits leave mirrors stale.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

exec "$PLUGIN_ROOT/bin/harness" hook skill-mirror-drift
