# Project Rules for CodexFlow

> 使用方式：把本文件复制到目标代码仓库根目录，文件名保持为 `AGENTS.md`。这是 CodexFlow 开发和 review 时读取的项目级规则。

## Project Structure

- Source code lives in `src/`. Replace this with the real source paths.
- Tests live in `tests/`. Replace this with the real test paths.
- Documentation lives in `docs/`. Replace this with the real docs paths.
- Do not modify generated, vendored, build, cache, or migration files unless the issue explicitly requires it.

## Development Commands

```bash
pytest -q
```

Add project-specific commands here:

```bash
# lint command
# type check command
# focused test command
```

## Coding Principles

- Keep changes scoped to the current issue.
- Prefer existing project patterns over new abstractions.
- Preserve public APIs and data contracts unless the issue explicitly requests a change.
- Make the smallest complete change that satisfies the acceptance criteria.
- Avoid unrelated refactors, dependency upgrades, formatting churn, and broad rewrites.
- Add comments only when they clarify non-obvious decisions.
- Do not hide errors silently. Prefer explicit errors, clear fallbacks, or blocked status when requirements are unclear.

## Coding Rules

- Keep changes scoped to the current issue.
- Add or update tests for changed behavior.
- Keep tests close to the changed behavior.
- Do not commit generated files, caches, local virtualenvs, build outputs, or local editor files.
- Do not introduce a new dependency unless the issue requires it and the reason is documented.
- Do not change unrelated files just to satisfy style preferences.

## Review Rules

- Review must check correctness, regression risk, test coverage, compatibility, security, and maintainability.
- Review should request changes for missing acceptance criteria, failing tests, unsafe behavior, or broad unrelated changes.
- Review should block when the issue is ambiguous enough that implementation would require guessing product behavior.
- Review should not require cosmetic changes unless they affect readability, consistency, or user-facing quality.

## Evaluation Rules

- The configured evaluation command must be run before completion.
- If tests fail, fix the code or mark the issue blocked with the failing command and error summary.
- If tests are skipped, explain why. Skipped tests do not count as success unless the project explicitly allows it.
- Do not mark the issue ready for review if required evaluation cannot be executed.

## Safety Boundaries

- Do not read or modify `.env`, token, secret, credential, certificate, or production config files.
- Do not run `git push`, create PRs, or merge unless CodexFlow configuration explicitly enables publishing.
- Do not skip configured evaluation commands.
- Do not make destructive git operations such as hard reset or force push.
- Do not access external systems unless the issue or project rules explicitly allow it.

## Commit Rules

- Commit message should describe the completed issue behavior, not the implementation process.
- Commit only the files needed for this issue.
- The final local commit should leave the worktree clean except for CodexFlow artifacts if configured to keep them.
