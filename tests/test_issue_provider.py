from pathlib import Path

from codexflow.config import CodexFlowConfig, IssueProviderConfig, TargetConfig
from codexflow.github import GitHubClient
from codexflow.gitlab import GitLabClient
from codexflow.issue_provider import create_issue_client


def test_create_github_issue_client() -> None:
    config = CodexFlowConfig(
        target=TargetConfig(path=Path("."), github_repo="owner/repo"),
        issues=IssueProviderConfig(provider="github", repo="owner/repo"),
    )

    client = create_issue_client(config)

    assert isinstance(client, GitHubClient)


def test_create_gitlab_issue_client() -> None:
    config = CodexFlowConfig(
        target=TargetConfig(path=Path("."), base_branch="V2.0"),
        issues=IssueProviderConfig(
            provider="gitlab",
            repo="che/stock_agent",
            host="gitlab.kingdomai.com",
            token_env="GITLAB_TOKEN",
        ),
    )

    client = create_issue_client(config)

    assert isinstance(client, GitLabClient)
    assert client.repo == "che/stock_agent"
    assert client.api_url == "https://gitlab.kingdomai.com/api/v4"
