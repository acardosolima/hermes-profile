#!/usr/bin/env bash
# codex-companion.sh — Proxy to official codex-plugin-cc companion
#
# 公式プラグイン openai/codex-plugin-cc の codex-companion.mjs を
# 動的に発見して呼び出す。Harness のスキル・エージェントは
# raw `codex exec` ではなく、このプロキシ経由で Codex を呼び出す。
#
# Usage:
#   bash scripts/codex-companion.sh task --write "Fix the bug"
#   bash scripts/codex-companion.sh review --base HEAD~3
#   bash scripts/codex-companion.sh setup --json
#   bash scripts/codex-companion.sh status
#   bash scripts/codex-companion.sh result <job-id>
#   bash scripts/codex-companion.sh cancel <job-id>
#
# Subcommands: task, review, adversarial-review, setup, status, result, cancel
#
# Effort 伝播:
#   task は明示 CLI/config > CODEX_EFFORT > role routing の順で解決する。
#   calculate-effort.sh は routing を明示的に無効化した互換経路だけで使う。
#   official companion が受け付けない max / ultra は Codex runtime の
#   `model_reasoning_effort` config へ渡す。公開 API の対応値とは別の契約。
#
# Worktree containment (Phase 92.2.2):
#   task 実行の前後で `bin/harness wt fingerprint` を呼び、$HOME 機微パスへの
#   書込変化があれば hard-stop する。`--cwd` / `--cd` は CWD ヒントであり書込境界ではない。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARY_ENV_GUARD="${SCRIPT_DIR}/codex-primary-environment-guard.sh"
MODEL_ROUTER="${SCRIPT_DIR}/model-routing.sh"
EXECUTION_ROOT="${HARNESS_CODEX_EXECUTION_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HARNESS_BIN_OVERRIDE="${HARNESS_BIN:-}"

resolve_harness_bin() {
  local candidate

  # An explicit binary is an operator contract: preserve it even when missing
  # so fingerprint_capture fails visibly at the exact requested path.
  if [ -n "${HARNESS_BIN_OVERRIDE}" ]; then
    printf '%s\n' "${HARNESS_BIN_OVERRIDE}"
    return 0
  fi

  if [ -n "${HARNESS_PLUGIN_ROOT:-}" ]; then
    candidate="${HARNESS_PLUGIN_ROOT}/bin/harness"
    if [ -x "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  fi

  candidate="${SCRIPT_DIR}/../bin/harness"
  if [ -x "${candidate}" ]; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  # Backward-compatible source-checkout fallback. EXECUTION_ROOT remains the
  # worktree being fingerprinted; it is not the preferred runtime bundle root.
  candidate="${EXECUTION_ROOT}/bin/harness"
  printf '%s\n' "${candidate}"
}

HARNESS_BIN="$(resolve_harness_bin)"
FP_BEFORE=""
FP_AFTER=""
CODEX_ROUTE_RESOLVED=0
CODEX_ROUTED_MODEL=""
CODEX_ROUTED_EFFORT=""
CODEX_REVIEW_ROUTE_RESOLVED=0
CODEX_REVIEW_ROUTED_MODEL=""
CODEX_REVIEW_ROUTED_EFFORT=""
CODEX_LEDGER_EMITTED=0
CODEX_NORMALIZED_ARGS=()
CODEX_EXPLICIT_MODEL=""
CODEX_EXPLICIT_EFFORT=""
CODEX_TASK_EFFORT=""
CODEX_STATE_MODE=""
CODEX_HAS_OUTPUT_SCHEMA=0
CODEX_HAS_EXTRA_CONFIG=0
CODEX_TASK_PROMPT_FILE=""
CODEX_TASK_WRITE_INTENT=0
CODEX_TASK_EXPLICIT_SANDBOX=0
CODEX_TARGET_CWD="${PWD}"
CODEX_SEEN_OPTIONS="|"
TASK_STDIN_CAPTURED=0
TASK_STDIN_CONTENT=""
REVIEW_COMPANION_ARGS=()
REVIEW_EXPLICIT_MODEL=0
REVIEW_EXPLICIT_MODEL_VALUE=""
REVIEW_EXPLICIT_EFFORT=""
REVIEW_APP_SERVER_DIR=""
REVIEW_APP_SERVER_SOCKET=""
REVIEW_APP_SERVER_ENDPOINT=""
REVIEW_APP_SERVER_READY_FILE=""
REVIEW_APP_SERVER_STATUS_FILE=""
REVIEW_APP_SERVER_PID=""
REVIEW_COMPANION_PID=""

# Orchestration ledger (Phase 90): record each delegation for the scorecard.
# This path exec()s into codex/node, so exit_code/duration are recorded null.
if [ -f "${SCRIPT_DIR}/lib/orchestration-ledger.sh" ]; then
  # shellcheck source=scripts/lib/orchestration-ledger.sh
  . "${SCRIPT_DIR}/lib/orchestration-ledger.sh" 2>/dev/null || true
fi
if ! command -v orch_emit_ledger >/dev/null 2>&1; then
  orch_emit_ledger() { return 0; }
fi

fingerprint_capture() {
  local output="$1"
  if [ ! -x "${HARNESS_BIN}" ]; then
    echo "ERROR: harness binary not found at ${HARNESS_BIN}" >&2
    return 1
  fi
  "${HARNESS_BIN}" wt fingerprint capture --output "${output}"
}

fingerprint_diff_or_stop() {
  if [ -z "${FP_BEFORE}" ] || [ ! -f "${FP_BEFORE}" ]; then
    return 0
  fi
  FP_AFTER="$(mktemp "${TMPDIR:-/tmp}/codex-companion-fp-after.XXXXXX")"
  if ! fingerprint_capture "${FP_AFTER}"; then
    echo "ERROR: worktree fingerprint capture (after) failed" >&2
    rm -f "${FP_AFTER}"
    return 1
  fi
  if ! "${HARNESS_BIN}" wt fingerprint diff --before "${FP_BEFORE}" --after "${FP_AFTER}"; then
    echo "WORKTREE-ESCAPE detected: see stderr for path list" >&2
    rm -f "${FP_AFTER}"
    return 1
  fi
  rm -f "${FP_AFTER}"
  return 0
}

run_task_with_fingerprint() {
  FP_BEFORE="$(mktemp "${TMPDIR:-/tmp}/codex-companion-fp-before.XXXXXX")"
  if ! fingerprint_capture "${FP_BEFORE}"; then
    rm -f "${FP_BEFORE}"
    echo "ERROR: worktree fingerprint capture (before) failed" >&2
    exit 1
  fi
  set +e
  "$@"
  local rc=$?
  set -e
  if ! fingerprint_diff_or_stop; then
    rm -f "${FP_BEFORE}"
    exit 1
  fi
  rm -f "${FP_BEFORE}"
  exit "${rc}"
}

is_valid_codex_effort() {
  case "${1:-}" in
    none|minimal|low|medium|high|xhigh|max|ultra) return 0 ;;
    *) return 1 ;;
  esac
}

is_valid_codex_model() {
  case "${1:-}" in
    ''|-*|*[!A-Za-z0-9._:/-]*) return 1 ;;
    *) return 0 ;;
  esac
}

record_codex_override() {
  local kind="$1" value="$2" previous=""
  case "${kind}" in
    model)
      previous="${CODEX_EXPLICIT_MODEL}"
      if ! is_valid_codex_model "${value}"; then
        echo "ERROR: invalid ${SUBCOMMAND} model '${value}'; refusing provider dispatch." >&2
        return 1
      fi
      ;;
    effort)
      previous="${CODEX_EXPLICIT_EFFORT}"
      if ! is_valid_codex_effort "${value}"; then
        echo "ERROR: invalid effort '${value}' for ${SUBCOMMAND}; refusing provider dispatch." >&2
        return 1
      fi
      ;;
  esac
  # Do not let different parsers choose different winners for duplicate flags.
  # This includes repeating the same value and mixing flags with -c overrides.
  if [ -n "${previous}" ]; then
    echo "ERROR: duplicate ${SUBCOMMAND} ${kind} override; refusing provider dispatch." >&2
    return 1
  fi
  if [ "${kind}" = model ]; then CODEX_EXPLICIT_MODEL="${value}";
  else CODEX_EXPLICIT_EFFORT="${value}"; fi
  CODEX_NORMALIZED_ARGS+=("--${kind}" "${value}")
}

normalize_codex_config() {
  local config="$1" key value quote
  if [[ ! "${config}" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_.-]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
    echo "ERROR: unsupported ${SUBCOMMAND} config syntax; refusing provider dispatch." >&2
    return 1
  fi
  key="${BASH_REMATCH[1]}"
  value="${BASH_REMATCH[2]}"
  value="${value%"${value##*[![:space:]]}"}"
  case "${key}" in
    model|model_reasoning_effort|model_verbosity)
      # Model IDs and effort names contain no escapes. Accept a bare value or
      # a matching TOML string; reject malformed strings before any dispatch.
      case "${value}" in
        \"*|\'*)
          quote="${value:0:1}"
          if [ "${#value}" -lt 2 ] || [ "${value: -1}" != "${quote}" ]; then
            echo "ERROR: malformed ${SUBCOMMAND} config '${key}'; refusing provider dispatch." >&2
            return 1
          fi
          value="${value:1:${#value}-2}"
          ;;
      esac
      case "${key}" in
        model) record_codex_override model "${value}" ;;
        model_reasoning_effort) record_codex_override effort "${value}" ;;
        model_verbosity)
          if [ "${SUBCOMMAND}" != task ]; then
            echo "ERROR: unsupported ${SUBCOMMAND} config '${key}'; refusing provider dispatch." >&2
            return 1
          fi
          case "${value}" in
            low|medium|high) ;;
            *) echo "ERROR: invalid model_verbosity; refusing provider dispatch." >&2; return 1 ;;
          esac
          CODEX_HAS_EXTRA_CONFIG=1
          CODEX_NORMALIZED_ARGS+=(-c "model_verbosity=\"${value}\"")
          ;;
      esac
      ;;
    *)
      # This adapter changes model selection, not provider, MCP, approval, or
      # permission configuration. Only the explicit model controls above are
      # supported; unknown keys must not open a new runtime configuration path.
      echo "ERROR: unsupported ${SUBCOMMAND} config '${key}'; refusing provider dispatch." >&2
      return 1
      ;;
  esac
}

record_codex_option_once() {
  case "${CODEX_SEEN_OPTIONS}" in
    *"|$1|"*)
      echo "ERROR: duplicate ${SUBCOMMAND} $1 option; refusing provider dispatch." >&2
      return 1
      ;;
  esac
  CODEX_SEEN_OPTIONS="${CODEX_SEEN_OPTIONS}$1|"
}

normalize_codex_overrides() {
  CODEX_NORMALIZED_ARGS=("$1")
  shift
  local current key value inline option_args saw_add_dir=0
  while [ $# -gt 0 ]; do
    current="$1"
    shift
    if [ "${current}" = -- ]; then
      CODEX_NORMALIZED_ARGS+=(-- "$@")
      break
    fi
    key="${current%%=*}"
    value=""
    inline=0
    option_args=("${current}")
    if [ "${key}" != "${current}" ]; then value="${current#*=}"; inline=1; fi
    case "${current}" in
      -c=*|-C=*|-s=*) ;;
      -c?*) key=-c; value="${current#-c}"; inline=1 ;;
      -C?*) key=-C; value="${current#-C}"; inline=1 ;;
      -s?*) key=-s; value="${current#-s}"; inline=1 ;;
    esac
    case "${key}" in
      -m) key=--model ;;
      --config) key=-c ;;
      --cd|-C) key=--cwd ;;
      -s) key=--sandbox ;;
      -i) key=--image ;;
      -o) key=--output-last-message ;;
      --yolo) key=--dangerously-bypass-approvals-and-sandbox ;;
    esac
    case "${key}" in
      --model|--effort|-c|--cwd|--json|--background|--resume-last|--resume|--fresh) ;;
      --write|--sandbox|--output-schema|--prompt-file|--output-last-message|--image|--add-dir|--color|--ephemeral|--skip-git-repo-check|--full-auto|--dangerously-bypass-approvals-and-sandbox)
        if [ "${SUBCOMMAND}" != task ]; then
          echo "ERROR: unsupported ${SUBCOMMAND} option '${current}'; refusing provider dispatch." >&2
          return 1
        fi
        ;;
      --base|--scope|--wait|--uncommitted)
        if [ "${SUBCOMMAND}" = task ]; then
          echo "ERROR: unsupported task option '${current}'; refusing provider dispatch." >&2
          return 1
        fi
        ;;
      --commit)
        echo "ERROR: review --commit target is unsupported by official companion; refusing provider dispatch." >&2
        return 1
        ;;
      -) CODEX_NORMALIZED_ARGS+=("${current}"); continue ;;
      -*)
        # Runtime passthrough is an explicit list. New profile/provider/rule
        # switches must not become new configuration entry points by accident.
        echo "ERROR: unsupported ${SUBCOMMAND} option '${current}'; refusing provider dispatch." >&2
        return 1
        ;;
      *) CODEX_NORMALIZED_ARGS+=("${current}"); continue ;;
    esac
    case "${key}" in
      --write|--json|--background|--resume-last|--resume|--fresh|--wait|--uncommitted|--ephemeral|--skip-git-repo-check|--full-auto|--dangerously-bypass-approvals-and-sandbox)
        case "${key}" in
          --ephemeral|--skip-git-repo-check|--full-auto|--dangerously-bypass-approvals-and-sandbox)
            if [ "${inline}" -eq 1 ]; then
              echo "ERROR: ${SUBCOMMAND} ${key} does not accept a value; refusing provider dispatch." >&2
              return 1
            fi
            ;;
        esac
        if [ "${inline}" -eq 0 ]; then value=true; fi
        case "${value}" in
          true|false) ;;
          *) echo "ERROR: invalid boolean for ${SUBCOMMAND} ${key}; refusing provider dispatch." >&2; return 1 ;;
        esac
        record_codex_option_once "${key}" || return 1
        [ "${value}" = false ] && continue
        case "${key}" in
          --write) CODEX_TASK_WRITE_INTENT=1 ;;
          --full-auto|--dangerously-bypass-approvals-and-sandbox)
            CODEX_TASK_WRITE_INTENT=1
            CODEX_TASK_EXPLICIT_SANDBOX=1
            ;;
          --background|--resume-last|--resume|--fresh) CODEX_STATE_MODE="${key#--}" ;;
        esac
        # The guard, ledger and both providers see the same boolean spelling.
        CODEX_NORMALIZED_ARGS+=("${key}")
        ;;
      *)
        if [ "${inline}" -eq 0 ]; then
          if [ $# -eq 0 ]; then
            if [ "${key}" = --effort ]; then
              echo "ERROR: ${SUBCOMMAND} --effort requires an effort value; refusing provider dispatch." >&2
            else
              echo "ERROR: ${SUBCOMMAND} ${key} requires a value; refusing provider dispatch." >&2
            fi
            return 1
          fi
          value="$1"
          shift
          option_args+=("${value}")
          if [[ "${value}" == -* ]]; then
            echo "ERROR: ${SUBCOMMAND} ${key} requires a value, not another option; refusing provider dispatch." >&2
            return 1
          fi
        fi
        if [ -z "${value}" ]; then
          echo "ERROR: ${SUBCOMMAND} ${key} requires a value; refusing provider dispatch." >&2
          return 1
        fi
        case "${key}" in
          --model) record_codex_override model "${value}" || return 1; continue ;;
          --effort) record_codex_override effort "${value}" || return 1; continue ;;
          -c) normalize_codex_config "${value}" || return 1; continue ;;
          --image|--add-dir) ;; # These options intentionally accept multiple entries.
          *) record_codex_option_once "${key}" || return 1 ;;
        esac
        case "${key}" in
          --cwd)
            case "${value}" in
              /*) CODEX_TARGET_CWD="${value}" ;;
              *) CODEX_TARGET_CWD="${PWD}/${value}" ;;
            esac
            # Both providers must receive the same target used by the guard.
            # Native companion only accepts separated --cwd/-C values safely.
            option_args=(--cwd "${CODEX_TARGET_CWD}")
            ;;
          --sandbox)
            case "${value}" in
              read-only) ;;
              workspace-write|danger-full-access) CODEX_TASK_WRITE_INTENT=1 ;;
              *) echo "ERROR: invalid task sandbox '${value}'; refusing provider dispatch." >&2; return 1 ;;
            esac
            CODEX_TASK_EXPLICIT_SANDBOX=1
            ;;
          --prompt-file) CODEX_TASK_PROMPT_FILE="${value}"; continue ;;
          --output-schema) CODEX_HAS_OUTPUT_SCHEMA=1 ;;
          --add-dir) saw_add_dir=1 ;;
          --base|--scope) option_args=("${key}" "${value}") ;;
        esac
        CODEX_NORMALIZED_ARGS+=("${option_args[@]}")
        ;;
    esac
  done
  # The primary-environment guard validates one cwd, not additional writable
  # roots. Preserve --add-dir only when it cannot extend write permissions.
  if [ "${saw_add_dir}" -eq 1 ] && [ "${CODEX_TASK_WRITE_INTENT}" -eq 1 ]; then
    echo "ERROR: task --add-dir is supported only without write intent; refusing provider dispatch." >&2
    return 1
  fi
  if [ -n "${CODEX_TASK_PROMPT_FILE}" ]; then
    case "${CODEX_TASK_PROMPT_FILE}" in
      /*) ;;
      *) CODEX_TASK_PROMPT_FILE="${CODEX_TARGET_CWD}/${CODEX_TASK_PROMPT_FILE}" ;;
    esac
    CODEX_NORMALIZED_ARGS=("${CODEX_NORMALIZED_ARGS[0]}" --prompt-file "${CODEX_TASK_PROMPT_FILE}" "${CODEX_NORMALIZED_ARGS[@]:1}")
  fi
}

resolve_codex_route_for_task() {
  if [ "${HARNESS_DISABLE_MODEL_ROUTING:-0}" = "1" ]; then
    return 0
  fi
  if [ ! -x "${MODEL_ROUTER}" ]; then
    echo "ERROR: Codex model router is unavailable; refusing provider dispatch." >&2
    return 1
  fi
  if [ "${CODEX_ROUTE_RESOLVED}" -eq 1 ]; then
    return 0
  fi

  local tier
  local routed_output
  tier="${CODEX_MODEL_TIER:-${HARNESS_MODEL_TIER:-standard}}"
  if ! routed_output="$(bash "${MODEL_ROUTER}" --host codex --tier "${tier}" --field model 2>&1)"; then
    echo "ERROR: Codex model routing failed for tier '${tier}'." >&2
    printf '%s\n' "${routed_output}" >&2
    return 1
  fi
  CODEX_ROUTED_MODEL="${routed_output}"

  if ! routed_output="$(bash "${MODEL_ROUTER}" --host codex --tier "${tier}" --field effort 2>&1)"; then
    echo "ERROR: Codex effort routing failed for tier '${tier}'." >&2
    printf '%s\n' "${routed_output}" >&2
    return 1
  fi
  CODEX_ROUTED_EFFORT="${routed_output}"
  CODEX_ROUTE_RESOLVED=1
}

resolve_codex_route_for_review() {
  if [ "${HARNESS_DISABLE_MODEL_ROUTING:-0}" = "1" ] || [ ! -x "${MODEL_ROUTER}" ]; then
    return 1
  fi
  if [ "${CODEX_REVIEW_ROUTE_RESOLVED}" -eq 1 ]; then
    return 0
  fi

  local routed_output
  if ! routed_output="$(bash "${MODEL_ROUTER}" --host codex --role reviewer --field model 2>&1)"; then
    echo "ERROR: Codex reviewer model routing failed." >&2
    printf '%s\n' "${routed_output}" >&2
    return 2
  fi
  CODEX_REVIEW_ROUTED_MODEL="${routed_output}"

  if ! routed_output="$(bash "${MODEL_ROUTER}" --host codex --role reviewer --field effort 2>&1)"; then
    echo "ERROR: Codex reviewer effort routing failed." >&2
    printf '%s\n' "${routed_output}" >&2
    return 2
  fi
  CODEX_REVIEW_ROUTED_EFFORT="${routed_output}"
  CODEX_REVIEW_ROUTE_RESOLVED=1
  return 0
}

extract_target_cwd() {
  printf '%s\n' "${CODEX_TARGET_CWD}"
}

task_has_write_intent() {
  # Normalization consumes option values and stops at -- exactly once. Do not
  # reinterpret prompt text or choose a different duplicate-option winner.
  [ "${1:-}" = task ] && [ "${CODEX_TASK_WRITE_INTENT}" -eq 1 ]
}

guard_primary_environment_if_needed() {
  if [ ! -x "${PRIMARY_ENV_GUARD}" ]; then
    return 0
  fi
  if task_has_write_intent "$@"; then
    local target_cwd
    target_cwd="$(extract_target_cwd "$@")"
    HARNESS_CODEX_EXECUTION_ROOT="${EXECUTION_ROOT}" \
      bash "${PRIMARY_ENV_GUARD}" --mode write --target-cwd "${target_cwd}"
  fi
}

should_use_structured_task_exec() {
  [ "${1:-}" = "task" ] || return 1
  [ "${CODEX_HAS_OUTPUT_SCHEMA}" -eq 1 ] && return 0
  [ "${CODEX_HAS_EXTRA_CONFIG}" -eq 1 ] && return 0
  # Only the task options understood by official companion 1.0.6 may use its
  # transport. Unknown CLI options there become prompt text; notably --write
  # plus --sandbox read-only would otherwise execute with workspace-write.
  # Pass runtime options to Codex itself regardless of reasoning effort.
  shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --) break ;;
      --model|--effort|--cwd|-C|--prompt-file) shift 2 ;;
      --model=*|--effort=*|--cwd=*|--prompt-file=*|--write|--json|--resume-last|--resume|--fresh|--background|--write=*|--json=*|--resume-last=*|--resume=*|--fresh=*|--background=*) shift ;;
      -) shift ;;
      -*) return 0 ;;
      *) shift ;;
    esac
  done
  # Official companion 1.0.6 accepts <=xhigh. Only Codex runtime transports
  # can preserve max/ultra; never substitute a lower effort for these values.
  case "${CODEX_TASK_EFFORT}" in max|ultra) return 0 ;; esac
  return 1
}

resolve_task_effort() {
  if [ -n "${CODEX_EXPLICIT_EFFORT}" ]; then
    CODEX_TASK_EFFORT="${CODEX_EXPLICIT_EFFORT}"
  elif [ -n "${CODEX_EFFORT:-}" ]; then
    CODEX_TASK_EFFORT="${CODEX_EFFORT}"
  elif [ "${HARNESS_DISABLE_MODEL_ROUTING:-0}" != 1 ]; then
    CODEX_TASK_EFFORT="${CODEX_ROUTED_EFFORT}"
  elif [ -z "${CODEX_STATE_MODE}" ]; then
    # Legacy prompt inference is opt-in via disabled routing. It must never
    # override a caller's explicit env/argv or a role's resolved effort.
    local description="" current expect_value=0 after_separator=0
    shift
    for current in "$@"; do
      if [ "${after_separator}" -eq 1 ]; then description="${current}"; continue; fi
      if [ "${expect_value}" -eq 1 ]; then expect_value=0; continue; fi
      case "${current}" in
        --) after_separator=1 ;;
        --write|--json|--full-auto|--ephemeral|--oss|--skip-git-repo-check|--dangerously-bypass-approvals-and-sandbox) ;;
        -*=*) ;;
        -*) expect_value=1 ;;
        *) description="${current}" ;;
      esac
    done
    CODEX_TASK_EFFORT=medium
    if [ -f "${SCRIPT_DIR}/calculate-effort.sh" ]; then
      if [ -n "${description}" ]; then
        CODEX_TASK_EFFORT="$(bash "${SCRIPT_DIR}/calculate-effort.sh" "${description}" 2>/dev/null || true)"
      elif [ ! -t 0 ]; then
        TASK_STDIN_CONTENT="$(cat)"
        TASK_STDIN_CAPTURED=1
        if [ -n "${TASK_STDIN_CONTENT}" ]; then
          CODEX_TASK_EFFORT="$(bash "${SCRIPT_DIR}/calculate-effort.sh" <<<"${TASK_STDIN_CONTENT}" 2>/dev/null || true)"
        fi
      fi
    fi
    if ! is_valid_codex_effort "${CODEX_TASK_EFFORT}"; then CODEX_TASK_EFFORT=medium; fi
  fi
  if [ -n "${CODEX_TASK_EFFORT}" ] && ! is_valid_codex_effort "${CODEX_TASK_EFFORT}"; then
    echo "ERROR: invalid task effort '${CODEX_TASK_EFFORT}'; refusing provider dispatch." >&2
    return 1
  fi
}

validate_task_prompt_file() {
  local prompt_file="${CODEX_TASK_PROMPT_FILE}"
  [ -n "${prompt_file}" ] || return 0
  if [ ! -f "${prompt_file}" ] || [ ! -r "${prompt_file}" ]; then
    echo "ERROR: task --prompt-file cannot read '${prompt_file}'; refusing provider dispatch." >&2
    return 1
  fi
}

reject_unrepresentable_task_mode() {
  [ "${1:-}" = "task" ] || return 0
  [ -n "${CODEX_STATE_MODE}" ] || return 0
  case "${CODEX_TASK_EFFORT}" in
    max|ultra)
      echo "ERROR: task --${CODEX_STATE_MODE} cannot preserve ${CODEX_TASK_EFFORT} effort; refusing provider dispatch." >&2
      return 1
      ;;
  esac
  if should_use_structured_task_exec "$@"; then
    echo "ERROR: task --${CODEX_STATE_MODE} cannot preserve structured/config execution; refusing provider dispatch." >&2
    return 1
  fi
}

run_structured_task_exec() {
  local passthrough=()
  local saw_write=0
  local saw_sandbox=0
  local prompt_file=""
  local current=""
  local explicit_sandbox="${CODEX_TASK_EXPLICIT_SANDBOX}"

  # Codex 0.123.0+ inherits root-level shared flags for `codex exec`.
  # These exec-local sandbox defaults are kept only to encode Harness task intent:
  # `task --write` means workspace-write, and read-only remains the safe default.
  # If the caller provides --sandbox/-s/--full-auto/bypass explicitly, preserve it.
  # `--full-auto` is deprecated in current Codex guidance, so Harness must not
  # add it by default here; explicit caller intent is passed through unchanged.
  shift || true # drop "task"
  while [ $# -gt 0 ]; do
    current="$1"
    case "$current" in
      --)
        passthrough+=("$@")
        break
        ;;
      --background|--resume-last|--resume|--fresh|--background=*|--resume-last=*|--resume=*|--fresh=*)
        echo "ERROR: structured task mode does not support ${current}; refusing provider dispatch." >&2
        exit 2
        ;;
      --prompt-file)
        if [ -z "${2:-}" ]; then
          echo "ERROR: task --prompt-file requires a readable file path; refusing provider dispatch." >&2
          exit 2
        fi
        prompt_file="${2}"
        shift 2
        ;;
      --prompt-file=*)
        prompt_file="${current#*=}"
        shift
        ;;
      --write)
        saw_write=1
        if [ "${explicit_sandbox}" -eq 0 ]; then
          passthrough+=(--sandbox workspace-write)
        fi
        shift
        ;;
      --sandbox|-s|--sandbox=*|-s?*|--full-auto|--dangerously-bypass-approvals-and-sandbox)
        saw_sandbox=1
        passthrough+=("${current}")
        shift
        if [ "${current}" = "--sandbox" ] || [ "${current}" = "-s" ]; then
          passthrough+=("${1:-}")
          shift || true
        fi
        ;;
      --effort)
        # codex exec does not accept the companion-only --effort flag.
        # Structured task mode goes through codex exec directly, so translate
        # it into the official config override instead of silently dropping it.
        if is_valid_codex_effort "${2:-}"; then
          passthrough+=(-c "model_reasoning_effort=\"${2}\"")
        fi
        shift
        shift || true
        ;;
      --effort=*)
        local effort_value="${current#*=}"
        if is_valid_codex_effort "${effort_value}"; then
          passthrough+=(-c "model_reasoning_effort=\"${effort_value}\"")
        fi
        shift
        ;;
      --cwd)
        passthrough+=(--cd "${2:-}")
        shift 2
        ;;
      --cwd=*)
        passthrough+=(--cd "${current#*=}")
        shift
        ;;
      *)
        passthrough+=("${current}")
        shift
        if [ "${current}" = "--model" ] || [ "${current}" = "-m" ] || \
           [ "${current}" = "--output-schema" ] || \
           [ "${current}" = "-o" ] || [ "${current}" = "--output-last-message" ] || \
           [ "${current}" = "-c" ] || [ "${current}" = "--config" ] || \
           [ "${current}" = "-C" ] || [ "${current}" = "--cd" ] || \
           [ "${current}" = "--add-dir" ] || [ "${current}" = "-i" ] || \
           [ "${current}" = "--image" ] || [ "${current}" = "--color" ]; then
          passthrough+=("${1:-}")
          shift || true
        fi
        ;;
    esac
  done

  if [ "${saw_write}" -eq 0 ] && [ "${saw_sandbox}" -eq 0 ]; then
    passthrough=(--sandbox read-only "${passthrough[@]+"${passthrough[@]}"}")
  fi

  if [ -n "${prompt_file}" ]; then
    run_task_with_fingerprint codex exec "${passthrough[@]}" - < "${prompt_file}"
  else
    run_task_with_fingerprint codex exec "${passthrough[@]}"
  fi
}

normalize_review_args() {
  REVIEW_COMPANION_ARGS=()
  REVIEW_EXPLICIT_MODEL=0
  REVIEW_EXPLICIT_MODEL_VALUE=""
  REVIEW_EXPLICIT_EFFORT=""

  local expect=""
  local current=""
  while [ "$#" -gt 0 ]; do
    current="$1"
    shift

    if [ -n "${expect}" ]; then
      case "${expect}" in
        effort)
          if ! is_valid_codex_effort "${current}"; then
            echo "ERROR: invalid review effort '${current}'; refusing provider dispatch." >&2
            return 1
          fi
          REVIEW_EXPLICIT_EFFORT="${current}"
          ;;
        model)
          if ! is_valid_codex_model "${current}"; then
            echo "ERROR: invalid review model '${current}'; refusing provider dispatch." >&2
            return 1
          fi
          REVIEW_EXPLICIT_MODEL_VALUE="${current}"
          REVIEW_COMPANION_ARGS+=("${current}")
          ;;
        passthrough)
          REVIEW_COMPANION_ARGS+=("${current}")
          ;;
      esac
      expect=""
      continue
    fi

    case "${current}" in
      --)
        REVIEW_COMPANION_ARGS+=(-- "$@")
        break
        ;;
      --effort)
        expect="effort"
        ;;
      --effort=*)
        REVIEW_EXPLICIT_EFFORT="${current#*=}"
        if ! is_valid_codex_effort "${REVIEW_EXPLICIT_EFFORT}"; then
          echo "ERROR: invalid review effort '${REVIEW_EXPLICIT_EFFORT}'; refusing provider dispatch." >&2
          return 1
        fi
        ;;
      --model|-m)
        REVIEW_EXPLICIT_MODEL=1
        REVIEW_COMPANION_ARGS+=("${current}")
        expect="model"
        ;;
      --model=*|-m=*)
        REVIEW_EXPLICIT_MODEL=1
        REVIEW_EXPLICIT_MODEL_VALUE="${current#*=}"
        if ! is_valid_codex_model "${REVIEW_EXPLICIT_MODEL_VALUE}"; then
          echo "ERROR: invalid review model '${REVIEW_EXPLICIT_MODEL_VALUE}'; refusing provider dispatch." >&2
          return 1
        fi
        if [[ "${current}" == -m=* ]]; then
          REVIEW_COMPANION_ARGS+=(--model "${current#*=}")
        else
          REVIEW_COMPANION_ARGS+=("${current}")
        fi
        ;;
      --commit)
        echo "ERROR: review --commit target is unsupported by official companion; refusing provider dispatch." >&2
        return 1
        ;;
      --commit=*)
        echo "ERROR: review --commit target is unsupported by official companion; refusing provider dispatch." >&2
        return 1
        ;;
      --uncommitted)
        REVIEW_COMPANION_ARGS+=(--scope working-tree)
        ;;
      --base|--scope|--cwd|--cd|-C)
        REVIEW_COMPANION_ARGS+=("${current}")
        expect="passthrough"
        ;;
      --base=*|--scope=*|--cwd=*|--cd=*|-C=*)
        REVIEW_COMPANION_ARGS+=("${current}")
        ;;
      *)
        REVIEW_COMPANION_ARGS+=("${current}")
        ;;
    esac
  done

  if [ -n "${expect}" ]; then
    case "${expect}" in
      effort) echo "ERROR: review --effort requires an effort value; refusing provider dispatch." >&2 ;;
      commit) echo "ERROR: review --commit target is unsupported by official companion; refusing provider dispatch." >&2 ;;
      model) echo "ERROR: review --model requires a model value; refusing provider dispatch." >&2 ;;
      passthrough) echo "ERROR: review option requires a value; refusing provider dispatch." >&2 ;;
    esac
    return 1
  fi

  if [ "${REVIEW_EXPLICIT_MODEL}" -eq 0 ] && [ -n "${CODEX_REVIEW_ROUTED_MODEL}" ]; then
    REVIEW_COMPANION_ARGS=("${REVIEW_COMPANION_ARGS[0]}" --model "${CODEX_REVIEW_ROUTED_MODEL}" "${REVIEW_COMPANION_ARGS[@]:1}")
  fi
}

stop_review_app_server() {
  local pid="${REVIEW_APP_SERVER_PID:-}"
  local attempts=0
  local proxy_wait_status=0
  local proxy_status=""
  local wait_status=0
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    kill -TERM "${pid}" 2>/dev/null || true
    # The proxy gives its app-server child up to 1s for TERM, then up to 1s
    # for KILL. Wait for its status marker instead of polling kill -0, which
    # remains true for an unreaped zombie on some hosts.
    while [ "${attempts}" -lt 60 ]; do
      if [ -s "${REVIEW_APP_SERVER_STATUS_FILE:-}" ]; then
        proxy_status="$(tr -d '[:space:]' <"${REVIEW_APP_SERVER_STATUS_FILE}")"
        break
      fi
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      attempts=$((attempts + 1))
      sleep 0.05
    done
    if [ -z "${proxy_status}" ] && kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  fi
  if [ -n "${pid}" ]; then
    wait "${pid}" 2>/dev/null || wait_status=$?
    if [ -z "${proxy_status}" ] && [ -s "${REVIEW_APP_SERVER_STATUS_FILE:-}" ]; then
      proxy_status="$(tr -d '[:space:]' <"${REVIEW_APP_SERVER_STATUS_FILE}")"
    fi
    if [ -n "${proxy_status}" ]; then
      case "${proxy_status}" in
        0|[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) proxy_wait_status="${proxy_status}" ;;
        *) proxy_wait_status=1 ;;
      esac
    elif [ "${wait_status}" -ne 0 ]; then
      proxy_wait_status="${wait_status}"
    elif [ -n "${REVIEW_APP_SERVER_STATUS_FILE:-}" ]; then
      proxy_wait_status=1
    fi
    if [ "${proxy_wait_status}" -ne 0 ]; then
      echo "ERROR: reviewer app-server proxy exited with status ${proxy_wait_status}." >&2
    fi
  fi
  if [ -n "${REVIEW_APP_SERVER_SOCKET:-}" ]; then
    rm -f -- "${REVIEW_APP_SERVER_SOCKET}"
  fi
  if [ -n "${REVIEW_APP_SERVER_READY_FILE:-}" ]; then
    rm -f -- "${REVIEW_APP_SERVER_READY_FILE}"
  fi
  if [ -n "${REVIEW_APP_SERVER_STATUS_FILE:-}" ]; then
    rm -f -- "${REVIEW_APP_SERVER_STATUS_FILE}"
  fi
  if [ -n "${REVIEW_APP_SERVER_DIR:-}" ]; then
    rm -f -- "${REVIEW_APP_SERVER_DIR}/app-server.log"
  fi
  if [ -n "${REVIEW_APP_SERVER_DIR:-}" ]; then
    rmdir "${REVIEW_APP_SERVER_DIR}" 2>/dev/null || true
  fi
  REVIEW_APP_SERVER_PID=""
  REVIEW_APP_SERVER_SOCKET=""
  REVIEW_APP_SERVER_ENDPOINT=""
  REVIEW_APP_SERVER_READY_FILE=""
  REVIEW_APP_SERVER_STATUS_FILE=""
  REVIEW_APP_SERVER_DIR=""
  return "${proxy_wait_status}"
}

start_review_app_server() {
  local codex_bin
  local app_server_log
  local config_model config_review_model config_effort effective_model
  local proxy_script
  local config_args=()
  local i

  codex_bin="$(command -v codex 2>/dev/null || true)"
  if [ -z "${codex_bin}" ]; then
    echo "ERROR: Codex CLI is required for the reviewer app-server." >&2
    return 1
  fi

  REVIEW_APP_SERVER_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-review-app-server.XXXXXX")"
  case "${OSTYPE:-}" in
    msys*|cygwin*|win32*)
      REVIEW_APP_SERVER_SOCKET=""
      REVIEW_APP_SERVER_ENDPOINT="pipe:\\\\.\\pipe\\codex-review-${PPID}-${RANDOM}"
      ;;
    *)
      REVIEW_APP_SERVER_SOCKET="${REVIEW_APP_SERVER_DIR}/review.sock"
      REVIEW_APP_SERVER_ENDPOINT="unix:${REVIEW_APP_SERVER_SOCKET}"
      ;;
  esac
  REVIEW_APP_SERVER_READY_FILE="${REVIEW_APP_SERVER_DIR}/ready"
  REVIEW_APP_SERVER_STATUS_FILE="${REVIEW_APP_SERVER_DIR}/status"
  app_server_log="${REVIEW_APP_SERVER_DIR}/app-server.log"
  proxy_script="${SCRIPT_DIR}/codex-review-app-server-proxy.mjs"
  if [ ! -f "${proxy_script}" ]; then
    echo "ERROR: reviewer app-server proxy is missing at ${proxy_script}." >&2
    stop_review_app_server || true
    return 1
  fi
  effective_model="${CODEX_REVIEW_ROUTED_MODEL}"
  if [ "${REVIEW_EXPLICIT_MODEL}" -eq 1 ]; then
    effective_model="${REVIEW_EXPLICIT_MODEL_VALUE}"
  fi
  if [ -n "${effective_model}" ]; then
    config_model="model=\"${effective_model}\""
    config_review_model="review_model=\"${effective_model}\""
    config_args+=(--config "${config_model}" --config "${config_review_model}")
  fi

  config_effort=""
  if [ -n "${REVIEW_EXPLICIT_EFFORT}" ]; then
    config_effort="model_reasoning_effort=\"${REVIEW_EXPLICIT_EFFORT}\""
  elif [ -n "${CODEX_REVIEW_ROUTED_EFFORT}" ]; then
    config_effort="model_reasoning_effort=\"${CODEX_REVIEW_ROUTED_EFFORT}\""
  fi

  if [ -n "${config_effort}" ]; then
    config_args+=(--config "${config_effort}")
  fi
  node "${proxy_script}" --endpoint "${REVIEW_APP_SERVER_ENDPOINT}" \
    --ready-file "${REVIEW_APP_SERVER_READY_FILE}" --codex "${codex_bin}" \
    --status-file "${REVIEW_APP_SERVER_STATUS_FILE}" \
    "${config_args[@]+"${config_args[@]}"}" >"${app_server_log}" 2>&1 &
  REVIEW_APP_SERVER_PID=$!

  # Codex app-server startup is bounded but can exceed two seconds on a loaded
  # host. Keep a finite ten-second readiness contract so startup signals are
  # handled by the scoped trap instead of being misreported as a race.
  for i in $(seq 1 200); do
    if [ -e "${REVIEW_APP_SERVER_READY_FILE}" ]; then
      return 0
    fi
    if ! kill -0 "${REVIEW_APP_SERVER_PID}" 2>/dev/null; then
      echo "ERROR: reviewer app-server exited before its endpoint became ready." >&2
      sed -n '1,80p' "${app_server_log}" >&2 || true
      stop_review_app_server || true
      return 1
    fi
    sleep 0.05
  done

  echo "ERROR: reviewer app-server endpoint did not become ready." >&2
  stop_review_app_server || true
  return 1
}

run_review_with_app_server() {
  # The scoped endpoint is torn down when this invocation exits. A queued or
  # resumed review cannot outlive it while retaining its model/effort config.
  if [ -n "${CODEX_STATE_MODE}" ]; then
    echo "ERROR: ${SUBCOMMAND} --${CODEX_STATE_MODE} cannot preserve the scoped reviewer transport; refusing provider dispatch." >&2
    return 2
  fi
  if ! normalize_review_args "$@"; then
    return 2
  fi
  local rc cleanup_rc=0 app_server_failed=0
  local app_server_status=""
  local previous_exit_trap previous_int_trap previous_term_trap
  previous_exit_trap="$(trap -p EXIT || true)"
  previous_int_trap="$(trap -p INT || true)"
  previous_term_trap="$(trap -p TERM || true)"
  trap 'review_forward_signal TERM 143' TERM
  trap 'review_forward_signal INT 130' INT
  trap review_app_server_exit_cleanup EXIT

  # Install the scoped cleanup handlers before proxy startup. A TERM/INT
  # arriving while the endpoint is becoming ready must still terminate the
  # proxy and its app-server child; the empty companion PID is intentional.
  if ! start_review_app_server; then
    stop_review_app_server || true
    if [ -n "${previous_exit_trap}" ]; then eval "${previous_exit_trap}"; else trap - EXIT; fi
    if [ -n "${previous_int_trap}" ]; then eval "${previous_int_trap}"; else trap - INT; fi
    if [ -n "${previous_term_trap}" ]; then eval "${previous_term_trap}"; else trap - TERM; fi
    return 2
  fi

  set +e
  CODEX_COMPANION_APP_SERVER_ENDPOINT="${REVIEW_APP_SERVER_ENDPOINT}" \
    node "${COMPANION}" "${REVIEW_COMPANION_ARGS[@]}" &
  REVIEW_COMPANION_PID=$!
  wait "${REVIEW_COMPANION_PID}"
  rc=$?
  REVIEW_COMPANION_PID=""
  set -e
  if [ -s "${REVIEW_APP_SERVER_STATUS_FILE}" ]; then
    app_server_status="$(tr -d '[:space:]' <"${REVIEW_APP_SERVER_STATUS_FILE}")"
    case "${app_server_status}" in
      0) app_server_failed=0 ;;
      *) app_server_failed=1 ;;
    esac
  fi
  if ! stop_review_app_server; then
    cleanup_rc=1
  fi
  # Emit only after proxy shutdown has reported a clean transport. A crash can
  # occur just after the companion returns, so emitting before stop would
  # count failed app-server work as a real delegation.
  if [ "${cleanup_rc}" -eq 0 ] && [ "${app_server_failed}" -eq 0 ] && [ "${rc}" -eq 0 ]; then
    emit_codex_ledger_once "${SUBCOMMAND}" "$@"
  fi
  if [ -n "${previous_exit_trap}" ]; then eval "${previous_exit_trap}"; else trap - EXIT; fi
  if [ -n "${previous_int_trap}" ]; then eval "${previous_int_trap}"; else trap - INT; fi
  if [ -n "${previous_term_trap}" ]; then eval "${previous_term_trap}"; else trap - TERM; fi
  if [ "${cleanup_rc}" -ne 0 ]; then return 1; fi
  if [ "${app_server_failed}" -ne 0 ]; then return 1; fi
  return "${rc}"
}

review_forward_signal() {
  local signal="$1"
  local exit_code="$2"
  local pid="${REVIEW_COMPANION_PID:-}"
  local app_server_pid="${REVIEW_APP_SERVER_PID:-}"
  local attempts=0
  # Stop the proxy at the same time as the official companion. This keeps
  # signal handling bounded by the two independent TERM -> KILL grace windows
  # instead of serializing companion shutdown before proxy cleanup.
  if [ -n "${app_server_pid}" ] && kill -0 "${app_server_pid}" 2>/dev/null; then
    kill -"${signal}" "${app_server_pid}" 2>/dev/null || true
  fi
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    kill -"${signal}" "${pid}" 2>/dev/null || true
    while kill -0 "${pid}" 2>/dev/null && [ "${attempts}" -lt 20 ]; do
      attempts=$((attempts + 1))
      sleep 0.05
    done
    if kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
    fi
    wait "${pid}" 2>/dev/null || true
  fi
  REVIEW_COMPANION_PID=""
  exit "${exit_code}"
}

emit_codex_ledger_once() {
  [ "${CODEX_LEDGER_EMITTED}" -eq 0 ] || return 0
  [ -n "${1:-}" ] || return 0
  local subcommand="$1"
  shift
  local write_flag=0
  if task_has_write_intent "$@"; then write_flag=1; fi
  orch_emit_ledger "codex" "${subcommand}" "${write_flag}" "" "" || true
  CODEX_LEDGER_EMITTED=1
}

review_app_server_exit_cleanup() {
  stop_review_app_server || true
}

SUBCOMMAND="${1:-}"
if [ "${SUBCOMMAND}" = task ] || [ "${SUBCOMMAND}" = review ] || [ "${SUBCOMMAND}" = adversarial-review ]; then
  if ! normalize_codex_overrides "$@"; then exit 2; fi
  set -- "${CODEX_NORMALIZED_ARGS[@]}"
fi
if [ "${SUBCOMMAND}" = "task" ] && ! resolve_codex_route_for_task; then
  exit 2
fi
if [ "${SUBCOMMAND}" = "task" ] && ! validate_task_prompt_file "$@"; then
  exit 2
fi
if [ "${SUBCOMMAND}" = task ] && ! resolve_task_effort "$@"; then
  exit 2
fi
if [ "${SUBCOMMAND}" = "task" ] && ! reject_unrepresentable_task_mode "$@"; then
  exit 2
fi
if should_use_structured_task_exec "$@"; then
  STRUCTURED_TASK_EXEC=1
else
  STRUCTURED_TASK_EXEC=0
fi
if [ "${SUBCOMMAND}" = task ]; then
  # Prepend defaults so they remain options even when the prompt follows --.
  if [ -z "${CODEX_EXPLICIT_MODEL}" ] && [ -n "${CODEX_ROUTED_MODEL}" ]; then
    set -- "$1" --model "${CODEX_ROUTED_MODEL}" "${@:2}"
  fi
  if [ -z "${CODEX_EXPLICIT_EFFORT}" ] && [ -n "${CODEX_TASK_EFFORT}" ]; then
    set -- "$1" --effort "${CODEX_TASK_EFFORT}" "${@:2}"
  fi
fi

# 公式プラグインの companion を検索
# Claude/Codex どちらの plugin ディレクトリでも見つかるようにし、
# cache と marketplace 配下の両方を対象にする。
PLUGIN_DIRS=()
[ -d "${HOME}/.claude/plugins" ] && PLUGIN_DIRS+=("${HOME}/.claude/plugins")
[ -d "${HOME}/.codex/plugins" ] && PLUGIN_DIRS+=("${HOME}/.codex/plugins")

COMPANION=""
if [ "${#PLUGIN_DIRS[@]}" -gt 0 ]; then
  # パスからバージョンセグメントを抽出し数値比較（macOS BSD sort 互換）
  COMPANION=$(find "${PLUGIN_DIRS[@]}" -name "codex-companion.mjs" \
    \( -path "*/openai-codex/*" -o -path "*/codex-plugin-cc/*" -o -path "*/plugins/codex/*" \) \
    2>/dev/null \
    | awk -F/ '{version="0.0.0"; for(i=1;i<=NF;i++){if($i~/^[0-9]+\.[0-9]+(\.[0-9]+)?$/){version=$i}} print version,$0}' \
    | sort -t. -k1,1n -k2,2n -k3,3n \
    | tail -1 \
    | cut -d' ' -f2-)
fi

if [ -z "$COMPANION" ] && [ "${STRUCTURED_TASK_EXEC}" -ne 1 ]; then
  echo "ERROR: codex-plugin-cc が見つかりません。" >&2
  echo "インストール: plugin marketplace add openai/codex-plugin-cc" >&2
  echo "または: /codex:setup を実行してください" >&2
  exit 1
fi

REVIEW_APP_SERVER_ENABLED=0
if [ "$SUBCOMMAND" = "review" ] || [ "$SUBCOMMAND" = "adversarial-review" ]; then
  if resolve_codex_route_for_review; then
    REVIEW_APP_SERVER_ENABLED=1
  else
    review_route_rc=$?
    if [ "${review_route_rc}" -ne 1 ]; then
      exit 2
    fi
  fi
  # Explicit review overrides still need the scoped runtime transport when
  # routing is disabled; the official reviewer has no effort/config option.
  if [ -n "${CODEX_EXPLICIT_MODEL}" ] || [ -n "${CODEX_EXPLICIT_EFFORT}" ]; then
    REVIEW_APP_SERVER_ENABLED=1
  fi
fi
if [ "${REVIEW_APP_SERVER_ENABLED}" -eq 1 ]; then
  run_review_with_app_server "$@"
  exit $?
fi

# A rejected write is not a delegation. Run the primary-environment guard
# before recording the task in the orchestration ledger.
guard_primary_environment_if_needed "$@"

# Compatibility paths emit only after all preflight validation has completed.
# Routed reviews emit from run_review_with_app_server after their app-server is
# ready, so rejected or failed transports do not inflate delegation counts.
emit_codex_ledger_once "${SUBCOMMAND}" "$@"

# Model and effort were resolved and validated before guards or ledger writes.
if [ "${SUBCOMMAND}" = task ]; then
  if [ "${STRUCTURED_TASK_EXEC}" -eq 1 ]; then
    if [ "${TASK_STDIN_CAPTURED}" -eq 1 ]; then
      run_structured_task_exec "$@" <<<"${TASK_STDIN_CONTENT}"
    else
      run_structured_task_exec "$@"
    fi
  elif [ "${TASK_STDIN_CAPTURED}" -eq 1 ]; then
    run_task_with_fingerprint node "$COMPANION" "$@" <<<"${TASK_STDIN_CONTENT}"
  else
    run_task_with_fingerprint node "$COMPANION" "$@"
  fi
fi

exec node "$COMPANION" "$@"
