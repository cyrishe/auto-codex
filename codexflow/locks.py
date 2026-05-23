from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path


class LockError(RuntimeError):
    pass


@dataclass(frozen=True)
class LockHandle:
    path: Path

    def release(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class LockManager:
    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = lock_dir

    def acquire(self, name: str) -> LockHandle:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        path = self.lock_dir / _lock_name(name)
        content = f"pid={os.getpid()}\ncreated_at={datetime.now(timezone.utc).isoformat()}\n"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(path, flags)
        except FileExistsError as exc:
            if is_stale_lock(path):
                path.unlink(missing_ok=True)
                return self.acquire(name)
            raise LockError(f"Lock already exists: {path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        return LockHandle(path=path)

    def stale_locks(self) -> list[Path]:
        if not self.lock_dir.exists():
            return []
        return sorted(path for path in self.lock_dir.glob("*.lock") if is_stale_lock(path))

    def clear_stale(self) -> list[Path]:
        removed = self.stale_locks()
        for path in removed:
            path.unlink(missing_ok=True)
        return removed


def _lock_name(name: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in name)
    return f"{safe}.lock"


def is_stale_lock(path: Path) -> bool:
    pid = _read_pid(path)
    if pid is None:
        return True
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _read_pid(path: Path) -> int | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("pid="):
                value = line.split("=", 1)[1].strip()
                return int(value) if value else None
    except (FileNotFoundError, ValueError, OSError):
        return None
    return None
