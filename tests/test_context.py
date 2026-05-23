from pathlib import Path

from codexflow.config import ContextConfig
from codexflow.context import ContextCollector, render_issue
from codexflow.models import GitHubComment, GitHubIssue

from .helpers import FakeRunner, command_result


def test_context_collector_collects_priority_files_and_filters_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("Rules", encoding="utf-8")
    (repo / "README.md").write_text("Readme", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=value\n", encoding="utf-8")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Guide", encoding="utf-8")

    issue = GitHubIssue(
        number=7,
        title="Do task",
        body="## Goal\nMake it work",
        comments=(GitHubComment(author="alice", body="note"),),
    )
    runner = FakeRunner([command_result(["git"], stdout="abc123 initial\n")])

    result = ContextCollector(repo, config=ContextConfig(), runner=runner).collect(issue=issue)

    assert "Issue #7: Do task" in result.content
    assert "Rules" in result.content
    assert "Readme" in result.content
    assert "Guide" in result.content
    assert "abc123 initial" in result.content
    assert "SECRET=value" not in result.content
    assert ".env" not in result.included_files
    assert any(decision.path == ".env" for decision in result.excluded_files)


def test_context_collector_enforces_max_chars(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x" * 500, encoding="utf-8")
    runner = FakeRunner([command_result(["git"], stdout="")])

    result = ContextCollector(
        repo,
        config=ContextConfig(max_context_chars=100, include_docs_glob=[]),
        runner=runner,
    ).collect()

    assert result.truncated
    assert len(result.content) <= 115
    assert "[TRUNCATED]" in result.content


def test_context_collector_redacts_sensitive_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("token = ghp_abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    issue = GitHubIssue(number=1, title="Title", body="api_key=sk-testabcdefghijklmnopqrstuvwxyz")
    runner = FakeRunner([command_result(["git"], stdout="")])

    result = ContextCollector(repo, config=ContextConfig(include_docs_glob=[]), runner=runner).collect(issue=issue)

    assert "ghp_" not in result.content
    assert "sk-test" not in result.content
    assert "[REDACTED]" in result.content


def test_render_issue_can_include_comments() -> None:
    issue = GitHubIssue(
        number=1,
        title="Title",
        body="Body",
        comments=(GitHubComment(author="bob", body="Comment"),),
    )

    rendered = render_issue(issue, include_comments=True)

    assert "# Issue #1: Title" in rendered
    assert "- bob: Comment" in rendered


def test_context_collector_includes_issue_related_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src"
    src.mkdir()
    (src / "toycalc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    issue = GitHubIssue(number=1, title="Update toycalc add", body="Change add behavior")
    runner = FakeRunner([command_result(["git"], stdout="")])

    result = ContextCollector(repo, config=ContextConfig(include_docs_glob=[]), runner=runner).collect(issue=issue)

    assert "Issue-Related Code" in result.content
    assert "src/toycalc.py" in result.content
    assert "def add" in result.content
