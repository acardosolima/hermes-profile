# Hermes skill and hook contract

Facts the harness sync tool and guard depend on. Each claim carries a tag:

- `source-read`: read from the Hermes source tree, not executed.
- `observed`: seen running on a device.
- `unknown`: not established.

Hermes version for every `source-read` claim: v0.22.6.

## Skills

| Claim | Tag |
|-------|-----|
| A skill is a directory with `SKILL.md`. `name` falls back to the directory name. | source-read |
| Frontmatter reads `name`, `description`, `platforms`, `version` and `metadata.hermes`. Name and description are length-capped (`MAX_NAME_LENGTH`, `MAX_DESCRIPTION_LENGTH`). | source-read |
| Extra frontmatter keys (for example `allowed-tools`, `kind`) are tolerated. | unknown |
| No `${...}` variable is substituted in skill text. A footer note tells the agent to resolve relative paths against the skill's absolute directory. | source-read |
| Support directories next to `SKILL.md` (for example `references/`, `scripts/`) are recognised as skill support paths. | source-read |
| `hermes profile install` and `update` copy nested skill files. A directory inside a skill, such as `scripts/`, belongs to that skill. | observed (v0.22.6): all 171 generated files installed, `references/` and `scripts/` included |
| Distributions are copied with `shutil.copytree` and `copy2`, which keep file modes. | observed (v0.22.6): 120 of 120 executable files stayed executable |
| A distribution containing any symlink is rejected. | source-read |
| `skills/<category>/` directories are merged per authored root. Each skill directory is replaced whole, so files upstream removed from a skill disappear. A skill dropped from the profile is not deleted from an existing device. | observed (v0.22.6): a removed reference file disappeared, a new one appeared, a dropped skill stayed |
| `hermes skills list` shows the installed skills under the `harness` category as enabled. | observed (v0.22.6): all 8 listed |
| `hermes profile update` states that `config.yaml` is preserved unless `--force-config` is given. | observed (v0.22.6) |
| `hermes profile install` and `update` ask for confirmation and cancel without a TTY unless `-y` is passed. | observed (v0.22.6) |

Consequence for translation: rewrite `${CLAUDE_SKILL_DIR}` and plugin-root
lookups into paths relative to the skill directory, and bundle referenced
scripts inside the skill directory.

## Hooks

| Claim | Tag |
|-------|-----|
| `pre_tool_call` is a valid event. Valid events also include `post_tool_call`, `pre_llm_call`, `on_session_start`, `on_session_end`, `subagent_start`, `subagent_stop`, `pre_verify` and others. | source-read |
| Shell hooks are configured under `hooks:` in `config.yaml`. Each `(event, command)` pair needs allowlist consent in `shell-hooks-allowlist.json`. | source-read |
| Shell hook stdin is JSON with `hook_event_name`, `tool_name`, `session_id` and tool arguments. The exact key for arguments (`args` or `tool_input`) is inconsistent between the module docstring and its code. | unknown |
| Exit code 2 blocks a `pre_tool_call`. Stdout JSON `{"action":"block","message":...}` or `{"decision":"block","reason":...}` also blocks. | source-read |
| A hook with `fail_closed: true` blocks on timeout or unparseable output, for blocking-capable events only. | source-read |
| A plugin can call `ctx.register_hook("pre_tool_call", callback)` from `register(ctx)`. A callback that exceeds `plugins.hook_callback_timeout` fails closed. | source-read |
| Plugins are opt-in through `plugins.enabled` in `config.yaml`. This profile already ships `plugins.enabled: [homeassistant]`. | source-read |
| A plugin hook needs no allowlist consent and no per-device command path. | unknown |
| `hermes profile update` keeps an existing device's `config.yaml` unless `--force-config` is given, so a new `plugins.enabled` entry does not reach existing devices by update. | source-read |

Consequence for the guard: a plugin shipped under `plugins/` registers its
hook without a command path or an allowlist step. It still has to be enabled
once per existing device, because `config.yaml` is not replaced on update.
This is the preferred design, pending the `unknown` rows above.

## Tool names seen in Hermes payloads

`terminal` (argument `command`), `read_file`, `write_file`, `skill_manage`,
`delegate_task`, `clarify`, `cronjob`, `execute_code`, `todo`, `search_files`.
Source: the default `hermes hooks test` payloads and the bundled hermes-agent
skill references.

## Claude Code to Hermes tool mapping

| Claude Code | Hermes | Status |
|-------------|--------|--------|
| `Bash` | `terminal` | mapped |
| `Read` | `read_file` | mapped |
| `Write`, `Edit` | `write_file`, `patch` | mapped, `patch` argument shape unknown |
| `AskUserQuestion` | `clarify` | mapped |
| `Agent`, `Task` | `delegate_task` | degraded, concurrency limits differ |
| `ScheduleWakeup` | `cronjob` | degraded, scheduling model differs |
| `WebSearch` | `web` toolset | mapped, toolset must be enabled |
| `TeamCreate`, hook-driven monitors | none | unsupported |

## Runtime verification

Run on Hermes v0.22.6 (2026.9.24), Linux, with a scratch profile installed
from a local clone of this repo and deleted afterwards. Observed: install,
skill discovery and the update path (rows above). Not observed: running a
harness skill through a model, slash command invocation, extra frontmatter
keys (the generator drops them), and plugin hooks. Those rows stay `unknown`
until exercised with a configured model provider.
