from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
from pathlib import Path

from .artifacts import ArtifactStore, generate_run_id
from .codex_runner import CodexRunner
from .commit_builder import CommitBuilder, CommitSummary
from .config import CodexFlowConfig
from .context import ContextCollector, render_issue
from .db import RunStore
from .github import GitHubClient
from .gitops import GitOps
from .locks import LockManager
from .prompts import PromptRenderer
from .review import ReviewDecision, ReviewInterpreter
from .secret_filter import SecretFilter
from .test_runner import TestResult, TestRunner


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    status: str
    run_dir: Path
    commit_sha: str | None = None


class PipelineBlocked(RuntimeError):
    pass


class Pipeline:
    def __init__(
        self,
        *,
        config: CodexFlowConfig,
        store: RunStore | None = None,
        artifacts: ArtifactStore | None = None,
        github: GitHubClient | None = None,
        codex: CodexRunner | None = None,
        prompts: PromptRenderer | None = None,
        tests: TestRunner | None = None,
        reviews: ReviewInterpreter | None = None,
        commits: CommitBuilder | None = None,
    ) -> None:
        self.config = config
        self.store = store or RunStore(config.storage.db_path)
        self.artifacts = artifacts or ArtifactStore(config.storage.runs_dir)
        self.github = github or GitHubClient(
            repo=config.target.github_repo,
            ready_label=config.github.ready_label,
            working_label=config.github.working_label,
            review_label=config.github.review_label,
            blocked_label=config.github.blocked_label,
        )
        self.codex = codex or CodexRunner()
        self.prompts = prompts or PromptRenderer()
        self.tests = tests or TestRunner()
        self.reviews = reviews or ReviewInterpreter()
        self.commits = commits or CommitBuilder()

    def run_next(self) -> PipelineResult | None:
        issue = self.github.get_ready_issue()
        if issue is None:
            return None
        return self.run_issue(issue.number)

    def run_all(self, *, limit: int) -> list[PipelineResult]:
        results: list[PipelineResult] = []
        for _ in range(limit):
            result = self.run_next()
            if result is None:
                break
            results.append(result)
        return results

    def resume(self, run_id: str) -> PipelineResult:
        self.store.initialize()
        run = self.store.get_run(run_id)
        if run is None:
            raise PipelineBlocked(f"Run not found: {run_id}")
        issue_number = run["issue_number"]
        lock_name = f"issue-{issue_number}" if issue_number is not None else f"run-{run_id}"
        lock_manager = LockManager(self.config.target.path / ".codexflow" / "locks")

        with lock_manager.acquire("global"), lock_manager.acquire(lock_name):
            run_dir = self.artifacts.run_dir(run_id)
            try:
                work_path = self._validate_resume_run(run, run_dir)
                return self._resume_validated_run(run, run_dir, work_path)
            except PipelineBlocked as exc:
                self.store.update_run_status(run_id, status="BLOCKED", current_phase="blocked")
                self._write_run_summary(
                    run_id,
                    status="BLOCKED",
                    issue_number=int(issue_number) if issue_number is not None else 0,
                    issue_title=run.get("issue_title") or "",
                    commit_sha=None,
                    test_status=None,
                    code_review_summary=str(exc),
                )
                if self.config.github.enabled and issue_number is not None:
                    self.github.mark_blocked(int(issue_number))
                    self._comment_blocked(run_id, int(issue_number), str(exc))
                self._update_meta(run_id, status="BLOCKED")
                raise
            except Exception:
                self.store.update_run_status(run_id, status="FAILED", current_phase="failed")
                if self.config.github.enabled and issue_number is not None:
                    self.github.mark_blocked(int(issue_number))
                self._update_meta(run_id, status="FAILED")
                raise

    def run_issue(self, issue_number: int) -> PipelineResult:
        self.store.initialize()
        self.artifacts.ensure_base_dirs()
        lock_manager = LockManager(self.config.target.path / ".codexflow" / "locks")

        with lock_manager.acquire("global"), lock_manager.acquire(f"issue-{issue_number}"):
            issue = self.github.get_issue(
                issue_number,
                include_comments=self.config.context.include_issue_comments,
            )
            run_id = generate_run_id(issue.number)
            branch = f"codex/issue-{issue.number}"
            target_git = GitOps(self.config.target.path)
            base_sha = target_git.current_sha(self.config.target.base_branch)
            work_path = self._prepare_worktree(target_git, run_id=run_id, branch=branch)

            run_dir = self.artifacts.create_run_dir(
                run_id,
                meta={
                    "run_id": run_id,
                    "issue_number": issue.number,
                    "issue_title": issue.title,
                    "status": "PENDING",
                    "target_path": str(self.config.target.path),
                    "github_repo": self.config.target.github_repo,
                    "base_branch": self.config.target.base_branch,
                    "work_path": str(work_path),
                    "work_branch": branch,
                    "base_sha": base_sha,
                },
            )
            self.store.create_run(
                run_id=run_id,
                target_repo_path=self.config.target.path,
                github_repo=self.config.target.github_repo,
                issue_number=issue.number,
                issue_title=issue.title,
                base_branch=self.config.target.base_branch,
                work_branch=branch,
                worktree_path=work_path if self.config.worktree.enabled else None,
                base_sha=base_sha,
                status="PENDING",
                current_phase="pending",
            )

            try:
                if self.config.github.enabled:
                    self.github.claim_issue(issue.number)
                self.store.update_run_status(run_id, status="CLAIMED", current_phase="claim")

                issue_path = self.artifacts.write_text(
                    run_id,
                    "00_issue.md",
                    self._redact_text(render_issue(issue, include_comments=self.config.context.include_issue_comments)),
                )
                self._record_artifact(run_id, "issue", issue_path)

                context_result = ContextCollector(
                    work_path,
                    config=self.config.context,
                    secret_filter=SecretFilter(
                        exclude_patterns=self.config.context.exclude,
                        protected_patterns=self.config.safety.protected_paths,
                    ),
                ).collect(issue=issue)
                context_path = self.artifacts.write_text(run_id, "00_context.md", context_result.content)
                self._record_artifact(run_id, "context", context_path)
                self.store.update_run_status(run_id, status="CONTEXT_COLLECTED", current_phase="context")

                design_path = self._codex_design(run_id, work_path, issue_path, context_path)
                design_review_path = self._codex_design_review(run_id, work_path, issue_path, context_path, design_path)
                design_decision = self.reviews.interpret_file(design_review_path)
                self.store.record_review(
                    run_id=run_id,
                    phase="design_review",
                    verdict=design_decision.verdict,
                    score=design_decision.output.score,
                    risk_level=design_decision.output.risk_level,
                    summary=design_decision.output.summary,
                    details_path=design_review_path,
                )
                if not design_decision.can_continue:
                    raise PipelineBlocked(f"Design review verdict: {design_decision.verdict}")
                self.store.update_run_status(run_id, status="DESIGN_REVIEWED", current_phase="design_review")

                implement_summary_path = self._codex_implement(
                    run_id,
                    work_path,
                    issue_path,
                    context_path,
                    design_path,
                    design_review_path,
                )
                self.store.update_run_status(run_id, status="IMPLEMENTED", current_phase="implement")

                work_git = GitOps(work_path)
                test_result, code_decision, diff_path, _, implement_summary_path = self._code_fix_loop(
                    run_id,
                    run_dir,
                    work_path,
                    work_git,
                    issue_path,
                    design_path,
                    implementation_summary_path=implement_summary_path,
                )
                return self._finish_commit(
                    run_id,
                    run_dir,
                    work_git,
                    issue_number=issue.number,
                    issue_title=issue.title,
                    implementation_summary_path=implement_summary_path,
                    diff_path=diff_path,
                    test_status=test_result.status,
                    code_review_summary=code_decision.output.summary,
                    work_branch=branch,
                    base_branch=self.config.target.base_branch,
                )
            except PipelineBlocked as exc:
                self.store.update_run_status(run_id, status="BLOCKED", current_phase="blocked")
                self._write_run_summary(
                    run_id,
                    status="BLOCKED",
                    issue_number=issue.number,
                    issue_title=issue.title,
                    commit_sha=None,
                    test_status=None,
                    code_review_summary=str(exc),
                )
                if self.config.github.enabled:
                    self.github.mark_blocked(issue.number)
                    self._comment_blocked(run_id, issue.number, str(exc))
                self._update_meta(run_id, status="BLOCKED")
                raise
            except Exception:
                self.store.update_run_status(run_id, status="FAILED", current_phase="failed")
                if self.config.github.enabled:
                    self.github.mark_blocked(issue.number)
                self._update_meta(run_id, status="FAILED")
                raise

    def _prepare_worktree(self, target_git: GitOps, *, run_id: str, branch: str) -> Path:
        if self.config.safety.fail_on_dirty_tree and not target_git.is_clean(
            ignored_patterns=[".codexflow/**"]
        ):
            raise PipelineBlocked("Target repository has a dirty working tree")
        if self.config.worktree.enabled:
            worktree_path = self.config.storage.worktree_dir / run_id
            target_git.create_worktree(
                path=worktree_path,
                branch=branch,
                base_ref=self.config.target.base_branch,
            )
            return worktree_path
        target_git.create_branch(branch, self.config.target.base_branch)
        return self.config.target.path

    def _validate_resume_run(self, run: dict, run_dir: Path) -> Path:
        if not run_dir.is_dir():
            raise PipelineBlocked(f"Run directory not found: {run_dir}")
        recorded_target = Path(run["target_repo_path"]).resolve()
        if recorded_target != self.config.target.path.resolve():
            raise PipelineBlocked(
                f"Run target does not match config target: {recorded_target} != {self.config.target.path.resolve()}"
            )
        work_path = Path(run["worktree_path"]) if run.get("worktree_path") else self.config.target.path
        if not work_path.exists():
            raise PipelineBlocked(f"Worktree path not found: {work_path}")
        work_git = GitOps(work_path)
        if not work_git.is_git_repo():
            raise PipelineBlocked(f"Worktree is not a git repository: {work_path}")
        work_branch = run.get("work_branch")
        if work_branch and work_git.current_branch() != work_branch:
            raise PipelineBlocked(f"Worktree branch mismatch: expected {work_branch}, got {work_git.current_branch()}")
        base_sha = run.get("base_sha")
        if base_sha and work_git.current_sha(base_sha) != base_sha:
            raise PipelineBlocked(f"Base sha is not available in worktree: {base_sha}")
        return work_path

    def _resume_validated_run(self, run: dict, run_dir: Path, work_path: Path) -> PipelineResult:
        run_id = run["id"]
        status = run["status"]
        if status == "DONE":
            return PipelineResult(run_id=run_id, status="DONE", run_dir=run_dir, commit_sha=run.get("final_sha"))
        if status not in {
            "CONTEXT_COLLECTED",
            "DEV_DESIGN_DONE",
            "DESIGN_REVIEWED",
            "IMPLEMENTED",
            "TESTED",
            "COMMIT_READY",
        }:
            raise PipelineBlocked(f"Run status is not resumable: {status}")

        issue_number = int(run["issue_number"])
        issue_title = run.get("issue_title") or ""
        issue_path = _require_artifact(run_dir, "00_issue.md")
        context_path = _require_artifact(run_dir, "00_context.md")
        work_git = GitOps(work_path)

        if status == "CONTEXT_COLLECTED":
            design_path = self._codex_design(run_id, work_path, issue_path, context_path)
            status = "DEV_DESIGN_DONE"
        else:
            design_path = _require_artifact(run_dir, "01_dev_design.output.json")

        if status == "DEV_DESIGN_DONE":
            design_review_path = self._codex_design_review(run_id, work_path, issue_path, context_path, design_path)
            design_decision = self.reviews.interpret_file(design_review_path)
            self.store.record_review(
                run_id=run_id,
                phase="design_review",
                verdict=design_decision.verdict,
                score=design_decision.output.score,
                risk_level=design_decision.output.risk_level,
                summary=design_decision.output.summary,
                details_path=design_review_path,
            )
            if not design_decision.can_continue:
                raise PipelineBlocked(f"Design review verdict: {design_decision.verdict}")
            self.store.update_run_status(run_id, status="DESIGN_REVIEWED", current_phase="design_review")
            status = "DESIGN_REVIEWED"
        else:
            design_review_path = _require_artifact(run_dir, "02_review_design.output.json")

        if status == "DESIGN_REVIEWED":
            implementation_summary_path = self._codex_implement(
                run_id,
                work_path,
                issue_path,
                context_path,
                design_path,
                design_review_path,
            )
            self.store.update_run_status(run_id, status="IMPLEMENTED", current_phase="implement")
            status = "IMPLEMENTED"
        else:
            implementation_summary_path = _latest_artifact(run_dir, "03_dev_fix", ".final.md") or _require_artifact(
                run_dir,
                "03_dev_implement.final.md",
            )

        if status == "IMPLEMENTED":
            test_result, code_decision, diff_path, _, implementation_summary_path = self._code_fix_loop(
                run_id,
                run_dir,
                work_path,
                work_git,
                issue_path,
                design_path,
                implementation_summary_path=implementation_summary_path,
            )
            return self._finish_commit(
                run_id,
                run_dir,
                work_git,
                issue_number=issue_number,
                issue_title=issue_title,
                implementation_summary_path=implementation_summary_path,
                diff_path=diff_path,
                test_status=test_result.status,
                code_review_summary=code_decision.output.summary,
                work_branch=run["work_branch"],
                base_branch=run["base_branch"],
            )

        if status == "TESTED":
            round_number = int(run.get("fix_round") or 0) + 1
            diff_path = _require_artifact(run_dir, _round_name("04_git_diff.patch", round_number))
            test_log_path = _require_artifact(run_dir, _round_name("05_test.log", round_number))
            test_result = _test_result_from_log(test_log_path, command=self.config.tests.command)
            protected = work_git.protected_path_changes(self.config.safety.protected_paths)
            test_block = self._test_policy_block(test_result)
            if test_block:
                code_review_path = self._write_policy_review(run_id, test_block, round_number=round_number)
            else:
                code_review_path = self._codex_code_review(
                    run_id,
                    work_path,
                    issue_path,
                    design_path,
                    diff_path,
                    test_log_path,
                    protected_paths=protected,
                    round_number=round_number,
                )
            code_decision = self.reviews.interpret_file(code_review_path)
            self.store.record_review(
                run_id=run_id,
                phase="code_review" if round_number == 1 else f"code_review.round{round_number}",
                verdict=code_decision.verdict,
                score=code_decision.output.score,
                risk_level=code_decision.output.risk_level,
                summary=code_decision.output.summary,
                details_path=code_review_path,
            )
            if not code_decision.can_continue:
                if round_number > self.config.codex.max_fix_rounds:
                    raise PipelineBlocked(
                        f"Code review verdict after {self.config.codex.max_fix_rounds} fix rounds: "
                        f"{code_decision.verdict} - {code_decision.output.summary}"
                    )
                next_round = round_number + 1
                implementation_summary_path = self._codex_fix(
                    run_id,
                    work_path,
                    issue_path,
                    design_path,
                    code_review_path,
                    diff_path,
                    test_log_path,
                    round_number=next_round,
                )
                test_result, code_decision, diff_path, _, implementation_summary_path = self._code_fix_loop(
                    run_id,
                    run_dir,
                    work_path,
                    work_git,
                    issue_path,
                    design_path,
                    implementation_summary_path=implementation_summary_path,
                    start_round=next_round,
                )
            return self._finish_commit(
                run_id,
                run_dir,
                work_git,
                issue_number=issue_number,
                issue_title=issue_title,
                implementation_summary_path=implementation_summary_path,
                diff_path=diff_path,
                test_status=test_result.status,
                code_review_summary=code_decision.output.summary,
                work_branch=run["work_branch"],
                base_branch=run["base_branch"],
            )

        if status == "COMMIT_READY":
            diff_path = _latest_artifact(run_dir, "04_git_diff", ".patch") or _require_artifact(run_dir, "04_git_diff.patch")
            test_log_path = _latest_artifact(run_dir, "05_test", ".log") or _require_artifact(run_dir, "05_test.log")
            review_path = _latest_artifact(run_dir, "06_review_code", ".output.json") or _require_artifact(
                run_dir,
                "06_review_code.output.json",
            )
            review_payload = json.loads(review_path.read_text(encoding="utf-8"))
            test_result = _test_result_from_log(test_log_path, command=self.config.tests.command)
            return self._finish_commit(
                run_id,
                run_dir,
                work_git,
                issue_number=issue_number,
                issue_title=issue_title,
                implementation_summary_path=implementation_summary_path,
                diff_path=diff_path,
                test_status=test_result.status,
                code_review_summary=review_payload.get("summary") or "",
                work_branch=run["work_branch"],
                base_branch=run["base_branch"],
            )

        raise PipelineBlocked(f"Run status is not resumable: {status}")

    def _codex_design(self, run_id: str, work_path: Path, issue_path: Path, context_path: Path) -> Path:
        prompt_path = self.artifacts.run_dir(run_id) / "01_dev_design.prompt.md"
        output_path = self.artifacts.run_dir(run_id) / "01_dev_design.output.json"
        _ensure_missing(prompt_path)
        _ensure_missing(output_path)
        prompt_path = self.prompts.render_to_file(
            "dev_design",
            {"CONTEXT": context_path.read_text(encoding="utf-8"), "ISSUE": issue_path.read_text(encoding="utf-8")},
            prompt_path,
        )
        result = self.codex.run(
            cwd=work_path,
            prompt_path=prompt_path,
            output_path=output_path,
            sandbox="read-only",
            schema_path=schema_path("design.schema.json"),
            extra_args=self.config.codex.extra_args,
            timeout_seconds=self.config.codex.design_timeout_seconds,
        )
        self._record_codex_step(run_id, "dev_design", "developer", result)
        if not result.ok:
            raise PipelineBlocked("Developer design failed")
        self._record_artifact(run_id, "design", output_path)
        self.store.update_run_status(run_id, status="DEV_DESIGN_DONE", current_phase="dev_design")
        return output_path

    def _codex_design_review(
        self,
        run_id: str,
        work_path: Path,
        issue_path: Path,
        context_path: Path,
        design_path: Path,
    ) -> Path:
        prompt_path = self.artifacts.run_dir(run_id) / "02_review_design.prompt.md"
        output_path = self.artifacts.run_dir(run_id) / "02_review_design.output.json"
        _ensure_missing(prompt_path)
        _ensure_missing(output_path)
        prompt_path = self.prompts.render_to_file(
            "review_design",
            {
                "CONTEXT": context_path.read_text(encoding="utf-8"),
                "ISSUE": issue_path.read_text(encoding="utf-8"),
                "DESIGN_JSON": design_path.read_text(encoding="utf-8"),
            },
            prompt_path,
        )
        result = self.codex.run(
            cwd=work_path,
            prompt_path=prompt_path,
            output_path=output_path,
            sandbox=self.config.codex.reviewer_sandbox,
            schema_path=schema_path("review.schema.json"),
            extra_args=self.config.codex.extra_args,
            timeout_seconds=self.config.codex.review_timeout_seconds,
        )
        self._record_codex_step(run_id, "review_design", "reviewer", result)
        if not result.ok:
            raise PipelineBlocked("Design review failed")
        self._record_artifact(run_id, "design_review", output_path)
        return output_path

    def _codex_implement(
        self,
        run_id: str,
        work_path: Path,
        issue_path: Path,
        context_path: Path,
        design_path: Path,
        design_review_path: Path,
    ) -> Path:
        prompt_path = self.artifacts.run_dir(run_id) / "03_dev_implement.prompt.md"
        output_path = self.artifacts.run_dir(run_id) / "03_dev_implement.final.md"
        stream_path = self.artifacts.run_dir(run_id) / "03_dev_implement.ndjson"
        _ensure_missing(prompt_path)
        _ensure_missing(output_path)
        _ensure_missing(stream_path)
        prompt_path = self.prompts.render_to_file(
            "dev_implement",
            {
                "CONTEXT": context_path.read_text(encoding="utf-8"),
                "ISSUE": issue_path.read_text(encoding="utf-8"),
                "DESIGN_JSON": design_path.read_text(encoding="utf-8"),
                "DESIGN_REVIEW_JSON": design_review_path.read_text(encoding="utf-8"),
            },
            prompt_path,
        )
        result = self.codex.run(
            cwd=work_path,
            prompt_path=prompt_path,
            output_path=output_path,
            sandbox=self.config.codex.developer_sandbox,
            json_stream_path=stream_path,
            extra_args=self.config.codex.extra_args,
            timeout_seconds=self.config.codex.implement_timeout_seconds,
        )
        self._record_codex_step(run_id, "dev_implement", "developer", result)
        if not result.ok:
            raise PipelineBlocked("Developer implementation failed")
        self._record_artifact(run_id, "implementation_summary", output_path)
        self._record_artifact(run_id, "implementation_stream", stream_path)
        return output_path

    def _codex_fix(
        self,
        run_id: str,
        work_path: Path,
        issue_path: Path,
        design_path: Path,
        code_review_path: Path,
        diff_path: Path,
        test_log_path: Path,
        *,
        round_number: int,
    ) -> Path:
        prompt_path = self.artifacts.run_dir(run_id) / _round_name("03_dev_fix.prompt.md", round_number)
        output_path = self.artifacts.run_dir(run_id) / _round_name("03_dev_fix.final.md", round_number)
        stream_path = self.artifacts.run_dir(run_id) / _round_name("03_dev_fix.ndjson", round_number)
        _ensure_missing(prompt_path)
        _ensure_missing(output_path)
        _ensure_missing(stream_path)
        prompt_path = self.prompts.render_to_file(
            "dev_fix",
            {
                "ISSUE": issue_path.read_text(encoding="utf-8"),
                "DESIGN_JSON": design_path.read_text(encoding="utf-8"),
                "CODE_REVIEW_JSON": code_review_path.read_text(encoding="utf-8"),
                "GIT_DIFF": diff_path.read_text(encoding="utf-8"),
                "TEST_LOG": test_log_path.read_text(encoding="utf-8"),
            },
            prompt_path,
        )
        result = self.codex.run(
            cwd=work_path,
            prompt_path=prompt_path,
            output_path=output_path,
            sandbox=self.config.codex.developer_sandbox,
            json_stream_path=stream_path,
            extra_args=self.config.codex.extra_args,
            timeout_seconds=self.config.codex.implement_timeout_seconds,
        )
        self._record_codex_step(run_id, f"dev_fix.round{round_number}", "developer", result)
        if not result.ok:
            raise PipelineBlocked(f"Developer fix round {round_number} failed")
        self._record_artifact(run_id, f"implementation_fix_round{round_number}", output_path)
        self._record_artifact(run_id, f"implementation_fix_stream_round{round_number}", stream_path)
        return output_path

    def _codex_code_review(
        self,
        run_id: str,
        work_path: Path,
        issue_path: Path,
        design_path: Path,
        diff_path: Path,
        test_log_path: Path,
        *,
        protected_paths: list[str],
        round_number: int = 1,
    ) -> Path:
        prompt_path = self.artifacts.run_dir(run_id) / _round_name("06_review_code.prompt.md", round_number)
        output_path = self.artifacts.run_dir(run_id) / _round_name("06_review_code.output.json", round_number)
        _ensure_missing(prompt_path)
        _ensure_missing(output_path)
        prompt_path = self.prompts.render_to_file(
            "review_code",
            {
                "ISSUE": issue_path.read_text(encoding="utf-8"),
                "DESIGN_JSON": design_path.read_text(encoding="utf-8"),
                "GIT_DIFF": diff_path.read_text(encoding="utf-8"),
                "TEST_LOG": test_log_path.read_text(encoding="utf-8"),
                "SAFETY_SCAN": json.dumps({"protected_path_changes": protected_paths}, ensure_ascii=False),
            },
            prompt_path,
        )
        result = self.codex.run(
            cwd=work_path,
            prompt_path=prompt_path,
            output_path=output_path,
            sandbox=self.config.codex.reviewer_sandbox,
            schema_path=schema_path("review.schema.json"),
            extra_args=self.config.codex.extra_args,
            timeout_seconds=self.config.codex.review_timeout_seconds,
        )
        phase = "review_code" if round_number == 1 else f"review_code.round{round_number}"
        self._record_codex_step(run_id, phase, "reviewer", result)
        if not result.ok:
            raise PipelineBlocked("Code review failed")
        self._record_artifact(run_id, "code_review" if round_number == 1 else f"code_review_round{round_number}", output_path)
        return output_path

    def _code_fix_loop(
        self,
        run_id: str,
        run_dir: Path,
        work_path: Path,
        work_git: GitOps,
        issue_path: Path,
        design_path: Path,
        *,
        implementation_summary_path: Path,
        start_round: int = 1,
    ) -> tuple[TestResult, ReviewDecision, Path, Path, Path]:
        max_fix_rounds = self.config.codex.max_fix_rounds
        round_number = start_round
        while True:
            changed_files = work_git.changed_files()
            if not changed_files:
                raise PipelineBlocked("Implementation produced no git diff")

            protected = work_git.protected_path_changes(self.config.safety.protected_paths)
            if protected and self.config.safety.fail_on_protected_path_change:
                raise PipelineBlocked(f"Protected paths changed: {', '.join(protected)}")

            diff_path = run_dir / _round_name("04_git_diff.patch", round_number)
            _ensure_missing(diff_path)
            diff_path = work_git.save_diff(diff_path)
            self._redact_file(diff_path)
            self._record_artifact(run_id, "diff" if round_number == 1 else f"diff_round{round_number}", diff_path)

            test_log_path = run_dir / _round_name("05_test.log", round_number)
            _ensure_missing(test_log_path)
            test_result = self.tests.run(
                cwd=work_path,
                command=self.config.tests.command,
                log_path=test_log_path,
                timeout_seconds=self.config.tests.timeout_seconds,
            )
            self._redact_file(test_result.log_path)
            self._record_artifact(run_id, "test_log" if round_number == 1 else f"test_log_round{round_number}", test_result.log_path)
            self.store.update_run_status(
                run_id,
                status="TESTED",
                current_phase="test" if round_number == 1 else f"test_round{round_number}",
                fix_round=max(0, round_number - 1),
            )

            test_block = self._test_policy_block(test_result)
            if test_block:
                code_review_path = self._write_policy_review(run_id, test_block, round_number=round_number)
            else:
                code_review_path = self._codex_code_review(
                    run_id,
                    work_path,
                    issue_path,
                    design_path,
                    diff_path,
                    test_result.log_path,
                    protected_paths=protected,
                    round_number=round_number,
                )

            code_decision = self.reviews.interpret_file(code_review_path)
            self.store.record_review(
                run_id=run_id,
                phase="code_review" if round_number == 1 else f"code_review.round{round_number}",
                verdict=code_decision.verdict,
                score=code_decision.output.score,
                risk_level=code_decision.output.risk_level,
                summary=code_decision.output.summary,
                details_path=code_review_path,
            )
            if code_decision.can_continue:
                return test_result, code_decision, diff_path, code_review_path, implementation_summary_path

            if round_number > max_fix_rounds:
                raise PipelineBlocked(
                    f"Code review verdict after {max_fix_rounds} fix rounds: "
                    f"{code_decision.verdict} - {code_decision.output.summary}"
                )

            next_round = round_number + 1
            self.store.update_run_status(
                run_id,
                status="FIXING",
                current_phase=f"dev_fix_round{next_round}",
                fix_round=round_number,
            )
            implementation_summary_path = self._codex_fix(
                run_id,
                work_path,
                issue_path,
                design_path,
                code_review_path,
                diff_path,
                test_result.log_path,
                round_number=next_round,
            )
            round_number = next_round

    def _test_policy_block(self, test_result: TestResult) -> str | None:
        if test_result.status == "pass":
            return None
        if test_result.status == "skipped":
            if self.config.tests.required and not self.config.tests.allow_skipped:
                return "Tests skipped but tests.required=true"
            return None
        if self.config.tests.fail_on_failure:
            return f"Tests did not pass: {test_result.status}"
        return None

    def _write_policy_review(self, run_id: str, summary: str, *, round_number: int) -> Path:
        payload = {
            "verdict": "needs_fix",
            "score": 0,
            "risk_level": "high",
            "summary": self._redact_text(summary),
            "blocking_issues": [
                {
                    "issue": "Test policy failed",
                    "reason": self._redact_text(summary),
                    "suggested_fix": "Fix the implementation so the configured test command passes.",
                }
            ],
            "non_blocking_suggestions": [],
        }
        relative_path = _round_name("06_review_code.output.json", round_number)
        _ensure_missing(self.artifacts.run_dir(run_id) / relative_path)
        path = self.artifacts.write_json(run_id, relative_path, payload)
        self._record_artifact(run_id, "code_review" if round_number == 1 else f"code_review_round{round_number}", path)
        return path

    def _finish_commit(
        self,
        run_id: str,
        run_dir: Path,
        work_git: GitOps,
        *,
        issue_number: int,
        issue_title: str,
        implementation_summary_path: Path,
        diff_path: Path,
        test_status: str,
        code_review_summary: str,
        work_branch: str,
        base_branch: str,
    ) -> PipelineResult:
        self.store.update_run_status(run_id, status="COMMIT_READY", current_phase="commit")
        commit_message_path = run_dir / "11_commit_message.txt"
        if not commit_message_path.exists():
            commit_message_path = self._write_commit_message(
                run_id,
                issue_number=issue_number,
                issue_title=issue_title,
                implementation_summary_path=implementation_summary_path,
                test_status=test_status,
                code_review_summary=code_review_summary,
            )
        if not self.config.commit.auto_commit:
            self.store.update_run_status(run_id, status="COMMIT_READY", current_phase="commit_ready")
            if self.config.github.enabled:
                self.github.mark_review(issue_number)
            self._update_meta(run_id, status="COMMIT_READY")
            return PipelineResult(run_id=run_id, status="COMMIT_READY", run_dir=run_dir)

        final_sha = work_git.commit_all(message_file=commit_message_path)
        self.store.record_commit(
            run_id=run_id,
            commit_sha=final_sha,
            commit_message_path=commit_message_path,
            diff_path=diff_path,
            test_summary=test_status,
        )
        self.store.update_run_status(
            run_id,
            status="DONE",
            current_phase="done",
            final_sha=final_sha,
        )
        self._write_run_summary(
            run_id,
            status="DONE",
            issue_number=issue_number,
            issue_title=issue_title,
            commit_sha=final_sha,
            test_status=test_status,
            code_review_summary=code_review_summary,
        )
        self._publish_after_commit(
            run_id,
            run_dir,
            work_git,
            issue_number=issue_number,
            issue_title=issue_title,
            commit_sha=final_sha,
            work_branch=work_branch,
            base_branch=base_branch,
            test_status=test_status,
            code_review_summary=code_review_summary,
        )
        if self.config.github.enabled:
            self.github.mark_review(issue_number)
        self._update_meta(run_id, status="DONE", final_sha=final_sha)
        return PipelineResult(run_id=run_id, status="DONE", run_dir=run_dir, commit_sha=final_sha)

    def _write_run_summary(
        self,
        run_id: str,
        *,
        status: str,
        issue_number: int,
        issue_title: str,
        commit_sha: str | None,
        test_status: str | None,
        code_review_summary: str | None,
    ) -> Path:
        path = self.artifacts.run_dir(run_id) / "14_run_summary.md"
        if path.exists():
            return path
        content = "\n".join(
            [
                f"# CodexFlow Run {run_id}",
                "",
                f"Status: `{status}`",
                f"Issue: `#{issue_number}` {issue_title}",
                f"Commit: `{commit_sha or 'not committed'}`",
                f"Test status: `{test_status or 'not recorded'}`",
                "",
                "## Code Review",
                "",
                self._redact_text(code_review_summary or "No code review summary recorded."),
                "",
            ]
        )
        path.write_text(content, encoding="utf-8")
        self._record_artifact(run_id, "run_summary", path)
        return path

    def _publish_after_commit(
        self,
        run_id: str,
        run_dir: Path,
        work_git: GitOps,
        *,
        issue_number: int,
        issue_title: str,
        commit_sha: str,
        work_branch: str,
        base_branch: str,
        test_status: str,
        code_review_summary: str,
    ) -> None:
        should_publish = (
            self.config.commit.auto_push
            or self.config.commit.create_pr
            or self.config.commit.comment_on_issue
            or self.config.commit.dry_run
        )
        if not should_publish:
            return

        body_path = self._write_pr_body(
            run_id,
            issue_number=issue_number,
            issue_title=issue_title,
            commit_sha=commit_sha,
            work_branch=work_branch,
            base_branch=base_branch,
            test_status=test_status,
            code_review_summary=code_review_summary,
        )
        publish_meta = {
            "auto_push": self.config.commit.auto_push,
            "create_pr": self.config.commit.create_pr,
            "comment_on_issue": self.config.commit.comment_on_issue,
            "dry_run": self.config.commit.dry_run,
            "remote": self.config.commit.push_remote,
            "branch": work_branch,
            "base_branch": base_branch,
            "body_path": str(body_path),
        }
        if self.config.commit.dry_run:
            dry_run_path = self.artifacts.write_json(run_id, "12_publish_dry_run.json", publish_meta)
            self._record_artifact(run_id, "publish_dry_run", dry_run_path)
            self._update_meta(run_id, publish=publish_meta)
            return

        if self.config.commit.auto_push:
            work_git.push_branch(remote=self.config.commit.push_remote, branch=work_branch)
            publish_meta["pushed"] = True
        if self.config.commit.create_pr:
            pr = self.github.create_pr(
                base=base_branch,
                head=work_branch,
                title=f"Address issue #{issue_number}: {issue_title}",
                body_file=str(body_path),
            )
            publish_meta["pr_url"] = pr.url
            if pr.number is not None:
                publish_meta["pr_number"] = pr.number
        if self.config.commit.comment_on_issue:
            comment_path = self._write_issue_comment(run_id, publish_meta=publish_meta)
            self.github.comment_issue(issue_number, body_file=str(comment_path))
            publish_meta["issue_comment_path"] = str(comment_path)
        self._update_meta(run_id, publish=publish_meta)

    def _write_pr_body(
        self,
        run_id: str,
        *,
        issue_number: int,
        issue_title: str,
        commit_sha: str,
        work_branch: str,
        base_branch: str,
        test_status: str,
        code_review_summary: str,
    ) -> Path:
        path = self.artifacts.run_dir(run_id) / "12_pr_body.md"
        _ensure_missing(path)
        content = "\n".join(
            [
                f"# CodexFlow run {run_id}",
                "",
                f"Issue: #{issue_number} - {issue_title}",
                f"Branch: `{work_branch}` -> `{base_branch}`",
                f"Commit: `{commit_sha}`",
                f"Test status: `{test_status}`",
                "",
                "## Review Summary",
                "",
                self._redact_text(code_review_summary or "No review summary recorded."),
                "",
                "## Artifacts",
                "",
                f"Run directory: `{self.artifacts.run_dir(run_id)}`",
                "",
            ]
        )
        path.write_text(content, encoding="utf-8")
        self._record_artifact(run_id, "pr_body", path)
        return path

    def _write_issue_comment(self, run_id: str, *, publish_meta: dict) -> Path:
        path = self.artifacts.run_dir(run_id) / "13_issue_comment.md"
        _ensure_missing(path)
        lines = [
            f"CodexFlow run `{run_id}` completed.",
            "",
            f"- Branch: `{publish_meta['branch']}`",
            f"- Dry run: `{publish_meta['dry_run']}`",
        ]
        if "pr_url" in publish_meta:
            lines.append(f"- PR: {publish_meta['pr_url']}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._record_artifact(run_id, "issue_comment", path)
        return path

    def _comment_blocked(self, run_id: str, issue_number: int, reason: str) -> None:
        if not self.config.commit.comment_on_issue or self.config.commit.dry_run:
            return
        path = self.artifacts.run_dir(run_id) / "13_blocked_comment.md"
        if path.exists():
            return
        path.write_text(
            "\n".join(
                [
                    f"CodexFlow run `{run_id}` is blocked.",
                    "",
                    f"Reason: {self._redact_text(reason)}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self._record_artifact(run_id, "blocked_comment", path)
        self.github.comment_issue(issue_number, body_file=str(path))

    def _write_commit_message(
        self,
        run_id: str,
        *,
        issue_number: int,
        issue_title: str,
        implementation_summary_path: Path,
        test_status: str,
        code_review_summary: str,
    ) -> Path:
        summary_payload = {
            "title": f"address issue #{issue_number} - {issue_title}",
            "issue": f"#{issue_number}",
            "summary": [
                self._redact_text(implementation_summary_path.read_text(encoding="utf-8").strip())
                or "Implemented requested change."
            ],
            "core_logic": ["See git diff for implementation details."],
            "tests": [f"{self._redact_text(self.config.tests.command or 'not configured')}: {test_status}"],
            "risks": [self._redact_text(code_review_summary) or "No additional risks reported."],
        }
        summary_target = self.artifacts.run_dir(run_id) / "10_final_commit_summary.json"
        commit_message_path = self.artifacts.run_dir(run_id) / "11_commit_message.txt"
        _ensure_missing(summary_target)
        _ensure_missing(commit_message_path)
        summary_path = self.artifacts.write_json(run_id, "10_final_commit_summary.json", summary_payload)
        self._record_artifact(run_id, "commit_summary", summary_path)
        self.commits.write_message(
            commit_message_path,
            issue_number=issue_number,
            issue_title=issue_title,
            run_id=run_id,
            design_review="pass",
            code_review="pass",
            test_command=self._redact_text(self.config.tests.command or "") or None,
            test_result=test_status,
            summary=CommitSummary(**summary_payload),
        )
        self._record_artifact(run_id, "commit_message", commit_message_path)
        return commit_message_path

    def _record_codex_step(self, run_id: str, phase: str, agent_role: str, result) -> None:
        self._redact_file(result.output_path)
        if result.stdout_log_path:
            self._redact_file(result.stdout_log_path)
        if result.stderr_log_path:
            self._redact_file(result.stderr_log_path)
        if result.json_stream_path:
            self._redact_file(result.json_stream_path)
        command_result = result.command_result
        self.store.record_step(
            run_id=run_id,
            phase=phase,
            agent_role=agent_role,
            command=" ".join(command_result.command),
            prompt_path=result.prompt_path,
            output_path=result.output_path,
            stdout_path=result.json_stream_path or result.stdout_log_path,
            stderr_path=result.stderr_log_path,
            exit_code=command_result.exit_code,
            started_at=command_result.started_at.isoformat(),
            ended_at=command_result.ended_at.isoformat(),
        )
        if result.stdout_log_path:
            self._record_artifact(run_id, f"{phase}_stdout", result.stdout_log_path)
        if result.stderr_log_path:
            self._record_artifact(run_id, f"{phase}_stderr", result.stderr_log_path)

    def _record_artifact(self, run_id: str, kind: str, path: Path) -> None:
        self.store.record_artifact(
            run_id=run_id,
            kind=kind,
            path=path,
            sha256=ArtifactStore.sha256_file(path) if path.exists() else None,
        )

    def _redact_text(self, content: str) -> str:
        return SecretFilter(
            exclude_patterns=self.config.context.exclude,
            protected_patterns=self.config.safety.protected_paths,
        ).redact_text(content)

    def _redact_file(self, path: Path | None) -> None:
        if path is None or not path.exists():
            return
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return
        redacted = self._redact_text(content)
        if redacted != content:
            path.write_text(redacted, encoding="utf-8")

    def _update_meta(self, run_id: str, **updates) -> None:
        meta_path = self.artifacts.run_dir(run_id) / "meta.json"
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        payload.update(updates)
        self.artifacts.write_json(run_id, "meta.json", payload)


def schema_path(name: str) -> Path:
    return Path(str(resources.files("codexflow.schemas").joinpath(name)))


def _round_name(name: str, round_number: int) -> str:
    if round_number == 1:
        return name
    replacements = [
        ".prompt.md",
        ".output.json",
        ".final.md",
        ".ndjson",
        ".patch",
        ".log",
    ]
    for suffix in replacements:
        if name.endswith(suffix):
            return f"{name[:-len(suffix)]}.round{round_number}{suffix}"
    return f"{name}.round{round_number}"


def _require_artifact(run_dir: Path, relative_path: str) -> Path:
    path = run_dir / relative_path
    if not path.exists():
        raise PipelineBlocked(f"Required artifact missing: {path}")
    return path


def _ensure_missing(path: Path) -> None:
    if path.exists():
        raise PipelineBlocked(f"Refusing to overwrite existing artifact: {path}")


def _latest_artifact(run_dir: Path, prefix: str, suffix: str) -> Path | None:
    candidates: list[tuple[int, Path]] = []
    base = run_dir / f"{prefix}{suffix}"
    if base.exists():
        candidates.append((1, base))
    for path in run_dir.glob(f"{prefix}.round*{suffix}"):
        marker = path.name[len(prefix) + len(".round") : -len(suffix)]
        if marker.isdigit():
            candidates.append((int(marker), path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _test_result_from_log(path: Path, *, command: str | None) -> TestResult:
    content = path.read_text(encoding="utf-8")
    status = None
    exit_code = None
    for line in content.splitlines():
        if line.startswith("status: "):
            status = line.split(": ", 1)[1].strip()
        elif line.startswith("exit_code: "):
            raw_exit_code = line.split(": ", 1)[1].strip()
            if raw_exit_code and raw_exit_code != "None":
                exit_code = int(raw_exit_code)
    if status not in {"pass", "fail", "timeout", "skipped"}:
        raise PipelineBlocked(f"Could not recover test status from log: {path}")
    return TestResult(command=command, status=status, exit_code=exit_code, log_path=path)
