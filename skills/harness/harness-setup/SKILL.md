---
name: "harness-setup"
description: "HAR: Project init, tool setup, agent config, memory setup, skill mirror sync. Trigger: setup, init, new project, CI/Codex setup, harness-mem, mirror. Do NOT load for: implementation, review, release, planning."
version: "v5.15.0"
platforms: [linux, macos, windows]
---

<!-- harness-sync:preamble:start -->
This skill was translated from Claude Code to Hermes. Claude Code tools map to Hermes tools as follows: Bash -> terminal, Read -> read_file, Write/Edit -> write_file/patch (patch arguments unverified), AskUserQuestion -> clarify, Agent/Task -> delegate_task (degraded), ScheduleWakeup -> cronjob (degraded), WebSearch -> web toolset. TeamCreate and hook-driven monitors have no Hermes equivalent. Guardrail hooks referenced by the original skill are not enforced here; only hooks shipped and activated in this profile under agent-hooks/ apply. Helper scripts bundled with this skill live in its scripts/ directory; where the text refers to a plugin root, use this skill's directory as that root for those scripts. Paths such as .claude/state and bin/harness may not exist on this host.
<!-- harness-sync:preamble:end -->

# Harness Setup

Harness の統合セットアップスキル。
以下の旧スキルを統合:

- `setup` — 統合セットアップハブ
- `harness-init` — プロジェクト初期化
- `harness-update` — Harness アップデート
- `maintenance` — ファイル整理・クリーンアップ

## Quick Reference

| サブコマンド | 動作 | 詳細 |
|------------|------|------|
| `/harness-setup init` | 新規プロジェクト初期化（CLAUDE.md + Plans.md + hooks + sync + doctor）| `references/init.md` |
| `/harness-setup ci` | CI/CD パイプライン設定 | `references/ci.md` |
| `/harness-setup codex` | Codex CLI インストール・設定 | `references/codex.md` |
| `/harness-setup harness-mem` | harness-mem 統合・メモリ設定 | `references/harness-mem.md` |
| `/harness-setup mirrors` | skills/ → 公開 mirror bundle 更新 | `references/mirrors-agents-localize.md` |
| `/harness-setup agents` | agents/ エージェント設定 | `references/mirrors-agents-localize.md` |
| `/harness-setup localize` | CLAUDE.md ルールのローカライズ | `references/mirrors-agents-localize.md` |
| marketplace / update | Plugin install, update, dependency policy | `references/marketplace.md` |
| maintenance | ファイル整理・クリーンアップ | `references/maintenance.md` |

> **Built-in slash discovery (CC 2.1.108+)**:
> `/init` のような built-in slash command も発見される。
> Harness 固有の bootstrap が必要な時だけ `/harness-setup init` と使い分ける。

> **Claude Code setup guidance (CC 2.1.120+)**:
> MCP `alwaysLoad`、`${CLAUDE_EFFORT}`、`claude plugin prune`、`claude project purge`、
> `ANTHROPIC_BEDROCK_SERVICE_TIER`、`claude_code.skill_activated.invocation_trigger`、
> Windows PowerShell primary shell、forked skills / subagents の deferred tools は
> `docs/claude-code-setup-mcp-telemetry-provider.md` を正本として扱う。

> **Codex plugin workflows**:
> Codex `/goal` と `Plans.md` を二重管理しない。
> plugin-bundled hooks は opt-in、external agent import は ownership 明記、
> MultiAgentV2 / `agents.max_threads = 8` は上限として扱い、
> sticky environments / app-server artifacts は safe default を優先する。
> Codex `0.130.0` stable の `codex remote-control`、large thread pagination、
> selected-environment `view_image`、live app-server config refresh、
> accurate turn diffs、plugin details bundled hooks、sharing discoverability controls は
> `docs/codex-plugin-workflows-policy.md` を正本として扱う。
> 詳細は `docs/codex-plugin-workflows-policy.md` と `references/codex.md` を参照。

## Execution

状態確認だけの依頼は read-only の診断で完了する。setup 依頼は対象、望む状態、合格条件を既存設定と照合し、明示された surface の変更を進める。
不足情報は設定や契約を読み取りで回収する。任意機能を追加したり、対象外の設定や保護された設定を目的から推測して変更したりしない。

1. ユーザーの目的に対応する Quick Reference 行を選ぶ。
2. 該当する `references/*.md` を読む。
3. 参照ファイルの手順に従い、dry-run がある操作は dry-run を先に実行する。
4. setup 後は必要に応じて `harness doctor`、`bash scripts/sync-skill-mirrors.sh --check`、`bash scripts/ci/check-consistency.sh` で確認する。

## Upstream Policy Anchors

- `docs/plugin-managed-settings-policy.md` — plugin managed settings policy; normal defaults must not inherit managed marketplace restrictions.
- `docs/codex-provider-setup-policy.md` — Codex provider setup policy, including `amazon-bedrock` and `model_provider = "amazon-bedrock"` examples.
- Codex `0.123.0` 以降の MCP diagnostics / plugin MCP loading guidance: use `/mcp verbose` and `docs/codex-mcp-diagnostics.md` for diagnostics.
- Codex sandbox / execution policy (0.123.0+): see `docs/codex-sandbox-execution-policy.md` for `remote_sandbox_config` and execution constraints.

## Cursor 実装バックエンド導入

詳細手順は `references/cursor.md` を読む。
契約アンカー: `set-impl-backend.sh` は AI 実行可。`permissions.json`、`.cursorignore`、`*.cursor.sh` allowlist はユーザー手動で、AI が編集できない protected path として扱う。
根拠ルールは `.claude/rules/cursor-cli-only.md` と `docs/sandbox-allowlist-recipe.md`。

## Reference Index

- `references/init.md` — init, Go binary verification, plugin sync, doctor.
- `references/ci.md` — GitHub Actions CI setup.
- `references/codex.md` — Codex CLI, provider/model metadata, app-server, MCP diagnostics, sandbox policy.
- `references/cursor.md` — Cursor implementation backend setup and boundaries.
- `references/harness-mem.md` — memory directory and template setup.
- `references/mirrors-agents-localize.md` — mirror sync, agent setup, localization.
- `references/marketplace.md` — plugin marketplace install/update and managed dependency policy.
- `references/maintenance.md` — cleanup commands and related skills.

## 関連スキル

- `harness-sync` — 設定/Plans/git 状態の同期確認
- `harness-work` — 実装タスク実行
- `harness-review` — 品質レビュー
- `maintenance` — ファイル整理（統合済み）
