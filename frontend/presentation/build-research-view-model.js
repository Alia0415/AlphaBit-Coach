(function initResearchPresentation(root) {
  "use strict";

  const AGENTS = {
    research: { name: "Research Agent", role: "基本面研究专家" },
    macro: { name: "Macro Agent", role: "宏观研究专家" },
    quant: { name: "Quant Agent", role: "量化研究专家" },
    risk: { name: "Risk Agent", role: "风险质疑专家" },
    portfolio: { name: "Portfolio Agent", role: "组合管理专家" },
    report: { name: "Report Agent", role: "研究整合专家" },
    manager: { name: "Manager Agent", role: "研究经理" },
  };

  const METRICS = {
    revenue_yoy: {
      label: "营业收入同比增长率",
      english: "Revenue Year-over-Year Growth",
      abbr: "Revenue YoY",
      measures: "本期营业收入相较上年同期的变化。",
      why: "用于观察业务规模是否扩大，并减少季节性差异的干扰。",
      reading: "正值代表同比增长，负值代表同比下降；单期变化不等于长期趋势。",
      limitation: "需要结合利润、现金流、行业周期和多个报告期判断。",
      combine: "营业利润、毛利率、经营活动现金流",
    },
    operating_profit_yoy: {
      label: "营业利润同比增长率",
      english: "Operating Profit Year-over-Year Growth",
      abbr: "Operating Profit YoY",
      measures: "本期营业利润相较上年同期的变化。",
      why: "用于观察主营经营成果的变化方向。",
      reading: "需与收入变化共同阅读，判断利润改善是否与业务增长同步。",
      limitation: "可能受费用、资产减值、基数或一次性因素影响。",
      combine: "营业收入、毛利率、费用率、扣非净利润、经营活动现金流",
    },
    net_profit_yoy: {
      label: "净利润同比增长率",
      english: "Net Profit Year-over-Year Growth",
      abbr: "Net Profit YoY",
      measures: "本期归属利润相较上年同期的变化。",
      why: "用于观察公司最终盈利结果的变化。",
      reading: "增长只说明变化方向，不能单独证明盈利质量改善。",
      limitation: "可能包含非经常性损益，需要结合扣非净利润与现金流。",
      combine: "扣非净利润、营业利润、经营活动现金流",
    },
    net_profit_excluding_nonrecurring_yoy: {
      label: "扣非净利润同比增长率",
      english: "Recurring Net Profit Year-over-Year Growth",
      abbr: "Recurring Profit YoY",
      measures: "剔除非经常性损益后的净利润同比变化。",
      why: "更接近持续经营活动带来的盈利变化。",
      reading: "与净利润方向不同时，需要检查补贴、处置收益等一次性项目。",
      limitation: "扣非口径仍不能替代现金流和业务分部分析。",
      combine: "净利润、营业利润、经营活动现金流",
    },
    gross_margin: {
      label: "毛利率",
      english: "Gross Margin",
      abbr: "GM",
      measures: "每一元营业收入扣除营业成本后保留的比例。",
      why: "用于观察产品定价、成本控制和业务结构的综合结果。",
      reading: "上升可能来自提价、成本下降或产品结构变化，原因仍需验证。",
      limitation: "不包含销售、管理、研发等期间费用。",
      combine: "营业利润率、费用率、收入增长率",
    },
    operating_margin: {
      label: "营业利润率",
      english: "Operating Margin",
      abbr: "OM",
      measures: "营业利润占营业收入的比例。",
      why: "用于观察主营经营活动的盈利效率。",
      reading: "变化应与毛利率和费用率一起拆解。",
      limitation: "单个报告期可能受费用确认节奏和基数影响。",
      combine: "毛利率、销售费用率、管理费用率、收入增长率",
    },
    net_margin: {
      label: "净利率",
      english: "Net Profit Margin",
      abbr: "NPM",
      measures: "净利润占营业收入的比例。",
      why: "用于观察收入最终转化为净利润的效率。",
      reading: "需要区分主营经营贡献与非经常性损益。",
      limitation: "不能替代现金流质量分析。",
      combine: "营业利润率、扣非净利润、经营活动现金流",
    },
    operating_cash_flow_to_net_profit: {
      label: "经营现金流与净利润比",
      english: "Operating Cash Flow to Net Profit",
      abbr: "OCF / Net Profit",
      measures: "经营活动现金流对账面净利润的覆盖程度。",
      why: "用于检查利润是否较好地转化为现金。",
      reading: "长期明显偏低通常需要继续检查应收账款、存货和收入确认。",
      limitation: "单期现金流可能受营运资金季节性影响。",
      combine: "应收账款、存货、收入增长率、连续多期现金流",
    },
    asset_liability_ratio: {
      label: "资产负债率",
      english: "Debt-to-Asset Ratio",
      abbr: "D/A",
      measures: "总负债占总资产的比例。",
      why: "用于观察公司资产结构中的债务承担程度。",
      reading: "高低没有跨行业统一答案，应结合行业资本强度和偿债能力。",
      limitation: "不能单独反映债务期限、利率和现金流覆盖能力。",
      combine: "流动比率、经营现金流、利息保障倍数",
    },
    current_ratio: {
      label: "流动比率",
      english: "Current Ratio",
      abbr: "CR",
      measures: "流动资产对流动负债的覆盖倍数。",
      why: "用于观察短期偿债资源是否充足。",
      reading: "偏低可能提示短期偿债压力，偏高也可能代表资产使用效率不足。",
      limitation: "流动资产的实际变现能力并不完全相同。",
      combine: "速动比率、经营现金流、短期借款",
    },
    accounts_receivable_to_revenue: {
      label: "应收账款收入比",
      english: "Accounts Receivable to Revenue",
      abbr: "AR / Revenue",
      measures: "应收账款相对于营业收入的规模。",
      why: "用于检查收入增长是否伴随回款压力上升。",
      reading: "持续上升时应进一步检查账龄、客户质量和坏账准备。",
      limitation: "不同结算模式和行业账期不可直接横向类比。",
      combine: "收入增长率、经营现金流、坏账准备",
    },
    inventory_to_revenue: {
      label: "存货收入比",
      english: "Inventory to Revenue",
      abbr: "Inventory / Revenue",
      measures: "存货相对于营业收入的规模。",
      why: "用于观察库存积压和经营周转压力。",
      reading: "持续上升可能来自备货、销售放缓或价格变化，需要结合业务解释。",
      limitation: "季节性备货和原材料价格会影响单期结果。",
      combine: "存货周转率、收入增长率、毛利率",
    },
    total_asset_turnover: {
      label: "总资产周转率",
      english: "Total Asset Turnover",
      abbr: "TAT",
      measures: "资产产生营业收入的效率。",
      why: "用于观察公司使用资产创造收入的能力。",
      reading: "应结合行业资产模式和盈利水平判断。",
      limitation: "高周转不一定代表高盈利，低周转也可能来自重资产模式。",
      combine: "净利率、资产收益率、收入增长率",
    },
    maximum_drawdown: {
      label: "最大回撤",
      english: "Maximum Drawdown",
      abbr: "MDD",
      measures: "观察区间内从阶段高点到随后低点的最大跌幅。",
      why: "用于理解历史上可能经历的最大阶段性损失。",
      reading: "绝对值越大，历史阶段性下跌越深。",
      limitation: "历史最大回撤不代表未来损失上限。",
      combine: "波动率、收益率、回撤持续时间",
    },
    annualized_volatility: {
      label: "年化波动率",
      english: "Annualized Volatility",
      abbr: "Ann. Vol.",
      measures: "将观察期收益波动换算为年度尺度。",
      why: "用于比较不同标的或策略的历史波动风险。",
      reading: "数值越高，历史价格波动通常越剧烈。",
      limitation: "波动率不区分上涨和下跌，也不能覆盖尾部风险。",
      combine: "最大回撤、收益率、下行波动",
    },
    daily_volatility: {
      label: "日波动率",
      english: "Daily Volatility",
      abbr: "Daily Vol.",
      measures: "日收益变化的离散程度。",
      why: "用于观察短期价格波动强弱。",
      reading: "数值越高，日度价格变化通常越不稳定。",
      limitation: "不能单独代表长期风险或亏损概率。",
      combine: "年化波动率、最大回撤、成交量",
    },
    period_return: {
      label: "区间收益率",
      english: "Period Return",
      abbr: "Return",
      measures: "标的在指定起止区间内的价格变化比例。",
      why: "用于描述本次研究区间内的历史表现。",
      reading: "正值代表区间上涨，负值代表区间下跌。",
      limitation: "历史区间收益不能直接外推为未来收益。",
      combine: "最大回撤、波动率、基准收益",
    },
    coverage_ratio: {
      label: "数据覆盖率",
      english: "Data Coverage Ratio",
      abbr: "Coverage",
      measures: "可参与本次计算的数据占应有数据的比例。",
      why: "用于判断计算是否受到缺失值影响。",
      reading: "越接近 100%，数据缺口通常越少，但不代表研究结论已经有效。",
      limitation: "覆盖完整不等于数据无偏，也不等于策略可获利。",
      combine: "样本范围、缺失分布、样本外验证",
    },
    observation_count: {
      label: "有效观察数量",
      english: "Observation Count",
      abbr: "N",
      measures: "本次分析实际使用的有效样本数量。",
      why: "用于理解结论所依赖的样本规模。",
      reading: "样本更多通常有利于稳定估计，但不能自动消除偏差。",
      limitation: "样本独立性、代表性和时间跨度同样重要。",
      combine: "样本期间、覆盖率、分组数量",
    },
    r020: {
      label: "R020 成交量扩张因子",
      english: "Five-Day Volume Expansion Z-Score",
      abbr: "R020",
      measures: "成交量相对五日滚动均值的标准化偏离程度。",
      why: "用于描述本次区间内成交量扩张或收缩的相对强弱。",
      reading: "正值表示成交量相对扩张，负值表示相对收缩；它不是涨跌预测。",
      limitation: "未经因子有效性、样本外和交易成本验证，不能据此推断未来收益。",
      combine: "后续收益、波动率、交易成本、样本外检验",
    },
  };

  const STATUS = {
    waiting: { label: "等待前置研究", tone: "waiting" },
    working: { label: "正在研究", tone: "working" },
    completed: { label: "已完成", tone: "completed" },
    partial: { label: "部分完成", tone: "partial" },
    failed: { label: "无法完成", tone: "failed" },
    blocked: { label: "等待依赖", tone: "waiting" },
  };

  const CONFIDENCE = {
    high: "较高",
    medium: "中等",
    low: "较低",
    not_applicable: "暂不适用",
  };

  const STANCE = {
    positive: "积极",
    cautiously_positive: "谨慎积极",
    neutral: "中性",
    mixed: "信号不一",
    cautiously_negative: "谨慎偏弱",
    negative: "偏弱",
    insufficient_evidence: "证据不足",
    not_applicable: "暂不适用",
  };

  const FORBIDDEN_KEYS =
    /(api|prompt|token|request|url|database|stack|trace|workflow|task.?id|skill.?id|source.?step|runtime|file.?path|local.?path|method|model|section|row.?count|record.?count|raw|sse|tool.?calls?)/i;
  const FORBIDDEN_TEXT =
    /(PandaData|get_fina_[A-Za-z0-9_]+|get_stock_[A-Za-z0-9_]+|pandadata_[A-Za-z0-9_]+|source_step|skill[_ -]?id|workflow[_ -]?id|task[_ -]?id|result_aggregator|https?:\/\/\S+|\/api\/[A-Za-z0-9_/?=&.-]+|\bAPI\b|\bprompt\b|\btoken\b|\bdatabase\b|\brequest[ _-]?url\b|\bmethod\b|\bmodel\b|\bDeepSeek\b|\bVolcano Ark\b|\bSSE\b)/gi;
  const INTERNAL_STEP = /\b(?:research|macro|quant|risk|portfolio|report)_[A-Za-z0-9_-]*\d+\b/gi;

  function agentInfo(id) {
    return AGENTS[String(id || "").toLowerCase()] || {
      name: "AI 投研专家",
      role: "专业研究专家",
    };
  }

  function publicText(value, fallback = "") {
    if (value == null) return fallback;
    const raw = String(value);
    if (/^\s*[\[{]/.test(raw) && /["'][^"']+["']\s*:/.test(raw)) {
      return fallback || "该部分仅保留用户可见的研究摘要。";
    }
    let text = raw
      .replace(FORBIDDEN_TEXT, "专业数据源")
      .replace(INTERNAL_STEP, "对应专家步骤")
      .replace(/\bcomputed_not_validated\b/gi, "已完成计算，尚未验证有效性")
      .replace(/\bmethodology_verified\b/gi, "研究方法已核对")
      .replace(/\bunverified\b/gi, "尚未验证")
      .replace(/\bno_data\b/gi, "暂无有效数据")
      .replace(/\bskill\b/gi, "专业分析")
      .replace(/\b[a-z][a-z0-9]+(?:_[a-z0-9]+){1,}\b/g, "专业研究方法")
      .replace(/\b(?:CI|IR|MB)\d{6,}\b/g, "对应宏观指标")
      .replace(/\b[A-Za-z]:\\[^\s]+|\/(?:home|Users|var|opt|srv)\/[^\s]+/g, "内部信息")
      .replace(/\b-?\d+\.\d{5,}\b/g, (raw) => {
        const number = Number(raw);
        return Number.isFinite(number) ? number.toFixed(4) : raw;
      })
      .replace(/[*#`>|]+/g, "")
      .replace(/\s+/g, " ")
      .trim();
    return text || fallback;
  }

  function snippet(value, max = 240) {
    const text = publicText(value);
    return text.length > max ? `${text.slice(0, max).trim()}…` : text;
  }

  function cleanFormula(value) {
    const formula = publicText(value);
    if (!formula || /专业研究信息/.test(formula)) return "";
    return formula.replace(/\b[A-Za-z_][A-Za-z0-9_]{2,}\b/g, (token) => {
      const known = METRICS[token];
      return known ? known.label : "相关数值";
    });
  }

  function unique(values) {
    const seen = new Set();
    return values.filter((value) => {
      const key = typeof value === "string" ? value : JSON.stringify(value);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function array(value) {
    return Array.isArray(value) ? value : [];
  }

  function object(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function formatNumber(value, metricKey = "") {
    if (typeof value !== "number" || !Number.isFinite(value)) return publicText(value);
    const percentLike =
      /ratio|margin|return|drawdown|volatility|yoy|rate|coverage/.test(metricKey);
    if (percentLike) {
      return new Intl.NumberFormat("zh-CN", {
        style: "percent",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    }
    return new Intl.NumberFormat("zh-CN", {
      maximumFractionDigits: 2,
    }).format(value);
  }

  function metricCard(metric, sourceSteps) {
    const item = object(metric);
    const key = String(item.metric || item.key || "").trim();
    const rawLabel = publicText(item.label);
    const knowledge = METRICS[key] || (/R020/i.test(rawLabel) ? METRICS.r020 : {});
    const label = rawLabel || knowledge.label || "研究指标";
    const displayValue = publicText(
      item.display_value,
      formatNumber(item.value, key) || "本次未形成有效数值",
    );
    const formula = cleanFormula(item.formula);
    const explanation = publicText(item.explanation);
    const usableExplanation =
      explanation && !/专业字段|专业研究方法|专业研究信息/.test(explanation)
        ? explanation
        : "";
    const subject = publicText(item.subject || item.period);
    return {
      id: `metric-${Math.random().toString(36).slice(2, 9)}`,
      key,
      label,
      english: knowledge.english || "",
      abbreviation: knowledge.abbr || "",
      value: displayValue,
      subject,
      purpose: knowledge.measures || usableExplanation || "用于回答本次研究中的对应专业问题。",
      importance: knowledge.why || usableExplanation || "该指标是本次证据链中的一项量化证据。",
      formula,
      reading: knowledge.reading || usableExplanation || "需要结合本次其他证据共同理解。",
      interpretation: usableExplanation || knowledge.reading || "需要结合本次其他证据共同理解。",
      limitation: knowledge.limitation || "单个指标不能独立支持完整投资结论。",
      combineWith: knowledge.combine || "本次报告中的其他事实与风险证据",
      sourceSteps: unique(array(sourceSteps).map(String)),
    };
  }

  function collectMetrics(aggregation) {
    const metrics = [];
    array(aggregation.content_blocks).forEach((block) => {
      const data = object(block && block.data);
      array(data.metrics).forEach((item) => {
        metrics.push(metricCard(item, block.source_steps));
      });
      array(data.entities).forEach((entity) => {
        array(entity && entity.metrics).forEach((item) => {
          metrics.push(metricCard(
            { ...object(item), subject: item.subject || entity.name },
            block.source_steps,
          ));
        });
      });
    });
    const bySignature = new Map();
    metrics
      .filter((metric) => !(
        metric.key === "observation_count"
        && metric.subject === "对应宏观指标"
      ))
      .forEach((metric) => {
      const signature = `${metric.label}|${metric.value}|${metric.subject}`;
      if (!bySignature.has(signature)) bySignature.set(signature, metric);
    });
    const priority = (metric) => {
      if (/yoy$/.test(metric.key)) return 0;
      if (/margin|cash_flow|turnover/.test(metric.key)) return 1;
      if (/liability|current_ratio|receivable|inventory/.test(metric.key)) return 2;
      if (/R020/i.test(metric.label)) return 3;
      if (metric.key === "coverage_ratio") return 4;
      if (/observation_count|non_null_count/.test(metric.key)) return 8;
      return 5;
    };
    return [...bySignature.values()]
      .sort((left, right) => priority(left) - priority(right))
      .slice(0, 24);
  }

  function normalizeResultItem(item, fallbackType = "judgment") {
    if (typeof item === "string") {
      return { text: publicText(item), type: fallbackType, sourceSteps: [] };
    }
    const value = object(item);
    const text = publicText(value.text || value.title);
    return {
      text,
      title: publicText(value.title),
      type: publicText(value.evidence_type, fallbackType),
      sourceSteps: unique(array(value.source_steps || value.source_step).map(String)),
    };
  }

  function resultItems(aggregation, key, fallbackType) {
    return array(aggregation[key])
      .map((item) => normalizeResultItem(item, fallbackType))
      .filter((item) => item.text);
  }

  function blockItems(aggregation, types, fallbackType) {
    return array(aggregation.content_blocks).flatMap((block) => {
      if (!types.includes(block && block.type)) return [];
      return array(object(block.data).items).map((item) => {
        const normalized = normalizeResultItem(item, fallbackType);
        if (!normalized.sourceSteps.length) {
          normalized.sourceSteps = unique(array(block.source_steps).map(String));
        }
        return normalized;
      });
    }).filter((item) => item.text);
  }

  function dataType(source) {
    const item = object(source);
    const text = JSON.stringify(item).toLowerCase();
    if (/audit|审计/.test(text)) return "审计意见";
    if (/forecast|预告/.test(text)) return "业绩预告";
    if (/financial|fina|report_period|利润|营收|财务/.test(text)) return "财务报表";
    if (/macro|indicator|利率|政策|宏观/.test(text)) return "宏观与行业数据";
    if (/event|事件/.test(text)) return "事件风险信息";
    if (/portfolio|position|holding|组合|持仓/.test(text)) return "组合与持仓信息";
    if (/price|market|symbol|start_date|end_date|行情/.test(text)) return "历史市场数据";
    return "研究证据";
  }

  function coverageItem(source) {
    const item = object(source);
    const statusValue = String(item.missing_status || item.status || "").toLowerCase();
    const status =
      /no_data|missing|unavailable|failed/.test(statusValue) ? "missing"
        : /partial/.test(statusValue) ? "partial"
          : "available";
    const range = object(item.query_range);
    const period = publicText(
      [
        range.start_period || item.start_date,
        range.end_period || item.end_date,
      ].filter(Boolean).join(" 至 ")
      || item.latest_report_period
      || item.period,
    );
    const type = dataType(item);
    return {
      type,
      status,
      period,
      latestPeriod: publicText(item.latest_report_period),
      purpose: `用于支持本次${type}相关问题的判断。`,
      impact: status === "missing"
        ? `当前未获取到有效${type}，相关判断不会被补造，结论置信度会相应降低。`
        : status === "partial"
          ? `${type}仅部分覆盖，相关结论需要保留条件。`
          : `${type}已用于本次研究。`,
    };
  }

  function collectCoverage(aggregation, results) {
    const sources = [
      ...array(aggregation.data_scope),
      ...array(aggregation.content_blocks).flatMap((block) =>
        block && block.type === "data_scope" ? array(object(block.data).sources) : []
      ),
      ...Object.values(results).flatMap((result) => array(result && result.data_sources)),
    ];
    const grouped = new Map();
    sources.forEach((source) => {
      const item = coverageItem(source);
      if (!grouped.has(item.type)) grouped.set(item.type, []);
      grouped.get(item.type).push(item);
    });
    return [...grouped.entries()].map(([type, items]) => {
      const statuses = new Set(items.map((item) => item.status));
      const status = statuses.size === 1
        ? items[0].status
        : statuses.has("available")
          ? "partial"
          : statuses.has("partial") ? "partial" : "missing";
      const periods = unique(items.map((item) => item.period).filter(Boolean));
      return {
        type,
        status,
        period: periods.join("；"),
        latestPeriod: unique(items.map((item) => item.latestPeriod).filter(Boolean)).join("；"),
        purpose: `用于支持本次${type}相关问题的判断。`,
        impact: status === "missing"
          ? `当前未获取到有效${type}，相关判断不会被补造，结论置信度会相应降低。`
          : status === "partial"
            ? `${type}存在部分期间或字段缺失，相关结论需要保留条件。`
            : `${type}已用于本次研究。`,
      };
    });
  }

  function intersects(left, right) {
    const set = new Set(left);
    return right.some((item) => set.has(item));
  }

  function resultStatus(result, coverage) {
    if (!result) return "waiting";
    if (result.status === "failed") return "failed";
    if (result.status === "blocked") return "blocked";
    if (coverage.some((item) => item.status !== "available")) return "partial";
    return "completed";
  }

  function sourceResults(aggregation) {
    return object(object(aggregation.technical_evidence).source_results);
  }

  function planSteps(plan) {
    return array(plan.steps).map((step) => ({
      id: String(step.id || ""),
      agent: String(step.agent || ""),
      objective: publicText(step.objective, "完成对应专业研究"),
      expectedOutput: publicText(step.expected_output),
      dependsOn: array(step.depends_on).map(String),
    }));
  }

  function buildPlan(task, aggregation) {
    const rawPlan = object(task.plan);
    const steps = planSteps(rawPlan);
    const selections = array(rawPlan.selected_agents);
    const byId = Object.fromEntries(steps.map((step) => [step.id, step]));
    const dependencies = steps.flatMap((step) =>
      step.dependsOn.map((dependency) => ({
        from: agentInfo(byId[dependency] && byId[dependency].agent).name,
        to: agentInfo(step.agent).name,
        reason: step.objective,
      }))
    );
    const layers = [];
    const depthMemo = {};
    function depth(step, seen = new Set()) {
      if (depthMemo[step.id] != null) return depthMemo[step.id];
      if (!step.dependsOn.length || seen.has(step.id)) return 0;
      seen.add(step.id);
      depthMemo[step.id] = 1 + Math.max(
        ...step.dependsOn.map((id) => byId[id] ? depth(byId[id], seen) : 0),
      );
      return depthMemo[step.id];
    }
    steps.forEach((step) => {
      const layer = depth(step);
      if (!layers[layer]) layers[layer] = [];
      layers[layer].push(agentInfo(step.agent).name);
    });
    return {
      originalQuestion: publicText(task.prompt || aggregation.user_goal),
      goal: publicText(rawPlan.goal || aggregation.user_goal),
      intent: publicText(rawPlan.intent),
      researchQuestions: steps.map((step, index) => ({
        order: index + 1,
        question: step.objective,
        agent: agentInfo(step.agent).name,
        role: agentInfo(step.agent).role,
        output: step.expectedOutput,
      })),
      agents: selections.map((selection) => ({
        id: String(selection.agent || ""),
        ...agentInfo(selection.agent),
        reason: publicText(selection.reason, "本次研究需要该专家的专业能力。"),
      })),
      dependencies,
      parallelGroups: layers
        .filter((layer) => layer && layer.length > 1)
        .map((layer) => unique(layer)),
      synthesis: steps
        .filter((step) => step.agent === "report")
        .map((step) => step.objective)[0]
        || "由结果整合层仅根据本次已完成的真实证据形成统一报告。",
      rawSteps: steps,
    };
  }

  function buildAgents(plan, aggregation, results, metrics, coverage) {
    const facts = unique([
      ...resultItems(aggregation, "evidence_summary", "fact"),
      ...blockItems(aggregation, ["metric_cards"], "fact"),
    ]);
    const findings = unique([
      ...resultItems(aggregation, "key_findings", "judgment"),
      ...blockItems(aggregation, ["finding_cards", "narrative"], "judgment"),
    ]);
    const globalActions = resultItems(aggregation, "next_research_steps", "research_action");
    const globalRisks = resultItems(aggregation, "risks", "risk");
    const globalLimitations = resultItems(aggregation, "limitations", "limitation");

    return plan.agents.map((agent) => {
      const steps = plan.rawSteps.filter((step) => step.agent === agent.id);
      const stepIds = steps.map((step) => step.id);
      const matchingResults = stepIds.map((id) => results[id]).filter(Boolean);
      const result = matchingResults[matchingResults.length - 1] || null;
      const agentCoverage = array(result && result.data_sources).map(coverageItem);
      const agentMetrics = metrics.filter((metric) =>
        !metric.sourceSteps.length || intersects(metric.sourceSteps, stepIds)
      );
      const agentFacts = facts.filter((item) =>
        !item.sourceSteps.length || intersects(item.sourceSteps, stepIds)
      );
      const agentFindings = findings.filter((item) =>
        !item.sourceSteps.length || intersects(item.sourceSteps, stepIds)
      );
      const limitations = unique([
        ...array(result && result.limitations).map((text) => publicText(text)),
        ...globalLimitations
          .filter((item) => !item.sourceSteps.length || intersects(item.sourceSteps, stepIds))
          .map((item) => item.text),
      ]).filter(Boolean);
      const nextChecks = unique([
        ...array(result && result.recommendations).map((text) => publicText(text)),
        ...globalActions
          .filter((item) => !item.sourceSteps.length || intersects(item.sourceSteps, stepIds))
          .map((item) => item.text),
        ...limitations.map((item) => `进一步验证：${item}`),
      ]).filter(Boolean);
      const assumptions = unique([
        ...array(result && result.assumptions).map((text) => publicText(text)),
        ...resultItems(aggregation, "assumptions", "assumption")
          .filter((item) => !item.sourceSteps.length || intersects(item.sourceSteps, stepIds))
          .map((item) => item.text),
      ]).filter(Boolean);
      const riskChallenges = unique([
        ...array(result && result.risks).map((text) => publicText(text)),
        ...globalRisks
          .filter((item) => !item.sourceSteps.length || intersects(item.sourceSteps, stepIds))
          .map((item) => item.text),
      ]).filter(Boolean);
      const rawSummary = publicText(result && result.summary);
      const summary = agent.id === "report" && rawSummary.length > 500
        ? "已综合本次实际完成的专家证据并形成正式研究报告。"
        : snippet(rawSummary, 520);
      const misconceptions = limitations.slice(0, 3).map((limitation) => ({
        wrong: summary
          ? `把“${summary.slice(0, 48)}${summary.length > 48 ? "…" : ""}”理解为无条件成立`
          : "把本次阶段性结果理解为已经完全证实",
        correct: limitation,
      }));
      const status = resultStatus(result, agentCoverage);
      return {
        id: agent.id,
        name: agent.name,
        role: agent.role,
        reason: agent.reason,
        status,
        statusLabel: (STATUS[status] || STATUS.waiting).label,
        researchQuestion: steps.map((step) => step.objective).join("；")
          || "完成本次分配的专业研究问题",
        analysisDimensions: unique(
          steps.flatMap((step) => [step.objective, step.expectedOutput]).filter(Boolean),
        ),
        facts: unique([
          ...agentMetrics.map((metric) => ({
            text: `${metric.label}：${metric.value}${metric.subject ? `（${metric.subject}）` : ""}`,
            type: "fact",
          })),
          ...agentFacts.map((item) => ({ text: item.text, type: item.type || "fact" })),
        ]),
        metrics: agentMetrics,
        interpretations: unique([
          ...agentFindings.map((item) => item.text),
          ...(summary ? [summary] : []),
        ]),
        hypotheses: assumptions,
        nextChecks,
        misconceptions,
        challenges: riskChallenges,
        terms: agentMetrics,
        emptyReason: !result
          ? "该专家本次尚未返回结果，因此不展示推测性内容。"
          : "",
      };
    });
  }

  function buildEvidenceChains(aggregation, metrics) {
    const findings = unique([
      ...resultItems(aggregation, "key_findings", "judgment"),
      ...blockItems(aggregation, ["finding_cards", "narrative"], "judgment"),
    ]);
    const evidence = resultItems(aggregation, "evidence_summary", "fact");
    const risks = resultItems(aggregation, "risks", "risk");
    const limitations = resultItems(aggregation, "limitations", "limitation");
    const conflicts = array(object(aggregation.technical_evidence).conflicts)
      .map((text) => publicText(text))
      .filter(Boolean);
    const confidence = CONFIDENCE[object(aggregation.direct_answer).confidence]
      || "暂无法判断";
    const seeds = findings.length
      ? findings
      : metrics.slice(0, 3).map((metric) => ({
          text: `${metric.label}为${metric.value}`,
          sourceSteps: metric.sourceSteps,
        }));
    return seeds.slice(0, 6).map((finding, index) => {
      const steps = array(finding.sourceSteps);
      const conclusion = publicText(finding.text);
      const namedMetrics = metrics.filter((metric) =>
        metric.label && conclusion.includes(metric.label)
      );
      const stepMetrics = steps.length
        ? metrics.filter((metric) =>
          metric.sourceSteps.length && intersects(metric.sourceSteps, steps)
        )
        : [];
      const relatedMetrics = namedMetrics.length
        ? namedMetrics
        : stepMetrics.length
          ? stepMetrics
          : metrics.slice(index, index + 1);
      const relatedEvidence = steps.length
        ? evidence.filter((item) =>
          item.sourceSteps.length && intersects(item.sourceSteps, steps)
        )
        : evidence.filter((item) =>
          relatedMetrics.some((metric) =>
            metric.label && item.text.includes(metric.label)
          )
        );
      return {
        id: `chain-${index + 1}`,
        conclusion,
        facts: unique([
          ...relatedMetrics.map((metric) => `${metric.label}：${metric.value}`),
          ...relatedEvidence.map((item) => item.text),
        ]).slice(0, 6),
        calculation: relatedMetrics
          .filter((metric) => metric.formula)
          .map((metric) => `${metric.label}：${metric.formula}`),
        supporting: relatedEvidence.map((item) => item.text).slice(0, 5),
        opposing: unique([...risks.map((item) => item.text), ...conflicts]).slice(0, 5),
        missing: limitations.map((item) => item.text).slice(0, 5),
        strength: confidence,
        nextChecks: resultItems(aggregation, "next_research_steps", "research_action")
          .map((item) => item.text)
          .slice(0, 5),
      };
    });
  }

  function collectReportText(aggregation) {
    return array(aggregation.content_blocks)
      .filter((block) => block && block.type === "report")
      .map((block) => publicText(object(block.data).content))
      .filter(Boolean)[0] || "";
  }

  function learningQuiz(metrics, limitations, findings) {
    const metric = metrics[0];
    if (metric) {
      const correct = metric.interpretation || metric.reading
        || "它是本次证据的一部分，需要结合其他指标与风险验证。";
      return {
        question: `本次研究中，${metric.label}为${metric.value}。最专业的理解是什么？`,
        options: [
          "这个数字可以直接决定未来收益",
          correct,
          "只要该指标为正，其他证据都可以忽略",
          "这个结果已经证明结论在所有时期都成立",
        ],
        answerIndex: 1,
        explanation: metric.limitation,
      };
    }
    const limitation = limitations[0] && limitations[0].text;
    const finding = findings[0] && findings[0].text;
    return {
      question: finding
        ? `面对“${finding.slice(0, 56)}${finding.length > 56 ? "…" : ""}”这一阶段性判断，下一步最合理的做法是什么？`
        : "当本次研究证据不足时，最专业的处理方式是什么？",
      options: [
        "把阶段性判断直接当成确定结论",
        limitation || "明确证据缺口，并继续验证影响结论的关键条件",
        "用与本次任务无关的案例补齐结论",
        "忽略缺失信息以保持结论简洁",
      ],
      answerIndex: 1,
      explanation: limitation || "专业研究需要保留证据边界，不能把推测写成事实。",
    };
  }

  function oneLineConclusion(direct, metrics) {
    const supplied = publicText(direct.headline);
    const generic = /已生成|已完成|完成所需|研究报告/.test(supplied);
    if (!generic && supplied.length >= 20) return supplied;
    const latest = (key) => [...metrics].reverse().find((metric) => metric.key === key);
    const revenue = latest("revenue_yoy");
    const profit = latest("operating_profit_yoy");
    if (revenue && profit) {
      const number = (value) => {
        const match = String(value).replaceAll(",", "").match(/-?\d+(?:\.\d+)?/);
        return match ? Number(match[0]) : null;
      };
      const revenueValue = number(revenue.value);
      const profitValue = number(profit.value);
      let judgment = "收入与营业利润变化需要交叉验证";
      if (revenueValue != null && profitValue != null) {
        if (revenueValue < 0 && profitValue < 0) judgment = "收入与营业利润同步承压";
        else if (revenueValue < 0 && profitValue >= 0) judgment = "收入承压但营业利润改善";
        else if (revenueValue >= 0 && profitValue >= 0) judgment = "收入与营业利润同步增长";
        else judgment = "收入增长但营业利润承压";
      }
      return `营业收入同比为 ${revenue.value}，营业利润同比为 ${profit.value}；${judgment}，持续性仍需结合现金流与风险证据验证。`;
    }
    return supplied || "本次研究已形成阶段性结论，证据强度与限制见下方报告。";
  }

  function buildResearchViewModel(bundle) {
    const source = object(bundle);
    const report = object(source.report || source);
    const task = object(source.task || report.task);
    const aggregation = object(report.aggregation || task.aggregation || source.aggregation);
    const direct = object(aggregation.direct_answer);
    const results = sourceResults(aggregation);
    const plan = buildPlan(task, aggregation);
    const metrics = collectMetrics(aggregation);
    const coverage = collectCoverage(aggregation, results);
    const findings = unique([
      ...resultItems(aggregation, "key_findings", "judgment"),
      ...blockItems(aggregation, ["finding_cards", "narrative"], "judgment"),
    ]);
    const risks = unique([
      ...resultItems(aggregation, "risks", "risk"),
      ...blockItems(aggregation, ["risk_list"], "risk"),
    ]);
    const limitations = unique([
      ...resultItems(aggregation, "limitations", "limitation"),
      ...blockItems(aggregation, ["limitations"], "limitation"),
    ]);
    const agents = buildAgents(plan, aggregation, results, metrics, coverage);
    const completed = agents.filter((agent) =>
      ["completed", "partial"].includes(agent.status)
    );
    const conflicts = array(object(aggregation.technical_evidence).conflicts)
      .map((text) => publicText(text))
      .filter(Boolean);
    const publicMetrics = metrics.map(({ key, sourceSteps, ...metric }) => metric);
    const publicAgents = agents.map((agent) => ({
      ...agent,
      metrics: agent.metrics.map(({ key, sourceSteps, ...metric }) => metric),
      terms: agent.terms.map(({ key, sourceSteps, ...metric }) => metric),
    }));
    const { rawSteps, ...publicPlan } = plan;
    return {
      summary: {
        text: oneLineConclusion(direct, metrics),
        explanation: publicText(direct.explanation),
        confidence: CONFIDENCE[direct.confidence] || "暂无法判断",
        status: STANCE[direct.stance] || "证据状态待确认",
        completionStatus: publicText(aggregation.completion_status, "failed"),
      },
      researchPlan: publicPlan,
      agents: publicAgents,
      metrics: publicMetrics,
      evidenceChains: buildEvidenceChains(aggregation, metrics),
      expertDisagreements: conflicts,
      positiveSignals: findings.map((item) => item.text),
      riskSignals: risks.map((item) => item.text),
      coverage,
      limitations: limitations.map((item) => item.text),
      reportText: collectReportText(aggregation),
      learningSummary: {
        framework: plan.researchQuestions.map((item) =>
          `第 ${item.order} 步：${item.question}`
        ),
        terms: unique(metrics.map((metric) => metric.label)),
        quiz: learningQuiz(metrics, limitations, findings),
      },
      participation: completed.map((agent) => ({
        name: agent.name,
        role: agent.role,
        contribution: snippet(agent.interpretations[0] || agent.researchQuestion, 140),
        status: agent.statusLabel,
      })),
      disclaimer: publicText(aggregation.disclaimer),
      empty: !direct.headline && !agents.length && !metrics.length,
    };
  }

  function translateProgressEvent(event) {
    const item = object(event);
    const agent = agentInfo(item.agent);
    const messages = {
      plan_created: "研究经理已完成问题拆解并组建本次专家团队。",
      step_started: `${agent.name}正在研究：${publicText(item.objective, "本次分配的专业问题")}`,
      skill_plan_created: `${agent.name}已选定本次研究需要的专业方法。`,
      skill_started: `${agent.name}开始执行一项专业分析步骤。`,
      tool_called: `${agent.name}正在核对本次研究需要的信息。`,
      skill_completed: `${agent.name}已完成一项专业分析步骤。`,
      skill_failed: `${agent.name}的一项分析未能完成，最终报告会说明影响。`,
      step_completed: `${agent.name}已完成本次专业研究。`,
      step_failed: `${agent.name}当前无法完成该研究步骤，最终报告将基于其他真实结果生成。`,
      synthesis_started: "研究整合专家正在比对各专家证据并控制结论强度。",
      task_completed: "本次研究已结束，可以查看统一研究报告。",
    };
    return messages[item.type] || "研究团队正在更新本次任务进度。";
  }

  function publicStatus(status) {
    return STATUS[status] || STATUS.waiting;
  }

  function safeObject(value, key = "", depth = 0) {
    if (depth > 6) return null;
    if (FORBIDDEN_KEYS.test(key)) return undefined;
    if (Array.isArray(value)) {
      return value.slice(0, 40)
        .map((item) => safeObject(item, key, depth + 1))
        .filter((item) => item !== undefined);
    }
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value)
          .map(([childKey, childValue]) => [
            childKey,
            safeObject(childValue, childKey, depth + 1),
          ])
          .filter(([, childValue]) => childValue !== undefined),
      );
    }
    return typeof value === "string" ? publicText(value) : value;
  }

  const api = {
    AGENTS,
    METRICS,
    agentInfo,
    buildResearchViewModel,
    formatNumber,
    publicStatus,
    publicText,
    safeObject,
    translateProgressEvent,
  };
  root.AlphaResearchPresentation = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
