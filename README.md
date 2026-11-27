# hermes-profile

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Personal Hermes Agent profile distribution — shared across your devices.

## Quick start

```bash
hermes profile install ~/path/to/hermes-profile --name master --alias
hermes profile use master
cp ~/.hermes/profiles/master/.env.EXAMPLE ~/.hermes/profiles/master/.env
# fill in only the keys this device has; none are required
```

On Windows, `HERMES_HOME` is `%LOCALAPPDATA%\hermes`. The installer prints the
real path. A profile without its own `auth.json` reuses the default profile's login.

## Configuration

`config.yaml` ships with Anthropic as a starting default. Point each device at
its own provider/key after install:

```bash
hermes model                              # interactive picker
```

Per-device overrides to `config.yaml` survive `hermes profile update`.

## What this ships

| Section | Source | Editable? |
|---------|--------|-----------|
| `config.yaml`, `SOUL.md` | From the repo | Yes — per-device overrides on every install |
| `skills/harness/` | Generated from upstream lock | No — regenerate via `tools/harness_sync.py` |
| `plugins/harness-guard/` | Pinned binary + plugin code | No — rule updates come from upstream binary |
| All other skills | Distribution from `distribution.yaml` | No — synced automatically |

## Guardrails

A `harness-guard` plugin maps Hermes tool calls to the upstream policy binary
and enforces rules: no sudo, no rm -rf without confirm, secret file protection,
git bypass prevention, etc. See [`docs/harness-guard-guide.md`](docs/harness-guard-guide.md)
for how it works, how to check it, and known gaps.

The guard blocks `skill_manage`, `execute_code`, `cronjob_manage`, and messaging
platform terminal access by default. These can be re-enabled per-device but
require care.

## Updating

When the upstream harness is updated, a CI workflow opens a PR. Merge it, then run:

```bash
hermes profile update master
```

Regenerate locally (Python 3.9+, git):

```bash
python tools/harness_sync.py bump    # pick newest upstream release
python tools/harness_sync.py sync    # regenerate skills/harness
python tools/harness_sync.py check   # verify nothing drifted
python -m unittest discover -s tools/tests -t tools
```
