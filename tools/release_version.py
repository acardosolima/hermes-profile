"""Decide the next profile version from conventional commits."""

from __future__ import annotations

import argparse
import re
import sys

_SUBJECT = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<breaking>!)?: (?P<subject>.+)$"
)
_PATCH = {"fix", "config", "chore", "perf", "refactor"}
_IGNORE = {"docs", "ci", "test", "style", "build"}


def parse_subject(subject: str, body: str) -> tuple[str, str, bool]:
    match = _SUBJECT.match(subject.strip())
    if not match:
        raise ValueError(f"not a conventional commit: {subject}")
    breaking = bool(match.group("breaking")) or "\nBREAKING CHANGE:" in f"\n{body}"
    return match.group("type"), match.group("subject"), breaking


def plan_version(
    current: str, commits: list[tuple[str, str, str]], has_tags: bool
) -> tuple[str, str]:
    if not has_tags:
        return ("publish", current)
    rank = 0
    for ctype, subject, body in commits:
        if ctype == "chore" and subject.startswith("release v"):
            continue
        if ctype in _IGNORE:
            continue
        breaking = "\nBREAKING CHANGE:" in f"\n{body}"
        if ctype == "feat" and not breaking:
            rank = max(rank, 2)
        elif ctype in _PATCH and not breaking:
            rank = max(rank, 1)
        elif breaking and (ctype == "feat" or ctype in _PATCH):
            rank = max(rank, 3)
        else:
            raise ValueError(f"unknown commit type: {ctype}")
    if rank == 0:
        return ("none", current)
    major, minor, patch = (int(part) for part in current.split("."))
    if rank == 3:
        return ("bump", f"{major + 1}.0.0")
    if rank == 2:
        return ("bump", f"{major}.{minor + 1}.0")
    return ("bump", f"{major}.{minor}.{patch + 1}")


def set_version_line(text: str, version: str) -> str:
    lines = text.splitlines(keepends=True)
    found = False
    out = []
    for line in lines:
        if not found and line.startswith("version:"):
            newline = "\n" if line.endswith("\n") else ""
            out.append(f"version: {version}{newline}")
            found = True
        else:
            out.append(line)
    if not found:
        raise ValueError("distribution.yaml has no version: line")
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--current", required=True)
    parser.add_argument("--has-tags", action="store_true")
    parser.add_argument("--commits-file")
    parser.add_argument("--version")
    parser.add_argument("--path", default="distribution.yaml")
    args = parser.parse_args(argv)
    if args.command == "apply":
        if not args.version:
            raise SystemExit("apply requires --version")
        path_text = open(args.path, encoding="utf-8").read()
        open(args.path, "w", encoding="utf-8").write(set_version_line(path_text, args.version))
        print(args.version)
        return 0
    commits: list[tuple[str, str, str]] = []
    if args.commits_file:
        raw = open(args.commits_file, encoding="utf-8").read()
        blocks = [block for block in raw.split("\n---\n") if block.strip()]
        for block in blocks:
            head, _, body = block.partition("\n")
            ctype, subject, _breaking = parse_subject(head, body)
            commits.append((ctype, subject, body))
    action, version = plan_version(args.current, commits, args.has_tags)
    print(f"{action} {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
