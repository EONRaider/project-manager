"""Tests for the reminder after GitHub writes."""

from __future__ import annotations

import json

import pytest
import tracker_write_notice as twn
from conftest import ProjectFactory, run_script

ON = {"hooks": {"tracker_write_notice": True}, "pm_title_prefix": "PM "}


def post(
    tool: str, tool_input: object | None = None, **extra: object
) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": tool_input or {},
        **extra,
    }


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__github__issue_write",
        "mcp__github__add_issue_comment",
        "mcp__0a1b2c3d-uuid__sub_issue_write",
        "mcp__gh__add_reply_to_pull_request_comment",
        "mcp__github__merge_pull_request",
    ],
)
def test_mcp_writes_on_any_server_match(tool: str) -> None:
    assert twn.is_tracker_write(post(tool))


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__github__issue_read",
        "mcp__github__list_issues",
        "Read",
        "mcp__x__issue_writer",
    ],
)
def test_reads_and_lookalikes_do_not_match(tool: str) -> None:
    assert not twn.is_tracker_write(post(tool))


@pytest.mark.parametrize(
    "command",
    [
        "gh issue comment 12 --body 'done'",
        "gh -R owner/repo issue edit 12 --add-label x",
        "gh pr create --fill",
        "cd repo && gh pr merge 5 --merge",
        "gh project item-edit --id X --field-id Y --single-select-option-id Z",
        "gh api graphql -f query='mutation { addComment(input: {}) { clientMutationId } }'",
        "gh api -X PATCH repos/o/r/issues/1 -f state=closed",
        "gh api repos/o/r/issues/1/comments -f body=hi",
        "GH_TOKEN=x gh issue close 3",
    ],
)
def test_gh_writes_match(command: str) -> None:
    assert twn.is_gh_write(command)


@pytest.mark.parametrize(
    "command",
    [
        "gh issue view 12",
        "gh pr list --state open",
        "gh project item-list 1 --owner @me",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api repos/o/r/issues",
        "gh api -X GET repos/o/r/issues -f per_page=5",
        "echo gh issue comment",
        "git commit -m 'gh pr create'",
    ],
)
def test_gh_reads_do_not_match(command: str) -> None:
    assert not twn.is_gh_write(command)


def test_notice_when_on(project: ProjectFactory) -> None:
    out = twn.decide(post("mcp__github__issue_write"), project(ON))
    assert out is not None
    assert "PM" in out["hookSpecificOutput"]["additionalContext"]


def test_silent_when_off(project: ProjectFactory) -> None:
    assert twn.decide(post("mcp__github__issue_write"), project({})) is None


def test_silent_in_a_subagent(project: ProjectFactory) -> None:
    assert (
        twn.decide(post("mcp__github__issue_write", agent_id="a1"), project(ON)) is None
    )


def test_notice_never_repeats_tool_input(project: ProjectFactory) -> None:
    payload = post("Bash", {"command": "gh issue comment 1 --body 'SECRET-TEXT'"})
    out = twn.decide(payload, project(ON))
    assert out is not None
    assert "SECRET-TEXT" not in json.dumps(out)


def test_main_end_to_end(project: ProjectFactory) -> None:
    result = run_script(
        "tracker_write_notice.py", post("mcp__github__issue_write"), project(ON)
    )
    assert result.returncode == 0
    assert (
        json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"]
        == "PostToolUse"
    )


def test_main_fails_open(project: ProjectFactory) -> None:
    result = run_script("tracker_write_notice.py", "[]", project(ON))
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.startswith("tracker_write_notice:")
