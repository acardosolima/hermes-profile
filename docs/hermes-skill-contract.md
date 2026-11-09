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
| `hermes -z "/harness-plan sync"` expands the slash command into a skill invocation. The model then made `search_files`, `terminal` and `skill_view` calls, and `skill_view` loaded the bundled `references/sync.md`. | observed (v0.22.6, model `claude-sonnet-5`) |
| `hermes -z "/harness-review ..."` ran to a structured review result and found a real defect (division by zero on an empty list) in a throwaway commit. | observed (v0.22.6, model `claude-sonnet-5`) |
| Upstream skill text is largely Japanese and some output text refers to Claude (for example a closing line saying Claude will summarize the result). The translator does not rewrite prose. | observed (v0.22.6) |
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
| A plugin hook needs no allowlist consent and no per-device command path. `hermes plugins enable <name>` is the only activation step. | observed (v0.22.6) |
| `hermes profile update` keeps an existing device's `config.yaml` unless `--force-config` is given, so a new `plugins.enabled` entry does not reach existing devices by update. | source-read |
| A plugin `pre_tool_call` callback receives `tool_name` (for example `terminal`), `args` (for example `{"command": ...}`), `session_id`, `task_id`, `tool_call_id` and `turn_id`. | observed (v0.22.6) |
| Returning `{"action": "block", "message": ...}` stops the call, and the model receives the message as an error result. The command does not run. | observed (v0.22.6) |
| The hook runs with the Hermes install directory as its working directory, not the project directory, and its `TERMINAL_CWD` environment value belongs to the shared gateway. The session directory is found where the terminal tool finds it: the per-session record (it follows `cd`, and its keys are profile-qualified, ending in the task id), the live terminal environment, then on the first call `terminal_tool._tenv("TERMINAL_CWD")` or `_get_env_config()["cwd"]`. | observed (v0.22.6) |
| An earlier version of the guard fell back to the Hermes install directory when no session directory was found. Live checks judged against that wrong directory and only passed because temp paths are allowed. The guard now blocks when the directory is unknown. | observed (v0.22.6) |
| `hermes profile install` prints `hermes gateway restart` for refreshing plugin code. | observed (v0.22.6) |
| The launching shell's environment variables are not visible to plugin hooks. A value set with `hermes config set` was also not returned by `hermes_cli.config.get_env_value` inside a hook. | observed (v0.22.6) |
| `{"action": "approve"}` goes to the approval gate. With the default `approvals.mode: smart` an auxiliary model approved a direct `git push origin main`, so `approve` is not a guaranteed human check. | observed (v0.22.6) |
| After a plugin is enabled, replacing its files with `hermes profile update` did not change the running behavior of that profile until a fresh profile was installed. The exact reload step was not found. | observed (v0.22.6) |
| Hermes' `read_file` refuses secret-bearing dotenv files on its own, independent of this guard. | observed (v0.22.6) |
| A `pre_tool_call` callback that raises or times out is treated as a veto: the tool call is blocked. | source-read |

Consequence for the guard: a plugin shipped under `plugins/` registers its
hook without a command path or an allowlist step. It is enabled for new
installs by `config.yaml` and once per existing device with
`hermes plugins enable harness-guard`, because `config.yaml` is not replaced on
update. Asks from the harness become blocks, because the approval gate cannot
be relied on. The guard reads no settings, so an agent cannot switch it off
through them; `hermes plugins disable` is the only off switch, and calls that
mention the guard or Hermes' administration commands are refused.

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

Run on Hermes v0.22.6 (2026.9.24), Linux, with scratch profiles installed
from a local clone of this repo and deleted afterwards. Observed: install,
skill discovery, the update path including a real bump to upstream v5.16.0,
and one-shot runs of `/harness-plan sync` and `/harness-review` through a
model (rows above). The guard plugin was also exercised live: a fresh profile,
`hermes plugins enable harness-guard`, then harmless commands. `echo` and a
write inside the project ran. `sudo -n true`, a force push to a nonexistent
remote, a direct push to `main`, a secret-file read and a write outside the
project were stopped. After the review fixes (patch-file mode, `workdir`, `~/`
paths, unjudgeable calls, protected references, directory lookup),
`plugins/harness-guard/acceptance.py --live` passed 50 of 50 checks on a fresh
install. Not observed: executing the bundled shell scripts through Hermes, an
end to end `/harness-plan create` or `/harness-work` run, extra frontmatter keys
(the generator drops them), the guard on macOS and Windows with a live Hermes,
and `execute_code` or `delegate_task` calls, which the guard does not inspect.
Those rows stay `unknown`.
