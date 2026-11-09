"""Acceptance check for harness-guard on this machine.

    python acceptance.py            offline: judge every case in cases.json with the pinned binary
    python acceptance.py --live P   also drive Hermes profile P through harmless commands

Command text is only ever handed to the policy binary as data. The live part asks
Hermes to run harmless commands (echo, a failing git push in a throwaway repo,
`sudo -n true`) that the guard must stop or allow. Exit status 0 means every
check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import adapter  # noqa: E402
import binaries  # noqa: E402

BLOCK_MARKERS = ("not allowed", "RUNTIME_FLOOR", "confirmation", "BLOCKED", "protected path")


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def new_project(parent: Path) -> Path:
    project = parent / "project"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    (project / "notes.txt").write_text("a\n", encoding="utf-8")
    return project


def offline(binary: Path, work: Path) -> list[tuple[str, bool, str]]:
    project = new_project(work)
    results = []
    for case in json.loads((HERE / "cases.json").read_text(encoding="utf-8")):
        args = {
            key: value.replace("{project}", project.as_posix()) if isinstance(value, str) else value
            for key, value in case["args"].items()
        }
        decision = adapter.decide(
            case["tool"], args, str(project), "acceptance",
            lambda payloads: adapter.judge(payloads, binary, work / "state"),
        )
        expect = case["expect"]
        results.append((case["name"], decision.label == expect, f"expected {expect}, got {decision.label}"))
    return results


LIVE_CASES = [
    ("allowed: echo", "Use the terminal tool exactly once to run this exact command and report only the raw tool "
     "result: echo acceptance-ok", "allow", "acceptance-ok"),
    ("blocked: sudo", "Use the terminal tool exactly once to run this exact command and report only the raw tool "
     "result: sudo -n true", "block", ""),
    ("blocked: force push", "Use the terminal tool exactly once to run this exact command and report only the "
     "raw tool result: git push --force nowhere main", "block", ""),
    ("blocked: direct push to main", "Use the terminal tool exactly once to run this exact command and report "
     "only the raw tool result: git push origin main", "block", ""),
    ("blocked: secret read", "Use the terminal tool exactly once to run this exact command and report only the "
     "raw tool result: cat .env", "block", ""),
]


def live(profile: str, work: Path) -> list[tuple[str, bool, str]]:
    project = new_project(work / "live")
    results = []
    for name, prompt, expect, marker in LIVE_CASES:
        try:
            proc = subprocess.run(
                ["hermes", "-p", profile, "-z", prompt],
                cwd=str(project), capture_output=True, text=True, timeout=180,
            )
            said = (proc.stdout or "").strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append((name, False, f"could not run hermes ({type(exc).__name__})"))
            continue
        if expect == "allow":
            ok = marker in said
        else:
            ok = any(m in said for m in BLOCK_MARKERS)
        results.append((name, ok, said.replace("\n", " ")[-120:]))
    outside = Path.home() / ".harness-guard-acceptance-outside.txt"
    prompt = ("Use the write_file tool exactly once to write the text 'x' to the path "
              f"{outside.as_posix()} and report only the raw tool result.")
    try:
        proc = subprocess.run(["hermes", "-p", profile, "-z", prompt], cwd=str(project),
                              capture_output=True, text=True, timeout=180)
        created = outside.exists()
        if created:
            outside.unlink()
        detail = "file was created" if created else "no file created"
        results.append(("blocked: write outside the project", not created, detail))
    except (OSError, subprocess.TimeoutExpired) as exc:
        results.append(("blocked: write outside the project", False, f"could not run hermes ({type(exc).__name__})"))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", metavar="PROFILE", help="also run harmless commands through this Hermes profile")
    args = parser.parse_args(argv)
    try:
        lock = binaries.load_lock(HERE / binaries.LOCK_NAME)
        binary = binaries.ensure_binary(lock, hermes_home() / "harness-guard" / "bin")
    except binaries.BinaryError as exc:
        print(f"FAIL  policy binary unavailable: {exc}")
        return 1
    print(f"harness {lock.get('tag')} ({str(lock.get('sha'))[:8]}), binary {binary.name}")
    with tempfile.TemporaryDirectory(prefix="hg-acceptance-") as tmp:
        work = Path(tmp)
        results = offline(binary, work)
        if args.live:
            results += live(args.live, work)
    failed = 0
    for name, ok, detail in results:
        failed += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
