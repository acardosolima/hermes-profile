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

- The guard is the Hermes plugin `plugins/harness-guard/`. It registers a
  `pre_tool_call` hook, so it needs no command path and no allowlist entry.
  `config.yaml` enables it for new installs. An existing device enables it once
  with `hermes plugins enable harness-guard`, because `hermes profile update`
  keeps that device's `config.yaml`.
- Rules are not reimplemented. The plugin maps `terminal`, `process_manage`
  input, `read_file`, `write_file` and `patch` calls to the harness payload and asks the pinned
  upstream policy binary for the verdict, so rules and their updates come from
  upstream. Command text is only ever passed to the binary as data.
- `plugins/harness-guard/binaries.lock.json` pins the upstream commit, the
  sha256 of each platform binary and the upstream rule ids. It is written by
  `tools/harness_sync.py sync` and verified by `check`. A binary is downloaded
  on first use from the pinned commit and used only if its hash matches.
- The guard fails closed. If the binary is missing, unverifiable or times out,
  the guarded tools are blocked with a message.
- A harness "ask" (a confirmation by a human) becomes a block that tells the
  agent to ask the user. Hermes' approval gate is not relied on, because its
  default mode lets an auxiliary model approve.
- The guard has no settings. The only off switch is
  `hermes plugins disable harness-guard`. As a best-effort text filter, commands
  and file paths that mention the guard, its lock, `harness.toml`, the Hermes
  plugin directory or `config.yaml` (shell spellings of the home directory are
  resolved), or the `hermes plugins|config|profile|gateway|hooks` commands, are
  refused before the policy runs. This is not a security boundary.
- A guarded call that cannot be judged is blocked, never sent on as empty input:
  mistyped or missing arguments, a patch that names no file, `~user` paths, an
  unknown working directory, or a working directory that is `/`, the home
  directory or a system location. Relative paths and `~/` are resolved before
  judging, a terminal `workdir` is honored, and every file named by a patch-file
  mode patch is judged.
- The binary is re-hashed on every call and runs with a scrubbed environment and
  the strictest upstream delete and push policy.
- Every upstream rule id is classified in `tests/guard/rules.json` as
  `enforced`, `warn-only` or `not-applicable`. A release that adds a rule fails
  the guard tests until the rule is classified. The bump workflow runs these
  tests before it opens a pull request.
- `tests/guard/` and `plugins/harness-guard/acceptance.py` judge a table of
  known cases against the real binary. They never execute a case.
- Known gaps are listed in the README: tools the guard does not inspect
  (`execute_code`, `delegate_task` children, `skill_manage`, `search_files`,
  scheduled scripts), rules that only warn upstream, and temp-directory writes
  that upstream allows.

### Invariants

- No secret, token or per-device credential in generated output.
- `not_observed != absent`: any Hermes behavior not observed on a real
  device is recorded as unknown, never as supported.
- Generated output is never hand-edited. A hand edit fails the drift check.
- Upstream support wording stays accurate: Hermes is a `candidate` host
  upstream, and docs here say so.
