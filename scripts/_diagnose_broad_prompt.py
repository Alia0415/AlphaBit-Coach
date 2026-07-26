"""One-off manual diagnosis: trace a broad user prompt through the planning path.

Runs PolicyGate -> TaskInterpreter -> ManagerAgent step by step and prints
every intermediate artifact plus the exact validation error, so we can see
why broad prompts fail while homepage examples succeed.

Consumes real Ark quota (at most 2 planning calls per prompt). Manual use only.
"""

from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from backend.agents.manager_agent import ManagerAgent
from backend.core.plan_validator import PlanValidationError
from backend.core.policy_gate import PolicyGate
from backend.core.task_interpreter import TaskInterpreter

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "现在新能源行业值得投资吗？"


def main() -> None:
    print("=== prompt ===")
    print(PROMPT)

    policy = PolicyGate().evaluate(PROMPT)
    print("\n=== policy ===")
    print(policy.model_dump_json(indent=2) if hasattr(policy, "model_dump_json") else policy)
    if not policy.allowed:
        print("BLOCKED at policy gate")
        return

    spec = TaskInterpreter().interpret(PROMPT, policy)
    print("\n=== task spec ===")
    print(json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2))

    manager = ManagerAgent()
    prompt = manager._planning_prompt(spec, PROMPT, None)
    print("\n=== requesting plan (attempt 1) ===")
    try:
        candidate = manager._request_plan(prompt, purpose="manager_plan")
    except Exception as exc:
        print(f"REQUEST FAILED: {type(exc).__name__}: {exc}")
        return
    print(json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False, indent=2))

    print("\n=== validating attempt 1 ===")
    try:
        manager._validate(candidate, spec)
        print("VALID — planning would succeed on the first attempt")
        return
    except (PlanValidationError, ValueError) as exc:
        print(f"VALIDATION FAILED: {type(exc).__name__}: {exc}")

    repair = manager._repair_prompt(
        request=PROMPT,
        task_spec=spec,
        profile_context=None,
        invalid_response=candidate.model_dump_json(),
        error=str(sys.exc_info()[1] or ""),
    )
    print("\n=== requesting plan (repair attempt 2) ===")
    try:
        repaired = manager._request_plan(repair, purpose="manager_plan_repair", attempt=2)
    except Exception as exc:
        print(f"REPAIR REQUEST FAILED: {type(exc).__name__}: {exc}")
        return
    print(json.dumps(repaired.model_dump(mode="json"), ensure_ascii=False, indent=2))

    print("\n=== validating repair ===")
    try:
        manager._validate(repaired, spec)
        print("VALID — repair attempt would succeed")
    except (PlanValidationError, ValueError) as exc:
        print(f"REPAIR VALIDATION FAILED: {type(exc).__name__}: {exc}")
        print("\n>>> This is the point where the user sees "
              "“Manager Agent 在一次修复后仍未返回有效的执行计划。”")


if __name__ == "__main__":
    main()
