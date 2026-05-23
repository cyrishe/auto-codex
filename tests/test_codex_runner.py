from pathlib import Path

from codexflow.codex_runner import CodexRunner

from .helpers import FakeRunner, command_result


def test_codex_runner_builds_structured_command(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Do work", encoding="utf-8")
    output = tmp_path / "out.json"
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    runner = FakeRunner([command_result(["codex"], stdout="{}", stderr="log")])

    result = CodexRunner(runner=runner).run(
        cwd=tmp_path,
        prompt_path=prompt,
        output_path=output,
        sandbox="read-only",
        schema_path=schema,
        timeout_seconds=10,
    )

    assert result.ok
    assert result.stdout_log_path is not None
    assert result.stderr_log_path is not None
    assert result.stdout_log_path.read_text(encoding="utf-8") == "{}"
    assert result.stderr_log_path.read_text(encoding="utf-8") == "log"
    assert runner.calls[0] == (
        "codex",
        "exec",
        "--cd",
        str(tmp_path),
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output),
        "--output-schema",
        str(schema),
        "-",
    )


def test_codex_runner_writes_json_stream_stdout(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Implement", encoding="utf-8")
    stream = tmp_path / "stream.ndjson"
    runner = FakeRunner([command_result(["codex"], stdout='{"event":"ok"}\n')])

    CodexRunner(runner=runner).run(
        cwd=tmp_path,
        prompt_path=prompt,
        output_path=tmp_path / "final.md",
        sandbox="workspace-write",
        json_stream_path=stream,
        extra_args=["--some-flag"],
    )

    assert stream.read_text(encoding="utf-8") == '{"event":"ok"}\n'
    assert "--json" in runner.calls[0]
    assert "--some-flag" in runner.calls[0]
