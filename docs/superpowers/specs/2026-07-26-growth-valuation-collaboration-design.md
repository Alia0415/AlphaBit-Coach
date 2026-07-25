# 成长性与估值复合研究协作设计

## 背景

“评估宁德时代（300750.SZ）的成长性与估值水平”在生产路径中可能被模型
解释为仅包含 `company_fundamentals`，导致 Manager 合法地只选择 Research。
确定性解释器已经能把该请求识别为多维研究，因此问题位于模型维度解释结果
缺少复合目标语义校正，而不是 Executor 丢失了计划中的 Agent。

产品主打可见的多 Agent 研究，但不能为了展示 Agent 数量而制造重复工作或
虚构估值证据。当前系统尚无可靠的 PE、PB、EV 或估值历史分位数据链，本次
实现必须如实暴露该证据边界。

## 目标

对同时要求公司成长性和估值判断的单公司研究：

1. 即使模型把请求低估为单一基本面维度，TaskInterpreter 也能恢复必要的
   多维研究要求。
2. Manager 根据 TaskSpec 动态生成真实分工的 DAG，而不是 Executor 追加步骤。
3. Research、Quant 和 Risk 各自执行其授权范围内的工作。
4. 缺少可靠估值指标时，结果明确标记估值证据不足，不用价格走势冒充估值。
5. 明确的单维请求仍使用最小充分专家集合。

## 方案选择

采用“现有团队多维协作并诚实降级”：

- Research 公司基本面步骤分析收入、利润、现金流和可用历史趋势，回答成长性。
- Research 行业竞争步骤获取可用行业与同业证据，为成长持续性及相对位置提供背景。
- Quant 使用现有受控市场数据计算价格、收益、波动、回撤和相对表现，只作为
  市场交叉验证，不声称其等于估值。
- Risk 等待上游步骤终态，审查成长持续性、估值假设、冲突和缺失证据。
- 不因普通聊天请求增加 Report；Aggregator 直接组织实际 ExpertResult。

未选择两个替代方案：

- 仅使用 `Research -> Risk`：实现更小，但仍弱化了可见协作，也缺少市场交叉验证。
- 先建设完整估值数据能力：结论最完整，但需要新增数据接口、指标计算和验证，
  不适合当前 DDL。

## 语义识别

TaskInterpreter 在模型输出校验后增加窄范围语义校正。校正只针对同时包含：

- 成长目标，例如“成长性”“成长能力”“增长能力”“业绩增长”；以及
- 估值目标，例如“估值”“估值水平”“贵不贵”。

满足条件的单公司研究至少要求：

- `company_fundamentals`
- `industry_competition`
- `quantitative_cross_check`
- `risk_assessment`

请求保持 focused，避免自动加入与原目标无关的宏观或正式报告维度。校正发生在
TaskSpec 生成处，Manager 仍是唯一规划者；Executor 和 Aggregator 不增加 Agent。

## Manager 与 DAG 约束

Manager prompt 明确说明这类请求的职责边界：

- 公司 Research 覆盖成长性事实。
- 行业 Research 覆盖同业及竞争背景。
- Quant 覆盖市场交叉验证，不覆盖估值结论。
- Risk 审查全部上游证据，并明确估值证据缺口。

Validator 要求：

- 四个 required dimensions 均被授权步骤覆盖。
- Risk 对至少一个上游研究步骤存在依赖，以便其审查实际证据。
- 不强制固定步骤 ID、固定 Agent 顺序或 Report 收尾。
- Manager 仍可在一个 Research 步骤中覆盖其两个授权维度，只要输入契约有效；
  推荐计划使用两个 Research 步骤以展示独立研究任务。

## 证据与降级

若 Research 没有获得 PE、PB、EV、可比估值或历史分位：

- 不生成具体估值高低结论。
- 在 limitations 或 evidence coverage 中标记估值数据不可用或不足。
- Quant 的涨跌、波动、回撤和相对收益只能表述为市场行为证据。
- Risk 将“缺少可验证估值指标”列为核心研究缺口。
- Aggregator 必须把该缺口展示给用户，不能静默省略“估值水平”目标。

任何模型输出的估值数字必须能追溯到实际 evidence；本次不新增估值数字来源。

## 测试

自动化测试全部 Mock ArkClient 和 PandaDataClient：

1. 模型仅返回 `company_fundamentals` 时，复合请求仍恢复四个 required dimensions。
2. 单独询问成长性或单独询问历史波动时，不触发该复合校正。
3. Manager prompt 包含四类职责和“市场交叉验证不等于估值”的约束。
4. 缺少任一 required dimension 的计划被 Validator 拒绝。
5. 合法计划可包含两个 Research 步骤、一个 Quant 步骤和一个 Risk 步骤。
6. 缺少估值指标时，聚合结果保留估值证据不足的限制，不产生估值数字。
7. 现有财务质量协作、综合研究和 focused 单维研究测试继续通过。

## 验收标准

输入“评估宁德时代（300750.SZ）的成长性与估值水平”时：

- TaskSpec 不再只有 `company_fundamentals`。
- Manager 计划至少使用 Research、Quant 和 Risk，并覆盖公司、行业、量化与风险维度。
- 前端能观察到多个实际执行步骤及其依赖。
- 最终结果包含成长性证据、市场交叉验证、风险审查和估值证据边界。
- 没有可靠估值数据时明确说证据不足，不给未经支持的估值判断。
