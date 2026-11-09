# Harness Setup Reference: codex

This file is part of `references/` for `harness-setup`.

### codex — Codex CLI 設定

```bash
# インストール確認（Codex CLI は Node.js ベース。Harness 本体とは別物）
which codex || npm install -g @openai/codex

# タイムアウトコマンド確認（macOS）
TIMEOUT=$(command -v timeout || command -v gtimeout || echo "")
# macOS の場合: brew install coreutils
```

> **注意**: Harness v4.0 本体（`harness` コマンド）は Node.js 不要の Go バイナリ。
> Codex CLI（`codex` コマンド）は別ツールであり、引き続き Node.js が必要。

### Codex provider / model metadata policy (0.123.0+ / 0.130.0 / current models)

Codex `0.123.0` 以降の provider / model guidance と、Codex `0.130.0` stable の Bedrock `aws login` guidance は
`docs/codex-provider-setup-policy.md` を正本として扱う。
公式の current model guidance は `https://developers.openai.com/codex/models` を参照する。

要点:

- Bedrock を使う場合は、Codex built-in provider の `amazon-bedrock` を使う。
- AWS profile は user / project の Codex config で `[model_providers.amazon-bedrock.aws]` に置く。
- AWS console-login credentials from `aws login` profiles は AWS 側の profile material として扱う。
- Harness は AWS credential、console-login cache、provider endpoint を書き込まない。
- Harness の配布用 Codex config は `model` を unset にし、provider/account/CLI recommended model を継承する。固定の gpt-5.4 default は仮定しない。
- Harness の配布用 Codex config には `model_provider = "amazon-bedrock"` も setup default として固定しない。
- GPT-5.4 and GPT-5.4 mini retire from Codex with ChatGPT sign-in on August 31, 2026.
- If you sign in with ChatGPT, replace `gpt-5.4` with `gpt-5.6-terra` and `gpt-5.4-mini` with `gpt-5.6-luna`.
- The OpenAI API and Codex authenticated with your own API key aren't affected.
- 古い `gpt-5.2-codex` などを推奨 sample として残さない。
- Claude Code 側の `CLAUDE_CODE_USE_BEDROCK` / `ANTHROPIC_DEFAULT_*` / `modelOverrides` guidance と、Codex の `model_provider = "amazon-bedrock"` は混ぜない。

Bedrock を使う user / project だけが、必要に応じて次を追加する:

```toml
model_provider = "amazon-bedrock"

[model_providers.amazon-bedrock.aws]
profile = "codex-bedrock"
```

Claude Code 側の provider / MCP / telemetry guidance は
`docs/claude-code-setup-mcp-telemetry-provider.md` を参照する。
特に `ANTHROPIC_BEDROCK_SERVICE_TIER` は Bedrock 利用者の provider 環境だけで扱い、
Harness の plugin default / template / shared project settings には入れない。

### Codex app-server / plugin workflow policy (0.130.0)

Codex `0.130.0` stable (`rust-v0.130.0`, published `2026-05-08T23:09:55Z`) の app-server / plugin workflow guidance は
`docs/codex-plugin-workflows-policy.md` を正本として扱う。

要点:

- `codex remote-control` は headless remotely controllable app-server の明示起動 entrypoint。Harness setup は remote-control defaults を config に書かない。
- App-server clients can page large threads。長い loop / Breezing transcript は必要な page 範囲を確認する。
- `view_image` は multi-environment session の selected environments 経由で file を解決できる。artifact report には environment / workdir を添える。
- Live app-server threads pick up config changes without restart。ただし secret / provider / hook policy の変更は diff と verification で扱う。
- Turn diffs stay accurate across `apply_patch` including partial failures。最終判断は `git diff` と tests で確認する。
- Plugin details now show bundled hooks。install / share 前に bundled hooks を確認し、Harness bundled hooks は opt-in のままにする。
- Plugin sharing exposes link metadata and discoverability controls。公開範囲と metadata は release surface として確認する。
- Configurable OpenTelemetry trace metadata は debugging / triage 補助に限定し、個人情報・顧客情報・secret を入れない。
- Built-in MCPs first-class runtime servers は Codex runtime owned surface として扱い、plugin-provided MCP と所有者を混ぜない。
- `CODEX_HOME` environments TOML provider は user-level environment source。選択 environment を報告し、write turn は one primary environment に固定する。
- Remove skills list extra roots に依存せず、Harness mirror install または `[[skills.config]]` path-based loading を明示する。

### Codex MCP diagnostics / plugin loading (0.123.0+)

Codex `0.123.0` 以降の MCP diagnostics / plugin MCP loading guidance は
`docs/codex-mcp-diagnostics.md` を正本として扱う。

要点:

- Codex TUI では、普段は `/mcp` で軽量に server 状態だけ確認する。
- MCP server が見えない、resources が出ない、resource templates が読めない時だけ `/mcp verbose` を使う。
- `/mcp verbose` では diagnostics / resources / resource templates を確認する。
- plugin 内 `.mcp.json` は `mcpServers` 形式と top-level server map 形式の両方を受け取れる前提で案内する。
- 新規 plugin では共有しやすい `mcpServers` 形式を優先する。
- 既存 plugin が top-level server map 形式なら、Codex 側の loading 改善を利用し、不要な書き換えを避ける。
- Claude Code 側の `claude mcp ...`、`.claude/mcp.json`、hook `type: "mcp_tool"` guidance と混ぜない。

`mcpServers` 形式:

```json
{
  "mcpServers": {
    "docs": {
      "command": "node",
      "args": ["server.js"]
    }
  }
}
```

top-level server map 形式:

```json
{
  "docs": {
    "command": "node",
    "args": ["server.js"]
  }
}
```

### Codex sandbox / execution policy (0.123.0+)

Codex `0.123.0` 以降の `remote_sandbox_config` と `codex exec` shared flags guidance は
`docs/codex-sandbox-execution-policy.md` を正本として扱う。

要点:

- `remote_sandbox_config` は `requirements.toml` の host-specific sandbox policy として案内する。
- remote devbox / ephemeral CI runner / shared host のように、remote environment ごとの `allowed_sandbox_modes` を比較して決める。
- host matching は便利な分類だが、強い device authentication ではない。高リスク環境では broad wildcard を避ける。
- Harness の配布用 `codex/.codex/config.toml` には organization-specific な `remote_sandbox_config` を書かない。
- Codex `0.123.0` 以降は `codex exec` が root-level shared flags を継承するため、wrapper 側で重複した `--approval-policy` / `--sandbox` pairs を追加しない。
- `scripts/codex-companion.sh task --write` が `--sandbox workspace-write` を付けるのは、Harness の「書き込みタスク」という意図を exec-local に変換しているためであり、root shared flags の重複転送ではない。
- `scripts/codex/codex-exec-wrapper.sh` の `--full-auto` は 53.2.4 では維持する。変更する場合は別 task で approval / sandbox behavior の回帰テストを追加する。

requirements example:

```toml
allowed_sandbox_modes = ["read-only"]

[[remote_sandbox_config]]
hostname_patterns = ["devbox-*.corp.example.com"]
allowed_sandbox_modes = ["read-only", "workspace-write"]
```

**使用パターン**（公式プラグイン経由）:
```bash
bash scripts/codex-companion.sh task --write "タスク内容"
# または stdin 経由
cat /tmp/prompt.md | bash scripts/codex-companion.sh task --write
```
