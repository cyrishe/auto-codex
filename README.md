# auto-codex

CodexFlow is a local-first CLI orchestrator for GitHub Issue driven development
with Codex CLI.

Current status: local MVP. CodexFlow can claim GitHub issues, create an isolated
worktree, collect context, run Developer/Reviewer Codex phases, execute tests,
perform a bounded fix loop, resume interrupted runs, create local commits, and
optionally push/create PRs/comment when explicitly configured.

Defaults are intentionally conservative: no push, no PR, no merge, and no issue
comment unless configured.

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

## Real GitHub Verification

Phase 3 requires GitHub CLI authentication:

```bash
gh auth login
CODEXFLOW_REAL_GITHUB=1 CODEXFLOW_GITHUB_REPO=owner/repo uv run pytest tests/test_real_github_boundary.py -q
```

The opt-in test creates a temporary issue in the target repo, applies
`codex:ready`, runs the real GitHub label flow, verifies the issue reaches
`codex:review`, and closes the temporary issue.
