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

Update after a push:

```bash
hermes profile update master
```

No secrets live in this repo. `.env` / `auth.json` are excluded by `.gitignore`
and also hard-stripped by the installer regardless.
