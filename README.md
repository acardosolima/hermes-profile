# hermes-profile

Personal Hermes Agent profile distribution — shared across my own devices only.

Install:

```bash
hermes profile install ~/Documents/repositories/hermes-profile --name master --alias
hermes profile use master
cp ~/.hermes/profiles/master/.env.EXAMPLE ~/.hermes/profiles/master/.env
# fill in ANTHROPIC_TOKEN with this device's own key
```

Update after a push:

```bash
hermes profile update master
```

No secrets live in this repo. `.env` / `auth.json` are excluded by `.gitignore`
and also hard-stripped by the installer regardless.
