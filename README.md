# hermes-profile

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![release](https://img.shields.io/github/v/release/acardosolima/hermes-profile)](https://github.com/acardosolima/hermes-profile/releases)

Personal Hermes Agent profile distribution — shared across your devices.

## Quick start

```bash
hermes profile install ~/path/to/hermes-profile --name master --alias
hermes profile use master
python ~/.hermes/profiles/master/agent-hooks/activate.py --profile master
cp ~/.hermes/profiles/master/.env.EXAMPLE ~/.hermes/profiles/master/.env
# fill in only the keys this device has; none are required
```

On Windows, `HERMES_HOME` is `%LOCALAPPDATA%\hermes`. The installer prints the
real path. A profile without its own `auth.json` reuses the default profile's login.

`activate.py` does two machine-local things the runtime cannot store in git:

1. Points this install at `gate-skill-manage.py` and `gate-protected-paths.py` (literal paths).
2. **Locks the built-in `default` profile** so it has no tools and only redirects
   to the named profile (`agent-hooks/lock-default-profile.py`, which then runs
   `lock_default.py`). The built-in default profile cannot be deleted; locking it
   is how a bypass session stays useless.

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

### Locked default profile

`default` is the built-in root home. It cannot be deleted and hosts the
multiplex gateway. After `activate.py`, that island is intentionally empty:

- `platform_toolsets.*` → `[]` (every platform)
- `agent.disabled_toolsets` → every toolset the runtime knows (`lock_default.py` verifies 0 enabled)
- `approvals.deny: ["*"]` (blocks any terminal even under yolo)
- `agent.max_turns: 1`
- connectors off, tool search `off`, lazy plugin installs off
- root `SOUL.md` only redirects to the named profile (**master** by default)

Re-run anytime:

```bash
python agent-hooks/activate.py --profile master
python agent-hooks/lock-default-profile.py --profile master
```

This is product friction, not OS isolation. A compromised **master** session
with shell can still edit the root config.

## Updating

The latest profile version is the newest GitHub release (`vX.Y.Z`). The version on a device is the `version` field in that profile's `distribution.yaml`. If they differ, run `hermes profile update master`. A release does not update a device by itself. `version` is bumped by `.github/workflows/release.yml` from conventional commits. Do not edit it by hand.

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
