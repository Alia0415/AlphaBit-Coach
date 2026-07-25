# Global Multi-Agent Minimum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent every executable AlphaOS research plan from running with fewer than two distinct Experts.

**Architecture:** Add a Manager-only semantic validator that requires two distinct selected Experts and at least one cross-Expert dependency, while exempting clarification plans. Keep WorkflowExecutor unchanged so it continues to execute exactly the validated Manager DAG.

**Tech Stack:** Python 3, Pydantic, pytest, Ruff

---

### Task 1: Specify the global validator with failing tests

**Files:**
- Create: `tests/test_global_multi_agent_minimum.py`
- Modify: `backend/core/plan_validator.py`

- [x] Write tests that call `validate_global_collaboration` and assert:
  - a one-Expert execution plan raises `PlanValidationError`;
  - two Experts without a cross-Expert dependency raise;
  - two Experts with a cross-Expert dependency pass;
  - a clarification plan passes without Experts or steps.
- [x] Run `python -m pytest tests/test_global_multi_agent_minimum.py -q` and verify RED because the validator does not exist.
- [x] Implement `validate_global_collaboration(plan)` using `selected_agents`, `steps`, and `PlanStep.all_dependency_step_ids()`.
- [x] Re-run the test file and verify GREEN.

### Task 2: Enforce the validator in Manager planning

**Files:**
- Modify: `backend/agents/manager_agent.py`
- Test: `tests/test_global_multi_agent_minimum.py`

- [x] Add a Mock Ark test where both initial and repair plans contain one Expert; assert `ManagerAgentError` after exactly two calls.
- [x] Add a Mock Ark test where the initial plan is one Expert and the repaired plan has two Experts plus a cross-Expert dependency; assert the repaired plan is returned.
- [x] Run the two tests and verify RED before changing Manager.
- [x] Call `validate_global_collaboration` from `ManagerAgent._validate` after structural validation and before dimension validation.
- [x] Rewrite initial and repair prompts to require at least two distinct Experts, a real cross-Expert dependency, and explicit failure when credible collaboration is impossible.
- [x] Remove contradictory prompt rules that describe price, risk, event, factor, or company requests as single-Expert tasks.
- [x] Re-run the new tests and verify GREEN.

### Task 3: Align the locked product architecture

**Files:**
- Modify: `AGENTS.md`

- [x] Replace the statement allowing a genuinely single-Expert plan with the approved global two-Expert minimum.
- [x] Update development rules so “minimal sufficient expert set” means the smallest credible set with a floor of two distinct Experts.
- [x] Preserve Manager ownership, dynamic DAG planning, Registry authorization, Skill ownership, and the prohibition on fixed workflows.

### Task 4: Update affected tests and verify

**Files:**
- Modify only existing Manager tests that fail solely because they encode the former single-Expert product rule.
- Do not modify concurrent LangGraph work in `backend/core/workflow_executor.py`, `requirements.txt`, or unrelated test changes.

- [x] Run `python -m pytest tests/test_global_multi_agent_minimum.py tests/test_growth_valuation_collaboration.py tests/test_financial_quality_collaboration.py -q`.
- [x] Run the full suite with `python -m pytest -q`.
- [x] Run `python -m ruff check` on every Python file changed by this task.
- [x] Run `git diff --check` and inspect staged paths.

### Task 5: Commit and push

- [ ] Stage only the global multi-Agent implementation, tests, architecture guide, and this plan.
- [ ] Commit with `feat: require multi-agent research plans`.
- [ ] Synchronize with `origin/main` without losing concurrent work.
- [ ] Re-run relevant verification if synchronization changes the base.
- [ ] Push `main` and confirm `origin/main` points to the new commit.
