from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from codexflow.codex_runner import CodexResult
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
from codexflow.gitops import GitOps
from codexflow.models import GitHubIssue
from codexflow.pipeline import Pipeline, PipelineBlocked

from .helpers import command_result
from .test_gitops import init_repo


class FakeGitHub:
    def __init__(self, issue: GitHubIssue) -> None:
        self.issue = issue
        self.ready_calls = 0
        self.claimed: list[int] = []
        self.reviewed: list[int] = []
        self.blocked: list[int] = []
        self.prs: list[dict[str, str]] = []
        self.comments: list[tuple[int, str]] = []

    def get_ready_issue(self) -> GitHubIssue | None:
        self.ready_calls += 1
        if self.ready_calls > 1:
            return None
        return self.issue

    def get_issue(self, number: int, *, include_comments: bool = False) -> GitHubIssue:
        assert number == self.issue.number
        return self.issue

    def claim_issue(self, number: int) -> None:
        self.claimed.append(number)

    def mark_review(self, number: int) -> None:
        self.reviewed.append(number)

    def mark_blocked(self, number: int) -> None:
        self.blocked.append(number)

    def create_pr(self, *, base: str, head: str, title: str, body_file: str):
        self.prs.append({"base": base, "head": head, "title": title, "body_file": body_file})

        class PR:
            url = "https://github.com/owner/repo/pull/1"
            number = 1

        return PR()

    def comment_issue(self, number: int, *, body_file: str) -> None:
        self.comments.append((number, body_file))


class FakeCodex:
    def __init__(self, *, code_review_verdict: str = "pass") -> None:
        self.code_review_verdict = code_review_verdict
        self.calls: list[Path] = []
        self.timeouts: list[int | None] = []

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
        self.calls.append(output_path)
        self.timeouts.append(timeout_seconds)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.name == "01_dev_design.output.json":
            output_path.write_text(
                """{
  "task_understanding": "Add a feature file",
  "scope": {"in_scope": ["feature file"], "out_of_scope": []},
  "target_files": ["feature.txt"],
  "implementation_plan": ["Create feature.txt"],
  "test_plan": ["test -f feature.txt"],
  "risks": [],
  "open_questions": []
}
""",
                encoding="utf-8",
            )
        elif output_path.name == "02_review_design.output.json":
            output_path.write_text(_review_json("pass"), encoding="utf-8")
        elif output_path.name == "03_dev_implement.final.md":
            (cwd / "feature.txt").write_text("implemented\n", encoding="utf-8")
            output_path.write_text("Created feature.txt", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"done"}\n', encoding="utf-8")
        elif output_path.name == "06_review_code.output.json":
            output_path.write_text(_review_json(self.code_review_verdict), encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected codex output path: {output_path}")
        return CodexResult(
            command_result=command_result(["codex", "fake"], cwd=cwd),
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
        )


class FixingCodex:
    def __init__(self, *, code_review_verdicts: list[str] | None = None) -> None:
        self.code_review_verdicts = list(code_review_verdicts or ["pass"])
        self.calls: list[Path] = []

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
        self.calls.append(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.name == "01_dev_design.output.json":
            output_path.write_text(
                """{
  "task_understanding": "Create a feature file",
  "scope": {"in_scope": ["feature file"], "out_of_scope": []},
  "target_files": ["feature.txt"],
  "implementation_plan": ["Create feature.txt"],
  "test_plan": ["configured test command"],
  "risks": [],
  "open_questions": []
}
""",
                encoding="utf-8",
            )
        elif output_path.name == "02_review_design.output.json":
            output_path.write_text(_review_json("pass"), encoding="utf-8")
        elif output_path.name == "03_dev_implement.final.md":
            (cwd / "feature.txt").write_text("broken\n", encoding="utf-8")
            output_path.write_text("Created feature.txt with initial content", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"implemented"}\n', encoding="utf-8")
        elif output_path.name.startswith("03_dev_fix"):
            (cwd / "feature.txt").write_text("fixed\n", encoding="utf-8")
            output_path.write_text("Fixed feature.txt", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"fixed"}\n', encoding="utf-8")
        elif output_path.name.startswith("06_review_code"):
            verdict = self.code_review_verdicts.pop(0) if self.code_review_verdicts else "pass"
            output_path.write_text(_review_json(verdict), encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected codex output path: {output_path}")
        return CodexResult(
            command_result=command_result(["codex", "fake"], cwd=cwd),
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
        )


class DesignFixingCodex:
    def __init__(self, *, design_review_verdicts: list[str]) -> None:
        self.design_review_verdicts = list(design_review_verdicts)
        self.calls: list[Path] = []
        self.prompts: dict[str, str] = {}

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
        self.calls.append(output_path)
        self.prompts[output_path.name] = prompt_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.name.startswith("01_dev_design"):
            output_path.write_text(
                json.dumps(
                    {
                        "task_understanding": f"Design from {output_path.name}",
                        "scope": {"in_scope": ["feature file"], "out_of_scope": []},
                        "target_files": ["feature.txt"],
                        "implementation_plan": ["Create feature.txt"],
                        "test_plan": ["test -f feature.txt"],
                        "risks": [],
                        "open_questions": [],
                    }
                ),
                encoding="utf-8",
            )
        elif output_path.name.startswith("02_review_design"):
            verdict = self.design_review_verdicts.pop(0) if self.design_review_verdicts else "pass"
            output_path.write_text(_review_json(verdict), encoding="utf-8")
        elif output_path.name == "03_dev_implement.final.md":
            (cwd / "feature.txt").write_text("implemented after design fix\n", encoding="utf-8")
            output_path.write_text("Created feature.txt", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"done"}\n', encoding="utf-8")
        elif output_path.name == "06_review_code.output.json":
            output_path.write_text(_review_json("pass"), encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected codex output path: {output_path}")
        return CodexResult(
            command_result=command_result(["codex", "fake"], cwd=cwd),
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
        )


class SecretArtifactCodex(FakeCodex):
    def run(self, **kwargs) -> CodexResult:
        result = super().run(**kwargs)
        output_path = kwargs["output_path"]
        cwd = kwargs["cwd"]
        if output_path.name == "03_dev_implement.final.md":
            (cwd / "feature.txt").write_text("OPENAI_API_KEY=sk-testabcdefghijklmnopqrstuvwxyz\n", encoding="utf-8")
            output_path.write_text("Used token ghp_abcdefghijklmnopqrstuvwxyz123456", encoding="utf-8")
        elif output_path.name == "06_review_code.output.json":
            output_path.write_text(
                json.dumps(
                    {
                        "verdict": "pass",
                        "score": 9,
                        "risk_level": "low",
                        "summary": "token ghp_abcdefghijklmnopqrstuvwxyz123456",
                        "blocking_issues": [],
                        "non_blocking_suggestions": [],
                    }
                ),
                encoding="utf-8",
            )
        return result


def test_pipeline_run_issue_happy_path(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))
    codex = FakeCodex()

    result = Pipeline(config=config, github=github, codex=codex).run_issue(123)

    assert result.status == "DONE"
    assert result.commit_sha is not None
    assert codex.timeouts == [900, 600, 1800, 600]
    assert github.claimed == [123]
    assert github.reviewed == [123]
    run = result.run_dir
    assert (run / "00_issue.md").exists()
    assert (run / "00_context.md").exists()
    assert (run / "04_git_diff.patch").read_text(encoding="utf-8").find("feature.txt") >= 0
    assert (run / "05_test.log").read_text(encoding="utf-8").find("status: pass") >= 0
    assert (run / "10_final_commit_summary.json").exists()
    assert (run / "11_commit_message.txt").exists()
    assert (run / "14_run_summary.md").exists()
    report = (run / "15_user_report.md").read_text(encoding="utf-8")
    assert "Recommendation" in report
    assert "建议人工审查后接纳" in report


def test_pipeline_blocks_on_code_review_needs_fix(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, max_fix_rounds=0)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    try:
        Pipeline(config=config, github=github, codex=FakeCodex(code_review_verdict="needs_fix")).run_issue(123)
    except PipelineBlocked as exc:
        assert "Code review verdict" in str(exc)
    else:
        raise AssertionError("Expected pipeline to block")

    assert github.blocked == [123]


def test_pipeline_comments_when_blocked_if_enabled(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, max_fix_rounds=0, comment_on_issue=True)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    with pytest.raises(PipelineBlocked):
        Pipeline(config=config, github=github, codex=FakeCodex(code_review_verdict="needs_fix")).run_issue(123)

    assert github.blocked == [123]
    assert len(github.comments) == 1
    assert github.comments[0][0] == 123
    assert Path(github.comments[0][1]).name == "13_blocked_comment.md"


def test_pipeline_blocks_on_test_failure_before_code_review(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, test_command="exit 7", max_fix_rounds=0)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))
    codex = FakeCodex()

    try:
        Pipeline(config=config, github=github, codex=codex).run_issue(123)
    except PipelineBlocked as exc:
        assert "Tests did not pass" in str(exc)
    else:
        raise AssertionError("Expected pipeline to block")

    assert github.blocked == [123]
    assert not any(path.name == "06_review_code.output.json" for path in codex.calls)


def test_pipeline_fixes_test_failure(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, test_command="grep fixed feature.txt", max_fix_rounds=1)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate fixed feature.txt"))

    result = Pipeline(config=config, github=github, codex=FixingCodex()).run_issue(123)

    assert result.status == "DONE"
    assert github.reviewed == [123]
    assert (result.run_dir / "03_dev_fix.round2.prompt.md").exists()
    assert (result.run_dir / "03_dev_fix.round2.final.md").exists()
    assert (result.run_dir / "04_git_diff.round2.patch").exists()
    assert (result.run_dir / "05_test.round2.log").read_text(encoding="utf-8").find("status: pass") >= 0
    fix_prompt = (result.run_dir / "03_dev_fix.round2.prompt.md").read_text(encoding="utf-8")
    assert "Tests did not pass" in fix_prompt
    assert "broken" in fix_prompt
    assert "status: fail" in fix_prompt
    assert _review_phases(config.storage.db_path) == ["design_review", "code_review", "code_review.round2"]


def test_pipeline_fixes_code_review_needs_fix(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, test_command="test -f feature.txt", max_fix_rounds=1)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    result = Pipeline(
        config=config,
        github=github,
        codex=FixingCodex(code_review_verdicts=["needs_fix", "pass"]),
    ).run_issue(123)

    assert result.status == "DONE"
    assert (result.run_dir / "03_dev_fix.round2.prompt.md").exists()
    assert (result.run_dir / "06_review_code.round2.output.json").exists()
    fix_prompt = (result.run_dir / "03_dev_fix.round2.prompt.md").read_text(encoding="utf-8")
    assert "Needs fix" in fix_prompt
    assert "Fix it" in fix_prompt
    assert "broken" in fix_prompt
    assert "status: pass" in fix_prompt
    assert _review_phases(config.storage.db_path) == ["design_review", "code_review", "code_review.round2"]


def test_pipeline_fixes_design_review_needs_fix(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, max_design_rounds=1)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))
    codex = DesignFixingCodex(design_review_verdicts=["needs_fix", "pass"])

    result = Pipeline(config=config, github=github, codex=codex).run_issue(123)

    assert result.status == "DONE"
    assert (result.run_dir / "01_dev_design.output.json").exists()
    assert (result.run_dir / "01_dev_design.round2.output.json").exists()
    assert (result.run_dir / "02_review_design.output.json").exists()
    assert (result.run_dir / "02_review_design.round2.output.json").exists()
    fix_prompt = codex.prompts["01_dev_design.round2.output.json"]
    assert "PREVIOUS_DESIGN_JSON" not in fix_prompt
    assert "Design from 01_dev_design.output.json" in fix_prompt
    assert "Needs fix" in fix_prompt
    assert "Fix it" in fix_prompt
    assert _review_phases(config.storage.db_path) == ["design_review", "design_review.round2", "code_review"]


def test_pipeline_blocks_after_design_fix_round_limit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, max_design_rounds=0)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    with pytest.raises(PipelineBlocked, match="Design review verdict after 0 design fix rounds"):
        Pipeline(
            config=config,
            github=github,
            codex=DesignFixingCodex(design_review_verdicts=["needs_fix"]),
        ).run_issue(123)

    assert github.blocked == [123]


def test_pipeline_respects_auto_commit_false(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, auto_commit=False)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    result = Pipeline(config=config, github=github, codex=FakeCodex()).run_issue(123)

    worktree = config.storage.worktree_dir / result.run_id
    assert result.status == "COMMIT_READY"
    assert result.commit_sha is None
    assert github.reviewed == [123]
    assert (worktree / "feature.txt").exists()
    assert GitOps(worktree).current_sha("HEAD") == GitOps(repo).current_sha("main")


def test_pipeline_publish_dry_run_writes_plan_without_external_actions(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo, auto_push=True, create_pr=True, comment_on_issue=True, dry_run=True)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    result = Pipeline(config=config, github=github, codex=FakeCodex()).run_issue(123)

    dry_run = json.loads((result.run_dir / "12_publish_dry_run.json").read_text(encoding="utf-8"))
    assert dry_run["auto_push"] is True
    assert dry_run["create_pr"] is True
    assert dry_run["comment_on_issue"] is True
    assert dry_run["dry_run"] is True
    assert (result.run_dir / "12_pr_body.md").exists()
    assert github.prs == []
    assert github.comments == []


def test_pipeline_redacts_sensitive_artifacts(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(
        tmp_path,
        repo,
        test_command="printf 'token=ghp_abcdefghijklmnopqrstuvwxyz123456\\n'",
        auto_commit=False,
    )
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="api_key=sk-testabcdefghijklmnopqrstuvwxyz"))

    result = Pipeline(config=config, github=github, codex=SecretArtifactCodex()).run_issue(123)

    for relative in ["00_issue.md", "03_dev_implement.final.md", "04_git_diff.patch", "05_test.log", "11_commit_message.txt"]:
        content = (result.run_dir / relative).read_text(encoding="utf-8")
        assert "ghp_" not in content
        assert "sk-test" not in content
    assert "[REDACTED]" in (result.run_dir / "04_git_diff.patch").read_text(encoding="utf-8")


def test_pipeline_push_create_pr_and_comment_with_local_remote(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    runner = CommandRunner()
    assert runner.run(["git", "init", "--bare", str(remote)]).ok
    assert runner.run(["git", "remote", "add", "origin", str(remote)], cwd=repo).ok
    config = _config(tmp_path, repo, auto_push=True, create_pr=True, comment_on_issue=True)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    result = Pipeline(config=config, github=github, codex=FakeCodex()).run_issue(123)

    assert runner.run(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/codex/issue-123"]).ok
    assert github.prs == [
        {
            "base": "main",
            "head": "codex/issue-123",
            "title": "Address issue #123: Add feature",
            "body_file": str(result.run_dir / "12_pr_body.md"),
        }
    ]
    assert github.comments == [(123, str(result.run_dir / "13_issue_comment.md"))]
    assert "pull/1" in (result.run_dir / "13_issue_comment.md").read_text(encoding="utf-8")


def test_pipeline_run_next_uses_ready_issue(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    result = Pipeline(config=config, github=github, codex=FakeCodex()).run_next()

    assert result is not None
    assert result.status == "DONE"
    assert github.ready_calls == 1


def test_pipeline_run_all_stops_when_queue_empty(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    config = _config(tmp_path, repo)
    github = FakeGitHub(GitHubIssue(number=123, title="Add feature", body="## Goal\nCreate feature.txt"))

    results = Pipeline(config=config, github=github, codex=FakeCodex()).run_all(limit=3)

    assert len(results) == 1
    assert github.ready_calls == 2


def _config(
    tmp_path: Path,
    repo: Path,
    *,
    test_command: str | None = "test -f feature.txt",
    test_required: bool = True,
    fail_on_failure: bool = True,
    allow_skipped: bool = False,
    auto_commit: bool = True,
    max_fix_rounds: int = 2,
    max_design_rounds: int = 1,
    auto_push: bool = False,
    create_pr: bool = False,
    comment_on_issue: bool = False,
    dry_run: bool = False,
) -> CodexFlowConfig:
    return CodexFlowConfig(
        target=TargetConfig(path=repo, github_repo="owner/repo", base_branch="main"),
        storage=StorageConfig(
            runs_dir=tmp_path / "runs",
            db_path=tmp_path / "codexflow.db",
            worktree_dir=tmp_path / "worktrees",
        ),
        github=GitHubConfig(enabled=True),
        worktree=WorktreeConfig(enabled=True),
        codex=CodexConfig(max_fix_rounds=max_fix_rounds, max_design_rounds=max_design_rounds),
        tests=CodexTestConfig(
            command=test_command,
            timeout_seconds=30,
            required=test_required,
            fail_on_failure=fail_on_failure,
            allow_skipped=allow_skipped,
        ),
        commit=CommitConfig(
            auto_commit=auto_commit,
            auto_push=auto_push,
            create_pr=create_pr,
            comment_on_issue=comment_on_issue,
            dry_run=dry_run,
        ),
    )


def _review_json(verdict: str) -> str:
    blocking = []
    if verdict != "pass":
        blocking = [{"issue": "Needs fix", "reason": "Test review", "suggested_fix": "Fix it"}]
    return json.dumps(
        {
            "verdict": verdict,
            "score": 9,
            "risk_level": "low",
            "summary": "Reviewed",
            "blocking_issues": blocking,
            "non_blocking_suggestions": [],
        }
    )


def _review_phases(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT phase FROM reviews ORDER BY id").fetchall()
    return [row[0] for row in rows]
