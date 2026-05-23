from pathlib import Path

from typer.testing import CliRunner

from codexflow.cli import app
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
