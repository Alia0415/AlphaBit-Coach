# 全局最小双 Expert 设计

## 决策

AlphaBit Coach 的可见多 Agent 协作从“复杂任务按需使用多个 Expert”升级为产品级
执行约束：

> 所有通过政策检查且信息充分、准备执行的投资研究任务，必须由至少两个不同的
> enabled Expert 协作完成。

若 Manager 无法为第二个 Expert 分配与当前目标相关、符合输入契约且可由实际证据
支持的工作，规划失败并明确说明能力边界。系统不得退化为单 Expert 执行，也不得用
重复步骤、空步骤或无关 Agent 凑数。

## 适用范围

约束适用于通过 AlphaOS v0.3 Manager 规划并准备执行的研究任务，包括 focused 和
comprehensive 请求。

以下情况不要求两个 Expert：

- `TaskSpec.execution_decision == "clarify"`，因为此时不会执行研究 DAG。
- 政策拒绝或规划失败，因为没有 Expert 被执行。

Manager、Coach 和用户画像不是 Expert，不能计入数量。相同 Expert 的多个步骤只算
一个 Expert。

## 动态分工

Manager 仍是唯一规划者，并从 Registry 的 enabled Expert 中动态选择最小可信的
双 Expert 组合。系统不规定固定的 `Research -> Risk` 或其他流水线。

第二个 Expert 必须承担以下至少一种真实职责：

- 获取主分析未覆盖的独立证据；
- 对主分析做授权范围内的量化交叉验证；
- 审查风险、关键假设、冲突和证据缺口；
- 在用户明确要求正式报告时，基于上游证据组织报告。

对于 focused 单维请求，辅助 Expert 可以执行不声明额外研究维度的交叉验证或审查
步骤，但必须拥有真实输入、明确输出和跨 Expert 依赖。它不能声称覆盖 Registry 未
授权的维度，也不能扩展用户目标。

典型分工仅用于说明，不构成固定路由：

- 单公司财务事实：Research 获取事实，Risk 审查数据质量、异常与缺口。
- 历史价格或波动：Quant 计算指标，Risk 审查窗口、下行风险和证据限制。
- 事件风险扫描：Risk 扫描事件，Research 获取可核验的公司或市场背景。
- 宏观主题：Macro 获取宏观证据，Risk 审查传导假设与不确定性。
- 行业竞争：Research 获取行业与同业证据，Quant 或 Risk 做适用的交叉验证。

## 计划校验

全局约束在 Manager 计划语义校验处执行：

1. `selected_agents` 必须包含至少两个不同 AgentId。
2. `selected_agents` 仍须与 steps 中实际使用的 Agent 完全一致。
3. 至少存在一条跨 Expert 依赖，证明计划包含协作而非两个并列孤岛。
4. 辅助步骤必须通过现有 Registry 授权和 Agent 输入契约校验。
5. focused 请求仍不得声明无关维度。
6. Report 仍只在 `formal_report` 被要求时使用，不能作为通用凑数 Agent。

首次计划违反约束时走现有一次受控 repair。repair 后仍不足两个 Expert 或没有跨
Expert 依赖时，Manager 返回规划失败，不启动 WorkflowExecutor。

## 提示与架构文档

更新 Manager 初始提示和 repair 提示，明确：

- “最小充分专家集合”现在以两个不同 Expert 为下限。
- 第二个 Expert 必须有真实职责和依赖，禁止凑数。
- 无法形成可信协作时停止规划。

同步更新根目录 `AGENTS.md` 中允许单 Expert 的旧规则，以及开发规则中关于最小充分
集合的描述，使后续实现和评审使用同一产品约束。

## 测试

自动化测试使用 Mock ArkClient，不消耗模型或 PandaData 配额：

1. focused 单 Agent 计划首次返回时触发一次 repair。
2. 两次均返回单 Agent 时，Manager 失败且 Executor 未启动。
3. 两个不同 Expert 但没有跨 Expert 依赖时，Manager 拒绝。
4. 两个不同 Expert、真实步骤和跨 Expert 依赖的计划通过。
5. clarification 任务不要求构造研究 DAG。
6. Report 不能被用于普通任务凑第二个 Expert。
7. 现有单 Agent Manager 测试改成合法双 Expert 计划或明确断言规划失败。
8. 财务质量、成长估值、综合研究和 Agent 输入契约回归继续通过。

## 验收标准

- 任意准备执行的用户研究请求都不能产生只有一个不同 Expert 的有效计划。
- 前端执行事件中至少出现两个不同 Expert。
- 无法生成可信双 Expert DAG 时，用户收到规划失败，而不是单 Agent 结果。
- 不增加新 Expert、不扩展 Skill 所有权、不让 Executor 或 Aggregator追加 Agent。
- 不用 Report、空步骤、重复步骤或未授权维度规避数量约束。
