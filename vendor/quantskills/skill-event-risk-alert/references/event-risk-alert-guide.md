# Event Risk Alert Guide

Use this reference for multi-category scans, recurring monitor specs, state files, and report formatting. Always verify exact Pandadata parameters and fields with the local `pandadata-api` skill before running calls.

## Event Normalization

Convert raw rows into normalized events with these fields:

| Field | Meaning |
|---|---|
| `event_id` | Stable hash or joined key from symbol, event type, source method, announcement date, event date, and principal party. |
| `symbol` | A-share code such as `000001.SZ` or `600000.SH`. |
| `name` | Stock name from the row, watchlist, or a separate symbol lookup. |
| `event_type` | One of `restricted_unlock`, `pledge`, `shareholder_plan`, `status_change`, `earnings_forecast`, `audit_opinion`, `holder_count_change`. |
| `severity` | `high`, `medium`, `low`, or `info`. |
| `source_method` | Pandadata method name used for the row. |
| `query` | Method parameters, especially symbol and date or quarter window. |
| `announcement_date` | Disclosure date when available. |
| `event_date` | Effective date, unlock date, plan begin/end date, forecast period, report quarter, or holder-count period. |
| `trigger_rule` | Rule name and threshold that caused the alert. |
| `raw_values` | Minimal raw fields needed to audit the classification. |
| `state_key` | Key used to suppress repeated alerts. |

## Default Severity Rules

Use these defaults unless the watchlist `rules` object overrides them.

| Risk | High | Medium | Low/info |
|---|---|---|---|
| Restricted unlock | Unlock within 7 calendar days, or unlocked shares exceed 5% of float when float is available. | Unlock within 30 days, or event is newly disclosed for a watched holding. | Older or already-announced unlock outside the active window. |
| Equity pledge | Accumulated pledge ratio to total shares is at least 50%, or a controller/major-holder new pledge is very large. | Accumulated pledge ratio is at least 30%, or a new pledge is material but below high threshold. | Pledge release, small new pledge, or no ratio available. |
| Shareholder reduction | Controller, actual controller, director, supervisor, officer, or large shareholder reduction plan; planned ratio at least 1%. | Any new reduction plan or negative progress update. | Increase plan, completed historical plan, or minor reduction with no size fields. |
| ST or delisting status | New ST, *ST, delisting-risk warning, trading termination, or major adverse status. | Status change with uncertain severity or warning withdrawal that still needs follow-up. | Withdrawal of warning with clearly positive status. |
| Earnings forecast | Loss, first loss, continued loss, sharp negative revision, or negative net-profit range. | Large profit decline, weak forecast text, or mixed range crossing zero. | Positive or neutral forecast. |
| Audit opinion | Qualified, adverse, disclaimer, emphasis of matter, internal-control issue, or any non-standard opinion. | Missing agency/opinion on a report where opinion is expected. | Unqualified opinion or no-audit interim report. |
| Holder-count change | Latest holder count rises at least 20% from prior disclosed period. | Latest holder count rises at least 10%. | Decline or small change. |

## Pandadata Planning Notes

- Restricted unlocks: use `get_restricted_list` with `start_date` and `end_date`; key fields are `date`, `relieve_date`, `shareholder`, `shareholder_type`, `relieve_shares`, `actual_relieve_shares`, and `relieve_reason`.
- Equity pledges: use `get_stock_pledge` for event rows and `get_stock_pledge_stat` for aggregate statistics. Watch `publish_date`, `shareholder_name`, `pledged_shares`, `pledge_ratio`, `acc_pledged_hold_ratio`, `acc_pledge_total_ratio`, `pledge_begin_date`, `pledge_end_date`, `release_date`, and `is_released`.
- Shareholder plans: use `get_stock_shareholder_change`; key fields include `info_date`, `first_info_date`, `progress`, `begin_date`, `end_date`, `shareholder_name`, `shareholder_type`, `direction`, `change_up_limit`, `ratio_up_limit`, and `reason`.
- Status changes: use `get_stock_status_change`; key fields include `date`, `info_date`, `change_date`, `description`, `type`, and `name`.
- Earnings forecasts: use `get_fina_forecast`; query by `symbol`, `info_date`, or `end_quarter` depending on scope. Watch `forecast_type`, growth-rate bounds, net-profit bounds, and forecast period.
- Audit opinions: use `get_audit_opinion`; query by quarter window. Escalate by `opinion` and `audit_type`.
- Holder counts: use `get_holder_count`; compare latest two rows by `end_date` or `date`, using `holders` or `a_holders`.

## State File

Use `alerts/state.json` when the user wants repeatable monitoring:

```json
{
  "last_scan_at": "2026-06-12T08:30:00+08:00",
  "last_report_date": "2026-06-12",
  "events": {
    "000001.SZ|restricted_unlock|20260701|shareholder": {
      "severity": "medium",
      "first_seen": "2026-06-12",
      "last_seen": "2026-06-12",
      "source_method": "get_restricted_list"
    }
  }
}
```

Update `last_seen` for repeated events. Emit a new alert when `severity` increases, when the `event_date` moves into a tighter alert window, or when the event key is unseen.

## Report Template

Use this Markdown shape:

```markdown
# A-share Event Risk Alert - YYYY-MM-DD

## Summary

| Severity | Count | Notes |
|---|---:|---|
| High | 0 | - |
| Medium | 0 | - |
| Low/info | 0 | Archived in detail section |

## High And Medium Alerts

| Symbol | Name | Severity | Event | Event date | Source | Trigger |
|---|---|---|---|---|---|---|

## Detail

### SYMBOL Name

- Severity:
- Event type:
- Source method and parameters:
- Announcement/update date:
- Event/effective date:
- Key values:
- Trigger rule:
- Monitoring next step:

## Data Notes

- Methods called:
- Empty or skipped datasets:
- Disclosure lag or stale-data warnings:

This report is generated from data monitoring rules for research support only and is not investment advice.
```

## Recurring Monitor Spec

Before creating a runtime automation, write a short spec with:

- Watchlist path and ownership.
- Scan categories and date or quarter windows.
- Cadence, timezone, and trading-day handling.
- Output path and whether reports overwrite or append.
- Push channel and severity threshold.
- State-file path and duplicate-suppression rule.
- Failure behavior for empty API responses, credentials, network errors, or stale datasets.

Recommended cadence: run daily before the A-share open for newly disclosed events and upcoming unlocks; run a weekly full review for pledges, audit opinions, and holder-count changes.
