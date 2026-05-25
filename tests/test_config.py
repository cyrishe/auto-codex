from pathlib import Path

import pytest

from codexflow.config import load_config, write_default_config


def test_write_and_load_default_config(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    config_path = tmp_path / ".codexflow.yaml"

    write_default_config(config_path, target_path=target)
    config = load_config(config_path)

    assert config.target.path == target.resolve()
    assert config.target.base_branch == "main"
    assert config.issues.provider == "github"
    assert config.issues.enabled is True
    assert config.storage.runs_dir == target / ".codexflow" / "runs"
    assert config.codex.reviewer_sandbox == "read-only"
    assert config.codex.design_timeout_seconds == 900
    assert config.codex.review_timeout_seconds == 600
    assert config.codex.implement_timeout_seconds == 1800
    assert config.tests.fail_on_failure is True
    assert config.tests.allow_skipped is False
    assert config.commit.auto_push is False
    assert config.commit.create_pr is False
    assert config.commit.comment_on_issue is False
    assert config.commit.dry_run is False
    assert config.commit.push_remote == "origin"


def test_legacy_github_config_populates_issue_provider(tmp_path: Path) -> None:
    config_path = tmp_path / ".codexflow.yaml"
    config_path.write_text(
        """
target:
  path: "."
  github_repo: "owner/repo"
  base_branch: "main"
github:
  enabled: false
  ready_label: "ready"
  working_label: "working"
  review_label: "review"
  blocked_label: "blocked"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.issues.repo == "owner/repo"
    assert config.issue_repo == "owner/repo"
    assert config.issue_updates_enabled is False
    assert config.issues.ready_label == "ready"


def test_write_default_config_refuses_overwrite(tmp_path: Path) -> None:
    config_path = tmp_path / ".codexflow.yaml"
    write_default_config(config_path)

    with pytest.raises(FileExistsError):
        write_default_config(config_path)
