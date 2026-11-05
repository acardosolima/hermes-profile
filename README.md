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

Update after a push:

```bash
hermes profile update master
```

No secrets live in this repo. `.env` / `auth.json` are excluded by `.gitignore`
and also hard-stripped by the installer regardless.
