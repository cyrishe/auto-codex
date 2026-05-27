from __future__ import annotations

from pathlib import Path

from .artifacts import ArtifactStore
from .db import RunStore


def write_user_report(*, store: RunStore, artifacts: ArtifactStore, run_id: str) -> Path:
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")

    run_dir = artifacts.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "15_user_report.md"
    content = build_user_report(
        run=run,
        latest_review=store.latest_review(run_id),
        latest_commit=store.latest_commit(run_id),
        artifacts=store.list_artifacts(run_id),
        run_dir=run_dir,
    )
    path.write_text(content, encoding="utf-8")
    store.record_artifact(
        run_id=run_id,
        kind="user_report",
        path=path,
        sha256=ArtifactStore.sha256_file(path),
    )
    return path


def build_user_report(
    *,
    run: dict,
    latest_review: dict | None,
    latest_commit: dict | None,
    artifacts: list[dict],
    run_dir: Path,
) -> str:
    recommendation = _recommendation(run)
    issue = f"#{run['issue_number']}" if run.get("issue_number") is not None else "-"
    lines = [
        f"# CodexFlow User Report: {run['id']}",
        "",
        f"Recommendation: **{recommendation}**",
        "",
        "## Summary",
        "",
        f"- Issue: {issue} {run.get('issue_title') or ''}".rstrip(),
        f"- Status: `{run['status']}`",
        f"- Current phase: `{run.get('current_phase') or '-'}`",
        f"- Branch: `{run.get('work_branch') or '-'}`",
        f"- Commit: `{run.get('final_sha') or (latest_commit or {}).get('commit_sha') or 'not committed'}`",
        f"- Run directory: `{run_dir}`",
        "",
        "## Evaluation",
        "",
        f"- Test status: `{(latest_commit or {}).get('test_summary') or 'not recorded'}`",
        f"- Latest review: `{(latest_review or {}).get('verdict') or 'not recorded'}`",
        f"- Risk: `{(latest_review or {}).get('risk_level') or 'not recorded'}`",
        "",
        "## Review Summary",
        "",
        (latest_review or {}).get("summary") or "No review summary recorded.",
        "",
        "## Artifacts",
        "",
    ]
    if artifacts:
        for artifact in artifacts:
            lines.append(f"- `{artifact['kind']}`: `{artifact['path']}`")
    else:
        lines.append("- No artifacts recorded.")
    lines.extend(["", "## User Action", "", _user_action(run)])
    return "\n".join(lines) + "\n"


def _recommendation(run: dict) -> str:
    if run["status"] in {"DONE", "COMMIT_READY"}:
        return "建议人工审查后接纳"
    if run["status"] == "BLOCKED":
        return "需要用户反馈"
    return "继续观察"


def _user_action(run: dict) -> str:
    if run["status"] in {"DONE", "COMMIT_READY"}:
        return "Review the diff, tests, and commit. Run `codexflow approve <run_id>` if acceptable."
    if run["status"] == "BLOCKED":
        return "Review the blocked reason and provide feedback or update the issue."
    return "No immediate user action is required."
