from codexflow.commit_builder import CommitBuilder, CommitSummary


def test_commit_builder_includes_required_traceability() -> None:
    message = CommitBuilder().build_message(
        issue_number=123,
        issue_title="Add feature",
        run_id="run-123",
        design_review="pass",
        code_review="pass",
        test_command="pytest -q",
        test_result="pass",
        summary=CommitSummary(
            title="address issue #123 - Add feature",
            issue="#123",
            summary=["Implemented feature"],
            core_logic=["Changed service"],
            tests=["pytest -q"],
            risks=["low"],
        ),
    )

    assert "Issue: #123" in message
    assert "Codex-Run: run-123" in message
    assert "Design-Review: pass" in message
    assert "Code-Review: pass" in message
    assert "Test-Command: pytest -q" in message
    assert "- Implemented feature" in message
