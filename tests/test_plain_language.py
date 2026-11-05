"""Tests for the plain-language hook, both events."""

from __future__ import annotations

import json

import plain_language
import pm_settings
import pytest
from conftest import ProjectFactory, run_script

ON = {"hooks": {"question_check": True, "plain_language_stop": True}}


def scan(text: str, **shorthand: tuple[str, ...]) -> list[str]:
    return plain_language.Scanner(pm_settings.Shorthand(**shorthand)).find(text)


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("see #42 for that", "#42"),
        ("merged in PR 17", "PR 17"),
        ("as comment 3 says", "comment 3"),
        ("the bug is in main.rs:12", "main.rs:12"),
        ("edit config.yaml first", "config.yaml"),
        ("look at line 40", "line 40"),
        ("per §3.2 of the spec", "§3.2"),
        ("landed as 3f9c2ab", "3f9c2ab"),
        ("open ./notes/today", "./notes/today"),
        ("under src/lib", "src/lib"),
        ("in /home/me/project", "/home/me/project"),
    ],
)
def test_generic_shorthand_matches(text: str, hit: str) -> None:
    assert hit in scan(text)


@pytest.mark.parametrize(
    "text",
    [
        "step #1 comes first",
        "the colour #112233 is fine",
        "the wall was defaced",
        "we use Node.js here",
        "read and/or write",
        "port TCP/443 is open",
        "see https://example.com/a/b.md for more",
        "the /admin route",
        "plain words only",
    ],
)
def test_near_misses_pass(text: str) -> None:
    assert scan(text) == []


def test_project_prefixes_come_from_settings() -> None:
    assert scan("fixed PROJ-12 today") == []
    assert scan("fixed PROJ-12 today", id_prefixes=("PROJ",)) == ["PROJ-12"]


def test_top_level_dirs_come_from_settings() -> None:
    assert scan("in lib/core") == []
    assert scan("in lib/core", top_level_dirs=("lib",)) == ["lib/core"]


def test_fenced_blocks_and_sources_are_exempt() -> None:
    message = "All done.\n\n```\ngit show 3f9c2ab\n```\n\n## Sources\n- 3f9c2ab, #42\n"
    assert scan(plain_language.reply_text(message)) == []


def test_trailing_sources_line_without_heading_is_exempt() -> None:
    message = "All done.\n\nSources: #42, main.py"
    assert scan(plain_language.reply_text(message)) == []


def test_later_heading_ends_the_sources_exemption() -> None:
    message = "## Sources\n- #42\n\n## Next\nsee #43\n"
    assert scan(plain_language.reply_text(message)) == ["#42", "#43"]


def question(text: str, preview: str = "") -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": text,
                    "header": "Pick",
                    "multiSelect": False,
                    "options": [
                        {"label": "Yes", "description": "go", "preview": preview},
                        {"label": "No", "description": "stop"},
                    ],
                }
            ]
        },
    }


def test_question_with_shorthand_is_denied(project: ProjectFactory) -> None:
    out = plain_language.decide(question("Merge #42 now?"), project(ON))
    assert out is not None
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert '"#42"' in hso["permissionDecisionReason"]


def test_question_preview_fence_is_exempt(project: ProjectFactory) -> None:
    out = plain_language.decide(question("Merge it?", "```\n#42\n```"), project(ON))
    assert out is None


def test_question_check_off_by_default(project: ProjectFactory) -> None:
    assert plain_language.decide(question("Merge #42 now?"), project({})) is None
    assert plain_language.decide(question("Merge #42 now?"), project()) is None


def stop(message: str, active: bool = False) -> dict[str, object]:
    return {
        "hook_event_name": "Stop",
        "stop_hook_active": active,
        "last_assistant_message": message,
    }


def test_stop_blocks_once(project: ProjectFactory) -> None:
    env = project(ON)
    out = plain_language.decide(stop("Pushed 3f9c2ab."), env)
    assert out is not None
    assert out["decision"] == "block"
    assert plain_language.decide(stop("Pushed 3f9c2ab.", active=True), env) is None


def test_stop_clean_reply_passes(project: ProjectFactory) -> None:
    assert plain_language.decide(stop("Pushed the fix."), project(ON)) is None


def test_stop_null_message_passes(project: ProjectFactory) -> None:
    payload = {"hook_event_name": "Stop", "stop_hook_active": False}
    assert plain_language.decide(payload, project(ON)) is None


def test_other_tools_pass(project: ProjectFactory) -> None:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}}
    assert plain_language.decide(payload, project(ON)) is None


def test_main_end_to_end_deny(project: ProjectFactory) -> None:
    result = run_script("plain_language.py", question("Merge #42 now?"), project(ON))
    assert result.returncode == 0
    assert (
        json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    )


def test_main_fails_open_on_bad_input(project: ProjectFactory) -> None:
    result = run_script("plain_language.py", "not json", project(ON))
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("plain_language:")


def test_main_bad_shape_fails_open(project: ProjectFactory) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {},
    }
    result = run_script("plain_language.py", payload, project(ON))
    assert result.returncode == 1
    assert result.stdout == ""


def test_scan_is_linear_on_long_input() -> None:
    text = "a" * 200_000 + " #42"
    assert scan(text) == ["#42"]


@pytest.mark.parametrize("name", ["React.js", "Alpine.js", "Ember.js", "Node.js"])
def test_product_names_ending_in_js_pass(name: str) -> None:
    assert scan(f"built with {name} today") == []


def test_lowercase_js_file_still_matches() -> None:
    assert scan("see index.js") == ["index.js"]


def test_issue_word_with_number_matches() -> None:
    assert scan("fixed in Issue 12") == ["Issue 12"]


@pytest.mark.parametrize("text", ["client-side/server-side/edge", "e-mail/phone/post"])
def test_hyphenated_word_lists_pass(text: str) -> None:
    assert scan(text) == []


def test_sources_heading_at_the_top_exempts_nothing() -> None:
    message = "## Sources\nMerged #42 today.\n"
    assert scan(plain_language.reply_text(message)) == ["#42"]
