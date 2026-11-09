"""Map Hermes tool calls to the harness policy payload and back.

Everything here is pure except `evaluate`, which runs the policy binary with the
payload on stdin. Command text is only ever passed to the binary as data; it is
never executed by this module.

A guarded call that cannot be judged (wrong argument types, an unknown working
directory, a patch that names no file) is blocked, never sent on as an empty payload.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

BINARY_TIMEOUT_SECONDS = 10

# Directory trees that are never an acceptable "project", because the policy treats the
# working directory as the project root when no repository is found.
SYSTEM_ROOTS = (
    "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot", "/dev", "/proc", "/sys",
    "/root", "/run", "/var/lib", "/var/log", "/var/spool", "/var/run",
    "/system", "/library", "/applications", "/private/etc", "/private/var/db",
    "c:/windows", "c:/program files", "c:/program files (x86)", "c:/programdata",
)

# Text that makes a call target the guard itself, its pinned lock, or the switches that turn it off.
GUARD_TERMS = (
    "harness-guard", "harness_guard", "binaries.lock.json", "harness.toml", ".hermes/config.yaml", ".hermes/plugins",
)
_HERMES_ADMIN_RE = re.compile(r"\bhermes(?:\.exe)?\b[^;&|\n]*?\s(plugins|config|profile|gateway|hooks)\b", re.I)

# Hermes' own patch parser accepts zero or more spaces after the asterisks, so this does too.
_V4A_PATH_RE = re.compile(r"^\s*\*\*\*\s*(Update|Add|Delete)\s+File\s*:\s*(.+?)\s*$", re.I | re.M)
_V4A_MOVE_RE = re.compile(r"^\s*\*\*\*\s*Move\s+File\s*:\s*(.+?)\s*->\s*(.+?)\s*$", re.I | re.M)
_V4A_LOOSE_RE = re.compile(r"^\s*\*\*\*.*\bFile\b.*:", re.I | re.M)

# Directories under the home directory that are never a project.
HOME_NON_PROJECT = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".hermes", ".config")

_ENV_KEEP = (
    "PATH", "HOME", "USER", "USERNAME", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT",
    "SYSTEMDRIVE", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PATHEXT", "COMSPEC", "XDG_RUNTIME_DIR",
)
# Strictest upstream policies. Project files and the surrounding environment must not loosen them.
POLICY_ENV = {
    "HARNESS_DESTRUCTIVE_DELETE_POLICY": "ask",
    "HARNESS_PROTECTED_BRANCH_PUSH_POLICY": "ask",
    "HARNESS_DIRECT_PUSH_POLICY": "ask",
}

GUARDED_TOOLS = ("terminal", "process_manage", "read_file", "write_file", "patch")


class Unjudgeable(Exception):
    """The call cannot be judged safely; the caller blocks it with this reason."""


@dataclass(frozen=True)
class Verdict:
    action: str  # "allow", "block" or "ask"
    message: str = ""
    rule: str = ""


def _norm(text: str) -> str:
    return text.replace("\\", "/").lower()


def check_cwd(cwd: Optional[str], home: Optional[str] = None) -> str:
    """Return `cwd` if it can serve as a project directory, else raise Unjudgeable."""
    if not isinstance(cwd, str) or not cwd.strip() or "\x00" in cwd:
        raise Unjudgeable("the working directory is unknown")
    home = home if home is not None else str(Path.home())
    here = _norm(cwd).rstrip("/") or "/"
    if here == "/" or re.fullmatch(r"[a-z]:", here):
        raise Unjudgeable("the working directory is the filesystem root")
    if here == _norm(home).rstrip("/"):
        raise Unjudgeable("the working directory is the home directory; open a project folder first")
    for root in SYSTEM_ROOTS:
        if here == root or here.startswith(root + "/"):
            raise Unjudgeable(f"the working directory is inside a system location ({root})")
    base = _norm(home).rstrip("/") + "/"
    for name in HOME_NON_PROJECT:
        if here == base + name or here.startswith(base + name + "/"):
            raise Unjudgeable(f"the working directory is inside ~/{name}, which is not a project")
    return cwd


def absolute_path(value: Any, cwd: str, home: Optional[str] = None) -> str:
    """Absolute form of a path argument: `~` expanded, relative paths joined to `cwd`."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise Unjudgeable("a path argument is missing or not a string")
    home = home if home is not None else str(Path.home())
    text = value
    if text.startswith("~"):
        if text == "~" or text[1:2] in ("/", "\\"):
            text = home.rstrip("/\\") + text[1:]
        else:
            raise Unjudgeable("paths of the form ~user cannot be judged")
    if os.name == "nt" and text[:1] in ("/", "\\") and text[1:2] not in ("/", "\\"):
        text = os.path.splitdrive(cwd)[0] + text
    if not (os.path.isabs(text) or text.startswith("/")):
        text = os.path.join(cwd, text)
    if os.name == "nt":
        text = text.replace("\\", "/")
    return text


def _is_absolute_text(value: str) -> bool:
    return value.startswith(("~/", "/", "\\")) or value == "~" or bool(re.match(r"^[A-Za-z]:[\\/]", value))


def _payload(harness_tool: str, tool_input: dict, cwd: str, session_id: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": harness_tool,
        "tool_input": tool_input,
        "cwd": cwd,
        "session_id": session_id or "hermes",
    }


def v4a_paths(text: str) -> list[tuple[str, str]]:
    """(harness tool, path) for every file a V4A patch updates, adds, deletes or moves."""
    found = []
    headers = 0
    for kind, path in _V4A_PATH_RE.findall(text):
        found.append(("Write" if kind.lower() == "add" else "Edit", path))
        headers += 1
    for source, target in _V4A_MOVE_RE.findall(text):
        found.append(("Edit", source))
        found.append(("Write", target))
        headers += 1
    if len(_V4A_LOOSE_RE.findall(text)) != headers:
        raise Unjudgeable("a patch header is not understood")
    return found


def is_guarded(tool_name: str, args: Any) -> bool:
    if tool_name not in GUARDED_TOOLS:
        return False
    if tool_name == "process_manage":
        return isinstance(args, dict) and args.get("action") in ("write", "submit")
    return True


def to_payloads(tool_name: str, args: Any, cwd: Optional[str], session_id: str = "", home: Optional[str] = None):
    """Harness PreToolUse payloads for a call, or None when the tool is not guarded.

    Raises Unjudgeable when the call is guarded but cannot be judged.
    """
    if not is_guarded(tool_name, args):
        return None
    if not isinstance(args, dict):
        raise Unjudgeable("the tool arguments are not an object")
    if tool_name in ("terminal", "process_manage"):
        key = "command" if tool_name == "terminal" else "data"
        command = args.get(key)
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise Unjudgeable(f"the {key} is missing or not a string")
        workdir = args.get("workdir")
        if isinstance(workdir, str) and workdir.strip() and _is_absolute_text(workdir):
            project = check_cwd(absolute_path(workdir, "/", home), home)
        else:
            project = check_cwd(cwd, home)
            if workdir not in (None, ""):
                project = check_cwd(absolute_path(workdir, project, home), home)
        return [_payload("Bash", {"command": command}, project, session_id)]
    project = check_cwd(cwd, home)
    if tool_name == "read_file":
        path = absolute_path(args.get("path"), project, home)
        return [_payload("Read", {"file_path": path}, project, session_id)]
    if tool_name == "write_file":
        path = absolute_path(args.get("path"), project, home)
        content = args.get("content")
        if not isinstance(content, str):
            raise Unjudgeable("the file content is missing or not a string")
        return [_payload("Write", {"file_path": path, "content": content}, project, session_id)]
    # patch: replace mode names one path, V4A mode names paths inside the patch text.
    mode = args.get("mode")
    if mode not in (None, "", "replace", "patch"):
        raise Unjudgeable("the patch mode is not recognised")
    payloads = []
    if args.get("path") not in (None, ""):
        path = absolute_path(args.get("path"), project, home)
        edit = {"file_path": path}
        for key in ("old_string", "new_string"):
            if isinstance(args.get(key), str):
                edit[key] = args[key]
        payloads.append(_payload("Edit", edit, project, session_id))
    patch_text = args.get("patch")
    if patch_text not in (None, ""):
        if not isinstance(patch_text, str):
            raise Unjudgeable("the patch text is not a string")
        named = v4a_paths(patch_text)
        if not named:
            raise Unjudgeable("the patch names no file")
        for harness_tool, path in named:
            payloads.append(
                _payload(harness_tool, {"file_path": absolute_path(path, project, home)}, project, session_id)
            )
    if not payloads:
        raise Unjudgeable("the patch call names no file")
    return payloads


def expand_shell_text(text: str, home: str, hermes_home: str) -> str:
    """Resolve ~, $HOME and $HERMES_HOME spellings so path terms can be matched."""
    for name, value in (("HOME", home), ("HERMES_HOME", hermes_home)):
        text = text.replace("${" + name + "}", value).replace("$" + name, value)
    return re.sub(r"(^|[\s=:'\"])~(?=/|$|\s)", lambda m: m.group(1) + home, text)


def guard_reference(payloads: list[dict], extra_terms: tuple[str, ...] = (), home: Optional[str] = None,
                    hermes_home: Optional[str] = None) -> Optional[str]:
    """The protected term a call refers to, if any (the guard, its lock, its off switches).

    Only text that names or runs something is checked: commands, process input and file paths.
    File contents and edit strings are not.
    """
    terms = tuple(_norm(t) for t in GUARD_TERMS + tuple(extra_terms) if t)
    home = home if home is not None else str(Path.home())
    hermes_home = hermes_home if hermes_home is not None else str(Path(home) / ".hermes")
    for payload in payloads:
        keys = ("command",) if payload["tool_name"] == "Bash" else ("file_path",)
        for key in keys:
            value = payload["tool_input"].get(key)
            if not isinstance(value, str):
                continue
            if payload["tool_name"] == "Bash":
                value = expand_shell_text(value, home, hermes_home)
            text = _norm(value)
            for term in terms:
                if term in text:
                    return term
            if payload["tool_name"] == "Bash" and _HERMES_ADMIN_RE.search(value):
                return "hermes administration command"
    return None


def parse_verdict(stdout: str, returncode: int) -> Verdict:
    """Interpret the binary's answer. Only an explicit allow is an allow."""
    text = (stdout or "").strip()
    body: Any = None
    if text:
        try:
            body = json.loads(text)
        except ValueError:
            return Verdict("block", "harness-guard could not read the policy answer")
    output = body.get("hookSpecificOutput") if isinstance(body, dict) else None
    decision = str(output.get("permissionDecision") or "").lower() if isinstance(output, dict) else ""
    reason = str(output.get("permissionDecisionReason") or "") if isinstance(output, dict) else ""
    if decision == "deny" or returncode == 2:
        return Verdict("block", reason or "Blocked by harness policy.", _rule_of(reason))
    if decision == "ask":
        return Verdict("ask", reason or "Confirmation required by harness policy.", _rule_of(reason))
    if returncode != 0:
        return Verdict("block", f"harness-guard policy binary failed (exit {returncode})")
    if not text:
        return Verdict("allow")
    if decision == "allow":
        return Verdict("allow")
    return Verdict("block", "harness-guard did not recognise the policy answer")


def _rule_of(reason: str) -> str:
    return reason.split(":", 1)[0] if reason.startswith("RUNTIME_FLOOR:") else ""


def clean_env(environ=None) -> dict:
    """Minimal environment for the policy binary, with the strictest policy knobs."""
    environ = os.environ if environ is None else environ
    env = {key: environ[key] for key in _ENV_KEEP if key in environ}
    env.update(POLICY_ENV)
    return env


def evaluate(payload: dict, binary: Path, state_dir: Path, runner=subprocess.run) -> Verdict:
    """Run the policy binary on `payload`. Any failure blocks."""
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        result = runner(
            [str(binary), "hook", "pre-tool"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(state_dir),
            timeout=BINARY_TIMEOUT_SECONDS,
            env=clean_env(),
        )
    except Exception as exc:
        return Verdict("block", f"harness-guard policy binary unavailable ({type(exc).__name__})")
    return parse_verdict(result.stdout, result.returncode)


def judge(payloads: list[dict], binary: Path, state_dir: Path, runner=subprocess.run) -> Verdict:
    """Strictest verdict over all payloads: block, then ask, then allow."""
    worst = Verdict("allow")
    for payload in payloads:
        verdict = evaluate(payload, binary, state_dir, runner=runner)
        if verdict.action == "block":
            return verdict
        if verdict.action == "ask" and worst.action == "allow":
            worst = verdict
    return worst


def to_hermes_directive(verdict: Verdict) -> Optional[dict]:
    """Translate a verdict to a Hermes pre_tool_call directive (None means proceed).

    The harness asks a human before some actions. Hermes' approval gate is not always a
    human (the default `smart` mode lets an auxiliary model approve), so an ask is a block.
    """
    if verdict.action == "block":
        return {"action": "block", "message": verdict.message or "Blocked by harness-guard."}
    if verdict.action == "ask":
        message = verdict.message or "Confirmation required by harness policy."
        return {
            "action": "block",
            "message": f"{message} This needs the user's confirmation: stop and ask the user to run it themselves.",
        }
    return None


@dataclass(frozen=True)
class Decision:
    """What the guard decided for one call: `kind` is unguarded, unjudgeable, refused or verdict."""

    kind: str
    message: str = ""
    verdict: Optional[Verdict] = None

    @property
    def label(self) -> str:
        return self.verdict.action if self.kind == "verdict" and self.verdict else self.kind


def decide(
    tool_name: str,
    args: Any,
    cwd: Optional[str],
    session_id: str,
    run_policy: Callable[[list], Verdict],
    extra_terms: tuple[str, ...] = (),
    home: Optional[str] = None,
    hermes_home: Optional[str] = None,
) -> Decision:
    """The whole pipeline: guarded or not, judgeable or not, protected references, then the policy."""
    if not is_guarded(tool_name, args):
        return Decision("unguarded")
    try:
        payloads = to_payloads(tool_name, args, cwd, session_id, home)
    except Unjudgeable as exc:
        return Decision("unjudgeable", f"harness-guard cannot judge this call ({exc}); it was blocked.")
    term = guard_reference(payloads, extra_terms, home, hermes_home)
    if term:
        return Decision(
            "refused",
            f"This call refers to the harness guard or its settings ({term}). "
            "Ask the user to change those, outside the agent.",
        )
    return Decision("verdict", verdict=run_policy(payloads))


def directive_for(decision: Decision) -> Optional[dict]:
    """Hermes pre_tool_call directive for a decision (None means proceed)."""
    if decision.kind == "unguarded":
        return None
    if decision.kind in ("unjudgeable", "refused"):
        return {"action": "block", "message": decision.message}
    return to_hermes_directive(decision.verdict)


def resolve_cwd(task_id: Optional[str], lookups: tuple[Callable[[str], Optional[str]], ...]) -> Optional[str]:
    """First absolute directory from `lookups`, in order. There is no fallback: unknown stays unknown."""
    for lookup in lookups:
        try:
            found = lookup(task_id)
        except Exception:
            found = None
        if isinstance(found, str) and found.strip() and (os.path.isabs(found) or found.startswith("/")):
            return found
    return None
