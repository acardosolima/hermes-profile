"""Shared helpers for the harness_sync test suite. Standard library only."""

import atexit
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TESTS_DIR.parent
CLI_PATH = TOOLS_DIR / "harness_sync.py"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

TAG = "v1.2.3"
ALLOWLIST_NAMES = (
    "harness-plan",
    "harness-work",
    "harness-review",
    "harness-sync",
    "harness-setup",
    "harness-loop",
    "harness-release",
    "breezing",
)
PREAMBLE_START = "<!-- harness-sync:preamble:start -->"
PREAMBLE_END = "<!-- harness-sync:preamble:end -->"
UTF8_BOM = b"\xef\xbb\xbf"
UNRELATED_SHA = "1" * 40
LONG_DESCRIPTION = "abcdefghij" * 150

SECRET_POSITIVE = (
    ("anthropic key at minimum length", "sk-ant-" + "a1b2c3d4e5"),
    ("github token at minimum length", "ghp_" + "A1b2C3d4E5f6G7h8I9j0"),
    ("aws access key id", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("slack bot token", "xoxb-" + "1234567890"),
    ("slack app token", "xoxa-" + "abcdefghij"),
    ("slack user token", "xoxp-" + "1234567890abcdef"),
    ("rsa private key header", "-----BEGIN RSA PRIVATE KEY-----"),
    ("openssh private key header", "-----BEGIN OPENSSH PRIVATE KEY-----"),
)

SECRET_NEGATIVE = (
    ("anthropic prefix with 9 token characters", "sk-ant-" + "a" * 9),
    ("github prefix with 19 characters", "ghp_" + "A" * 19),
    ("aws prefix with 15 uppercase characters", "AKIA" + "A" * 15),
    ("aws prefix with 16 lowercase characters", "AKIA" + "a" * 16),
    ("slack bot prefix with 9 characters", "xoxb-" + "1" * 9),
    ("slack refresh token prefix", "xoxr-" + "1234567890"),
    ("certificate header", "-----BEGIN CERTIFICATE-----"),
)

_HARNESS_PLAN = """---
allowed-tools: "Read, Write"
name: harness-plan
description: Plan tasks (base text)
description-en: Plan tasks in English.
description-ja: タスクを計画する
kind: skill
---
# Harness plan

Read the procedure in ${CLAUDE_SKILL_DIR}/references/plan.md first.
Skill root is ${CLAUDE_SKILL_DIR} here.
Run the checker with ${HARNESS_PLUGIN_ROOT}/scripts/plan-check.sh before writing.
A vendor token ${CLAUDE_FOO} stays in this line.
Mention: scripts/plan-check.sh is the same helper.
"""

_PLAN_REFERENCE = (
    "# Plan procedure\n"
    "\n"
    "Follow the steps in ${CLAUDE_SKILL_DIR}/references/detail.md.\n"
    "Render with ${CLAUDE_PLUGIN_ROOT}/scripts/plan-check.sh when needed.\n"
)

_PLAN_DETAIL = "# Detail\n\nNumbered step list.\n"

_PLAN_DATA = '{"root": "${HARNESS_PLUGIN_ROOT}/docs/", "note": "kept verbatim"}\n'

_HARNESS_WORK = """---
name: harness-work
description: Work through tasks
allowed-tools: Bash
kind: skill
---
# Harness work

Run ${CLAUDE_PLUGIN_ROOT}/scripts/run-tasks.sh to start the loop.
Batch details live in references/work-detail.md.
"""

_WORK_DETAIL = (
    "# Work detail\n\nBatch rendering: ${HARNESS_PLUGIN_ROOT}/scripts/render.py --all\n"
)

_HARNESS_REVIEW = """---
name: harness-review
description: "Review: diffs"
kind: skill
---
# Harness review

Checklist: ${CLAUDE_SKILL_DIR}/references/checklist.md
"""

_REVIEW_CHECKLIST = "# Checklist\r\n\r\n- Check the diff.\r\n"

_HARNESS_SYNC = (
    "---\r\n"
    "name: harness-sync\r\n"
    "description: Sync the harness\r\n"
    "kind: skill\r\n"
    "---\r\n"
    "# Harness sync\r\n"
    "\r\n"
    "Sync helper: ${CLAUDE_PLUGIN_ROOT}/scripts/common.sh\r\n"
)

_HARNESS_SETUP = (
    "---\n"
    "name: harness-setup\n"
    "description: Set up the harness\n"
    "kind: skill\n"
    "---\n"
    "# Harness setup\n"
    "\n"
    "No helper scripts.\n"
)

_HARNESS_LOOP = (
    "---\n"
    "name: harness-loop\n"
    "description: Loop short\n"
    "description-en: " + LONG_DESCRIPTION + "\n"
    "kind: skill\n"
    "---\n"
    "# Harness loop\n"
    "\n"
    "Loop body.\n"
)

_HARNESS_RELEASE = (
    "---\n"
    "name: harness-release\n"
    "description: Release the harness\n"
    "kind: skill\n"
    "---\n"
    "# Harness release\n"
    "\n"
    "Follow ${CLAUDE_SKILL_DIR}/references/steps.md.\n"
)

_RELEASE_STEPS = "# Steps\n\n1. Tag the release.\n"

_BREEZING = (
    "---\n"
    "name: breezing\n"
    "description: Breezing team run\n"
    "kind: skill\n"
    "---\n"
    "# Breezing\n"
    "\n"
    "Team run body.\n"
)

_CURSOR_ASK = (
    "---\n"
    "name: cursor-ask\n"
    "description: Ask cursor\n"
    "kind: skill\n"
    "---\n"
    "# Cursor ask\n"
    "\n"
    "Helper: ${HARNESS_PLUGIN_ROOT}/scripts/cursor-only.sh\n"
)

_SCRIPTS = {
    "scripts/plan-check.sh": "#!/usr/bin/env bash\necho plan-check\n",
    "scripts/run-tasks.sh": (
        "#!/usr/bin/env bash\n"
        "# Loads scripts/common.sh before running.\n"
        "source scripts/common.sh\n"
    ),
    "scripts/common.sh": 'log() { echo "$*"; }\n',
    "scripts/render.py": "# Delegates formatting to scripts/format-util.sh\nprint('render')\n",
    "scripts/format-util.sh": "echo format\n",
    "scripts/unused-helper.sh": "echo unused\n",
    "scripts/cursor-only.sh": "echo cursor\n",
}


def fixture_files():
    """Return the upstream fixture as a mapping of posix relpath to bytes."""
    text_files = {
        "skills/harness-plan/SKILL.md": _HARNESS_PLAN,
        "skills/harness-plan/references/plan.md": _PLAN_REFERENCE,
        "skills/harness-plan/references/detail.md": _PLAN_DETAIL,
        "skills/harness-work/SKILL.md": _HARNESS_WORK,
        "skills/harness-work/references/work-detail.md": _WORK_DETAIL,
        "skills/harness-setup/SKILL.md": _HARNESS_SETUP,
        "skills/harness-loop/SKILL.md": _HARNESS_LOOP,
        "skills/harness-release/SKILL.md": _HARNESS_RELEASE,
        "skills/harness-release/references/steps.md": _RELEASE_STEPS,
        "skills/breezing/SKILL.md": _BREEZING,
        "skills/cursor-ask/SKILL.md": _CURSOR_ASK,
    }
    files = {rel: text.encode("utf-8") for rel, text in text_files.items()}
    files["skills/harness-plan/references/data.json"] = _PLAN_DATA.encode("utf-8")
    files["skills/harness-review/SKILL.md"] = UTF8_BOM + _HARNESS_REVIEW.encode("utf-8")
    files["skills/harness-review/references/checklist.md"] = _REVIEW_CHECKLIST.encode("utf-8")
    files["skills/harness-sync/SKILL.md"] = _HARNESS_SYNC.encode("utf-8")
    for rel, text in _SCRIPTS.items():
        files[rel] = text.encode("utf-8")
    return files


def isolated_env():
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["PYTHONUTF8"] = "1"
    return env


_IDENTITY = [
    "-c", "user.name=fixture",
    "-c", "user.email=fixture@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "tag.gpgSign=false",
]


def git_run(args, cwd, identity=False):
    cmd = ["git", "-c", "core.autocrlf=false"]
    if identity:
        cmd += _IDENTITY
    subprocess.run(
        cmd + list(args),
        cwd=str(cwd),
        env=isolated_env(),
        check=True,
        capture_output=True,
    )


def git_output(args, cwd):
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=str(cwd),
        env=isolated_env(),
        check=True,
        capture_output=True,
    )
    return proc.stdout.decode("utf-8").strip()


def put(root, rel, data):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def make_upstream(parent, overrides=None):
    """Create a git repo with one annotated tag. Returns (path, tag, commit sha)."""
    root = Path(parent) / "upstream"
    files = fixture_files()
    files.update(overrides or {})
    for rel, data in files.items():
        put(root, rel, data)
    git_run(["init", "-q"], root)
    git_run(["add", "-A"], root)
    git_run(["commit", "-q", "-m", "fixture"], root, identity=True)
    git_run(["tag", "-a", TAG, "-m", "fixture tag"], root, identity=True)
    sha = git_output(["rev-parse", TAG + "^{commit}"], root)
    return root, TAG, sha


_SHARED = {}


def shared_upstream():
    """Build the read-only upstream once per test process."""
    if "upstream" not in _SHARED:
        base = Path(tempfile.mkdtemp(prefix="hs-fixture-"))
        atexit.register(_rm, base)
        _SHARED["upstream"] = make_upstream(base)
    return _SHARED["upstream"]


def copy_upstream(src, dst):
    shutil.copytree(str(src), str(dst))
    return Path(dst)


def lock_for(root, tag, sha):
    return {"repo": str(root), "tag": tag, "sha": sha}


def write_lock(path, lock):
    Path(path).write_text(json.dumps(lock), encoding="utf-8")


def harness_sync():
    return importlib.import_module("harness_sync")


def snapshot(directory):
    base = Path(directory)
    if not base.exists():
        return {}
    return {
        p.relative_to(base).as_posix(): p.read_bytes()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


def norm_line(line):
    kind, _, rest = line.partition(" ")
    return kind + " " + rest.replace("\\", "/")


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(data):
    """Return (list of (key, value) pairs, body text) from a generated file."""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    lines = text.lstrip("﻿").split("\n")
    if lines[0].rstrip("\r") != "---":
        raise AssertionError("missing opening frontmatter line")
    end = None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r") == "---":
            end = index
            break
    if end is None:
        raise AssertionError("frontmatter is not closed")
    pairs = []
    for raw in lines[1:end]:
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise AssertionError("frontmatter line without colon: %r" % line)
        pairs.append((key.strip(), _unquote(value.strip())))
    body = "\n".join(lines[end + 1:])
    return pairs, body


def preamble_block(text):
    start = text.index(PREAMBLE_START)
    end = text.index(PREAMBLE_END) + len(PREAMBLE_END)
    return text[start:end]


def _force_remove(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rm(path):
    path = Path(path)
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(str(path), onexc=lambda func, p, exc: _force_remove(func, p, exc))
    else:
        shutil.rmtree(str(path), onerror=_force_remove)


class TempCase(unittest.TestCase):
    """Gives each test a private temp dir and the module under test."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="hs-test-"))
        self.addCleanup(_rm, self.tmp)
        self.hs = harness_sync()
