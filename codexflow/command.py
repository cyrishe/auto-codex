from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    cwd: Path | None
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    ended_at: datetime
    timed_out: bool = False

    @property
    def duration_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CommandRunner:
    """Single execution boundary for external commands."""

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
        started_at = datetime.now(timezone.utc)
        command_tuple = tuple(str(part) for part in command)
        try:
            completed = subprocess.run(
                command_tuple,
                cwd=str(cwd) if cwd else None,
                env=dict(env) if env else None,
                timeout=timeout_seconds,
                text=True,
                input=input_text,
                capture_output=True,
                check=False,
            )
            ended_at = datetime.now(timezone.utc)
            result = CommandResult(
                command=command_tuple,
                cwd=cwd,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                started_at=started_at,
                ended_at=ended_at,
            )
        except subprocess.TimeoutExpired as exc:
            ended_at = datetime.now(timezone.utc)
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            result = CommandResult(
                command=command_tuple,
                cwd=cwd,
                exit_code=124,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                ended_at=ended_at,
                timed_out=True,
            )

        if stdout_path:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text(result.stdout, encoding="utf-8")
        if stderr_path:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text(result.stderr, encoding="utf-8")

        return result
