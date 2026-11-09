# hermes-profile

Personal Hermes Agent profile distribution — shared across my own devices only.

Install:

```bash
hermes profile install ~/Documents/repositories/hermes-profile --name master --alias
hermes profile use master
cp ~/.hermes/profiles/master/.env.EXAMPLE ~/.hermes/profiles/master/.env
# fill in ONLY the keys this device actually has (see .env.EXAMPLE comments) —
# none are required; leave the rest blank
```

Per-device setup:

`config.yaml` ships with `model.provider: anthropic` / `delegation.provider:
anthropic` as a starting default only. Each device has its own provider and
key (e.g. this consultancy's Anthropic key on one machine, a personal
OpenRouter/Grok account on another, a different Anthropic key on the work
laptop). After installing, point this device at whatever it actually has:

```bash
hermes model                              # interactive picker
# or
hermes config set model.provider openrouter
hermes config set model.default <model-id>
hermes config set delegation.provider openrouter
hermes config set delegation.model <model-id>
```

### skill_manage guard hook (per-device activation)

This profile ships `agent-hooks/gate-skill-manage.py`, a `pre_tool_call`
shell hook that blocks the agent from calling `skill_manage` (create/patch/
delete a skill) — reading/discovering skills (`skill_view`, `skills_list`,
auto-loaded skills) is unaffected. `config.yaml` does NOT hardcode the
`hooks:` block pointing at it, because the hook `command` is a literal path
with no variable expansion and `HERMES_HOME` differs per device (notably:
on at least one Windows install, `HERMES_HOME` is
`%LOCALAPPDATA%\hermes`, NOT `~/.hermes` — verify with `hermes doctor`
before assuming either).

After `hermes profile install` / `hermes profile update`, point this
device's own config at its own absolute script path:

```bash
hermes config set hooks.pre_tool_call '[{"matcher": "skill_manage", "command": "python <ABSOLUTE_PATH_TO_PROFILE>/agent-hooks/gate-skill-manage.py", "timeout": 5, "fail_closed": true}]'
```

Then approve the hook. The classic CLI prompts interactively on first use;
the Desktop app and gateway never prompt (no TTY), so on those surfaces
write the allowlist entry by hand — `~/.hermes/shell-hooks-allowlist.json`
relative to the ACTUAL `HERMES_HOME` for this install, not a literal `~/.hermes`:

```json
{
  "approvals": [
    {
      "event": "pre_tool_call",
      "command": "python <ABSOLUTE_PATH_TO_PROFILE>/agent-hooks/gate-skill-manage.py"
    }
  ]
}
```

Verify with `hermes hooks doctor` (expect "allowlisted" + valid JSON on the
synthetic payload). A hook added to an already-running Desktop/gateway
session does not reliably hot-reload — open a new chat/session before
trusting the block.

### Harness skills (generated)

`skills/harness/` holds the claude-code-harness workflow skills translated for
Hermes: `harness-plan`, `harness-work`, `harness-review`, `harness-sync`,
`harness-setup`, `harness-loop`, `harness-release` and `breezing`. Do not edit
them by hand. They are generated from the upstream release pinned in
`upstream.lock` by `tools/harness_sync.py`, and CI fails if they drift.

How updates arrive:

- A daily workflow looks for a newer upstream `vX.Y.Z` release, regenerates the
  skills and opens a pull request titled `chore: bump harness to <tag>`.
- Merge it, then run `hermes profile update master` on each device.
- The installed version is in `skills/harness/GENERATED.json` (`upstream.tag`).
  That file also lists `unresolved` Claude Code variables and `missing_scripts`
  per skill, so review it on every bump.

Regenerate locally (Python 3.9+, git, no other dependencies):

```bash
python tools/harness_sync.py bump    # move upstream.lock to the newest release
python tools/harness_sync.py sync    # regenerate skills/harness
python tools/harness_sync.py check   # exit 1 if skills/harness differs from the lock
python -m unittest discover -s tools/tests -t tools
```

Limits:

- Claude Code hooks and agent definitions are not translated. Guardrails are
  enforced by the `harness-guard` plugin below, not by the skills.
- `hermes profile update` replaces each shipped skill directory, but does not
  delete a skill that was dropped from the profile. Remove those by hand.
- The bundled helper scripts were not run through Hermes, and 38 shipped files
  mention the upstream `bin/harness` program, which is not shipped as a skill
  file. Treat scripts as untested until you run them.
- What was observed on a live Hermes and what was only read from its source is
  tagged in `docs/hermes-skill-contract.md`.

### Guardrails (`harness-guard` plugin)

The harness blocks risky actions on Claude Code (sudo, force push, bypassing git
hooks or signing, reading or staging secret files, deletes outside the project,
writes to protected paths, direct pushes to `main`). Hermes has no such layer, so
`plugins/harness-guard/` adds one. It does not reimplement the rules: it maps
Hermes `terminal`, `process_manage` input, `read_file`, `write_file` and `patch`
calls (including patch-file mode) to the harness format and asks the pinned
upstream policy binary for the verdict. The binary is downloaded from the pinned
upstream commit and used only if its sha256 matches
`plugins/harness-guard/binaries.lock.json`. The hash is checked on every call.

Enable it:

- New installs get it from `config.yaml`.
- An existing device keeps its own `config.yaml` on update, so run once:
  `hermes plugins enable harness-guard`.
- After the plugin files change on an already-enabled profile, run
  `hermes gateway restart` before trusting the new version. During testing, a
  running profile kept the earlier version of the plugin after an update, and
  Hermes prints that command after an install.

Behavior:

- A denied action is blocked and the agent sees the reason.
- Actions the harness would confirm with a human ("ask") are blocked too, with a
  message telling the agent to ask you. Hermes' approval gate is not used,
  because its default `smart` mode lets a model approve on its own.
- A call the guard cannot judge is blocked: missing or mistyped arguments, a patch
  that names no file, `~user` paths, an unknown working directory, or a working
  directory that is `/`, your home directory or a system location. Relative paths
  and `~/` are resolved before judging, and a terminal `workdir` is honored.
- If the binary is missing, fails its hash check or is too slow, guarded tools
  are blocked. A bug in the plugin blocks the call as well.
- The binary runs with a scrubbed environment and with upstream's strictest
  delete and push policy, so a project file cannot loosen them.
- The guard has no settings. `hermes plugins disable harness-guard` is the only
  off switch. As a best-effort text filter, commands and file paths that mention
  the guard's files, its lock, `harness.toml`, `~/.hermes/config.yaml`, the Hermes
  plugin directory (`~`, `$HOME` and `$HERMES_HOME` spellings are resolved), or the
  `hermes plugins|config|profile|gateway|hooks` commands are refused. File
  contents are not checked. This is not a boundary: `execute_code` and shell
  indirection can still reach those files. It also means an agent working in
  this repo cannot edit the guard; disable the plugin or edit it outside Hermes.

Check that it works on a machine (nothing dangerous is executed; commands are
judged as text, and the live part only runs harmless commands):

```bash
python ~/.hermes/profiles/<profile>/plugins/harness-guard/acceptance.py            # offline cases
python ~/.hermes/profiles/<profile>/plugins/harness-guard/acceptance.py --live <profile>
```

In the repo: `python -m unittest discover -s tests/guard`. CI runs it with the
real binary on Linux, macOS and Windows. Every upstream rule must be classified
in `tests/guard/rules.json`, so a harness release that adds a rule fails the
bump workflow until someone decides what to do with it.

Supported platforms are the ones upstream ships a binary for: Linux amd64,
macOS amd64 and arm64, Windows amd64. Anywhere else every guarded call is blocked.

Known gaps, so you can judge the risk:

- `execute_code` runs Python the guard cannot read. The `code_execution` toolset
  is enabled in this profile's shipped `config.yaml`, so a model can delete files
  or run commands through it unseen. Turn that toolset off if you rely on the
  guard. This is the largest gap.
- `delegate_task` children, `skill_manage` and `search_files` are not inspected,
  and whether hooks fire inside delegated children is unverified.
- The `cronjob_manage` tool can schedule scripts. It is disabled in this
  profile's `config.yaml`; keep it disabled.
- Reading a secret file with `read_file` is only a warning upstream, so the
  guard allows it. Hermes itself refuses dotenv files, and `cat` of one is
  blocked by the guard.
- Writes to the OS temp directory are allowed, as upstream allows them.
- Deletes the policy can prove are inside the project are allowed. With the
  strict policy the guard forces, anything it cannot prove (a relative target
  after `cd`, a glob, `..`) is an "ask", which the guard blocks. A delete from
  `/`, your home directory or a system location is blocked.
- Input sent to a background process is judged one call at a time, so a command
  split across several `write` calls is not reassembled.
- The binary's hash is checked and the binary is run as two separate steps. A
  process that can write to the plugin cache could race them.
- The guard judges each call on its own. A shell that has changed directory
  carries that directory into the next call, and the guard only checks that it is
  not `/`, home or a system location.
- On Windows, upstream's check that stops `git add` of a secret file does not
  fire, because its pattern needs a `/` before the file name and Windows paths use
  backslashes. The test table pins this as a known gap.
- Verified live on Linux only. macOS and Windows are covered by the offline
  conformance tests in CI, not by a live Hermes session.

Update after a push:

```bash
hermes profile update master
```

No secrets live in this repo. `.env` / `auth.json` are excluded by `.gitignore`
and also hard-stripped by the installer regardless.
