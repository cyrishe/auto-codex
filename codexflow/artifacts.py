from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


def generate_run_id(issue_number: int | None = None, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S")
    if issue_number is None:
        return timestamp
    return f"{timestamp}-issue-{issue_number}"


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "artifact"


class ArtifactStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir

    def ensure_base_dirs(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / safe_slug(run_id)

    def create_run_dir(self, run_id: str, *, meta: dict[str, Any] | None = None) -> Path:
        path = self.run_dir(run_id)
        if path.exists():
            raise FileExistsError(f"Run directory already exists: {path}")
        path.mkdir(parents=True)
        self.write_json(run_id, "meta.json", meta or {"run_id": run_id})
        return path

    def write_text(self, run_id: str, relative_path: str, content: str) -> Path:
        path = self.run_dir(run_id) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, run_id: str, relative_path: str, payload: dict[str, Any]) -> Path:
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        return self.write_text(run_id, relative_path, content)

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
