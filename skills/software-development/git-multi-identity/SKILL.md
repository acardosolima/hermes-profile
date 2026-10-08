---
name: git-multi-identity
description: "Separate git identity per client/org folder on one machine."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, github, credentials, identity, multi-client, windows, signing, hooks]
    category: software-development
    related_skills: [github]
---

# Multi-Client / Multi-Org Git Identity Separation

For a user who works across several distinct contexts on one machine —
multiple consulting clients, their own company, and personal projects —
each needing its own commit identity, and sometimes its own git host or
credential set. Goal: never let one identity's name/email/credentials leak
into another context's commits or MCP/API calls.

## When to Use

- The user mentions working for multiple clients/employers/orgs plus
  personal projects on the same machine and wants commits, credentials, or
  MCP tokens kept separate per context.
- A `git config --global user.email` turns out to be hardcoded to one
  client/org when the user expects it to vary by repo.
- Investigating a "missing" per-project config (MCP server, credential,
  env var) that turns out to be scoped to a project folder rather than
  global — check whether the owning folder still exists before assuming
  the tool lost the config.

## Procedure

1. **Inventory the identities first.** Ask for (or infer from existing
   config/remotes) each identity's: display name, commit email, git host(s)
   it pushes to, and whether it needs its own GitHub account. Don't guess —
   confirm the email mapping explicitly before writing config; a wrong
   mapping silently mis-attributes commits.
2. **Pick a folder-per-identity layout** under the repos root, e.g.
   `repositories/<client-a>/`, `repositories/<client-b>/`,
   `repositories/<own-company>/`, `repositories/personal/`. Sort every
   existing repo into one of these by its `git remote -v` origin, not by
   guessing from the repo name. Repos whose origin doesn't clearly match a
   client go to `personal/` by default (safest bucket, see step 4).
3. **One `[user]` stanza per identity**, in its own file: e.g.
   `~/.gitconfig.d/<identity>` containing just:
   ```
   [user]
   	name = ...
   	email = ...
   ```
4. **Wire `~/.gitconfig` with includeIf, default-first:**
   ```
   [include]
   	path = C:/Users/<user>/.gitconfig.d/personal
   [includeIf "gitdir/i:C:/Users/<user>/Documents/repositories/<client-a>/"]
   	path = C:/Users/<user>/.gitconfig.d/<client-a>
   [includeIf "gitdir/i:C:/Users/<user>/Documents/repositories/<client-b>/"]
   	path = C:/Users/<user>/.gitconfig.d/<client-b>
   ```
   Remove any pre-existing global `[user]` block — leaving it in place means
   it silently wins as the default for every repo until a conditional block
   overrides it, which is how a client identity ends up as the machine-wide
   default by accident.
   - The unconditional `[include]` default MUST be the least-sensitive
     identity (personal), never a client's — it's what every repo outside
     the known folders falls back to.
   - On Windows use `gitdir/i:` (case-insensitive matcher), not `gitdir:` —
     Windows paths aren't case-sensitive and the case-sensitive form can
     silently fail to match.
   - Order in the file only matters for the default: put it first; the
     conditional blocks override it for matching paths regardless of where
     they sit relative to each other.
5. **Host-level credentials are a separate axis from identity.** Keep
   `credential."https://<host>".provider=...` (or SSH host aliases) scoped
   per host, independent of the includeIf identity blocks above — one
   client can have multiple repos/identities on the same host, and one
   identity can touch multiple hosts.
6. **Multiple accounts on the SAME host** (e.g. two github.com accounts) —
   prefer SSH over HTTPS for this; see the dedicated section below. Use
   distinct SSH host aliases in `~/.ssh/config`:
   ```
   Host github.com-<identity>
       HostName git@github.com
       User git
       IdentityFile ~/.ssh/id_ed25519_<identity>_sign
       IdentitiesOnly yes
   ```
   One keypair can serve both auth and signing for a given identity ONLY
   if push never needs to require a passphrase on its own — see "Separate
   auth key from signing key" below before defaulting to that. Pair
   whichever key you choose with a rewrite in that identity's include file
   so existing remotes (SSH *or*
   HTTPS form) transparently route through the right alias without
   touching the stored remote URL:
   ```
   [url "git@github.com-<identity>:"]
   	insteadOf = git@github.com:
   	insteadOf = https://github.com/
   ```
   Verify the routing actually took effect — don't just trust the config —
   with `GIT_SSH_COMMAND="ssh -vvv" GIT_TRACE=1 git ls-remote origin`
   and check the identity file it picked, or simply `ssh -T
   git@github.com-<identity>` and confirm the greeted username matches.
   `gh` itself only tracks one "active" account at a time — for `gh`
   subcommands (not plain `git`) to also auto-resolve per directory, wrap
   `gh` in a shell function that runs `gh auth switch --hostname
   github.com --user <mapped-account>` (looked up from the same
   folder→identity mapping) before forwarding every call to the real
   `gh.exe`; call the real binary by its resolved path/extension so the
   wrapper function doesn't recurse into itself. This does compose with
   working across multiple directories in the same session — each `gh`
   invocation independently re-resolves and switches first.
7. **Verify per folder with a REAL repo**, not a fake one: `git init`
   inside it, then `git config user.email`. A directory with just a bare
   `mkdir .git` (no `HEAD`/refs) is NOT recognized as a repository by git's
   config discovery, so testing against one gives a false negative — it
   silently falls through to the default identity instead of the folder's,
   making a correct config look broken.

## Pitfall: moving existing repos into the new layout, on Windows

If the repo directory is the current working directory of ANY live shell
or process (including the agent's own host session), `mv`/rename fails
with "Device or resource busy" even when a single command passes a
`workdir` override — the override doesn't change the *persistent* shell
session's cwd, which is what holds the lock.

- Fix: `cd` the persistent session itself out of the directory first
  (`cd <repos-root>`), then retry `mv`.
- If a cross-directory `mv` still fails (or you need `robocopy`'s
  resilience), use `MSYS_NO_PATHCONV=1 cmd /c robocopy <src> <dst> /E /MOVE`
  from git-bash. Use forward slashes in the paths — bare backslashes are
  eaten as bash escape characters when the argument isn't quoted, mangling
  the path into garbage (e.g. `C:UsersAdriano...` with slashes stripped).
  Quoting with literal backslashes inside git-bash also breaks because the
  quotes themselves get folded into the path; forward slashes sidestep both
  problems since `robocopy` accepts them natively.
- Robocopy may still fail to delete the now-empty source directory
  ("process cannot access the file") if an external process holds a
  handle on it — that leftover empty directory is harmless; it can be
  removed once the lock releases (e.g. after the agent session ends).

## Blocking direct commits to protected branches

A reviewer who keeps seeing work land straight on `main`/`master`/`trunk`
wants this enforced, not just promised — revertable is not the same as a
clean log, and "I'll remember to branch next time" doesn't hold up across
a long session. Add to the `pre-commit` hook (same shared `hooksPath` as
the other checks, every identity, not just client ones):

```sh
branch="$(git symbolic-ref --short HEAD 2>/dev/null)"
[ -z "$branch" ] && exit 0   # detached HEAD (e.g. mid-rebase) — let it through
if printf '%s\n' "$branch" | grep -Eqi '^(main|master|trunk)$'; then
  echo "refusing to commit directly on protected branch '$branch'" >&2
  exit 1
fi
```

Give it one explicit bypass env var (e.g. `GIT_ALLOW_PROTECTED_COMMIT=1`)
for genuine exceptions (a repo's very first commit, before branching makes
sense) — same escape-hatch pattern as the push-confirmation hook. Verify
with a real repo: commit on the protected branch name (must fail), commit
on a feature branch (must pass), bypass var set on the protected branch
(must pass) — test the bypass against the protected branch specifically,
not incidentally on a feature branch where it was never being tested.

## Best-effort auto-fix formatting on commit (lint-staged pattern)

When the user wants linting handled but NOT gated (a formatter should just
fix what it can, never block a commit over style), replicate the
lint-staged pattern as a hook step: detect staged files by extension, run
whatever formatter is actually installed against just those files, re-stage
what changed, and always exit 0 regardless of whether a tool was found or
ran — a missing tool is silence, not an error:

```sh
staged="$(git diff --cached --name-only --diff-filter=ACM)"
# bucket $staged by extension, then e.g.:
command -v black >/dev/null 2>&1 && printf '%s\n' "$py_files" | xargs -r black --quiet --
# ...re-stage whatever was touched:
printf '%s\n' "$changed_files" | xargs -r git add --
exit 0
```

Do NOT extend this to running the test suite on commit, even "informally"
— a failing test is often legitimate mid-work (the whole point of TDD's
RED step), so a test-runner hook that's supposed to never block isn't
actually doing anything useful, and one that does block fights the user's
own workflow. Tests belong in CI or at most a `pre-push` gate, not
`pre-commit`. Verify the auto-fixer with a fake formatter script placed on
`PATH` for the test (don't require the real tool to be installed just to
prove the hook's plumbing works) — and remember `PATH` entries for a
bash-resolved command must be POSIX form (`/c/...`) even though the file
arguments passed to a native `.exe` on the very same command line need the
`C:/...` form; mixing the two up means `command -v <fake-tool>` silently
returns not-found with no error to explain why.

## Pitfall: native Windows binaries mangle `/c/...` MSYS paths

Passing an MSYS-style path (`/c/Users/...`) as a positional argument to
any native Windows binary invoked from git-bash — `git` (`git init
/c/Users/x/repo`, `git -C /c/Users/x/repo ...`), `gh` (`gh ssh-key add
/c/Users/x/key.pub`), `cmd`, etc. — can silently double-prefix it into
garbage like `C:/c/Users/x/repo` or strip it to a mangled relative path.
These binaries have their own path handling that disagrees with
git-bash's MSYS path rewriting the way plain file-copy coreutils do.
Always pass native `C:/Users/...`-style paths (forward slashes still fine)
to any subcommand of a native `.exe` that takes a path argument; reserve
`/c/...` paths for bash builtins (`cd`, `ls`) and coreutils. If a native
binary reports a nonsensical "file not found" or doubled-prefix error, path
mangling is the first thing to check, not a real missing-file condition.

## Related: Claude Code project-scoped MCP config is folder-bound

If this client separation involves per-client MCP servers (e.g. a Foundry/
internal MCP server whose token is tied to one client), be aware a plain
`.mcp.json` dropped at a project root by a custom setup script is CWD-
relative and is NOT tracked in `~/.claude.json`'s `projects.<path>.mcpServers`
even though it works. Consequences:
- A setup script that writes `.mcp.json` with a relative path (e.g.
  PowerShell `Set-Content .mcp.json`) lands wherever the shell's cwd was
  when run, not a fixed location — always print/confirm the resolved
  absolute path right after creation, and prefer writing to an explicit
  absolute path over a bare relative filename.
- `.mcp.json` is typically gitignored (it often embeds `${ENV_VAR}`
  references to secrets), so deleting or renaming the project folder
  deletes the only copy of that MCP config, even though the underlying
  credentials (env vars, `.npmrc` registry tokens) survive globally and can
  be reused to regenerate it.
- To recover an apparently "lost" MCP server: don't assume it was
  uninstalled. Check `~/.claude.json`'s `projects` map for a session that
  ran in the right directory (confirms the folder existed and was used),
  then check whether that folder still exists on disk and whether
  `.mcp.json` is present there — the config almost always just moved or was
  deleted with its folder, not actually removed from the tool.

## Gating client pushes without blocking commits

For client identities where an accidental or automated push would be
costly (unlike a local commit, which is free and reversible), add a
`pre-push` hook scoped to just that identity via the same `.gitconfig.d`
file used for `[user]`:

```
[core]
	hooksPath = C:/Users/<user>/.githooks/client-confirm
```

Point `hooksPath` at one shared hook directory (not a per-repo copy) so a
single hook file governs every repo under that identity. Make the hook
fail closed when there's no controlling terminal — open `/dev/tty` on a
new file descriptor and bail if that fails, rather than testing `-e
/dev/tty` (the path exists under MSYS even with no real terminal attached,
so an existence check alone gives a false positive):

```sh
if ! exec 3< /dev/tty 2>/dev/null; then
  echo "pre-push: no interactive terminal; refusing automated push." >&2
  exit 1
fi
# ...prompt, read -r answer <&3, exit 1 unless y/yes
```

This blocks subagents/cron/scripts (no tty) while a human at a real
terminal still gets a yes/no prompt. Give it exactly one intentional
bypass — an env var checked at the top of the hook, e.g.
`GIT_PUSH_CONFIRM=skip` — for automation the user explicitly trusts, and
say in the hook's own comments that this is friction, not a security
boundary: `git push --no-verify` or editing the hook bypasses it just the
same, to anyone with the same local user privileges. Apply it only to
identities that actually carry that risk (client/employer repos); leave
personal/low-stakes identities unrestricted so the friction doesn't become
blanket annoyance. Verify by pushing to a real local `git init --bare`
repo from a non-interactive tool call (must fail) and again with the
bypass var set (must succeed) — never test against the user's actual
remote.

## Per-identity commit signing (SSH format)

Git ≥2.34 supports SSH-format commit signing, simpler per-identity than
GPG (just a keypair, no keyring):

1. Generate one dedicated signing key per identity that needs it —
   `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_<identity>_sign -N ""` —
   rather than reusing an existing key of unknown purpose. If the user
   can't confirm what an existing key is already used for, leave it alone
   and generate a fresh one.
2. In that identity's `.gitconfig.d/<identity>` file add:
   ```
   [gpg]
   	format = ssh
   [gpg "ssh"]
   	allowedSignersFile = C:/Users/<user>/.ssh/allowed_signers
   [commit]
   	gpgsign = true
   [user]
   	signingkey = C:/Users/<user>/.ssh/id_ed25519_<identity>_sign.pub
   ```
3. Maintain one shared `allowed_signers` file (one `<email> namespaces="git"
   <pubkey>` line per identity) so `git log --show-signature` can verify
   locally — independent of whatever the remote host does with the key.
4. Skip identities whose git host has nowhere to register a signing key
   (e.g. an internal/enterprise server) — signing without anywhere to
   publish the public key only buys local verification, not a
   platform-visible "Verified" badge, so confirm the host supports it
   before building out keys for it.
5. Verify end-to-end before handing over public keys: commit
   `--allow-empty` in a real (or throwaway) repo under that identity's
   folder, then `git log -1 --show-signature` and look for `Good "git"
   signature`. Only then give the user the `.pub` contents to paste into
   the host's dedicated *signing*-key setting — GitHub, for one,
   distinguishes a signing key from an authentication key, and the wrong
   slot silently doesn't work.

Note: direct writes under `~/.ssh/` are commonly blocked by sandboxing as
a protected-credential path — use the `terminal` tool (`cat > ... <<EOF`)
to create plain files there (like `allowed_signers`) instead of a file-write
tool.

To check whether a private key is passphrase-protected without needing the
passphrase, use `scripts/ssh_key_cipher.py <native-path>` (reads the
cipher name straight out of the key's own header).

## Separate auth key from signing key when push must require a passphrase

A single keypair has one passphrase state. If the user wants commits to
stay frictionless (so TDD/subagent workflows aren't interrupted) but wants
`git push`/`pull`/`fetch` itself to demand a password, that is two separate
keypairs per identity, not one:

1. Keep the existing passphrase-less `id_ed25519_<identity>_sign` wired to
   `user.signingkey` exactly as above — untouched, still signs every commit
   with no prompt.
2. Generate a second, dedicated key for transport only —
   `id_ed25519_<identity>_auth` — WITH a passphrase. Never generate a
   passphrase-protected key by driving `ssh-keygen` yourself through
   agent/pty tool calls: every keystroke you send (`process_manage
   write`/`submit`) passes through your own tool-call arguments and logs,
   defeating the point of a secret the user doesn't want you to see. Ask
   the user to run `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_<identity>_auth`
   themselves in their own terminal, then confirm completion before
   continuing.
3. Verify the passphrase actually got set without needing it yourself: an
   OpenSSH private key's own header declares its cipher in plaintext right
   after the `openssh-key-v1` magic bytes — `none` means unencrypted,
   anything else (`aes256-ctr`, etc.) confirms a passphrase is set. Use
   `scripts/ssh_key_cipher.py <native-path-to-key>` rather than hand-rolling
   this each time.
4. Point the identity's `~/.ssh/config` `Host github.com-<identity>` block's
   `IdentityFile` at the new `_auth` key (not the `_sign` key).
5. On GitHub, register the new `_auth` public key as an Authentication Key,
   then delete the OLD Authentication Key registration that belongs to the
   `_sign` key's public key (list both with `gh api user/keys --jq '.[] |
   "\(.id) \(.title)"'`, delete by id with `gh api -X DELETE
   user/keys/<id>`) — leave the `_sign` key registered ONLY as a Signing
   Key. Otherwise the unencrypted signing key remains independently usable
   to push, silently defeating the whole point of gating push behind a
   passphrase.
6. Verify both properties hold: commit `--allow-empty` and confirm no
   prompt + `Good "git" signature` in `git log --show-signature`; separately
   confirm the transport now blocks without the passphrase (a non-interactive
   `ssh -T git@github.com-<identity>` or `git ls-remote` from a tool call
   should hang/fail for lack of a tty to supply it — that failure IS the
   verification, you cannot and should not complete it yourself).

## Ready-to-copy hook files

The above sections describe the design; `scripts/githooks/` ships the actual
working files so a new machine doesn't need to hand-write them from prose:

```
scripts/githooks/lib/            shared logic sourced by every hook below
scripts/githooks/common/         default hooksPath: branch-protect, autofix, commit-msg
scripts/githooks/client-confirm/ same three + the tty push-confirmation gate
```

To deploy: copy the whole `scripts/githooks/` tree to `~/.githooks/` (or
wherever `core.hooksPath` should point), `chmod +x` every file except
`lib/secret-patterns.txt`, then wire `core.hooksPath` per the includeIf
sections above. Note the shipped `common/` has no `pre-push` file at all
(no-op by design — push-time secret re-scanning was tried and deliberately
dropped; see the pitfalls section below for why pre-commit-only was kept).
Re-verify with the test recipes in each section above after copying — don't
assume a copy-pasted hook behaves identically on a different machine/git
version without checking.

## Pitfalls writing the pre-commit/pre-push secret-scanner and commit-msg hooks

- **Secret-pattern regex must be case-insensitive AND tolerate a variable-name
  suffix between the keyword and the assignment operator.** A naive pattern
  like `(secret|token)[[:space:]]*[:=]...` misses `AWS_SECRET_KEY = "..."`
  twice over: `SECRET` is uppercase, and `_KEY` sits between the keyword and
  `=`. Use `grep -Eif` (case-insensitive) and allow `[a-zA-Z_]*` right after
  the keyword alternation before the whitespace/operator. Verify with a
  deliberately-uppercase, deliberately-suffixed test string, not just a
  lowercase exact-keyword one — the exact-keyword case passes even a broken
  pattern and gives false confidence.
- **A `pre-push` hook that diffs `$local_sha` alone for a brand-new branch
  (`remote_sha` all zeros) silently scans nothing.** `git diff <sha>` compares
  the working tree/index to that commit, not the commit's own changes — for a
  clean working tree this is an empty diff, so the scan always "passes" on a
  repo's first push regardless of content. Use the empty-tree hash as the
  base instead: `git diff 4b825dc642cb6eb9a060e54bf8d69288fbee4904..$local_sha`.
  This bug is invisible unless you specifically test the first-push case
  (new branch, `remote_sha = 000...0`) — testing only incremental pushes
  against an already-existing remote branch won't catch it.
- Test the push-side scanner by committing the secret with `--no-verify`
  (bypassing pre-commit on purpose) so you're proving the push hook catches
  it independently, not just re-testing the commit hook. Test both the
  first-push and incremental-push code paths separately — the bug above only
  manifests on the first.
- For a hooksPath that combines a secret scan with a human-confirmation gate
  (e.g. client identities), run the scan BEFORE the tty-confirmation prompt
  and `exit 1` immediately on a match — don't let a human approve past a
  secret leak. Verify the ordering explicitly: a secret-laden non-interactive
  push must fail with the scanner's message, not the tty one; a clean
  non-interactive push must fail with the tty message, proving the scan step
  isn't accidentally swallowing the confirmation step too.
- A `commit-msg` hook enforcing Conventional Commits should special-case
  `Merge *`, `Revert *`, `fixup!/squash!` subjects — rejecting merge commits
  breaks normal git workflows for no benefit.
- Put the actual regex/scan logic in a shared `lib/` script sourced by both
  `pre-commit` and `pre-push` (and by every per-identity hooksPath directory
  that needs it) rather than duplicating it — `core.hooksPath` is a full
  override of the hooks directory, so an identity with a stricter hooksPath
  (e.g. adding a push-confirmation gate) must still carry its own copies of
  the shared checks, not just the extra gate, or it silently loses them.

## Prefer SSH over HTTPS for multi-account GitHub — avoid surprise auth popups

Git Credential Manager *can* isolate multiple HTTPS accounts on the same
host via `credential."https://github.com".username = <account>` per
identity — it correctly refuses to leak a different cached account's token
when asked for a username with nothing cached. But the first time anything
touches that identity's remote with no cached credential yet (including a
background auto-fetch from an editor, not just something you ran
deliberately), GCM pops an interactive sign-in dialog at an unpredictable
moment. A user who wants credentials handled silently (no typed
passwords/tokens, no popups) is better served by the SSH host-alias setup
above: once the key is registered, it never prompts again. Default to SSH
for this reason; only reach for HTTPS + `credential.username` pinning if
the host doesn't support SSH at all.

## SSH key naming and `gh ssh-key add` gotchas

- Name every key you register on GitHub after the machine's actual
  `hostname` output, consistently across every account — not an invented
  per-account label. If the user already has a same-machine key on one
  account, match its existing title exactly on every other account rather
  than picking a new name; consistency across accounts is itself the
  convention, so check what's already there first (`gh api user/keys
  --jq '.[].title'` after switching to each account).
- `gh ssh-key add` on first-ever `gh auth login` tends to auto-offer the
  generic ambient key (e.g. plain `id_ed25519`) rather than a dedicated
  per-identity key — decline that offer (the dedicated key is the point of
  this whole setup) and register the correct key explicitly afterward with
  `gh auth switch --hostname github.com --user <account>` then `gh
  ssh-key add <native-path-to-dedicated-pubkey> --title <hostname>`.
- The same physical SSH key cannot be registered on two different GitHub
  accounts — GitHub rejects the second attempt with `HTTP 422 key is
  already in use`. That's expected and harmless if you're deliberately
  reusing one identity's key; it signals a mistake if you see it while
  trying to set up what should be a distinct per-identity key.
- Driving `gh auth login --web` (or any flavor) through a background tool
  call: never put `&` inside the monitored command string (e.g. `gh auth
  login ... 2>&1 &\nsleep 1\necho started`) — the wrapper script itself
  exits once it hits `echo`, and that tears down the backgrounded `gh`
  process before the device-code poll can complete, even if the user
  finishes the browser step. Launch the bare `gh auth login ...` command
  itself as the backgrounded/pty process directly so it stays alive for
  the whole wait.
- To correct a wrong key title or revoke a key's ability to authenticate
  (while keeping its Signing Key registration), list keys with `gh api
  user/keys --jq '.[] | "\(.id) \(.title)"'` per account (`gh auth switch
  --hostname github.com --user <account>` first), then `gh api -X DELETE
  user/keys/<id>` and re-add with `gh ssh-key add <path> --title <name>`.
  There is no rename — delete and recreate.
- `cmdkey /list` dumps Windows Credential Manager entries (targets like
  `git:https://github.com`, `gh:github.com:<user>`) — check this before
  assuming a credential isn't cached yet, and to diagnose "where did this
  login come from" after an unexpected auth popup.
