#!/bin/sh
# Validates the commit message subject line follows Conventional Commits.
# $1 is the path git passes to the commit-msg hook (the message file).
msgfile="$1"
first_line="$(head -1 "$msgfile")"

case "$first_line" in
  Merge\ *|Revert\ *|fixup!\ *|squash!\ *)
    exit 0
    ;;
esac

if ! printf '%s\n' "$first_line" | grep -Eq '^(feat|fix|chore|docs|style|refactor|perf|test|build|ci)(\([a-zA-Z0-9_.-]+\))?!?: .+'; then
  echo "commit-msg: message doesn't follow Conventional Commits format." >&2
  echo "commit-msg: expected e.g. 'feat: add X' or 'fix(scope): correct Y' — got:" >&2
  echo "    $first_line" >&2
  exit 1
fi
exit 0
