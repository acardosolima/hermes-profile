#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LEDGER="$ROOT/docs/branch-alignment-ledger.md"

if [ ! -f "$LEDGER" ]; then
  echo "missing docs/branch-alignment-ledger.md" >&2
  exit 1
fi

required=(
  1873c8a3
  6ac3eec0
  4d7b6245
  3b8e64db
  5249ad76
  5a2d0df9
  d4b8573c
  d9b3fd34
  2141c7ef
  8097802e
  fa88d4cf
)

for sha in "${required[@]}"; do
  if ! grep -q "$sha" "$LEDGER"; then
    echo "branch alignment ledger missing commit: $sha" >&2
    exit 1
  fi
done

if grep -nE '\|[[:space:]]*(pending|todo|未処理)[[:space:]]*\|' "$LEDGER"; then
  echo "branch alignment ledger has unresolved entries" >&2
  exit 1
fi

echo "branch alignment ledger OK"
