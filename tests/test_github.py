import json

import pytest

from codexflow.github import GitHubClient, GitHubClientError

from .helpers import FakeRunner, command_result


def test_get_ready_issue_parses_first_issue() -> None:
    payload = [
        {
            "number": 123,
            "title": "Add feature",
            "body": "## Goal\nShip it",
            "labels": [{"name": "codex:ready"}],
            "url": "https://github.com/owner/repo/issues/123",
            "state": "OPEN",
            "author": {"login": "alice"},
            "createdAt": "2026-05-23T00:00:00Z",
            "updatedAt": "2026-05-23T01:00:00Z",
        }
    ]
    runner = FakeRunner([command_result(["gh"], stdout=json.dumps(payload))])

    issue = GitHubClient(runner=runner, repo="owner/repo").get_ready_issue()

    assert issue is not None
    assert issue.number == 123
    assert issue.title == "Add feature"
    assert issue.author == "alice"
    assert issue.has_label("codex:ready")
    assert runner.calls[0][:3] == ("gh", "--repo", "owner/repo")
    assert "issue" in runner.calls[0]
    assert "list" in runner.calls[0]


def test_get_ready_issue_returns_none_when_queue_empty() -> None:
    runner = FakeRunner([command_result(["gh"], stdout="[]")])

    issue = GitHubClient(runner=runner).get_ready_issue()

    assert issue is None


def test_get_issue_can_include_comments() -> None:
    payload = {
        "number": 5,
        "title": "Fix bug",
        "body": "body",
        "labels": [],
        "comments": [
            {
                "author": {"login": "bob"},
                "body": "extra context",
                "createdAt": "2026-05-23T02:00:00Z",
            }
        ],
    }
    runner = FakeRunner([command_result(["gh"], stdout=json.dumps(payload))])

    issue = GitHubClient(runner=runner).get_issue(5, include_comments=True)

    assert issue.comments[0].author == "bob"
    assert issue.comments[0].body == "extra context"
    assert "comments" in runner.calls[0][-1]


def test_claim_issue_updates_labels_idempotently() -> None:
    runner = FakeRunner([command_result(["gh"])])

    GitHubClient(runner=runner).claim_issue(123)

    assert runner.calls[0] == (
        "gh",
        "issue",
        "edit",
        "123",
        "--remove-label",
        "codex:ready",
        "--add-label",
        "codex:working",
    )


def test_github_failure_raises_clear_error() -> None:
    runner = FakeRunner([command_result(["gh"], exit_code=1, stderr="not authenticated")])

    with pytest.raises(GitHubClientError, match="not authenticated"):
        GitHubClient(runner=runner).get_ready_issue()


def test_create_pr_parses_url_output() -> None:
    runner = FakeRunner(
        [
            command_result(
                ["gh"],
                stdout="https://github.com/owner/repo/pull/17\n",
            )
        ]
    )

    pr = GitHubClient(runner=runner, repo="owner/repo").create_pr(
        base="main",
        head="codex/issue-1",
        title="CodexFlow: issue",
        body_file=".codexflow/runs/run/pr_body.md",
    )

    assert pr.url == "https://github.com/owner/repo/pull/17"
    assert pr.number == 17
    assert runner.calls[0] == (
        "gh",
        "--repo",
        "owner/repo",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        "codex/issue-1",
        "--title",
        "CodexFlow: issue",
        "--body-file",
        ".codexflow/runs/run/pr_body.md",
    )


def test_comment_issue_uses_body_file() -> None:
    runner = FakeRunner([command_result(["gh"])])

    GitHubClient(runner=runner, repo="owner/repo").comment_issue(123, body_file=".codexflow/comment.md")

    assert runner.calls[0] == (
        "gh",
        "--repo",
        "owner/repo",
        "issue",
        "comment",
        "123",
        "--body-file",
        ".codexflow/comment.md",
    )
