# Broad Stock-Selection Rewrite Design

## Goal

Make broad stock-selection prompts such as "我应该买什么股票" reliably enter
the existing research workflow without producing direct buy or sell advice.

## Scope

The change is limited to `ResearchQueryRefiner`. After the model returns its
draft, the service detects explicit stock-selection wording in the original
query and replaces the model draft with one deterministic, research-only
question:

> 研究当前 A 股市场值得关注的行业方向、公司筛选框架、基本面证据和主要风险，不提供具体买卖建议。

The rewritten query requires user confirmation, just like other material
rewrites. It does not select experts, Skills, dimensions, or DAG edges.
Manager remains the sole planner.

## Detection

Use a small, reviewable set of phrases that explicitly ask which security to
buy or choose, including:

- 买什么股票
- 买哪只股票
- 买哪些股票
- 该买什么股票
- 应该买什么股票
- 推荐股票

Matching applies only to the original normalized user query. Unrelated
research questions continue using the model draft unchanged.

## Data Flow

1. The frontend submits the original query to `ResearchQueryRefiner`.
2. The existing model rewrite runs as it does today.
3. The deterministic boundary rewrite checks the original query.
4. For a stock-selection request, it returns the fixed research-only query
   with `requires_confirmation=true`.
5. After confirmation, the frontend submits that research query through the
   existing PolicyGate, TaskInterpreter, Manager, and executor flow.

## Error Handling

The deterministic override runs only after a valid model response. Existing
model failure behavior remains unchanged. This patch does not introduce a
fallback that silently proceeds when the rewrite model is unavailable.

## Testing

Add regression coverage proving:

- "我应该买什么股票" is always converted to the fixed research-only query,
  even when the model returns a recommendation-style rewrite.
- The result requires confirmation.
- A normal, specific research question still uses the model result unchanged.

Run the query-refinement tests, planning tests, and the broader governed
workflow tests.

## Non-Goals

- Returning named stocks as recommendations.
- Relaxing Manager DAG, expert, Skill, or evidence validation.
- Adding a fixed research workflow.
- Resolving company names to securities codes.
- Changing PolicyGate behavior.
