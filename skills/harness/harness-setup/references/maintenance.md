# Harness Setup Reference: maintenance

This file is part of `references/` for `harness-setup`.

## Maintenance — ファイル整理

定期メンテナンスタスク:

| タスク | コマンド |
|--------|---------|
| 古いログ削除 | `find .claude/logs -mtime +30 -delete` |
| Plans.md 圧縮 | 完了タスクをアーカイブセクションに移動 |
| 古いトレース削除 | `tail -1000 .claude/state/agent-trace.jsonl > /tmp/trace && mv /tmp/trace .claude/state/agent-trace.jsonl` |

## 関連スキル

- `harness-plan` — セットアップ後にプロジェクト計画を作成
- `harness-work` — セットアップ後にタスクを実行
- `harness-review` — セットアップ設定をレビュー
