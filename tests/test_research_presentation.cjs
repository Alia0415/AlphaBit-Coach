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
  assert.deepEqual(vm.agents.map((agent) => agent.id), ["research", "risk", "report"]);
  assert.equal(vm.agents.some((agent) => agent.id === "macro"), false);
  assert.equal(vm.metrics[0].value, "-9.70%");
  assert.match(vm.metrics[0].formula, /本期营业收入/);
  assert.equal(vm.coverage.some((item) => item.status === "missing"), true);
  assert.match(vm.learningSummary.quiz.question, /营业收入同比增长率/);
  assert.equal(vm.learningSummary.quiz.answerIndex, 1);
  assert.equal(vm.evidenceChains.length > 0, true);

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
    "method",
    "task_id",
    "skill_id",
  ].forEach((forbidden) => {
    assert.equal(serialized.includes(forbidden), false, `leaked ${forbidden}`);
  });
  assert.equal(/\d+\.\d{5,}/.test(serialized), false);
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
