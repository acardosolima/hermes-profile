---
name: hermes-workflow-configuration
description: "Route Hermes model tiers, skill harnesses, profile sync."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, configuration, delegation, model-routing, skills, orchestration, profiles, distribution, git]
    related_skills: [hermes-agent, hermes-credential-management]
---

# Hermes Workflow Configuration

How to shape a user's STANDING Hermes behavior across sessions: which model
drives the conversation vs. which model delegated subagents run on, and
which skills must load in full every session instead of only when
semantically relevant. These are config.yaml changes that persist, not
in-session advice.

## When to Use

- User wants a cheap/local model to drive orchestration (reading the task,
  looping on `delegate_task`) while a stronger paid model does the actual
  implementation work in the spawned subagents.
- User wants certain skills (TDD, code review, debugging discipline, etc.)
  active on every single session by default, not dependent on the agent
  judging them relevant.
- User wants a standing config.yaml change that should survive `/new` and
  apply across CLI/TUI/gateway/cron for the profile.

## Procedure

### Split-model orchestration (cheap/local coordinator, stronger implementer)

`delegate_task` children inherit the parent session's model UNLESS
`delegation.provider`/`delegation.model` are set in config.yaml — those
override regardless of what the parent session is running on.

1. Set the parent/orchestrator session's own model to the cheap/local one:
   `hermes config set model.provider ollama-launch`
   `hermes config set model.default <local-model>`
2. Pin delegated subagents to the stronger model independent of the parent:
   `hermes config set delegation.provider anthropic`
   `hermes config set delegation.model <strong-model>`
3. For a one-off planning pass stronger than both tiers, swap the session
   model for a single turn (`/model opus`) rather than reconfiguring
   anything persistent, then switch back.
4. When picking a LOCAL model for the orchestrator/coordinator role
   specifically, prefer one tuned for tool-calling/agentic loops over a
   generic chat model of similar size — a model fine-tuned for function
   calling follows a `delegate_task` loop far more reliably than a plain
   instruct model of the same parameter count. Check what's already pulled
   with `ollama list` before suggesting any new download; a suitable model
   is often already sitting there.

### Persistent auto-loaded skills (standing harness)

`skills.auto_load` forces named skills to load in full at the start of
EVERY new session (CLI, TUI, gateway, cron, API) — this is how to build a
real "harness" (e.g. always-on TDD + code-review gates) instead of relying
on the agent's own relevance judgment each time.

1. `hermes config set skills.auto_load '["skill-a","skill-b"]'`
   — list-valued config keys take a JSON array literal as the value
   string; comma-separated plain text does not parse the same way.
2. Verify with `hermes config get skills.auto_load` — confirm the exact
   list before telling the user it's done.
3. This is PROFILE-global, not per-repo: it applies to every session run
   under that Hermes profile, regardless of working directory. If the user
   wants repo-scoped always-on skills instead, point them at project-local
   skill directories (`./.hermes/skills`, `./.agents/skills`) plus
   `hermes skills trust`, not `skills.auto_load`.

### Cross-device profile sync (export vs. distribution)

Two ways to carry a profile's config/skills/SOUL to the user's other
machines. Both always strip `auth.json`/`.env` automatically — credentials
are never the user's problem to scrub manually.

1. Decide which fits: a one-off `/export` + `/import` (or
   `hermes profile export/import`) `.tar.gz` for "just copy my setup once";
   a git-based distribution (`distribution.yaml` manifest + repo) when the
   user will keep tweaking config and wants every device to pick up changes
   with a single `hermes profile update <name>`. If the user says they'll
   iterate and sync repeatedly, default to the distribution, not repeated
   manual export/import.
2. Build the distribution in a FRESH named profile/repo dir, never by
   `git init`-ing the user's live `default` profile (`$HERMES_HOME` root) or
   a profile they've already been chatting in — that directory has
   `auth.json`, `sessions/`, `memories/`, `logs/` already mixed in with the
   content you want to ship, which is exactly the setup where a `git add .`
   accidentally stages a secret. Copy just the wanted files
   (`config.yaml`, `SOUL.md`, `skills/` minus `.hub`/`.locks`/`.usage.json*`
   bookkeeping, any plugin dirs minus their own `.git/`) into the new repo
   instead.
3. You cannot name the installed/imported target profile `default` — it's
   the reserved root profile name. Pick anything else and make it the
   sticky default on that device with `hermes profile use <name>`.
4. Write a `distribution.yaml` manifest (`name`, `version`, `env_requires`
   listing each credential var the config expects, with a one-line
   description of what it is and whether it's required) and a `.gitignore`
   excluding `auth.json`, `.env*`, `sessions/`, `memories/`, `state.db*`,
   `logs/`, cache dirs — before the first `git add`, not after.
5. Before pushing anywhere, run `gh auth status` (or check git's configured
   remote credentials) and confirm which account it will land under. A
   company-tied git login sitting authenticated on a machine is the same
   cross-contamination risk as a company OAuth token in the credential pool
   — don't let a personal cross-device config repo land in a company org
   silently.

## Pitfalls

- When creating any new git repo on this user's behalf, initialize the
  default branch as `master` (`git init -b master`), never `main` — this is
  a standing preference, not a one-off choice for a single repo.
- Never hand-edit `config.yaml` directly for either of the above — always
  `hermes config set key value`; a stray indent corrupts the file and can
  break the live gateway.
- Don't assume `delegation.model`/`delegation.provider` is set just because
  the parent model was switched — the two are independent, and leaving
  delegation unset means children silently inherit whatever the parent
  session happens to be on, defeating a split-tier setup.
- Don't default to the smallest/most generic local model for an
  orchestrator role out of habit — check `ollama list` for anything already
  pulled that's specifically tuned for function-calling/agentic tasks
  first; it coordinates `delegate_task` loops far more reliably.
- `skills.auto_load` changes don't retroactively affect the CURRENT running
  session — they take effect on the next new session (`/new` or fresh
  launch), same as other tool/skill config changes.
