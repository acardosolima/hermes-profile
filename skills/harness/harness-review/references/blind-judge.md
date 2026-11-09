# Blind Judge (opt-in) — rubric なしの第二意見

`--blind-judge` で opt-in する review 拡張。通常の reviewer は rubric（`references/code-review.md`
や `references/ui-rubric.md` のチェックリスト）を渡されて評点するため、「チェックリストは満たすが
意図した読者には伝わらない・読みにくい」という失敗を見落としやすい。blind judge は rubric も
prior verdict も一切渡さない **fresh agent** に、成果物と読者/目的だけを見せて素の第一印象を取る。

**既定 OFF。明示 `--blind-judge` のときだけ動く。自動発火しない。**

## `dual_review` との違い

| | dual_review (`references/dual-review.md`) | blind judge |
|---|---|---|
| 目的 | 同じ rubric を複数モデルで評価し、見落としを減らす | rubric そのものを外し、rubric が測れない「伝わるか」を見る |
| 渡す情報 | rubric + diff + 仕様正本 + Plans.md | 成果物 + 読者/目的 1 行のみ |
| 対象 | code 全般 | 主観品質が支配的な外部向け成果物のみ（下記 Eligibility） |
| verdict への効き方 | primary verdict にマージされる（Codex/Cursor は advisory、Opus 優先） | **verdict を変えない**。divergence を報告するだけ |

同じ review 実行内で両方を使ってよい。dual_review は「rubric の中で正しいか」、blind judge は
「rubric の外で伝わるか」を見るため、役割は重複しない。

## Eligibility（対象を絞る）

主観品質が支配的な成果物だけに使う。コード・テスト・設定・スキーマには使わない — この種の
成果物は「正しいか / 動くか」が rubric で機械的に判定でき、rubric なしの第一印象は評価軸として
無意味かノイズになるため。

| 対象 | 適用 | 理由 |
|---|---|---|
| 外部向け UI コピー（ボタン文言、エラーメッセージ、オンボーディング文） | 適用可 | 意図した読者に伝わるかが本質で、rubric だけでは測れない |
| ドキュメント（README、ガイド、説明資料） | 適用可 | 同上。読み手が実際に迷わず読めるかは fresh eyes でしか測れない |
| cognitive-load HTML surfaces（Plan Brief / 進捗確認 / 受け入れ判断。`docs/cognitive-load-surfaces.md`） | 適用可 | 非エンジニア読者向けの判断材料 HTML。伝達失敗が直接判断ミスに繋がる |
| コード実装 | **不可** | 正誤は rubric（テスト・型・lint）で判定すべきで、rubric なし第一印象は評価軸にならない |
| テスト | **不可** | 同上 |
| 設定ファイル（`.eslintrc*`, `tsconfig*.json` 等） | **不可** | 主観品質の入る余地がない |
| スキーマ（`templates/schemas/**`） | **不可** | 同上。構造の正しさが全てで「読みやすさ」は評価対象外 |

対象外の成果物に `--blind-judge` が指定された場合は、実行せず `not_applicable` として報告する
（無理に実行して意味のない divergence を作らない）。

## 判定役の設計原則: 「plain fresh sub-agent」であり `context: fork` skill ではない

**blind judge は Task tool で起動する plain な fresh sub-agent として実装する。`context: fork` を
持つ skill として実装してはならない。**

理由（次に手を入れる人が「fork の方がシンプル」と判断して置き換えないための明記）:

`.claude/rules/skill-editing.md` の「`context: fork` + `disable-model-invocation: true` 時の
auto-start pattern」節（Issue #84）が実測として記録している通り、`context: fork` skill は
isolated context の**仕様上は** host project の CLAUDE.md / session-start rules を継承しない
はずだが、CC の実装上は host project の rules が fork 先に**実際に流入する**ケースが確認されて
いる。blind judge にとってこれは致命的で、rubric（= このスキル自身の SKILL.md や
`references/*.md`）が fork 先に漏れ込めば、judge は「rubric を知らないふり」をした rubric-aware
reviewer になり、blind judge という設計の前提が崩れる。

Task tool で起動する plain sub-agent はこの漏れ込み経路を持たない。渡すのはプロンプト文字列
だけであり、呼び出し元 skill のファイルシステム上のコンテキスト（SKILL.md 本体や
`references/`）を継承しない。したがって blind judge は必ず Task tool 経由の sub-agent として
起動する。

## 手順

1. Eligibility を確認する。対象外なら `not_applicable` として終了する（Output Contract 参照）。
2. rubric 側のレビュー（通常の code/ui-rubric review）は独立して先に、または並行して進めてよい。
   ただし judge には **その結果を一切渡さない**。
3. 下記「渡してよいもの / 渡してはいけないもの」を厳守し、Judge Prompt Template を組み立てる。
4. Task tool で fresh sub-agent（`subagent_type: general-purpose` 推奨。専用 agent 定義は持たない
   — 専用 agent ファイルを作ると、その agent の説明文自体が rubric の漏れ込み経路になりうる
   ため、汎用 agent に都度プロンプトで渡す設計を維持する）を起動する。
5. judge の生の一言判定（読める/読めない、伝わる/伝わらない、の一次反応）を受け取る。
6. rubric 側の verdict と judge の反応を突き合わせ、`blind_judge` finding を組み立てる
   （Output Contract 参照）。divergence があっても rubric 側の verdict は変えない。

## 渡してよいもの / 渡してはいけないもの

| 渡してよいもの | 渡してはいけないもの |
|---|---|
| 成果物そのもの（ファイル内容 / レンダリング結果） | rubric 本文（`references/ui-rubric.md` 等の評価軸・閾値） |
| 読者/目的 1 行（下記 template の `{AUDIENCE_PURPOSE_LINE}`） | rubric 側の verdict（APPROVE / REQUEST_CHANGES） |
| — | rubric 側の findings / observations |
| — | diff の commit メッセージ（意図の説明が答えを教えてしまう） |
| — | implementer の report（worker-report.v1 等。実装意図の弁明が答えを教えてしまう） |
| — | この review セッションのそれまでの会話・判定 |

judge に渡すのは「成果物」と「読者/目的 1 行」の 2 つだけ。これ以外の文脈は、どれだけ無害に
見えても rubric や prior verdict の代理情報になりうるため渡さない。

## Judge Prompt Template

Task tool 呼び出し時のプロンプトは次の形に固定する。`{...}` を埋めるだけで、追加の説明文や
前置きを足さない。

```
あなたは初見の読者としてこの成果物を見ます。事前情報も採点基準も与えられていません。

読者/目的: {AUDIENCE_PURPOSE_LINE}

成果物:
{ARTIFACT_CONTENT}

この成果物を上記の読者/目的の立場で読んで、次の3点だけ答えてください。
1. 一読して意図が伝わったか（伝わった / 伝わらなかった / 一部だけ伝わった）
2. 読んでいて引っかかった箇所があれば具体的に（無ければ「なし」)
3. この成果物をそのまま読者に見せてよいと思うか（見せてよい / 見せない方がよい / 迷う）

採点基準やチェックリストはありません。あなたの第一印象をそのまま述べてください。
```

`{AUDIENCE_PURPOSE_LINE}` の例: 「投資家向け提案資料の要約スライド。数分で読み切れて、次に
何を判断すればよいかが分かる必要がある」

## Output Contract — `blind_judge` finding

`review-result.v1` に任意フィールド `blind_judge` を追加する。`dual_review` と同じく optional
field なので既存 consumer（HTML render / harness-accept 等）は無視してよく、parser を壊さない。

schema ファイルは作らない。理由: `dual_review` / `cursor_verdict` など既存の review 拡張フィー
ルドも `templates/schemas/**` 側に schema を持たず、`review-result.v1` の一部として SKILL.md /
reference 内にインラインでのみ定義されている（例: `templates/schemas/` には
`review-result.v1` 自体の schema ファイルすら存在しない）。`blind_judge` を機械的に読む
script は現時点でなく、この場に厚い契約を作るのは不釣り合い。機械 consumer が生まれた時点で
`templates/schemas/blind-judge.v1.json` を切り出す。

```json
{
  "blind_judge": {
    "applicable": true,
    "eligibility_reason": "external-facing UI copy | docs | cognitive-load HTML surface | not_applicable | unavailable",
    "audience_purpose_line": "投資家向け提案資料の要約スライド。数分で読み切れて...",
    "judge_first_impression": "conveyed | not_conveyed | partially_conveyed | uncertain",
    "judge_friction_points": ["引っかかった箇所の具体的な引用または要約"],
    "judge_show_as_is": "show_as_is | do_not_show | uncertain",
    "rubric_verdict": "APPROVE | REQUEST_CHANGES",
    "divergence": "none | rubric_pass_judge_fail | rubric_fail_judge_pass",
    "divergence_notes": "divergence がある場合の具体的な説明。無ければ空文字列"
  }
}
```

フィールドの意味:

| field | 型 | 意味 |
|---|---|---|
| `applicable` | bool | Eligibility を満たし judge を実行したか。`false` なら以下は省略可 |
| `eligibility_reason` | enum | どの Eligibility 区分に該当したか、`not_applicable`、または Task tool 不在時の `unavailable` |
| `audience_purpose_line` | string | judge に渡した読者/目的 1 行（監査用にそのまま記録） |
| `judge_first_impression` | enum | judge の回答 1. をそのまま writeup。応答が3点形式に沿わない場合は `uncertain`（下記フォールバック） |
| `judge_friction_points` | string[] | judge の回答 2.（「なし」なら空配列） |
| `judge_show_as_is` | enum | judge の回答 3. |
| `rubric_verdict` | enum | 同一 review 内の rubric 側 verdict（`--ui-rubric` 併用時は `references/ui-rubric.md` の判定、それ以外は通常 `code` review の verdict） |
| `divergence` | enum | rubric と judge が食い違っているか。`rubric_pass_judge_fail` = rubric は通したが judge は「見せない方がよい」、`rubric_fail_judge_pass` = 逆 |
| `divergence_notes` | string | divergence がある場合、何が食い違ったかを具体的に |

## Advisory-only 制約（絶対）

**`blind_judge` の divergence は verdict を書き換えない。** `divergence != none` でも自動的に
`REQUEST_CHANGES` にしない。理由: judge は rubric を知らない第一印象に過ぎず、rubric が正しく
最終防衛線であるべき軸（security・regression・spec alignment 等）に judge の主観が介入すると、
このスキルの合格ライン（`references/governance.md`）を判断者不在で歪める。

divergence は次のように出力の `Findings` セクションに **observation として** 追加する。severity
は付けない（severity を付けた瞬間に verdict gate へ滑り込むため）。

```
Findings:
- [observation] blind_judge divergence: rubric=APPROVE, judge=do_not_show — 「{friction point の要約}」。人間/Lead の判断待ち。
```

`decision_needed` にもしない。divergence は「止めるべき理由」ではなく「rubric が見落として
いるかもしれない、という追加の判断材料」であり、止めるかどうかは人間/Lead が決める。

## フォールバック

- Task tool が使えない環境（Codex 等）: `blind_judge.applicable: false` とし、
  `eligibility_reason` に `"unavailable: task tool not available in this environment"` を記録する。
  fake の judge 結果を作らない。
- judge の応答が3点の形式に沿わない: そのまま `judge_friction_points` に生の応答を格納し、
  `judge_first_impression` / `judge_show_as_is` は `"uncertain"` とする。

## Related

- `references/dual-review.md` — rubric を保ったまま複数モデルで評価する既存の second-opinion 機構
- `references/ui-rubric.md` — blind judge が対象にできる代表的な rubric（4軸採点）
- `references/governance.md` — verdict gate の合格ライン（blind judge はこれを変更しない）
- `.claude/rules/skill-editing.md` — `context: fork` の継承漏れ実測（Issue #84）
