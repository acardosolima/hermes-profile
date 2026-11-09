# Review Loop

The review loop is shared by Solo, Parallel, and Breezing. Parallel runs it once
per Worker; Breezing runs it from the Lead (see below).

## Order

1. Prefer Codex companion structured review when available.
2. Fall back to the internal `reviewer` agent (when `command -v codex` fails or
   the companion times out at 120s).
3. Run AI Residuals in parallel with either:

```bash
bash "scripts/review-ai-residuals.sh" --base-ref "${BASE_REF}" --include-untracked
```

4. Normalize the review artifact with `write-review-result.sh`.

## Verdict Threshold

Give the reviewer only this threshold; it must judge verdict from it alone.
Below-threshold suggestions become `recommendations` and never flip the verdict.

Provide the original request, outcome and DoD, selected plan/spec/contract,
owned scope and authorization source, actual target diff, and existing
validation evidence to the reviewer. Use fresh read-only context; the author's
report is a claim to check. Recover missing evidence through allowed reads
before requesting material input. Findings need a location, failure condition,
and checkable reason, not private reasoning transcripts.

| Severity | Definition | Verdict effect |
|---|---|---|
| `critical` | Security vulnerability, data loss risk, possible production outage | Any finding means `REQUEST_CHANGES` |
| `major` | Breaks an existing feature, clearly contradicts spec, failing test | Any finding means `REQUEST_CHANGES` |
| `minor` | Naming, missing comment, style inconsistency | Does not change verdict |
| `recommendation` | Best-practice suggestion, future improvement | Does not change verdict |

Minor-only and recommendation-only reviews must approve. "Would be nice to have" is never a reason for `REQUEST_CHANGES`.

## Codex Companion Review

Capture `BASE_REF=$(git rev-parse HEAD)` before implementation starts, then diff against it:

```bash
BASE_REF=$(git rev-parse HEAD)
# ... implementation complete ...
bash "scripts/codex-companion.sh" review --base "${BASE_REF}"
REVIEW_EXIT=$?
```

Verdict mapping (official plugin → Harness):

| Official plugin | Harness | Verdict effect |
|---|---|---|
| `approve` | `APPROVE` | - |
| `needs-attention` | `REQUEST_CHANGES` | - |
| `findings[].severity: critical` | `critical_issues[]` | Any → `REQUEST_CHANGES` |
| `findings[].severity: high` | `major_issues[]` | Any → `REQUEST_CHANGES` |
| `findings[].severity: medium/low` | `recommendations[]` | Does not change verdict |

## Internal Reviewer Agent Fallback

When Codex exec is unavailable:

```
Agent tool: subagent_type="reviewer"
prompt: "Review the original request and DoD against the actual diff in fresh read-only context. Request/why/owned scope/authorization source: {task_request}. Plan/spec/contract: {paths}. Validation evidence: {evidence}. Verdict rule: critical/major -> REQUEST_CHANGES, minor/recommendation only -> APPROVE. Report locations, failure conditions, evidence, and unverified items. diff: {git diff ${BASE_REF}}"
```

The `reviewer` agent is read-only (no Write/Edit/Bash) so it can review safely.

## Repair Loop

Iteration state is externalized to `.claude/state/repair-loop/<task>.json`
(schema: `templates/schemas/repair-loop.v1.json`) instead of living only in
conversation memory. This makes the `MAX_REVIEWS` ceiling machine-judged: the
same agent bounded by the ceiling cannot self-report an undercount, and a
long loop that loses earlier findings to context rot can still read them
back from the state file.

```
MAX_REVIEWS = read_contract(contract_path, ".review.max_iterations") or 3
bash scripts/repair-loop-state.sh init "${PROJECT_ROOT}" "${TASK_ID}" "${MAX_REVIEWS}"

while true:
    1. Run the review (see Order above); get verdict + findings
    2. bash scripts/repair-loop-state.sh record "${PROJECT_ROOT}" "${TASK_ID}" "${verdict}" "${findings_json}"
    3. if verdict == "APPROVE": break
    4. Parse the findings (critical / major only) and fix each one
    5. bash scripts/repair-loop-state.sh check "${PROJECT_ROOT}" "${TASK_ID}"
       - exit 0 -> below the ceiling (or already approved), loop continues
       - exit 1 -> ceiling reached without APPROVE
       - any other non-zero (2 = jq missing, 4 = cannot evaluate)
                -> the loop state could not be judged; this is NOT an escalation
    6. Re-run the review with the same threshold and priority order

if `check` exited 1:
    -> escalate to the user with the remaining critical/major findings
       (read from the state file's iterations[], not from memory),
       wait for continue/abort

if `check` exited 2 or 4:
    -> report the tooling failure itself (missing `init`, wrong project root,
       corrupt state file, jq unavailable). Do NOT report it as "review limit
       reached" — that would blame the reviewer for a broken invocation.
```

> **Why exit 1 and exit 4 are separate**: this branch is taken by an autonomous
> agent that sees only the exit code. If "the ceiling was reached" and "the
> state could not be read" shared a code, a forgotten `init` or a wrong path
> would be reported to the operator as a genuine review escalation — the
> infrastructure would misreport in exactly the place this feature exists to
> stop the agent from misreporting.

Breezing repair instructions go back to the same Worker. In Codex, resume the
Worker and use `send_input`; in Claude Code, send the equivalent teammate
message (`SendMessage`).
Keep the original scope, DoD, and approval source in repair instructions; attach
the critical/major findings and relevant evidence. Re-review the changed output
in fresh context within the same iteration limit. Once DoD and required checks
pass, stop; optional improvements do not start another repair or test cycle.

## Breezing-Specific Application

In Breezing, the **Lead** runs the review loop:

1. Worker implements and commits inside its worktree, then returns the result to Lead.
2. Lead reviews via Codex exec (preferred) or the Reviewer agent (fallback).
3. `REQUEST_CHANGES` → Lead sends fix instructions via `SendMessage`; Worker amends.
4. Re-review after the fix (up to `MAX_REVIEWS`).
5. `APPROVE` → Lead cherry-picks onto trunk and marks `Plans.md` `cc:完了 [{hash}]`.
