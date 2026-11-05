"""Load and validate a project's ``project-manager`` settings file.

The file lives at ``$CLAUDE_PROJECT_DIR/.claude/project-manager.json``. A plugin's own
``userConfig`` is stored per user, so per-project values need a file inside the project.

Every hook in this plugin calls :func:`load` first and does nothing unless its own flag under
``hooks`` is ``true``. A missing file means every hook is off. A file with a wrong type is an
error, so every hook stays off and the caller reports it. An unknown key is ignored with a
warning, so a settings file written for a newer plugin never silences an older one.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SETTINGS_RELATIVE_PATH = Path(".claude") / "project-manager.json"

HOOK_NAMES = (
    "plain_language_stop",
    "question_check",
    "tracker_write_notice",
    "barred_paths",
)

DEFAULT_TOP_LEVEL_DIRS = ("src", "tests", "docs", "scripts", ".github", ".claude")

KNOWN_KEYS = frozenset(
    {
        "$schema_version",
        "tracker_repo",
        "project",
        "decider",
        "pm_title_prefix",
        "notes_dir",
        "rulings_branch",
        "rulings_path",
        "barred_paths",
        "review_model",
        "hooks",
        "shorthand",
    }
)


class SettingsError(ValueError):
    """The settings file exists but cannot be used."""


@dataclass(frozen=True)
class ProjectBoard:
    """The GitHub Project that holds status: its owner and its number."""

    owner: str
    number: int


@dataclass(frozen=True)
class Shorthand:
    """Project-specific additions to the plain-language patterns."""

    id_prefixes: tuple[str, ...] = ()
    top_level_dirs: tuple[str, ...] = DEFAULT_TOP_LEVEL_DIRS


@dataclass(frozen=True)
class Settings:
    """A validated settings file. Defaults apply to every key the file leaves out."""

    tracker_repo: str = ""
    project: ProjectBoard | None = None
    decider: str = "the decider"
    pm_title_prefix: str = "PM "
    notes_dir: str = ""
    rulings_branch: str = "pm-records"
    rulings_path: str = "rulings.md"
    barred_paths: tuple[str, ...] = ()
    review_model: str = "opus"
    hooks: Mapping[str, bool] = field(default_factory=dict)
    shorthand: Shorthand = field(default_factory=Shorthand)
    warnings: tuple[str, ...] = ()

    def hook_enabled(self, name: str) -> bool:
        """Whether the hook called ``name`` is switched on.

        Args:
            name: One of :data:`HOOK_NAMES`.

        Returns:
            ``True`` only when the file sets that hook's flag to ``true``.
        """
        return self.hooks.get(name, False) is True


def settings_path(env: Mapping[str, str] | None = None) -> Path | None:
    """The settings file's path, or ``None`` when the project directory is unknown.

    Args:
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        The absolute path of the settings file, whether or not it exists.
    """
    environ = os.environ if env is None else env
    project_dir = environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if not project_dir:
        return None
    return Path(project_dir) / SETTINGS_RELATIVE_PATH


def _string(raw: Mapping[str, Any], key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise SettingsError(f"{key} must be a string")
    return value


def _string_tuple(
    raw: Mapping[str, Any], key: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    value = raw.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SettingsError(f"{key} must be a list of strings")
    return tuple(value)


def _project(raw: Mapping[str, Any]) -> ProjectBoard | None:
    value = raw.get("project")
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


def _hooks(raw: Mapping[str, Any], warnings: list[str]) -> dict[str, bool]:
    value = raw.get("hooks", {})
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


def _shorthand(raw: Mapping[str, Any]) -> Shorthand:
    value = raw.get("shorthand", {})
    if not isinstance(value, dict):
        raise SettingsError("shorthand must be an object")
    return Shorthand(
        id_prefixes=_string_tuple(value, "id_prefixes", ()),
        top_level_dirs=_string_tuple(value, "top_level_dirs", DEFAULT_TOP_LEVEL_DIRS),
    )


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
    return Settings(
        tracker_repo=_string(raw, "tracker_repo", ""),
        project=_project(raw),
        decider=_string(raw, "decider", "the decider"),
        pm_title_prefix=_string(raw, "pm_title_prefix", "PM "),
        notes_dir=_string(raw, "notes_dir", ""),
        rulings_branch=_string(raw, "rulings_branch", "pm-records"),
        rulings_path=_string(raw, "rulings_path", "rulings.md"),
        barred_paths=_string_tuple(raw, "barred_paths", ()),
        review_model=_string(raw, "review_model", "opus"),
        hooks=_hooks(raw, warnings),
        shorthand=_shorthand(raw),
        warnings=tuple(warnings),
    )


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
    if path is None or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"cannot read {path.name}: {exc}") from exc
    return parse(raw)


def enabled_settings(
    hook: str, prefix: str, env: Mapping[str, str] | None = None
) -> Settings | None:
    """The settings when ``hook`` is switched on, otherwise ``None``.

    A hook calls this first. Warnings and errors go to stderr as one line each, starting with
    ``prefix``, and an error leaves the hook switched off.

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
            print("usage: pm_settings.py [--project-dir DIR] [--path]")
            return 2
        env["CLAUDE_PROJECT_DIR"] = args[1]
        args = args[2:]
    if args not in ([], ["--path"]):
        print("usage: pm_settings.py [--project-dir DIR] [--path]")
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
