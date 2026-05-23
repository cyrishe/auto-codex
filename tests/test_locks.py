from pathlib import Path

import pytest

from codexflow.locks import LockError, LockManager


def test_lock_manager_acquires_and_releases(tmp_path: Path) -> None:
    manager = LockManager(tmp_path / "locks")

    with manager.acquire("issue-123") as handle:
        assert handle.path.exists()
        with pytest.raises(LockError):
            manager.acquire("issue-123")

    assert not handle.path.exists()


def test_lock_manager_sanitizes_lock_name(tmp_path: Path) -> None:
    handle = LockManager(tmp_path / "locks").acquire("owner/repo issue #1")

    assert handle.path.name == "owner-repo-issue--1.lock"


def test_lock_manager_clears_stale_locks(tmp_path: Path) -> None:
    manager = LockManager(tmp_path / "locks")
    stale = tmp_path / "locks" / "issue-1.lock"
    stale.parent.mkdir()
    stale.write_text("pid=999999999\ncreated_at=old\n", encoding="utf-8")

    assert manager.stale_locks() == [stale]
    handle = manager.acquire("issue-1")

    assert handle.path.exists()
    assert "pid=999999999" not in handle.path.read_text(encoding="utf-8")
