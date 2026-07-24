"""Safe instruction adapter for the pinned macro-monitor methodology."""

from __future__ import annotations

from backend.skills.contracts import (
    SkillInvocation,
    SkillResult,
    SkillSpec,
    SkillStatus,
)
from backend.skills.loaders.instruction_skill_loader import (
    InstructionSkillLoader,
    SkillUnavailableError,
)


class MacroMonitorAdapter:
    """Verify the reviewed playbook without executing documentation commands."""

    def __init__(self, *, loader: InstructionSkillLoader) -> None:
        self._loader = loader

    def __call__(
        self,
        invocation: SkillInvocation,
        spec: SkillSpec,
    ) -> SkillResult:
        try:
            loaded = self._loader.load(spec)
        except (OSError, ValueError, SkillUnavailableError) as exc:
            return SkillResult(
                invocation_id=invocation.invocation_id,
                skill_id=invocation.skill_id,
                status=SkillStatus.UNAVAILABLE,
                summary="Macro Monitor Skill 未安装或未通过锁定校验。",
                limitations=[str(exc)],
                error=str(exc),
            )

        return SkillResult(
            invocation_id=invocation.invocation_id,
            skill_id=invocation.skill_id,
            status=SkillStatus.COMPLETED,
            summary="已加载并校验 Macro Monitor 方法约束。",
            data={
                "methodology_loaded": True,
                "validation_status": "methodology_verified",
                "data_source": "PandaData",
                "instruction_truncated": loaded.truncated,
            },
            evidence=[
                {
                    "type": "methodology_control",
                    "skill_id": spec.id,
                    "data_source": "PandaData",
                    "controls": [
                        "catalog_first",
                        "allowlisted_macro_methods_only",
                        "facts_inference_separation",
                        "freshness_and_unit_required",
                    ],
                }
            ],
            assumptions=[
                "实际宏观事实必须来自 AlphaOS 受控 PandaDataClient。",
            ],
            limitations=[
                "Skill 仅提供方法约束；它本身不提供或伪造宏观数据。",
            ],
            provenance=loaded.provenance,
        )
