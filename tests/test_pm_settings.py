"""Tests for the settings loader."""

from __future__ import annotations

from pathlib import Path

import pm_settings
import pytest
from conftest import ProjectFactory


def test_missing_project_dir_means_no_settings() -> None:
    assert pm_settings.load({}) is None


def test_missing_file_means_no_settings(project: ProjectFactory) -> None:
    assert pm_settings.load(project()) is None


def test_defaults_fill_every_key(project: ProjectFactory) -> None:
    settings = pm_settings.load(project({}))
    assert settings is not None
    assert settings.rulings_branch == "pm-records"
    assert settings.pm_title_prefix == "PM "
    assert settings.barred_paths == ()
    assert not any(settings.hook_enabled(name) for name in pm_settings.HOOK_NAMES)


def test_full_file_parses(project: ProjectFactory) -> None:
    settings = pm_settings.load(
        project(
            {
                "tracker_repo": "owner/name",
                "project": {"owner": "owner", "number": 3},
                "decider": "Sam",
                "barred_paths": [":(top,exclude)secrets/"],
                "hooks": {"question_check": True, "barred_paths": False},
                "shorthand": {"id_prefixes": ["PROJ"], "top_level_dirs": ["lib"]},
            }
        )
    )
    assert settings is not None
    assert settings.project == pm_settings.ProjectBoard(owner="owner", number=3)
    assert settings.hook_enabled("question_check")
    assert not settings.hook_enabled("barred_paths")
    assert settings.shorthand.id_prefixes == ("PROJ",)
    assert settings.shorthand.top_level_dirs == ("lib",)


def test_unknown_keys_warn_and_are_ignored(project: ProjectFactory) -> None:
    settings = pm_settings.load(project({"future_key": 1, "hooks": {"new_hook": True}}))
    assert settings is not None
    assert len(settings.warnings) == 2


@pytest.mark.parametrize(
    "bad",
    [
        {"decider": 3},
        {"barred_paths": "secrets/"},
        {"barred_paths": [1]},
        {"hooks": {"question_check": "yes"}},
        {"hooks": []},
        {"project": {"owner": "o", "number": "3"}},
        {"project": {"owner": "o", "number": True}},
        {"shorthand": {"id_prefixes": "PROJ"}},
        [],
    ],
)
def test_wrong_types_raise(project: ProjectFactory, bad: object) -> None:
    with pytest.raises(pm_settings.SettingsError):
        pm_settings.load(project(bad))


def test_unreadable_json_raises(project: ProjectFactory) -> None:
    with pytest.raises(pm_settings.SettingsError):
        pm_settings.load(project(raw="{not json"))


def test_enabled_settings_reports_error_and_stays_off(
    project: ProjectFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pm_settings.enabled_settings("question_check", "t", project(raw="{")) is None
    assert capsys.readouterr().err.startswith("t: settings ignored")


def test_enabled_settings_only_for_the_named_hook(project: ProjectFactory) -> None:
    env = project({"hooks": {"question_check": True}})
    assert pm_settings.enabled_settings("question_check", "t", env) is not None
    assert pm_settings.enabled_settings("plain_language_stop", "t", env) is None


def test_cli_verdicts(
    project: ProjectFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    env = project({"hooks": {"tracker_write_notice": True}})
    root = env["CLAUDE_PROJECT_DIR"]
    assert pm_settings.main(["--project-dir", root]) == 0
    assert "tracker_write_notice" in capsys.readouterr().out
    assert pm_settings.main(["--project-dir", root, "--path"]) == 0
    assert capsys.readouterr().out.strip().endswith("project-manager.json")
    assert pm_settings.main(["--bogus"]) == 2


def test_settings_found_from_a_subfolder(project: ProjectFactory) -> None:
    env = project({"hooks": {"question_check": True}})
    root = env["CLAUDE_PROJECT_DIR"]
    (Path(root) / ".git").mkdir()
    sub = Path(root) / "src" / "deep"
    sub.mkdir(parents=True)
    settings = pm_settings.load({"CLAUDE_PROJECT_DIR": str(sub)})
    assert settings is not None
    assert settings.project_root == root


def test_relative_notes_dir_is_an_error(project: ProjectFactory) -> None:
    with pytest.raises(pm_settings.SettingsError):
        pm_settings.load(project({"notes_dir": "notes"}))
