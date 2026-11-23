# hermes-profile product contract

## Purpose

One git repo that configures Hermes identically on every device through
`hermes profile install` and `hermes profile update`. It carries config,
persona, skills and plugins. It carries no secrets.

## Harness skills contract

The repo ships selected Claude Code harness workflow skills to Hermes without
a manual copy step.

- Upstream: `github.com/Chachamaru127/claude-code-harness`. Pinned in `upstream.lock`.
- `tools/harness_sync.py` is the only writer of `skills/harness/`. Output is
  deterministic for a given lock.
- Generated files are committed. A device needs only the profile repo.
- A scheduled CI workflow detects newer upstream releases, regenerates, and
  opens a PR. Merge to master is the only path devices receive updates.
- Devices pick up changes with `hermes profile update`.

**Allow-listed skills:** `harness-plan`, `harness-work`, `harness-review`,
`harness-sync`, `harness-setup`, `harness-loop`, `harness-release`, `breezing`.

Guardrails on these skills come from the `harness-guard` plugin below.

## Guard hook contract

The guard is the Hermes plugin `plugins/harness-guard/`. It registers a
`pre_tool_call` hook. Rules are not reimplemented — the plugin maps Hermes
tool calls to the upstream policy binary and asks for the verdict.

- `binaries.lock.json` pins the upstream commit, binary sha256, and upstream
  rule IDs. Written by `sync`, verified by `check`.
- The guard fails closed: missing binary, hash mismatch, or timeout → blocked.
- "Ask" (human confirmation) from upstream becomes a block telling the agent
  to ask you. Hermes' approval gate is not relied on.
- No settings. `hermes plugins disable harness-guard` is the only off switch.
  The guard also blocks commands referring to its own config files.
- Calls the guard cannot judge are blocked, never silently passed through.
- Every upstream rule ID is classified in `tests/guard/rules.json`.
  New unclassified rules fail the tests until handled.

**Known gaps** (listed in README): `execute_code`, `delegate_task`,
`skill_manage`, `search_files`, background process input, temp-directory writes.

## Invariants

- No secrets in generated output.
- `not_observed != absent`: behavior not seen on a real device is unknown, never claimed supported.
- Generated output is never hand-edited; a drift check catches it.
