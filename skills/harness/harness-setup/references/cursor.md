# Harness Setup Reference: cursor

This file is part of `references/` for `harness-setup`.

## Cursor 実装バックエンド導入（脳 Opus / 体 composer）

Cursor を Harness の実装（worker）バックエンドとして使うための導入手順。
レビュー / advisor ロールは Opus に固定し、cursor バックエンドへ切り替えない（`.claude/rules/cursor-cli-only.md` の Role scope）。

### 1. AI 実行可（バックエンド選択の永続化）

`set-impl-backend.sh` でバックエンドを永続化する。Harness / AI がこのステップを実行できる。

```bash
# プロジェクトスコープ（このプロジェクトの env.local に書く）
bash "scripts/set-impl-backend.sh" cursor

# ユーザースコープ（全プロジェクト共通: ${HOME}/.config/claude-harness/impl-backend.env）
bash "scripts/set-impl-backend.sh" --user cursor

# 現在解決されるバックエンドを表示して確認
bash "scripts/set-impl-backend.sh" --show
```

解決の優先順位: プロジェクト env.local がユーザースコープより優先される。

### 2. ユーザー手動（AI は編集不可。protected path + sandbox のため）

以下 3 ファイルは `Edit/Write(.claude/settings*)` deny と self-audit guard、および `~/.cursor/*` が
plugin write 対象外であるため Harness / AI が編集できない。ユーザー自身がターミナル / エディタで設定する。

- **`~/.cursor/permissions.json`**: `terminalAllowlist` / `mcpAllowlist` を追加する。
  テンプレートは `.claude/rules/cursor-cli-only.md` の `~/.cursor/permissions.json` テンプレートを使う。
  `--force` / Run Everything（`--yolo`）は使わない（Cursor 公式が "Never use"）。
- **`.cursorignore`**: secrets（`.env`, `*.pem`, `*.key`, `.ssh`, `.aws`, `.git`）を列挙する。
  テンプレートは `.claude/rules/cursor-cli-only.md` の `.cursorignore` テンプレートを使う。
- **`~/.claude/settings.json` の sandbox（2 点）**: (1) `network.allowedDomains` に `*.cursor.sh` を追加、
  (2) 公式キー **`sandbox.filesystem.allowWrite`** に `~/.cursor` を追加する（cursor-agent は実行時に
  `~/.cursor/projects/...` と `~/.cursor/cli-config.json.tmp` へ状態を書くため、未許可だと
  `EPERM` で失敗する）。⚠️ **キー名は `allowWrite`**: `write` という名前にすると未知キーとして
  無視され設定が効かない（実測で確認）。`~/` は sandbox 側で展開される（公式例 `["~/.kube"]`）。
  両方揃うと per-run の
  sandbox 無効化なしで実行できる。手順は `docs/sandbox-allowlist-recipe.md` の jq merge レシピと
  `.claude/rules/cursor-cli-only.md` の「Sandbox 要件」に従う。CC 完全再起動後に有効化される。

### 3. 境界（cursor は candidate のまま）

cursor バックエンドは candidate の位置づけ。安全性は Cursor の allowlist（best-effort、bypass 可能）ではなく、
**専用 `.git` を持つ worktree での隔離実行 + Lead による diff レビュー + cherry-pick での本流取り込み**で担保する。
cursor-agent の出力は Lead レビューまで untrusted として扱う。詳細は `.claude/rules/cursor-cli-only.md` を参照。

