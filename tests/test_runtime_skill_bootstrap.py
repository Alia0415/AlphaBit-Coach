from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.skills.loaders.instruction_skill_loader import (
    InstructionSkillLoader,
)
from backend.skills.runtime_bootstrap import ensure_bundled_instruction_skills
from backend.skills.skill_registry import SkillRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_bundled_macro_and_risk_skills_install_without_network(
    tmp_path: Path,
) -> None:
    runtime_home = tmp_path / "runtime"
    result = ensure_bundled_instruction_skills(runtime_home=runtime_home)

    assert result == {
        "macro_monitor": "installed",
        "event_risk_alert": "installed",
    }
    registry = SkillRegistry(
        project_root=PROJECT_ROOT,
        runtime_home=runtime_home,
        lock_path=PROJECT_ROOT / "skills.lock.json",
        register_default_adapters=False,
    )
    loader = InstructionSkillLoader(locator=registry.locator)
    assert loader.load(registry.get("macro_monitor")).truncated is False
    assert loader.load(registry.get("event_risk_alert")).truncated is False


def test_bundled_install_does_not_overwrite_existing_runtime(
    tmp_path: Path,
) -> None:
    runtime_home = tmp_path / "runtime"
    existing = runtime_home / "skill-macro-monitor"
    existing.mkdir(parents=True)
    marker = existing / "local-marker.txt"
    marker.write_text("preserve", encoding="utf-8")

    result = ensure_bundled_instruction_skills(runtime_home=runtime_home)

    assert result["macro_monitor"] == "existing"
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert result["event_risk_alert"] == "installed"


def test_application_import_bootstraps_bundled_skills(tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    environment = os.environ.copy()
    environment["QUANTSKILLS_HOME"] = str(runtime_home)

    completed = subprocess.run(
        [sys.executable, "-c", "import backend.main"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (runtime_home / "skill-macro-monitor" / "SKILL.md").is_file()
    assert (runtime_home / "skill-event-risk-alert" / "SKILL.md").is_file()


def test_concurrent_bootstrap_keeps_completed_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.skills import runtime_bootstrap

    runtime_home = tmp_path / "runtime"
    original_copytree = runtime_bootstrap.shutil.copytree
    raced = False

    def competing_copy(
        source: Path,
        destination: Path,
        *args: object,
        **kwargs: object,
    ) -> Path:
        nonlocal raced
        copied = original_copytree(source, destination, *args, **kwargs)
        if Path(destination).name == "skill-macro-monitor" and not raced:
            raced = True
            raise FileExistsError(destination)
        return copied

    monkeypatch.setattr(runtime_bootstrap.shutil, "copytree", competing_copy)

    result = runtime_bootstrap.ensure_bundled_instruction_skills(
        runtime_home=runtime_home
    )

    assert result["macro_monitor"] == "existing"
    assert result["event_risk_alert"] == "installed"
