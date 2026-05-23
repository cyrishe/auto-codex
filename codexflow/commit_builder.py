from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CommitSummary:
    title: str
    issue: str
    summary: list[str] = field(default_factory=list)
    core_logic: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


class CommitBuilder:
    def build_message(
        self,
        *,
        issue_number: int,
        issue_title: str,
        run_id: str,
        design_review: str,
        code_review: str,
        test_command: str | None,
        test_result: str,
        summary: CommitSummary,
    ) -> str:
        title = summary.title or f"address issue #{issue_number} - {issue_title}"
        lines = [
            f"feat: {title}",
            "",
            f"Issue: #{issue_number}",
            f"Codex-Run: {run_id}",
            f"Design-Review: {design_review}",
            f"Code-Review: {code_review}",
            f"Test-Command: {test_command or 'not configured'}",
            f"Test-Result: {test_result}",
            "",
            "Summary:",
            *_bullets(summary.summary),
            "",
            "Core Logic:",
            *_bullets(summary.core_logic),
            "",
            "Tests:",
            *_bullets(summary.tests),
            "",
            "Risks:",
            *_bullets(summary.risks),
            "",
        ]
        return "\n".join(lines)

    def write_message(self, path: Path, **kwargs) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.build_message(**kwargs), encoding="utf-8")
        return path


def _bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]
