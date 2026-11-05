"""Tests for the barred-folder guard."""

from __future__ import annotations

import json
from pathlib import Path

import barred_paths as bp
import pytest
from conftest import ROOT, ProjectFactory, run_script

SPECS = [
    ":(top,exclude)secrets/",
    ":(top,exclude,icase)*_private*",
    ":(top,exclude)vendor/raw",
]


def env_with(project: ProjectFactory, specs: list[str] | None = None) -> dict[str, str]:
    env = project({"hooks": {"barred_paths": True}, "barred_paths": specs or SPECS})
    root = Path(env["CLAUDE_PROJECT_DIR"])
    (root / "secrets").mkdir()
    (root / "src").mkdir()
    (root / "vendor" / "raw").mkdir(parents=True)
    return env


def call(
    tool: str, tool_input: dict[str, object], env: dict[str, str], cwd: str = ""
) -> object:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": cwd or env["CLAUDE_PROJECT_DIR"],
    }
    return bp.decide(payload, env)


def decision(out: object) -> str | None:
    if out is None:
        return None
    assert isinstance(out, dict)
    return str(out["hookSpecificOutput"]["permissionDecision"])


def test_parse_spec() -> None:
    barred = bp.parse_spec(":(top,exclude,icase)*_private*")
    assert barred is not None
    assert barred.icase
    assert barred.pattern == "*_private*"
    assert barred.fixed_prefix == ""
    folder = bp.parse_spec(":(top,exclude)vendor/raw")
    assert folder is not None
    assert folder.fixed_prefix == "vendor/raw"


@pytest.mark.parametrize(
    ("rel", "barred"),
    [
        ("secrets", True),
        ("secrets/key.pem", True),
        ("secretsx/a", False),
        ("src/My_PRIVATE_notes.txt", True),
        ("src/public.txt", False),
        ("vendor/raw/x/y", True),
        ("vendor/rawish", False),
    ],
)
def test_matching(rel: str, barred: bool) -> None:
    patterns = [p for p in map(bp.parse_spec, SPECS) if p]
    assert any(p.matches(rel) for p in patterns) is barred


def test_read_of_barred_file_denied(project: ProjectFactory) -> None:
    env = env_with(project)
    out = call(
        "Read", {"file_path": env["CLAUDE_PROJECT_DIR"] + "/secrets/key.pem"}, env
    )
    assert decision(out) == "deny"


def test_read_outside_project_passes(project: ProjectFactory) -> None:
    env = env_with(project)
    assert call("Read", {"file_path": "/etc/hosts"}, env) is None


def test_read_of_ordinary_file_passes(project: ProjectFactory) -> None:
    env = env_with(project)
    assert (
        call("Read", {"file_path": env["CLAUDE_PROJECT_DIR"] + "/src/a.py"}, env)
        is None
    )


def test_grep_from_root_is_denied_with_exclusions(project: ProjectFactory) -> None:
    env = env_with(project)
    out = call("Grep", {"pattern": "x"}, env)
    assert decision(out) == "deny"
    assert ":(top,exclude)secrets/" in json.dumps(out)


def test_glob_inside_unrelated_folder_passes_when_no_anywhere_pattern(
    project: ProjectFactory,
) -> None:
    env = env_with(project, [":(top,exclude)secrets/"])
    out = call(
        "Glob", {"pattern": "*.py", "path": env["CLAUDE_PROJECT_DIR"] + "/src"}, env
    )
    assert out is None


def test_bash_cat_of_barred_path_denied(project: ProjectFactory) -> None:
    env = env_with(project)
    assert decision(call("Bash", {"command": "cat secrets/key.pem"}, env)) == "deny"
    assert decision(call("Bash", {"command": "ls secrets"}, env)) == "deny"


def test_bash_unpruned_search_denied(project: ProjectFactory) -> None:
    env = env_with(project)
    for command in (
        "grep -rn TODO .",
        "git grep TODO",
        "find . -name '*.py'",
        "rg TODO",
    ):
        assert decision(call("Bash", {"command": command}, env)) == "deny", command


def test_bash_pruned_search_passes(project: ProjectFactory) -> None:
    env = env_with(project)
    specs = " ".join(f"'{s}'" for s in SPECS)
    assert call("Bash", {"command": f"git grep TODO -- {specs}"}, env) is None


def test_bash_ordinary_commands_pass(project: ProjectFactory) -> None:
    env = env_with(project)
    for command in (
        "ls",
        "ls src",
        "grep TODO src/a.py",
        "git status",
        "echo TODO",
        "cat src/a.py",
    ):
        assert call("Bash", {"command": command}, env) is None, command


def test_bash_unparseable_command_asks(project: ProjectFactory) -> None:
    env = env_with(project)
    assert decision(call("Bash", {"command": "echo 'unclosed"}, env)) == "ask"


def test_off_by_default(project: ProjectFactory) -> None:
    env = project({"barred_paths": SPECS})
    assert (
        call("Read", {"file_path": env["CLAUDE_PROJECT_DIR"] + "/secrets/k"}, env)
        is None
    )


def test_other_tools_pass(project: ProjectFactory) -> None:
    env = env_with(project)
    assert call("Write", {"file_path": "secrets/x"}, env) is None


def test_main_end_to_end(project: ProjectFactory) -> None:
    env = env_with(project)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "cat secrets/key.pem"},
        "cwd": env["CLAUDE_PROJECT_DIR"],
    }
    result = run_script("barred_paths.py", payload, env)
    assert result.returncode == 0
    assert (
        json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    )


def test_main_fails_open(project: ProjectFactory) -> None:
    result = run_script("barred_paths.py", "nope", env_with(project))
    assert result.returncode == 1
    assert result.stdout == ""


def test_wildcard_under_a_barred_folder_denied(project: ProjectFactory) -> None:
    env = env_with(project)
    assert decision(call("Bash", {"command": "cat secrets/*"}, env)) == "deny"
    assert call("Bash", {"command": "cat src/*.py"}, env) is None


def test_hooks_json_matcher_covers_the_guarded_tools() -> None:
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    commands = {
        entry["matcher"]
        for entry in hooks["hooks"]["PreToolUse"]
        if "barred_paths.py" in entry["hooks"][0]["command"]
    }
    assert commands == {
        "|".join(sorted(bp.GUARDED_TOOLS, key=["Read", "Grep", "Glob", "Bash"].index))
    }
