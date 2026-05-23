from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import shutil

from .command import CommandRunner
from .config import CodexFlowConfig
from .gitops import GitOps
from .locks import LockManager


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    details: str
    required: bool = True


class Doctor:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def run(self, config: CodexFlowConfig) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []

        checks.append(self._command_exists("git", required=True))
        checks.append(self._command_exists("codex", required=True))
        checks.append(self._command_exists("gh", required=config.github.enabled))

        if config.github.enabled and shutil.which("gh"):
            result = self.runner.run(["gh", "auth", "status"], timeout_seconds=20)
            checks.append(
                DoctorCheck(
                    name="gh auth",
                    ok=result.ok,
                    details="authenticated" if result.ok else result.stderr.strip() or "gh auth status failed",
                    required=True,
                )
            )

        target_path = config.target.path
        checks.append(
            DoctorCheck(
                name="target path",
                ok=target_path.exists(),
                details=str(target_path),
                required=True,
            )
        )

        if target_path.exists() and shutil.which("git"):
            repo_result = self.runner.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=target_path,
                timeout_seconds=20,
            )
            checks.append(
                DoctorCheck(
                    name="target git repo",
                    ok=repo_result.ok and repo_result.stdout.strip() == "true",
                    details=repo_result.stderr.strip() or repo_result.stdout.strip(),
                    required=True,
                )
            )

            branch_result = self.runner.run(
                ["git", "rev-parse", "--verify", config.target.base_branch],
                cwd=target_path,
                timeout_seconds=20,
            )
            checks.append(
                DoctorCheck(
                    name="base branch",
                    ok=branch_result.ok,
                    details=config.target.base_branch,
                    required=True,
                )
            )

            if config.safety.fail_on_dirty_tree:
                clean = GitOps(target_path, runner=self.runner).is_clean(ignored_patterns=[".codexflow/**"])
                checks.append(
                    DoctorCheck(
                        name="clean tree",
                        ok=clean,
                        details="clean" if clean else "dirty working tree",
                        required=True,
                    )
                )

        checks.append(self._path_writable_parent("runs dir", config.storage.runs_dir))
        checks.append(self._path_writable_parent("db path", config.storage.db_path))

        stale_locks = LockManager(config.target.path / ".codexflow" / "locks").stale_locks()
        checks.append(
            DoctorCheck(
                name="stale locks",
                ok=not stale_locks,
                details="none" if not stale_locks else ", ".join(str(path) for path in stale_locks),
                required=False,
            )
        )

        if config.tests.required:
            command = config.tests.command or ""
            command_name = shlex.split(command)[0] if command.strip() else ""
            ok = bool(command_name)
            details = command
            if ok and "/" not in command_name:
                ok = shutil.which(command_name) is not None
                details = f"{command_name}: {'found' if ok else 'not found'}"
            checks.append(DoctorCheck(name="test command", ok=ok, details=details, required=True))

        return checks

    @staticmethod
    def has_failures(checks: list[DoctorCheck]) -> bool:
        return any(check.required and not check.ok for check in checks)

    @staticmethod
    def _command_exists(name: str, *, required: bool) -> DoctorCheck:
        path = shutil.which(name)
        return DoctorCheck(
            name=f"{name} command",
            ok=path is not None,
            details=path or "not found",
            required=required,
        )

    @staticmethod
    def _path_writable_parent(name: str, path: Path) -> DoctorCheck:
        parent = path if path.suffix == "" else path.parent
        exists = parent.exists()
        writable = exists and parent.is_dir()
        return DoctorCheck(
            name=name,
            ok=writable,
            details=str(parent),
            required=True,
        )
