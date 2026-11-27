# Changelog

All notable changes to this distribution are documented here.

## [Unreleased]

No changes yet.

## [1.2.0] — 2026-11-xx

### Fixed
- Block token substitution, allow public HTTPS clone
- Always lock the default profile

### Added
- Lock built-in default profile after activate

## [1.1.0]

### Added
- PR #14: Enforce English-only responses (prevent Japanese text from upstream harness skills leaking into agent output)
- PR #13: Streamline documentation
- PR #12: Add `hooks.pre_tool_call` gate on `skill_manage` with `fail_closed: true`

## [1.0.1]

### Fixed
- Turn off every tool in the default profile, which has no enforcement plugin

## [1.0.0]

### Added
- Initial profile distribution with enforcement policy
- Auto-loaded skills: TDD, requesting-code-review, systematic-debugging
- Split-model orchestration support (local coordinator / stronger subagents)
- Multi-device export/install/update workflow via `distribution.yaml`
- Agent hooks for activation flow
