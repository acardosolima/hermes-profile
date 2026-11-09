"""Locate, download and verify the pinned upstream policy binary.

The lock file `binaries.lock.json` is written by tools/harness_sync.py. It pins
the upstream commit and the sha256 of each platform binary. A binary is only
used when its hash matches the lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

LOCK_NAME = "binaries.lock.json"
DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_BINARY_BYTES = 64 * 1024 * 1024

_REPO_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?")


class BinaryError(Exception):
    pass


def platform_key(system: Optional[str] = None, machine: Optional[str] = None) -> str:
    system = (system or sys.platform).lower()
    machine = (machine or platform.machine()).lower()
    if system.startswith("linux"):
        os_name = "linux"
    elif system == "darwin":
        os_name = "darwin"
    elif system in ("win32", "cygwin", "windows"):
        os_name = "windows"
    else:
        raise BinaryError(f"unsupported operating system: {system}")
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise BinaryError(f"unsupported architecture: {machine}")
    return f"{os_name}-{arch}"


def load_lock(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BinaryError(f"cannot read {LOCK_NAME}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("binaries"), dict):
        raise BinaryError(f"{LOCK_NAME} has no binaries table")
    return data


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_url(lock: dict, relative_file: str) -> str:
    match = _REPO_RE.fullmatch(str(lock.get("repo", "")))
    sha = str(lock.get("sha", ""))
    if not match or not re.fullmatch(r"[0-9a-f]{40}", sha) or ".." in relative_file.split("/"):
        raise BinaryError("lock does not describe a downloadable GitHub release")
    owner, name = match.groups()
    if {owner, name} & {".", ".."}:
        raise BinaryError("lock does not describe a downloadable GitHub release")
    return f"https://raw.githubusercontent.com/{owner}/{name}/{sha}/{relative_file}"


def _fetch(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "harness-guard"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        total = 0
        with open(destination, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    return
                total += len(chunk)
                if total > MAX_BINARY_BYTES:
                    raise BinaryError("binary is larger than the allowed size")
                handle.write(chunk)


def ensure_binary(lock: dict, cache_root: Path, key: Optional[str] = None, fetch=_fetch) -> Path:
    """Return a verified binary path, downloading it when missing or when its hash differs.

    The cached file is hashed on every call, so a replaced binary is never returned.
    """
    try:
        return _ensure(lock, cache_root, key, fetch)
    except OSError as exc:
        raise BinaryError(f"binary cache unusable ({type(exc).__name__})") from exc


def _ensure(lock: dict, cache_root: Path, key: Optional[str], fetch) -> Path:
    key = key or platform_key()
    entry = lock["binaries"].get(key)
    if not isinstance(entry, dict) or not entry.get("sha256") or not entry.get("file"):
        raise BinaryError(f"no pinned binary for {key}")
    expected = str(entry["sha256"])
    target = Path(cache_root) / str(lock.get("sha", "unpinned")) / os.path.basename(str(entry["file"]))
    if target.is_file() and sha256_of(target) == expected:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=".download-", dir=str(target.parent))
    os.close(handle)
    temp = Path(temp_name)
    try:
        try:
            fetch(download_url(lock, str(entry["file"])), temp)
        except BinaryError:
            raise
        except Exception as exc:
            raise BinaryError(f"download failed ({type(exc).__name__})") from exc
        if sha256_of(temp) != expected:
            raise BinaryError("downloaded binary does not match the pinned hash")
        temp.chmod(0o755)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return target
