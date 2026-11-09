# GitHub Release Body Rules

GitHub Release の本文は `.github/workflows/release.yml` が CHANGELOG の該当 version
section から抽出する。Harness は別の release notes を生成しない。Confirmation Gate では
実際に公開される CHANGELOG-derived release body をそのまま提示する。

## CHANGELOG フォーマット

Keep a Changelog の標準見出しを使い、各項目はユーザー価値が判断できる粒度で書く。
「今まで → 今後」は理解を助ける場合に使えるが、固定 table や英訳、フッターは必須ではない。

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added

- **機能名**。何が使えるようになり、誰の操作がどう変わるか

### Changed

- **変更名**。以前の挙動と新しい挙動、移行条件
```

**書き方ルール**:
- KaCL の `Added` / `Changed` / `Fixed` / `Security` 等を使う
- 最初に利用者の変化を書き、内部ファイル名は必要な場合だけ補足する
- 後戻り条件、再起動、再 setup などの移行条件を省略しない
- 未観測の provider/runtime 結果は保証として書かない

## Prohibited

- workflow が使わない別本文を作らない
- CHANGELOG にない価値・実測・保証を release preview へ追加しない
- 技術的な変更一覧だけで、利用者への影響を落とさない
- preview を省略・翻訳・要約して、実際の公開本文とずらさない

## マージ方式（merge commit 固定 / squash 不採用）

release PR および main へ取り込む PR は **merge commit** (`gh pr merge --merge` /
`git merge --no-ff`) を使う。squash / rebase は不採用（Phase 114 preamble 裁定 2026-07-14）。

**なぜ**: Plans.md は task の Status 列に commit hash を台帳として埋めている
（例: 113.1 `cc:done [fa2b9c37]`）。squash はこれらの hash を main の ancestry から
外し、台帳と履歴の突合（`scripts/ci/check-branch-alignment-ledger.sh`、AR-16）を
破壊する。squash は技術的には可能（3 方式許可 + binary は `-buildvcs=false` で
SHA 非依存）だが、hash 台帳が Plans.md に存在する限り採用しない。

- 機械 gate: merge 前に `bash scripts/ci/check-branch-alignment-ledger.sh` exit 0 を確認する
- 先例: v5.0.0 の #235 / #236 も merge commit
- 見直し条件: Plans.md が hash 台帳方式をやめた時のみ再検討する

## Release evidence の保存（v5.1.0 監査指摘の codify）

upgrade smoke（旧 version → 新 version の実測）や release gate の実行ログは、
宣言だけでなく **artifact として `.claude/state/release-evidence/<version>/` に保存**する。
Plans.md の cc:done マーカーが「実測した」と主張する項目には、対応するログファイルか
コマンド出力の記録が存在しなければならない（SA-13 completeness 監査 2026-07-16 の指摘）。

## Workflow-owned Release Creation

GitHub Release の作成は `.github/workflows/release.yml` に委譲する。Harness は
default branch 到達済み commit に tag を付けて push し、workflow が CHANGELOG の
該当 section を release body として公開する。Harness から直接 Release を作成・編集しない。

```bash
git push origin vX.X.X
gh run list --workflow release.yml --limit 5
bash scripts/release-verify-publish.sh vX.X.X OWNER/REPO
```

公開済み Release の本文訂正が必要な場合は、通常リリースとは別の外部変更 Risk Gate
として扱う。まず CHANGELOG と workflow の正本を修正し、operator の明示承認なしに
公開済み本文を変更しない。

## CC バージョン統合時の CHANGELOG パターン

Claude Code の新バージョン統合を含むリリースでは、通常の「今まで / 今後」形式ではなく、
**「CC のアプデ → Harness での活用」形式**を使用する。
上流（CC）の変更理由から説明することで、読者が「なぜこの変更が自分に関係あるか」を文脈から理解できる。

### 判定条件

以下のいずれかに該当する場合、このパターンを適用する:

- Feature Table のバージョン表記が更新されている
- hooks.json に CC 由来の新イベントが追加されている
- skills に CC 新機能の活用ガイドが追記されている

### 構造

```markdown
#### N. Claude Code X.Y.Z 統合

（1 行で全体概要）

##### N-1. 機能名

**CC のアプデ**: Claude Code で何が変わったか。ユーザー視点で、その機能が何をするものか分かるように説明。

**Harness での活用**: その変更を Harness がどう活かしているか。具体的な仕組み（スクリプト名、フロー）を含める。

##### N-2. 次の機能名

**CC のアプデ**: ...
**Harness での活用**: ...
```

### 書き方ルール

- 機能ごとに `##### N-X.` で独立セクションにする
- 「CC のアプデ」はファイル変更ではなく**ユーザー体験の変化**を書く
- 「Harness での活用」は**具体的な仕組み**（何が動くか、何が防がれるか）を書く
- ファイル名の羅列は避ける。「hooks.json を更新」ではなく「Worker のフリーズを防止」のように書く
- ドキュメントのみの変更（Feature Table 更新、詳細セクション追加）は個別エントリにせず、冒頭の概要 1 行に含める

### Good Example

```markdown
##### 5-1. MCP Elicitation への自動対応

**CC のアプデ**: MCP サーバーが、タスク実行中にユーザーへ「質問」できるようになった（Elicitation）。
例えば「どのリポジトリに push しますか？」のようなフォーム入力を求められる。

**Harness での活用**: Breezing の Worker はバックグラウンド実行のため質問フォームに応答できない。
放置すると Worker がフリーズする。elicitation-handler.sh を新規作成し、
Breezing セッション中は自動スキップ、通常セッションではそのまま通過してユーザーが回答する仕組みを実装。
```

### Bad Example

```markdown
#### CC 2.1.76 統合

- hooks.json に Elicitation を追加
- elicitation-handler.sh を作成
- CLAUDE.md を更新
```

→ ファイル変更の羅列で、なぜその変更が必要だったか、ユーザーにとって何が変わるかが伝わらない

## Reference

- Good examples: v2.8.0, v2.8.2, v2.9.1, v3.10.3 (CC統合パターン)
- Keep consistent with CHANGELOG
