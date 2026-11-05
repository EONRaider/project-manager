"""Shared plumbing for the hook scripts: running a hook, building a decision, splitting a command.

Each hook runs as a fresh ``python3`` process on every matching tool call, so this module imports
only what its callers already need and does no work at import time.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    Decide = Callable[[object], dict[str, Any] | None]

# Commands that run the command after them, so the real command is the next word.
WRAPPERS = frozenset(
    {"env", "command", "exec", "sudo", "time", "nice", "nohup", "xargs"}
)

_PUNCTUATION = ";&|<>()\n"
_SEPARATOR_CHARS = frozenset(";&|()\n")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def segments(command: str) -> list[list[str]]:
    """Split a shell command into simple commands, one token list each.

    Splits on ``;``, ``&``, ``|``, their doubled forms, brackets and unquoted newlines. Redirection
    operators stay in the segment as their own tokens. Quotes are removed the way the shell would.

    Args:
        command: A shell command line, possibly several lines long.

    Returns:
        The non-empty segments, in order.

    Raises:
        ValueError: When the command has an unclosed quote.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    result: list[list[str]] = [[]]
    for token in lexer:
        if set(token) <= _SEPARATOR_CHARS:
            result.append([])
        else:
            result[-1].append(token)
    return [segment for segment in result if segment]


def command_start(segment: list[str]) -> int:
    """The index of the command a segment runs, past variable assignments and wrapper words.

    Args:
        segment: One simple command's tokens.

    Returns:
        The index of the command's name, or ``len(segment)`` when there is none.
    """
    for index, token in enumerate(segment):
        if token in WRAPPERS or _ASSIGNMENT.match(token):
            continue
        return index
    return len(segment)


def program(token: str) -> str:
    """A command name without its folder: ``/usr/bin/gh`` becomes ``gh``."""
    return os.path.basename(token)


def permission(decision: str, reason: str) -> dict[str, Any]:
    """A PreToolUse decision document.

    Args:
        decision: ``"deny"`` or ``"ask"``.
        reason: The text shown to the model and the user.

    Returns:
        The hook output.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }


def run(prefix: str, decide: Decide, error_exit: int) -> int:
    """Read one hook input on stdin, decide, and print the output when there is one.

    Any error is reported as one stderr line starting with ``prefix`` and the hook fails open.

    Args:
        prefix: The hook's name, which starts every stderr line.
        decide: Maps the decoded input to an output document, or ``None`` for silence.
        error_exit: The exit code after an error: 1 shows it as a non-blocking hook error, 0
            keeps it quiet.

    Returns:
        0 normally, ``error_exit`` after an error.
    """
    try:
        output = decide(json.loads(sys.stdin.read()))
    except Exception as exc:  # noqa: BLE001 -- fail open on any internal error
        detail = " ".join(str(exc).split())
        print(
            f"{prefix}: skipped after an internal error: {type(exc).__name__}: {detail}",
            file=sys.stderr,
        )
        return error_exit
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0
