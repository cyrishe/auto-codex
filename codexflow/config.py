from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
import yaml


SandboxName = Literal["read-only", "workspace-write", "danger-full-access"]


class TargetConfig(BaseModel):
    path: Path = Path(".")
    github_repo: str | None = None
    base_branch: str = "main"


class StorageConfig(BaseModel):
    runs_dir: Path = Path(".codexflow/runs")
    db_path: Path = Path(".codexflow/codexflow.db")
    worktree_dir: Path = Path(".codexflow/worktrees")


class GitHubConfig(BaseModel):
    enabled: bool = True
    ready_label: str = "codex:ready"
    working_label: str = "codex:working"
    review_label: str = "codex:review"
    blocked_label: str = "codex:blocked"


class WorktreeConfig(BaseModel):
    enabled: bool = True
    cleanup_on_success: bool = False


class CodexConfig(BaseModel):
    developer_sandbox: SandboxName = "workspace-write"
    reviewer_sandbox: SandboxName = "read-only"
    max_fix_rounds: int = 2
    design_timeout_seconds: int = 900
    review_timeout_seconds: int = 600
    implement_timeout_seconds: int = 1800
    extra_args: list[str] = Field(default_factory=list)

    @field_validator("max_fix_rounds")
    @classmethod
    def validate_max_fix_rounds(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_fix_rounds must be >= 0")
        return value

    @field_validator("design_timeout_seconds", "review_timeout_seconds", "implement_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("codex timeouts must be > 0")
        return value


class ContextConfig(BaseModel):
    max_context_chars: int = 120_000
    include_recent_commits: int = 30
    include_issue_comments: bool = True
    include_related_code: bool = True
    related_code_max_files: int = 5
    related_code_max_chars: int = 20_000
    include_docs_glob: list[str] = Field(default_factory=lambda: ["docs/**/*.md", "*.md"])
    exclude: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".codexflow",
            "node_modules",
            ".venv",
            "dist",
            "build",
        ]
    )

    @field_validator("max_context_chars")
    @classmethod
    def validate_max_context_chars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_context_chars must be > 0")
        return value

    @field_validator("include_recent_commits")
    @classmethod
    def validate_recent_commits(cls, value: int) -> int:
        if value < 0:
            raise ValueError("include_recent_commits must be >= 0")
        return value

    @field_validator("related_code_max_files", "related_code_max_chars")
    @classmethod
    def validate_related_code_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("related code limits must be > 0")
        return value


class TestConfig(BaseModel):
    command: str | None = "pytest -q"
    timeout_seconds: int = 600
    required: bool = True
    fail_on_failure: bool = True
    allow_skipped: bool = False

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_seconds must be > 0")
        return value


class CommitConfig(BaseModel):
    auto_commit: bool = True
    auto_push: bool = False
    create_pr: bool = False
    comment_on_issue: bool = False
    dry_run: bool = False
    push_remote: str = "origin"


class SafetyConfig(BaseModel):
    fail_on_dirty_tree: bool = True
    fail_on_protected_path_change: bool = True
    protected_paths: list[str] = Field(
        default_factory=lambda: [
            ".env",
            ".env.*",
            "**/*secret*",
            "**/*token*",
            "prod.yaml",
            "production.yaml",
        ]
    )


class CodexFlowConfig(BaseModel):
    target: TargetConfig = Field(default_factory=TargetConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    worktree: WorktreeConfig = Field(default_factory=WorktreeConfig)
    codex: CodexConfig = Field(default_factory=CodexConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    tests: TestConfig = Field(default_factory=TestConfig)
    commit: CommitConfig = Field(default_factory=CommitConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)


DEFAULT_CONFIG_TEMPLATE = """target:
  path: "{target_path}"
  github_repo: null
  base_branch: "main"

storage:
  runs_dir: ".codexflow/runs"
  db_path: ".codexflow/codexflow.db"
  worktree_dir: ".codexflow/worktrees"

github:
  enabled: true
  ready_label: "codex:ready"
  working_label: "codex:working"
  review_label: "codex:review"
  blocked_label: "codex:blocked"

worktree:
  enabled: true
  cleanup_on_success: false

codex:
  developer_sandbox: "workspace-write"
  reviewer_sandbox: "read-only"
  max_fix_rounds: 2
  design_timeout_seconds: 900
  review_timeout_seconds: 600
  implement_timeout_seconds: 1800
  extra_args: []

context:
  max_context_chars: 120000
  include_recent_commits: 30
  include_issue_comments: true
  include_related_code: true
  related_code_max_files: 5
  related_code_max_chars: 20000
  include_docs_glob:
    - "docs/**/*.md"
    - "*.md"
  exclude:
    - ".git"
    - ".codexflow"
    - "node_modules"
    - ".venv"
    - "dist"
    - "build"

tests:
  command: "pytest -q"
  timeout_seconds: 600
  required: true
  fail_on_failure: true
  allow_skipped: false

commit:
  auto_commit: true
  auto_push: false
  create_pr: false
  comment_on_issue: false
  dry_run: false
  push_remote: "origin"

safety:
  fail_on_dirty_tree: true
  fail_on_protected_path_change: true
  protected_paths:
    - ".env"
    - ".env.*"
    - "**/*secret*"
    - "**/*token*"
    - "prod.yaml"
    - "production.yaml"
"""


def _resolve_path(path: Path, base: Path) -> Path:
    if path.is_absolute():
        return path
    return (base / path).resolve()


def load_config(
    config_path: Path = Path(".codexflow.yaml"),
    *,
    target_override: Path | None = None,
) -> CodexFlowConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = CodexFlowConfig.model_validate(data)

    config_dir = config_path.resolve().parent
    config.target.path = _resolve_path(config.target.path, config_dir)
    if target_override is not None:
        config.target.path = target_override.resolve()

    target_root = config.target.path
    config.storage.runs_dir = _resolve_path(config.storage.runs_dir, target_root)
    config.storage.db_path = _resolve_path(config.storage.db_path, target_root)
    config.storage.worktree_dir = _resolve_path(config.storage.worktree_dir, target_root)
    return config


def write_default_config(
    config_path: Path = Path(".codexflow.yaml"),
    *,
    target_path: Path = Path("."),
    force: bool = False,
) -> Path:
    if config_path.exists() and not force:
        raise FileExistsError(f"Config file already exists: {config_path}")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    target_value = str(target_path)
    config_path.write_text(
        DEFAULT_CONFIG_TEMPLATE.format(target_path=target_value),
        encoding="utf-8",
    )
    return config_path
