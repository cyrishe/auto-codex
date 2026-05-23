# Review and Evaluation Template

> 使用方式：把本模板复制到目标仓库，例如 `docs/codexflow_review.md`，或合并进 `AGENTS.md`。它定义“什么算完成”和“review 怎么判断”。

## Completion Definition

一个 issue 只有同时满足以下条件，才算完成：

- Issue 中的所有验收标准都已满足。
- 实现没有超出 issue 的非目标范围。
- 必要测试已新增或更新。
- 配置的评估命令已执行并通过。
- 没有修改敏感文件、生产配置、无关模块或生成产物。
- 本地 commit 已生成，commit 内容可以被用户审查。

## Required Evaluation

默认评估命令：

```bash
pytest -q
```

项目可以按需要替换为更完整的命令：

```bash
# example
ruff check .
mypy .
pytest -q
```

## Pass Criteria

以下情况可以判定为通过：

- 所有必需测试通过。
- 新增或修改的行为有测试覆盖，或者 issue 明确说明不需要自动化测试。
- Review 没有发现 correctness、safety、compatibility 或 scope 问题。
- 用户可以通过 commit、diff 和 run artifacts 审查完整过程。

## Fail Criteria

以下情况必须判定为失败或需要修复：

- 必需测试失败。
- 实现遗漏验收标准。
- 修改了非目标范围内的行为。
- 引入不必要依赖、全局重构或格式化噪音。
- 破坏公开接口、配置兼容性或数据兼容性。
- 触碰敏感文件、生产配置、secret、token、证书或私有凭据。

## Blocked Criteria

以下情况应该标记为 blocked，而不是继续猜测实现：

- Issue 缺少关键需求，无法判断正确行为。
- 必需的环境、权限、数据、服务或依赖不可用。
- 评估命令本身无法运行，且无法在本地修复。
- 验收标准互相矛盾。
- 实现会要求超出 issue 授权范围的产品决策。

## Review Checklist

- [ ] 是否满足 issue 的目标和验收标准。
- [ ] 是否没有进入非目标范围。
- [ ] 是否有必要的测试。
- [ ] 是否通过配置的评估命令。
- [ ] 是否保持已有接口和行为兼容。
- [ ] 是否没有引入敏感信息或修改敏感文件。
- [ ] 是否没有不必要的新依赖。
- [ ] 是否没有无关重构、格式化或生成文件。
- [ ] commit message 是否清楚说明完成的行为。

## Reviewer Output Guidance

Review 结论应该明确属于以下之一：

- `pass`：可以交给用户审查和后续 push/PR。
- `needs_changes`：实现方向正确，但必须先修复具体问题。
- `blocked`：需要用户补充需求、权限、环境或产品决策。

Review 反馈应包含：

- 结论：
- 关键问题：
- 必须修复项：
- 可选建议：
- 已运行的评估命令：
- 剩余风险：
