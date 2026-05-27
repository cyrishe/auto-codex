# CodexFlow TODO

本文用于跟踪 CodexFlow 从当前线性 MVP 到可持续执行流程的主线进度。

原则：

- 先验证主路径，再增加循环、恢复和后台化。
- 默认只本地 commit，不自动 push、不自动 PR、不自动 merge。
- 用户负责 issue 质量、验收标准、项目规则和最终批准。
- CodexFlow 负责按流程执行、记录、评审、测试、生成本地可审查结果。
- 不过度设计；每一步都围绕核心链路推进。

## 用户需要编辑的输入

这些是用户需要按目标项目实际情况填写或维护的内容：

- 目标 repo 的 issue：使用 `examples/codexflow_task.md`，写清目标、非目标、验收标准、评估方式和约束。
- 目标 repo 的项目规则：把 `examples/AGENTS.md` 复制成目标仓库根目录的 `AGENTS.md`，填写代码规范、review 规则、安全边界和命令。
- 目标 repo 的评审/评测口径：使用 `examples/review_evaluation_template.md`，可合并进 `AGENTS.md` 或放在目标仓库文档中。
- 运行配置：`.codexflow.yaml` 中填写 `target.path`、`target.base_branch`、`issues.provider`、`issues.repo`、`tests.command` 等实际项目配置。
- 可选 prompt 模板：如果要自己优化设计、评审、编码、总结等提示词，把 `codexflow/prompt_templates/*.md` 复制到自定义目录，并在 `.codexflow.yaml` 设置 `codex.prompt_templates_dir`。
- 用户反馈文件：使用 `examples/feedback_template.md`，用于 `codexflow reject` 或 `codexflow feedback`。

其他内容主要由用户 review，不需要直接编辑：

- Python 调度、状态机、DB、Git/GitHub/GitLab provider、report builder。
- 内置 prompt 模板。只有当用户想定制提示词时才复制到自定义目录修改，不建议直接改包内默认模板。
- TODO 中已完成的框架能力。用户主要审查责任边界、交互方式和验证范围是否符合预期。

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
- [x] 真实端到端验证
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

- 2026-05-27：使用 `cyrishe/auto-codex-test` 跑通真实 GitHub issue #1，最终本地 commit `4313af89f03b6bd10f1e50d1be64d0d02c394217`，issue label 进入 `codex:review`。

- [x] 准备真实测试 repo 或用户指定目标 repo
- [x] 创建清晰的最小 GitHub issue
- [x] 添加 `codex:ready` label
- [x] 运行 `codexflow run-issue <issue_number>`
- [x] 验证 issue 被 claim
- [x] 验证成功后进入 review label
- [ ] 验证 blocked/failed 时进入 blocked label
- [x] 验证本地 branch/worktree/commit/artifact 都可审查
- [x] 记录真实链路中的配置和权限要求

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

## Phase 9: 串行闭环强化

目标：吸收多 agent 分工思想，但保持主流程串行、可控。上一阶段只有通过评审或明确满足准入条件，才允许进入下一阶段。

职责边界：

- 用户负责每个阶段提示词的具体质量、风格、检查标准和业务判断细则。
- CodexFlow 负责阶段编排、状态机、artifact 契约、提示词变量注入、重试/修订循环、测试执行、报告生成和本地可审查结果。
- CodexFlow 不把 `needs_fix` 简单等同于 blocked。可修订的问题必须进入下一轮对应阶段。
- `blocked` 只用于需求矛盾、权限/环境缺失、超过最大轮数、或继续执行会要求用户做产品决策的情况。

原则：

- 不引入多个常驻 agent 并行扫描 commit。
- 不把 git commit 当作 agent 间消息队列。
- 继续使用中心调度器、SQLite 状态和 artifact 目录作为可信状态来源。
- commit 只作为本地交付结果和审查对象。
- 每个阶段都必须有输入 artifact、输出 artifact、状态记录和失败/blocked 记录。

### Phase 9.0: 提示词契约与反馈承接

目标：框架稳定提供“起承转合”的输入输出契约，用户可以持续优化每个阶段的具体提示词内容，而不需要改调度代码。

第一版阶段契约：

- `dev_design`：输入 issue、上下文、项目规则；输出设计 JSON。
- `review_design`：输入 issue、上下文、设计 JSON；输出设计评审 JSON。
- `dev_design_fix`：输入 issue、上下文、上一轮设计 JSON、上一轮设计评审 JSON；输出新设计 JSON。
- `dev_implement`：输入 issue、上下文、已通过设计 JSON、设计评审 JSON；输出代码改动和实现摘要。
- `review_code`：输入 issue、设计 JSON、diff、测试日志、安全扫描；输出代码评审 JSON。
- `dev_fix`：输入 issue、设计 JSON、代码评审 JSON、diff、测试日志；输出修复后的代码改动和实现摘要。
- `summary`：输入 issue、设计、评审、diff、测试、commit、artifact 索引；输出用户可读报告。

待办：

- [x] 明确每个 prompt template 的变量名和含义
- [x] 每个阶段 prompt 支持用户直接编辑模板文件
- [x] 用户改 prompt 不需要改 Python 调度逻辑
- [x] 设计评审中的 `blocking_issues` 必须完整传入 `dev_design_fix`
- [x] 设计评审中的 `non_blocking_suggestions` 也应传入 `dev_design_fix`，但不得强制扩大范围
- [x] 代码评审中的 `blocking_issues` 必须完整传入 `dev_fix`
- [x] 每轮修订都记录“上一轮输入、评审反馈、本轮输出”
- [x] 增加 prompt 变量缺失测试
- [x] 增加用户可替换 prompt template 的测试

### Phase 9.1: 设计修订循环

目标：设计评审发现问题时，不直接进入编码；如果 verdict 是 `needs_fix`，自动把设计评审反馈交回设计阶段重做，直到通过或超过最大轮数。

- [x] 配置新增 `codex.max_design_rounds`
- [x] 新增 `dev_design_fix` prompt
- [x] 设计 artifact 支持 round 命名，不覆盖上一轮
- [x] 设计评审 artifact 支持 round 命名，不覆盖上一轮
- [x] `review_design=pass` 才能进入编码
- [x] `review_design=needs_fix` 进入下一轮设计，不标记 blocked
- [x] 下一轮设计 prompt 必须包含上一轮设计和设计评审反馈
- [x] 下一轮设计 prompt 必须要求显式回应每个 blocking issue
- [x] 下一轮设计输出必须替代上一轮设计进入后续编码
- [x] `review_design=blocked` 立即 blocked
- [x] 超过 `max_design_rounds` 后 blocked
- [x] DB 记录每轮 design review verdict
- [x] resume 支持从设计修订循环中恢复
- [x] 增加设计评审失败后修订成功的测试
- [x] 增加设计评审持续失败后 blocked 的测试

空 repo 验证方法：

- [ ] 在 `/Users/cyrcyrisis/work/auto-codex-test/` 创建 toy project
- [ ] 准备一个 issue：第一轮设计故意遗漏边界条件
- [ ] fake/controlled Reviewer 返回 `needs_fix`，指出具体设计问题
- [ ] 验证第二轮 `dev_design_fix` prompt 中包含该反馈
- [ ] 验证第二轮设计修正后进入编码
- [ ] 验证最终 commit 和 report 使用的是通过后的设计

### Phase 9.2: 阶段准入门禁

目标：明确每个阶段的进入条件，避免前一阶段有问题时继续向后执行。

- [x] 设计阶段失败不能进入设计评审
- [x] 设计评审未 pass 不能进入编码
- [x] 编码无 diff 不能进入测试
- [x] protected path 变更不能进入测试或 review
- [x] 测试 required 且失败时不能进入最终通过
- [x] 代码 review 未 pass 不能 commit
- [x] 每个 blocked 状态都写 run summary
- [x] blocked 时 issue label 进入 blocked

空 repo 验证方法：

- [ ] 构造设计 blocked 的 issue，验证不会进入编码
- [ ] 构造无 diff 的实现，验证不会进入测试
- [ ] 构造测试失败且不可修复场景，验证不会 commit
- [ ] 构造代码 review needs_fix 后修复成功场景，验证才 commit
- [ ] 检查每个失败场景都有 run summary 和 artifact

## Phase 10: 用户人工确认队列

目标：用户可以看到“当前所有已经本地完成、但尚未 push/MR/PR 或尚未人工确认”的结果列表。

第一版定义：

- 已本地 commit 且 `auto_push=false` 的 run，需要用户确认。
- 已 `COMMIT_READY` 但 `auto_commit=false` 的 run，需要用户确认。
- 已 blocked 的 run，需要用户反馈或修正 issue。

待办：

- [x] 增加 run confirmation 状态字段或独立表
- [x] 区分 `DONE`、`PENDING_USER_REVIEW`、`USER_APPROVED`、`USER_REJECTED`
- [x] 新增 CLI：`codexflow pending-review`
- [x] 列出 issue、run id、branch、commit、test status、review summary、artifact 路径
- [x] 新增 CLI：`codexflow approve <run_id>`
- [x] 新增 CLI：`codexflow reject <run_id> --feedback-file <path>`
- [x] `approve` 默认只标记用户已确认，不自动 push
- [ ] 可选配置允许 approve 后 push/create PR/MR/comment
- [x] 增加 pending list 单元测试
- [x] 增加 approve/reject 状态流测试

空 repo 验证方法：

- [x] 使用 `/Users/cyrcyrisis/work/auto-codex-test/`
- [x] 保持 `auto_push=false`
- [x] 验证该 run 出现在 `pending-review`
- [ ] 执行 `approve` 后不再出现在待确认列表
- [ ] 执行 `reject --feedback-file` 后记录用户反馈

## Phase 11: Summary Agent 与用户报告

目标：增加一个独立的总结阶段，面向用户生成可快速审查的报告，而不是只给原始 artifact。

第一版只做本地 Markdown/HTML 报告，不直接接入 IM 或 web server。

责任边界：

- CodexFlow 负责收集结构化输入、生成报告文件、列出审查入口。
- 用户负责定义总结 prompt 的具体表达方式、风险口径和接纳标准。
- 第一版 summary 可以先用 deterministic report builder；后续再切到 summary agent prompt。

报告内容：

- issue 标题和链接
- 目标与验收标准摘要
- 设计结论
- 设计评审结论
- 修改文件列表
- 核心 diff 摘要
- 测试命令与结果
- 代码 review 结论
- commit/branch/worktree 信息
- 风险和需要用户关注的问题
- artifact 索引

待办：

- [x] 新增 summary prompt 或 deterministic report builder
- [x] 在 commit 后生成 `15_user_report.md`
- [ ] 可选生成 `15_user_report.html`
- [x] CLI `codexflow report <run_id>` 打印报告路径和关键信息
- [x] CLI `codexflow report --pending` 汇总所有待用户确认结果
- [x] report 中明确“建议接纳 / 需要反馈 / blocked”
- [x] 增加报告生成测试

空 repo 验证方法：

- [x] 跑完 toy issue 后生成 `15_user_report.md`
- [x] 报告能链接到 issue、commit、diff、测试日志、review 输出
- [x] 报告能明确告诉用户建议接纳还是需要反馈
- [x] `codexflow report --pending` 能汇总所有待确认结果

## Phase 12: 用户反馈转 Issue

目标：用户对报告提出反馈后，可以自动沉淀成新的 issue，进入同一条 CodexFlow 流程。

第一版只支持 CLI 输入反馈文件，不做 IM/web 接入。

待办：

- [x] 定义 feedback 文件模板
- [x] 新增 CLI：`codexflow feedback <run_id> --feedback-file <path>`
- [x] 根据反馈生成新 issue body
- [x] 新 issue 关联原 issue、run id、commit、报告路径
- [x] 支持 GitHub provider 创建 issue
- [x] 支持 GitLab provider 创建 issue
- [x] 新 issue 默认不自动加 `codex:ready`，除非配置允许
- [x] 增加 fake provider 测试

空 repo 验证方法：

- [x] 对 toy issue 的 report 写一个 feedback 文件
- [x] 执行 `codexflow feedback <run_id> --feedback-file <path>`
- [x] 验证生成的新 issue body 包含原 issue、run id、commit、用户反馈
- [x] 验证新 issue 默认不自动执行
- [ ] 用户人工加 `codex:ready` 后可进入下一轮

## Phase 13: 真实测试仓库验证

目标：使用用户提供的真实空测试仓库，设计 toy example，验证端到端流程。

测试仓库：

- 本地路径：`/Users/cyrcyrisis/work/auto-codex-test/`
- 当前分支：`master`
- 远端：`git@github.com:cyrishe/auto-codex-test.git`

验证范围：

- [x] 在测试仓库创建最小 toy 项目
- [x] 创建清晰的测试 issue
- [x] 配置 `.codexflow.yaml` 指向测试仓库
- [x] 跑通 `doctor`
- [x] 跑通单个 `run-issue`
- [x] 验证本地 worktree、branch、commit、artifact
- [x] 验证 issue label 流转
- [x] 验证 pending-review list
- [x] 验证 user report
- [x] 验证 feedback 转 issue
- [x] 记录真实链路配置、权限和注意事项

实验要求：

- [x] 该 test repo 可以不提交；每次运行结束可以清空环境，失败后也可以清空环境重做
- [x] toy project 必须足够小，便于人工 review
- [x] 真实实验项目使用自然语言量化选股 demo
- [x] demo 使用简单 Python sandbox 支持自然语言输入需求
- [x] demo 能展示生成的 Python 代码
- [x] demo 能执行生成代码并返回结果
- [x] demo 有本地 web service，可通过 API 验证功能
- [x] demo 可读取 `.env` 中的连接配置，但不得把密钥写入 artifact
- [x] demo 业务库名：`kingdomai`
- [x] demo 表范围：`aiia_stock_realtime_minute_snapshot`、`kcrp_stock_price`、`kcrp_stock_moneyflow`
- [x] 至少包含一个成功 issue
- [ ] 至少包含一个设计 needs_fix 后成功的 issue
- [ ] 至少包含一个 blocked issue
- [x] 成功实验保留 issue、run artifacts、report 和最终状态记录

## 暂缓事项

以下想法有价值，但暂不作为主线实现，避免过度设计：

- 多个常驻 subagent 并行扫描 commit。
- 用 git commit 作为 agent 之间的主要消息队列。
- IM 推送。
- Web dashboard 常驻服务。
- 多 issue 并行 worker。
