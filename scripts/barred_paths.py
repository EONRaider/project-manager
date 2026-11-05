"""Barred-folder guard. PreToolUse on Read, Grep, Glob and Bash; settings flag ``barred_paths``.

A project lists paths no session may open or list, as git pathspec exclusions
(``":(top,exclude)secrets/"``, ``":(top,exclude,icase)*_private*"``). This guard refuses:

- ``Read`` of a barred file;
- ``Grep`` or ``Glob`` whose search root is barred, or could reach a barred path: the tools take
  no exclusions, so a search that starts at or above a barred folder is refused, with the
  exclusions to use in a ``git grep`` instead;
- a ``Bash`` command with any argument that names a barred path;
- a ``Bash`` search (``grep -r``, ``rg``, ``find``, ``fd``, ``git grep``, ``git ls-files``,
  ``ls -R``, ``tree``) that starts at or above a barred folder and names no exclusion for it.

Matching follows git pathspec rules for these patterns: the pattern is matched against the path
from the project root, ``*`` also crosses ``/``, and a pattern with no wildcard also covers
everything under it. ``icase`` makes the match case-insensitive.

Every other command passes. A command the guard cannot parse gets ``ask``, so the person
decides. Any other internal error fails open with one stderr line starting ``barred_paths:``:
this is a convenience guard that keeps honest sessions honest, not a security boundary.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import pm_settings

PREFIX = "barred_paths"

_WILDCARDS = frozenset("*?[")

SEARCH_TOOLS = frozenset({"grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "tree"})

_SEPARATORS = frozenset({";", "&&", "||", "|", "&"})


@dataclass(frozen=True)
class Barred:
    """One barred pattern: the pattern itself, its fixed leading folder, and its case rule."""

    spec: str
    pattern: str
    icase: bool

    @property
    def fixed_prefix(self) -> str:
        """The folder part of the pattern before its first wildcard, without a trailing slash."""
        cut = next((i for i, c in enumerate(self.pattern) if c in _WILDCARDS), None)
        if cut is None:
            return self.pattern.rstrip("/")
        head = self.pattern[:cut]
        return head[: head.rfind("/")] if "/" in head else ""

    def matches(self, rel: str) -> bool:
        """Whether a path relative to the project root is barred by this pattern.

        Args:
            rel: A normalized path relative to the project root, with ``/`` separators.

        Returns:
            ``True`` when the path is the pattern, lies under it, or matches its wildcards.
        """
        path = rel.lower() if self.icase else rel
        pattern = self.pattern.lower() if self.icase else self.pattern
        bare = pattern.rstrip("/")
        if not any(c in _WILDCARDS for c in bare):
            return path == bare or path.startswith(bare + "/")
        return fnmatch.fnmatchcase(path, bare) or fnmatch.fnmatchcase(path, bare + "/*")

    def reachable_from(self, rel_root: str) -> bool:
        """Whether a recursive search starting at ``rel_root`` could reach a barred path.

        Args:
            rel_root: The search root relative to the project root; ``""`` is the root itself.

        Returns:
            ``True`` when the root is barred, or is the pattern's fixed folder or an ancestor.
        """
        if rel_root and self.matches(rel_root):
            return True
        prefix = self.fixed_prefix.lower() if self.icase else self.fixed_prefix
        root = rel_root.lower() if self.icase else rel_root
        return not root or not prefix or prefix == root or prefix.startswith(root + "/")

    def named_in(self, text: str) -> bool:
        """Whether a command's text names this pattern as an exclusion.

        Args:
            text: The command segment's text.

        Returns:
            ``True`` when the whole pathspec, or its bare pattern, appears in the text.
        """
        core = self.pattern.rstrip("/")
        return self.spec in text or (bool(core) and core in text)


def parse_spec(spec: str) -> Barred | None:
    """Turn one pathspec exclusion into a :class:`Barred` pattern.

    Args:
        spec: A pathspec such as ``":(top,exclude,icase)*_private*"``, or a bare pattern.

    Returns:
        The pattern, or ``None`` for an empty one.
    """
    text = spec.strip()
    icase = False
    if text.startswith(":(") and ")" in text:
        magic, text = text[2:].split(")", 1)
        icase = "icase" in {word.strip() for word in magic.split(",")}
    elif text.startswith((":!", ":^")):
        text = text[2:]
    text = text.lstrip("/")
    text = text.removeprefix("./")
    return Barred(spec=spec, pattern=text, icase=icase) if text else None


def relative(path: str, project_dir: str, cwd: str) -> str | None:
    """A path relative to the project root, or ``None`` when it lies outside the project.

    Args:
        path: An absolute path, or one relative to ``cwd``; ``~`` is not expanded.
        project_dir: The project root.
        cwd: The working directory that a relative ``path`` starts from.

    Returns:
        The normalized relative path, ``""`` for the root itself.
    """
    joined = os.path.normpath(os.path.join(cwd, path))
    root = os.path.normpath(project_dir)
    if joined == root:
        return ""
    if not joined.startswith(root + os.sep):
        return None
    return PurePosixPath(*joined[len(root) + 1 :].split(os.sep)).as_posix()


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _ask(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def _exclusions(patterns: Iterable[Barred]) -> str:
    return " ".join(f"'{p.spec}'" for p in patterns)


class Guard:
    """Decides one tool call against the project's barred patterns."""

    def __init__(self, patterns: list[Barred], project_dir: str, cwd: str) -> None:
        """Hold the patterns and the two directories paths are resolved against.

        Args:
            patterns: The barred patterns.
            project_dir: The project root.
            cwd: The session's working directory.
        """
        self.patterns = patterns
        self.project_dir = project_dir
        self.cwd = cwd

    def barred(self, path: str) -> Barred | None:
        """The first pattern that bars ``path``, if any."""
        rel = relative(path, self.project_dir, self.cwd)
        if rel is None or rel == "":
            return None
        return next((p for p in self.patterns if p.matches(rel)), None)

    def unpruned(self, root: str, text: str) -> list[Barred]:
        """Patterns a recursive search from ``root`` could reach and ``text`` doesn't exclude."""
        rel = relative(root, self.project_dir, self.cwd)
        if rel is None:
            return []
        return [
            p for p in self.patterns if p.reachable_from(rel) and not p.named_in(text)
        ]

    def read(self, tool_input: Mapping[str, Any]) -> dict[str, Any] | None:
        """Decide a ``Read`` call."""
        path = tool_input.get("file_path")
        if isinstance(path, str) and (hit := self.barred(path)):
            return _deny(
                f"Read refused: this path is barred by {hit.spec}. Do not open it."
            )
        return None

    def search_tool(
        self, tool: str, tool_input: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Decide a ``Grep`` or ``Glob`` call, which take no exclusions."""
        root = tool_input.get("path")
        root = root if isinstance(root, str) and root else self.cwd
        if hit := self.barred(root):
            return _deny(f"{tool} refused: its search root is barred by {hit.spec}.")
        reachable = self.unpruned(root, "")
        if not reachable:
            return None
        return _deny(
            f"{tool} refused: a search from here could reach barred paths, and {tool} takes no "
            "exclusions. Search with git grep or git ls-files and add these pathspecs to the "
            f"command: {_exclusions(reachable)}"
        )

    def bash(self, command: str) -> dict[str, Any] | None:
        """Decide a ``Bash`` call."""
        try:
            segments = _segments(command)
        except ValueError:
            return _ask(
                "The barred-folder guard could not parse this command. Check it."
            )
        for segment in segments:
            text = " ".join(segment)
            for token in segment:
                candidate = _path_candidate(token, self.cwd)
                if candidate is not None and (hit := self.barred(candidate)):
                    return _deny(
                        f"Command refused: {candidate} is barred by {hit.spec}."
                    )
            roots = search_roots(segment)
            if roots is None:
                continue
            missing: list[Barred] = []
            for root in roots:
                missing += [p for p in self.unpruned(root, text) if p not in missing]
            if missing:
                return _deny(
                    "Search refused: it starts at or above a barred folder and names no exclusion "
                    f"for it. Prune these inside the command itself: {_exclusions(missing)}"
                )
        return None


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    segments: list[list[str]] = [[]]
    for token in lexer:
        if token in _SEPARATORS or set(token) <= set(";&|()\n"):
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")

_WRAPPERS = frozenset(
    {"env", "command", "exec", "sudo", "time", "nice", "xargs", "nohup"}
)


def _path_candidate(token: str, cwd: str) -> str | None:
    """The path a command token names, or ``None`` when it names none.

    A token counts as a path when it holds a ``/`` or names something that exists under the
    working directory, so a search pattern such as ``TODO`` is not mistaken for one.
    """
    if token.startswith("-") and "=" in token:
        token = token.split("=", 1)[1]
    if not token or token.startswith((":(", ":!", ":^", "-")):
        return None
    if any(c in token for c in "*?["):
        return None
    if "/" in token or os.path.lexists(os.path.join(cwd, token)):
        return token
    return None


def _command_start(segment: list[str]) -> int:
    for index, token in enumerate(segment):
        if token in _WRAPPERS or _ASSIGNMENT.match(token):
            continue
        return index
    return len(segment)


def search_roots(segment: list[str]) -> list[str] | None:
    """The folders a recursive search command starts from, or ``None`` if it isn't one.

    Args:
        segment: One shell command's tokens.

    Returns:
        The start folders (``"."`` when none is named), or ``None`` for a non-search command.
    """
    start = _command_start(segment)
    if start >= len(segment):
        return None
    name = os.path.basename(segment[start])
    args = segment[start + 1 :]
    positional = [a for a in args if not a.startswith("-")]
    if name == "git":
        sub = next((a for a in args if not a.startswith("-")), "")
        return ["."] if sub in {"grep", "ls-files", "ls-tree"} else None
    if name == "ls":
        short = [a for a in args if a.startswith("-") and not a.startswith("--")]
        if "--recursive" not in args and not any("R" in a for a in short):
            return None
        return positional or ["."]
    if name not in SEARCH_TOOLS:
        return None
    if name in {"grep", "egrep", "fgrep"}:
        recursive = any(
            a in {"--recursive", "--dereference-recursive"}
            or (a.startswith("-") and not a.startswith("--") and ("r" in a or "R" in a))
            for a in args
        )
        if not recursive:
            return None
        return positional[1:] or ["."]
    if name in {"rg", "ag"}:
        return positional[1:] or ["."]
    if name == "find":
        roots: list[str] = []
        for arg in args:
            if arg.startswith("-") or arg in {"(", "!", ")"}:
                break
            roots.append(arg)
        return roots or ["."]
    if name == "fd":
        return positional[1:] or ["."]
    return positional or ["."]


def decide(
    payload: object, env: Mapping[str, str] | None = None
) -> dict[str, Any] | None:
    """The hook output for one PreToolUse input, or ``None`` to let it through.

    Args:
        payload: The decoded hook input.
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        A deny or ask document, or ``None``.

    Raises:
        TypeError: When the input is not a JSON object.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload is not a JSON object")
    tool = payload.get("tool_name")
    if tool not in {"Read", "Grep", "Glob", "Bash"}:
        return None
    settings = pm_settings.enabled_settings("barred_paths", PREFIX, env)
    if settings is None:
        return None
    patterns = [
        p for p in (parse_spec(s) for s in settings.barred_paths) if p is not None
    ]
    if not patterns:
        return None
    environ = os.environ if env is None else env
    project_dir = environ.get("CLAUDE_PROJECT_DIR", "")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else project_dir
    guard = Guard(patterns, project_dir, cwd or project_dir)
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if tool == "Read":
        return guard.read(tool_input)
    if tool in {"Grep", "Glob"}:
        return guard.search_tool(str(tool), tool_input)
    command = tool_input.get("command")
    return guard.bash(command) if isinstance(command, str) else None


def main() -> int:
    """Read one hook input on stdin and print a decision when one applies.

    Returns:
        0 normally, 1 after an internal error, which Claude Code treats as non-blocking.
    """
    try:
        output = decide(json.loads(sys.stdin.read()))
    except Exception as exc:  # noqa: BLE001 -- fail open on any internal error
        print(
            f"{PREFIX}: check skipped after an internal error: {exc}", file=sys.stderr
        )
        return 1
    if output is not None:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
