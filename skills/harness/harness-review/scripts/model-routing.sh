#!/usr/bin/env bash
# Resolve Harness model/effort routing from a small role-tier contract.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/host-registry.sh
source "${SCRIPT_DIR}/lib/host-registry.sh"
HOST_REGISTRY_PATH="$(cd "${SCRIPT_DIR}/.." && pwd)/hosts/registry.json"

HOST="codex"
TIER=""
ROLE=""
FIELD=""
FORMAT="json"

usage() {
  local hosts
  hosts="$(host_registry_routing_hosts 2>/dev/null | tr '\n' '|' | sed 's/|$//')"
  [ -n "$hosts" ] || hosts="codex|claude|cursor|grok"
  cat <<EOF
Usage:
  scripts/model-routing.sh --host ${hosts} --tier TIER [--format json|args|env] [--field model|effort]
  scripts/model-routing.sh --host ${hosts} --role ROLE [--format json|args|env] [--field model|effort]

Tiers: lite, standard, worker, deep, review, advisor, release, long-context, spark
Roles: explorer, worker, reviewer, advisor, plan, release, operator, long-context
Allowed --host values come from hosts/registry.json (routing_host).
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:-}"; shift 2 ;;
    --host=*) HOST="${1#*=}"; shift ;;
    --tier) TIER="${2:-}"; shift 2 ;;
    --tier=*) TIER="${1#*=}"; shift ;;
    --role) ROLE="${2:-}"; shift 2 ;;
    --role=*) ROLE="${1#*=}"; shift ;;
    --field) FIELD="${2:-}"; shift 2 ;;
    --field=*) FIELD="${1#*=}"; shift ;;
    --format) FORMAT="${2:-}"; shift 2 ;;
    --format=*) FORMAT="${1#*=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

role_to_tier() {
  case "$1" in
    explorer|reader|search|lite) printf 'lite\n' ;;
    worker|implementer)
      if [ "${HOST}" = "codex" ]; then
        printf 'worker\n'
      else
        printf 'standard\n'
      fi
      ;;
    setup|standard) printf 'standard\n' ;;
    plan|planner|architect|deep) printf 'deep\n' ;;
    reviewer|review|adversarial-review) printf 'review\n' ;;
    advisor) printf 'advisor\n' ;;
    release|closeout) printf 'release\n' ;;
    operator) printf 'standard\n' ;;
    long-context|long_context) printf 'long-context\n' ;;
    spark) printf 'spark\n' ;;
    *) echo "ERROR: unknown role: $1" >&2; exit 2 ;;
  esac
}

if [ -z "$TIER" ]; then
  if [ -n "$ROLE" ]; then
    TIER="$(role_to_tier "$ROLE")"
  else
    TIER="standard"
  fi
fi

if ! host_registry_is_routing_host "$HOST"; then
  echo "ERROR: unsupported host: $HOST (not in hosts/registry.json routing_host list)" >&2
  exit 2
fi

# HARNESS_BRAIN_MODEL switches the Claude brain tiers (deep/advisor) only.
# Fable 5.1 starts at high; an explicit Opus 5 selection retains its xhigh
# contract. Other hosts and the independent Claude review route stay unchanged.
CLAUDE_BRAIN_MODEL="claude-fable-5-1"
CLAUDE_BRAIN_EFFORT="high"
case "${HARNESS_BRAIN_MODEL:-fable}" in
  fable) ;;
  opus|opus5) CLAUDE_BRAIN_MODEL="claude-opus-5"; CLAUDE_BRAIN_EFFORT="xhigh" ;;
  *) echo "ERROR: unknown HARNESS_BRAIN_MODEL: ${HARNESS_BRAIN_MODEL} (use opus|opus5|fable)" >&2; exit 2 ;;
esac

MODEL=""
EFFORT=""

if [ "$HOST" = "codex" ]; then
  # Frontier roles use astra with their existing effort. Breezing workers
  # retain the dedicated Luna/max tier, independent of review capacity.
  case "$TIER" in
    lite) MODEL="gpt-5.6-luna"; EFFORT="low" ;;
    standard|deep) MODEL="gpt-6-astra"; EFFORT="xhigh" ;;
    worker) MODEL="gpt-5.6-luna"; EFFORT="max" ;;
    review|advisor) MODEL="gpt-6-astra"; EFFORT="xhigh" ;;
    release|long-context) MODEL="gpt-6-astra"; EFFORT="high" ;;
    spark) MODEL="gpt-5.3-codex-spark"; EFFORT="low" ;;
    *) echo "ERROR: unknown codex tier: $TIER" >&2; exit 2 ;;
  esac
elif [ "$HOST" = "cursor" ]; then
  case "$TIER" in
    lite) MODEL="composer-2-fast"; EFFORT="low" ;;
    standard) MODEL="composer-2.5-fast"; EFFORT="medium" ;;
    # claude-fable-5 verified in ~/.cursor/cli-config.json (2026-07-25);
    # opus-4-8-thinking retired per the same operator decision as the claude catalog.
    deep|advisor) MODEL="claude-fable-5"; EFFORT="xhigh" ;;
    review) MODEL="composer-2.5-fast"; EFFORT="xhigh" ;;
    release) MODEL="composer-2.5-fast"; EFFORT="high" ;;
    long-context) MODEL="gemini-3.1-pro"; EFFORT="high" ;;
    spark) echo "ERROR: spark tier is codex-only" >&2; exit 2 ;;
    *) echo "ERROR: unknown cursor tier: $TIER" >&2; exit 2 ;;
  esac
elif [ "$HOST" = "grok" ]; then
  # Grok catalog — verified 2026-08-13 against the CLI that is actually
  # installed (`grok 0.2.118`, "Grok Build TUI"), reading the account catalog
  # it fetched from cli-chat-proxy.grok.com/v1/models. Operator-ratified.
  #
  #   grok-4.6   500k ctx, DEFAULT, "SpaceXAI's latest frontier model",
  #              reasoning effort: xhigh (default) | high | medium | low
  #   grok-4.5   500k ctx, reasoning effort: high (default) | medium | low
  #
  # That is the WHOLE catalog for this account — there is no third id.
  #
  # Two earlier tables were wrong for the same reason. Both were derived from
  # `grok-cli` (the TypeScript project at LocalWork/Code/grok-cli), which is a
  # DIFFERENT PRODUCT from the installed Rust `grok`. The v1.1.7 table
  # (grok-4.3 / grok-4.20-* / grok-3-mini) and the table before it
  # (grok-composer-2.5-fast) both pinned ids that do not exist here, so every
  # call would have failed. Ironically the pre-2026-08-12 `grok-4.5` WAS real —
  # its comment said "observed on CLI 0.2.93", i.e. measured against the
  # installed binary rather than a lookalike repo.
  #
  # Rule this cost us twice: verify capability and catalogue against the binary
  # that actually runs (CLAUDE.md FACT-4), not against a same-named source tree.
  #
  # EFFORT values below stay inside each model's own advertised vocabulary.
  # Keep model IDs only here — skills must not hardcode them.
  case "$TIER" in
    lite) MODEL="grok-4.5"; EFFORT="low" ;;
    standard) MODEL="grok-4.5"; EFFORT="medium" ;;
    deep|advisor) MODEL="grok-4.6"; EFFORT="xhigh" ;;
    review) MODEL="grok-4.6"; EFFORT="xhigh" ;;
    release) MODEL="grok-4.6"; EFFORT="high" ;;
    long-context) MODEL="grok-4.6"; EFFORT="high" ;;
    spark) echo "ERROR: spark tier is codex-only" >&2; exit 2 ;;
    *) echo "ERROR: unknown grok tier: $TIER" >&2; exit 2 ;;
  esac
else
  case "$TIER" in
    lite) MODEL="claude-haiku-4-5"; EFFORT="low" ;;
    standard) MODEL="claude-sonnet-5"; EFFORT="medium" ;;
    deep|advisor) MODEL="$CLAUDE_BRAIN_MODEL"; EFFORT="$CLAUDE_BRAIN_EFFORT" ;;
    review) MODEL="claude-fable-5-1"; EFFORT="high" ;;
    release) MODEL="claude-sonnet-5"; EFFORT="high" ;;
    long-context) MODEL="sonnet[1m]"; EFFORT="high" ;;
    spark) echo "ERROR: spark tier is codex-only" >&2; exit 2 ;;
    *) echo "ERROR: unknown claude tier: $TIER" >&2; exit 2 ;;
  esac
fi

case "$FIELD" in
  "") ;;
  model) printf '%s\n' "$MODEL"; exit 0 ;;
  effort) printf '%s\n' "$EFFORT"; exit 0 ;;
  *) echo "ERROR: unsupported field: $FIELD" >&2; exit 2 ;;
esac

case "$FORMAT" in
  json)
    printf '{"host":"%s","tier":"%s","model":"%s","effort":"%s"}\n' "$HOST" "$TIER" "$MODEL" "$EFFORT"
    ;;
  args)
    if [ "$HOST" = "codex" ]; then
      printf '%s\n' "--model" "$MODEL" "-c" "model_reasoning_effort=\"$EFFORT\""
    elif [ "$HOST" = "cursor" ] || [ "$HOST" = "grok" ]; then
      printf '%s\n' "--model" "$MODEL"
    else
      printf '%s\n' "--model" "$MODEL" "--effort" "$EFFORT"
    fi
    ;;
  env)
    if [ "$HOST" = "codex" ]; then
      printf 'CODEX_MODEL=%s\nCODEX_EFFORT=%s\n' "$MODEL" "$EFFORT"
    elif [ "$HOST" = "cursor" ]; then
      printf 'CURSOR_MODEL=%s\nCURSOR_EFFORT=%s\n' "$MODEL" "$EFFORT"
    elif [ "$HOST" = "grok" ]; then
      printf 'GROK_MODEL=%s\nGROK_EFFORT=%s\n' "$MODEL" "$EFFORT"
    else
      printf 'CLAUDE_MODEL=%s\nCLAUDE_EFFORT=%s\n' "$MODEL" "$EFFORT"
    fi
    ;;
  *) echo "ERROR: unsupported format: $FORMAT" >&2; exit 2 ;;
esac
