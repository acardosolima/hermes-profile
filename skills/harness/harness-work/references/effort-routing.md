# Effort Routing Detail

`harness-work` で使う推論量と、見直しの判断材料。

## 背景

Fable 5.1 の計画と相談は `high` を既定にする。
Codex の高度な担当は astra に更新し、既存の役割別推論量を維持する。
推論量を増やすと常に総合品質が上がる、とは判断しない。
Fable の FrontierCode 評価では、高い推論量で機能正確性が上がる一方、依頼外変更で総合点が下がった。
一次資料と役割表は `docs/model-routing-policy.md` を参照する。

利用者の明示した model/effort を優先する。
未指定の担当は router または native agent 定義の設定を使う。
`ultrathink` のような自由文から設定を引き上げない。

## 多要素スコアリング

タスク着手時に以下のスコアを合算する。

| 要素 | 条件 | スコア |
|------|------|--------|
| ファイル数 | 変更対象 4 ファイル以上 | +1 |
| ディレクトリ | core/, guardrails/, security/ を含む | +1 |
| キーワード | architecture, security, design, migration を含む | +1 |
| 失敗履歴 | agent memory に同タスクの失敗記録あり | +2 |
| 明示指定 | PM テンプレートに `effort: high` / `effort: xhigh` の設定あり | スコアより指定値を優先 |

## effort tier の決め方（注入しない）

スコアは設定見直しの候補を出すために使う。
依頼外変更や原因の誤認がある場合は、変更範囲と検証方法を先に確認する。
既存の設定を変更する必要がある場合は、呼出し側の明示指定または承認済みの担当設定を使う。

- **session `/effort`**: Claude Code の会話に使う推論量。担当 agent の frontmatter が別値を持つ場合は、その値が優先される。
- **worker frontmatter**: `agents/worker.md` の Sonnet 5/medium は実装 worker の既定。計画や相談の Fable 5.1/high とは別に扱う。
- **Codex companion**: 明示引数 > `CODEX_EFFORT` > router の役割別設定。Codex の `ultra` は CLI の実行モードであり、公開 API の effort 値として渡さない。

| スコア | code-risk（core/guardrails/security/architecture/migration を含む） | 見直し候補 |
|--------|-----------------------------------|-------------|
| 0-2 | 不問 | `medium`（Worker frontmatter 既定のまま） |
| ≥ 3 | なし | `high` |
| ≥ 3 | あり | `xhigh` |

breezing でも役割を分離する。親のモデルや推論量を、そのまま全 worker に広げない。

## 任せる仕事と完了判定

目的、対象パス、完成条件、既に許可された操作を渡す。
承認済みの可逆作業は、再現から修正後の検証まで進める。
独立した調査は並行させ、同じファイルを複数 worker に同時編集させない。
完成条件を満たした時点で止め、依頼外の整理や重複テストを追加しない。
報告では実物の差分と検証結果を使い、進行中の作業では利用者に定期的に状況を返す。
