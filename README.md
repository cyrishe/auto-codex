# auto-codex

CodexFlow is a local-first CLI orchestrator for issue-driven development with
Codex CLI.

Current status: local MVP. CodexFlow can claim GitHub or GitLab issues, create an isolated
worktree, collect context, run Developer/Reviewer Codex phases, execute tests,
perform a bounded fix loop, resume interrupted runs, create local commits, and
optionally push/create PRs or MRs/comment when explicitly configured.

Defaults are intentionally conservative: no push, no PR/MR, no merge, and no
issue comment unless configured.

## Development

```bash
uv run python -m codexflow --help
uv run pytest -q
CODEXFLOW_REAL_CODEX=1 uv run pytest tests/test_real_codex_boundary.py -q
CODEXFLOW_REAL_GITHUB=1 CODEXFLOW_GITHUB_REPO=owner/repo uv run pytest tests/test_real_github_boundary.py -q
```

## First Commands

```bash
uv run codexflow init --target /path/to/target-repo
uv run codexflow doctor
uv run codexflow run-next
uv run codexflow resume <run_id>
uv run codexflow status
```

## Recommended Inputs

- Write issues with background, goal, non-goals, acceptance criteria, affected
  modules, evaluation command, and constraints.
- Add an `AGENTS.md` to the target repo for project rules.
- Keep evaluation commands deterministic, for example `pytest -q`.

Templates are available in `examples/`:

- `codexflow_task.md`: GitHub issue template.
- `AGENTS.md`: target-repo coding rules template.
- `review_evaluation_template.md`: review and evaluation criteria template.
- `codexflow_gitlab.yaml`: GitLab `.codexflow.yaml` template.

## Issue Providers

GitHub is the default provider and uses `gh`:

```yaml
issues:
  provider: "github"
  repo: "OWNER/ISSUE_REPO"
```

Self-hosted GitLab uses the GitLab API. Put the token in an environment variable,
not in `.codexflow.yaml`:

```bash
export GITLAB_TOKEN="..."
```

```yaml
issues:
  provider: "gitlab"
  repo: "che/stock_agent"
  host: "gitlab.kingdomai.com"
  token_env: "GITLAB_TOKEN"
  ready_label: "codex:ready"
  working_label: "codex:working"
  review_label: "codex:review"
  blocked_label: "codex:blocked"
```

`issues.repo` may also be a full GitLab project URL, for example
`https://gitlab.kingdomai.com/che/stock_agent/-/tree/V2.0`.

To add another issue platform such as Codeup, implement
`codexflow.issue_provider.IssueClient`, add the provider name to
`IssueProviderName`, route it from `create_issue_client`, and add provider checks
in `Doctor`. The pipeline does not need platform-specific changes.

## GitLab Start Order

1. Clone or update the target repo:

```bash
git clone --branch V2.0 git@gitlab.kingdomai.com:che/stock_agent.git /path/to/stock_agent
```

2. Copy the GitLab config template:

```bash
cp examples/codexflow_gitlab.yaml .codexflow.yaml
```

3. Edit `.codexflow.yaml`:

```yaml
target:
  path: "/path/to/stock_agent"
  base_branch: "V2.0"
issues:
  provider: "gitlab"
  repo: "che/stock_agent"
  host: "gitlab.kingdomai.com"
tests:
  command: "pytest -q"
```

4. Export the GitLab token:

```bash
export GITLAB_TOKEN="..."
```

5. Add `codex:ready` to one GitLab issue.

6. Run checks:

```bash
uv run codexflow doctor
```

7. Run one issue:

```bash
uv run codexflow run-issue <issue-iid>
```

After one issue works, use:

```bash
uv run codexflow run-next
uv run codexflow watch --interval 60
```

## Real GitHub Verification

Phase 3 requires GitHub CLI authentication:

```bash
gh auth login
CODEXFLOW_REAL_GITHUB=1 CODEXFLOW_GITHUB_REPO=owner/repo uv run pytest tests/test_real_github_boundary.py -q
```

The opt-in test creates a temporary issue in the target repo, applies
`codex:ready`, runs the real GitHub label flow, verifies the issue reaches
`codex:review`, and closes the temporary issue.
