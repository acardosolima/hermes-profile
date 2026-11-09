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

## Phase 5: Guard plugin

Design settled by evidence: a Hermes plugin (`plugins/harness-guard/`) maps tool calls to the harness payload and asks the pinned upstream policy binary for the verdict, so rules and their updates come from upstream. See `spec.md` ("Guard hook contract") and `docs/hermes-skill-contract.md`.

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 5.1 | [lane:fast] [tdd:skip:research] Record the Hermes hook contract on a live Hermes: payload keys, block behavior, working directory, environment visibility, approval gate behavior. | Each item in `docs/hermes-skill-contract.md` is tagged `observed` or `unknown`, with the Hermes version. | 0.1 | cc:done |
| 5.2 | [lane:gate] [tdd:skip:research] Choose the guard design from the evidence: plugin hook that calls the upstream binary. A hand port of the Go rules was rejected because the binary also has a runtime-floor layer a port would miss. | Decision recorded with the evidence in the contract doc. | 5.1, 2.1 | cc:done |
| 5.3 | [lane:gate] [tdd:required] Implement `plugins/harness-guard/` (adapter, binary fetch and hash check, hook) and `tests/guard/`. Fail closed when the binary is unavailable. Asks become blocks. Tests never execute a case. | 127 guard tests pass, including the real pinned binary on a table of 51 dangerous, safe, malformed and refused cases. Two independent review rounds fixed 2 critical and 10 major findings. The `execute_code` gap is closed by removing the toolset from the shipped config (see 6.2). | 5.2, 2.2 | cc:WIP |
| 5.4 | [lane:gate] [tdd:required] Pin binary hashes and upstream rule ids in `binaries.lock.json` from `sync`, verify in `check`, classify every rule in `tests/guard/rules.json`, run the guard tests in the bump workflow, and ship `acceptance.py`. | Generator tests pass. A new unclassified upstream rule fails the guard tests. The real v5.16.0 passes the gate. | 5.3 | cc:WIP |
| 5.5 | [lane:release] [tdd:skip:manual-device-smoke] Live smoke on a fresh profile: enable the plugin, run harmless guarded and allowed commands, run `acceptance.py --live`. | Observed on Linux with Hermes v0.22.6 on a fresh install: 57 of 57 checks pass. Second machine still open (6.1). | 5.4 | cc:WIP |
| 5.6 | [lane:fast] [tdd:skip:docs-only] README: how the guard works, how to enable it, how to check it, known gaps. | README matches the verified commands. | 5.5 | cc:done |

## Phase 6: Acceptance on a second machine, then the bump

| Task | Content | DoD | Depends | Status |
|------|---------|-----|---------|--------|
| 6.1 | [lane:release] [tdd:skip:manual-device-smoke] On another machine: install the profile, run `hermes plugins enable harness-guard` if it was not enabled by `config.yaml`, then run `acceptance.py` and `acceptance.py --live <profile>`. | Every check passes, on macOS or Windows if that is the second machine. Output recorded in the contract doc. | 5.4 | cc:TODO |
| 6.2 | [lane:gate] [tdd:required] Close or document the unguarded paths: `execute_code`, `delegate_task` and subagents. Decided: the `code_execution` toolset is removed from the shipped config. `delegate_task` stays an unverified gap. | Each path is either inspected by the guard with tests, or listed as an accepted gap with the reason. The acceptance script fails when `code_execution` is enabled in `platform_toolsets`. | 5.3 | cc:WIP |
| 6.3 | [lane:gate] [tdd:skip:research] Run the 121 bundled helper scripts' entry points under Hermes and list which need the upstream `bin/harness` program. | A table in the contract doc: works, needs `bin/harness`, or untested. Decision recorded on whether to keep each script. | 5.5 | cc:TODO |
| 6.4 | [lane:release] [tdd:skip:manual-device-smoke] Re-run the bump for upstream v5.16.0 with the guard gate, merge it only after 6.1, then run `acceptance.py` again on the device. | The bump PR contains the regenerated guard lock. Acceptance passes before and after the merge. | 6.1 | cc:TODO |

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
