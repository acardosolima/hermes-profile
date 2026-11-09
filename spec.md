# hermes-profile product contract

## Purpose

One git repo that configures Hermes identically on every device through
`hermes profile install` and `hermes profile update`. It carries config,
persona, skills and plugins. It carries no secrets.

## Harness skills contract

The repo ships the claude-code-harness workflow skills to Hermes without any
manual copy step.

- Upstream is `github.com/Chachamaru127/claude-code-harness`. It is the only
  source of truth for skill content.
- `upstream.lock` pins one upstream tag and commit sha.
- `tools/harness_sync.py` is the only writer of `skills/harness/`. Output is
  deterministic for a given lock and generator version.
- Generated files are committed, so a device needs only the profile repo and
  never a harness checkout or a symlink.
- A scheduled workflow detects a newer upstream release, regenerates, and
  opens a pull request. A merge to master is the only way a device receives
  the new version.
- Devices pick up changes with `hermes profile update`.

### Translated skills

Allow-list: `harness-plan`, `harness-work`, `harness-review`,
`harness-sync`, `harness-setup`, `harness-loop`, `harness-release`,
`breezing`. All other upstream skills are out of scope.

### Parity boundary

Skill text and bundled helper scripts translate. Claude Code hook
definitions, monitors and agent definitions do not. Guardrails are enforced
only where a Hermes hook covers them (see "Guard hook"). Each translated
skill states which guardrails are and are not enforced in a generated
compatibility preamble.

## Guard hook contract

- The profile ships `pre_tool_call` shell hooks under `agent-hooks/`.
- Hermes hook config holds a literal command path, so `config.yaml` does not
  carry the `hooks:` block. `agent-hooks/activate.py` writes it per device and
  keeps existing guard entries.
- Hook approval in the Hermes allowlist stays a per-device consent step. The
  repo never writes the allowlist without the activation command being run.
- Guards fail closed for the tools they cover. Unrelated tools pass through.
- Guard coverage is documented per guardrail. A guardrail with no hook
  coverage is listed as not enforced.

### Invariants

- No secret, token or per-device credential in generated output.
- `not_observed != absent`: any Hermes behavior not observed on a real
  device is recorded as unknown, never as supported.
- Generated output is never hand-edited. A hand edit fails the drift check.
- Upstream support wording stays accurate: Hermes is a `candidate` host
  upstream, and docs here say so.
