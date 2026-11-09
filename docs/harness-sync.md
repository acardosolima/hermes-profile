# harness_sync

`tools/harness_sync.py` translates selected claude-code-harness skills into
Hermes skills under `skills/harness/`. Python 3.9+, standard library only,
must run on Linux, macOS and Windows.

## Inputs

`upstream.lock` is JSON: `{"repo": "<git url>", "tag": "<tag>", "sha": "<40 hex>"}`.
`load_lock` raises `LockError` for an unreadable or non-UTF-8 file, invalid or
non-object JSON, a missing key, a `repo` or `tag` that is not a non-empty
string without NUL, or a sha that is not 40 lowercase hex characters.

## Public API

All functions live in `tools/harness_sync.py`.

- `ALLOWLIST`: tuple `("harness-plan", "harness-work", "harness-review",
  "harness-sync", "harness-setup", "harness-loop", "harness-release",
  "breezing")`.
- `load_lock(path) -> dict`
- `fetch_upstream(lock, dest, clone_url=None) -> Path`: shallow-clone `clone_url`
  (default `lock["repo"]`) at `lock["tag"]` into `dest`, verify `HEAD` equals
  `lock["sha"]`, return the checkout root. `dest` must not exist; an existing
  `dest` raises `FetchError`. A `repo` or `tag` that is empty, starts with `-`
  or contains NUL also raises `FetchError`. On sha mismatch or any git failure raise
  `FetchError` and leave nothing at `dest`.
- `split_frontmatter(text) -> (dict, str)`: parse the leading `---` block of
  top-level `key: value` lines (quoted or bare scalars) and return the body.
  No frontmatter returns `({}, text)`. A UTF-8 BOM and CRLF newlines are accepted.
- `translate_skill(name, upstream_root, lock) -> dict[str, bytes]`: path
  relative to the skill directory to content for one skill (`SKILL.md`,
  `references/...`, `scripts/...`).
- `generate(upstream_root, lock, allowlist=ALLOWLIST) -> dict[str, bytes]`:
  keys are `<skill>/<relpath>` relative to `skills/harness/`, plus the top-level
  key `GENERATED.json`.
- `write_output(files, target)`: replace the directory `target` so that a
  failure leaves the previous contents intact. A missing `target` is created,
  with its parents. Files absent from `files` are removed.
- `check(upstream_root, lock, target) -> list[str]`: regenerate in memory and
  compare with `target`. Return lines ordered by path: `added <path>` (generated, absent
  from `target`), `removed <path>` (present in `target`, not generated) and
  `changed <path>` (both, different bytes). Empty list means in sync. A missing
  `target` yields an `added` line for every generated file. `check` compares
  file contents only, not modes.
- `resolve_release(repo, tag=None) -> (tag, sha)`: read `git ls-remote --tags`
  from `repo`. Without `tag`, pick the highest `vX.Y.Z` tag compared
  numerically; pre-release and non-version tags are ignored. The sha is the
  commit sha, peeled for annotated tags. Raises `FetchError` when `repo` is
  unreachable or option-like, no release tag exists, or `tag` is absent.
- `bump(lock_path, tag=None, repo=None) -> (old_tag, new_tag)`: update
  `upstream.lock` to `resolve_release(repo or lock["repo"], tag)` and write it
  as `json.dumps(obj, indent=2, sort_keys=True)` plus a newline. Without `tag`
  the lock only moves forward. If the lock's tag now points to a different
  commit, raise `FetchError` and leave the file untouched. When nothing
  changes the file is not written and `old_tag == new_tag`.
- `scan_secrets(files) -> None`: raise `SecretFoundError` naming the path when
  any generated file matches a secret pattern. Files that are not valid UTF-8
  are scanned with undecodable bytes replaced.
- `main(argv) -> int`

## Upstream layout

Skills live at `<upstream_root>/skills/<name>/SKILL.md`. Helper scripts live in
the shared directory `<upstream_root>/scripts/`. Each translated skill bundles
its own copy of the scripts it needs under `<skill>/scripts/`.

## Translation rules

1. Frontmatter is rewritten to exactly these keys, in this order: `name`,
   `description`, `version` (the upstream tag), `platforms` (`[linux, macos,
   windows]`). `description` is the upstream `description-en` when present,
   otherwise `description`, truncated to 1024 characters. All other upstream
   keys are dropped. A skill with no `name` or no description raises
   `TranslateError`.
2. `${CLAUDE_SKILL_DIR}/` is replaced by an empty string, leaving paths
   relative to the skill directory. A bare `${CLAUDE_SKILL_DIR}` becomes `.`.
3. `${HARNESS_PLUGIN_ROOT}/scripts/` and `${CLAUDE_PLUGIN_ROOT}/scripts/`
   become `scripts/`.
4. A fixed compatibility preamble is inserted directly after the frontmatter,
   wrapped in `<!-- harness-sync:preamble:start -->` and
   `<!-- harness-sync:preamble:end -->`. It names the Claude Code to Hermes tool
   mapping and states that guardrail hooks are not enforced by the skill.
5. Rules 2 and 3 also apply to every `.md` file under `references/`. Other
   files are copied byte for byte.
6. `scripts/`: copy each upstream `scripts/<file>` whose path appears as the
   literal token `scripts/<file>` in the skill's `SKILL.md` or `references/`,
   then repeat for files those scripts mention, until no new file appears.
   Trailing dots are stripped from a token. A token naming an upstream
   directory is neither bundled nor reported. A token matching no upstream file
   is not bundled and is recorded in the manifest under `missing_scripts` as
   `scripts/<token>`; only tokens in `SKILL.md` and `.md` references are
   reported. Scripts are copied byte for byte.
7. Generated `SKILL.md`, `.md` references and `GENERATED.json` use LF newlines
   and UTF-8 without BOM. Scripts and non-`.md` reference files keep their
   original bytes.
   Frontmatter string values are written as JSON-quoted strings.
8. After translation, any remaining `${CLAUDE_NAME` expansion in a generated
   `.md` file, in any form (`${CLAUDE_NAME}`, `${CLAUDE_NAME:-}`), is recorded in
   the manifest under `unresolved` as `${CLAUDE_NAME}`, and is not removed.
9. Reads stay inside the skill directory (`SKILL.md`, `references/`) or the
   upstream `scripts/` directory (scripts). A symlink under a skill directory
   raises `TranslateError`. A script token containing `..` is never bundled.
   `.git` directories are skipped. A symlink under `scripts/` is not followed,
   and a token naming one is reported as `missing_scripts`. A symlinked `skills/` or `skills/<name>`
   directory raises `TranslateError`. A script token is bundled only when it is
   already the canonical path of an existing file under `scripts/` (no `..`,
   `.` or doubled separators); other tokens are reported as `missing_scripts`. Invalid UTF-8 in `SKILL.md` or a `.md`
   reference raises `TranslateError`.
10. Shell scripts (a file under a `scripts/` directory that starts with `#!`)
    are written with mode 0755 and output directories with 0755 on POSIX.
11. Skills not in the allowlist are never read or copied. A missing allowlist
   skill raises `TranslateError`.

## GENERATED.json

JSON with sorted keys, 2-space indent, trailing newline:

```
{
  "generator_version": "1",
  "skills": {"<name>": {"files": {"<relpath>": "<sha256 hex>"},
                        "missing_scripts": ["scripts/<token>", ...],
                        "unresolved": ["${CLAUDE_NAME}", ...]}},
  "upstream": {"repo": "...", "sha": "...", "tag": "..."}
}
```

`files` keys are relative to the skill directory. It lists every generated file
except itself. Serialization is exactly `json.dumps(obj, indent=2,
sort_keys=True)` plus a trailing newline. Two runs on the same inputs
produce byte-identical output.

## Secret patterns

`sk-ant-` followed by 10 or more token characters, `ghp_` followed by 20 or
more, `AKIA` followed by 16 uppercase alphanumerics, `xox[bap]-` followed by 10
or more, and PEM `-----BEGIN ... PRIVATE KEY-----` headers.

## CLI

```
python tools/harness_sync.py sync  [--lock upstream.lock] [--out skills/harness] [--source <git url or path>]
python tools/harness_sync.py check [--lock upstream.lock] [--out skills/harness] [--source <git url or path>]
```

```
python tools/harness_sync.py bump  [--lock upstream.lock] [--tag <tag>] [--source <git url or path>]
```

`bump` prints `bumped <old> <new>` or `unchanged <tag>` and exits 0.

`sync` fetches, generates, scans for secrets, then writes. `check` exits 0
when in sync and 1 with the diff lines on stdout otherwise. Any error exits 2
with a message on stderr and writes nothing.
