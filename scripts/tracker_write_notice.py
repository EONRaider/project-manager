"""Reminder after a GitHub write: tell the PM. PostToolUse, settings flag ``tracker_write_notice``.

A session that writes to the tracker sends the PM a one-line notice of what changed and where the
record is. This hook only reminds; it decides nothing and never blocks.

It fires on two kinds of tool call:

- A GitHub MCP write tool, whatever the server is called in this install: the tool name is
  matched in full against ``mcp__<server>__<tool>`` for the tools in :data:`MCP_WRITE_TOOLS`.
- A ``Bash`` command with a segment that runs a ``gh`` write: an ``issue`` or ``pr`` subcommand
  that changes something, a ``project`` subcommand that changes something, or ``gh api`` with a
  GraphQL mutation or a writing HTTP method.

It stays silent inside a subagent (the input carries ``agent_id``), since a subagent owes no
notice; its dispatcher sends one. It never reads the transcript and never repeats any tool input.

Fail-open policy: every path exits 0. An error prints one stderr line starting
``tracker_write_notice:``.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from collections.abc import Mapping
from typing import Any

import pm_settings

PREFIX = "tracker_write_notice"

MCP_WRITE_TOOLS = (
    "issue_write",
    "add_issue_comment",
    "update_issue_comment",
    "sub_issue_write",
    "create_pull_request",
    "update_pull_request",
    "pull_request_review_write",
    "add_comment_to_pending_review",
    "add_reply_to_pull_request_comment",
    "merge_pull_request",
)

MCP_PATTERN = re.compile(r"mcp__.+__(?:" + "|".join(MCP_WRITE_TOOLS) + r")")

GH_ISSUE_PR_WRITES = frozenset(
    {
        "create", "edit", "comment", "close", "reopen", "delete", "lock", "unlock", "pin",
        "unpin", "transfer", "develop", "merge", "ready", "review",
    }
)  # fmt: skip

GH_PROJECT_WRITES = frozenset(
    {
        "create", "edit", "close", "delete", "copy", "link", "unlink", "mark-template",
        "field-create", "field-delete", "item-add", "item-archive", "item-create", "item-delete",
        "item-edit",
    }
)  # fmt: skip

WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

_SEPARATORS = frozenset({";", "&&", "||", "|", "&", "\n"})


def notice(pm_prefix: str) -> str:
    """The reminder text.

    Args:
        pm_prefix: The title prefix that names the PM session.

    Returns:
        One sentence of context for the model.
    """
    return (
        "Tracker write: send the PM (the newest session titled "
        f"'{pm_prefix.strip()} ...') a one-line notice of what changed and where the record is, "
        "unless you are the PM, a cloud session, or no PM is listed."
    )


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = ""
    segments: list[list[str]] = [[]]
    for token in lexer:
        if token in _SEPARATORS or set(token) <= set(";&|"):
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _gh_args(segment: list[str]) -> list[str] | None:
    for index, token in enumerate(segment):
        if token == "gh" or token.endswith("/gh"):
            return segment[index + 1 :]
        if "=" not in token and token not in {"env", "command", "exec", "sudo"}:
            return None
    return None


def _is_api_write(args: list[str]) -> bool:
    if "graphql" in args:
        return bool(re.search(r"\bmutation\b", " ".join(args)))
    for index, token in enumerate(args):
        if token in {"-X", "--method"} and index + 1 < len(args):
            return args[index + 1].upper() in WRITE_METHODS
        if token.startswith("--method="):
            return token.split("=", 1)[1].upper() in WRITE_METHODS
        if token.startswith("-X") and len(token) > 2:
            return token[2:].upper() in WRITE_METHODS
    return any(
        flag in args for flag in ("-f", "-F", "--field", "--raw-field", "--input")
    )


def is_gh_write(command: str) -> bool:
    """Whether a shell command runs a ``gh`` write against issues, PRs or Projects.

    Args:
        command: The Bash tool's ``command`` input.

    Returns:
        ``True`` when any segment of the command is such a write.
    """
    try:
        segments = _segments(command)
    except ValueError:
        return bool(re.search(r"\bgh\s+(?:issue|pr|project|api)\b", command))
    for segment in segments:
        args = _gh_args(segment)
        if not args:
            continue
        words = [a for a in args if not a.startswith("-")]
        group = next(
            (i for i, w in enumerate(words) if w in {"issue", "pr", "project", "api"}),
            None,
        )
        if group is None:
            continue
        noun = words[group]
        verb = words[group + 1] if group + 1 < len(words) else ""
        if noun in {"issue", "pr"} and verb in GH_ISSUE_PR_WRITES:
            return True
        if noun == "project" and verb in GH_PROJECT_WRITES:
            return True
        if noun == "api" and _is_api_write(args):
            return True
    return False


def is_tracker_write(payload: Mapping[str, Any]) -> bool:
    """Whether a PostToolUse input records a GitHub write.

    Args:
        payload: The decoded hook input.

    Returns:
        ``True`` for a matching MCP tool or a Bash ``gh`` write.

    Raises:
        TypeError: When ``tool_name`` is missing or not a string.
    """
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        raise TypeError("tool_name is not a string")
    if MCP_PATTERN.fullmatch(tool_name):
        return True
    if tool_name == "Bash":
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return isinstance(command, str) and is_gh_write(command)
    return False


def decide(
    payload: object, env: Mapping[str, str] | None = None
) -> dict[str, Any] | None:
    """The hook output for one input, or ``None`` for silence.

    Args:
        payload: The decoded hook input.
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        The ``additionalContext`` document, or ``None``.

    Raises:
        TypeError: When the input is not a JSON object or has no string ``tool_name``.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload is not a JSON object")
    if payload.get("agent_id"):
        return None
    if not is_tracker_write(payload):
        return None
    settings = pm_settings.enabled_settings("tracker_write_notice", PREFIX, env)
    if settings is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": notice(settings.pm_title_prefix),
        }
    }


def main() -> int:
    """Read one hook input on stdin and print the reminder when it applies.

    Returns:
        Always 0.
    """
    try:
        output = decide(json.loads(sys.stdin.read()))
        if output is not None:
            print(json.dumps(output))
    except Exception as exc:  # noqa: BLE001 -- fail open: any error is one stderr line
        print(
            f"{PREFIX}: {type(exc).__name__}: {' '.join(str(exc).split())}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
