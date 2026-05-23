# CodexFlow TODO

本文用于跟踪 CodexFlow 从当前线性 MVP 到可持续执行流程的主线进度。

原则：

- 先验证主路径，再增加循环、恢复和后台化。
- 默认只本地 commit，不自动 push、不自动 PR、不自动 merge。
- 用户负责 issue 质量、验收标准、项目规则和最终批准。
- CodexFlow 负责按流程执行、记录、评审、测试、生成本地可审查结果。
- 不过度设计；每一步都围绕核心链路推进。

## 当前状态

- [x] 基础 CLI：`init`、`doctor`、`status`、`show-run`
- [x] Issue 执行入口：`run-issue`、`run-next`、`run-all`
- [x] 配置加载与默认 `.codexflow.yaml`
- [x] SQLite run store
- [x] artifact 目录与文件记录
- [x] GitHub issue/label 基础封装
- [x] Git branch/worktree/diff/commit 基础封装
- [x] lock 基础能力
- [x] context 采集
- [x] secret 路径过滤
- [x] prompt 渲染
- [x] Codex subprocess wrapper
- [x] test runner
- [x] review JSON 解析
- [x] commit message 生成
- [x] 线性 `run-issue` 主流程
- [x] 测试失败策略配置
- [x] Codex 阶段超时配置
- [ ] 真实端到端验证
- [x] fix loop
- [x] resume
- [x] watch
- [x] push / PR 闭环

## Phase 1: 主路径集成验证

目标：证明一个 issue 可以稳定走完 `ready -> design -> review -> implement -> test -> code review -> local commit`。

- [x] 新建可复现 toy repo fixture
- [x] 准备最小 issue：例如 `Add multiply(a, b)`
- [x] 使用 fake GitHubClient 返回固定 issue
- [x] 使用 fake CodexRunner 输出固定 design / review / implementation
- [x] 使用真实 GitOps 创建 worktree、保存 diff、生成 commit
- [x] 验证 run DB 最终状态为 `DONE`
- [x] 验证 `meta.json` 记录完整
- [x] 验证关键 artifacts 都存在
- [x] 验证 diff 包含预期代码改动
- [x] 验证测试日志为 pass
- [x] 验证 commit message 包含 issue、run id、test status、review summary
- [x] 验证 fake GitHub label 流转：ready -> working -> review
- [x] 写入可复现集成测试

## Phase 2: 真实 Codex 边界验证

目标：验证 prompt、schema、sandbox 和真实 `codex exec` 输出是否能支撑主路径。

验证记录：

- 2026-05-23：真实 `codex exec` toy repo 跑通。发现并修正 JSON Schema strictness 问题：object schema 需要显式 `additionalProperties: false`。

- [x] 复用 toy repo
- [x] GitHub 仍使用 fake boundary
- [x] CodexRunner 使用真实 `codex exec`
- [x] 运行一个最小 issue
- [x] 检查 design JSON 是否稳定符合 schema
- [x] 检查 review JSON 是否稳定符合 schema
- [x] 检查 implementation 是否真实修改代码
- [x] 检查测试是否通过
- [x] 记录 prompt/schema 需要调整的问题
- [x] 不在此阶段引入 fix loop

## Phase 3: 真实 GitHub 最小链路

目标：验证真实 GitHub issue 和 label 流转。

当前阻塞：

- 2026-05-23：本机 `gh auth status` 显示未登录。需要先完成 `gh auth login` 或提供 `GH_TOKEN`，并确认用于验证的真实测试 repo。
- 已准备 opt-in 验证命令：

```bash
CODEXFLOW_REAL_GITHUB=1 CODEXFLOW_GITHUB_REPO=owner/repo uv run pytest tests/test_real_github_boundary.py -q
```

该测试会在指定 repo 中创建临时 issue，验证 `ready -> working -> review` label 流转，然后关闭临时 issue。

- [ ] 准备真实测试 repo 或用户指定目标 repo
- [ ] 创建清晰的最小 GitHub issue
- [ ] 添加 `codex:ready` label
- [ ] 运行 `codexflow run-issue <issue_number>`
- [ ] 验证 issue 被 claim
- [ ] 验证成功后进入 review label
- [ ] 验证 blocked/failed 时进入 blocked label
- [ ] 验证本地 branch/worktree/commit/artifact 都可审查
- [ ] 记录真实链路中的配置和权限要求

## Phase 4: 最小 fix loop

目标：review 或测试失败时，允许有限轮自动修复，而不是立即 blocked。

验证记录：

- 2026-05-23：单元测试覆盖测试失败后修复成功、code review `needs_fix` 后修复成功、超出修复轮数后 blocked。
- 2026-05-23：真实 `codex exec` toy repo 边界在当前 pipeline 下通过，最终 code review 为 pass。

- [x] 定义 code fix loop 的最小状态流
- [x] 测试失败进入 fix prompt
- [x] code review `needs_fix` 进入 fix prompt
- [x] 每轮保存独立 artifact，不覆盖旧文件
- [x] fix prompt 包含 blocking issues、suggested_fix、当前 diff、测试日志
- [x] 限制最大修复轮数
- [x] 超过最大轮数后 blocked
- [x] 记录每轮 review verdict
- [x] 增加测试失败后修复成功的集成测试
- [x] 增加 review needs_fix 后修复成功的集成测试
- [x] 暂缓复杂 design fix loop，除非真实验证显示必要

## Phase 5: resume

目标：中断后可以从关键阶段继续，避免重复跑完整 issue。

验证记录：

- 2026-05-23：`tests/test_resume.py` 覆盖所有第一版恢复点，并验证 worktree/base 信息校验、artifact 防覆盖和最终 commit。
- 2026-05-23：CLI `resume <run_id>` 已接入 Pipeline。

- [x] 明确第一版支持的恢复点
- [x] 从 `CONTEXT_COLLECTED` 恢复到 design
- [x] 从 `DEV_DESIGN_DONE` 恢复到 design review
- [x] 从 `DESIGN_REVIEWED` 恢复到 implement
- [x] 从 `IMPLEMENTED` 恢复到 diff/test
- [x] 从 `TESTED` 恢复到 code review
- [x] 从 `COMMIT_READY` 恢复到 commit
- [x] 校验 worktree_path、work_branch、base_sha
- [x] 避免覆盖已有 artifact
- [x] 增加 `codexflow resume <run_id>`
- [x] 增加中断恢复测试

## Phase 6: push / PR 闭环

目标：在用户显式开启时，把本地结果发布到 GitHub 协作流。

验证记录：

- 2026-05-23：默认仍不 push、不 PR、不评论。
- 2026-05-23：使用本地 bare repo 验证 push branch；使用 fake GitHub 验证 create PR、issue comment、blocked comment；dry-run 不执行外部动作。

- [x] 保持默认 `auto_push=false`
- [x] 保持默认 `create_pr=false`
- [x] 实现 push branch
- [x] 实现 create PR
- [x] PR body 写入 run summary
- [x] issue comment 写入 run 结果
- [x] blocked 时 comment blocking reason
- [x] 支持 dry-run
- [x] 增加 fake/真实边界测试

## Phase 7: watch

目标：持续轮询 ready issues，自动按顺序执行。

验证记录：

- 2026-05-23：`watch` 复用 `run-next` 串行处理，支持 `--limit`，空队列 sleep，`KeyboardInterrupt` graceful shutdown。
- 2026-05-23：LockManager 自动清理 stale lock；`unlock --stale` 可手动清理。

- [x] 在 resume 可用后再实现 watch
- [x] 实现循环 `run-next`
- [x] 空队列 sleep
- [x] graceful shutdown
- [x] 处理 stale lock
- [x] 处理异常重试策略
- [x] 避免重复领取同一 issue
- [x] 输出清晰运行日志
- [x] 增加 watch smoke test

## Phase 8: 必要强化

只做和主线稳定性直接相关的增强。

验证记录：

- 2026-05-23：stale lock 自动清理、`unlock --stale` 和 doctor stale lock 提示已实现。
- 2026-05-23：context、diff、test log、Codex output、commit message 等 artifact 增加内容级 redaction。
- 2026-05-23：新增 issue template、AGENTS 示例、issue 相关代码召回、run summary 和 README 使用说明。

- [x] stale lock 检测与清理命令
- [x] doctor 提示 stale lock
- [x] 内容级 secret redaction
- [x] test log / diff / Codex output 的敏感信息过滤
- [x] issue template
- [x] AGENTS.md 示例
- [x] issue 相关代码轻量召回
- [x] run summary 报告
- [x] README 使用说明更新
