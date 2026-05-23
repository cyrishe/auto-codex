import sys

from codexflow.command import CommandRunner


def test_command_runner_captures_success() -> None:
    result = CommandRunner().run([sys.executable, "-c", "print('ok')"])

    assert result.ok
    assert result.stdout.strip() == "ok"
    assert result.stderr == ""


def test_command_runner_captures_failure() -> None:
    result = CommandRunner().run([sys.executable, "-c", "import sys; sys.exit(7)"])

    assert not result.ok
    assert result.exit_code == 7


def test_command_runner_passes_stdin() -> None:
    result = CommandRunner().run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
        input_text="hello",
    )

    assert result.ok
    assert result.stdout.strip() == "HELLO"
