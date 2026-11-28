---
name: durable-artifact-git-hygiene
description: "Write commits, PRs, docs for future readers, not chat history."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, commits, pull-requests, documentation, hygiene]
    related_skills: [requesting-code-review, test-driven-development]
---

# Durable Artifact and Git Hygiene

## Core principle

Describe the durable artifact, not the conversation or process that produced it. Before persisting text (commit message, PR description, docstring, README, comment), apply both tests:

1. Would a reader who never saw the chat understand it?
2. Would it remain accurate and useful later?

If either answer is no, rewrite it. If something can't be made durable and artifact-centered, keep it in the chat reply instead of the artifact.

## Never persist in code/docs/commits/PRs

- Context that exists only in the conversation.
- Instructions, requests, or corrections received in chat.
- Alternatives discussed, abandoned attempts, implementation sequence/narrative.
- Phrases like "as requested", "after our discussion", "in this session".
- Tool, agent, or editing-process narratives ("I ran...", "manually confirmed...").
- Relative-time claims ("currently", "recently", "today") when a stable fact can be stated instead.
- Who requested/decided/implemented something — write about the artifact, not the person.
- Out-of-scope commentary, unless omitting it would create a dangerous misunderstanding.

## Comments, docstrings, error messages

Explain durable constraints, contracts, invariants, non-obvious intent — never chat history, temporary circumstances, authorship, or attempted approaches. Error messages describe the violated condition and useful corrective context, never the agent or the editing process.

## Commit messages

Format: `<type>: <short, specific, imperative summary>` — lowercase Conventional Commits prefix (`feat|fix|docs|test|refactor|chore|perf|style|revert`), subject <=~72 chars, no trailing period, no generic subjects ("updates", "various fixes"). Body only for durable technical info that doesn't fit the subject — never a process narrative. `BREAKING CHANGE:` goes in the footer, never the subject.

Before committing, confirm:

    commit prefix: [feat|fix|docs|test|refactor|chore|perf|style|revert]
    subject is imperative and specific (not "updates"/"various changes"): yes/no
    body (if present) is technically necessary, not a narrative: yes/no/absent
    chat-only or process context present: no

## Pull requests

**Never open, update, or submit a PR without an explicit human request in the current session.** Permission to code, commit, or push is not permission to open a PR — this is the single highest-value check in this skill; most PR-hygiene failures are actually this check being skipped.

Before the PR operation:

    did the human explicitly ask to open/update a PR in this session: yes/no
    if no: STOP — do not perform the PR operation

Description: 2-5 concise bullets of key changes, one motivation sentence only if the diff doesn't make it obvious. Exclude CI status, verification narratives, branch history, chat context, implementation chronology.

Before submitting:

    understandable without the chat: yes/no
    every statement verifiable in the diff or a durable motivation: yes/no
    contains conversation/process narrative: no
    2-5 concise change bullets present: yes/no

If a repository's own template/instructions require something stricter or different (e.g. mandatory sections), follow the local instructions and ask the user if they conflict with the rules above rather than silently picking one.
