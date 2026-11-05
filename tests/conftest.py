"""Shared fixtures: the scripts folder on the import path, and a project with a settings file."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

ProjectFactory = Callable[..., dict[str, str]]


@pytest.fixture
def project(tmp_path: Path) -> ProjectFactory:
    """A factory: write a settings file into a fresh project and return the hook environment."""

    def make(settings: object | None = None, raw: str | None = None) -> dict[str, str]:
        root = tmp_path / "proj"
        (root / ".claude").mkdir(parents=True, exist_ok=True)
        path = root / ".claude" / "project-manager.json"
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
        elif settings is not None:
            path.write_text(json.dumps(settings), encoding="utf-8")
        return {"CLAUDE_PROJECT_DIR": str(root)}

    return make


def run_script(
    name: str, payload: Any, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one hook script as Claude Code would: JSON on stdin, project dir in the environment."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **env},
        check=False,
        timeout=30,
    )
