from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from codexflow.codex_runner import CodexResult
from codexflow.config import (
    CodexFlowConfig,
    CommitConfig,
    GitHubConfig,
    StorageConfig,
    TargetConfig,
    TestConfig as CodexTestConfig,
    WorktreeConfig,
)
from codexflow.github import GitHubClient
from codexflow.models import GitHubIssue
from codexflow.pipeline import Pipeline

from .helpers import command_result
from .integration_support import review_json


pytestmark = pytest.mark.skipif(
    os.environ.get("CODEXFLOW_REAL_GITHUB") != "1" or shutil.which("gh") is None,
    reason="set CODEXFLOW_REAL_GITHUB=1, install gh, and set CODEXFLOW_GITHUB_REPO to run",
)


def test_phase3_real_github_issue_label_flow(tmp_path: Path) -> None:
    repo_name = os.environ.get("CODEXFLOW_GITHUB_REPO")
    if not repo_name:
        pytest.skip("CODEXFLOW_GITHUB_REPO is required, for example owner/repo")
    _require_gh_auth()

    target = tmp_path / "target"
    _run(["gh", "repo", "clone", repo_name, str(target)])
    _run(["git", "config", "user.email", "codexflow@example.com"], cwd=target)
    _run(["git", "config", "user.name", "CodexFlow Tests"], cwd=target)
    base_branch = os.environ.get("CODEXFLOW_GITHUB_BASE_BRANCH") or _current_branch(target)
    _ensure_label(repo_name, "codex:ready", "0E8A16")
    _ensure_label(repo_name, "codex:working", "FBCA04")
    _ensure_label(repo_name, "codex:review", "1D76DB")
    _ensure_label(repo_name, "codex:blocked", "B60205")
    issue_number = _create_issue(repo_name)
    try:
        _run(["gh", "issue", "edit", str(issue_number), "--repo", repo_name, "--add-label", "codex:ready"])
        config = CodexFlowConfig(
            target=TargetConfig(path=target, github_repo=repo_name, base_branch=base_branch),
            storage=StorageConfig(
                runs_dir=tmp_path / "runs",
                db_path=tmp_path / "codexflow.db",
                worktree_dir=tmp_path / "worktrees",
            ),
            github=GitHubConfig(enabled=True),
            worktree=WorktreeConfig(enabled=True),
            tests=CodexTestConfig(command="test -f feature.txt", timeout_seconds=60, required=True),
            commit=CommitConfig(auto_commit=True, auto_push=False, create_pr=False, comment_on_issue=False),
        )

        result = Pipeline(config=config, github=GitHubClient(repo=repo_name), codex=RealGitHubFakeCodex()).run_issue(
            issue_number
        )

        labels = _issue_labels(repo_name, issue_number)
        assert result.status == "DONE"
        assert result.commit_sha is not None
        assert "codex:ready" not in labels
        assert "codex:working" not in labels
        assert "codex:review" in labels
        assert (result.run_dir / "04_git_diff.patch").read_text(encoding="utf-8").find("feature.txt") >= 0
        assert (result.run_dir / "05_test.log").read_text(encoding="utf-8").find("status: pass") >= 0
    finally:
        _run(["gh", "issue", "close", str(issue_number), "--repo", repo_name, "--comment", "CodexFlow E2E cleanup."])


class RealGitHubFakeCodex:
    def run(
        self,
        *,
        cwd: Path,
        prompt_path: Path,
        output_path: Path,
        sandbox: str,
        schema_path: Path | None = None,
        json_stream_path: Path | None = None,
        extra_args: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> CodexResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.name == "01_dev_design.output.json":
            output_path.write_text(
                json.dumps(
                    {
                        "task_understanding": "Create feature.txt for the real GitHub label flow test.",
                        "scope": {"in_scope": ["feature.txt"], "out_of_scope": []},
                        "target_files": ["feature.txt"],
                        "implementation_plan": ["Create feature.txt"],
                        "test_plan": ["test -f feature.txt"],
                        "risks": [],
                        "open_questions": [],
                    }
                ),
                encoding="utf-8",
            )
        elif output_path.name == "02_review_design.output.json":
            output_path.write_text(review_json("Design is sufficient for GitHub flow test"), encoding="utf-8")
        elif output_path.name == "03_dev_implement.final.md":
            (cwd / "feature.txt").write_text("real github flow\n", encoding="utf-8")
            output_path.write_text("Created feature.txt.", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"implemented"}\n', encoding="utf-8")
        elif output_path.name == "06_review_code.output.json":
            output_path.write_text(review_json("Real GitHub flow implementation reviewed"), encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected Codex output: {output_path}")
        return CodexResult(
            command_result=command_result(["codex", "fake"], cwd=cwd),
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
        )


def _require_gh_auth() -> None:
    result = subprocess.run(["gh", "auth", "status"], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        pytest.skip(result.stderr.strip() or result.stdout.strip() or "gh auth status failed")


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip() or f"command failed: {command}")
    return result.stdout.strip()


def _current_branch(repo: Path) -> str:
    return _run(["git", "branch", "--show-current"], cwd=repo)


def _ensure_label(repo: str, name: str, color: str) -> None:
    result = subprocess.run(
        ["gh", "label", "create", name, "--repo", repo, "--color", color],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


def _create_issue(repo: str) -> int:
    output = _run(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            "CodexFlow E2E label flow",
            "--body",
            "Create feature.txt and ensure `test -f feature.txt` passes.",
        ]
    )
    return int(output.rstrip("/").split("/")[-1])


def _issue_labels(repo: str, issue_number: int) -> set[str]:
    output = _run(["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "labels"])
    payload = json.loads(output)
    return {label["name"] for label in payload["labels"]}
