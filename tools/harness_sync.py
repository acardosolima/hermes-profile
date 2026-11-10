"""Translate claude-code-harness skills into Hermes skills.

Fetches the upstream claude-code-harness repository at a pinned tag and
sha, translates the allow-listed skills into the Hermes skill format under
``skills/harness/``, and writes (or checks) that output deterministically.
Standard library only; works on Linux, macOS and Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class HarnessSyncError(Exception):
    """Base error for all harness_sync failures."""


class LockError(HarnessSyncError):
    """Raised for a missing, unreadable, or malformed upstream.lock."""


class FetchError(HarnessSyncError):
    """Raised when fetching or verifying the upstream checkout fails."""


class TranslateError(HarnessSyncError):
    """Raised when a skill cannot be translated into Hermes format."""


class SecretFoundError(HarnessSyncError):
    """Raised when generated output matches a known secret pattern."""


ALLOWLIST = (
    "harness-plan",
    "harness-work",
    "harness-review",
    "harness-sync",
    "harness-setup",
    "harness-loop",
    "harness-release",
    "breezing",
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_SKILL_DIR_TOKEN_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/")
_SKILL_DIR_BARE_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}")
_PLUGIN_SCRIPTS_RE = re.compile(
    r"\$\{(?:HARNESS_PLUGIN_ROOT|CLAUDE_PLUGIN_ROOT)\}/scripts/"
)
_UNRESOLVED_TOKEN_RE = re.compile(r"\$\{(CLAUDE_[A-Z0-9_]+)")
_RELEASE_TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
_GUARD_BINARY_RE = re.compile(r"harness-(linux|darwin|windows)-(amd64|arm64)(?:\.exe)?")
_GUARD_RULE_ID_RE = re.compile(r'ID:\s+"(R\d+:[a-z0-9-]+)"')
GUARD_LOCK_PATH = "plugins/harness-guard/binaries.lock.json"
_SCRIPT_TOKEN_RE = re.compile(r"scripts/([A-Za-z0-9_][A-Za-z0-9_./-]*)")

_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"xox[bap]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_PREAMBLE_TEXT = (
    "This skill was translated from Claude Code to Hermes. Claude Code "
    "tools map to Hermes tools as follows: Bash -> terminal, Read -> "
    "read_file, Write/Edit -> write_file/patch (patch arguments unverified), "
    "AskUserQuestion -> "
    "clarify, Agent/Task -> delegate_task (degraded), ScheduleWakeup -> "
    "cronjob (degraded), "
    "WebSearch -> web toolset. TeamCreate and hook-driven monitors have "
    "no Hermes equivalent. Guardrail hooks referenced by the original "
    "skill are not enforced here; only hooks shipped and activated in "
    "this profile under agent-hooks/ apply. Helper scripts bundled with "
    "this skill live in its scripts/ directory; where the text refers to a "
    "plugin root, use this skill's directory as that root for those "
    "scripts. Paths such as .claude/state and bin/harness may not exist on "
    "this host."
)

_GIT_TIMEOUT_SECONDS = 300

_GIT_ENV_SCRUBBED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")

_GIT_ENV_OVERRIDES = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git_env():
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_SCRUBBED}
    env.update(_GIT_ENV_OVERRIDES)
    return env


def load_lock(path):
    """Load and validate an ``upstream.lock`` JSON file."""
    lock_path = Path(path)
    try:
        raw = lock_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise LockError(f"cannot read lock file: {lock_path}") from exc
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise LockError(f"invalid JSON in lock file: {lock_path}") from exc
    if not isinstance(data, dict):
        raise LockError(f"lock file must contain a JSON object: {lock_path}")
    for key in ("repo", "tag", "sha"):
        if key not in data:
            raise LockError(f"lock file missing key '{key}': {lock_path}")
    for key in ("repo", "tag"):
        value = data[key]
        if not isinstance(value, str) or not value or "\x00" in value:
            raise LockError(f"lock {key} must be a non-empty string without NUL")
    sha = data["sha"]
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        raise LockError(f"lock sha must be 40 lowercase hex characters: {sha!r}")
    return data


def fetch_upstream(lock, dest, clone_url=None):
    """Shallow-clone the upstream repo at the locked tag, verify its sha.

    Clones into a private staging directory first and only moves content
    into ``dest`` once the checked-out HEAD matches ``lock["sha"]``. On a
    mismatch, or any git failure, ``dest`` is left untouched.
    """
    dest = Path(dest)
    if dest.exists():
        raise FetchError(f"destination already exists: {dest}")
    url = clone_url if clone_url else lock.get("repo")
    tag = lock.get("tag")
    _check_git_arg("url", url)
    _check_git_arg("tag", tag)
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=".harness_sync_fetch_", dir=str(parent)))
    checkout_dir = staging / "checkout"
    env = _git_env()
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", tag, "--", url, str(checkout_dir)],
            check=True,
            env=env,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise FetchError(f"git clone failed for tag {tag}: {type(exc).__name__}") from exc

    try:
        result = subprocess.run(
            ["git", "-C", str(checkout_dir), "rev-parse", "HEAD"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise FetchError(f"git rev-parse failed: {type(exc).__name__}") from exc

    actual_sha = result.stdout.strip()
    expected_sha = lock.get("sha")
    if actual_sha != expected_sha:
        shutil.rmtree(staging, ignore_errors=True)
        raise FetchError(f"sha mismatch: expected {expected_sha} got {actual_sha}")

    os.replace(checkout_dir, dest)
    shutil.rmtree(staging, ignore_errors=True)
    return dest


def _normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text):
    """Split a leading ``---`` frontmatter block of ``key: value`` lines.

    Accepts a UTF-8 BOM and CRLF newlines. Returns ``({}, text)`` when
    there is no frontmatter block.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    normalized = _normalize_newlines(text)
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_index = i
            break
    if end_index is None:
        return {}, text

    data = {}
    for line in lines[1:end_index]:
        if not line.strip() or line[0] in " \t" or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value

    body = "\n".join(lines[end_index + 1 :])
    return data, body


def _apply_path_substitutions(text):
    text = _SKILL_DIR_TOKEN_RE.sub("", text)
    text = _SKILL_DIR_BARE_RE.sub(".", text)
    text = _PLUGIN_SCRIPTS_RE.sub("scripts/", text)
    return text


def _yaml_scalar(value):
    return json.dumps(value, ensure_ascii=False)


def _render_skill_md(name, description, version, body):
    frontmatter = "\n".join(
        [
            "---",
            f"name: {_yaml_scalar(name)}",
            f"description: {_yaml_scalar(description)}",
            f"version: {_yaml_scalar(version)}",
            "platforms: [linux, macos, windows]",
            "---",
        ]
    )
    preamble = "\n".join(
        [
            "<!-- harness-sync:preamble:start -->",
            _PREAMBLE_TEXT,
            "<!-- harness-sync:preamble:end -->",
        ]
    )
    body = _normalize_newlines(body).strip("\n")
    parts = [part for part in (frontmatter, preamble, body) if part]
    return "\n\n".join(parts) + "\n"


def _read_bytes_within(path, root):
    """Read a file, rejecting any resolved path outside ``root``."""
    root_resolved = Path(root).resolve()
    try:
        resolved = Path(path).resolve()
    except OSError as exc:
        raise TranslateError(f"cannot resolve path: {path}") from exc
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise TranslateError(f"path escapes upstream root: {path}")
    return resolved.read_bytes()


def _check_git_arg(label, value):
    if not isinstance(value, str) or not value or value.startswith("-") or "\x00" in value:
        raise FetchError(f"invalid {label} for git")


def _release_key(tag):
    match = _RELEASE_TAG_RE.fullmatch(tag)
    return tuple(int(part) for part in match.groups()) if match else None


def _remote_tags(repo):
    """Map tag name to commit sha from ``git ls-remote --tags`` (peeled when annotated)."""
    _check_git_arg("url", repo)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--", repo],
            check=True,
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, UnicodeError) as exc:
        raise FetchError(f"git ls-remote failed: {type(exc).__name__}") from exc
    tags = {}
    for line in result.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/") or not _SHA_RE.fullmatch(sha):
            continue
        name = ref[len("refs/tags/"):]
        peeled = name.endswith("^{}")
        if peeled:
            name = name[:-3]
        if peeled or name not in tags:
            tags[name] = sha
    return tags


def resolve_release(repo, tag=None):
    """Return ``(tag, commit sha)`` for ``tag`` or the highest ``vX.Y.Z`` tag."""
    tags = _remote_tags(repo)
    if tag is None:
        releases = [name for name in tags if _release_key(name)]
        if not releases:
            raise FetchError("no vX.Y.Z release tag found")
        tag = max(releases, key=_release_key)
    elif tag not in tags:
        raise FetchError(f"tag not found: {tag}")
    return tag, tags[tag]


def bump(lock_path, tag=None, repo=None):
    """Move ``upstream.lock`` to a newer release. Returns ``(old_tag, new_tag)``.

    Without ``tag`` the lock only moves forward. A tag that now points at a
    different commit than the lock records raises ``FetchError``.
    """
    lock = load_lock(lock_path)
    old_tag = lock["tag"]
    new_tag, new_sha = resolve_release(repo or lock["repo"], tag)
    if new_tag == old_tag:
        if new_sha != lock["sha"]:
            raise FetchError(f"tag {old_tag} moved to a different commit")
        return old_tag, old_tag
    if tag is None:
        old_key, new_key = _release_key(old_tag), _release_key(new_tag)
        if old_key is not None and new_key <= old_key:
            return old_tag, old_tag
    updated = dict(lock, tag=new_tag, sha=new_sha)
    with open(lock_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(updated, indent=2, sort_keys=True) + "\n")
    return old_tag, new_tag


def _decode_text(content, path):
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TranslateError(f"not valid UTF-8: {path}") from exc


def _read_skill_file(path, skill_dir):
    """Read a file that must be a regular file inside ``skill_dir``."""
    if Path(path).is_symlink():
        raise TranslateError(f"symlink not allowed: {path}")
    return _read_bytes_within(path, skill_dir)


def _walk_files(directory):
    """Yield regular files below ``directory`` in sorted order, never following links."""
    for current, dirs, names in os.walk(directory, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for dirname in dirs:
            if (Path(current) / dirname).is_symlink():
                raise TranslateError(f"symlink not allowed: {Path(current) / dirname}")
        for name in sorted(names):
            yield Path(current) / name


def _script_tokens(text):
    """Return ``scripts/<file>`` tokens with sentence-ending dots removed."""
    tokens = (token.rstrip(".") for token in _SCRIPT_TOKEN_RE.findall(text))
    return [token for token in tokens if token]


def _collect_scripts(files, upstream_root):
    """Expand literal ``scripts/<file>`` tokens found in skill text.

    Repeats over newly copied scripts so that a script referencing
    another script is also pulled in, until no new file appears. Tokens
    with path traversal or that resolve outside ``upstream_root/scripts``
    are ignored, as are tokens matching no upstream file.
    """
    scripts_root = upstream_root / "scripts"
    if not scripts_root.is_dir():
        return {}
    scripts_root_resolved = scripts_root.resolve()

    queue = []
    for relpath, content in files.items():
        if relpath == "SKILL.md" or relpath.startswith("references/"):
            try:
                queue.extend(_script_tokens(content.decode("utf-8")))
            except UnicodeDecodeError:
                continue

    discovered = {}
    seen_tokens = set()
    while queue:
        token = queue.pop()
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        if ".." in Path(token).parts:
            continue
        candidate = scripts_root / token
        try:
            candidate_resolved = candidate.resolve()
        except OSError:
            continue
        if (
            candidate_resolved != scripts_root_resolved
            and scripts_root_resolved not in candidate_resolved.parents
        ):
            continue
        if not candidate_resolved.is_file():
            continue
        if candidate_resolved.relative_to(scripts_root_resolved).as_posix() != token:
            continue
        content = _read_bytes_within(candidate_resolved, upstream_root)
        discovered[f"scripts/{token}"] = content
        try:
            queue.extend(_script_tokens(content.decode("utf-8")))
        except UnicodeDecodeError:
            pass
    return discovered


def _missing_scripts(translated, upstream_root):
    """Script tokens in skill text that no bundled file satisfies.

    A token naming an upstream directory is not missing.
    """
    scripts_root = Path(upstream_root) / "scripts"
    missing = set()
    for relpath, content in translated.items():
        if not (relpath == "SKILL.md" or relpath.startswith("references/")):
            continue
        if not relpath.endswith(".md"):
            continue
        for token in _script_tokens(content.decode("utf-8")):
            if f"scripts/{token}" in translated:
                continue
            if ".." not in Path(token).parts and (scripts_root / token).is_dir():
                continue
            missing.add(f"scripts/{token}")
    return sorted(missing)


def translate_skill(name, upstream_root, lock):
    """Translate one upstream skill into its Hermes output files."""
    upstream_root = Path(upstream_root)
    skill_dir = upstream_root / "skills" / name
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        raise TranslateError(f"missing skill: {name}")
    for link in (upstream_root / "skills", skill_dir):
        if link.is_symlink():
            raise TranslateError(f"symlink not allowed: {link}")

    raw_text = _decode_text(_read_skill_file(skill_md_path, skill_dir), skill_md_path)
    frontmatter, body = split_frontmatter(raw_text)

    upstream_name = frontmatter.get("name")
    if not upstream_name:
        raise TranslateError(f"skill '{name}' has no name")
    description = frontmatter.get("description-en") or frontmatter.get("description")
    if not description:
        raise TranslateError(f"skill '{name}' has no description")
    description = description[:1024]

    body = _apply_path_substitutions(body)
    skill_md_text = _render_skill_md(upstream_name, description, lock["tag"], body)

    files = {"SKILL.md": skill_md_text.encode("utf-8")}

    references_dir = skill_dir / "references"
    if references_dir.is_symlink():
        raise TranslateError(f"symlink not allowed: {references_dir}")
    if references_dir.is_dir():
        for path in _walk_files(references_dir):
            rel = path.relative_to(skill_dir).as_posix()
            content = _read_skill_file(path, skill_dir)
            if path.suffix == ".md":
                text = _apply_path_substitutions(_decode_text(content, path))
                content = (_normalize_newlines(text)).encode("utf-8")
            files[rel] = content

    files.update(_collect_scripts(files, upstream_root))
    return files


def _unresolved_tokens(text_files):
    tokens = set()
    for content in text_files.values():
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        tokens.update("${" + name + "}" for name in _UNRESOLVED_TOKEN_RE.findall(text))
    return sorted(tokens)


def generate(upstream_root, lock, allowlist=ALLOWLIST):
    """Translate every allow-listed skill and build ``GENERATED.json``."""
    upstream_root = Path(upstream_root)
    files = {}
    skills_manifest = {}
    for name in sorted(allowlist):
        translated = translate_skill(name, upstream_root, lock)
        file_hashes = {}
        text_files = {}
        for relpath in sorted(translated):
            content = translated[relpath]
            files[f"{name}/{relpath}"] = content
            file_hashes[relpath] = hashlib.sha256(content).hexdigest()
            if relpath.endswith(".md"):
                text_files[relpath] = content
        skills_manifest[name] = {
            "files": file_hashes,
            "missing_scripts": _missing_scripts(translated, upstream_root),
            "unresolved": _unresolved_tokens(text_files),
        }

    manifest = {
        "generator_version": "1",
        "skills": skills_manifest,
        "upstream": {
            "repo": lock["repo"],
            "sha": lock["sha"],
            "tag": lock["tag"],
        },
    }
    manifest_text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    files["GENERATED.json"] = manifest_text.encode("utf-8")
    return files


def _is_shell_script(relpath, content):
    parts = relpath.split("/")
    return "scripts" in parts[:-1] and content.startswith(b"#!")


def _open_directory_modes(root):
    """mkdtemp creates 0700 directories; published trees should be 0755."""
    for current, _dirs, _ in os.walk(root):
        Path(current).chmod(0o755)


def write_output(files, target):
    """Atomically replace ``target`` with exactly the contents of ``files``.

    Builds the new tree in a sibling staging directory, then swaps it
    into place. If anything raises before the swap completes, ``target``
    keeps its previous contents.
    """
    target = Path(target)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=".harness_sync_new_", dir=str(parent)))
    try:
        for relpath in sorted(files):
            dest_path = staging / relpath
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as fh:
                fh.write(files[relpath])
            if _is_shell_script(relpath, files[relpath]):
                dest_path.chmod(0o755)
        _open_directory_modes(staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    backup = staging.with_name(staging.name + "-old")
    had_backup = False
    try:
        if target.exists():
            os.replace(target, backup)
            had_backup = True
        os.replace(staging, target)
    except BaseException:
        if had_backup and not target.exists():
            os.replace(backup, target)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if had_backup:
        shutil.rmtree(backup, ignore_errors=True)


def check(upstream_root, lock, target):
    """Regenerate in memory and diff it against the files under ``target``."""
    generated = generate(upstream_root, lock)
    target = Path(target)
    existing = {}
    if target.exists():
        for path in sorted(target.rglob("*")):
            if path.is_file():
                rel = path.relative_to(target).as_posix()
                existing[rel] = path.read_bytes()

    generated_keys = set(generated)
    existing_keys = set(existing)
    diffs = {}
    for rel in generated_keys - existing_keys:
        diffs[rel] = "added"
    for rel in existing_keys - generated_keys:
        diffs[rel] = "removed"
    for rel in generated_keys & existing_keys:
        if generated[rel] != existing[rel]:
            diffs[rel] = "changed"
    return [f"{kind} {rel}" for rel, kind in sorted(diffs.items())]


def guard_lock(upstream_root, lock):
    """Bytes of the guard lock: pinned binary hashes and upstream rule ids."""
    upstream_root = Path(upstream_root)
    bin_dir = upstream_root / "bin"
    binaries = {}
    if bin_dir.is_dir():
        for path in sorted(bin_dir.iterdir()):
            match = _GUARD_BINARY_RE.fullmatch(path.name)
            if not match:
                continue
            if path.is_symlink():
                raise TranslateError(f"symlink not allowed: {path}")
            content = _read_bytes_within(path, upstream_root)
            binaries[f"{match.group(1)}-{match.group(2)}"] = {
                "file": f"bin/{path.name}",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
    rules_path = upstream_root / "go" / "internal" / "policy" / "rules.go"
    rules = []
    if rules_path.is_file() and not rules_path.is_symlink():
        text = _decode_text(_read_bytes_within(rules_path, upstream_root), rules_path)
        rules = sorted(set(_GUARD_RULE_ID_RE.findall(text)))
    manifest = {
        "binaries": binaries,
        "repo": lock["repo"],
        "rules": rules,
        "sha": lock["sha"],
        "tag": lock["tag"],
    }
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_guard_lock(content, path):
    """Replace the guard lock file with `content`, creating parents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".tmp")
    with open(staging, "wb") as handle:
        handle.write(content)
    os.replace(staging, path)


def check_guard_lock(upstream_root, lock, path):
    """Diff lines for the guard lock file against what the lock would generate."""
    path = Path(path)
    expected = guard_lock(upstream_root, lock)
    if not path.is_file():
        return [f"added {path.as_posix()}"]
    if path.read_bytes() != expected:
        return [f"changed {path.as_posix()}"]
    return []


def scan_secrets(files):
    """Raise ``SecretFoundError`` if any text file matches a secret pattern."""
    for relpath in sorted(files):
        content = files[relpath]
        text = content.decode("utf-8", errors="replace")
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                raise SecretFoundError(f"secret pattern found in {relpath}")
    return None


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="harness_sync.py",
        description="Sync claude-code-harness skills into skills/harness/.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd, help_text in (
        ("sync", "Fetch, translate and write skills/harness/."),
        ("check", "Fetch, translate and diff against skills/harness/."),
    ):
        cmd_parser = sub.add_parser(cmd, help=help_text)
        cmd_parser.add_argument("--lock", default="upstream.lock")
        cmd_parser.add_argument("--out", default="skills/harness")
        cmd_parser.add_argument("--source", default=None)
        cmd_parser.add_argument("--guard-lock", default=GUARD_LOCK_PATH)
    bump_parser = sub.add_parser("bump", help="Move upstream.lock to the newest release tag.")
    bump_parser.add_argument("--lock", default="upstream.lock")
    bump_parser.add_argument("--tag", default=None)
    bump_parser.add_argument("--source", default=None)
    return parser


def main(argv):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "bump":
            old_tag, new_tag = bump(args.lock, tag=args.tag, repo=args.source)
            print(f"unchanged {old_tag}" if old_tag == new_tag else f"bumped {old_tag} {new_tag}")
            return 0
        lock = load_lock(args.lock)
        with tempfile.TemporaryDirectory(prefix="harness_sync_upstream_") as tmp_dir:
            upstream_dest = Path(tmp_dir) / "upstream"
            upstream_root = fetch_upstream(lock, upstream_dest, clone_url=args.source)

            if args.command == "sync":
                files = generate(upstream_root, lock)
                scan_secrets(files)
                guard = guard_lock(upstream_root, lock)
                write_output(files, args.out)
                write_guard_lock(guard, args.guard_lock)
                return 0

            diffs = check(upstream_root, lock, args.out)
            diffs += check_guard_lock(upstream_root, lock, args.guard_lock)
            for line in diffs:
                print(line)
            return 1 if diffs else 0
    except Exception as exc:
        if isinstance(exc, (HarnessSyncError, OSError)) and str(exc):
            message = str(exc)
        else:
            message = f"{type(exc).__name__}: {exc}"
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
