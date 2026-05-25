from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GitHubLabel:
    name: str


@dataclass(frozen=True)
class GitHubComment:
    author: str | None
    body: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: tuple[GitHubLabel, ...] = field(default_factory=tuple)
    url: str | None = None
    state: str | None = None
    author: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    comments: tuple[GitHubComment, ...] = field(default_factory=tuple)

    @classmethod
    def from_gh_json(cls, payload: dict) -> "GitHubIssue":
        labels = tuple(GitHubLabel(name=item["name"]) for item in payload.get("labels", []) if "name" in item)
        comments = tuple(_parse_comment(item) for item in payload.get("comments", []))
        author = payload.get("author")
        if isinstance(author, dict):
            author = author.get("login")
        return cls(
            number=int(payload["number"]),
            title=payload.get("title") or "",
            body=payload.get("body") or "",
            labels=labels,
            url=payload.get("url"),
            state=payload.get("state"),
            author=author,
            created_at=payload.get("createdAt"),
            updated_at=payload.get("updatedAt"),
            comments=comments,
        )

    def has_label(self, name: str) -> bool:
        return any(label.name == name for label in self.labels)

    @classmethod
    def from_gitlab_json(cls, payload: dict, *, comments: tuple[GitHubComment, ...] = ()) -> "GitHubIssue":
        labels = tuple(GitHubLabel(name=str(item)) for item in payload.get("labels", []))
        author = payload.get("author")
        if isinstance(author, dict):
            author = author.get("username") or author.get("name")
        return cls(
            number=int(payload["iid"]),
            title=payload.get("title") or "",
            body=payload.get("description") or "",
            labels=labels,
            url=payload.get("web_url"),
            state=payload.get("state"),
            author=author,
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            comments=comments,
        )


@dataclass(frozen=True)
class PullRequestInfo:
    url: str
    number: int | None = None


IssueLabel = GitHubLabel
IssueComment = GitHubComment
Issue = GitHubIssue


def _parse_comment(payload: dict) -> GitHubComment:
    author = payload.get("author")
    if isinstance(author, dict):
        author = author.get("login")
    return GitHubComment(
        author=author,
        body=payload.get("body") or "",
        created_at=payload.get("createdAt"),
        updated_at=payload.get("updatedAt"),
    )
