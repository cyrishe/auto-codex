from __future__ import annotations

import json
from pathlib import Path

from codexflow.command import CommandRunner
from codexflow.config import (
    CodexConfig,
    CodexFlowConfig,
    CommitConfig,
    GitHubConfig,
    StorageConfig,
    TargetConfig,
    TestConfig as CodexTestConfig,
    WorktreeConfig,
)
from codexflow.models import GitHubIssue, GitHubLabel


class TrackingGitHub:
    def __init__(self, issue: GitHubIssue) -> None:
        self.issue = issue
        self.labels = {"codex:ready"}
        self.events: list[str] = []

    def get_ready_issue(self) -> GitHubIssue | None:
        self.events.append("get_ready_issue")
        if "codex:ready" not in self.labels:
            return None
        return self._issue_with_current_labels()

    def get_issue(self, number: int, *, include_comments: bool = False) -> GitHubIssue:
        self.events.append(f"get_issue:{number}")
        assert number == self.issue.number
        return self._issue_with_current_labels()

    def claim_issue(self, number: int) -> None:
        self.events.append(f"claim:{number}")
        self.labels.discard("codex:ready")
        self.labels.add("codex:working")

    def mark_review(self, number: int) -> None:
        self.events.append(f"mark_review:{number}")
        self.labels.discard("codex:working")
        self.labels.add("codex:review")

    def mark_blocked(self, number: int) -> None:
        self.events.append(f"mark_blocked:{number}")
        self.labels.discard("codex:working")
        self.labels.add("codex:blocked")

    def _issue_with_current_labels(self) -> GitHubIssue:
        return GitHubIssue(
            number=self.issue.number,
            title=self.issue.title,
            body=self.issue.body,
            labels=tuple(GitHubLabel(name=label) for label in sorted(self.labels)),
            url=self.issue.url,
            state=self.issue.state,
            author=self.issue.author,
            created_at=self.issue.created_at,
            updated_at=self.issue.updated_at,
            comments=self.issue.comments,
        )


def toy_issue() -> GitHubIssue:
    return GitHubIssue(
        number=7,
        title="Add multiply(a, b)",
        body="""## 背景

toycalc currently supports addition only.

## 目标

Add `multiply(a, b)` to `src/toycalc.py`.

## 验收标准

- [ ] `multiply(3, 4)` returns `12`.
- [ ] Existing `add(a, b)` behavior remains unchanged.

## 评估方式

```bash
PYTHONPATH=src python -m pytest -q
```
""",
    )


def init_toy_repo(path: Path) -> Path:
    path.mkdir()
    runner = CommandRunner()
    assert runner.run(["git", "init"], cwd=path).ok
    assert runner.run(["git", "config", "user.email", "codexflow@example.com"], cwd=path).ok
    assert runner.run(["git", "config", "user.name", "CodexFlow Tests"], cwd=path).ok
    (path / "src").mkdir()
    (path / "tests").mkdir()
    (path / "README.md").write_text("# toycalc\n", encoding="utf-8")
    (path / ".gitignore").write_text(
        """__pycache__/
*.pyc
.pytest_cache/
""",
        encoding="utf-8",
    )
    (path / "pyproject.toml").write_text(
        """[project]
name = "toycalc"
version = "0.1.0"
""",
        encoding="utf-8",
    )
    (path / "src" / "toycalc.py").write_text(
        """def add(a: int, b: int) -> int:
    return a + b
""",
        encoding="utf-8",
    )
    (path / "tests" / "test_toycalc.py").write_text(
        """from toycalc import add


def test_add() -> None:
    assert add(2, 3) == 5
""",
        encoding="utf-8",
    )
    assert runner.run(["git", "add", "."], cwd=path).ok
    assert runner.run(["git", "commit", "-m", "initial toycalc"], cwd=path).ok
    assert runner.run(["git", "branch", "-M", "main"], cwd=path).ok
    return path


def toy_config(tmp_path: Path, repo: Path, *, codex: CodexConfig | None = None) -> CodexFlowConfig:
    return CodexFlowConfig(
        target=TargetConfig(path=repo, github_repo="owner/toy-repo", base_branch="main"),
        storage=StorageConfig(
            runs_dir=tmp_path / "runs",
            db_path=tmp_path / "codexflow.db",
            worktree_dir=tmp_path / "worktrees",
        ),
        github=GitHubConfig(enabled=True),
        worktree=WorktreeConfig(enabled=True),
        codex=codex or CodexConfig(),
        tests=CodexTestConfig(
            command="PYTHONPATH=src python -m pytest -q",
            timeout_seconds=60,
            required=True,
            fail_on_failure=True,
            allow_skipped=False,
        ),
        commit=CommitConfig(auto_commit=True, auto_push=False, create_pr=False),
    )


def review_json(summary: str) -> str:
    return json.dumps(
        {
            "verdict": "pass",
            "score": 9,
            "risk_level": "low",
            "summary": summary,
            "blocking_issues": [],
            "non_blocking_suggestions": [],
        }
    )
