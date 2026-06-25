from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ecosystem.claude_code_adapter import export_to_claude_code
from ecosystem.hermes_adapter import export_to_hermes
from ecosystem.openclaw_adapter import export_to_openclaw
from ecosystem.skill_schema import CanonicalSkill
from ecosystem.skill_sync import (
    SkillSyncRegistry,
    apply_skill_export_plan,
    build_dynamic_skill_graph,
    build_skill_sync_manifest,
    build_skill_export_plan,
    discover_skill_records,
    write_skill_sync_manifest,
)
from agent.agent import TapMakerAgent
from llm.mock_llm import MockLLM


def _skill(skill_id: str, version: str = "1.0.0", body: str = "Use it") -> CanonicalSkill:
    return CanonicalSkill(
        id=skill_id,
        name=skill_id,
        version=version,
        description="Portable test skill",
        parameters={"type": "object", "properties": {}},
        tags=["test"],
        body=body,
    )


def _write_canonical(root: Path, skill: CanonicalSkill) -> None:
    skill_dir = root / "storage" / "skills" / skill.id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "skill.json").write_text(
        json.dumps(skill.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_skill_sync_manifest_has_no_conflict_for_matching_export():
    tmp = Path(tempfile.mkdtemp())
    try:
        skill = _skill("build_helper", body="Run build checks")
        _write_canonical(tmp, skill)
        export_dir = tmp / ".claude" / "skills" / skill.id
        export_dir.mkdir(parents=True)
        (export_dir / "SKILL.md").write_text(export_to_claude_code(skill), encoding="utf-8")

        records = discover_skill_records(tmp)
        manifest = build_skill_sync_manifest(records)

        assert manifest["summary"]["total_records"] == 2
        assert manifest["summary"]["total_skills"] == 1
        assert manifest["conflicts"] == []
        print("[PASS] matching skill export has no sync conflict")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_sync_detects_version_conflict():
    tmp = Path(tempfile.mkdtemp())
    try:
        canonical = _skill("maker_publish", version="1.0.0")
        openclaw = _skill("maker_publish", version="2.0.0")
        _write_canonical(tmp, canonical)
        export_dir = tmp / ".openclaw" / "skills" / openclaw.id
        export_dir.mkdir(parents=True)
        (export_dir / "SKILL.md").write_text(export_to_openclaw(openclaw), encoding="utf-8")

        manifest = build_skill_sync_manifest(discover_skill_records(tmp))
        conflict_types = {item["type"] for item in manifest["conflicts"]}

        assert "version_conflict" in conflict_types
        assert manifest["summary"]["total_conflicts"] >= 1
        print("[PASS] skill version conflict detected")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_sync_detects_same_version_content_drift():
    tmp = Path(tempfile.mkdtemp())
    try:
        canonical = _skill("context_pack", version="1.0.0", body="Load compact context")
        hermes = _skill("context_pack", version="1.0.0", body="Load every file")
        _write_canonical(tmp, canonical)
        export_dir = tmp / ".hermes" / "skills" / hermes.id
        export_dir.mkdir(parents=True)
        (export_dir / "SKILL.md").write_text(export_to_hermes(hermes), encoding="utf-8")

        manifest = build_skill_sync_manifest(discover_skill_records(tmp))
        conflict_types = {item["type"] for item in manifest["conflicts"]}

        assert "fingerprint_mismatch" in conflict_types
        print("[PASS] same-version content drift detected")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_sync_manifest_can_be_written():
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_canonical(tmp, _skill("writer"))
        manifest = build_skill_sync_manifest(discover_skill_records(tmp))
        path = write_skill_sync_manifest(tmp, manifest)

        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["summary"]["total_records"] == 1
        print("[PASS] skill sync manifest written")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_export_plan_creates_missing_targets_and_skips_matching_targets():
    tmp = Path(tempfile.mkdtemp())
    try:
        skill = _skill("planner", body="Plan safely")
        _write_canonical(tmp, skill)
        claude_dir = tmp / ".claude" / "skills" / skill.id
        claude_dir.mkdir(parents=True)
        (claude_dir / "SKILL.md").write_text(export_to_claude_code(skill), encoding="utf-8")

        records = discover_skill_records(tmp)
        manifest = build_skill_sync_manifest(records)
        plan = build_skill_export_plan(
            tmp,
            records=records,
            manifest=manifest,
            target_ecosystems=["claude_code", "codex"],
        )
        actions = {(item["target"], item["skill_id"]): item for item in plan["actions"]}

        assert actions[("claude_code", "planner")]["action"] == "skip"
        assert actions[("codex", "planner")]["action"] == "create"
        assert plan["summary"]["create"] == 1
        print("[PASS] skill export plan handles missing and matching targets")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_export_plan_marks_content_drift_for_review():
    tmp = Path(tempfile.mkdtemp())
    try:
        canonical = _skill("review_me", body="Canonical behavior")
        drifted = _skill("review_me", body="Different behavior")
        _write_canonical(tmp, canonical)
        codex_dir = tmp / ".codex" / "skills" / canonical.id
        codex_dir.mkdir(parents=True)
        (codex_dir / "SKILL.md").write_text(export_to_claude_code(drifted), encoding="utf-8")

        records = discover_skill_records(tmp)
        plan = build_skill_export_plan(tmp, records=records, target_ecosystems=["codex"])

        assert plan["actions"][0]["action"] == "update"
        assert plan["actions"][0]["needs_review"] is True
        print("[PASS] skill export plan marks content drift for review")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_export_plan_apply_writes_non_review_actions():
    tmp = Path(tempfile.mkdtemp())
    try:
        skill = _skill("writer")
        _write_canonical(tmp, skill)
        plan = build_skill_export_plan(tmp, target_ecosystems=["codex"])
        result = apply_skill_export_plan(
            plan,
            skills_dir=tmp / "storage" / "skills",
            require_review=True,
            dry_run=False,
        )

        assert result["summary"]["applied"] == 1
        assert (tmp / ".codex" / "skills" / "writer" / "SKILL.md").exists()
        print("[PASS] skill export plan apply writes safe actions")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skill_sync_registry_refresh_writes_registry_payload():
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_canonical(tmp, _skill("registry_skill"))
        registry = SkillSyncRegistry(tmp, tmp / "storage", refresh_interval_seconds=30)
        status = registry.refresh(force=True)

        assert status["registry"]["state"] == "ok"
        assert status["manifest"]["summary"]["total_records"] == 1
        assert status["export_plan"]["summary"]["create"] == 4
        assert status["skill_graph"]["summary"]["total_skills"] == 1
        assert registry.registry_path.exists()
        saved = json.loads(registry.registry_path.read_text(encoding="utf-8"))
        assert saved["manifest"]["records"][0]["id"] == "registry_skill"
        assert saved["skill_graph"]["nodes"][0]["skill_id"] == "registry_skill"
        print("[PASS] skill sync registry writes shared status")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_dynamic_skill_graph_exposes_schema_providers_and_actions():
    tmp = Path(tempfile.mkdtemp())
    try:
        skill = _skill("graph_skill", body="Graph me")
        _write_canonical(tmp, skill)
        records = discover_skill_records(tmp)
        manifest = build_skill_sync_manifest(records)
        export_plan = build_skill_export_plan(
            tmp,
            records=records,
            manifest=manifest,
            target_ecosystems=["codex"],
        )
        graph = build_dynamic_skill_graph(
            tmp,
            records=records,
            manifest=manifest,
            export_plan=export_plan,
        )
        node = graph["nodes"][0]

        assert graph["summary"]["total_skills"] == 1
        assert node["skill_id"] == "graph_skill"
        assert node["input_schema"]["type"] == "object"
        assert node["providers"][0]["ecosystem"] == "canonical"
        assert node["pending_export_actions"][0]["target"] == "codex"
        assert node["callability"] == "available"
        print("[PASS] dynamic skill graph exposes schema providers and actions")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_agent_query_skills_tool_reads_dynamic_skill_graph():
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_canonical(tmp, _skill("data_analyzer", body="Analyze data"))
        agent = TapMakerAgent(
            llm=MockLLM(),
            project_root=tmp,
            storage_root=tmp / "storage",
            connect_mcp=False,
        )

        result = agent.executor.propose_action(
            "skillq",
            "query_skills",
            {"query": "data", "ecosystem": "canonical"},
        )

        assert result["ok"] is True
        assert result["count"] == 1
        assert result["skills"][0]["skill_id"] == "data_analyzer"
        assert result["skills"][0]["input_schema"]["type"] == "object"
        assert any(tool["name"] == "query_skills" for tool in agent.tools.list_tools())
        print("[PASS] agent query_skills tool reads dynamic skill graph")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_skill_sync_manifest_has_no_conflict_for_matching_export()
    test_skill_sync_detects_version_conflict()
    test_skill_sync_detects_same_version_content_drift()
    test_skill_sync_manifest_can_be_written()
    test_skill_export_plan_creates_missing_targets_and_skips_matching_targets()
    test_skill_export_plan_marks_content_drift_for_review()
    test_skill_export_plan_apply_writes_non_review_actions()
    test_skill_sync_registry_refresh_writes_registry_payload()
    test_dynamic_skill_graph_exposes_schema_providers_and_actions()
    test_agent_query_skills_tool_reads_dynamic_skill_graph()
    print("[PASS] skill sync tests")
