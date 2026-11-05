"""Barred-folder guard. PreToolUse on Read, Grep, Glob and Bash; settings flag ``barred_paths``.

A project lists paths no session may open or list, as git pathspec exclusions
(``":(top,exclude)secrets/"``, ``":(top,exclude,icase)*_private*"``). This guard refuses:

- ``Read`` of a barred file;
- ``Grep`` or ``Glob`` whose search root is barred, or could reach a barred path: the tools take
  no exclusions, so a search that starts at or above a barred folder is refused, with the
  exclusions to use in a ``git grep`` instead;
- a ``Bash`` command with any argument that names a barred path, or a wildcard argument whose
  fixed leading folder is barred;
- a ``Bash`` search (``grep -r``, ``rg``, ``ag``, ``fd``, ``find``, ``tree``, ``git grep``,
  ``git ls-files``, ``ls -R``) that starts at or above a barred folder and names no exclusion
  for it.

Matching follows git pathspec rules for these patterns: the pattern is matched against the path
from the project root, ``*`` also crosses ``/``, and a pattern with no wildcard also covers
everything under it. ``icase`` makes the match case-insensitive.

Every other command passes. A command the guard cannot parse gets ``ask``, so the person
decides. Any other internal error fails open with one stderr line starting ``barred_paths:``:
this is a convenience guard that keeps honest sessions honest, not a security boundary.
"""

from __future__ import annotations

import fnmatch
import os

import hook_io
import pm_settings

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Any

PREFIX = "barred_paths"

GUARDED_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash"})

_WILDCARDS = frozenset("*?[")

_GREP_TOOLS = frozenset({"grep", "egrep", "fgrep"})

_PATTERN_FIRST_TOOLS = frozenset({"rg", "ag", "fd"})

_GIT_LISTERS = frozenset({"grep", "ls-files", "ls-tree"})


def _has_wildcard(text: str) -> bool:
    return any(c in _WILDCARDS for c in text)


class Barred:
    """One barred pattern, with the parts every check needs worked out once."""

    __slots__ = ("bare", "fixed_prefix", "icase", "pattern", "spec", "wild")

    def __init__(self, spec: str, pattern: str, icase: bool) -> None:
        """Hold one pattern.

        Args:
            spec: The pathspec as the settings file wrote it.
            pattern: The pattern with its magic prefix removed.
            icase: Whether matching ignores case.
        """
        self.spec = spec
        self.pattern = pattern
        self.icase = icase
        bare = pattern.rstrip("/")
        self.bare = bare.lower() if icase else bare
        self.wild = _has_wildcard(bare)
        cut = next((i for i, c in enumerate(pattern) if c in _WILDCARDS), None)
        if cut is None:
            prefix = bare
        else:
            head = pattern[:cut]
            prefix = head[: head.rfind("/")] if "/" in head else ""
        self.fixed_prefix = prefix.lower() if icase else prefix

    def _fold(self, path: str) -> str:
        return path.lower() if self.icase else path

    def matches(self, rel: str) -> bool:
        """Whether a path relative to the project root is barred by this pattern.

        Args:
            rel: A normalized path relative to the project root, with ``/`` separators.

        Returns:
            ``True`` when the path is the pattern, lies under it, or matches its wildcards.
        """
        path = self._fold(rel)
        if not self.wild:
            return path == self.bare or path.startswith(self.bare + "/")
        return fnmatch.fnmatchcase(path, self.bare) or fnmatch.fnmatchcase(
            path, self.bare + "/*"
        )

    def reachable_from(self, rel_root: str) -> bool:
        """Whether a recursive search starting at ``rel_root`` could reach a barred path.

        Args:
            rel_root: The search root relative to the project root; ``""`` is the root itself.

        Returns:
            ``True`` when the root is barred, or is the pattern's fixed folder or an ancestor.
        """
        if rel_root and self.matches(rel_root):
            return True
        root = self._fold(rel_root)
        prefix = self.fixed_prefix
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
    text = text.lstrip("/").removeprefix("./")
    return Barred(spec=spec, pattern=text, icase=icase) if text else None


def relative(path: str, project_dir: str, cwd: str) -> str | None:
    """A path relative to the project root, or ``None`` when it lies outside the project.

    Args:
        path: An absolute path, or one relative to ``cwd``; ``~`` is not expanded.
        project_dir: The project root.
        cwd: The working directory that a relative ``path`` starts from.

    Returns:
        The normalized relative path with ``/`` separators, ``""`` for the root itself.
    """
    joined = os.path.normpath(os.path.join(cwd, path))
    root = os.path.normpath(project_dir)
    if joined == root:
        return ""
    if not joined.startswith(root + os.sep):
        return None
    return joined[len(root) + 1 :].replace(os.sep, "/")


def _exclusions(patterns: Iterable[Barred]) -> str:
    return " ".join(f"'{p.spec}'" for p in patterns)


def _glob_head(token: str) -> str:
    """The fixed folder in front of a wildcard argument: ``secrets/*.pem`` gives ``secrets``."""
    cut = next(i for i, c in enumerate(token) if c in _WILDCARDS)
    head = token[:cut]
    return head[: head.rfind("/")] if "/" in head else ""


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
        if not rel:
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

    def token_hit(self, token: str) -> tuple[str, Barred] | None:
        """The barred path a command argument names, with its pattern, if any.

        A plain argument counts when a pattern matches it and it holds a ``/`` or exists under
        the working directory, so a search word such as ``TODO`` is not mistaken for a path. A
        wildcard argument counts when its fixed leading folder is barred.
        """
        if token.startswith("-") and "=" in token:
            token = token.split("=", 1)[1]
        if not token or token.startswith((":(", ":!", ":^", "-")):
            return None
        candidate = _glob_head(token) if _has_wildcard(token) else token
        if not candidate:
            return None
        hit = self.barred(candidate)
        if hit is None:
            return None
        if "/" in candidate or os.path.lexists(os.path.join(self.cwd, candidate)):
            return candidate, hit
        return None

    def read(self, tool_input: Mapping[str, Any]) -> dict[str, Any] | None:
        """Decide a ``Read`` call."""
        path = tool_input.get("file_path")
        if isinstance(path, str) and (hit := self.barred(path)):
            reason = f"Read refused: this path is barred by {hit.spec}. Do not open it."
            return hook_io.permission("deny", reason)
        return None

    def search_tool(
        self, tool: str, tool_input: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Decide a ``Grep`` or ``Glob`` call, which take no exclusions."""
        root = tool_input.get("path")
        root = root if isinstance(root, str) and root else self.cwd
        if hit := self.barred(root):
            return hook_io.permission(
                "deny", f"{tool} refused: its root is barred by {hit.spec}."
            )
        reachable = self.unpruned(root, "")
        if not reachable:
            return None
        return hook_io.permission(
            "deny",
            f"{tool} refused: a search from here could reach barred paths, and {tool} takes no "
            "exclusions. Search with git grep or git ls-files and add these pathspecs to the "
            f"command: {_exclusions(reachable)}",
        )

    def bash(self, command: str) -> dict[str, Any] | None:
        """Decide a ``Bash`` call."""
        try:
            segments = hook_io.segments(command)
        except ValueError:
            reason = "The barred-folder guard could not parse this command. Check it."
            return hook_io.permission("ask", reason)
        for segment in segments:
            for token in segment:
                if found := self.token_hit(token):
                    candidate, hit = found
                    reason = f"Command refused: {candidate} is barred by {hit.spec}."
                    return hook_io.permission("deny", reason)
            roots = search_roots(segment)
            if roots is None:
                continue
            text = " ".join(segment)
            missing: list[Barred] = []
            for root in roots:
                missing += [p for p in self.unpruned(root, text) if p not in missing]
            if missing:
                return hook_io.permission(
                    "deny",
                    "Search refused: it starts at or above a barred folder and names no "
                    f"exclusion for it. Prune these inside the command itself: "
                    f"{_exclusions(missing)}",
                )
        return None


def search_roots(segment: list[str]) -> list[str] | None:
    """The folders a recursive search command starts from, or ``None`` if it isn't one.

    Args:
        segment: One shell command's tokens.

    Returns:
        The start folders (``"."`` when none is named), or ``None`` for a non-search command.
    """
    start = hook_io.command_start(segment)
    if start >= len(segment):
        return None
    name = hook_io.program(segment[start])
    args = segment[start + 1 :]
    positional = [a for a in args if not a.startswith("-")]
    if name == "git":
        return ["."] if positional[:1] and positional[0] in _GIT_LISTERS else None
    if name == "ls":
        short = [a for a in args if a.startswith("-") and not a.startswith("--")]
        if "--recursive" not in args and not any("R" in a for a in short):
            return None
        return positional or ["."]
    if name in _GREP_TOOLS:
        recursive = any(
            a in {"--recursive", "--dereference-recursive"}
            or (a.startswith("-") and not a.startswith("--") and ("r" in a or "R" in a))
            for a in args
        )
        return (positional[1:] or ["."]) if recursive else None
    if name in _PATTERN_FIRST_TOOLS:
        return positional[1:] or ["."]
    if name == "find":
        roots: list[str] = []
        for arg in args:
            if arg.startswith("-") or arg in {"(", "!", ")"}:
                break
            roots.append(arg)
        return roots or ["."]
    if name == "tree":
        return positional or ["."]
    return None


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
    if tool not in GUARDED_TOOLS:
        return None
    settings = pm_settings.enabled_settings("barred_paths", PREFIX, env)
    if settings is None:
        return None
    patterns = [p for p in map(parse_spec, settings.barred_paths) if p is not None]
    tool_input = payload.get("tool_input")
    if not patterns or not isinstance(tool_input, dict):
        return None
    project_dir = pm_settings.project_dir(env)
    cwd = payload.get("cwd")
    guard = Guard(
        patterns, project_dir, cwd if isinstance(cwd, str) and cwd else project_dir
    )
    if tool == "Read":
        return guard.read(tool_input)
    if tool == "Bash":
        command = tool_input.get("command")
        return guard.bash(command) if isinstance(command, str) else None
    return guard.search_tool(tool, tool_input)


def main() -> int:
    """Read one hook input on stdin and print a decision when one applies.

    Returns:
        0 normally, 1 after an internal error, which Claude Code treats as non-blocking.
    """
    return hook_io.run(PREFIX, decide, error_exit=1)


if __name__ == "__main__":
    raise SystemExit(main())
