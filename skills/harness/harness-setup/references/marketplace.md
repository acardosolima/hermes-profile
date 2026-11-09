# Harness Setup Reference: marketplace

This file is part of `references/` for `harness-setup`.

## Plugin インストール (v2.1.71+ Marketplace)

v2.1.71 で Marketplace の安定性が大幅に改善された。
Claude Code 2.1.117-2.1.118 以降の plugin / managed settings 方針は
`docs/plugin-managed-settings-policy.md` を正本として扱う。

### 推奨インストール方式

```bash
# @ref 形式でバージョン固定（推奨）
claude plugin install owner/repo@v4.0.0

# 最新版
claude plugin install owner/repo
```

`owner/repo@vX.X.X` 形式を推奨。`@ref` パーサー修正により、タグ・ブランチ・コミットハッシュいずれも正確に解決される。

### アップデート

```bash
claude plugin update owner/repo
```

v2.1.71 で update 時の merge conflict が修正され、安定したアップデートが可能になった。

### その他の改善点

- MCP server 重複排除: 同一 MCP サーバーの多重登録を自動防止
- `/plugin uninstall` が `settings.local.json` を使用: ユーザーローカル設定に正確に反映

### Managed marketplace / dependency policy (v2.1.117+)

企業利用で plugin marketplace を制御する場合は、Claude Code 本体の managed settings を使う。
Harness は独自の marketplace resolver や dependency resolver を重ねない。

| 項目 | 用途 | Harness の扱い |
|------|------|----------------|
| `extraKnownMarketplaces` | チームに推奨 marketplace を案内・登録する | 通常の onboarding ではこちらを優先 |
| `blockedMarketplaces` | 特定 marketplace source をブロックする | managed settings 専用。通常ユーザー向け default には入れない |
| `strictKnownMarketplaces` | 許可した marketplace source だけ追加できるようにする | managed settings 専用。通常ユーザー向け default には入れない |
| plugin dependency auto-resolve | `dependencies` の自動 install / missing dependency hints | Claude Code 本体に任せる。Harness 独自 resolver は追加しない |
| plugin `themes/` directory | plugin が theme を配布する | 今回は P: 将来タスク。Harness は theme を同梱しない |

`DISABLE_AUTOUPDATER` は自動更新を止める。
`DISABLE_UPDATES` は手動 `claude update` まで止めるため、企業の固定バージョン運用向け。
Harness の project default にはどちらも入れず、必要な組織が managed settings または端末管理で設定する。

依存関係が欠けた場合は、まず Claude Code の `/plugin` Errors、`/doctor`、`claude plugin list --json` を確認する。
marketplace 未登録が原因なら `/plugin marketplace add` または `claude plugin marketplace add` で登録し、本体の auto-resolve に任せる。

