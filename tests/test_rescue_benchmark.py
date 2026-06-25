"""
tests/test_rescue_benchmark.py — Phase 8 真实任务救援闭环实测

在 taptap-maker-project 的临时副本上运行「季度祭典」功能开发任务：
- 本地模型被故意降级，前 N 步失败以触发专家救援。
- 专家 LLM 使用 config.json 中配置的 real API（DeepSeek / Claude）。
- 验证救援事件、专家步骤、蒸馏产出。

运行：
    python tests/test_rescue_benchmark.py

环境要求：
- config.json 中 expert.enabled=true 且 llm.api_key / expert.api_key 有效。
- 网络可访问对应 API。
"""

from __future__ import annotations
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from learning.knowledge_base import KnowledgeBase
from tests.helpers.always_failing_mock_llm import AlwaysFailingMockLLM
from tests.helpers.degraded_mock_llm import DegradedMockLLM


def _load_task_spec(name: str = "seasonal_festival_task") -> dict:
    path = _PROJECT_ROOT / "tests" / "benchmark_tasks" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_project(src: Path) -> Path:
    dst = Path(tempfile.mkdtemp(prefix="ttm_benchmark_project_"))
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
        ".git", "storage", ".tmp", "node_modules", "dist"
    ))
    return dst


def _make_config(base_config_path: Path, project_root: Path, storage_root: Path) -> Config:
    cfg = Config(base_config_path)
    cfg.data["project_root"] = str(project_root)
    cfg.data["storage_root"] = str(storage_root)
    cfg.data["sandbox"] = {"mode": "workspace-write"}
    cfg.data["approval"] = {"policy": "never"}
    cfg.data["expert"] = cfg.data.get("expert", {})
    cfg.data["expert"]["enabled"] = True
    cfg.data["rescue"] = {
        "max_consecutive_errors": 2,
        "max_iterations_ratio": 0.75,
        "detect_repeated_actions": True,
        "health_degraded": False,
        "max_rescue_per_session": 3,
        "cooldown_seconds": 0,
        "max_takeover_steps": 5,
        "distill_after_rescue": True,
        "skip_if_no_expert_key": True,
    }
    cfg.data["learning"] = cfg.data.get("learning", {})
    cfg.data["learning"]["skill_generation_enabled"] = True
    cfg.data["learning"]["expert_skill_confidence_floor"] = 0.75
    cfg.data["runtime"] = cfg.data.get("runtime", {})
    cfg.data["runtime"]["human_confirm_for_core_changes"] = False
    cfg._profiles = cfg.data.get("profiles", {})
    return cfg


def _event_names(events: list) -> list:
    return [e.get("type") for e in events]


def _count_expert_steps(trajectory: list) -> int:
    return sum(1 for s in trajectory if s.get("source") == "expert")


def _files_created(project_root: Path, expected_files: list) -> list:
    created = []
    for rel in expected_files:
        path = project_root / rel
        if path.exists():
            created.append(rel)
    return created


def _patterns_found(project_root: Path, expected_patterns: list) -> dict:
    found = {p: False for p in expected_patterns}
    for root, _, files in project_root.walk():
        for fname in files:
            if not fname.endswith(".lua"):
                continue
            try:
                text = (root / fname).read_text(encoding="utf-8")
            except Exception:
                continue
            for pat in expected_patterns:
                if pat in text:
                    found[pat] = True
    return found


def main():
    spec = _load_task_spec()
    src_project = Path(spec["project_root"]).resolve()
    if not src_project.exists():
        print(f"[ERROR] source project not found: {src_project}")
        sys.exit(1)

    # 验证 API key
    base_cfg = Config(_PROJECT_ROOT / "config.json")
    api_key = base_cfg.get("llm.api_key", "") or base_cfg.get("expert.api_key", "")
    if not api_key or api_key.strip().lower().startswith("sk-...") or api_key.strip() == "":
        print("[SKIP] real expert API key not configured in config.json (llm.api_key / expert.api_key)")
        sys.exit(0)

    print(f"[INFO] source project: {src_project}")
    print("[INFO] copying project to temp dir...")
    project_copy = _copy_project(src_project)
    storage_root = project_copy / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] project copy: {project_copy}")

    cfg = _make_config(_PROJECT_ROOT / "config.json", project_copy, storage_root)

    # 故意失败的本地模型：每步都失败，迫使专家通过多次救援 direct_action 推进任务
    local_llm = AlwaysFailingMockLLM(
        fail_action={"tool": "read_file", "params": {"path": "this_file_does_not_exist.txt"}},
    )

    agent = TapMakerAgent(llm=local_llm, config=cfg, project_root=project_copy, storage_root=storage_root)
    if agent.rescue_orchestrator is None:
        print("[ERROR] rescue orchestrator not initialized; check expert.enabled and api_key")
        sys.exit(1)

    task = spec["task"]
    print(f"[INFO] task length: {len(task)} chars")
    print("[INFO] running benchmark (this may take a while and consume API tokens)...")
    started_at = time.time()
    result = agent.run(task)
    elapsed = time.time() - started_at

    events = agent.get_events(result.get("session_id", ""))
    names = _event_names(events)
    trajectory = result.get("trajectory", [])
    expert_steps = _count_expert_steps(trajectory)

    print(f"\n[REPORT] session_id={result.get('session_id')}")
    print(f"[REPORT] elapsed_seconds={elapsed:.1f}")
    print(f"[REPORT] iteration_count={result.get('iteration_count', 0)}")
    print(f"[REPORT] expert_steps={expert_steps}")
    print(f"[REPORT] events={names}")

    # 断言 1：触发了救援
    assert "rescue_triggered" in names, f"rescue_triggered not in events: {names}"
    print("[PASS] rescue triggered")

    # 断言 2：专家参与了轨迹或产生了 rescue_applied
    assert expert_steps > 0 or "rescue_applied" in names, (
        f"no expert step and no rescue_applied: {names}"
    )
    print("[PASS] expert engaged")

    # 断言 3：应用了救援
    assert "rescue_applied" in names, f"rescue_applied not in events: {names}"
    print("[PASS] rescue applied")

    # 断言 4：产生了蒸馏事件
    assert "rescue_distilled" in names, f"rescue_distilled not in events: {names}"
    print("[PASS] rescue distilled")

    # 断言 5：任务有输出
    output = result.get("output", "")
    print(f"[REPORT] output=\n{output}\n")
    assert output, "task output is empty"
    print(f"[PASS] task has output ({len(output)} chars)")

    # 报告任务产物（Phase 8 重点验证救援闭环，不强制完整功能一次完成）
    created = _files_created(project_copy, spec.get("expected_files", []))
    patterns = _patterns_found(project_copy, spec.get("expected_patterns", []))
    print(f"[REPORT] expected_files_created={created}")
    print(f"[REPORT] patterns_found={patterns}")
    if created or any(patterns.values()):
        print("[PASS] task artifact evidence found")
    else:
        print("[WARN] no expected artifacts created in this run; rescue loop was exercised but task was not fully completed")

    # 断言 7：知识库存在 expert_rescue 条目
    kb = agent.knowledge_base
    hits = kb.search("seasonal festival rescue", top_k=10)
    rescue_hits = [h for h in hits if "expert_rescue" in h.get("tags", [])]
    assert rescue_hits, "no expert_rescue entries in knowledge base"
    print(f"[PASS] knowledge base has {len(rescue_hits)} expert_rescue entries")

    print("\n[PASS] all rescue benchmark assertions")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
