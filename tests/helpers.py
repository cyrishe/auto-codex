from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from codexflow.command import CommandResult


def command_result(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> CommandResult:
    now = datetime.now(timezone.utc)
    return CommandResult(
        command=tuple(command),
        cwd=cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=now,
        ended_at=now,
    )


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
    ) -> CommandResult:
        self.calls.append(tuple(str(part) for part in command))
        if not self.results:
            raise AssertionError(f"No fake result queued for command: {command}")
        result = self.results.pop(0)
        if stdout_path:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text(result.stdout, encoding="utf-8")
        if stderr_path:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text(result.stderr, encoding="utf-8")
        return result
