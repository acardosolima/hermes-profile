# Review Governance

## ひとことで

`APPROVE` は「重大な問題がない」と証拠つきで言える時だけ返す。

## 明確な合格ライン

`APPROVE` の条件:

- critical / major が 0 件
- root `spec.md` alignment: 上位 product contract と矛盾しない。sub-spec (`spec_path`) がある場合も root contract を優先確認する。不要 task のみ `spec_skip_reason` を許容
- `Plans.md` alignment: task / DoD / Depends と矛盾しない。`[lane:fast|gate|release]` と stage gate metadata が contract と一致
- TDD evidence: `[tdd:required]` task では `tdd_red_log`、literal failing output、または明示 `skip_tdd_reason` がある
- unknown data contract: 証拠なしの「問題なし」「データなし」を `APPROVE` しない。`not_observed != absent` — 未観測は `unknown` / `not observed` と報告する
- regression safety: 既存挙動、既存テスト、既存 UX、既存 CLI、既存設定、既存 docs、配布 mirror にデグレ証拠がない
- evidence pack: accepted findings / rejected findings、focused tests、`release-preflight` warnings の処理方針が report にある
- TeamAgent Debate の未解消 disagreement がない

## Severity

| severity | 意味 | verdict |
|---|---|---|
| critical | 秘密情報露出、データ破壊、権限破壊、release 事故に直結する | REQUEST_CHANGES |
| major | DoD 未達、仕様正本違反、lane/stage 不整合、TDD evidence 欠落、明確なデグレ、テスト未実行で危険 | REQUEST_CHANGES |
| minor | 品質は上がるが出荷停止ほどではない | APPROVE 可 |
| recommendation | 任意改善 | APPROVE 可 |

minor / recommendation だけなら、必ずしも止めない。
止めるなら、なぜ major なのかを具体的に説明する。

## AskUserQuestion / decision_needed

まず元の依頼、spec、選択した plan、既存の承認と読み取り可能な根拠から不足情報を回収する。それでも重要な仕様や権限の判断が残る場合は、`REQUEST_CHANGES` ではなく `decision_needed` とする。軽微な仮定は明示し、独立して確認できる範囲のレビューは続ける。

`decision_needed` の例:

- 仕様正本を変える必要がある
- `Plans.md` の DoD / Depends / lane / stage を変える必要がある
- security と UX の優先順位をユーザーが選ぶ必要がある
- backward compatibility を残すか削るかの事業判断が必要

必要な判断には対象の操作、具体的な推奨案、根拠、承認を要求する契約のパスと該当指示を添える。既に同じ範囲の承認がある場合は聞き直さない。AskUserQuestion が使える場合は使う。
Codex 環境などで使えない場合は `decision_needed.v1` を stdout に出し、推測で進めない。

## Side effects

review default read-only boundary:

- `APPROVE` でも自動 commit しない
- `APPROVE` は commit / push / PR 作成命令ではない
- Do not push just to review
- commit / push / release は `harness-work` / `harness-release` / ユーザー明示依頼の責務

## Output evidence

必須:

- 対象範囲
- 実行した review command
- 実行した tests
- accepted findings
- rejected findings
- release-preflight warnings と処理方針
- clean result または残課題
- root `spec.md` / `Plans.md` lane-stage / デグレ / TDD / unknown data の合格ライン

`APPROVE` なのに evidence pack が空なら、その `APPROVE` は無効。
