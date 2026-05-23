from pathlib import Path

from codexflow.command import CommandRunner
from codexflow.gitops import GitOps, matches_any


def init_repo(path: Path) -> Path:
    path.mkdir()
    runner = CommandRunner()
    assert runner.run(["git", "init"], cwd=path).ok
    assert runner.run(["git", "config", "user.email", "codexflow@example.com"], cwd=path).ok
    assert runner.run(["git", "config", "user.name", "CodexFlow Tests"], cwd=path).ok
    (path / "README.md").write_text("# test\n", encoding="utf-8")
    assert runner.run(["git", "add", "README.md"], cwd=path).ok
    assert runner.run(["git", "commit", "-m", "initial"], cwd=path).ok
    assert runner.run(["git", "branch", "-M", "main"], cwd=path).ok
    return path


def test_gitops_repo_branch_clean_and_sha(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    git = GitOps(repo)

    assert git.is_git_repo()
    assert git.current_branch() == "main"
    assert len(git.current_sha()) == 40
    assert git.branch_exists("main")
    assert git.is_clean()


def test_gitops_is_clean_includes_untracked_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    git = GitOps(repo)

    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

    assert not git.is_clean()


def test_gitops_is_clean_can_ignore_tool_metadata(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    git = GitOps(repo)

    locks = repo / ".codexflow" / "locks"
    locks.mkdir(parents=True)
    (locks / "global.lock").write_text("pid=1\n", encoding="utf-8")

    assert git.is_clean(ignored_patterns=[".codexflow/**"])


def test_gitops_changed_files_diff_and_protected_paths(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    git = GitOps(repo)
    (repo / ".env").write_text("SECRET=value\n", encoding="utf-8")
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")

    changed = git.changed_files()
    diff_path = git.save_diff(tmp_path / "run" / "diff.patch")

    assert ".env" in changed
    assert "README.md" in changed
    assert "changed" in diff_path.read_text(encoding="utf-8")
    assert git.protected_path_changes([".env", "**/*secret*"]) == [".env"]


def test_gitops_create_branch_and_worktree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    git = GitOps(repo)

    git.create_branch("codex/issue-1", "main")
    assert git.current_branch() == "codex/issue-1"

    assert CommandRunner().run(["git", "switch", "main"], cwd=repo).ok
    worktree = git.create_worktree(
        path=tmp_path / "worktrees" / "issue-2",
        branch="codex/issue-2",
        base_ref="main",
    )

    assert worktree.path.exists()
    assert (worktree.path / "README.md").exists()
    assert GitOps(worktree.path).current_branch() == "codex/issue-2"


def test_gitops_push_branch_to_remote(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    runner = CommandRunner()
    assert runner.run(["git", "init", "--bare", str(remote)]).ok
    assert runner.run(["git", "remote", "add", "origin", str(remote)], cwd=repo).ok
    git = GitOps(repo)

    git.push_branch(remote="origin", branch="codex/issue-1")

    assert runner.run(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/codex/issue-1"]).ok


def test_matches_any_supports_globs() -> None:
    assert matches_any(".env", [".env"])
    assert matches_any("config/my-token.txt", ["**/*token*"])
    assert not matches_any("src/app.py", ["**/*token*"])
