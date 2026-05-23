from __future__ import annotations

import json
from pathlib import Path

import pytest

from codexflow.artifacts import ArtifactStore
from codexflow.codex_runner import CodexResult
from codexflow.config import CodexFlowConfig
from codexflow.db import RunStore
from codexflow.gitops import GitOps
from codexflow.pipeline import Pipeline

from .helpers import command_result
from .integration_support import TrackingGitHub, init_toy_repo, review_json, toy_config, toy_issue


RESUMABLE_STATUSES = [
    "CONTEXT_COLLECTED",
    "DEV_DESIGN_DONE",
    "DESIGN_REVIEWED",
    "IMPLEMENTED",
    "TESTED",
    "COMMIT_READY",
]


@pytest.mark.parametrize("status", RESUMABLE_STATUSES)
def test_pipeline_resume_from_supported_status(tmp_path: Path, status: str) -> None:
    seeded = seed_resume_run(tmp_path, status)
    github = TrackingGitHub(issue=toy_issue())
    github.labels = {"codex:working"}

    result = Pipeline(config=seeded.config, github=github, codex=ResumeCodex()).resume(seeded.run_id)

    assert result.status == "DONE"
    assert result.commit_sha is not None
    assert github.events == ["mark_review:7"]
    assert github.labels == {"codex:review"}
    run = RunStore(seeded.config.storage.db_path).get_run(seeded.run_id)
    assert run is not None
    assert run["status"] == "DONE"
    assert run["current_phase"] == "done"
    assert run["final_sha"] == result.commit_sha
    assert (seeded.run_dir / "11_commit_message.txt").exists()
    assert GitOps(seeded.worktree).current_sha("HEAD") == result.commit_sha

    if status in {"DEV_DESIGN_DONE", "DESIGN_REVIEWED", "IMPLEMENTED", "TESTED", "COMMIT_READY"}:
        assert (seeded.run_dir / "01_dev_design.output.json").read_text(encoding="utf-8") == DESIGN_JSON
    if status in {"TESTED", "COMMIT_READY"}:
        assert (seeded.run_dir / "05_test.log").read_text(encoding="utf-8") == TEST_LOG


def test_pipeline_resume_refuses_to_overwrite_existing_next_artifact(tmp_path: Path) -> None:
    seeded = seed_resume_run(tmp_path, "DEV_DESIGN_DONE")
    (seeded.run_dir / "02_review_design.output.json").write_text("partial\n", encoding="utf-8")
    github = TrackingGitHub(issue=toy_issue())
    github.labels = {"codex:working"}

    with pytest.raises(Exception, match="overwrite existing artifact"):
        Pipeline(config=seeded.config, github=github, codex=ResumeCodex()).resume(seeded.run_id)


class SeededRun:
    def __init__(self, *, config: CodexFlowConfig, run_id: str, run_dir: Path, worktree: Path) -> None:
        self.config = config
        self.run_id = run_id
        self.run_dir = run_dir
        self.worktree = worktree


class ResumeCodex:
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
            output_path.write_text(DESIGN_JSON, encoding="utf-8")
        elif output_path.name == "02_review_design.output.json":
            output_path.write_text(review_json("Design is resumable"), encoding="utf-8")
        elif output_path.name == "03_dev_implement.final.md":
            write_implementation(cwd)
            output_path.write_text("Implemented multiply after resume.", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"implemented"}\n', encoding="utf-8")
        elif output_path.name == "06_review_code.output.json":
            output_path.write_text(review_json("Reviewed after resume"), encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected Codex output during resume: {output_path}")
        return CodexResult(
            command_result=command_result(["codex", "fake"], cwd=cwd),
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
        )


def seed_resume_run(tmp_path: Path, status: str) -> SeededRun:
    repo = init_toy_repo(tmp_path / f"repo-{status.lower()}")
    config = toy_config(tmp_path, repo)
    issue = toy_issue()
    run_id = f"resume-{status.lower()}"
    branch = f"codex/{run_id}"
    target_git = GitOps(repo)
    base_sha = target_git.current_sha("main")
    worktree = config.storage.worktree_dir / run_id
    target_git.create_worktree(path=worktree, branch=branch, base_ref="main")

    store = RunStore(config.storage.db_path)
    store.initialize()
    artifacts = ArtifactStore(config.storage.runs_dir)
    artifacts.ensure_base_dirs()
    run_dir = artifacts.create_run_dir(
        run_id,
        meta={
            "run_id": run_id,
            "issue_number": issue.number,
            "issue_title": issue.title,
            "status": status,
            "target_path": str(config.target.path),
            "github_repo": config.target.github_repo,
            "base_branch": config.target.base_branch,
            "work_path": str(worktree),
            "work_branch": branch,
            "base_sha": base_sha,
        },
    )
    store.create_run(
        run_id=run_id,
        target_repo_path=config.target.path,
        github_repo=config.target.github_repo,
        issue_number=issue.number,
        issue_title=issue.title,
        base_branch=config.target.base_branch,
        work_branch=branch,
        worktree_path=worktree,
        base_sha=base_sha,
        status=status,
        current_phase=status.lower(),
        )

    artifacts.write_text(run_id, "00_issue.md", f"# Issue #{issue.number}: {issue.title}\n\n{issue.body}")
    artifacts.write_text(run_id, "00_context.md", "## File Tree Summary\n\nsrc/toycalc.py\ntests/test_toycalc.py\n")
    if status in {"DEV_DESIGN_DONE", "DESIGN_REVIEWED", "IMPLEMENTED", "TESTED", "COMMIT_READY"}:
        artifacts.write_text(run_id, "01_dev_design.output.json", DESIGN_JSON)
    if status in {"DESIGN_REVIEWED", "IMPLEMENTED", "TESTED", "COMMIT_READY"}:
        artifacts.write_text(run_id, "02_review_design.output.json", review_json("Seeded design review"))
    if status in {"IMPLEMENTED", "TESTED", "COMMIT_READY"}:
        write_implementation(worktree)
        artifacts.write_text(run_id, "03_dev_implement.final.md", "Seeded implementation summary.")
    if status in {"TESTED", "COMMIT_READY"}:
        GitOps(worktree).save_diff(run_dir / "04_git_diff.patch")
        artifacts.write_text(run_id, "05_test.log", TEST_LOG)
    if status == "COMMIT_READY":
        artifacts.write_text(run_id, "06_review_code.output.json", review_json("Seeded code review"))
    return SeededRun(config=config, run_id=run_id, run_dir=run_dir, worktree=worktree)


def write_implementation(repo: Path) -> None:
    (repo / "src" / "toycalc.py").write_text(
        """def add(a: int, b: int) -> int:
    return a + b


def multiply(a: int, b: int) -> int:
    return a * b
""",
        encoding="utf-8",
    )
    (repo / "tests" / "test_toycalc.py").write_text(
        """from toycalc import add, multiply


def test_add() -> None:
    assert add(2, 3) == 5


def test_multiply() -> None:
    assert multiply(3, 4) == 12
""",
        encoding="utf-8",
    )


DESIGN_JSON = json.dumps(
    {
        "task_understanding": "Add multiply(a, b) to toycalc.",
        "scope": {"in_scope": ["src/toycalc.py", "tests/test_toycalc.py"], "out_of_scope": []},
        "target_files": ["src/toycalc.py", "tests/test_toycalc.py"],
        "implementation_plan": ["Add multiply.", "Add tests."],
        "test_plan": ["PYTHONPATH=src python -m pytest -q"],
        "risks": [],
        "open_questions": [],
    }
)

TEST_LOG = """$ PYTHONPATH=src python -m pytest -q
exit_code: 0
status: pass
duration_seconds: 0.100

## stdout
2 passed

## stderr

"""

