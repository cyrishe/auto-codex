from pathlib import Path

from typer.testing import CliRunner

from codexflow.cli import app
from codexflow.db import RunStore
from codexflow.pipeline import PipelineResult


runner = CliRunner()


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "CodexFlow" in result.output


def test_init_creates_config_storage_and_db(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"

    result = runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])

    assert result.exit_code == 0
    assert config.exists()
    assert (target / ".codexflow" / "runs").exists()
    assert (target / ".codexflow" / "worktrees").exists()
    assert (target / ".codexflow" / "locks").exists()
    assert (target / ".codexflow" / "codexflow.db").exists()


def test_init_refuses_missing_target(tmp_path: Path) -> None:
    config = tmp_path / ".codexflow.yaml"
    missing_target = tmp_path / "missing"

    result = runner.invoke(app, ["init", "--config", str(config), "--target", str(missing_target)])

    assert result.exit_code == 1
    assert not missing_target.exists()
    assert "Target path does not exist" in result.output


def test_resume_command_runs_pipeline_resume(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])
    calls = []

    class FakePipeline:
        def __init__(self, *, config) -> None:
            calls.append(config.target.path)

        def resume(self, run_id: str) -> PipelineResult:
            calls.append(run_id)
            return PipelineResult(run_id=run_id, status="DONE", run_dir=tmp_path / "runs" / run_id, commit_sha="abc123")

    monkeypatch.setattr("codexflow.cli.Pipeline", FakePipeline)

    result = runner.invoke(app, ["resume", "run-1", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [target.resolve(), "run-1"]
    assert "Resumed" in result.output
    assert "abc123" in result.output


def test_watch_command_processes_ready_issue_with_limit(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])

    class FakePipeline:
        def __init__(self, *, config) -> None:
            self.calls = 0

        def run_next(self):
            self.calls += 1
            return PipelineResult(run_id="run-1", status="DONE", run_dir=tmp_path / "runs" / "run-1")

    monkeypatch.setattr("codexflow.cli.Pipeline", FakePipeline)
    monkeypatch.setattr("codexflow.cli._sleep", lambda seconds: None)

    result = runner.invoke(app, ["watch", "--limit", "1", "--config", str(config)])

    assert result.exit_code == 0
    assert "Watching" in result.output
    assert "Done" in result.output


def test_watch_command_sleeps_on_empty_queue_and_stops_cleanly(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])
    sleeps = []

    class EmptyPipeline:
        def __init__(self, *, config) -> None:
            pass

        def run_next(self):
            return None

    def stop_after_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr("codexflow.cli.Pipeline", EmptyPipeline)
    monkeypatch.setattr("codexflow.cli._sleep", stop_after_sleep)

    result = runner.invoke(app, ["watch", "--interval", "1", "--config", str(config)])

    assert result.exit_code == 0
    assert sleeps == [1]
    assert "No ready issue found" in result.output
    assert "Stopped" in result.output


def test_unlock_stale_removes_dead_pid_lock(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])
    lock = target / ".codexflow" / "locks" / "stale.lock"
    lock.write_text("pid=999999999\n", encoding="utf-8")

    result = runner.invoke(app, ["unlock", "--stale", "--config", str(config)])

    assert result.exit_code == 0
    assert "Removed stale locks: 1" in result.output
    assert not lock.exists()


def test_pending_review_approve_and_reject_commands(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])
    store = RunStore(target / ".codexflow" / "codexflow.db")
    store.create_run(
        run_id="run-1",
        target_repo_path=target,
        issue_number=1,
        issue_title="Task",
        base_branch="main",
        work_branch="codex/issue-1",
        status="DONE",
        current_phase="done",
    )
    store.update_run_status("run-1", status="DONE", current_phase="done", final_sha="abc123")
    store.update_user_review("run-1", status="PENDING_USER_REVIEW")
    (target / ".codexflow" / "runs" / "run-1").mkdir(parents=True)

    pending = runner.invoke(app, ["pending-review", "--config", str(config)])
    assert pending.exit_code == 0
    assert "run-1" in pending.output

    approved = runner.invoke(app, ["approve", "run-1", "--config", str(config)])
    assert approved.exit_code == 0
    assert "Approved" in approved.output
    assert store.get_run("run-1")["user_review_status"] == "USER_APPROVED"

    store.update_user_review("run-1", status="PENDING_USER_REVIEW")
    feedback = tmp_path / "feedback.md"
    feedback.write_text("Needs clearer report.\n", encoding="utf-8")
    rejected = runner.invoke(
        app,
        ["reject", "run-1", "--feedback-file", str(feedback), "--config", str(config)],
    )
    assert rejected.exit_code == 0
    assert "Rejected" in rejected.output
    run = store.get_run("run-1")
    assert run["user_review_status"] == "USER_REJECTED"
    assert Path(run["user_feedback_path"]).name == "16_user_feedback.md"


def test_report_command_writes_user_report(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])
    store = RunStore(target / ".codexflow" / "codexflow.db")
    store.create_run(
        run_id="run-1",
        target_repo_path=target,
        issue_number=1,
        issue_title="Task",
        base_branch="main",
        work_branch="codex/issue-1",
        status="DONE",
        current_phase="done",
    )
    store.update_run_status("run-1", status="DONE", current_phase="done", final_sha="abc123")
    store.update_user_review("run-1", status="PENDING_USER_REVIEW")
    (target / ".codexflow" / "runs" / "run-1").mkdir(parents=True)

    result = runner.invoke(app, ["report", "run-1", "--config", str(config)])

    assert result.exit_code == 0
    assert "Report:" in result.output
    assert (target / ".codexflow" / "runs" / "run-1" / "15_user_report.md").exists()


def test_feedback_command_creates_followup_issue(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config = tmp_path / ".codexflow.yaml"
    runner.invoke(app, ["init", "--config", str(config), "--target", str(target)])
    store = RunStore(target / ".codexflow" / "codexflow.db")
    store.create_run(
        run_id="run-1",
        target_repo_path=target,
        issue_number=1,
        issue_title="Task",
        base_branch="main",
        work_branch="codex/issue-1",
        status="DONE",
        current_phase="done",
    )
    store.update_run_status("run-1", status="DONE", current_phase="done", final_sha="abc123")
    (target / ".codexflow" / "runs" / "run-1").mkdir(parents=True)
    feedback_file = tmp_path / "feedback.md"
    feedback_file.write_text("Please adjust the behavior.\n", encoding="utf-8")
    created = []

    class FakeIssueClient:
        def create_issue(self, *, title: str, body_file: str, labels: list[str] | None = None):
            created.append((title, Path(body_file).read_text(encoding="utf-8"), labels))

            class Issue:
                url = "https://example.test/issues/2"
                number = 2

            return Issue()

    monkeypatch.setattr("codexflow.cli.create_issue_client", lambda config: FakeIssueClient())

    result = runner.invoke(
        app,
        ["feedback", "run-1", "--feedback-file", str(feedback_file), "--config", str(config)],
    )

    assert result.exit_code == 0
    assert "Created feedback issue" in result.output
    assert created[0][0] == "Feedback for issue #1: Task"
    assert "Please adjust the behavior." in created[0][1]
    assert created[0][2] == []
