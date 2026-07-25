# AlphaBit Coach

> PandaAI "Build the Next AI Trader" 赛道提交说明
> 一支看得见的 AI 投研团队，一位帮助用户学习研究方法的金融教练。

AlphaBit Coach 基于 AlphaOS 动态多 Agent 运行时构建。它不是把多个 Agent
按固定顺序串联，而是由 Manager Agent 根据当前研究目标临时组建专家团队、
生成任务 DAG，并让各专家在自己的授权边界内选择 Skill。

最终答案只来自实际执行产生的 `ExpertResult`。失败步骤、缺失数据和未经验证的
假设不会被补写成确定结论。

完整的开发、安装、测试和能力边界文档请参阅项目原始
[README](./README.md)。

## Submission Links

| Entry | URL | Purpose |
| --- | --- | --- |
| Live product | [http://118.178.136.23:8000/office](http://118.178.136.23:8000/office) | Pixel office、任务 DAG、执行过程和研究结果 |
| Agent Card | [http://118.178.136.23:8000/.well-known/agent-card.json](http://118.178.136.23:8000/.well-known/agent-card.json) | A2A 能力、协议、Skill 和鉴权声明 |
| A2A endpoint | `http://118.178.136.23:8000/a2a` | JSON-RPC 2.0 `message/send` 与 `tasks/get` |
| OpenAPI | [http://118.178.136.23:8000/docs](http://118.178.136.23:8000/docs) | HTTP API 调试文档 |

评测用 Bearer token 仅通过赛道提交表单提供，不写入仓库。

## Project Overview

传统 AI 投研产品通常只展示最终答案。用户看不到答案由谁完成、使用了什么数据、
哪些步骤失败，也难以判断结论是否超出证据范围。

AlphaBit Coach 将投研过程本身变成产品界面：

1. 用户用自然语言提出研究目标。
2. Policy Gate 检查能力与合规边界。
3. Task Interpreter 将目标转换成结构化研究任务。
4. Manager Agent 动态选择最小充分专家集合并生成任务 DAG。
5. 系统使用 Pydantic 与图校验拒绝非法计划。
6. Research、Quant、Macro、Risk 等专家独立执行获授权任务。
7. Result Aggregator 只基于真实专家结果形成结论、证据块和限制说明。
8. Pixel office、SSE 日志和 Skill 事件实时展示协作过程。

产品包含两个长期支柱：

- **Visible multi-agent research**：已实现动态专家选择、任务 DAG、Agent
  状态动画、SSE 执行日志、Skill 调用可视化和证据结果页。
- **AI financial coach**：已实现用户画像、报告追问、术语解释、通俗/专业视图、
  基于报告证据的研究复盘与引导问题。独立的任务前置教练层仍在规划中，不作为
  本次已交付能力声明。

## Core Features

| Feature | What it does | User value |
| --- | --- | --- |
| Dynamic expert selection | Manager 从 `research`、`quant`、`macro`、`risk`、`report` 中选择最小充分集合 | 不把所有问题硬塞进固定流程 |
| Validated task DAG | 校验未知 Agent、循环依赖、输入契约、维度覆盖和步骤上限 | 模型生成的计划不能直接获得执行权 |
| Expert-owned Skill planning | Manager 只选专家，每个专家只在自己的 allowlist 内选择 Skill | 责任边界清晰，Skill 调用可审计 |
| Visible collaboration | Pixel office 展示 Agent 状态、并行步骤、依赖、SSE 日志和 Skill 事件 | 用户能观察研究如何完成 |
| Evidence-bounded aggregation | Aggregator 只读取实际 `ExpertResult`，保留来源、验证状态、冲突和缺失证据 | 不用模拟结果补齐失败步骤 |
| Layered result views | 通俗结论、动态内容块和专业证据视图共享同一后端结果 | 初学者可读，专业用户可追溯 |
| Financial learning support | 报告追问、术语解释、研究复盘和知识水平适配 | 用户不仅得到答案，也学习研究方法 |
| A2A interoperability | 公开 Agent Card，支持 Bearer 鉴权 JSON-RPC 调用 | 可被评测平台和其他 Agent 调用 |

## Use Cases

### 综合公司研究

并行研究市场表现、财务基本面、行业竞争、宏观环境和事件风险，最后由
Report Agent 汇总证据、冲突和局限。

### 市场与量化交叉验证

计算收益、波动、回撤和成交量指标，用历史市场证据检查上游观点是否一致，
但不把历史一致性表述为未来预测。

### 因子研究

生成结构化因子假设，或计算固定、哈希校验的 R020 成交量放大因子。系统明确区分：

- `unverified`：待验证研究假设；
- `computed_not_validated`：完成计算但没有形成有效性证据；
- 回测、IC 和绩效证据：当前能力边界之外。

### 财报与基本面尽调

通过单公司 dossier 分析财务表现、盈利质量、现金流、审计意见和披露风险。

### 宏观与事件风险监控

Macro Agent 使用受控 PandaData 指标，Risk Agent 扫描公告和事件线索。
数据不可用时显式失败，不生成模型事实替代。

### 研究学习

用户可在结果页切换通俗/专业视图，对已完成报告追问概念、提取术语，
并获得基于报告证据的研究复盘。

## Architecture

```text
User / A2A Client
        |
        v
Policy Gate -> Task Interpreter -> Manager Agent
                                  |
                                  v
                         Dynamic Expert Selection
                                  |
                                  v
                      Validated Task Graph (DAG)
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
        Research Agent       Quant Agent        Macro / Risk Agent
        |          |         |          |        |             |
        |          |         |          |        |             |
   Market path  Research   Quant     Allowlisted macro_monitor  event_risk_alert
                Planner    Planner      Skills
                   |          |
                   v          v
       a_share_stock_dossier  factor_idea_generation / R020
              +-------------------+-------------------+
                                  |
                                  v
                         Result Aggregator
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             A2A task/artifacts          Pixel Office UI
             plan/events/results         DAG/SSE/content blocks
                    |
                    v
          Report follow-up / glossary / coach guide
```

### Architecture rules

- Manager 只能选择专家和专家间依赖，不能选择或调用底层 Skill。
- Manager 不能作为专家出现在 `selected_agents` 或任务步骤中。
- `WorkflowExecutor` 严格执行校验后的 DAG，不会追加隐藏步骤。
- 每个专家只能看到并选择归属于自己的已启用 Skill。
- `ResultAggregator` 独立于 Manager，只读取实际执行结果。
- 前端只渲染后端返回的结果，不生成研究结论。
- 任务图最多 8 个步骤，并拒绝环路、未知 Agent 和非法输入。

### Expert pool

| Expert | Responsibility |
| --- | --- |
| `research` | PandaData 市场研究、单公司财报和基本面尽调、行业研究 |
| `quant` | 历史量化交叉验证、因子假设、固定 R020 计算 |
| `macro` | 宏观、政策、周期、利率和流动性研究 |
| `risk` | 独立风险审查和 PandaData 事件风险扫描 |
| `report` | 按声明的上游依赖整合正式报告，不是默认必经节点 |

## Skills Invocation

### Two-level planning

Skill 调用分成专家选择和专家内部选择两层：

```text
1. Manager creates an ExpertTask
   -> agent, objective, structured inputs and dependencies

2. WorkflowExecutor dispatches the ExpertTask
   -> only to the agent named by the validated DAG

3. The selected expert runs its own Skill Planner
   -> sees only Skills owned by that expert

4. SkillRegistry validates and dispatches the invocation
   -> ownership, mode, lock entry, hash, path and input checks

5. The Skill returns SkillResult
   -> data, validation status, assumptions, limitations and provenance

6. The expert wraps actual SkillResults in ExpertResult
   -> Aggregator receives evidence, never raw model intentions
```

Manager 的计划中不允许出现 `skill_id`。例如，Manager 只创建 Quant 因子研究步骤；
Quant Skill Planner 再决定使用 `factor_idea_generation`、
`r020_volume_expansion`，或不调用 Skill。

### Runtime allowlist

`backend/skills/skill_registry.py` 是运行时唯一 Skill 事实源：

| Skill ID | Mode | Owner | Purpose | Status boundary |
| --- | --- | --- | --- | --- |
| `factor_idea_generation` | instruction | `quant` | 生成结构化因子假设 | `unverified` |
| `r020_volume_expansion` | executable | `quant` | 计算固定 R020 成交量放大因子 | `computed_not_validated` |
| `a_share_stock_dossier` | instruction | `research` | A 股单公司财报和基本面尽调 | 不验证未来收益 |
| `macro_monitor` | instruction | `macro` | 宏观监控方法与指标选择 | 事实必须来自 PandaData |
| `event_risk_alert` | instruction | `risk` | 事件与公告风险扫描 | 事件线索不等于因果结论 |

### Runtime security

- Skill 必须安装在 `QUANTSKILLS_HOME` 并记录于 `skills.lock.json`。
- 启动时校验仓库来源、固定 commit、入口文件和 SHA-256。
- Instruction Skill 被视为不可信方法文本，只允许有界读取。
- 系统不会执行 `SKILL.md` 中出现的命令。
- Executable Skill 只能加载 lock 文件声明的固定入口。
- 模型输出必须通过 Pydantic 校验，最多进行一次受控 JSON 修复。
- 未知目录、用户提供的仓库和未登记 Skill 不会被自动发现。

## Result Presentation

同一次执行只产生一份后端事实，Web UI 和 A2A 是两种展示方式。

### Web product

- **Pixel office**：Agent 根据 `idle`、`working`、`blocked`、`completed`
  状态移动并切换动画。
- **Dynamic DAG**：只展示本次 Manager 实际选择的步骤、并行关系和依赖边。
- **Execution stream**：SSE 持续发送计划、步骤和 Skill 生命周期事件。
- **Simple view**：先展示 `aggregation.direct_answer`，再渲染动态
  `content_blocks`。
- **Professional evidence view**：展示完整 `ExpertResult`、数据来源、验证状态、
  冲突、缺失证据、假设、限制和 provenance。
- **Learning tools**：对已完成报告提供术语解释、证据锚定追问和研究复盘。

前端不会自行生成研究结论。没有被调用的专家不会产生空白章节，失败的 Skill
也不会被替换成示例结果。

### A2A result

`message/send` 返回 JSON-RPC task。`artifacts` 同时包含：

- `text`：适合直接阅读的结论；
- `data.plan`：校验后的动态专家 DAG；
- `data.events`：Agent 与 Skill 执行事件；
- `data.results`：按 step ID 索引的完整 `ExpertResult`；
- `data.aggregation`：直接答案、内容块、执行摘要和技术证据；
- `data.disclaimer`：研究用途和非投资建议边界。

## Verified Multi-agent Example

以下问题已通过线上 `/api/plan` 验证：

```text
请对贵州茅台（600519.SH）在2026年4月1日至2026年7月25日做一份综合研究报告：
分别研究市场价格与成交量表现、公司基本面、白酒行业竞争与宏观消费环境；
使用历史收益、波动和回撤进行量化交叉验证，扫描同期重大事件风险，
最后整合证据、冲突和局限。不要提供买卖建议。
```

Manager 动态选择 5 类专家并生成 7 步 DAG：

```text
research_market ───────┐
research_fundamentals ─┤
research_industry ─────┤
macro ─────────────────┼─> report
quant ─────────────────┤
risk ──────────────────┘
```

前六个步骤可并行执行，`report` 只在声明的上游结果完成后运行。
这个结构来自当前问题的研究维度，不是硬编码的 Agent 顺序。

预期 A2A 输出包括：

1. 人类可读的研究结论；
2. Manager 创建的动态 DAG；
3. 每个 Agent 和 Skill 的执行事件；
4. 市场、基本面、行业、宏观、量化和风险证据；
5. 专家结论之间的一致点与冲突；
6. 缺失证据、验证状态和研究局限；
7. 非投资建议声明。

## A2A Usage

### Send a message

```bash
curl -X POST "http://118.178.136.23:8000/a2a" \
  -H "Authorization: Bearer ${ALPHAOS_A2A_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "demo-1",
    "method": "message/send",
    "params": {
      "taskId": "demo-1",
      "message": {
        "role": "user",
        "messageId": "demo-message-1",
        "parts": [{
          "kind": "text",
          "text": "分析 600519.SH 的市场表现、量化证据和主要风险。"
        }]
      }
    }
  }'
```

### Get an existing task

```bash
curl -X POST "http://118.178.136.23:8000/a2a" \
  -H "Authorization: Bearer ${ALPHAOS_A2A_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "demo-get-1",
    "method": "tasks/get",
    "params": {"id": "demo-1"}
  }'
```

## Capability Boundary

Currently supported:

- Dynamic selection and execution of Research, Quant, Macro, Risk and Report;
- PandaData-backed market, company, macro and event-risk research;
- allowlisted factor idea generation and R020 computation;
- dynamic DAG, SSE events and Skill-call visualization;
- evidence-bounded aggregation and professional evidence view;
- report follow-up, glossary, plain-language explanation and research review;
- A2A Agent Card, authenticated task submission and task retrieval.

Not currently supported:

- complete factor backtesting or multidimensional IC diagnostics;
- automatic trading, account access or order placement;
- buy/sell recommendations, return promises or target prices;
- dynamic execution of unknown repositories or commands from Skill documents;
- a Coach that joins the expert DAG or triggers new research.

All output is for investment research and technical demonstration only.
It does not constitute investment advice, a securities recommendation,
a return promise or a trading instruction.
