from pathlib import Path

from codexflow.test_runner import TestRunner


def test_test_runner_records_pass(tmp_path: Path) -> None:
    result = TestRunner().run(
        cwd=tmp_path,
        command="printf ok",
        log_path=tmp_path / "test.log",
        timeout_seconds=10,
    )

    assert result.status == "pass"
    assert result.exit_code == 0
    assert "ok" in result.log_path.read_text(encoding="utf-8")


def test_test_runner_records_fail(tmp_path: Path) -> None:
    result = TestRunner().run(
        cwd=tmp_path,
        command="exit 3",
        log_path=tmp_path / "test.log",
        timeout_seconds=10,
    )

    assert result.status == "fail"
    assert result.exit_code == 3


def test_test_runner_skips_missing_command(tmp_path: Path) -> None:
    result = TestRunner().run(
        cwd=tmp_path,
        command=None,
        log_path=tmp_path / "test.log",
        timeout_seconds=10,
    )

    assert result.status == "skipped"
    assert result.exit_code is None
