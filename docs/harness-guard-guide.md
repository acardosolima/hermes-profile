# Guardrails (`harness-guard`)

A `harness-guard` plugin maps Hermes tool calls to the upstream policy binary
and enforces rules on risky actions.

## What it blocks

The guard checks these tools: `terminal`, `process_manage` input, `read_file`,
`write_file`, `patch`.

Blocked by default: sudo, force push, git bypass flags, writing/deleting outside
the project, writes to protected system paths, pushing directly to `main`,
staging secret files. "Ask" actions from upstream become blocks telling the agent
to ask you instead.

## What it does not inspect

These tools are intentionally unguarded. Disabling them increases risk:

- `execute_code` — runs Python the guard cannot read. Disabled in shipped config.
- `delegate_task` / `delegation` — subagents inherit unchecked toolsets.
- `skill_manage` — gated separately by the `gate-skill-manage.py` hook.
- `search_files` — no path judgment.
- Background process `write` — each call judged independently; split commands
  are not reassembled.
- `cronjob_manage` — schedules scripts. Disabled in shipped config.

## How it works

1. A `pre_tool_call` hook fires before any guarded tool executes.
2. The plugin maps the Hermes call to the upstream harness payload format.
3. The pinned upstream policy binary decides enforce/ask/block.
4. On every call the binary's sha256 is re-verified. A mismatch → block.
5. If the binary is missing, slow, or the plugin bugs out → everything guarded is blocked.

The binary ships for Linux amd64, macOS amd64/arm64, Windows amd64. Other
platforms fail closed (blocked).

## Enabling and disabling

New installs get it from `config.yaml`. An existing device that survived an older
install may still need:

```bash
hermes plugins enable harness-guard
hermes gateway restart
```

Turn off (not recommended):

```bash
hermes plugins disable harness-guard
```

## Checking it works

Nothing dangerous is executed. Commands are judged as text only.

```bash
python ~/.hermes/profiles/<profile>/plugins/harness-guard/acceptance.py
python ~/.hermes/profiles/<profile>/plugins/harness-guard/acceptance.py --live <profile>
```

In the repo: `python -m unittest discover -s tests/guard`
