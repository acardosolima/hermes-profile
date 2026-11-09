"""harness-guard: harness guardrail rules for Hermes tool calls.

Registers a `pre_tool_call` hook. Terminal, process input, file read, file write and
patch calls are mapped to the harness payload and judged by the pinned upstream policy
binary. A deny becomes a Hermes block, and so does an ask, because Hermes' approval gate
is not always a human. A call that cannot be judged is blocked, and so is every guarded
call when the binary is missing, fails its hash check or times out (fail closed).

The guard has no settings. It reads nothing an agent can change: the only off switch is
`hermes plugins disable harness-guard`, and tool calls that mention the guard, its lock or
Hermes' plugin and config commands are blocked.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

try:
    from . import adapter, binaries
except ImportError:  # imported as top-level modules by the tests
    import adapter
    import binaries

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent
_LOCK = threading.Lock()


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        import os

        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _matching(table, task):
    """Value in `table` whose key is the task id or ends with it (keys are profile-qualified)."""
    if not task:
        return None
    for key, value in dict(table).items():
        if key == task or str(key).endswith(":" + task):
            return value
    return None


def _cwd_lookups():
    """Where the terminal tool itself gets its directory, in the same order.

    The directory recorded after the session's last command (follows `cd`), then the scoped
    default that the first call will use. The live environment's directory is not used,
    because it can belong to another session.
    """
    try:
        from tools import terminal_tool as tt
    except Exception:
        return ()
    return (
        lambda task: tt.get_session_cwd(task) if task else None,
        lambda task: _matching(getattr(tt, "_session_cwd", {}), task),
        lambda task: tt._tenv("TERMINAL_CWD"),
        lambda task: tt._get_env_config().get("cwd"),
    )


def _binary() -> Path:
    """Verified binary path. The hash is checked on every call; raises BinaryError."""
    with _LOCK:
        lock = binaries.load_lock(_PLUGIN_DIR / binaries.LOCK_NAME)
        return binaries.ensure_binary(lock, _hermes_home() / "harness-guard" / "bin")


def _protected_terms() -> tuple[str, ...]:
    home = _hermes_home().as_posix()
    default_home = (Path.home() / ".hermes").as_posix()
    terms = {_PLUGIN_DIR.as_posix(), f"{home}/plugins", f"{home}/config.yaml", f"{default_home}/config.yaml"}
    return tuple(sorted(terms))


def _block(message: str) -> dict:
    return {"action": "block", "message": message}


def on_pre_tool_call(tool_name=None, args=None, task_id=None, session_id=None, **_ignored):
    try:
        return _judge(tool_name, args, task_id, session_id)
    except Exception as exc:  # a bug here must block the call with a readable reason
        return _block(f"harness-guard failed ({type(exc).__name__}); the call was blocked.")


def _run_policy(payloads):
    try:
        binary = _binary()
    except binaries.BinaryError as exc:
        return adapter.Verdict(
            "block",
            f"harness-guard cannot run ({exc}). Fix it, or ask the user to disable the plugin with "
            "`hermes plugins disable harness-guard`.",
        )
    return adapter.judge(payloads, binary, _hermes_home() / "harness-guard" / "state")


def _judge(tool_name, args, task_id, session_id):
    if not adapter.is_guarded(tool_name, args):
        return None
    cwd = adapter.resolve_cwd(task_id, _cwd_lookups())
    decision = adapter.decide(
        tool_name, args, cwd, session_id or "", _run_policy, _protected_terms(), hermes_home=str(_hermes_home())
    )
    return adapter.directive_for(decision)


def _prefetch():
    try:
        _binary()
    except Exception as exc:
        logger.warning("harness-guard could not prepare its policy binary: %s", exc)


def register(ctx):
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    threading.Thread(target=_prefetch, name="harness-guard-prefetch", daemon=True).start()
