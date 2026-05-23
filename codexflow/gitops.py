from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from .command import CommandRunner


class GitOpsError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch: str
    base_ref: str


class GitOps:
    def __init__(self, repo_path: Path, *, runner: CommandRunner | None = None) -> None:
        self.repo_path = repo_path
        self.runner = runner or CommandRunner()

    def is_git_repo(self) -> bool:
        result = self._git(["rev-parse", "--is-inside-work-tree"])
        return result.ok and result.stdout.strip() == "true"

    def current_branch(self) -> str:
        result = self._git(["branch", "--show-current"])
        self._raise_on_failure(result)
        return result.stdout.strip()

    def current_sha(self, ref: str = "HEAD") -> str:
        result = self._git(["rev-parse", ref])
        self._raise_on_failure(result)
        return result.stdout.strip()

    def branch_exists(self, branch: str) -> bool:
        result = self._git(["rev-parse", "--verify", branch])
        return result.ok

    def is_clean(self, *, ignored_patterns: list[str] | None = None) -> bool:
        result = self._git(["status", "--porcelain"])
        self._raise_on_failure(result)
        ignored_patterns = ignored_patterns or []
        for line in result.stdout.splitlines():
            paths = _porcelain_paths(line)
            if paths and all(matches_any(path, ignored_patterns) for path in paths):
                continue
            return False
        return True

    def create_branch(self, branch: str, base_ref: str) -> None:
        result = self._git(["switch", "-c", branch, base_ref])
        self._raise_on_failure(result)

    def create_worktree(self, *, path: Path, branch: str, base_ref: str) -> WorktreeInfo:
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self._git(["worktree", "add", "-b", branch, str(path), base_ref])
        self._raise_on_failure(result)
        return WorktreeInfo(path=path, branch=branch, base_ref=base_ref)

    def changed_files(self, *, staged: bool = False, include_untracked: bool = True) -> list[str]:
        args = ["diff", "--name-only"]
        if staged:
            args.append("--cached")
        result = self._git(args)
        self._raise_on_failure(result)
        files = {line for line in result.stdout.splitlines() if line.strip()}
        if include_untracked and not staged:
            untracked = self._git(["ls-files", "--others", "--exclude-standard"])
            self._raise_on_failure(untracked)
            files.update(line for line in untracked.stdout.splitlines() if line.strip())
        return sorted(files)

    def save_diff(self, output_path: Path, *, staged: bool = False, include_untracked: bool = True) -> Path:
        if include_untracked and not staged:
            intent_result = self._git(["add", "--intent-to-add", "-A"])
            self._raise_on_failure(intent_result)
        args = ["diff"]
        if staged:
            args.append("--cached")
        result = self._git(args)
        self._raise_on_failure(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.stdout, encoding="utf-8")
        return output_path

    def protected_path_changes(self, patterns: list[str]) -> list[str]:
        files = set(self.changed_files())
        files.update(self.changed_files(staged=True))
        return sorted(path for path in files if matches_any(path, patterns))

    def commit_all(self, *, message_file: Path) -> str:
        add_result = self._git(["add", "-A"])
        self._raise_on_failure(add_result)
        commit_result = self._git(["commit", "-F", str(message_file)])
        self._raise_on_failure(commit_result)
        return self.current_sha("HEAD")

    def push_branch(self, *, remote: str, branch: str) -> None:
        result = self._git(["push", remote, f"HEAD:{branch}"])
        self._raise_on_failure(result)

    def _git(self, args: list[str]):
        return self.runner.run(["git", *args], cwd=self.repo_path, timeout_seconds=60)

    @staticmethod
    def _raise_on_failure(result) -> None:
        if not result.ok:
            raise GitOpsError(result.stderr.strip() or result.stdout.strip() or "git command failed")


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    return any(fnmatch(normalized, pattern) or posix_path.match(pattern) for pattern in patterns)


def _porcelain_paths(line: str) -> tuple[str, ...]:
    payload = line[3:].strip()
    if not payload:
        return ()
    if " -> " in payload:
        before, after = payload.split(" -> ", 1)
        return (_strip_git_quotes(before), _strip_git_quotes(after))
    return (_strip_git_quotes(payload),)


def _strip_git_quotes(value: str) -> str:
    return value.strip().strip('"')
