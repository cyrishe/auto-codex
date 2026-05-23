from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .command import CommandRunner


TestStatus = Literal["pass", "fail", "timeout", "skipped"]


@dataclass(frozen=True)
class TestResult:
    command: str | None
    status: TestStatus
    exit_code: int | None
    log_path: Path
    duration_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class TestRunner:
    __test__ = False

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def run(
        self,
        *,
        cwd: Path,
        command: str | None,
        log_path: Path,
        timeout_seconds: int,
    ) -> TestResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not command or not command.strip():
            log_path.write_text("Test command skipped: no command configured.\n", encoding="utf-8")
            return TestResult(command=command, status="skipped", exit_code=None, log_path=log_path)

        result = self.runner.run(
            ["bash", "-lc", command],
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
        status: TestStatus
        if result.timed_out:
            status = "timeout"
        elif result.ok:
            status = "pass"
        else:
            status = "fail"

        log = [
            f"$ {command}",
            f"exit_code: {result.exit_code}",
            f"status: {status}",
            f"duration_seconds: {result.duration_seconds:.3f}",
            "",
            "## stdout",
            result.stdout.rstrip(),
            "",
            "## stderr",
            result.stderr.rstrip(),
            "",
        ]
        log_path.write_text("\n".join(log), encoding="utf-8")
        return TestResult(
            command=command,
            status=status,
            exit_code=result.exit_code,
            log_path=log_path,
            duration_seconds=result.duration_seconds,
        )
