---
name: hermes-credential-management
description: "Audit/lock Hermes provider credentials; stop OAuth fallback."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, auth, credentials, billing, providers, oauth, security]
    related_skills: [hermes-agent]
---

# Hermes Credential Management

How to find out which stored credential Hermes is actually using for a given
provider, and how to permanently stop it from using one you don't want
touched (e.g. a personal API key vs. a company Claude Code / Codex OAuth
login sitting on the same machine). Billing/account identity is at stake, so
treat "never use X" as requiring removal, not just deprioritization.

## When to Use

- User asks which account/subscription/API key Hermes is actually using or
  billing against for a given provider.
- User wants to guarantee a specific credential (often a company OAuth
  login shared with another CLI) is NEVER used, even as a fallback.
- Multiple credentials exist for one provider and you need to tell them
  apart without exposing secret values.

## Procedure

1. List the credential pool for the provider in question:
   `hermes auth list`
   Shows every registered credential per provider, in priority order
   (priority 0 = tried first, marked with `←` = currently active).

2. Identify what's behind each entry WITHOUT printing live secrets:
   - `source` — `env:VAR_NAME` means it's a raw value from `.env`; a bare
     name like `claude_code` means Hermes auto-detected a sibling CLI's own
     login (e.g. `~/.claude/.credentials.json` for Claude Code, similarly
     for Codex/other coding CLIs installed on the same box).
   - `auth_type` as stored in the pool is NOT proof of what the secret
     actually is — a value sitting in an `env:VAR_NAME` source can itself be
     an OAuth token that was manually copy-pasted into `.env` under a
     generic-looking name (e.g. `ANTHROPIC_TOKEN`), not a real Console API
     key, even though it "looks like" a plain key to the user who set it.
     Don't take the variable's name as evidence of its type.
   - To tell a real provider API key from a copy-pasted OAuth/CLI-login
     token WITHOUT printing the value, check the prefix only (first ~8
     chars, never the full secret): for Anthropic, `***` is a
     Console API key; `***` (the `oat` family) is an OAuth access
     token — the same kind issued by `claude login` / Claude Code. If
     unsure, a format-only probe confirms it safely: Console keys
     authenticate via `x-api-key:*** OAuth tokens only work via
     `Authorization: *** plus an `anthropic-beta: oauth-2025-04-20`
     header. A 401 on the first and a real (even if permission-denied)
     response on the second confirms it's an OAuth session, not a key —
     and therefore tied to whatever account was logged into that OAuth
     flow, which may not be the account the user assumes.
   - To confirm identity between two entries, diff `secret_fingerprint`
     values from `~/.hermes/auth.json` (resolve the real root via
     `$HERMES_HOME` — on Windows this is under `AppData/Local/hermes`, not
     a literal path). Never cat the credential file itself or echo the key
     value back to the user; fingerprints are enough to prove "is this the
     same credential".
   - To find the backing `.env` var for a listed `env:VAR_NAME` source,
     grep by name only and redact the value before showing it:
     `grep -n "^VARNAME=" ~/.hermes/.env | sed -E 's/VARNAME=.*/VARNAME=<redacted>/'`
   - There is no API endpoint that maps a token back to an owning email —
     don't try to "look up" whose account a credential belongs to beyond
     fingerprint-matching against a known source. If the user is unsure
     which account a token belongs to, the only real resolutions are: ask
     them to recall which login produced it, or have them generate a fresh
     key from the account they confirm is correct and replace it.

3. To permanently block an unwanted credential, remove it from the pool —
   do not just lower its priority:
   `hermes auth remove <provider> <id-or-label>`
   This also sets a suppression flag so Hermes will NOT silently re-seed it
   next time it detects the sibling CLI's login again.

4. Re-run `hermes auth list` after ANY change — including changes that
   look unrelated, like `hermes auth add` for a different credential or
   `hermes auth priority` — to confirm the pool still matches intent before
   telling the user it's fixed. Don't trust the confirmation line a
   subcommand prints; re-list and read the actual resulting state.

## Pitfalls

- A credential at lower priority is a live fallback, not a disabled one —
  if the primary errors or gets rate-limited, Hermes will silently use it.
  When the user says an account must NEVER be touched, removal is the only
  guarantee; reordering priority is not sufficient.
- Never hand-edit `~/.hermes/auth.json` or `.env` to remove/add a
  credential — use `hermes auth remove`/`hermes auth add`/`hermes auth
  priority`. The CLI also updates the suppression/re-seed bookkeeping that a
  manual edit would skip.
- Never print a raw secret value (API key, OAuth token) to answer "which
  account is this" — redact to a few leading/trailing characters or compare
  `secret_fingerprint` hashes instead. The user needs to recognize the
  credential, not see it echoed in full.
- Always resolve the Hermes config root from `$HERMES_HOME`, never hardcode
  `~/.hermes` — on Windows (and in profiles) it lives elsewhere.
- Editing `.env` on disk to remove/rename a credential variable does NOT
  stop an ALREADY-RUNNING Hermes process from still using it — the process
  loaded that var into its own memory at startup and won't see the file
  edit until it restarts. `hermes auth remove` clears the persisted pool
  entry, but a later unrelated `hermes auth add`/`refresh` call in the same
  running session can re-trigger a reseed pass that reads the live
  in-memory env var (and live singleton files like
  `~/.claude/.credentials.json`) right back into the pool, silently undoing
  the removal. Always re-check `hermes auth list` after any further auth
  command in the same session, not just once after the original removal.
- `hermes auth priority <provider> <id> <N>` does not guarantee the
  requested priority — Hermes keeps manually-added credentials ahead of
  auto-seeded ones regardless of the number you pass, and prints a note
  saying so. Read that note and re-check `hermes auth list` for the actual
  effective order rather than assuming the requested N applied.
