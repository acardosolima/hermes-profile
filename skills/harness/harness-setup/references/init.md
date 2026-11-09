# Harness Setup Reference: init

This file is part of `references/` for `harness-setup`.

## サブコマンド詳細

### init — プロジェクト初期化

新規プロジェクトに Harness を導入する。

**生成ファイル**:
```
project/
├── CLAUDE.md            # プロジェクト設定
├── Plans.md             # タスク管理（空テンプレート）
├── .claude/
│   ├── settings.json    # Claude Code 設定
│   └── hooks.json       # フック設定（Go バイナリ）
└── hooks/
    ├── pre-tool.sh      # 薄いシム（→ core/src/index.ts）
    └── post-tool.sh     # 薄いシム（→ core/src/index.ts）
```

**フロー**:
1. プロジェクト種別を検出（Node.js/Python/Go/Rust/その他）
2. 最小限の CLAUDE.md を生成
3. Plans.md テンプレートを生成
4. hooks.json を配置
5. **Go バイナリ検証**: `harness version` でバイナリが利用可能か確認（v4.0 以降 Node.js 不要）
6. **プラグインファイル同期**: `harness sync` で `.claude-plugin/` 配下のファイルを最新に同期
7. **ヘルスチェック**: `harness doctor` で全チェック項目をパス。問題があれば修正案を提示

### Go バイナリ検証

```bash
# バイナリの存在と動作を確認
harness version
# 例: harness v4.0.0 (go1.22.0, darwin/arm64)
```

v4.0 以降、Harness のコアエンジンは Go バイナリに移行した。
Node.js は不要。バイナリは `bin/harness`（または PATH 上の `harness`）を使用する。

### プラグインファイル同期

```bash
# .claude-plugin/ 配下のファイルを最新に同期
harness sync

# 同期内容の確認のみ（変更なし）
harness sync --dry-run
```

`harness sync` は skills/ の SSOT から各 mirror（codex/.codex/skills/、opencode/skills/）へ
変更を伝播させる。init 後に必ず実行すること。

### ヘルスチェック

```bash
# 全チェック項目を実行
harness doctor
```

`harness doctor` は以下を確認する:

| チェック項目 | 内容 |
|------------|------|
| バイナリ | `harness version` が正常に返るか |
| プラグイン設定 | `.claude-plugin/plugin.json` の形式が正しいか |
| hooks 配置 | hooks が正しいパスに存在するか |
| mirror 同期 | skills/ と mirror の内容が一致しているか |
| CLAUDE.md | 必須セクションが存在するか |

問題が検出された場合は修正コマンドを提示する。

