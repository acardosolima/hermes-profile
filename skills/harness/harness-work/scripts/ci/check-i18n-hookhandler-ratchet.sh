#!/usr/bin/env bash
# Phase 105.2: i18n contract ratchet for go/internal/hookhandler.
#
# The spec i18n contract requires user-facing runtime strings to go through the
# locale resolver (localizedHarnessMessage / resolveHarnessLocale), with English
# as the default and Japanese opt-in.
#
# This gate counts "bare" Japanese string literals — Japanese text in a string
# literal on a line that does NOT go through localizedHarnessMessage and is NOT
# a comment — and fails if any are present.
#
# Exit 0 if count <= baseline, exit 1 if it exceeds the baseline.
# Note: no `set -e` — grep returning 1 (no match) in the counting pipeline is
# expected and must not abort the script.
set -uo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HANDLER_DIR="$ROOT/go/internal/hookhandler"

# Phase 106.2: all hookhandler Japanese user-facing text is localized. Never
# raise this baseline to accommodate new debt.
BASELINE=0

if [ ! -d "$HANDLER_DIR" ]; then
  echo "i18n ratchet: hookhandler dir not found ($HANDLER_DIR) — skipping (not-configured)"
  exit 0
fi

# Count Japanese string-literal lines that are NOT inside a localizedHarnessMessage(...)
# call span and are not comments. awk tracks paren depth so that ja arguments on
# their own line inside a multi-line localizer call are correctly excluded.
count=0
for f in "$HANDLER_DIR"/*.go; do
  case "$f" in *_test.go) continue ;; esac
  [ -f "$f" ] || continue
  n=$(awk '
    # Strip a Go line comment (//) only when it is NOT inside a string literal.
    # A naive sub(/\/\/.*/) would truncate at the // inside a URL such as
    # "参照: https://example.com", deleting a localizer call closing paren and
    # leaking paren depth across the rest of the file — silently disabling the
    # ratchet. Track double-quote and backtick (raw) string state with escapes.
    function stripComment(s,   i, ch, inD, inB, esc, len) {
      len = length(s); inD = 0; inB = 0; esc = 0
      for (i = 1; i <= len; i++) {
        ch = substr(s, i, 1)
        if (esc) { esc = 0; continue }
        if (ch == "\\" && inD) { esc = 1; continue }
        if (ch == "\"" && !inB) { inD = !inD; continue }
        if (ch == "`" && !inD) { inB = !inB; continue }
        if (ch == "/" && !inD && !inB && i < len && substr(s, i + 1, 1) == "/") {
          return substr(s, 1, i - 1)
        }
      }
      return s
    }
    # Maintain paren depth of an active localizedHarnessMessage(...) call.
    { line = stripComment($0) }
    {
      inCall = (depth > 0)
      # If this line opens a localizer call, everything from here is localized.
      if (line ~ /localizedHarnessMessage[[:space:]]*\(/) { opensCall = 1 } else { opensCall = 0 }
      # A Japanese literal outside any localizer call is a bare (unmigrated) string.
      if (!inCall && !opensCall && line ~ /"[^"]*[ぁ-んァ-ヶ一-龠][^"]*"/) { bare++ }
      # Update paren depth across the line for multi-line localizer spans.
      if (opensCall || inCall) {
        for (i = 1; i <= length(line); i++) {
          c = substr(line, i, 1)
          if (c == "(") depth++
          else if (c == ")") { if (depth > 0) depth-- }
        }
      }
    }
    END { print bare + 0 }
  ' "$f")
  count=$((count + n))
done

if [ "$count" -gt "$BASELINE" ]; then
  echo "❌ i18n ratchet: bare Japanese literals rose to $count (baseline $BASELINE)."
  echo "   New user-facing strings must use localizedHarnessMessage(locale, en, ja)."
  exit 1
fi

if [ "$count" -lt "$BASELINE" ]; then
  echo "✅ i18n ratchet: bare Japanese literals down to $count (baseline $BASELINE) — lower BASELINE in this script."
else
  echo "✅ i18n ratchet: bare Japanese literals at baseline ($count)."
fi
exit 0
