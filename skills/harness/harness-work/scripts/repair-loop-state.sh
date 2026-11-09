#!/usr/bin/env bash
# repair-loop-state.sh
# review→fix→re-review ループの状態を .claude/state/repair-loop/<task>.json に外部化する。
# 反復回数と各回の verdict は会話記憶ではなくこのファイルに保持し、
# MAX_REVIEWS の上限判定を `check` の終了コードで機械判定する (Task 133.4)。
#
# Usage:
#   repair-loop-state.sh init   <project-root> <task-id> <max-iterations>
#   repair-loop-state.sh record <project-root> <task-id> <APPROVE|REQUEST_CHANGES> [findings-json]
#   repair-loop-state.sh check  <project-root> <task-id>

set -euo pipefail

SCHEMA_VERSION="repair-loop.v1"
TASK_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9_.-]*$'

usage() {
  cat <<'EOF'
Usage:
  repair-loop-state.sh init   <project-root> <task-id> <max-iterations>
  repair-loop-state.sh record <project-root> <task-id> <APPROVE|REQUEST_CHANGES> [findings-json]
  repair-loop-state.sh check  <project-root> <task-id>

findings-json: a JSON array of {severity, issue[, file]} objects.
Defaults to "[]" when omitted. Pass "-" to read the JSON array from stdin.

check exit codes (呼び出し側はこの 3 値を区別すること):
  0  status is "open" (below max_iterations) or "approved"  -> ループ継続 / 完了
  1  status is "escalated"                                  -> 上限到達。人間へ escalate
  2  jq unavailable                                         -> 判定不能 (環境不備)
  4  cannot evaluate (bad root / bad task id / no state file / corrupt status)
                                                            -> 判定不能 (呼び出し誤り)
1 と 4 を分けているのは、「上限に達した」という業務上の結論と「そもそも判定できな
かった」を同じ終了コードにすると、init 忘れやパス誤りが「レビュー上限到達」として
利用者に誤報されるため (Phase D レビュー指摘)。
EOF
}

# 判定不能系の終了コード。cmd_check だけが 4 に切り替える (上記 usage 参照)。
USAGE_EXIT=1

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "repair-loop-state.sh: jq is required" >&2
    exit 2
  fi
}

validate_task_id() {
  local task="$1"
  if [[ ! "${task}" =~ ${TASK_ID_PATTERN} ]]; then
    echo "repair-loop-state.sh: invalid task id (must match ${TASK_ID_PATTERN}): ${task}" >&2
    exit "${USAGE_EXIT}"
  fi
}

# ---- 排他制御 -------------------------------------------------------------
# record は read → compute → write の read-modify-write であり、atomic_write
# だけでは同時実行を直列化できない (並行 10 プロセスで 9 件の iteration が
# 失われることを Phase D レビューが実測)。repo 既存の session-state.sh /
# auto-checkpoint.sh と同じ flock + mkdir フォールバックを使う
# (macOS には flock が無いため、フォールバック側が主経路になる)。
LOCK_FD=200
LOCK_PATH=""
LOCK_HELD=0

acquire_lock() {
  local target="$1"
  local timeout="${2:-10}"
  local waited=0
  LOCK_PATH="${target}.lock"
  if command -v flock >/dev/null 2>&1; then
    eval "exec ${LOCK_FD}>\"${LOCK_PATH}\""
    if flock -w "${timeout}" "${LOCK_FD}"; then
      LOCK_HELD=1
      return 0
    fi
    return 1
  fi
  while ! mkdir "${LOCK_PATH}.dir" 2>/dev/null; do
    sleep 0.1
    waited=$((waited + 1))
    if [ "${waited}" -ge $((timeout * 10)) ]; then
      return 1
    fi
  done
  LOCK_HELD=1
  return 0
}

release_lock() {
  [ "${LOCK_HELD}" = "1" ] || return 0
  if command -v flock >/dev/null 2>&1; then
    eval "exec ${LOCK_FD}>&-"
  else
    rmdir "${LOCK_PATH}.dir" 2>/dev/null || true
  fi
  LOCK_HELD=0
}

trap release_lock EXIT

state_dir_for() {
  local project_root="$1"
  echo "${project_root}/.claude/state/repair-loop"
}

state_path_for() {
  local project_root="$1"
  local task="$2"
  echo "$(state_dir_for "${project_root}")/${task}.json"
}

# path containment: task id が正規表現を通っても、実パスが state_dir の外に
# 出ていないことを二重に確認する (defense in depth)。
assert_contained() {
  local state_dir="$1"
  local target="$2"
  local resolved_dir target_parent
  resolved_dir="$(cd "${state_dir}" 2>/dev/null && pwd)" || {
    echo "repair-loop-state.sh: state directory missing: ${state_dir}" >&2
    exit 1
  }
  target_parent="$(cd "$(dirname "${target}")" 2>/dev/null && pwd)" || {
    echo "repair-loop-state.sh: cannot resolve target directory for ${target}" >&2
    exit 1
  }
  if [ "${target_parent}" != "${resolved_dir}" ]; then
    echo "repair-loop-state.sh: refusing task id that escapes ${state_dir}" >&2
    exit "${USAGE_EXIT}"
  fi
}

# findings[] を schema (templates/schemas/repair-loop.v1.json) と同じ制約で
# 検証する。ここを緩めると schema ファイルは飾りになり、`check` が読む状態が
# schema を通らなくなる (Phase D レビューで実証された欠落)。
FINDING_SEVERITIES='["critical","major","minor","recommendation"]'
validate_findings() {
  local findings_json="$1"
  if echo "${findings_json}" | jq -e --argjson sev "${FINDING_SEVERITIES}" '
      type == "array"
      and all(.[];
        type == "object"
        and ((keys_unsorted - ["severity", "issue", "file"]) | length) == 0
        and has("severity") and has("issue")
        and ((.severity as $s | $sev | index($s)) != null)
        and ((.issue | type) == "string") and ((.issue | length) >= 1)
        and ((has("file") | not) or (.file == null) or ((.file | type) == "string"))
      )' >/dev/null 2>&1; then
    return 0
  fi
  echo "record: findings must be an array of {severity: critical|major|minor|recommendation, issue: string, file?: string}" >&2
  echo "        (templates/schemas/repair-loop.v1.json と同じ制約。余分なキーも不可)" >&2
  exit "${USAGE_EXIT}"
}

atomic_write() {
  local target="$1"
  local content_file="$2"
  local tmp="${target}.tmp.$$"
  cp "${content_file}" "${tmp}"
  mv "${tmp}" "${target}"
}

cmd_init() {
  require_jq
  local project_root="${1:-}"
  local task="${2:-}"
  local max_iterations="${3:-}"
  if [ -z "${project_root}" ] || [ ! -d "${project_root}" ]; then
    echo "init: project root not found: ${project_root:-<missing>}" >&2
    exit 1
  fi
  validate_task_id "${task}"
  if ! [[ "${max_iterations}" =~ ^[0-9]+$ ]] || [ "${max_iterations}" -lt 1 ]; then
    echo "init: max-iterations must be a positive integer: ${max_iterations:-<missing>}" >&2
    exit 1
  fi

  local state_dir state_path now tmp
  state_dir="$(state_dir_for "${project_root}")"
  mkdir -p "${state_dir}"
  state_path="$(state_path_for "${project_root}" "${task}")"
  assert_contained "${state_dir}" "${state_path}"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  tmp="$(mktemp)"
  jq -n \
    --arg schema_version "${SCHEMA_VERSION}" \
    --arg task "${task}" \
    --argjson max_iterations "${max_iterations}" \
    --arg now "${now}" \
    '{
      schema_version: $schema_version,
      task: $task,
      max_iterations: $max_iterations,
      status: "open",
      created_at: $now,
      updated_at: $now,
      iterations: []
    }' > "${tmp}"
  atomic_write "${state_path}" "${tmp}"
  rm -f "${tmp}"
  echo "${state_path}"
}

cmd_record() {
  require_jq
  local project_root="${1:-}"
  local task="${2:-}"
  local verdict="${3:-}"
  local findings_arg="${4:-[]}"
  if [ -z "${project_root}" ] || [ ! -d "${project_root}" ]; then
    echo "record: project root not found: ${project_root:-<missing>}" >&2
    exit 1
  fi
  validate_task_id "${task}"
  case "${verdict}" in
    APPROVE|REQUEST_CHANGES) ;;
    *)
      echo "record: verdict must be APPROVE or REQUEST_CHANGES: ${verdict:-<missing>}" >&2
      exit 1
      ;;
  esac

  local state_dir state_path
  state_dir="$(state_dir_for "${project_root}")"
  state_path="$(state_path_for "${project_root}" "${task}")"
  assert_contained "${state_dir}" "${state_path}"
  if [ ! -f "${state_path}" ]; then
    echo "record: no state file for task ${task}; run 'init' first" >&2
    exit 1
  fi

  local findings_json
  if [ "${findings_arg}" = "-" ]; then
    findings_json="$(cat)"
  else
    findings_json="${findings_arg}"
  fi
  validate_findings "${findings_json}"

  # read-modify-write を直列化する。ここを外すと並行 record で iteration が失われる。
  if ! acquire_lock "${state_path}"; then
    echo "record: could not acquire lock for ${state_path}" >&2
    exit "${USAGE_EXIT}"
  fi

  local now tmp
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  tmp="$(mktemp)"
  jq \
    --arg verdict "${verdict}" \
    --argjson findings "${findings_json}" \
    --arg now "${now}" \
    '
    (.iterations | length + 1) as $n
    | .iterations += [{iteration: $n, verdict: $verdict, findings: $findings, recorded_at: $now}]
    | .updated_at = $now
    | .status = (
        if $verdict == "APPROVE" then "approved"
        elif $n >= .max_iterations then "escalated"
        else "open"
        end
      )
    ' "${state_path}" > "${tmp}"
  atomic_write "${state_path}" "${tmp}"
  rm -f "${tmp}"
  release_lock
  echo "${state_path}"
}

cmd_check() {
  # 判定不能を業務上の escalate (exit 1) と混同させない。usage の表を参照。
  # bash の local は動的スコープなので、ここから呼ぶ validate_task_id /
  # assert_contained にもこの値が見える (関数を抜ければ自動で元に戻る)。
  local USAGE_EXIT=4
  require_jq
  local project_root="${1:-}"
  local task="${2:-}"
  if [ -z "${project_root}" ] || [ ! -d "${project_root}" ]; then
    echo "check: project root not found: ${project_root:-<missing>}" >&2
    exit "${USAGE_EXIT}"
  fi
  validate_task_id "${task}"

  local state_dir state_path
  state_dir="$(state_dir_for "${project_root}")"
  state_path="$(state_path_for "${project_root}" "${task}")"
  assert_contained "${state_dir}" "${state_path}"
  if [ ! -f "${state_path}" ]; then
    echo "check: no state file for task ${task}; run 'init' first" >&2
    exit "${USAGE_EXIT}"
  fi

  local status iteration max_iterations
  status="$(jq -r '.status' "${state_path}")"
  iteration="$(jq -r '.iterations | length' "${state_path}")"
  max_iterations="$(jq -r '.max_iterations' "${state_path}")"

  case "${status}" in
    approved)
      echo "APPROVE: iteration ${iteration}/${max_iterations}"
      exit 0
      ;;
    escalated)
      echo "ESCALATE: max_iterations reached (${iteration}/${max_iterations}) without APPROVE"
      exit 1
      ;;
    open)
      echo "CONTINUE: iteration ${iteration}/${max_iterations}"
      exit 0
      ;;
    *)
      echo "check: unknown status in ${state_path}: ${status}" >&2
      exit "${USAGE_EXIT}"
      ;;
  esac
}

case "${1:-}" in
  init)
    shift
    cmd_init "$@"
    ;;
  record)
    shift
    cmd_record "$@"
    ;;
  check)
    shift
    cmd_check "$@"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "unknown command: $1" >&2
    usage >&2
    exit 1
    ;;
esac
