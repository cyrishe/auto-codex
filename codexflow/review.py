from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


ReviewVerdict = Literal["pass", "needs_fix", "blocked"]
RiskLevel = Literal["low", "medium", "high"]


class BlockingIssue(BaseModel):
    issue: str
    reason: str
    suggested_fix: str


class NonBlockingSuggestion(BaseModel):
    comment: str
    file: str | None = None
    line_hint: str | None = None


class ReviewOutput(BaseModel):
    verdict: ReviewVerdict
    score: float
    risk_level: RiskLevel
    summary: str
    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
    non_blocking_suggestions: list[NonBlockingSuggestion] = Field(default_factory=list)


@dataclass(frozen=True)
class ReviewDecision:
    output: ReviewOutput

    @property
    def verdict(self) -> ReviewVerdict:
        return self.output.verdict

    @property
    def can_continue(self) -> bool:
        return self.output.verdict == "pass"

    @property
    def needs_fix(self) -> bool:
        return self.output.verdict == "needs_fix"

    @property
    def blocked(self) -> bool:
        return self.output.verdict == "blocked"


class ReviewInterpretationError(RuntimeError):
    pass


class ReviewInterpreter:
    def interpret_text(self, content: str) -> ReviewDecision:
        try:
            output = ReviewOutput.model_validate_json(content)
        except ValidationError as exc:
            raise ReviewInterpretationError(str(exc)) from exc
        return self._decision(output)

    def interpret_file(self, path: Path) -> ReviewDecision:
        return self.interpret_text(path.read_text(encoding="utf-8"))

    @staticmethod
    def _decision(output: ReviewOutput) -> ReviewDecision:
        if output.verdict == "pass" and output.blocking_issues:
            raise ReviewInterpretationError("pass verdict cannot include blocking_issues")
        return ReviewDecision(output=output)
