from pathlib import Path

import pytest

from codexflow.gitlab import GitLabClient, GitLabClientError


def test_gitlab_normalizes_full_project_url_and_gets_ready_issue() -> None:
    calls = []

    def requester(method, path, params, data):
        calls.append((method, path, params, data))
        return [
            {
                "iid": 123,
                "title": "Add feature",
                "description": "## Goal\nShip it",
                "labels": ["codex:ready"],
                "web_url": "https://gitlab.kingdomai.com/che/stock_agent/-/issues/123",
                "state": "opened",
                "author": {"username": "alice"},
                "created_at": "2026-05-25T00:00:00Z",
                "updated_at": "2026-05-25T01:00:00Z",
            }
        ]

    issue = GitLabClient(
        repo="https://gitlab.kingdomai.com/che/stock_agent/-/tree/V2.0",
        requester=requester,
        token="token",
    ).get_ready_issue()

    assert issue is not None
    assert issue.number == 123
    assert issue.title == "Add feature"
    assert issue.author == "alice"
    assert issue.has_label("codex:ready")
    assert calls[0][0] == "GET"
    assert calls[0][1] == "projects/che%2Fstock_agent/issues"
    assert calls[0][2]["labels"] == "codex:ready"


def test_gitlab_get_issue_can_include_comments() -> None:
    calls = []

    def requester(method, path, params, data):
        calls.append((method, path, params, data))
        if path.endswith("/notes"):
            return [
                {"body": "system note", "system": True, "author": {"username": "bot"}},
                {
                    "body": "extra context",
                    "system": False,
                    "author": {"username": "bob"},
                    "created_at": "2026-05-25T02:00:00Z",
                },
            ]
        return {"iid": 5, "title": "Fix bug", "description": "body", "labels": []}

    issue = GitLabClient(repo="che/stock_agent", host="gitlab.kingdomai.com", requester=requester, token="token").get_issue(
        5,
        include_comments=True,
    )

    assert issue.comments[0].author == "bob"
    assert issue.comments[0].body == "extra context"
    assert calls[0][1] == "projects/che%2Fstock_agent/issues/5"
    assert calls[1][1] == "projects/che%2Fstock_agent/issues/5/notes"


def test_gitlab_claim_issue_updates_label_set() -> None:
    calls = []

    def requester(method, path, params, data):
        calls.append((method, path, params, data))
        return {"iid": 123, "labels": ["codex:working"]}

    GitLabClient(repo="che/stock_agent", host="gitlab.kingdomai.com", requester=requester, token="token").claim_issue(123)

    assert calls == [
        (
            "PUT",
            "projects/che%2Fstock_agent/issues/123",
            None,
            {"add_labels": "codex:working", "remove_labels": "codex:ready"},
        ),
    ]


def test_gitlab_create_merge_request_and_comment_issue(tmp_path: Path) -> None:
    calls = []
    body = tmp_path / "body.md"
    body.write_text("run summary", encoding="utf-8")

    def requester(method, path, params, data):
        calls.append((method, path, params, data))
        if path.endswith("/merge_requests"):
            return {"web_url": "https://gitlab.kingdomai.com/che/stock_agent/-/merge_requests/17", "iid": 17}
        return {}

    client = GitLabClient(repo="che/stock_agent", host="gitlab.kingdomai.com", requester=requester, token="token")
    pr = client.create_pr(base="V2.0", head="codex/issue-1", title="Address issue #1", body_file=str(body))
    client.comment_issue(1, body_file=str(body))

    assert pr.url.endswith("/merge_requests/17")
    assert pr.number == 17
    assert calls[0][0] == "POST"
    assert calls[0][1] == "projects/che%2Fstock_agent/merge_requests"
    assert calls[0][3]["description"] == "run summary"
    assert calls[1] == (
        "POST",
        "projects/che%2Fstock_agent/issues/1/notes",
        None,
        {"body": "run summary"},
    )


def test_gitlab_requires_host_or_api_url_for_relative_repo() -> None:
    with pytest.raises(GitLabClientError, match="host or issues.api_url"):
        GitLabClient(repo="che/stock_agent", token="token")
