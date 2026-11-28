---
name: subagent-driven-development
description: "Use when delegating to delegate_task subagents. Bounded tasks, owned review."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [delegation, subagents, coordination, review]
    related_skills: [requesting-code-review, test-driven-development, systematic-debugging]
---

# Subagent-Driven Development

## Core rule

Delegation does not transfer accountability. The coordinator (you) stays responsible for scope control, consistency, review, remediation, integration, continuity state, and the final completion claim. A subagent's summary is a self-report, not evidence.

Prefer subagents for decomposable implementation/review work — they cut elapsed time. Delegation is only acceptable when you keep control through bounded tasks and checkpoints.

## Prerequisite

Non-trivial implementation work needs a plan (even an informal one stated to the user) with acceptance criteria before you dispatch mutating subagents. Exploration/research can be delegated before that; mutation (file writes, commits, pushes) waits for the plan.

## Stall prevention — mandatory

A `delegate_task` call blocks you until the child returns; you cannot observe or interrupt it mid-run. Every dispatch must be shaped so a stall costs little and loses nothing:

- **Bounded tasks.** One subagent = one small, verifiable step (one file group, one test suite, one review). Never dispatch "implement the whole plan."
- **Explicit step budget in the task context.** State: "if not finished within this scope, stop, save/commit what's complete, and report what remains." No open-ended exploration.
- **Mandatory checkpoints for writers.** A subagent doing file/repo work should commit (or otherwise persist) after each functional increment. Uncommitted work is treated as lost if the subagent stalls.
- **Required return report.** Ask for: what's done, what remains, any blockers, and (for code) the last commit/diff reference.
- **Your checkpoint after every return.** Before the next dispatch, inspect the actual artifact — `git log`/`git diff`, the file content, test output — never trust the summary alone. If a child stalls or is cancelled, don't assume nothing happened and don't assume it finished: inspect state and resume from there.
- **Believe user observations.** If the user reports a subagent stalled or produced something wrong, treat that as fact; inspect and continue without arguing.
- **Parallelize only independent bounded tasks**, one writer per file/resource. Sequence dependent tasks.
- **Don't relaunch an equivalent oversized task after a stall.** Split the remaining work smaller, or finish the small residue yourself directly.

## Decomposition

Before dispatching, define per workstream: objective/deliverable, exact files/resources it owns, explicit non-changes, dependencies, acceptance criteria, step budget, checkpoint requirement. Assign one writer per file/resource. Establish shared contracts (interfaces, schemas) before dispatching implementations that consume them.

## Dispatch

Every `delegate_task` context should give the child: the relevant plan/goal, its bounded scope and ownership, correct branch/working directory, acceptance criteria, and the checkpoint-commit + return-report requirement. Do not authorize a subagent to widen scope, perform destructive operations, expand access, or open PRs/merge/tag/release — those stay with you (see `requesting-code-review`), unless the user explicitly delegated that too.

## Coordinator review

After each subagent returns, inspect the real diff/output/test results yourself — the implementer must not be the only reviewer of its own work. Check: compliance with assigned scope, acceptance criteria met, correctness/consistency with existing patterns, unsupported or out-of-scope changes, required test/build evidence present.

## Remediation loop

For each defect found, send a new bounded task to the responsible subagent with: what's wrong, what the plan required, what was observed, the required correction, and how to validate it. If the fix stays within the approved plan, just request it — don't re-ask the user. Re-involve the user only for scope expansion, new design decisions, destructive actions, access expansion, or genuine ambiguity.

## Integration review

After individual workstreams pass, do one final pass over shared contracts, naming, cross-component behavior, and the full test/check suite. Map every acceptance criterion to implementation and evidence before claiming the overall task complete — don't claim done while findings remain open or evidence is missing.

## Failure handling

If a bounded subagent task fails or stalls twice, stop launching equivalents. Record the blocker, finish the small residue directly or split it further, and escalate to the user only when the blocker can't be resolved within the confirmed scope.
