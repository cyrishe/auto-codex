from pathlib import Path

from codexflow.artifacts import ArtifactStore, generate_run_id
from codexflow.db import RunStore


def test_run_store_initializes_and_records_run(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "codexflow.db")
    store.initialize()

    store.create_run(
        run_id="run-1",
        target_repo_path=tmp_path,
        issue_number=123,
        issue_title="Add feature",
        base_branch="main",
    )
    store.update_run_status("run-1", status="CONTEXT_COLLECTED", current_phase="context")

    run = store.get_run("run-1")
    assert run is not None
    assert run["status"] == "CONTEXT_COLLECTED"
    assert run["current_phase"] == "context"


def test_artifact_store_creates_run_dir_and_json(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "runs")
    run_id = generate_run_id(123)

    run_dir = artifacts.create_run_dir(run_id, meta={"run_id": run_id, "status": "PENDING"})
    issue_path = artifacts.write_text(run_id, "00_issue.md", "# Issue")

    assert run_dir.exists()
    assert (run_dir / "meta.json").exists()
    assert issue_path.read_text(encoding="utf-8") == "# Issue"
    assert len(ArtifactStore.sha256_file(issue_path)) == 64
