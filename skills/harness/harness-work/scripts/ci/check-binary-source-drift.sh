#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Byte-identical comparison requires an environment-independent build:
# pin the toolchain to go.mod's go directive and drop VCS stamping
# (vcs.revision can never match a binary committed one commit earlier).
GO_DIRECTIVE="$(sed -n 's/^go //p' "$ROOT/go/go.mod" | head -1 | tr -d '[:space:]')"
if [ -n "$GO_DIRECTIVE" ]; then
  export GOTOOLCHAIN="go${GO_DIRECTIVE}"
fi

GOOS_VALUE="$(go env GOOS)"
GOARCH_VALUE="$(go env GOARCH)"
case "$GOOS_VALUE/$GOARCH_VALUE" in
  darwin/arm64) target="$ROOT/bin/harness-darwin-arm64" ;;
  darwin/amd64) target="$ROOT/bin/harness-darwin-amd64" ;;
  linux/amd64) target="$ROOT/bin/harness-linux-amd64" ;;
  windows/amd64) target="$ROOT/bin/harness-windows-amd64.exe" ;;
  *) echo "unsupported binary drift platform: $GOOS_VALUE/$GOARCH_VALUE" >&2; exit 0 ;;
esac

if [ ! -f "$target" ]; then
  echo "missing platform binary: ${target#$ROOT/}" >&2
  exit 1
fi

version="$(tr -d '[:space:]' < "$ROOT/VERSION")"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/harness-bin-drift.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT
built="$tmpdir/$(basename "$target")"

(
  cd "$ROOT/go"
  CGO_ENABLED=0 GOOS="$GOOS_VALUE" GOARCH="$GOARCH_VALUE" \
    go build -trimpath -buildvcs=false -ldflags "-s -w -X main.version=$version" -o "$built" ./cmd/harness
)

if ! cmp -s "$built" "$target"; then
  # CI pre-steps may overwrite the working-tree binary with a plain dev
  # build (validate-plugin.yml "Build harness binary for validation
  # scripts"). The gate's contract is committed-binary == source, so fall
  # back to the HEAD blob before declaring drift. A tampered commit still
  # fails: neither the working file nor the HEAD blob matches the rebuild.
  committed="$tmpdir/committed-$(basename "$target")"
  if git -C "$ROOT" cat-file blob "HEAD:${target#$ROOT/}" >"$committed" 2>/dev/null \
    && cmp -s "$built" "$committed"; then
    echo "binary/source drift OK (via HEAD blob; working-tree copy was overwritten): ${target#$ROOT/}"
    exit 0
  fi
  echo "binary/source drift detected for ${target#$ROOT/}" >&2
  echo "rebuild with: cd go && GOTOOLCHAIN=go${GO_DIRECTIVE:-<go.mod go directive>} CGO_ENABLED=0 GOOS=$GOOS_VALUE GOARCH=$GOARCH_VALUE go build -trimpath -buildvcs=false -ldflags '-s -w -X main.version=$version' -o ../${target#$ROOT/} ./cmd/harness" >&2
  exit 1
fi

echo "binary/source drift OK: ${target#$ROOT/}"
