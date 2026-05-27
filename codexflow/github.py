from __future__ import annotations

import json
import re

from .command import CommandRunner
from .models import GitHubIssue, IssueCreateInfo, PullRequestInfo


class GitHubClientError(RuntimeError):
    pass


class GitHubClient:
    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        repo: str | None = None,
        ready_label: str = "codex:ready",
        working_label: str = "codex:working",
        review_label: str = "codex:review",
        blocked_label: str = "codex:blocked",
    ) -> None:
        self.runner = runner or CommandRunner()
        self.repo = repo
        self.ready_label = ready_label
        self.working_label = working_label
        self.review_label = review_label
        self.blocked_label = blocked_label

    def get_ready_issue(self) -> GitHubIssue | None:
        command = self._gh_base() + [
            "issue",
            "list",
            "--state",
            "open",
            "--label",
            self.ready_label,
            "--limit",
            "1",
            "--json",
            "number,title,body,labels,url,state,author,createdAt,updatedAt",
        ]
        result = self.runner.run(command, timeout_seconds=30)
        self._raise_on_failure(result.stderr, result.ok)
        payload = json.loads(result.stdout or "[]")
        if not payload:
            return None
        return GitHubIssue.from_gh_json(payload[0])

    def get_issue(self, number: int, *, include_comments: bool = False) -> GitHubIssue:
        fields = "number,title,body,labels,url,state,author,createdAt,updatedAt"
        if include_comments:
            fields += ",comments"
        command = self._gh_base() + ["issue", "view", str(number), "--json", fields]
        result = self.runner.run(command, timeout_seconds=30)
        self._raise_on_failure(result.stderr, result.ok)
        return GitHubIssue.from_gh_json(json.loads(result.stdout))

    def update_labels(
        self,
        number: int,
        *,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        command = self._gh_base() + ["issue", "edit", str(number)]
        for label in remove or []:
            command.extend(["--remove-label", label])
        for label in add or []:
            command.extend(["--add-label", label])
        result = self.runner.run(command, timeout_seconds=30)
        self._raise_on_failure(result.stderr, result.ok)

    def claim_issue(self, number: int) -> None:
        self.update_labels(number, add=[self.working_label], remove=[self.ready_label])

    def mark_review(self, number: int) -> None:
        self.update_labels(number, add=[self.review_label], remove=[self.working_label])

    def mark_blocked(self, number: int) -> None:
        self.update_labels(number, add=[self.blocked_label], remove=[self.working_label])

    def restore_ready(self, number: int) -> None:
        self.update_labels(number, add=[self.ready_label], remove=[self.working_label])

    def create_pr(self, *, base: str, head: str, title: str, body_file: str) -> PullRequestInfo:
        command = self._gh_base() + [
            "pr",
            "create",
            "--base",
            base,
            "--head",
            head,
            "--title",
            title,
            "--body-file",
            body_file,
        ]
        result = self.runner.run(command, timeout_seconds=60)
        self._raise_on_failure(result.stderr, result.ok)
        url = result.stdout.strip().splitlines()[-1]
        match = re.search(r"/pull/(\d+)(?:$|[/?#])", url)
        return PullRequestInfo(url=url, number=int(match.group(1)) if match else None)

    def comment_issue(self, number: int, *, body_file: str) -> None:
        command = self._gh_base() + ["issue", "comment", str(number), "--body-file", body_file]
        result = self.runner.run(command, timeout_seconds=30)
        self._raise_on_failure(result.stderr, result.ok)

    def create_issue(self, *, title: str, body_file: str, labels: list[str] | None = None) -> IssueCreateInfo:
        command = self._gh_base() + ["issue", "create", "--title", title, "--body-file", body_file]
        for label in labels or []:
            command.extend(["--label", label])
        result = self.runner.run(command, timeout_seconds=30)
        self._raise_on_failure(result.stderr, result.ok)
        url = result.stdout.strip().splitlines()[-1]
        match = re.search(r"/issues/(\d+)(?:$|[/?#])", url)
        return IssueCreateInfo(url=url, number=int(match.group(1)) if match else None)

    def _gh_base(self) -> list[str]:
        command = ["gh"]
        if self.repo:
            command.extend(["--repo", self.repo])
        return command

    @staticmethod
    def _raise_on_failure(stderr: str, ok: bool) -> None:
        if not ok:
            raise GitHubClientError(stderr.strip() or "gh command failed")
