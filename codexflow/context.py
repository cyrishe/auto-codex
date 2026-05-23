from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from .command import CommandRunner
from .config import ContextConfig
from .models import GitHubIssue
from .secret_filter import FilterDecision, SecretFilter, normalize_path


MANIFEST_FILES = [
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "requirements.txt",
]


@dataclass(frozen=True)
class ContextResult:
    content: str
    included_files: tuple[str, ...] = field(default_factory=tuple)
    excluded_files: tuple[FilterDecision, ...] = field(default_factory=tuple)
    truncated: bool = False


@dataclass(frozen=True)
class ContextSection:
    title: str
    body: str

    def render(self) -> str:
        return f"## {self.title}\n\n{self.body.strip()}\n"


class ContextCollector:
    def __init__(
        self,
        repo_path: Path,
        *,
        config: ContextConfig,
        secret_filter: SecretFilter | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.repo_path = repo_path
        self.config = config
        self.secret_filter = secret_filter or SecretFilter(exclude_patterns=config.exclude)
        self.runner = runner or CommandRunner()

    def collect(self, *, issue: GitHubIssue | None = None) -> ContextResult:
        sections: list[ContextSection] = []
        included_files: list[str] = []
        excluded_files: list[FilterDecision] = []
        seen: set[str] = set()

        if issue is not None:
            sections.append(
                ContextSection(
                    "Issue",
                    self.secret_filter.redact_text(render_issue(issue, include_comments=self.config.include_issue_comments)),
                )
            )

        for relative in ["AGENTS.md", ".codexflow.yaml", "README.md"]:
            self._append_file_section(relative, sections, included_files, excluded_files, seen)

        for relative in MANIFEST_FILES:
            self._append_file_section(relative, sections, included_files, excluded_files, seen)

        for relative in self._doc_paths():
            self._append_file_section(relative, sections, included_files, excluded_files, seen)

        related_code = self._related_code(issue, excluded_files)
        if related_code:
            sections.append(ContextSection("Issue-Related Code", related_code))

        git_log = self._git_log()
        if git_log:
            sections.append(ContextSection("Recent Git Log", git_log))

        tree = self._file_tree(excluded_files)
        if tree:
            sections.append(ContextSection("File Tree Summary", tree))

        content, truncated = enforce_limit(sections, self.config.max_context_chars)
        return ContextResult(
            content=content,
            included_files=tuple(included_files),
            excluded_files=tuple(excluded_files),
            truncated=truncated,
        )

    def _append_file_section(
        self,
        relative: str,
        sections: list[ContextSection],
        included_files: list[str],
        excluded_files: list[FilterDecision],
        seen: set[str],
    ) -> None:
        normalized = normalize_path(relative)
        if normalized in seen:
            return
        seen.add(normalized)
        decision = self.secret_filter.should_include(normalized)
        if not decision.included:
            excluded_files.append(decision)
            return
        path = self.repo_path / normalized
        if not path.is_file():
            return
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            excluded_files.append(FilterDecision(path=normalized, included=False, reason="decode_error"))
            return
        included_files.append(normalized)
        sections.append(ContextSection(f"File: {normalized}", self.secret_filter.redact_text(body)))

    def _doc_paths(self) -> list[str]:
        paths: list[str] = []
        for pattern in self.config.include_docs_glob:
            for path in self.repo_path.glob(pattern):
                if path.is_file():
                    paths.append(normalize_path(str(path.relative_to(self.repo_path))))
        return sorted(set(paths))

    def _git_log(self) -> str:
        if self.config.include_recent_commits <= 0:
            return ""
        result = self.runner.run(
            ["git", "log", "-n", str(self.config.include_recent_commits), "--oneline"],
            cwd=self.repo_path,
            timeout_seconds=30,
        )
        if not result.ok:
            return ""
        return result.stdout.strip()

    def _file_tree(self, excluded_files: list[FilterDecision]) -> str:
        files: list[str] = []
        for path in self.repo_path.rglob("*"):
            if not path.is_file():
                continue
            relative = normalize_path(str(path.relative_to(self.repo_path)))
            decision = self.secret_filter.should_include(relative)
            if not decision.included:
                excluded_files.append(decision)
                continue
            files.append(relative)
        return "\n".join(sorted(files)[:500])

    def _related_code(self, issue: GitHubIssue | None, excluded_files: list[FilterDecision]) -> str:
        if issue is None or not self.config.include_related_code:
            return ""
        tokens = _issue_tokens(issue)
        if not tokens:
            return ""
        snippets: list[str] = []
        used_chars = 0
        for path in sorted(self.repo_path.rglob("*")):
            if len(snippets) >= self.config.related_code_max_files:
                break
            if not path.is_file():
                continue
            relative = normalize_path(str(path.relative_to(self.repo_path)))
            decision = self.secret_filter.should_include(relative)
            if not decision.included:
                excluded_files.append(decision)
                continue
            if _looks_binary_or_generated(relative):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            matches = [
                (index, line)
                for index, line in enumerate(lines, start=1)
                if any(token in line.lower() for token in tokens)
            ]
            if not matches:
                continue
            excerpt_lines: list[str] = []
            for line_number, _line in matches[:8]:
                start = max(1, line_number - 2)
                end = min(len(lines), line_number + 2)
                for current in range(start, end + 1):
                    excerpt_lines.append(f"{current}: {lines[current - 1]}")
            body = self.secret_filter.redact_text("\n".join(dict.fromkeys(excerpt_lines)))
            snippet = f"### {relative}\n\n```text\n{body}\n```"
            if used_chars + len(snippet) > self.config.related_code_max_chars:
                break
            snippets.append(snippet)
            used_chars += len(snippet)
        return "\n\n".join(snippets)


def render_issue(issue: GitHubIssue, *, include_comments: bool) -> str:
    parts = [f"# Issue #{issue.number}: {issue.title}", "", issue.body.strip()]
    if include_comments and issue.comments:
        parts.extend(["", "### Comments"])
        for comment in issue.comments:
            author = comment.author or "unknown"
            parts.append(f"- {author}: {comment.body.strip()}")
    return "\n".join(parts).strip()


def enforce_limit(sections: list[ContextSection], max_chars: int) -> tuple[str, bool]:
    chunks: list[str] = []
    used = 0
    truncated = False
    for section in sections:
        rendered = section.render()
        separator = "\n" if chunks else ""
        required = len(separator) + len(rendered)
        if used + required <= max_chars:
            chunks.append(rendered)
            used += required
            continue
        remaining = max_chars - used - len(separator)
        if remaining > 0:
            chunks.append(separator + rendered[:remaining].rstrip() + "\n\n[TRUNCATED]\n")
        truncated = True
        break
    return "\n".join(chunks).strip() + "\n", truncated


def _issue_tokens(issue: GitHubIssue) -> set[str]:
    text = f"{issue.title}\n{issue.body}".lower()
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "目标",
        "背景",
        "验收标准",
    }
    return {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text) if token not in stop_words}


def _looks_binary_or_generated(path: str) -> bool:
    return path.endswith((".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip")) or "__pycache__/" in path
