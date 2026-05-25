from __future__ import annotations

from typing import Protocol

from .config import CodexFlowConfig
from .github import GitHubClient
from .gitlab import GitLabClient
from .models import GitHubIssue, PullRequestInfo


class IssueClient(Protocol):
    def get_ready_issue(self) -> GitHubIssue | None: ...

    def get_issue(self, number: int, *, include_comments: bool = False) -> GitHubIssue: ...

    def claim_issue(self, number: int) -> None: ...

    def mark_review(self, number: int) -> None: ...

    def mark_blocked(self, number: int) -> None: ...

    def restore_ready(self, number: int) -> None: ...

    def create_pr(self, *, base: str, head: str, title: str, body_file: str) -> PullRequestInfo: ...

    def comment_issue(self, number: int, *, body_file: str) -> None: ...


def create_issue_client(config: CodexFlowConfig) -> IssueClient:
    provider = config.issues.provider
    labels = {
        "ready_label": config.issues.ready_label,
        "working_label": config.issues.working_label,
        "review_label": config.issues.review_label,
        "blocked_label": config.issues.blocked_label,
    }
    if provider == "github":
        return GitHubClient(repo=config.issue_repo, **labels)
    if provider == "gitlab":
        repo = config.issue_repo
        if not repo:
            raise ValueError("GitLab issue provider requires issues.repo.")
        return GitLabClient(
            repo=repo,
            host=config.issues.host,
            api_url=config.issues.api_url,
            token_env=config.issues.token_env,
            **labels,
        )
    raise ValueError(f"Unsupported issue provider: {provider}")
