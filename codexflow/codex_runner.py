from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .command import CommandResult, CommandRunner
from .config import SandboxName


@dataclass(frozen=True)
class CodexResult:
    command_result: CommandResult
    prompt_path: Path
    output_path: Path
    schema_path: Path | None = None
    json_stream_path: Path | None = None
    stdout_log_path: Path | None = None
    stderr_log_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.command_result.ok

    @property
    def exit_code(self) -> int:
        return self.command_result.exit_code


class CodexRunner:
    """Subprocess wrapper for `codex exec`."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def run(
        self,
        *,
        cwd: Path,
        prompt_path: Path,
        output_path: Path,
        sandbox: SandboxName,
        schema_path: Path | None = None,
        json_stream_path: Path | None = None,
        extra_args: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> CodexResult:
        prompt = prompt_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if json_stream_path:
            json_stream_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_log_path = json_stream_path or output_path.with_name(f"{output_path.name}.stdout.log")
        stderr_log_path = output_path.with_name(f"{output_path.name}.stderr.log")

        command = [
            "codex",
            "exec",
            "--cd",
            str(cwd),
            "--sandbox",
            sandbox,
            "--output-last-message",
            str(output_path),
        ]
        if schema_path:
            command.extend(["--output-schema", str(schema_path)])
        if json_stream_path:
            command.append("--json")
        command.extend(extra_args or [])
        command.append("-")

        result = self.runner.run(
            command,
            cwd=cwd,
            input_text=prompt,
            stdout_path=stdout_log_path,
            stderr_path=stderr_log_path,
            timeout_seconds=timeout_seconds,
        )
        return CodexResult(
            command_result=result,
            prompt_path=prompt_path,
            output_path=output_path,
            schema_path=schema_path,
            json_stream_path=json_stream_path,
            stdout_log_path=None if json_stream_path else stdout_log_path,
            stderr_log_path=stderr_log_path,
        )
