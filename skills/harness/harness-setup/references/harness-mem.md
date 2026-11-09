# Harness Setup Reference: harness-mem

This file is part of `references/` for `harness-setup`.

### harness-mem — メモリ設定

Unified Harness Memory の設定を行う。

```bash
# メモリディレクトリ作成
mkdir -p .claude/agent-memory/claude-code-harness-worker
mkdir -p .claude/agent-memory/claude-code-harness-reviewer

# MEMORY.md テンプレート配置
cat > .claude/agent-memory/claude-code-harness-worker/MEMORY.md << 'EOF'
# Worker Agent Memory

## Project Context
[プロジェクト概要]

## Patterns
[学習パターン]
EOF
```

