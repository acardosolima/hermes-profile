#!/bin/sh
# Best-effort auto-fix formatter for staged files, lint-staged style.
# NEVER blocks the commit — only re-stages whatever a local formatter fixed.
# Silently does nothing for file types with no formatter installed.

staged="$(git diff --cached --name-only --diff-filter=ACM)"
[ -z "$staged" ] && exit 0

py_files=""
js_files=""
go_files=""
rs_files=""

old_ifs="$IFS"
IFS='
'
for f in $staged; do
  [ -f "$f" ] || continue
  case "$f" in
    *.py) py_files="$py_files
$f" ;;
    *.js|*.jsx|*.ts|*.tsx|*.json|*.css|*.scss|*.md|*.yaml|*.yml)
      js_files="$js_files
$f" ;;
    *.go) go_files="$go_files
$f" ;;
    *.rs) rs_files="$rs_files
$f" ;;
  esac
done
IFS="$old_ifs"

changed=0

if [ -n "$py_files" ]; then
  if command -v ruff >/dev/null 2>&1; then
    printf '%s\n' "$py_files" | xargs -r ruff check --fix --quiet -- 2>/dev/null
    changed=1
  fi
  if command -v black >/dev/null 2>&1; then
    printf '%s\n' "$py_files" | xargs -r black --quiet -- 2>/dev/null
    changed=1
  fi
fi

if [ -n "$js_files" ]; then
  if command -v prettier >/dev/null 2>&1; then
    printf '%s\n' "$js_files" | xargs -r prettier --write --loglevel=silent -- 2>/dev/null
    changed=1
  elif [ -x "./node_modules/.bin/prettier" ]; then
    printf '%s\n' "$js_files" | xargs -r ./node_modules/.bin/prettier --write --loglevel=silent -- 2>/dev/null
    changed=1
  fi
fi

if [ -n "$go_files" ] && command -v gofmt >/dev/null 2>&1; then
  printf '%s\n' "$go_files" | xargs -r gofmt -w -- 2>/dev/null
  changed=1
fi

if [ -n "$rs_files" ] && command -v rustfmt >/dev/null 2>&1; then
  printf '%s\n' "$rs_files" | xargs -r rustfmt --quiet -- 2>/dev/null
  changed=1
fi

if [ "$changed" = "1" ]; then
  printf '%s\n%s\n%s\n%s\n' "$py_files" "$js_files" "$go_files" "$rs_files" | grep -v '^$' | xargs -r git add -- 2>/dev/null
fi

exit 0
