"""Barred-folder guard. PreToolUse on Read, Grep, Glob and Bash; settings flag ``barred_paths``.

A project lists paths no session may open or list, as git pathspec exclusions
(``":(top,exclude)secrets/"``, ``":(top,exclude,icase)*_private*"``). This guard refuses:

- ``Read`` of a barred file;
- ``Grep`` or ``Glob`` whose search root is barred or sits at or above a barred folder. The tools
  take no exclusions, so the reason names the ``git grep`` exclusions to use instead. A pattern
  with no fixed folder (``*_private*``) refuses them only when their root itself matches;
- a ``Bash`` argument that names an existing barred path, or a wildcard argument whose fixed
  leading folder is barred, and ``git show <rev>:<path>`` style arguments naming a barred path;
- a ``Bash`` search (``grep -r``, ``rg``, ``ag``, ``fd``, ``find``, ``tree``, ``ls -R``,
  ``git grep``, ``git ls-files``, ``git ls-tree``) that starts at or above a barred folder, or
  anywhere for a pattern with no fixed folder, and names no exclusion for it.

An exclusion counts only in an exclusion form: a ``:(exclude)``, ``:!`` or ``:^`` pathspec,
``--exclude``/``--exclude-dir``, ``--ignore``, ``-g '!...'``, fd's ``-E``, tree's ``-I``, or a
``find`` test negated with ``-not``/``!`` or followed by ``-prune``.

Matching follows git pathspec rules for these patterns: the pattern is matched against the path
from the project root, ``*`` also crosses ``/``, and a pattern with no wildcard also covers
everything under it. ``icase`` makes the match case-insensitive.

Known limits, by design: commands inside scripts, aliases or functions are not seen, and
``git diff`` or ``git log -p`` over a whole range can still show barred content. This is a
convenience guard that keeps honest sessions honest, not a security boundary. A command it
cannot parse gets ``ask``. Any other internal error fails open with one stderr line starting
``barred_paths:``.
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

_SHELLS = frozenset({"bash", "sh", "zsh", "dash"})

# Flags that take the next token as their value, per search tool. A value is never a root.
_VALUE_FLAGS = {
    "grep": frozenset(
        [
            "-A",
            "-B",
            "-C",
            "-m",
            "-e",
            "-f",
            "-d",
            "-D",
            "--regexp",
            "--file",
            "--max-count",
            "--context",
            "--after-context",
            "--before-context",
            "--include",
            "--exclude",
            "--exclude-dir",
            "--exclude-from",
            "--label",
        ]
    ),
    "rg": frozenset(
        [
            "-t",
            "-T",
            "-g",
            "-e",
            "-f",
            "-A",
            "-B",
            "-C",
            "-m",
            "-M",
            "-j",
            "-d",
            "-E",
            "-r",
            "--type",
            "--type-not",
            "--glob",
            "--iglob",
            "--regexp",
            "--file",
            "--max-count",
            "--max-columns",
            "--threads",
            "--context",
            "--after-context",
            "--before-context",
            "--max-depth",
            "--type-add",
            "--sort",
            "--sortr",
            "--encoding",
            "--replace",
            "--pre",
            "--ignore-file",
        ]
    ),
    "ag": frozenset(
        [
            "-G",
            "-g",
            "-A",
            "-B",
            "-C",
            "-m",
            "--ignore",
            "--ignore-dir",
            "--depth",
            "--file-search-regex",
            "--context",
        ]
    ),
    "fd": frozenset(
        [
            "-e",
            "-t",
            "-E",
            "-d",
            "-x",
            "-X",
            "-S",
            "-o",
            "-c",
            "-j",
            "--extension",
            "--type",
            "--exclude",
            "--max-depth",
            "--min-depth",
            "--exact-depth",
            "--exec",
            "--exec-batch",
            "--size",
            "--changed-within",
            "--changed-before",
            "--owner",
            "--search-path",
            "--base-directory",
            "--color",
            "--threads",
            "--max-results",
        ]
    ),
    "tree": frozenset(["-I", "-P", "-L", "-o", "--filelimit", "--charset", "--sort"]),
}
_VALUE_FLAGS["egrep"] = _VALUE_FLAGS["fgrep"] = _VALUE_FLAGS["grep"]

# Flags whose value is an exclusion, per tool.
_EXCLUDE_FLAGS = frozenset(
    ["--exclude", "--exclude-dir", "--ignore", "--ignore-dir", "-E", "-I"]
)
_GLOB_FLAGS = frozenset({"-g", "--glob", "--iglob"})

_GIT_GLOBAL_VALUE_FLAGS = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
)
_GIT_LISTERS = frozenset({"grep", "ls-files", "ls-tree"})
# git subcommand flags whose value is text, never a path.
_GIT_TEXT_FLAGS = frozenset(
    {
        "--grep",
        "--author",
        "--committer",
        "-m",
        "--message",
        "-S",
        "-G",
        "--format",
        "--pretty",
    }
)
# Commands whose bare-word arguments (no `/`) name files they read.
_FILE_READERS = frozenset(
    {
        "cat", "less", "more", "head", "tail", "wc", "nl", "od", "xxd", "hexdump", "strings",
        "file", "stat", "cp", "mv", "rsync", "scp", "tar", "zip", "unzip", "jq", "yq", "sed",
        "awk", "sort", "uniq", "diff", "cmp", "base64", "md5sum", "sha1sum", "sha256sum",
        "source", ".", "vi", "vim", "nano", "bat", "du", "ls", "python", "python3", "node",
    }
)  # fmt: skip
_GREP_LIKE = frozenset({"grep", "egrep", "fgrep", "rg", "ag"})
# Flags, for any command, whose value is text such as a title or a message, never a path.
_TEXT_FLAGS = frozenset(
    {"--title", "--body", "--message", "-m", "--subject", "--description", "--notes"}
)
# Commands that only print their arguments.
_PRINTERS = frozenset({"echo", "printf"})
_GIT_FILE_READERS = frozenset(
    {"show", "cat-file", "blame", "diff", "log", "archive", "grep"}
)
_FIND_NAME_TESTS = frozenset(
    {"-path", "-ipath", "-name", "-iname", "-wholename", "-regex"}
)


def _has_wildcard(text: str) -> bool:
    return any(c in _WILDCARDS for c in text)


class Barred:
    """One barred pattern, with the parts every check needs worked out once."""

    __slots__ = ("bare", "core", "fixed_prefix", "icase", "spec", "wild")

    def __init__(self, spec: str, pattern: str, icase: bool) -> None:
        """Hold one pattern.

        Args:
            spec: The pathspec as the settings file wrote it.
            pattern: The pattern with its magic prefix removed.
            icase: Whether matching ignores case.
        """
        self.spec = spec
        self.icase = icase
        bare = pattern.rstrip("/")
        self.bare = self._fold(bare)
        self.wild = _has_wildcard(bare)
        self.core = self._fold(bare.strip("*?").rstrip("/")) or self.bare
        cut = next((i for i, c in enumerate(bare) if c in _WILDCARDS), None)
        if cut is None:
            prefix = bare
        else:
            head = bare[:cut]
            prefix = head[: head.rfind("/")] if "/" in head else ""
        self.fixed_prefix = self._fold(prefix)

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

    def reachable_from(self, rel_root: str, anywhere: bool) -> bool:
        """Whether a recursive search starting at ``rel_root`` could reach a barred path.

        Args:
            rel_root: The search root relative to the project root; ``""`` is the root itself.
            anywhere: Whether a pattern with no fixed folder counts as reachable from any root.

        Returns:
            ``True`` when the root is barred, or is the pattern's fixed folder or an ancestor.
        """
        if rel_root and self.matches(rel_root):
            return True
        if not self.fixed_prefix:
            return anywhere
        root = self._fold(rel_root)
        prefix = self.fixed_prefix
        return not root or prefix == root or prefix.startswith(root + "/")

    def excluded_by(self, exclusions: Iterable[str]) -> bool:
        """Whether one of a command's exclusion values names this pattern.

        Args:
            exclusions: The values the command passes in exclusion form.

        Returns:
            ``True`` when the whole pathspec is passed, or an exclusion value, with its
            ``!``, ``./``, ``**/`` and trailing ``/**`` or ``/`` removed, is the pattern itself.
        """
        wanted = {self.bare, self.core}
        return any(
            value == self.spec
            or any(self._fold(part) in wanted for part in normalize_exclusion(value))
            for value in exclusions
        )


def normalize_exclusion(value: str) -> list[str]:
    """An exclusion value reduced to the paths it names: ``'!./secrets/**'`` gives ``secrets``.

    A brace list (``{secrets,.git}``) and a ``|``-separated list (tree's ``-I 'a|b'``) give one
    path each.

    Args:
        value: One exclusion value as the command passed it.

    Returns:
        The bare paths or patterns.
    """
    text = value.strip()
    if text.startswith(":(") and ")" in text:
        text = text.split(")", 1)[1]
    elif text.startswith((":!", ":^")):
        text = text[2:].removeprefix(":")
    parts: list[str] = []
    if "{" in text and "}" in text:
        head, rest = text.split("{", 1)
        body, tail = rest.split("}", 1)
        parts = [head + item + tail for item in body.split(",")]
    else:
        parts = text.split("|")
    result: list[str] = []
    for part in parts:
        part = part.removeprefix("!").removeprefix("./").removeprefix("/")
        while part.startswith(("**/", "*/")):
            part = part.split("/", 1)[1]
        for suffix in ("/**", "/*", "/"):
            part = part.removesuffix(suffix)
        if part:
            result.append(part)
    return result


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
    if os.path.lexists(joined):
        # A symlink into a barred folder is the barred folder.
        joined = os.path.realpath(joined)
    root = os.path.realpath(project_dir)
    if joined == root:
        return ""
    if not joined.startswith(root + os.sep):
        return None
    return joined[len(root) + 1 :].replace(os.sep, "/")


def _exclusions_text(patterns: Iterable[Barred]) -> str:
    return " ".join(f"'{p.spec}'" for p in patterns)


def _glob_head(token: str) -> str:
    """The fixed folder in front of a wildcard argument: ``secrets/*.pem`` gives ``secrets``."""
    cut = next(i for i, c in enumerate(token) if c in _WILDCARDS)
    head = token[:cut]
    return head[: head.rfind("/")] if "/" in head else ""


def strip_redirections(segment: list[str]) -> tuple[list[str], list[str]]:
    """Split a segment's redirections from its command and arguments.

    ``2>/dev/null`` and ``> out`` go, with their targets. An input redirection's target
    (``< file``) is returned on its own, since it is a file the command reads. A here-document
    or here-string (``<<``, ``<<<``) reads no file.

    Args:
        segment: One simple command's tokens.

    Returns:
        The command and its arguments, and the files read through input redirection.
    """
    kept: list[str] = []
    inputs: list[str] = []
    skip_next = False
    read_next = False
    for index, token in enumerate(segment):
        if skip_next:
            skip_next = False
            if read_next:
                inputs.append(token)
                read_next = False
            continue
        if token and set(token) <= set("<>&"):
            skip_next = True
            read_next = token in {"<", "<>", "<&"}
            continue
        following = segment[index + 1] if index + 1 < len(segment) else ""
        if token.isdigit() and following and set(following) <= set("<>&"):
            continue
        kept.append(token)
    return kept, inputs


def positionals(args: list[str], value_flags: frozenset[str]) -> list[str]:
    """The non-option arguments, skipping each value-taking flag's value.

    Args:
        args: The arguments after the command name.
        value_flags: The flags that take the next token as their value.

    Returns:
        The positional arguments, in order.
    """
    result: list[str] = []
    skip = False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg == "--":
            result += args[index + 1 :]
            break
        if arg in value_flags:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        result.append(arg)
    return result


def exclusion_values(name: str, args: list[str]) -> list[str]:
    """The values a search command passes in an exclusion form.

    Args:
        name: The command's name.
        args: Its arguments.

    Returns:
        Every value that excludes something.
    """
    values: list[str] = []
    negated_find = name == "find" and any(a in {"-not", "!", "-prune"} for a in args)
    for index, arg in enumerate(args):
        following = args[index + 1] if index + 1 < len(args) else ""
        if arg.startswith((":(", ":!", ":^")) and (
            not arg.startswith(":(") or "exclude" in arg
        ):
            values.append(arg)
        elif "=" in arg and arg.split("=", 1)[0] in _EXCLUDE_FLAGS:
            values.append(arg.split("=", 1)[1])
        elif arg in _EXCLUDE_FLAGS or arg in _GLOB_FLAGS and following.startswith("!"):
            values.append(following)
        elif "=" in arg and arg.split("=", 1)[0] in _GLOB_FLAGS and "=!" in arg:
            values.append(arg.split("=", 1)[1])
        elif negated_find and arg in _FIND_NAME_TESTS:
            values.append(following)
    return [v for v in values if v]


class Search:
    """A recursive search command: where it starts and what it excludes."""

    __slots__ = ("exclusions", "roots")

    def __init__(self, roots: list[str], exclusions: list[str]) -> None:
        """Hold the start folders and the exclusion values."""
        self.roots = roots
        self.exclusions = exclusions


def search_of(name: str, args: list[str]) -> Search | None:
    """The search a command runs, or ``None`` when it isn't a recursive search.

    Args:
        name: The command's name, without its folder.
        args: Its arguments, redirections removed.

    Returns:
        The search's start folders (``"."`` when none is named) and exclusions.
    """
    exclusions = exclusion_values(name, args)
    if name == "git":
        root = "."
        rest = list(args)
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in _GIT_GLOBAL_VALUE_FLAGS and rest:
                value = rest.pop(0)
                if flag == "-C":
                    root = os.path.join(root, value)
        if not rest or rest[0] not in _GIT_LISTERS:
            return None
        return Search([root], exclusions)
    if name == "ls":
        short = [a for a in args if a.startswith("-") and not a.startswith("--")]
        if "--recursive" not in args and not any("R" in a for a in short):
            return None
        return Search(positionals(args, frozenset()) or ["."], exclusions)
    if name == "find":
        roots: list[str] = []
        for arg in args:
            if arg.startswith("-") or arg in {"(", "!", ")"}:
                break
            roots.append(arg)
        return Search(roots or ["."], exclusions)
    if name not in _VALUE_FLAGS:
        return None
    if name in {"grep", "egrep", "fgrep"}:
        short = [a for a in args if a.startswith("-") and not a.startswith("--")]
        recursive = any(
            a in {"--recursive", "--dereference-recursive"} for a in args
        ) or any(("r" in a or "R" in a) for a in short)
        if not recursive:
            return None
    words = positionals(args, _VALUE_FLAGS[name])
    if name == "tree":
        return Search(words or ["."], exclusions)
    pattern_given = name not in {"fd", "ag"} and any(
        a in {"-e", "-f", "--regexp", "--file"} for a in args
    )
    paths = words if pattern_given else words[1:]
    return Search(paths or ["."], exclusions)


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

    def barred(self, path: str, cwd: str | None = None) -> Barred | None:
        """The first pattern that bars ``path``, if any."""
        rel = relative(path, self.project_dir, cwd or self.cwd)
        if not rel:
            return None
        return next((p for p in self.patterns if p.matches(rel)), None)

    def reachable(self, root: str, cwd: str, anywhere: bool) -> list[Barred]:
        """The patterns a recursive search from ``root`` could reach."""
        rel = relative(root, self.project_dir, cwd)
        if rel is None:
            return []
        return [p for p in self.patterns if p.reachable_from(rel, anywhere)]

    def token_hit(
        self, token: str, cwd: str, bare_files_only: bool = False
    ) -> tuple[str, Barred] | None:
        """The existing barred path a command argument names, with its pattern, if any.

        Only arguments naming something that exists count, so a branch name, a URL or a commit
        message that merely contains a barred word passes. A wildcard argument counts when its
        fixed leading folder is barred. With ``bare_files_only``, an argument without a ``/``
        counts only when it names an existing regular file: ``kubectl get secrets`` names a
        folder at most, while ``openssl rsa -in key`` names a file.
        """
        if token.startswith("-") and "=" in token:
            token = token.split("=", 1)[1]
        if not token or token.startswith((":(", ":!", ":^", "-")) or "://" in token:
            return None
        if any(c.isspace() for c in token):
            return None
        candidate = _glob_head(token) if _has_wildcard(token) else token
        if not candidate:
            return None
        hit = self.barred(candidate, cwd)
        if hit is None:
            return None
        path = os.path.join(cwd, candidate)
        exists = (
            os.path.isfile(path) if bare_files_only and "/" not in candidate else None
        )
        if exists if exists is not None else os.path.lexists(path):
            return candidate, hit
        return None

    def revision_path_hit(self, token: str, cwd: str) -> tuple[str, Barred] | None:
        """A ``<rev>:<path>`` argument naming a barred path, as ``git show HEAD:secrets/key``.

        The path is from the repository root, except one starting ``./`` or ``../``, which git
        reads from the working folder.
        """
        if ":" not in token or token.startswith((":(", ":!", ":^", "-")):
            return None
        path = token.split(":", 1)[1]
        if not path:
            return None
        if path.startswith(("./", "../")):
            rel = relative(path, self.project_dir, cwd)
            if rel is None:
                return None
            path = rel
        hit = next((p for p in self.patterns if p.matches(path)), None)
        return (path, hit) if hit is not None else None

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
        reachable = self.reachable(root, self.cwd, anywhere=False)
        if not reachable:
            return None
        return hook_io.permission(
            "deny",
            f"{tool} refused: a search from here reaches a barred folder, and {tool} takes no "
            "exclusions. Search a folder below it, or use git grep or git ls-files with these "
            f"pathspecs in the command: {_exclusions_text(reachable)}",
        )

    def bash(self, command: str, depth: int = 0) -> dict[str, Any] | None:
        """Decide a ``Bash`` call."""
        try:
            segments = hook_io.segments(command)
        except ValueError:
            reason = "The barred-folder guard could not parse this command. Check it."
            return hook_io.permission("ask", reason)
        cwd = self.cwd
        for raw in segments:
            segment, inputs = strip_redirections(raw)
            for target in inputs:
                if found := self.token_hit(target, cwd):
                    return _refused(found)
            start = hook_io.command_start(segment)
            if start >= len(segment):
                continue
            name = hook_io.program(segment[start])
            args = segment[start + 1 :]
            if name == "cd":
                cwd = (
                    os.path.normpath(os.path.join(cwd, args[0]))
                    if args
                    else self.project_dir
                )
                continue
            if name in _SHELLS and (script := _shell_script(args)) is not None:
                if depth >= 2:
                    reason = "The barred-folder guard stops at two nested shells. Check this."
                    return hook_io.permission("ask", reason)
                if inner := self.bash_in(script, cwd, depth):
                    return inner
                continue
            if out := self._arguments(name, args, cwd):
                return out
            search = search_of(name, args)
            if search is None:
                continue
            missing: list[Barred] = []
            for root in search.roots:
                for pattern in self.reachable(root, cwd, anywhere=True):
                    if (
                        not pattern.excluded_by(search.exclusions)
                        and pattern not in missing
                    ):
                        missing.append(pattern)
            if missing:
                return hook_io.permission(
                    "deny",
                    "Search refused: it starts at or above a barred folder and names no "
                    "exclusion for it. Prune these inside the command itself: "
                    f"{_exclusions_text(missing)}",
                )
        return None

    def bash_in(self, command: str, cwd: str, depth: int) -> dict[str, Any] | None:
        """Decide a command run through ``sh -c``, from the working directory it inherits."""
        inner = Guard(self.patterns, self.project_dir, cwd)
        return inner.bash(command, depth + 1)

    def _arguments(self, name: str, args: list[str], cwd: str) -> dict[str, Any] | None:
        if name in _PRINTERS:
            return None
        if name == "git":
            return self._git_arguments(args, cwd)
        excluded = set(exclusion_values(name, args))
        skip = set(search_pattern_indices(name, args))
        skip |= {i + 1 for i, a in enumerate(args) if a in _TEXT_FLAGS}
        bare_files_only = name not in _FILE_READERS and name not in _GREP_LIKE
        for index, token in enumerate(args):
            if index in skip or token.split("=", 1)[0] in _TEXT_FLAGS:
                continue
            value = (
                token.split("=", 1)[1]
                if token.startswith("-") and "=" in token
                else token
            )
            if value in excluded:
                continue
            if found := self.token_hit(token, cwd, bare_files_only):
                return _refused(found)
        return None

    def _git_arguments(self, args: list[str], cwd: str) -> dict[str, Any] | None:
        rest = list(args)
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in _GIT_GLOBAL_VALUE_FLAGS and rest:
                value = rest.pop(0)
                if flag == "-C":
                    cwd = os.path.normpath(os.path.join(cwd, value))
        if not rest or rest[0] not in _GIT_FILE_READERS:
            return None
        for token in positionals(rest[1:], _GIT_TEXT_FLAGS):
            if found := self.revision_path_hit(token, cwd) or self.token_hit(
                token, cwd
            ):
                return _refused(found)
        return None


def _refused(found: tuple[str, Barred]) -> dict[str, Any]:
    return hook_io.permission(
        "deny", f"Command refused: {found[0]} is barred by {found[1].spec}."
    )


def _shell_script(args: list[str]) -> str | None:
    """The script a shell runs with ``-c`` (also inside a cluster such as ``-lc``), if any."""
    for index, arg in enumerate(args):
        if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
            rest = [a for a in args[index + 1 :] if a != "--"]
            return rest[0] if rest else None
    return None


def search_pattern_indices(name: str, args: list[str]) -> list[int]:
    """Where a grep-like command's search patterns sit: its first word, or its ``-e`` values.

    Args:
        name: The command's name.
        args: Its arguments.

    Returns:
        The indices in ``args`` of pattern texts, which are never paths.
    """
    if name not in _GREP_LIKE:
        return []
    explicit = [i + 1 for i, a in enumerate(args[:-1]) if a in {"-e", "--regexp"}]
    explicit += [i for i, a in enumerate(args) if a.startswith("--regexp=")]
    if explicit or any(a in {"-f", "--file"} for a in args):
        return explicit
    skip = False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg == "--":
            return [index + 1] if index + 1 < len(args) else []
        if arg in _VALUE_FLAGS[name]:
            skip = True
            continue
        if not arg.startswith("-"):
            return [index]
    return []


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
    project_dir = settings.project_root or pm_settings.project_dir(env)
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
