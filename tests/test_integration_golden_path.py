from __future__ import annotations

import json
from pathlib import Path

from codexflow.codex_runner import CodexResult
from codexflow.db import RunStore
from codexflow.gitops import GitOps
from codexflow.pipeline import Pipeline

from .helpers import command_result
from .integration_support import TrackingGitHub, init_toy_repo, review_json, toy_config, toy_issue


def test_phase1_toy_repo_golden_path(tmp_path: Path) -> None:
    repo = init_toy_repo(tmp_path / "toy-repo")
    config = toy_config(tmp_path, repo)
    github = TrackingGitHub(issue=toy_issue())
    codex = GoldenPathCodex()

    result = Pipeline(config=config, github=github, codex=codex).run_next()

    assert result is not None
    assert result.status == "DONE"
    assert result.commit_sha is not None
    assert github.events == [
        "get_ready_issue",
        "get_issue:7",
        "claim:7",
        "mark_review:7",
    ]
    assert github.labels == {"codex:review"}

    store_run = RunStore(config.storage.db_path).get_run(result.run_id)
    assert store_run is not None
    assert store_run["status"] == "DONE"
    assert store_run["current_phase"] == "done"
    assert store_run["issue_number"] == 7
    assert store_run["work_branch"] == "codex/issue-7"
    assert store_run["base_branch"] == "main"
    assert store_run["final_sha"] == result.commit_sha

    meta = json.loads((result.run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["run_id"] == result.run_id
    assert meta["issue_number"] == 7
    assert meta["status"] == "DONE"
    assert meta["github_repo"] == "owner/toy-repo"
    assert meta["base_branch"] == "main"
    assert meta["work_branch"] == "codex/issue-7"
    assert meta["base_sha"] == GitOps(repo).current_sha("main")
    assert meta["final_sha"] == result.commit_sha

    expected_artifacts = [
        "meta.json",
        "00_issue.md",
        "00_context.md",
        "01_dev_design.prompt.md",
        "01_dev_design.output.json",
        "02_review_design.prompt.md",
        "02_review_design.output.json",
        "03_dev_implement.prompt.md",
        "03_dev_implement.final.md",
        "03_dev_implement.ndjson",
        "04_git_diff.patch",
        "05_test.log",
        "06_review_code.prompt.md",
        "06_review_code.output.json",
        "10_final_commit_summary.json",
        "11_commit_message.txt",
    ]
    for relative in expected_artifacts:
        assert (result.run_dir / relative).is_file(), relative

    diff = (result.run_dir / "04_git_diff.patch").read_text(encoding="utf-8")
    assert "def multiply(a: int, b: int) -> int:" in diff
    assert "test_multiply" in diff

    test_log = (result.run_dir / "05_test.log").read_text(encoding="utf-8")
    assert "status: pass" in test_log

    commit_message = (result.run_dir / "11_commit_message.txt").read_text(encoding="utf-8")
    assert "Issue: #7" in commit_message
    assert f"Codex-Run: {result.run_id}" in commit_message
    assert "Test-Result: pass" in commit_message
    assert "Reviewed toycalc implementation" in commit_message

    worktree = Path(store_run["worktree_path"])
    committed_file = worktree / "src" / "toycalc.py"
    assert "def multiply" in committed_file.read_text(encoding="utf-8")
    assert GitOps(worktree).current_sha("HEAD") == result.commit_sha
    assert GitOps(repo).current_sha("main") == meta["base_sha"]

class GoldenPathCodex:
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
                        "task_understanding": "Add multiply(a, b) to toycalc without changing add(a, b).",
                        "scope": {
                            "in_scope": ["src/toycalc.py", "tests/test_toycalc.py"],
                            "out_of_scope": ["packaging changes"],
                        },
                        "target_files": ["src/toycalc.py", "tests/test_toycalc.py"],
                        "implementation_plan": [
                            "Add multiply next to add.",
                            "Add pytest coverage for multiply.",
                        ],
                        "test_plan": ["PYTHONPATH=src python -m pytest -q"],
                        "risks": [],
                        "open_questions": [],
                    }
                ),
                encoding="utf-8",
            )
        elif output_path.name == "02_review_design.output.json":
            output_path.write_text(review_json("Design is scoped and testable"), encoding="utf-8")
        elif output_path.name == "03_dev_implement.final.md":
            (cwd / "src" / "toycalc.py").write_text(
                """def add(a: int, b: int) -> int:
    return a + b


def multiply(a: int, b: int) -> int:
    return a * b
""",
                encoding="utf-8",
            )
            (cwd / "tests" / "test_toycalc.py").write_text(
                """from toycalc import add, multiply


def test_add() -> None:
    assert add(2, 3) == 5


def test_multiply() -> None:
    assert multiply(3, 4) == 12
""",
                encoding="utf-8",
            )
            output_path.write_text("Implemented multiply and added pytest coverage.", encoding="utf-8")
            if json_stream_path:
                json_stream_path.write_text('{"event":"done"}\n', encoding="utf-8")
        elif output_path.name == "06_review_code.output.json":
            output_path.write_text(review_json("Reviewed toycalc implementation"), encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected codex output: {output_path}")
        return CodexResult(
            command_result=command_result(["codex", "fake"], cwd=cwd),
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
        )
