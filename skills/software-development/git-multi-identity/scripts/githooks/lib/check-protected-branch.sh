#!/bin/sh
# Blocks commits directly on protected branches (main/master/trunk) to force
# a feature-branch workflow. Reverting a bad commit on a protected branch
# still leaves a messy, hard-to-read log; a branch can just be abandoned.
#
# Intentional bypass (e.g. a deliberate hotfix, or an initial repo setup
# commit before any branching makes sense):
#   GIT_ALLOW_PROTECTED_COMMIT=1 git commit ...

PROTECTED='^(main|master|trunk)$'

if [ "$GIT_ALLOW_PROTECTED_COMMIT" = "1" ]; then
  exit 0
fi

branch="$(git symbolic-ref --short HEAD 2>/dev/null)"
# Detached HEAD (e.g. rebase in progress) — not a named branch, let it through.
[ -z "$branch" ] && exit 0

if printf '%s\n' "$branch" | grep -Eqi "$PROTECTED"; then
  echo "pre-commit: refusing to commit directly on protected branch '$branch'." >&2
  echo "pre-commit: create a feature branch first, e.g.:" >&2
  echo "    git checkout -b feature/short-description" >&2
  echo "pre-commit: deliberate exception: GIT_ALLOW_PROTECTED_COMMIT=1 git commit ..." >&2
  exit 1
fi
exit 0
