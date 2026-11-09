# Harness Setup Reference: mirrors-agents-localize

This file is part of `references/` for `harness-setup`.

### mirrors — 公開 skill bundle 同期

Windows の `core.symlinks=false` では repository symlink が通常ファイルになり、`harness-*` skill が command 一覧に出なくなることがあります。公開 bundle は実ディレクトリ mirror として同期します。

```bash
./scripts/sync-skill-mirrors.sh
./scripts/sync-skill-mirrors.sh --check
```

更新対象:

- `skills/`
- `codex/.codex/skills/`
- `opencode/skills/`

### agents — エージェント設定

agents/ の3エージェント構成を設定する。

```
agents/
├── worker.md      # 実装担当（task-worker + codex-implementer + error-recovery）
└── reviewer.md    # レビュー担当（code-reviewer + plan-critic）
```

### localize — ルールローカライズ

`.claude/rules/` のルールを現プロジェクトに適応する。

```bash
# ルール一覧確認
ls .claude/rules/

# プロジェクト固有ルールの追加
cat >> .claude/rules/project-rules.md << 'EOF'
# Project-Specific Rules
[プロジェクト固有ルール]
EOF
```

