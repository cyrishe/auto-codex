from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath
import re


DEFAULT_SECRET_PATTERNS = [
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/*secret*",
    "**/*token*",
    "**/*credential*",
    "**/*private*key*",
    "**/*.pem",
    "**/*.p12",
    "**/*.pfx",
]

REDACTION_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?im)^(\s*[A-Za-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)"
        r"[A-Za-z0-9_.-]*\s*[:=]\s*)(.+)$"
    ),
]


@dataclass(frozen=True)
class FilterDecision:
    path: str
    included: bool
    reason: str | None = None


class SecretFilter:
    def __init__(
        self,
        *,
        exclude_patterns: list[str] | None = None,
        protected_patterns: list[str] | None = None,
        secret_patterns: list[str] | None = None,
    ) -> None:
        self.exclude_patterns = exclude_patterns or []
        self.protected_patterns = protected_patterns or []
        self.secret_patterns = secret_patterns or DEFAULT_SECRET_PATTERNS

    def should_include(self, path: str) -> FilterDecision:
        normalized = normalize_path(path)
        if matches_any(normalized, self.exclude_patterns):
            return FilterDecision(path=normalized, included=False, reason="excluded_by_config")
        if self.is_secret_path(normalized):
            return FilterDecision(path=normalized, included=False, reason="secret_path")
        return FilterDecision(path=normalized, included=True)

    def is_secret_path(self, path: str) -> bool:
        return matches_any(path, self.secret_patterns)

    def is_protected_path(self, path: str) -> bool:
        return matches_any(path, self.protected_patterns)

    def filter_paths(self, paths: list[str]) -> tuple[list[str], list[FilterDecision]]:
        included: list[str] = []
        excluded: list[FilterDecision] = []
        for path in paths:
            decision = self.should_include(path)
            if decision.included:
                included.append(decision.path)
            else:
                excluded.append(decision)
        return included, excluded

    def redact_text(self, content: str) -> str:
        redacted = content
        for pattern in REDACTION_PATTERNS:
            if pattern.flags & re.MULTILINE and pattern.pattern.startswith("(?im)^("):
                redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
            else:
                redacted = pattern.sub("[REDACTED]", redacted)
        return redacted


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    posix_path = PurePosixPath(normalized)
    return any(
        fnmatch(normalized, pattern)
        or posix_path.match(pattern)
        or fnmatch(posix_path.name, pattern)
        for pattern in patterns
    )
