---
name: event-risk-alert
description: A-share event-risk monitoring and alerting skill for Pandadata-based scans of stock watchlists, holdings, or portfolios. Use when the user asks to monitor A-share holding risks, restricted-share unlocks, equity pledges, shareholder increase/decrease plans, ST or delisting-risk status changes, earnings forecast risk, audit-opinion risk, shareholder-count changes, daily or weekly event-risk scans, risk alert reports, or scheduled event-risk automation.
license: GPL-3.0-only
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: skill-event-risk-alert
  repository_url: https://github.com/quantskills/skill-event-risk-alert
  project_type: skill
  collection: event-risk-alert
  creator: abgyjaguo
  creator_url: https://github.com/abgyjaguo
  maintainer: abgyjaguo
  maintainer_url: https://github.com/abgyjaguo
quantSkills:
  project_type: skill
  category: monitor
  tags:
    - a-share
    - event-risk
    - alerts
    - monitoring
    - pandadata
  platforms:
    - claude-code
    - codex
    - openclaw
    - cursor
  status: stable
  requires:
    - skill-pandadata-api
  validation_level: runnable
  maintainer_type: community
  summary_zh: "A 股持仓和自选股事件风险预警：解禁、质押、减持、ST、业绩预告、审计意见等事件扫描与可追溯告警报告。"
  summary_en: "A-share event-risk alert skill for watchlists, holdings, unlocks, pledges, reductions, ST changes, forecasts, audit opinions, and traceable reports."
---

```json qsh-form
{
  "version": 1,
  "task": {
    "placeholder": "请输入 A 股持仓或自选股代码列表，并说明需要扫描的风险类别",
    "required": true
  },
  "fields": [
    {
      "key": "date",
      "label": "报告日期",
      "type": "date",
      "help": "留空时使用最近可用交易日"
    },
    {
      "key": "horizon",
      "label": "事件监控窗口",
      "type": "select",
      "default": "6",
      "options": [
        { "value": "3", "label": "未来 3 个月" },
        { "value": "6", "label": "未来 6 个月" },
        { "value": "12", "label": "未来 12 个月" }
      ]
    }
  ],
  "prompt_template": "{{#task}}任务与材料：\n{{task}}\n\n{{/task}}{{#attachments}}用户上传的材料（已放入工作区）：\n{{attachments}}\n\n{{/attachments}}{{#date}}以 {{date}} 为报告日期，{{/date}}未指定日期时以最近可用交易日为报告日期。对给定 A 股持仓或自选股执行未来 {{horizon}} 个月事件风险扫描，覆盖限售解禁、股权质押、股东增减持、ST/退市风险、业绩预告、审计意见和股东户数变化；按严重度分级并标注来源方法、事件日期、触发规则、原始值、缺失数据及下次监控日期，输出中文报告。"
}
```

# Event Risk Alert

Use this skill to turn an A-share watchlist into a traceable event-risk scan and a concise alert report. Prefer Pandadata as the data source, use exact method contracts from the local `pandadata-api` skill, and keep the output factual rather than advisory.

## Core Rules

- Load `pandadata-api` before making real API calls. Search its method index or use its search script to confirm parameters, fields, units, and date formats; do not guess signatures.
- Treat the watchlist as user-maintained portfolio context. If no watchlist exists or the user does not provide symbols, ask for a symbol list before scanning.
- Use absolute dates such as `2026-06-12` in reports and scheduled-monitor specs. Convert Pandadata `YYYYMMDD` fields for human output.
- De-duplicate alerts against prior state when state is available. Re-alert only when an event is new, severity rises, a key date enters a tighter window, or the user asks for a full rescan.
- Label every material claim with source method, query window, data date or event date, and whether the value is raw from Pandadata or calculated.
- Do not provide personalized trading instructions. End formal alerts with a note that the output is data monitoring and research support, not investment advice.

## Workflow

1. **Normalize scope**: identify symbols, report date, scan window, output path, and whether this is a one-off scan or recurring monitor.
2. **Validate inputs**: if using a JSON watchlist, run `scripts/validate_watchlist.py <watchlist.json>`. Fix invalid symbol formats, date formats, duplicate symbols, or malformed rule overrides before scanning.
3. **Confirm trading context**: use `get_last_trade_date` and `get_trade_cal` through `pandadata-api` when the scan depends on a completed A-share trading day.
4. **Read the playbook**: for multi-category scans, recurring monitors, state-file design, or report formatting, read `references/event-risk-alert-guide.md`.
5. **Plan method calls**: choose the narrowest event methods that answer the request, then smoke-test one symbol or a small date range before expanding to the full watchlist.
6. **Score events**: classify each finding as `high`, `medium`, `low`, or `info`; include the triggering rule and enough raw fields for auditability.
7. **Persist outputs**: when the user asks for files, save reports under `alerts/YYYYMMDD.md` and state under `alerts/state.json` unless another path is specified.
8. **Schedule carefully**: for recurring alerts, first produce the monitor spec with timezone, cadence, watchlist path, alert channels, idempotency rules, and stale-data handling. Use the active runtime's automation capability only after the schedule/channel is known.

## Event Method Map

| Risk area | Primary Pandadata methods | Default scan logic |
|---|---|---|
| Restricted-share unlocks | `get_restricted_list` | Look ahead 30 days by `relieve_date`; escalate large upcoming unlocks or unlocks near the report date. |
| Equity pledges | `get_stock_pledge`, `get_stock_pledge_stat` | Review new pledges, releases, and accumulated pledge ratios; escalate high accumulated pledge exposure. |
| Shareholder plans | `get_stock_shareholder_change` | Flag new reduction plans, controller or director/officer reductions, large planned reduction ratios, and plan status changes. |
| ST and delisting-risk status | `get_stock_status_change` | Flag new ST, *ST, delisting-risk warnings, withdrawals, and status changes by `change_date` and `type`. |
| Earnings forecast risk | `get_fina_forecast` | Flag loss forecasts, first losses, continued losses, sharp downward revisions, or large negative net-profit ranges. |
| Audit-opinion risk | `get_audit_opinion` | Escalate non-standard audit opinions or internal-control audit issues; treat normal/no-audit rows as context, not alerts. |
| Shareholder-count changes | `get_holder_count` | Compare latest two disclosed periods; flag sharp holder-count increases that may indicate ownership dispersion. |

## Watchlist Contract

Prefer `watchlist.json` with this shape:

```json
{
  "as_of": "2026-06-12",
  "symbols": [
    {
      "symbol": "000001.SZ",
      "name": "Ping An Bank",
      "position_cost": 10.25,
      "tags": ["core-holding"]
    }
  ],
  "rules": {
    "restricted_unlock_days": 30,
    "high_unlock_float_pct": 5,
    "medium_pledge_total_ratio": 30,
    "high_pledge_total_ratio": 50,
    "holder_count_increase_pct": 20
  }
}
```

All fields except `symbol` are optional for each entry. Preserve user-provided metadata and rule overrides in generated state or reports.

## Output Standards

- Write Chinese Markdown by default unless the user requests another language.
- Start with a severity summary: high, medium, low, and no-new-risk counts.
- For each alert include: symbol, name when known, severity, event type, source method, query parameters, event date, announcement/update date, trigger rule, key raw values, and next monitoring date.
- Include a "Data Notes" section for empty method results, lagging disclosures, failed calls, stale state, or methods skipped by request scope.
- Distinguish upcoming dated events from newly disclosed historical events.
- Keep low-risk and informational findings in the file report, but push or highlight only high and medium alerts unless the user asks otherwise.

## Maintenance And Limitations

- Creator and maintainer: `abgyjaguo` (`https://github.com/abgyjaguo`), published under the `quantskills/skill-event-risk-alert` repository.
- Upstream dependency: use the sibling `pandadata-api` skill for Pandadata runtime setup and exact API contracts.
- This skill does not certify data completeness, production readiness, alert delivery, or trading outcomes.
- Event-risk output is only as current as the available disclosure data and API refresh cycle; always report missing, stale, or lagging data.

## Cross-Agent Use

- Codex and Claude Code can load this folder directly as a skill named `$event-risk-alert`.
- Cursor should use `agents/cursor-rule.mdc` as the project rule adapter and keep the full folder under `.cursor/skills/event-risk-alert`.
- Hermes should keep the full folder under `.hermes/skills/finance/event-risk-alert` or use `agents/portable-loader.md`.
- OpenClaw should keep the full folder under `.openclaw/skills/event-risk-alert` or use `agents/portable-loader.md`.
- Agents without native skill discovery can paste the prompt in `agents/portable-loader.md`.
