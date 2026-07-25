"use strict";

const assert = require("node:assert/strict");
const {
  buildResearchViewModel,
  publicText,
  translateProgressEvent,
} = require("../frontend/presentation/build-research-view-model.js");

function reportBundle() {
  return {
    report: {
      title: "公司基本面研究",
      created_at: "2026-07-25T08:00:00Z",
      completeness: {
        planned_steps: 3,
        completed_steps: 3,
        failed_steps: 0,
        blocked_steps: 0,
        completion_ratio: 1,
      },
      aggregation: {
        user_goal: "分析公司基本面是否正在改善",
        completion_status: "completed",
        task_understanding: {
          task_type: "company_research",
        },
        direct_answer: {
          headline: "收入同比下降 9.70%，营业利润同比增长 19.24%，盈利改善原因仍需验证。",
          explanation: "收入与利润变化方向不同，现阶段只能确认盈利表现优于收入表现。",
          confidence: "medium",
          stance: "cautiously_positive",
        },
        key_findings: [
          {
            text: "盈利表现优于收入表现。",
            evidence_type: "judgment",
            source_steps: ["research_1"],
          },
        ],
        evidence_summary: [
          {
            text: "营业收入同比下降 9.70%。",
            evidence_type: "fact",
            source_steps: ["research_1"],
          },
          {
            text: "营业利润同比增长 19.24%。",
            evidence_type: "fact",
            source_steps: ["research_1"],
          },
        ],
        risks: [
          {
            text: "利润改善可能来自费用压缩或低基数。",
            evidence_type: "risk",
            source_steps: ["risk_2"],
          },
        ],
        limitations: [
          {
            text: "尚未验证经营现金流是否同步改善。",
            evidence_type: "limitation",
            source_steps: ["research_1"],
          },
        ],
        next_research_steps: [
          {
            text: "继续检查毛利率、费用率和经营活动现金流。",
            evidence_type: "research_action",
            source_steps: ["research_1"],
          },
        ],
        content_blocks: [
          {
            type: "metric_cards",
            source_steps: ["research_1"],
            data: {
              metrics: [
                {
                  metric: "revenue_yoy",
                  label: "营业收入同比增长率",
                  value: -0.097000000012,
                  display_value: "-9.70%",
                  subject: "2024 年第四季度",
                  formula: "（本期营业收入 / 上年同期营业收入 - 1）× 100%",
                  method: "get_fina_reports",
                  explanation: "本期营业收入低于上年同期。",
                },
                {
                  metric: "operating_profit_yoy",
                  label: "营业利润同比增长率",
                  value: 0.192400000031,
                  display_value: "19.24%",
                  subject: "2024 年第四季度",
                  formula: "（本期营业利润 / 上年同期营业利润 - 1）× 100%",
                  explanation: "本期营业利润高于上年同期。",
                },
              ],
            },
          },
        ],
        data_scope: [
          {
            name: "PandaData",
            method: "get_fina_reports",
            missing_status: "available",
            latest_report_period: "2024q4",
            row_count: 8,
          },
          {
            name: "PandaData",
            method: "get_fina_forecast",
            missing_status: "no_data",
            row_count: 0,
          },
        ],
        technical_evidence: {
          conflicts: ["Research Agent 与 Risk Agent 对持续性的判断强度不同。"],
          source_results: {
            research_1: {
              agent: "research",
              status: "completed",
              summary: "盈利表现优于收入表现，但持续性需要验证。",
              assumptions: ["当前报告期口径可比。"],
              risks: [],
              limitations: ["尚未验证经营现金流。"],
              recommendations: ["继续检查现金流和费用率。"],
              data_sources: [
                {
                  name: "PandaData",
                  method: "get_fina_reports",
                  missing_status: "available",
                  latest_report_period: "2024q4",
                },
              ],
            },
            risk_2: {
              agent: "risk",
              status: "completed",
              summary: "持续性证据仍然不足。",
              assumptions: [],
              risks: ["存在低基数效应的可能。"],
              limitations: ["缺少连续多个季度验证。"],
              recommendations: ["补充多期趋势。"],
              data_sources: [],
            },
            report_3: {
              agent: "report",
              status: "completed",
              summary: "综合结论已形成。",
              assumptions: [],
              risks: [],
              limitations: [],
              recommendations: [],
              data_sources: [],
            },
          },
        },
        disclaimer: "仅用于研究，不构成投资建议。",
      },
    },
    task: {
      prompt: "分析这家公司的基本面是否正在改善。",
      plan: {
        goal: "判断公司基本面是否正在改善",
        intent: "company_research",
        selected_agents: [
          { agent: "research", reason: "分析财务事实和指标组合" },
          { agent: "risk", reason: "挑战改善结论的可靠性" },
          { agent: "report", reason: "综合真实证据形成结论" },
        ],
        steps: [
          {
            id: "research_1",
            agent: "research",
            objective: "收入和利润是否同步改善",
            expected_output: "财务事实与指标解释",
            depends_on: [],
          },
          {
            id: "risk_2",
            agent: "risk",
            objective: "改善是否可持续",
            expected_output: "反对证据与缺口",
            depends_on: ["research_1"],
          },
          {
            id: "report_3",
            agent: "report",
            objective: "形成带条件的综合判断",
            expected_output: "统一研究报告",
            depends_on: ["research_1", "risk_2"],
          },
        ],
      },
    },
  };
}

{
  const vm = buildResearchViewModel(reportBundle());
  assert.equal(vm.summary.confidence, "中等");
  assert.equal(vm.researchPlan.originalQuestion, "分析这家公司的基本面是否正在改善。");
  assert.deepEqual(vm.agents.map((agent) => agent.id), ["research", "risk"]);
  assert.equal(vm.agents.some((agent) => agent.id === "macro"), false);
  assert.deepEqual(vm.chapters.map((chapter) => chapter.title), ["公司与财务", "风险审查"]);
  assert.deepEqual(
    vm.navigation.map((section) => section.label),
    ["结论速览", "公司与财务", "风险审查", "证据边界", "学习总结"],
  );
  vm.chapters.forEach((chapter) => {
    assert.ok(chapter.researchQuestion);
    assert.ok(chapter.methods.length);
    assert.ok(chapter.interpretations.length);
    assert.ok(chapter.boundaries.length);
    assert.ok(chapter.misconceptions.length);
    assert.ok(chapter.coach.oneLine);
  });
  assert.equal(vm.metrics[0].value, "-9.70%");
  assert.match(vm.metrics[0].formula, /本期营业收入/);
  assert.equal(vm.coverage.some((item) => item.status === "missing"), true);
  assert.match(vm.learningSummary.quiz.question, /营业收入同比增长率/);
  assert.equal(vm.learningSummary.quiz.answerIndex, 1);
  assert.equal(vm.evidenceChains.length > 0, true);
  assert.ok(vm.finalSummary);
  assert.equal(
    vm.finalSummary.conclusion.headline,
    "收入同比下降 9.70%，营业利润同比增长 19.24%，盈利改善原因仍需验证。",
  );
  assert.equal(vm.finalSummary.conclusion.stance, "谨慎积极");
  assert.equal(vm.finalSummary.conclusion.confidence, "中等");
  assert.equal(vm.finalSummary.evidence.length <= 3, true);
  assert.equal(vm.finalSummary.uncertainties.length <= 3, true);
  assert.deepEqual(vm.finalSummary.learning, {
    title: "如何判断公司基本面是否真正改善",
    methods: [
      "先看收入变化，判断业务是否增长",
      "再看利润变化，判断盈利能力是否提升",
      "检查现金流，判断利润质量",
      "观察多个周期，判断改善是否持续",
    ],
    misconception: "利润增长不一定代表经营全面改善。",
  });

  const serialized = JSON.stringify(vm);
  [
    "PandaData",
    "get_fina_reports",
    "get_fina_forecast",
    "source_step",
    "research_1",
    "risk_2",
    "report_3",
    "row_count",
    "task_id",
    "skill_id",
  ].forEach((forbidden) => {
    assert.equal(serialized.includes(forbidden), false, `leaked ${forbidden}`);
  });
  assert.equal(/\d+\.\d{5,}/.test(serialized), false);

  const visibleFinalText = JSON.stringify([
    vm.finalSummary.conclusion,
    vm.finalSummary.evidence,
    vm.finalSummary.uncertainties,
    vm.finalSummary.learning,
    vm.finalSummary.nextSteps,
  ]);
  ["PandaData", "API", "prompt", "task_id", "skill_id", "source_step"].forEach((forbidden) => {
    assert.equal(visibleFinalText.includes(forbidden), false, `leaked ${forbidden}`);
  });
}

{
  const bundle = reportBundle();
  bundle.task.plan.selected_agents = [
    { agent: "research", reason: "只需要核对本次公司的财务事实" },
  ];
  bundle.task.plan.steps = [bundle.task.plan.steps[0]];
  bundle.report.aggregation.risks = [];
  bundle.report.aggregation.technical_evidence.conflicts = [];
  bundle.report.aggregation.technical_evidence.source_results = {
    research_1: bundle.report.aggregation.technical_evidence.source_results.research_1,
  };
  const vm = buildResearchViewModel(bundle);
  assert.deepEqual(vm.chapters.map((chapter) => chapter.title), ["公司与财务"]);
  assert.equal(vm.navigation.some((section) => section.label === "风险审查"), false);
  assert.equal(vm.navigation.some((section) => section.label === "量化验证"), false);
  assert.equal(vm.navigation.some((section) => section.label === "整合报告"), false);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.task_understanding.task_type = "factor_research";
  bundle.task.plan.selected_agents = [
    { agent: "quant", reason: "计算本次量化指标" },
    { agent: "risk", reason: "检查量化结论边界" },
  ];
  bundle.task.plan.steps = [
    {
      id: "quant_1",
      agent: "quant",
      objective: "计算样本内指标",
      expected_output: "量化计算结果",
      depends_on: [],
    },
    {
      id: "risk_2",
      agent: "risk",
      objective: "检查计算结果不能说明什么",
      expected_output: "风险与验证边界",
      depends_on: ["quant_1"],
    },
  ];
  aggregation.key_findings = [{
    text: "样本内指标已经完成计算，但尚未验证有效性。",
    evidence_type: "judgment",
    source_steps: ["quant_1"],
  }];
  aggregation.evidence_summary = [{
    text: "本次样本包含 120 个有效观察。",
    evidence_type: "fact",
    source_steps: ["quant_1"],
  }];
  aggregation.content_blocks[0].source_steps = ["quant_1"];
  aggregation.risks = [{
    text: "样本内结果不能外推为未来收益。",
    evidence_type: "risk",
    source_steps: ["risk_2"],
  }];
  aggregation.technical_evidence.source_results = {
    quant_1: {
      agent: "quant",
      status: "completed",
      summary: "样本内指标已经完成计算，但尚未验证有效性。",
      evidence: [{ text: "本次样本包含 120 个有效观察。" }],
      limitations: ["尚未完成样本外验证。"],
      recommendations: ["补充样本外检验。"],
    },
    risk_2: {
      agent: "risk",
      status: "completed",
      summary: "当前计算结果不能证明未来收益。",
      risks: ["样本内结果不能外推为未来收益。"],
      limitations: ["缺少样本外验证。"],
      recommendations: ["检查不同市场阶段的稳定性。"],
    },
  };
  const vm = buildResearchViewModel(bundle);
  assert.deepEqual(vm.chapters.map((chapter) => chapter.title), ["量化验证", "风险审查"]);
  assert.equal(vm.navigation.some((section) => section.label === "公司与财务"), false);
  assert.equal(vm.navigation.some((section) => section.label === "宏观与政策"), false);
  assert.equal(vm.navigation.some((section) => section.label === "整合报告"), false);
}

{
  [
    "已完成分析",
    "正式研究报告已生成",
    "任务已执行完成",
    "已完成数据计算",
    "已完成所需的数据计算",
    "300750.SZ 财务分析完成，覆盖 3 个报告期。",
    "已形成研究结果",
  ].forEach((invalidHeadline) => {
    const bundle = reportBundle();
    bundle.report.aggregation.direct_answer.headline = invalidHeadline;
    const vm = buildResearchViewModel(bundle);
    assert.equal(vm.finalSummary.conclusion.headline, "盈利表现优于收入表现。");
    ["已完成", "已生成", "报告"].forEach((invalidText) => {
      assert.equal(vm.finalSummary.conclusion.headline.includes(invalidText), false);
    });
  });
}

{
  const bundle = reportBundle();
  const longHeadline = "截至2026年7月24日，中国宏观经济呈现弱复苏态势，PMI三大指数均回升至扩张区间，但数值仍处于临界点附近，表明经济增长动能温和，新订单指数明显反弹。";
  bundle.report.aggregation.direct_answer.headline = longHeadline;
  const vm = buildResearchViewModel(bundle);
  assert.equal(vm.finalSummary.conclusion.headline, longHeadline);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.direct_answer.headline = "任务已执行";
  aggregation.direct_answer.explanation = "解释".repeat(100);
  aggregation.key_findings = [{ text: "已完成" }];
  const vm = buildResearchViewModel(bundle);
  assert.equal(
    vm.finalSummary.conclusion.headline,
    "盈利表现优于收入表现，但持续性需要验证。",
  );
  assert.equal(vm.finalSummary.conclusion.explanation.length, 180);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.key_findings = [];
  aggregation.evidence_summary = [];
  aggregation.content_blocks = [aggregation.content_blocks[0]];
  const vm = buildResearchViewModel(bundle);
  assert.deepEqual(vm.finalSummary.evidence[0], {
    title: "营业收入同比增长率 -9.70%",
    explanation: "本期营业收入低于上年同期。",
  });
  assert.equal(vm.finalSummary.evidence.length, 2);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.key_findings = [{ text: "300750.SZ 财务分析完成，覆盖 3 个报告期。" }];
  aggregation.evidence_summary = [{ text: "营业利润同比增长 19.24%。" }];
  aggregation.content_blocks = [];
  const vm = buildResearchViewModel(bundle);
  assert.deepEqual(vm.finalSummary.evidence, [{
    title: "营业利润同比增长 19.24%。",
    explanation: "",
  }]);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.direct_answer = {
    headline: "已完成",
    explanation: "",
  };
  aggregation.key_findings = [];
  aggregation.evidence_summary = [];
  aggregation.risks = [];
  aggregation.limitations = [];
  aggregation.next_research_steps = [];
  aggregation.content_blocks = [];
  aggregation.technical_evidence.source_results = {};
  const vm = buildResearchViewModel(bundle);
  assert.equal(
    vm.finalSummary.conclusion.headline,
    "当前证据不足以形成明确判断",
  );
  assert.deepEqual(vm.finalSummary.evidence, []);
  assert.deepEqual(vm.finalSummary.uncertainties, []);
  assert.deepEqual(vm.finalSummary.nextSteps, []);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.key_findings = [];
  aggregation.evidence_summary = [{
    text: [
      "风险摘要：存货与应收项目相对营收的占比持续上升，可能反映销售回款放缓或库存积压，",
      "存在资产减值和现金流压力加大的风险。",
      "（专业数据源: 专业研究方法, derived:2025q4:专业研究方法, SM0044820）",
    ].join(""),
  }];
  aggregation.content_blocks = [];
  const vm = buildResearchViewModel(bundle);
  assert.equal(vm.finalSummary.evidence[0].title.length <= 80, true);
  ["专业数据源", "专业研究方法", "derived:", "SM0044820"].forEach((forbidden) => {
    assert.equal(JSON.stringify(vm.finalSummary).includes(forbidden), false);
  });
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.key_findings = [];
  aggregation.evidence_summary = [];
  aggregation.content_blocks[0].data.metrics[0].explanation = "专业字段：。";
  const vm = buildResearchViewModel(bundle);
  assert.equal(vm.finalSummary.evidence[0].explanation, "");
  assert.equal(JSON.stringify(vm.finalSummary).includes("专业字段"), false);
}

{
  const bundle = reportBundle();
  const aggregation = bundle.report.aggregation;
  aggregation.direct_answer.headline = "建议买入并加仓";
  aggregation.direct_answer.explanation = "当前适合买入。";
  aggregation.key_findings = [{ text: "盈利表现优于收入表现。" }];
  aggregation.next_research_steps = [{ text: "建议加仓" }];
  const vm = buildResearchViewModel(bundle);
  assert.equal(vm.finalSummary.conclusion.headline, "盈利表现优于收入表现。");
  assert.equal(vm.finalSummary.conclusion.explanation, "");
  assert.deepEqual(vm.finalSummary.nextSteps, []);
}

{
  const message = translateProgressEvent({
    type: "tool_called",
    agent: "quant",
    message: "quant 调用了 pandadata_market_data",
    metadata: { tool: "pandadata_market_data", skill_id: "r020_volume_expansion" },
  });
  assert.equal(message, "Quant Agent正在核对本次研究需要的信息。");
  assert.equal(message.includes("pandadata"), false);
  assert.equal(message.includes("r020"), false);
}

{
  assert.equal(
    publicText("PandaData get_fina_reports 返回 0.123456789"),
    "专业数据源 专业数据源 返回 0.1235",
  );
  const filtered = publicText(
    "API prompt token request_url method internal_route_secret DeepSeek model SSE",
  );
  ["API", "prompt", "token", "request_url", "method", "DeepSeek", "model", "SSE"].forEach((forbidden) => {
    assert.equal(filtered.includes(forbidden), false, `leaked ${forbidden}`);
  });
  assert.equal(
    publicText('{"task_id":"secret","raw":"payload"}'),
    "该部分仅保留用户可见的研究摘要。",
  );
}

console.log("research presentation tests passed");
