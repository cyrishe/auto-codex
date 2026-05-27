from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from .models import GitHubComment, GitHubIssue, IssueCreateInfo, PullRequestInfo


class GitLabClientError(RuntimeError):
    pass


RequestFunc = Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], Any]


class GitLabClient:
    def __init__(
        self,
        *,
        repo: str,
        host: str | None = None,
        api_url: str | None = None,
        token_env: str = "GITLAB_TOKEN",
        token: str | None = None,
        ready_label: str = "codex:ready",
        working_label: str = "codex:working",
        review_label: str = "codex:review",
        blocked_label: str = "codex:blocked",
        requester: RequestFunc | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        normalized_repo, inferred_host = _normalize_repo_and_host(repo, host)
        self.repo = normalized_repo
        self.host = inferred_host
        self.api_url = (api_url or _api_url_from_host(inferred_host)).rstrip("/")
        self.token_env = token_env
        self.token = token
        self.ready_label = ready_label
        self.working_label = working_label
        self.review_label = review_label
        self.blocked_label = blocked_label
        self.requester = requester
        self.timeout_seconds = timeout_seconds

    def get_ready_issue(self) -> GitHubIssue | None:
        payload = self._request_json(
            "GET",
            f"projects/{self._project_id()}/issues",
            params={
                "state": "opened",
                "labels": self.ready_label,
                "per_page": 1,
                "order_by": "updated_at",
                "sort": "asc",
            },
        )
        if not payload:
            return None
        return GitHubIssue.from_gitlab_json(payload[0])

    def get_issue(self, number: int, *, include_comments: bool = False) -> GitHubIssue:
        payload = self._request_json("GET", f"projects/{self._project_id()}/issues/{number}")
        comments: tuple[GitHubComment, ...] = ()
        if include_comments:
            comments = self._issue_comments(number)
        return GitHubIssue.from_gitlab_json(payload, comments=comments)

    def update_labels(
        self,
        number: int,
        *,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        data: dict[str, str] = {}
        if add:
            data["add_labels"] = ",".join(add)
        if remove:
            data["remove_labels"] = ",".join(remove)
        if not data:
            return
        self._request_json(
            "PUT",
            f"projects/{self._project_id()}/issues/{number}",
            data=data,
        )

    def claim_issue(self, number: int) -> None:
        self.update_labels(number, add=[self.working_label], remove=[self.ready_label])

    def mark_review(self, number: int) -> None:
        self.update_labels(number, add=[self.review_label], remove=[self.working_label])

    def mark_blocked(self, number: int) -> None:
        self.update_labels(number, add=[self.blocked_label], remove=[self.working_label])

    def restore_ready(self, number: int) -> None:
        self.update_labels(number, add=[self.ready_label], remove=[self.working_label])

    def create_pr(self, *, base: str, head: str, title: str, body_file: str) -> PullRequestInfo:
        body = Path(body_file).read_text(encoding="utf-8")
        payload = self._request_json(
            "POST",
            f"projects/{self._project_id()}/merge_requests",
            data={
                "source_branch": head,
                "target_branch": base,
                "title": title,
                "description": body,
            },
        )
        url = payload.get("web_url") or payload.get("url") or ""
        iid = payload.get("iid")
        return PullRequestInfo(url=url, number=int(iid) if iid is not None else None)

    def comment_issue(self, number: int, *, body_file: str) -> None:
        body = Path(body_file).read_text(encoding="utf-8")
        self._request_json(
            "POST",
            f"projects/{self._project_id()}/issues/{number}/notes",
            data={"body": body},
        )

    def create_issue(self, *, title: str, body_file: str, labels: list[str] | None = None) -> IssueCreateInfo:
        body = Path(body_file).read_text(encoding="utf-8")
        data = {"title": title, "description": body}
        if labels:
            data["labels"] = ",".join(labels)
        payload = self._request_json(
            "POST",
            f"projects/{self._project_id()}/issues",
            data=data,
        )
        url = payload.get("web_url") or payload.get("url") or ""
        iid = payload.get("iid")
        return IssueCreateInfo(url=url, number=int(iid) if iid is not None else None)

    def check_project(self) -> None:
        self._request_json("GET", f"projects/{self._project_id()}")

    def _issue_comments(self, number: int) -> tuple[GitHubComment, ...]:
        payload = self._request_json(
            "GET",
            f"projects/{self._project_id()}/issues/{number}/notes",
            params={"per_page": 100, "order_by": "created_at", "sort": "asc"},
        )
        comments: list[GitHubComment] = []
        for item in payload:
            if item.get("system"):
                continue
            author = item.get("author")
            if isinstance(author, dict):
                author = author.get("username") or author.get("name")
            comments.append(
                GitHubComment(
                    author=author,
                    body=item.get("body") or "",
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                )
            )
        return tuple(comments)

    def _project_id(self) -> str:
        return quote(self.repo, safe="")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        if self.requester:
            return self.requester(method, path, params, data)

        token = self.token or os.environ.get(self.token_env)
        if not token:
            raise GitLabClientError(f"Missing GitLab token. Set ${self.token_env}.")

        query = f"?{urlencode(params, doseq=True)}" if params else ""
        url = f"{self.api_url}/{path.lstrip('/')}{query}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "PRIVATE-TOKEN": token,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise GitLabClientError(f"GitLab API {method} {path} failed: HTTP {exc.code} {details}") from exc
        except URLError as exc:
            raise GitLabClientError(f"GitLab API {method} {path} failed: {exc.reason}") from exc

        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise GitLabClientError(f"GitLab API returned invalid JSON for {method} {path}") from exc


def _normalize_repo_and_host(repo: str, host: str | None) -> tuple[str, str | None]:
    if re.match(r"^https?://", repo):
        parsed = urlparse(repo)
        repo_path = parsed.path.strip("/")
        if "/-/" in repo_path:
            repo_path = repo_path.split("/-/", 1)[0]
        if repo_path.endswith(".git"):
            repo_path = repo_path[:-4]
        return repo_path, host or parsed.netloc
    normalized = repo[:-4] if repo.endswith(".git") else repo
    return normalized.strip("/"), host


def _api_url_from_host(host: str | None) -> str:
    if not host:
        raise GitLabClientError("GitLab provider requires issues.host or issues.api_url.")
    if host.startswith("http://") or host.startswith("https://"):
        return f"{host.rstrip('/')}/api/v4"
    return f"https://{host}/api/v4"
