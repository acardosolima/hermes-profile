# Release Body Preview

tag-triggered workflow が GitHub Release に公開する、CHANGELOG 本文の preview ルール。

## CHANGELOG ドラフト作成（メモリ上、Pre-Gate ステップ 7）

Confirmation Gate に提示する前に、以下をメモリ上で計算する。まだファイルには書き込まない。

1. `## [Unreleased]` の本文を切り出す。
2. `## [Unreleased]` と `## [<previous>]` の間に `## [<new>] - YYYY-MM-DD` を挿入した形を作る。
3. 末尾 compare link を更新する。
   - `[Unreleased]: .../compare/v<prev>...HEAD` を `v<new>...HEAD` に更新する。
   - `[<new>]: .../compare/v<prev>...v<new>` を追加する。
4. repo URL は既存の `[Unreleased]: ` 行から動的に抽出する。

## 公開本文の正本

`.github/workflows/release.yml` は tag の version を使い、`CHANGELOG.md` の
`## [X.Y.Z]` 見出し直後から次の version 見出し直前までをそのまま抽出する。
したがって preview も同じ本文を表示する。英訳、別要約、固定フッターを加えない。

CHANGELOG が日本語なら GitHub Release も日本語になる。言語を変えたい場合は、
別本文を作るのではなく Confirmation Gate で CHANGELOG ドラフト自体を修正する。

## CHANGELOG release body preview の作り方

1. メモリ上で昇格後の `## [<new>] - YYYY-MM-DD` セクションを組み立てる。
2. version 見出しを除き、次の `## [` の直前までを抽出する。
3. Confirmation Gate に、workflow が公開する本文として省略せず提示する。
4. ユーザーが修正を指示した場合は CHANGELOG ドラフトを直し、同じ抽出を再実行する。

## 検証

- 本文が空でない。
- `[Unreleased]` の全項目が含まれる。
- 別 version の本文や compare link が混ざっていない。
- placeholder や生成途中の marker が残っていない。
- preview と昇格後 CHANGELOG からの抽出結果が byte-for-byte で一致する。

同日に複数バージョンを出すのは非推奨（versioning.md）。複数変更は同じ
KaCL section の `Added` / `Changed` / `Fixed` などでまとめる。
