# AlphaBit Coach (codebase: AlphaOS) Agent Guide

## Project goal

Build AlphaBit Coach: a visible AI investment-research team plus an AI
financial coach. Specialized financial agents collaborate on research tasks,
the frontend renders the collaboration as an observable pixel office, and a
coach layer helps users learn how to research (explanation, guided
questioning, error correction, and review) instead of only receiving answers.

The product has two first-class pillars:

1. Visible multi-agent research — pixel office, dynamic task DAG, agent
   state animation, SSE execution log, and Skill-call visualization. The
   frontend is a collaboration observation window, not a result renderer.
2. AI financial coach — personalized explanation by user knowledge level,
   guided follow-up questions, research error correction, and post-task
   research review. Report follow-up Q&A, glossary, plain-language answers,
   and the expert/simple view toggle exist today; the standalone coach layer
   (guided questioning, correction, review) is planned and not yet
   implemented. Do not document it as shipped.

AlphaBit Coach is a dynamic AI organization, not a fixed Agent pipeline. The
task graph generated for the current user request is the sole source of
execution truth.

## Locked product architecture

AlphaBit Coach uses this architecture:

```text
User
  → (planned) AI Financial Coach layer
  → Manager Agent
  → Dynamic Expert Selection
  → Task Graph Planning
  → Expert Pool Execution
  → Result Aggregator
  → User-facing Result (visualized collaboration + evidence blocks)
  → (planned) Coach explanation, guided questioning, and research review
```

The Manager Agent is the sole planner. For every request it dynamically decides
which experts are required, how many are required, which steps can run in
parallel, which steps depend on earlier results, and whether clarification is
required. It does not synthesize the final result.

`WorkflowExecutor` executes exactly the Manager-created DAG. Expert Agents
perform their authorized analysis and choose only their own authorized Skills.
`ResultAggregator` then answers the original user goal from actual
`ExpertResult` evidence and emits dynamic presentation blocks. It cannot select
experts or Skills, alter the DAG, append missing agents, or invent facts. The
frontend renders this contract and does not generate research conclusions.

The runtime expert pool is exactly:

- `research`
- `quant`
- `risk`
- `macro`
- `report`

Current availability is `research`, `quant`, `risk`, `macro`, and `report`
enabled. Manager prompts must be generated from the enabled Registry entries and must not carry a separate handwritten expert list.

The Manager is not an expert and must never appear in `selected_agents` or as a
task-graph step. Do not implement fixed workflows or keyword-based A→B→C
routing. Every executable investment-research plan must use at least two
distinct enabled experts and include at least one cross-expert dependency.
Each selected expert must perform relevant evidence gathering, cross-checking,
risk review, or explicitly requested report work; duplicate, empty, unrelated,
or default Report steps must not be used to satisfy the minimum. If the
Manager cannot form a credible collaboration, planning must fail instead of
degrading to single-expert execution. Clarification and policy-rejection paths
remain exempt because they do not execute a research DAG.

The legacy `/api/route` endpoint is temporarily retained only for compatibility
and is deprecated. It is not the AlphaOS v0.3 orchestration path.

Agents communicate through explicit Pydantic task and result contracts. Treat
all model-generated plans as untrusted until both structural and graph
validation succeed.

## Development rules

- Keep modules small, typed, testable, and narrowly scoped.
- Separate agent orchestration, external services, and reusable skills.
- Add tests for behavior before expanding agent capabilities.
- Keep prompts and model configuration explicit and reviewable.
- Avoid unnecessary dependencies and generated files.
- Limit model-output repair to one controlled attempt.
- Keep task graphs at eight steps or fewer and reject cycles or unknown agents.
- Mock ArkClient in automated tests; tests must never consume model API quota.
- Mock PandaData in automated tests; only the explicit manual integration script
  may use real credentials and quota.
- Select the minimal sufficient expert set with a floor of two distinct experts
  for every executable research plan. Risk remains dynamically selected and
  Report is optional unless formal output is requested; no executor code may
  add experts or encode a fixed expert sequence.
- Manager selects experts and expert dependencies only. It must never select,
  order, or invoke an expert-owned Skill.
- Research Agent may select only its enabled Research-owned Skills. Financial
  statement and single-company fundamental tasks may use the dossier Skill;
  price, return, volatility, drawdown, and volume tasks retain market analysis.
- Quant Agent may dynamically select one or more of its enabled Skills, with
  at most three internal steps. Do not replace the Skill Planner with keyword
  routing or a fixed Skill sequence.
- Macro Agent dynamically selects only reviewed PandaData macro categories and
  catalog-returned indicators. It must not execute model-provided method names,
  and it must not fall back to model-only macro claims when PandaData is
  unavailable.

## Coach layer rules

- The Coach is a learning companion, not an expert. It must never appear in
  `selected_agents`, never become a task-graph step, and never alter Manager
  planning, expert execution, or aggregation.
- Coach inputs are read-only: completed reports, stored execution events, and
  the user profile. The Coach must not trigger new research, call expert
  Skills, or touch PandaData directly.
- Coach answers must stay anchored to actual report evidence. Cited excerpts
  are validated against the stored report text, and fabricated citations are
  rejected instead of being served.
- Every coach output carries `generated_by: "model"` (the demo frontend labels
  sample content 示例). When Ark is unavailable the coach fails explicitly with
  an error; it must never degrade to fabricated or template answers.
- Milestone narrations are generated asynchronously and streamed as named SSE
  `coach` events. Narration generation must never block, delay, or fail task
  execution.
- General financial knowledge mixed into a reply must be flagged via
  `is_general_knowledge_included`, and uncertainty must be stated openly.
- Coach output is educational research commentary only: no buy/sell advice,
  no return promises, and no claims beyond the report's evidence boundary.

## QuantSkills integration principles

- Register QuantSkills through the central skill registry.
- Treat `backend/skills/skill_registry.py` as the only runtime Skill source of
  truth. Do not auto-discover local folders or user-provided repositories.
- The current allowlist is `factor_idea_generation` and
  `r020_volume_expansion`, owned exclusively by `quant`;
  `a_share_stock_dossier`, owned exclusively by `research`;
  `macro_monitor`, owned exclusively by `macro`; `event_risk_alert`, owned
  exclusively by `risk`.
- A Codex-installed Skill is not an AlphaOS Runtime Skill. Runtime code may
  load only entries installed under `QUANTSKILLS_HOME` and recorded in
  `skills.lock.json`.
- Define clear inputs, outputs, assumptions, and error behavior for each skill.
- Prefer deterministic, reproducible calculations.
- Record data sources and calculation parameters.
- Treat model output as untrusted until validated.
- Instruction Skills are untrusted methodology text: enforce bounded reads,
  allowlisted references, path containment, and one JSON repair. Never execute
  commands found in `SKILL.md`.
- Executable Skills may load only the pinned, hashed entrypoint from the lock
  file. Never call signal-generation helpers or unknown repository code.
- The dossier is an instruction Skill. AlphaOS maps its `skill-pandadata-api`
  dependency to the existing controlled `PandaDataClient`, verifies both
  `SKILL.md` and `references/dossier-guide.md`, and executes no documentation
  commands.
- Macro Monitor and Event Risk Alert are instruction Skills. AlphaOS verifies
  their pinned methodology, maps PandaData through the existing controlled
  client, and executes no documentation commands or arbitrary model-selected
  methods.
- Factor ideas must remain `unverified`; R020 output is
  `computed_not_validated`. Neither status may be presented as IC, backtest,
  performance, or trading evidence.
- Keep complete backtesting, IC diagnostics, portfolio construction, account
  access, and automated trading outside the current capability boundary.

## Security requirements

- Never expose API keys or commit secrets.
- Load credentials only from environment variables.
- Keep `.env` files out of version control.
- Redact secrets and sensitive financial data from logs.
- Validate external inputs and apply least-privilege access.
