"""Install reviewed bundled instruction Skills into the runtime home."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from backend.skills.loaders.instruction_skill_loader import (
    InstructionSkillLoader,
    PROJECT_ROOT,
    RuntimeSkillLocator,
)
from backend.skills.skill_registry import SkillRegistry


BUNDLED_INSTRUCTION_SKILL_IDS = ("macro_monitor", "event_risk_alert")
BootstrapStatus = Literal["installed", "existing"]


def ensure_bundled_instruction_skills(
    *,
    runtime_home: Path | None = None,
    project_root: Path | None = None,
    vendor_root: Path | None = None,
    lock_path: Path | None = None,
) -> dict[str, BootstrapStatus]:
    """Install missing bundled Skills without network access or overwrites."""

    resolved_project_root = (project_root or PROJECT_ROOT).resolve()
    resolved_vendor_root = (
        vendor_root or resolved_project_root / "vendor" / "quantskills"
    ).resolve()
    resolved_lock_path = (
        lock_path or resolved_project_root / "skills.lock.json"
    ).resolve()
    runtime_locator = RuntimeSkillLocator(
        project_root=resolved_project_root,
        runtime_home=runtime_home,
        lock_path=resolved_lock_path,
    )
    runtime_locator.runtime_home.mkdir(parents=True, exist_ok=True)

    registry = SkillRegistry(
        project_root=resolved_project_root,
        runtime_home=resolved_vendor_root,
        lock_path=resolved_lock_path,
        register_default_adapters=False,
    )
    loader = InstructionSkillLoader(locator=registry.locator)
    statuses: dict[str, BootstrapStatus] = {}

    for skill_id in BUNDLED_INSTRUCTION_SKILL_IDS:
        spec = registry.get(skill_id)
        destination = (runtime_locator.runtime_home / spec.runtime_path).resolve()
        if not destination.is_relative_to(runtime_locator.runtime_home):
            raise ValueError("Bundled runtime skill path escapes QUANTSKILLS_HOME")
        if destination.exists():
            statuses[skill_id] = "existing"
            continue

        loader.load(spec)
        source = (resolved_vendor_root / spec.runtime_path).resolve()
        if not source.is_relative_to(resolved_vendor_root):
            raise ValueError("Bundled source path escapes the vendor root")
        try:
            shutil.copytree(source, destination)
        except FileExistsError:
            if not destination.exists():
                raise
            statuses[skill_id] = "existing"
        else:
            statuses[skill_id] = "installed"

    return statuses
