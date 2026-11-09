#!/usr/bin/env bash
# night-watch-report.sh — Night Watch patrol report (Phase 99.1)
#
# Usage:
#   night-watch-report.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

dry_run=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true ;;
    -h|--help)
      echo "Usage: night-watch-report.sh [--dry-run]"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

args=(report --repo-root "$ROOT")
if [[ "$dry_run" == true ]]; then
  args+=(--dry-run)
fi

# 単一バイナリ配布規約: precompiled bin/harness を使う。未ビルド時のみ go run にフォールバック。
BIN="$ROOT/bin/harness"
case "$(uname -s)" in
  Darwin) BIN="$ROOT/bin/harness-darwin-$(uname -m | sed 's/x86_64/amd64/')" ;;
esac
if [[ -x "$BIN" ]]; then
  "$BIN" night-watch "${args[@]}"
elif [[ -x "$ROOT/bin/harness" ]]; then
  "$ROOT/bin/harness" night-watch "${args[@]}"
else
  (cd "$ROOT/go" && go run ./cmd/harness night-watch "${args[@]}")
fi
