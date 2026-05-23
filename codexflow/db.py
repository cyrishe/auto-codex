from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  target_repo_path TEXT NOT NULL,
  github_repo TEXT,
  issue_number INTEGER,
  issue_title TEXT,
  base_branch TEXT,
  work_branch TEXT,
  worktree_path TEXT,
  base_sha TEXT,
  final_sha TEXT,
  status TEXT NOT NULL,
  current_phase TEXT,
  fix_round INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  agent_role TEXT,
  command TEXT,
  prompt_path TEXT,
  output_path TEXT,
  stdout_path TEXT,
  stderr_path TEXT,
  exit_code INTEGER,
  started_at TEXT,
  ended_at TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  verdict TEXT NOT NULL,
  score REAL,
  risk_level TEXT,
  summary TEXT,
  details_path TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS commits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  commit_sha TEXT,
  commit_message_path TEXT,
  diff_path TEXT,
  test_summary TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_run(
        self,
        *,
        run_id: str,
        target_repo_path: Path,
        status: str = "PENDING",
        github_repo: str | None = None,
        issue_number: int | None = None,
        issue_title: str | None = None,
        base_branch: str | None = None,
        work_branch: str | None = None,
        worktree_path: Path | None = None,
        base_sha: str | None = None,
        current_phase: str | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                  id, target_repo_path, github_repo, issue_number, issue_title,
                  base_branch, work_branch, worktree_path, base_sha, status,
                  current_phase, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(target_repo_path),
                    github_repo,
                    issue_number,
                    issue_title,
                    base_branch,
                    work_branch,
                    str(worktree_path) if worktree_path else None,
                    base_sha,
                    status,
                    current_phase,
                    now,
                    now,
                ),
            )

    def update_run_status(
        self,
        run_id: str,
        *,
        status: str,
        current_phase: str | None = None,
        final_sha: str | None = None,
        fix_round: int | None = None,
    ) -> None:
        assignments = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, utc_now()]
        if current_phase is not None:
            assignments.append("current_phase = ?")
            values.append(current_phase)
        if final_sha is not None:
            assignments.append("final_sha = ?")
            values.append(final_sha)
        if fix_round is not None:
            assignments.append("fix_round = ?")
            values.append(fix_round)
        values.append(run_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE runs SET {', '.join(assignments)} WHERE id = ?",
                values,
            )

    def record_artifact(
        self,
        *,
        run_id: str,
        kind: str,
        path: Path,
        sha256: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (run_id, kind, path, sha256, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, kind, str(path), sha256, utc_now()),
            )

    def record_step(
        self,
        *,
        run_id: str,
        phase: str,
        agent_role: str | None = None,
        command: str | None = None,
        prompt_path: Path | None = None,
        output_path: Path | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        exit_code: int | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO steps (
                  run_id, phase, agent_role, command, prompt_path, output_path,
                  stdout_path, stderr_path, exit_code, started_at, ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    phase,
                    agent_role,
                    command,
                    str(prompt_path) if prompt_path else None,
                    str(output_path) if output_path else None,
                    str(stdout_path) if stdout_path else None,
                    str(stderr_path) if stderr_path else None,
                    exit_code,
                    started_at,
                    ended_at,
                ),
            )

    def record_review(
        self,
        *,
        run_id: str,
        phase: str,
        verdict: str,
        score: float | None = None,
        risk_level: str | None = None,
        summary: str | None = None,
        details_path: Path | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews (
                  run_id, phase, verdict, score, risk_level, summary,
                  details_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    phase,
                    verdict,
                    score,
                    risk_level,
                    summary,
                    str(details_path) if details_path else None,
                    utc_now(),
                ),
            )

    def record_commit(
        self,
        *,
        run_id: str,
        commit_sha: str,
        commit_message_path: Path,
        diff_path: Path,
        test_summary: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO commits (
                  run_id, commit_sha, commit_message_path, diff_path,
                  test_summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    commit_sha,
                    str(commit_message_path),
                    str(diff_path),
                    test_summary,
                    utc_now(),
                ),
            )

    def list_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, issue_number, issue_title, status, current_phase,
                       created_at, updated_at
                FROM runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
