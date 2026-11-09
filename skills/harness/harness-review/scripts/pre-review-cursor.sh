#!/usr/bin/env bash
# pre-review-cursor.sh — Fresh-context Cursor advisory pre-review (read-only)
#
# Runs one read-only composer pass before the brain's primary review verdict.
# Findings are advisory; APPROVE / REQUEST_CHANGES remain brain-only.
#
# Usage:
#   bash scripts/pre-review-cursor.sh [--base <ref>]
#
# Defaults:
#   --base HEAD~1
#
# Testability hooks:
#   HARNESS_PRE_REVIEW_CURSOR_COMPANION — override cursor-companion.sh path
#   HARNESS_PRE_REVIEW_MODEL_ROUTER     — override model-routing.sh path
#
# Exit codes:
#   0 — findings emitted (PRE_REVIEW_FINDINGS:) or fail-open skip (PRE_REVIEW_SKIPPED:)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPANION="${HARNESS_PRE_REVIEW_CURSOR_COMPANION:-${SCRIPT_DIR}/cursor-companion.sh}"
MODEL_ROUTER="${HARNESS_PRE_REVIEW_MODEL_ROUTER:-${SCRIPT_DIR}/model-routing.sh}"
BASE_REF="HEAD~1"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/pre-review-cursor.sh [--base <ref>]

Fresh-context Cursor advisory pre-review (read-only). Emits PRE_REVIEW_FINDINGS
on success or PRE_REVIEW_SKIPPED on companion failure (fail-open, exit 0).
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base)
      BASE_REF="${2:-}"
      if [ -z "${BASE_REF}" ]; then
        echo "ERROR: --base requires a ref" >&2
        exit 2
      fi
      shift 2
      ;;
    --base=*)
      BASE_REF="${1#--base=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -x "${COMPANION}" ]; then
  echo "PRE_REVIEW_SKIPPED: cursor-companion not found or not executable"
  exit 0
fi

MODEL=""
if [ -x "${MODEL_ROUTER}" ]; then
  MODEL="$(bash "${MODEL_ROUTER}" --host cursor --tier review --field model 2>/dev/null || true)"
fi

DIFF_STAT="$(git diff --stat "${BASE_REF}..HEAD" 2>/dev/null || true)"
DIFF_TEXT="$(git diff "${BASE_REF}..HEAD" 2>/dev/null || true)"

PROMPT="$(cat <<EOF
Review this diff as an advisory pre-review pass only.
Do not emit a final review verdict — findings and severity notes only.

Base ref: ${BASE_REF}
Focus on bugs, regressions, missing tests, and unsafe assumptions.

Diff stat:
${DIFF_STAT}

Diff:
${DIFF_TEXT}
EOF
)"

COMPANION_ARGS=(task)
if [ -n "${MODEL}" ]; then
  COMPANION_ARGS+=(--model "${MODEL}")
fi
COMPANION_ARGS+=("${PROMPT}")

set +e
FINDINGS="$(bash "${COMPANION}" "${COMPANION_ARGS[@]}" 2>&1)"
RC=$?
set -e

if [ "${RC}" -ne 0 ]; then
  REASON="$(printf '%s' "${FINDINGS}" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [ -z "${REASON}" ]; then
    REASON="companion exit ${RC}"
  fi
  echo "PRE_REVIEW_SKIPPED: ${REASON}"
  exit 0
fi

echo "PRE_REVIEW_FINDINGS:"
printf '%s\n' "${FINDINGS}"
exit 0
