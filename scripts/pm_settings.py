"""Load and validate a project's ``project-manager`` settings file.

The file lives at ``$CLAUDE_PROJECT_DIR/.claude/project-manager.json``. A plugin's own
``userConfig`` is stored per user, so per-project values need a file inside the project.

Every hook calls :func:`enabled_settings` first and does nothing unless its own flag under
``hooks`` is ``true``. A missing file means every hook is off. A file with a wrong type is an
error, so every hook stays off and the caller reports it. An unknown key is ignored with a
warning, so a settings file written for a newer plugin never silences an older one.

This module runs at the start of every hook process, so it avoids slow imports.
"""

from __future__ import annotations

import json
import os
import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

SETTINGS_RELATIVE_PATH = os.path.join(".claude", "project-manager.json")

HOOK_NAMES = (
    "plain_language_stop",
    "question_check",
    "tracker_write_notice",
    "barred_paths",
)

DEFAULT_TOP_LEVEL_DIRS = ("src", "tests", "docs", "scripts", ".github", ".claude")

USAGE = "usage: pm_settings.py [--project-dir DIR] [--path]"


class SettingsError(ValueError):
    """The settings file exists but cannot be used."""


class ProjectBoard:
    """The GitHub Project that holds status: its owner and its number."""

    __slots__ = ("number", "owner")

    def __init__(self, owner: str, number: int) -> None:
        """Hold the board's owner and number."""
        self.owner = owner
        self.number = number

    def __eq__(self, other: object) -> bool:
        """Equal when owner and number are."""
        if not isinstance(other, ProjectBoard):
            return NotImplemented
        return (self.owner, self.number) == (other.owner, other.number)

    def __hash__(self) -> int:
        """Hash of the owner and number."""
        return hash((self.owner, self.number))

    def __repr__(self) -> str:
        """The board as ``ProjectBoard(owner=..., number=...)``."""
        return f"ProjectBoard(owner={self.owner!r}, number={self.number!r})"


class Shorthand:
    """Project-specific additions to the plain-language patterns."""

    __slots__ = ("id_prefixes", "top_level_dirs")

    def __init__(
        self,
        id_prefixes: tuple[str, ...] = (),
        top_level_dirs: tuple[str, ...] = DEFAULT_TOP_LEVEL_DIRS,
    ) -> None:
        """Hold the project's id prefixes and top-level folder names."""
        self.id_prefixes = id_prefixes
        self.top_level_dirs = top_level_dirs


class Settings:
    """A validated settings file. The ``__init__`` defaults apply to every key the file omits."""

    __slots__ = (
        "barred_paths",
        "decider",
        "hooks",
        "notes_dir",
        "pm_title_prefix",
        "project",
        "review_model",
        "rulings_branch",
        "rulings_path",
        "shorthand",
        "tracker_repo",
        "warnings",
    )

    def __init__(
        self,
        tracker_repo: str = "",
        project: ProjectBoard | None = None,
        decider: str = "the decider",
        pm_title_prefix: str = "PM ",
        notes_dir: str = "",
        rulings_branch: str = "pm-records",
        rulings_path: str = "rulings.md",
        barred_paths: tuple[str, ...] = (),
        review_model: str = "opus",
        hooks: Mapping[str, bool] | None = None,
        shorthand: Shorthand | None = None,
        warnings: tuple[str, ...] = (),
    ) -> None:
        """Hold one value per settings key."""
        self.tracker_repo = tracker_repo
        self.project = project
        self.decider = decider
        self.pm_title_prefix = pm_title_prefix
        self.notes_dir = notes_dir
        self.rulings_branch = rulings_branch
        self.rulings_path = rulings_path
        self.barred_paths = barred_paths
        self.review_model = review_model
        self.hooks: Mapping[str, bool] = hooks or {}
        self.shorthand = shorthand or Shorthand()
        self.warnings = warnings

    def hook_enabled(self, name: str) -> bool:
        """Whether the hook called ``name`` is switched on.

        Args:
            name: One of :data:`HOOK_NAMES`.

        Returns:
            ``True`` only when the file sets that hook's flag to ``true``.
        """
        return self.hooks.get(name, False)


_STRING_KEYS = (
    "tracker_repo",
    "decider",
    "pm_title_prefix",
    "notes_dir",
    "rulings_branch",
    "rulings_path",
    "review_model",
)

KNOWN_KEYS = (frozenset(Settings.__slots__) - {"warnings"}) | {"$schema_version"}


def project_dir(env: Mapping[str, str] | None = None) -> str:
    """The project root from ``CLAUDE_PROJECT_DIR``, or ``""`` when it is unset.

    Args:
        env: The environment to read. Defaults to ``os.environ``.

    Returns:
        The project root, with surrounding whitespace removed.
    """
    environ = os.environ if env is None else env
    return environ.get("CLAUDE_PROJECT_DIR", "").strip()


def settings_path(env: Mapping[str, str] | None = None) -> str | None:
    """The settings file's path, or ``None`` when the project directory is unknown.

    Args:
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        The absolute path of the settings file, whether or not it exists.
    """
    root = project_dir(env)
    return os.path.join(root, SETTINGS_RELATIVE_PATH) if root else None


def _string_tuple(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SettingsError(f"{key} must be a list of strings")
    return tuple(value)


def _project(value: object) -> ProjectBoard | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SettingsError("project must be an object with owner and number")
    owner = value.get("owner")
    number = value.get("number")
    if (
        not isinstance(owner, str)
        or isinstance(number, bool)
        or not isinstance(number, int)
    ):
        raise SettingsError(
            "project.owner must be a string and project.number an integer"
        )
    return ProjectBoard(owner=owner, number=number)


def _hooks(value: object, warnings: list[str]) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise SettingsError("hooks must be an object")
    flags: dict[str, bool] = {}
    for name, flag in value.items():
        if name not in HOOK_NAMES:
            warnings.append(f"unknown hook {name!r} ignored")
            continue
        if not isinstance(flag, bool):
            raise SettingsError(f"hooks.{name} must be true or false")
        flags[name] = flag
    return flags


def _shorthand(value: object) -> Shorthand:
    if not isinstance(value, dict):
        raise SettingsError("shorthand must be an object")
    keys = ("id_prefixes", "top_level_dirs")
    return Shorthand(**{key: _string_tuple(value, key) for key in keys if key in value})


def parse(raw: object) -> Settings:
    """Validate a decoded settings document.

    Args:
        raw: The JSON value read from the settings file.

    Returns:
        The validated settings, with any warnings about ignored keys.

    Raises:
        SettingsError: When the document is not an object or a known key has the wrong type.
    """
    if not isinstance(raw, dict):
        raise SettingsError("the settings file must hold a JSON object")
    warnings = [f"unknown key {key!r} ignored" for key in raw if key not in KNOWN_KEYS]
    fields: dict[str, Any] = {}
    for key in _STRING_KEYS:
        if key in raw:
            if not isinstance(raw[key], str):
                raise SettingsError(f"{key} must be a string")
            fields[key] = raw[key]
    if "barred_paths" in raw:
        fields["barred_paths"] = _string_tuple(raw, "barred_paths")
    if "project" in raw:
        fields["project"] = _project(raw["project"])
    if "hooks" in raw:
        fields["hooks"] = _hooks(raw["hooks"], warnings)
    if "shorthand" in raw:
        fields["shorthand"] = _shorthand(raw["shorthand"])
    return Settings(**fields, warnings=tuple(warnings))


def load(env: Mapping[str, str] | None = None) -> Settings | None:
    """Read the project's settings file.

    Args:
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        The validated settings, or ``None`` when there is no project directory or no file.

    Raises:
        SettingsError: When the file cannot be read, is not JSON, or fails validation.
    """
    path = settings_path(env)
    if path is None or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"cannot read {os.path.basename(path)}: {exc}") from exc
    return parse(raw)


def enabled_settings(
    hook: str, prefix: str, env: Mapping[str, str] | None = None
) -> Settings | None:
    """The settings when ``hook`` is switched on, otherwise ``None``.

    Warnings and errors go to stderr as one line each, starting with ``prefix``, and an error
    leaves the hook switched off.

    Args:
        hook: The hook's name, one of :data:`HOOK_NAMES`.
        prefix: The hook's own name, used to start every stderr line.
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        The settings when the hook is on, else ``None``.
    """
    try:
        settings = load(env)
    except SettingsError as exc:
        print(f"{prefix}: settings ignored, every hook is off: {exc}", file=sys.stderr)
        return None
    if settings is None:
        return None
    for warning in settings.warnings:
        print(f"{prefix}: settings warning: {warning}", file=sys.stderr)
    return settings if settings.hook_enabled(hook) else None


def main(argv: list[str]) -> int:
    """Check the settings file from the command line and print a one-line verdict.

    The Bash tool's environment has no ``CLAUDE_PROJECT_DIR``, so a skill passes the project
    root with ``--project-dir``.

    Args:
        argv: Command-line arguments after the program name: an optional ``--project-dir DIR``,
            then an optional ``--path``, which prints the file's path instead of checking it.

    Returns:
        0 when the file is valid or absent, 1 when it has an error, 2 on a usage error.
    """
    env = dict(os.environ)
    args = list(argv)
    if args[:1] == ["--project-dir"]:
        if len(args) < 2:
            print(USAGE)
            return 2
        env["CLAUDE_PROJECT_DIR"] = args[1]
        args = args[2:]
    if args not in ([], ["--path"]):
        print(USAGE)
        return 2
    if args == ["--path"]:
        path = settings_path(env)
        print(path if path is not None else "CLAUDE_PROJECT_DIR is not set")
        return 0
    try:
        settings = load(env)
    except SettingsError as exc:
        print(f"invalid: {exc}")
        return 1
    if settings is None:
        print("absent: no settings file, every hook is off")
        return 0
    on = [name for name in HOOK_NAMES if settings.hook_enabled(name)]
    for warning in settings.warnings:
        print(f"warning: {warning}")
    print(f"valid: hooks on: {', '.join(on) if on else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
