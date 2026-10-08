#!/bin/sh
# Reads a unified diff on stdin, fails (exit 1) if any ADDED line matches a
# known secret shape. Used by pre-commit (staged diff).
label="$1"
LIBDIR="$(cd "$(dirname "$0")" && pwd)"

added="$(grep -E '^\+' | grep -Ev '^\+\+\+')"
if [ -z "$added" ]; then
  exit 0
fi

match=$(printf '%s\n' "$added" | grep -Eif "$LIBDIR/secret-patterns.txt")
if [ -n "$match" ]; then
  echo "[$label] Refusing: possible secret detected in the diff:" >&2
  printf '%s\n' "$match" | sed 's/^/    /' >&2
  echo "[$label] If this is a false positive, fix the pattern in ~/.githooks/lib/secret-patterns.txt" >&2
  echo "[$label] or bypass deliberately with 'git commit/push --no-verify'." >&2
  exit 1
fi
exit 0
