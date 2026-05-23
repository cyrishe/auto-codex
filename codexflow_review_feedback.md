# CodexFlow 当前实现反馈与下一步建议

## 1. 结论

结合目前已看到的代码和开发总结，我的判断是：

CodexFlow 当前已经完成了一个较清晰的主干 MVP：能够围绕 GitHub Issue 拉取任务、采集上下文、调用 Codex 完成设计、进行设计评审、执行实现、运行测试、做代码评审并生成本地提交。这个主流程方向是对的，也符合“开发 Agent + Review Agent”的基本架构。

但当前阶段还不能按成熟自动化开发系统来要求。开发总结里提到的几个未完成项是合理的：fix loop、resume、watch、真实 GitHub/Codex 端到端试跑还没有完成。因此，接下来不建议马上扩很多功能，而应该先把“主干链路是否能稳定跑通”验证清楚。

我认可开发总结中的判断：

> 下一步最贴近主线的是先用一个 toy repo + fake/真实 gh 边界做一次更接近真实的 run-issue 集成验证，然后再补 fix loop。

这个顺序是合理的。原因是：fix loop 是建立在 run-issue 主干可复现、artifact 可追踪、状态可恢复、Git 操作可验证的基础上的。如果主干链路还没有经过端到端验证，过早加入修复循环会增加调试复杂度。

---

## 2. 当前代码完成度判断

### 2.1 已经完成的主干能力

从已阅读代码看，当前已经具备以下基础能力：

1. GitHub Issue 驱动任务入口；
2. 本地 run 记录与 artifact 输出；
3. 工作目录 / worktree 准备；
4. context 采集；
5. developer design；
6. reviewer design review；
7. developer implement；
8. git diff 采集；
9. test command 执行；
10. reviewer code review；
11. 本地 commit message 生成与提交；
12. CLI 层提供 `init`、`doctor`、`status`、`show-run`、`run-issue`、`run-next`、`run-all` 等基础命令。

这些已经足够支撑一次“golden path”的端到端验证。

### 2.2 当前还不应被视为完成的能力

以下能力还不能算真正完成：

1. review 后自动修复循环；
2. 测试失败后的自动修复；
3. resume 中断恢复；
4. watch 轮询常驻执行；
5. GitHub PR 创建与完整远程协作闭环；
6. 真实 Codex + 真实 GitHub + 真实目标 repo 的端到端稳定性验证；
7. stale lock 清理；
8. 更强的 secret 内容级脱敏；
9. 更细粒度的失败状态分类；
10. issue 相关代码自动检索增强。

因此，当前系统更准确的定位是：

> 可运行的线性 MVP 主流程，而不是已经完成的自动迭代开发平台。

---

## 3. 对开发总结的评价

开发总结中的这句话是准确的：

> 当前还没做：fix loop、resume、watch、真实 GitHub/Codex 端到端试跑。

这说明开发者对当前边界的判断是清楚的，没有过度宣称完成度。

我尤其同意下一步先做 run-issue 集成验证，而不是马上补 fix loop。原因如下：

1. `run-issue` 是整个系统的最小闭环；
2. fix loop 会反复调用 design / implement / review / test，如果基础链路未稳定，会把问题放大；
3. fake boundary 可以更快定位流程问题，而不是被真实 GitHub、真实 Codex、真实 repo 的不确定性干扰；
4. toy repo 能提供可控任务，便于确认 artifact、DB、Git diff、review schema、commit 等关键节点是否完整。

因此建议下一阶段目标定义为：

> 先验证一个 issue 从 ready 到本地 commit / review label 的完整主路径，再进入 fix loop 开发。

---

## 4. 下一步优先级建议

## P0：先做 run-issue 集成验证

这是当前最优先事项。

### 目标

用 toy repo 跑通一次接近真实的流程：

1. 创建一个最小 toy repo；
2. 准备一个明确、简单、可测试的 issue；
3. 通过 fake GitHub 或真实 GitHub issue 触发；
4. 跑 `codexflow run-issue <issue_number>`；
5. 检查 artifact、DB 状态、diff、测试日志、review 输出、commit 结果。

### 推荐 toy repo 设计

toy repo 不要复杂，建议包含：

```text
toy-repo/
  README.md
  pyproject.toml
  src/toycalc.py
  tests/test_toycalc.py
```

issue 示例：

```text
Add multiply(a, b) to src/toycalc.py and add tests.
```

这样可以清楚验证：

1. issue 能否被读取；
2. README / manifest / file tree 能否进入 context；
3. Codex 能否设计；
4. reviewer 能否输出合法 JSON；
5. Codex 能否改代码；
6. tests 是否执行；
7. diff 是否保存；
8. code review 是否能判断；
9. commit 是否生成。

### fake boundary 建议

建议先做 fake 边界，不要一开始就全部接真实 GitHub 和真实 Codex。

可分三层：

#### Level 1：全 fake

- fake GitHubClient：返回固定 issue；
- fake CodexRunner：按阶段输出固定 design / review / implementation；
- fake TestRunner：返回 pass；
- 目标：验证 Pipeline 状态机、artifact、DB、Git 操作。

#### Level 2：fake GitHub + real Codex

- issue 仍由 fake client 提供；
- Codex 使用真实 `codex exec`；
- 目标：验证 prompt、schema、Codex 输出、真实代码修改。

#### Level 3：real GitHub + real Codex

- 使用真实 GitHub issue；
- 使用真实 label；
- 使用真实 Codex；
- 目标：验证接近生产的完整流程。

这个三层顺序比直接跑真实全链路更稳。

---

## 5. P0 验收标准

建议把本轮集成验证的验收标准写清楚，不要只看“命令没报错”。

### 5.1 run 记录验收

一次成功 run 后，DB 中应能看到：

1. run_id；
2. issue_number；
3. target_repo_path；
4. base_branch；
5. work_branch；
6. base_sha；
7. status = DONE；
8. current_phase = done；
9. final_sha。

### 5.2 artifact 验收

run 目录下至少应包含：

1. `meta.json`；
2. `00_issue.md`；
3. `00_context.md`；
4. `01_dev_design.prompt.md`；
5. `01_dev_design.output.json`；
6. `02_review_design.prompt.md`；
7. `02_review_design.output.json`；
8. `03_dev_implement.prompt.md`；
9. `03_dev_implement.final.md`；
10. `04_git_diff.patch`；
11. `05_test.log`；
12. `06_review_code.prompt.md`；
13. `06_review_code.output.json`；
14. `10_final_commit_summary.json`；
15. `11_commit_message.txt`。

### 5.3 Git 验收

应确认：

1. work branch 已创建；
2. git diff 曾经存在并被保存；
3. commit 已生成；
4. commit message 包含 issue number、run id、test status、review summary；
5. protected path 没有被修改。

### 5.4 Review 验收

应确认：

1. design review 输出符合 schema；
2. code review 输出符合 schema；
3. `pass` 时没有 blocking issues；
4. `needs_fix` 或 `blocked` 时有明确 blocking issue；
5. score、risk_level、summary 都被记录。

### 5.5 GitHub 验收

如果启用 GitHub，应确认：

1. ready label 被移除；
2. working label 被加入；
3. 成功后进入 review label；
4. 失败或阻断后进入 blocked label；
5. label 状态不会残留在 working。

---

## 6. 关于 fix loop 的建议

fix loop 很重要，但不建议先于端到端验证实现。

### 6.1 当前 review 结果的使用方式

目前 review 只起到“通过 / 阻断”的作用。更理想的方式是：

```text
developer design
→ reviewer design review
→ pass：进入 implement
→ needs_fix：developer revise design
→ blocked：停止
```

代码实现阶段也类似：

```text
developer implement
→ test
→ reviewer code review
→ pass：commit
→ needs_fix：developer fix implementation
→ test again
→ review again
→ blocked 或超过最大轮数：停止
```

### 6.2 fix loop 最小实现建议

不建议一上来做复杂状态机。可以先做两个小循环：

1. design fix loop；
2. code fix loop。

每个 loop 加三个约束：

1. 最大轮数，例如 `max_design_fix_rounds = 2`，`max_code_fix_rounds = 3`；
2. 每轮都保存独立 artifact；
3. 每轮都记录 review verdict 和 blocking issues。

artifact 命名建议：

```text
01_dev_design.round1.output.json
02_review_design.round1.output.json
01_dev_design.round2.output.json
02_review_design.round2.output.json

03_dev_implement.round1.final.md
06_review_code.round1.output.json
03_dev_fix.round2.final.md
06_review_code.round2.output.json
```

不要覆盖旧文件。fix loop 最怕历史不可追踪。

### 6.3 fix prompt 内容

fix prompt 不应只传原 issue 和 diff，还应明确传入：

1. 上一轮 review 的 blocking issues；
2. reviewer suggested_fix；
3. 当前 git diff；
4. 测试日志；
5. 不允许扩大 scope；
6. 不允许跳过测试；
7. 本轮只修复 blocking issues。

---

## 7. 关于 resume 的建议

resume 可以晚于第一次集成验证，但应早于 watch。

原因是 watch 会让任务自动持续执行。如果没有 resume，一旦中间失败，就只能重新跑整个 issue，容易产生：

1. 重复分支；
2. 重复 run；
3. 重复 commit；
4. GitHub label 状态错乱；
5. artifact 难以对应。

### 7.1 最小 resume 范围

第一版 resume 不需要支持任意阶段恢复，可以先支持几个关键状态：

1. `CONTEXT_COLLECTED`：从 design 继续；
2. `DEV_DESIGN_DONE`：从 design review 继续；
3. `DESIGN_REVIEWED`：从 implement 继续；
4. `IMPLEMENTED`：从 diff/test 继续；
5. `TESTED`：从 code review 继续；
6. `COMMIT_READY`：从 commit 继续。

### 7.2 resume 需要的前提

为支持 resume，需要确保：

1. 每个阶段输出路径可从 DB 或 meta.json 找回；
2. worktree_path 可恢复；
3. work_branch 可恢复；
4. base_sha 可校验；
5. 当前 git 状态可检查；
6. artifact 不被覆盖。

如果这些基础信息已经在 `RunStore` 和 `meta.json` 里有，就可以较轻量实现。

---

## 8. 关于 watch 的建议

watch 不建议现在做。

watch 的本质不是简单循环 `run-next`，而是一个守护进程形态。它需要处理：

1. 空队列等待；
2. 异常重试；
3. stale lock；
4. GitHub rate limit；
5. 系统退出信号；
6. 日志输出；
7. 一次只处理一个 issue 还是并发处理；
8. 失败任务是否自动重试。

因此建议顺序是：

```text
run-issue 集成验证
→ fix loop
→ resume
→ 再做 watch
```

否则 watch 会把所有未解决的状态问题放大。

---

## 9. 关于 GitHub / PR 闭环

目前从已看到代码看，GitHubClient 有 issue label 操作，也有 create_pr 能力，但主 Pipeline 更偏向本地 commit 后把 issue 标记为 review。

后续建议明确产品形态：

### 方案 A：本地开发助手

只负责：

```text
issue → 本地分支 → 本地 commit → artifact
```

这种情况下，不一定要 create PR。

### 方案 B：GitHub 自动开发机器人

应负责：

```text
issue → branch → commit → push → PR → issue comment → review label
```

如果目标是通用 repo 自动开发工具，建议走方案 B。否则用户还需要手动 push 和建 PR，自动化价值会弱一些。

建议后续补：

1. push branch；
2. create PR；
3. PR body 写入 run summary；
4. issue comment 写入 run 结果；
5. blocked 时 comment blocking reason；
6. 支持 dry-run，不实际 push。

---

## 10. 对当前代码的重点改进建议

## 10.1 测试失败策略要明确

当前 TestRunner 能区分 pass / fail / timeout / skipped。建议 Pipeline 层增加策略：

```yaml
tests:
  required: true
  fail_on_failure: true
  allow_skipped: false
```

对应行为：

1. `pass`：继续；
2. `fail`：进入 code fix loop；
3. `timeout`：进入 code fix loop 或 blocked；
4. `skipped`：如果 required=true，则 blocked。

这样比把测试失败完全交给 reviewer 判断更稳定。

## 10.2 Codex 调用应统一超时

CodexRunner 已经支持 timeout_seconds，但 Pipeline 调用时应从配置传入。建议至少分阶段配置：

```yaml
codex:
  design_timeout_seconds: 900
  review_timeout_seconds: 600
  implement_timeout_seconds: 1800
  fix_timeout_seconds: 1800
```

这样可以避免 `codex exec` 卡死导致全流程挂住。

## 10.3 Lock 要支持 stale 清理

当前锁机制能避免并发，但进程异常退出后可能留下 stale lock。建议增加：

1. lock TTL；
2. pid 存活检查；
3. `codexflow unlock --stale`；
4. doctor 中提示 stale lock。

## 10.4 Secret 过滤应增加内容级脱敏

路径级 secret 过滤是必要的，但不够。建议再增加内容级 redaction：

1. API key；
2. GitHub token；
3. OpenAI style token；
4. private key block；
5. password / secret / token 配置项；
6. 云厂商 AK/SK。

应用位置：

1. context；
2. test log；
3. git diff；
4. Codex output；
5. PR body；
6. issue comment。

## 10.5 Context 采集应增加 issue 相关代码召回

当前 context 偏文档和文件树。后续建议根据 issue 内容做轻量检索：

1. 从 issue title/body 抽关键词；
2. 用 ripgrep 搜索相关文件；
3. 加入命中的函数、类或文件片段；
4. 控制 max chars；
5. 记录 included/excluded 文件。

这比简单塞 README 和 file tree 更有助于 design 阶段。

---

## 11. 建议的下一轮开发计划

## Milestone 1：run-issue 集成验证

目标：跑通 golden path。

任务：

1. 建 toy repo；
2. 写 fake GitHubClient；
3. 写 fake CodexRunner；
4. 写 fake TestRunner；
5. 增加 integration test；
6. 验证 artifacts；
7. 验证 RunStore 状态；
8. 验证 git diff 和 commit；
9. 验证 GitHub label 状态变化。

输出：

1. 一份 run log；
2. 一份 run artifact；
3. 一份集成测试报告；
4. 一组可复现命令。

## Milestone 2：真实 Codex 边界验证

目标：验证 prompt / schema / sandbox / Codex 输出。

任务：

1. toy repo 使用真实 Codex；
2. GitHub 仍可 fake；
3. 固定简单 issue；
4. 检查 design output JSON；
5. 检查 review output JSON；
6. 检查 implementation 是否真的改代码；
7. 检查 tests 是否通过。

输出：

1. 真实 Codex run artifact；
2. prompt 优化建议；
3. schema 调整建议。

## Milestone 3：fix loop

目标：实现最小自动修复闭环。

任务：

1. design needs_fix loop；
2. code needs_fix loop；
3. 测试失败进入 fix；
4. max rounds；
5. 每轮 artifact 独立保存；
6. 超轮数后 blocked；
7. review blocking issues 进入 fix prompt。

输出：

1. fix loop demo；
2. 两个故意失败 issue 的验证；
3. 修复轮次报告。

## Milestone 4：resume

目标：中断后可恢复。

任务：

1. DB/meta 记录阶段输入输出；
2. 支持从关键阶段恢复；
3. 校验 worktree 和 branch；
4. 避免 artifact 覆盖；
5. CLI 增加 `resume <run_id>`。

输出：

1. 手动 kill 后恢复测试；
2. resume 使用说明。

## Milestone 5：GitHub PR 闭环

目标：形成真实协作流。

任务：

1. push branch；
2. create PR；
3. PR body 汇总 run；
4. issue comment；
5. blocked comment；
6. dry-run 模式。

输出：

1. toy repo PR；
2. issue 状态变化；
3. PR 模板。

## Milestone 6：watch

目标：持续轮询执行。

任务：

1. 循环 run-next；
2. graceful shutdown；
3. stale lock 处理；
4. 错误重试策略；
5. 日志；
6. rate limit 保护。

输出：

1. watch demo；
2. 守护进程运行说明。

---

## 12. 最终建议

当前阶段最重要的不是继续堆更多功能，而是把系统从“代码看起来能跑”推进到“主路径被验证确实能跑”。

我建议下一步严格按下面顺序：

```text
1. toy repo + fake boundary 跑通 run-issue
2. toy repo + real Codex 跑通 run-issue
3. real GitHub + real Codex 跑通最小 issue
4. 补 fix loop
5. 补 resume
6. 补 PR 闭环
7. 最后补 watch
```

这条路线比较稳，因为它先验证主干，再增加循环，再增加恢复，再进入常驻运行。

如果反过来先做 watch 或复杂 fix loop，很容易出现问题难定位：到底是 GitHub label、Codex 输出、review schema、worktree、DB 状态、测试命令、还是锁机制出了问题，会非常难查。

因此，我对当前开发总结的判断是：方向正确，而且下一步“先做更接近真实的 run-issue 集成验证，再补 fix loop”是当前最合理的工程推进路径。
