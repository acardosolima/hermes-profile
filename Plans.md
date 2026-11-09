# Plans

Purpose: keep the Hermes profile's harness skills in sync with the upstream
claude-code-harness repo automatically. Contract: `spec.md` ("Harness skills
contract"). Marker legend: `cc:TODO`, `cc:WIP`, `cc:done`, `blocked`.

Conventions: `[lane:gate]` needs review before merge. `[tdd:required]` means
write the failing test first. Anything not observed on a real Hermes install
is `unknown`, not absent.

## Phase 0: Hermes contract discovery

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 0.1 | [lane:fast] [tdd:skip:research] Record the Hermes skill contract in `docs/hermes-skill-contract.md`: tolerated frontmatter keys, a variable equivalent to `${CLAUDE_SKILL_DIR}`, tool names, whether `hermes profile install` copies nested `references/` and script files. Source-read pass done against Hermes v0.22.6; runtime rows stay `unknown` until observed on a device where Hermes starts. | Every claim in the doc is tagged `source-read`, `observed` or `unknown`. Doc names the Hermes version. | - | cc:done |
| 0.2 | [lane:fast] [tdd:skip:research] Decide Claude-to-Hermes tool mapping (`Agent`/Task, `AskUserQuestion`, `ScheduleWakeup`, `WebSearch`) from 0.1. Hermes names seen in the bundled hermes-agent skill: `delegate_task`, `clarify`, `cronjob`, `terminal`, `read_file`, `write_file`. | Mapping table in the contract doc. Each row marked `mapped`, `degraded` or `unsupported`, with the reason. | 0.1 | cc:done |

## Phase 1: Pin upstream

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 1.1 | [lane:fast] [tdd:skip:data-file] Add `upstream.lock` (repo URL, tag, commit sha) pinned to the upstream release currently installed on this device. | File parses as JSON. The sha resolves to the tag via `git ls-remote`. | - | cc:done |
| 1.2 | [lane:fast] [tdd:skip:setup] Add Python lint and format baseline for `tools/`: ruff config in `pyproject.toml`, tests written with stdlib `unittest` so `python -m unittest` and `pytest` both run them with no install. | `python -m unittest discover tools` exits 0 on a smoke test. `ruff check tools` exits 0. | - | cc:done |

## Phase 2: Generator

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 2.1 | [lane:gate] [tdd:required] `tools/harness_sync.py` fetch stage: shallow-clone upstream at the locked sha into a temp dir, verify the sha, never write inside the clone. | Test with a local fixture repo passes. Wrong sha makes the tool exit nonzero with no output written. | 1.1, 1.2 | cc:done |
| 2.2 | [lane:gate] [tdd:required] Translation rules: frontmatter normalization, path-variable rewrite, tool-name mapping from 0.2, compatibility preamble injection. Allow-list from `spec.md` only. | Fixture-based tests cover each rule. A fixture skill with an unmapped Claude-only construct is reported, not silently copied. | 0.2, 2.1 | cc:done |
| 2.3 | [lane:gate] [tdd:required] Helper script bundling: copy only the upstream scripts each allow-listed skill references into that skill's own `scripts/` directory and rewrite the references. Record tokens with no upstream file in the manifest as `missing_scripts`. | Test asserts every script path referenced by a generated skill exists in output. No unreferenced script is copied. | 2.2 | cc:done |
| 2.4 | [lane:gate] [tdd:required] Manifest and determinism: write `skills/harness/GENERATED.json` (upstream tag, sha, content hashes, generator version). Do not name it with a leading dot, because `.gitignore` excludes `skills/.*`. | Two runs on the same lock produce byte-identical output. | 2.3 | cc:done |
| 2.5 | [lane:gate] [tdd:required] `--check` mode: regenerate to a temp dir and diff against `skills/harness/`. | Exit 0 when equal. Exit 1 and a diff summary after a hand edit to a generated file. | 2.4 | cc:done |
| 2.6 | [lane:gate] [tdd:required] Secret guard: generator fails if any generated file contains a token-shaped string (Anthropic, GitHub, AWS, Slack keys, PEM private key headers). | Test with a planted `sk-ant-` string in a fixture makes the tool exit nonzero. | 2.2 | cc:done |

## Phase 3: Automation

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 3.0 | [lane:gate] [tdd:required] `bump` subcommand: resolve the newest `vX.Y.Z` upstream tag, pin its commit sha in `upstream.lock`, never downgrade, refuse a tag that moved. | Tests against local git fixtures pass, including numeric tag ordering, annotated-tag peeling, moved-tag refusal and CLI exit codes. | 2.1 | cc:done |
| 3.1 | [lane:gate] [tdd:skip:ci-config] `.github/workflows/harness-bump.yml`: scheduled daily, runs `bump`, and if the lock moved regenerates, verifies and opens a PR titled `chore: bump harness to <tag>`. The workflow verifies before opening the PR because PRs opened with the workflow token do not trigger other workflows. | `actionlint` passes. A manual `workflow_dispatch` run against a newer tag opens a PR with the lock and `skills/harness/` changes. | 3.0, 2.5 | cc:WIP |
| 3.2 | [lane:gate] [tdd:skip:ci-config] `.github/workflows/ci.yml`: on PR run the unit tests on Linux, macOS and Windows, lint, and `check`. | A PR with a hand-edited generated file fails the check. A clean PR passes on all three operating systems. | 2.5 | cc:done |
| 3.3 | [lane:fast] [tdd:skip:docs-only] README section "Harness skills": how updates arrive, `hermes profile update master`, how to see the installed harness version from `GENERATED.json`. | README steps match the verified commands from Phase 4. | 4.1 | cc:TODO |

## Phase 4: Verification on Hermes

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 4.1 | [lane:release] [tdd:skip:manual-device-smoke] On a device with Hermes, install the profile into a scratch profile name and run `hermes skills list`. Invoke `/harness-plan` and `/harness-review` on a throwaway repo. | Skills listed. Both commands start and reach their first tool call. Result recorded in `docs/hermes-skill-contract.md` with the Hermes version. Observed on v0.22.6: install, discovery, `/harness-plan sync` and `/harness-review` through a model, each reaching tool calls. | 2.5 | cc:done |
| 4.2 | [lane:release] [tdd:skip:manual-device-smoke] Update path: bump the lock to a newer tag in a branch, run `hermes profile update` on the scratch profile. | Installed `GENERATED.json` shows the new tag. Files upstream removed from a skill are gone. A skill dropped from the allow-list is documented as a manual removal, because update does not delete it. Observed on v0.22.6 with a simulated change and with a real `bump` to upstream v5.16.0: the device moved from v5.15.0 to v5.16.0 and its skills matched the generated output. | 4.1, 3.1 | cc:done |
| 4.3 | [lane:fast] [tdd:skip:docs-only] Parity matrix in the contract doc: what works, degrades or is absent on Hermes versus Claude Code. | Each row cites 0.1, 0.2 or 4.1 evidence. No row claims enforcement parity. | 4.1 | cc:TODO |

## Phase 5: Guard hook

Hermes supports `pre_tool_call` shell hooks (see `agent-hooks/gate-skill-manage.py` and the README section on it). Upstream enforces its guardrails with `bin/harness hook pre-tool`, a Go binary fed Claude Code tool payloads. The hook `command` is a literal path, so activation is per device.

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 5.1 | [lane:fast] [tdd:skip:research] Record the Hermes hook contract on a device with Hermes: event names beyond `pre_tool_call`, the stdin payload keys for `terminal`, `read_file`, `write_file`, whether `HERMES_HOME` is set in the hook environment, and whether the allowlist approval can be written non-interactively. | Each item in `docs/hermes-skill-contract.md` is tagged `observed` or `unknown`, with the Hermes version. | 0.1 | cc:TODO |
| 5.2 | [lane:gate] [tdd:skip:research] Choose the guard design from 5.1 evidence. Option A: an adapter hook maps the Hermes payload to the upstream payload shape and calls the upstream `harness` binary, so rules follow upstream. Option B: a Python guard whose rules the generator extracts from upstream. Option C (preferred, source-read): a Hermes plugin under `plugins/` registers `pre_tool_call` through `ctx.register_hook`, so no per-device command path or allowlist step exists. `hermes profile update` keeps an existing device's `config.yaml`, so each existing device enables the plugin once. Weigh binary size and per-OS builds against rule drift. | Decision recorded in the contract doc with the evidence for it. | 5.1, 2.1 | cc:TODO |
| 5.3 | [lane:gate] [tdd:required] Implement the chosen guard under `agent-hooks/`, generated by the sync tool when it derives from upstream. Fail closed on a parse error for dangerous tools, and pass unrelated tools through. | Tests cover: secret-path read blocked, `rm -rf` blocked, force push blocked, a benign command passes, malformed payload on a guarded tool exits 2. | 5.2, 2.2 | cc:TODO |
| 5.4 | [lane:gate] [tdd:required] Activation script `agent-hooks/activate.py`: resolve the profile's absolute path, run the `hermes config set hooks.pre_tool_call` merge so the existing `skill_manage` entry is kept, and print the allowlist entry for the actual `HERMES_HOME`. Works on Linux, macOS and Windows paths. | Test with a fake home asserts the merged hooks list contains both guards and the printed allowlist path matches the fake home. | 5.3 | cc:TODO |
| 5.5 | [lane:release] [tdd:skip:manual-device-smoke] On a device with Hermes, activate and approve the hooks, then trigger a blocked and an allowed call. Run `hermes hooks doctor`. | Doctor reports allowlisted. The blocked call is refused with the guard message, the allowed call runs. Evidence recorded with the Hermes version. | 5.4 | cc:TODO |
| 5.6 | [lane:fast] [tdd:skip:docs-only] README: replace the manual `skill_manage` hook steps with the activation command, and state which guardrails are enforced on Hermes. | README commands match those verified in 5.5. Parity matrix in 4.3 lists hook coverage per guardrail. | 5.5, 4.3 | cc:TODO |

## Priority matrix

| Class | Items |
|-------|-------|
| Required | 0.1, 0.2, 1.1, 1.2, 2.1 to 2.5, 3.1, 4.1, 5.1 to 5.5 |
| Recommended | 2.6, 3.2, 3.3, 4.2, 4.3, 5.6 |
| Optional | Auto-merge of bump PRs after CI passes. Translate more skills later. |
| Reject | Git submodule (bloats profile installs). Runtime symlinks (per-device setup, security warning). Manual copy scripts. Porting upstream Claude Code hook definitions verbatim (Hermes uses its own hook config). |

## Spec delta

`spec.md` created with the "Harness skills contract" section.

## team_validation_mode

`manual-pass`. Perspectives reviewed by one author:
- Product: removes every manual step from upstream tracking.
- Architecture: committed generated output removes dependence on installer symlink behavior, which is `unknown`.
- Security: no secrets in output (2.6). Upstream content is untrusted input, so the bump goes through a PR and CI, never auto-merge.
- QA: every generator task has a failing-test-first DoD. Device behavior is only claimed after 4.1.
- Skeptic: upstream may restructure skills. The fixture tests and `--check` surface that as a failed bump PR, not a broken device.

## 事前確認

- 事項: network fetch of the upstream GitHub repo (shallow clone, read-only)
  理由: generator input and the daily bump check
  scope: Phase 2 / Task 2.1, Phase 3 / Task 3.1
- 事項: external-send via `git push` of a bump branch and `gh pr create`
  理由: bump workflow opens a PR on the profile repo
  scope: Phase 3 / Task 3.1
- 事項: external-send via `git push` of feature branches
  理由: normal delivery of this plan's changes
  scope: Phase 1 to Phase 4
