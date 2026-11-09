#!/usr/bin/env bash
# release-preflight-host-smoke.sh
# Run host workflow smoke for all dist hosts with REQUIRED=1 (fail-closed).
#
# Usage: bash scripts/release-preflight-host-smoke.sh
#
# Test-only: set HARNESS_PREFLIGHT_HOST_SMOKE_CMD to override the per-host smoke
# command (invoked as $HARNESS_PREFLIGHT_HOST_SMOKE_CMD "$host" with REQUIRED env).
# Test-only: set HARNESS_PREFLIGHT_HOST_CLI_PROBE_CMD to override the host-CLI
# presence probe (invoked as $CMD "$cli"; default: command -v).
#
# Runner scope: on GitHub-hosted runners (GITHUB_ACTIONS=true) a host whose CLI
# is not provisioned is SKIPPED with a visible line instead of failing. The
# fail-closed consumer of this gate is the operator-machine release preflight
# (H7); the tag-triggered workflow re-runs preflight on a runner that cannot
# host the CLIs, and a hard fail there would block every release (observed:
# v5.3.0 run 29679591686). Outside GITHUB_ACTIONS, a missing CLI still fails.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=lib/host-registry.sh
source "${SCRIPT_DIR}/lib/host-registry.sh"
HOST_REGISTRY_PATH="${ROOT_DIR}/hosts/registry.json"

pass_count=0
total_count=0
skip_count=0
any_failed=0

host_cli_for() {
  case "$1" in
    # Cursor 公式 docs (2026-08-11) は全例を `agent` 表記に統一し、`cursor-agent`
    # は install script 内で "legacy alias" と明記された。どちらの名前でも
    # presence を検出しないと、alias 廃止後に runner を「CLI 不在」と誤判定して
    # 全 cursor smoke が無言 SKIP になる (Task 133.1)。空白区切りの候補列。
    cursor) echo "agent cursor-agent" ;;
    *) echo "$1" ;;
  esac
}

# 候補列のうち 1 つでも見つかれば present とみなす。
host_cli_present() {
  local cli
  # shellcheck disable=SC2086  # 空白区切りの候補列を意図的に分割する
  for cli in $1; do
    if [ -n "${HARNESS_PREFLIGHT_HOST_CLI_PROBE_CMD:-}" ]; then
      if "${HARNESS_PREFLIGHT_HOST_CLI_PROBE_CMD}" "$cli" >/dev/null 2>&1; then
        return 0
      fi
    elif command -v "$cli" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

while IFS= read -r h; do
  [ -n "$h" ] || continue
  total_count=$((total_count + 1))

  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    cli_bin="$(host_cli_for "$h")"
    if ! host_cli_present "$cli_bin"; then
      echo "host-smoke ${h}: SKIP (runner lacks ${cli_bin}; operator preflight is the fail-closed consumer)"
      skip_count=$((skip_count + 1))
      continue
    fi
  fi

  # Per-host fail-closed: HARNESS_<HOST>_WORKFLOW_SMOKE_REQUIRED=1
  required_var="HARNESS_$(printf '%s' "$h" | tr '[:lower:]' '[:upper:]')_WORKFLOW_SMOKE_REQUIRED"
  export "${required_var}=1"

  if [ -n "${HARNESS_PREFLIGHT_HOST_SMOKE_CMD:-}" ]; then
    if "${HARNESS_PREFLIGHT_HOST_SMOKE_CMD}" "$h"; then
      echo "host-smoke ${h}: PASS"
      pass_count=$((pass_count + 1))
    else
      echo "host-smoke ${h}: FAIL"
      any_failed=1
    fi
  elif bash "${ROOT_DIR}/tests/test-host-workflow-smoke.sh" --host "$h"; then
    echo "host-smoke ${h}: PASS"
    pass_count=$((pass_count + 1))
  else
    echo "host-smoke ${h}: FAIL"
    any_failed=1
  fi
done < <(host_registry_dist_hosts)

if [ "$total_count" -eq 0 ]; then
  echo "host-smoke summary: 0/0 pass" >&2
  exit 1
fi

if [ "$skip_count" -gt 0 ]; then
  echo "host-smoke summary: ${pass_count}/${total_count} pass (${skip_count} skipped on runner)"
else
  echo "host-smoke summary: ${pass_count}/${total_count} pass"
fi

if [ "$any_failed" -ne 0 ]; then
  exit 1
fi

exit 0
