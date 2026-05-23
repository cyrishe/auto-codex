import json

import pytest

from codexflow.review import ReviewInterpretationError, ReviewInterpreter


def review_payload(**overrides):
    payload = {
        "verdict": "pass",
        "score": 9,
        "risk_level": "low",
        "summary": "Looks good",
        "blocking_issues": [],
        "non_blocking_suggestions": [],
    }
    payload.update(overrides)
    return payload


def test_review_interpreter_accepts_pass() -> None:
    decision = ReviewInterpreter().interpret_text(json.dumps(review_payload()))

    assert decision.can_continue
    assert not decision.needs_fix
    assert not decision.blocked


def test_review_interpreter_accepts_needs_fix() -> None:
    decision = ReviewInterpreter().interpret_text(json.dumps(review_payload(verdict="needs_fix")))

    assert decision.needs_fix


def test_review_interpreter_rejects_invalid_json() -> None:
    with pytest.raises(ReviewInterpretationError):
        ReviewInterpreter().interpret_text("{not-json")


def test_review_interpreter_rejects_pass_with_blocking_issues() -> None:
    payload = review_payload(
        blocking_issues=[
            {
                "issue": "Bug",
                "reason": "Breaks behavior",
                "suggested_fix": "Fix it",
            }
        ]
    )

    with pytest.raises(ReviewInterpretationError, match="blocking_issues"):
        ReviewInterpreter().interpret_text(json.dumps(payload))
