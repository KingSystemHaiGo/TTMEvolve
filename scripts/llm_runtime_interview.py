from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Config
from core.runtime_events import feedback_event
from llm.api_errors import LLMAPIError, LLMTimeoutError
from llm.llm_factory import LLMFactory
from llm.provider_presets import provider_preset
from llm.utils import parse_llm_json


LIGHT_PROMPT = """你是 TTMEvolve 里真正执行任务的 Agent LLM。

只输出一行 JSON，不要解释，不要 Markdown，不要 `<think>`。

系统现状：
- ReAct 工具链、Workbench、取消、API timeout、Maker MCP status、三层事件已接入。
- 工具调用有超时和 partial observation；MCP stdio 超时会断开旧进程避免串线。
- 写入/副作用工具 observation 已带 `idempotency_key`、`committed`、`observed_at`。
- 本地文件写/删已支持 `committed=null` 后自动 `commit_reconcile`；Workbench 已显示最近提交态：已确认写入 / 未提交 / 待确认。
- 长任务工具已通过 `tool_progress` 心跳事件向 Workbench 展示运行时长和 heartbeat_count，不刷屏主聊天。
- Maker MCP status 已有 `remote_identity` 诊断：会标出 task/file lookup 工具是否存在、最近 MCP 返回里有哪些 id 字段，并已用于远端 `committed=null` 保守回查。
- 远端 `committed=null` 已有保守回查：通过 Maker MCP remote_identity 的 task/file lookup 工具查远端记录；只有 path、remote_id、task_id、file_id、asset_id、resource_id、idempotency_key 等明确身份匹配时才补 committed，工具名匹配会被拒绝避免假阳性；Workbench 会显示 `reconcile_status`、lookup 工具和 lookup 次数。
- 运行健康已显示 `context_saturation`，Workbench 会展示 token/context 窗口压力；ContextBudgetManager 已在预算紧张时主动压缩低优先级内容，保留任务、工具说明、最近步骤和旧的失败/提交态/plan_validation 证据，并暴露 `compression_applied`、`dropped_parts`、`truncated_chars`。
- 工具选择已经有 ranked/capped candidate tools、schema validation structured errors、tool_preflight 事件、失败时 suggested_next_step 与 alternatives，Workbench 会展示 preflight 失败和替代工具。
- ReAct 每步 observation 后已有轻量 `plan_validation` 事件：按 observation/提交态/重复动作输出 pass/warn/fail、expected_evidence、issues、next_check，并写回 trajectory 与 Workbench。
- ReAct 已有跨步 `goal_checklist`：按任务生成验收项，跟随每步 plan_validation/commit state/final output 更新，发 `goal_checklist` 事件，写入 result，并把 open criteria 注入下一轮上下文；Workbench 会展示验收清单。
- 提交态历史已有只读入口：`/sessions/{id}/commit-history?steps=5` 和 `/sessions/{id}/submissions?steps=5`。
- 仍未完成的方向：跨 Agent skill 同步、把反馈 artifact/事件元数据暴露给 Workbench、更强的领域特定验收标准生成。
请从“我作为 Agent 是否顺手”的角度，指出一个当前仍真实存在的最大卡点。
你必须避免重复提出已完成项：不要再只说“工具无法取消”“没有提交态三元组”“没有本地提交态回查”“没有 remote id 诊断”“没有远端 committed=null 回查”“没有 context 指标”“没有工具 preflight/替代工具建议”“没有计划验证事件”“没有主动上下文压缩”“没有提交态历史入口”“没有跨步目标/验收清单”。

输出严格 JSON：
{
  "top_pain_point": "一句话",
  "why_it_hurts_me": "为什么妨碍我工作",
  "smallest_fix": "最小可落地修复",
  "priority": "P0|P1|P2",
  "files_likely_touched": ["path"],
  "success_signal": "怎么判断改完变顺了"
}
"""


ULTRA_LIGHT_PROMPT = """你是 TTMEvolve 的 Agent LLM。只输出一行 JSON。
已完成：工具/MCP timeout、partial observation、提交态三元组、本地 commit_reconcile、远端 committed=null 保守回查、Workbench 提交态、Maker MCP remote_identity 诊断、context_saturation 指标、tool_preflight、替代工具建议、plan_validation 事件、主动上下文压缩指标与低优先级轨迹压缩、commit-history/submissions 查询入口、goal_checklist 跨步验收清单。
未完成候选：跨 Agent skill 同步、反馈 artifact/事件元数据 UI、更强的领域特定验收标准生成。
指出一个当前最大真实卡点，避开已完成项。
{"top_pain_point":"...","why_it_hurts_me":"...","smallest_fix":"...","priority":"P0|P1|P2","files_likely_touched":["path"],"success_signal":"..."}"""


FULL_PROMPT = """你现在不是普通助手，而是 TTMEvolve 运行时里真正被调用的 Agent LLM。

请从“你作为 Agent 实际执行任务是否顺手”的角度，审查下面这个系统。不要夸奖，不要泛泛而谈。

当前架构摘要：
- GUI: Electron + React。左侧 Agent 对话/Workbench，中间 Maker 浏览器预览，左中为文件/素材，代码编辑器只在打开文件时出现。
- 预览: Electron GUI 使用 BrowserView；Playwright browser_service 保留给 Agent 工具和 fallback。
- 后端: AppServer HTTP/SSE，按 session 创建 TapMakerAgent，基础 AppServer agent 保留 IDE/shared Maker MCP/control-plane。
- ReAct: think -> tool_selection -> choose_action -> validate -> Executor -> observation。
- 工具: read_file/list_directory/search_files/modify_file/execute_shell/delete_file/git_commit/browser_*，以及 Maker MCP 工具。
- 已完成可靠性机制: tool validation structured errors；工具/MCP timeout；partial observation；`idempotency_key`/`committed`/`observed_at`；本地文件写/删的 `commit_reconcile`；Maker MCP 远端 `committed=null` 保守回查；工具运行 `tool_progress` 心跳；Workbench 提交态/进度展示；三层 layer events；runtime event envelope；LLM feedback artifacts；Maker MCP remote_identity 诊断；context_saturation 指标；tool_preflight 事件；失败时 suggested_next_step 与 alternatives；Workbench preflight 展示；每步 `plan_validation` pass/warn/fail 事件与 Workbench 展示；主动上下文压缩 stats 与重要旧步骤保留；commit-history/submissions 查询入口；`goal_checklist` 跨步验收事件与 Workbench 展示。
- 仍未完成候选方向: 跨 Codex/Claude Code skill 体系同步；反馈 artifact/事件元数据 UI；更强的领域特定验收标准生成。
- 已知目标: TapTap Maker 开发 Agent，重点是任务响应速度、工具衔接、Maker MCP、上下文压缩、渐进式加载、跨 Agent skill 体系兼容。

请输出严格 JSON，格式：
{
  "top_pain_points": [
    {
      "title": "短标题",
      "why_it_hurts_me": "为什么这会妨碍你作为 Agent 工作",
      "symptom_user_sees": "用户会看到什么问题",
      "concrete_fix": "最小可落地修复",
      "priority": "P0|P1|P2",
      "files_likely_touched": ["path"]
    }
  ],
  "prompt_runtime_feedback": ["..."],
  "ui_feedback": ["..."],
  "tooling_feedback": ["..."],
  "one_change_to_do_first": {
    "title": "...",
    "reason": "..."
  }
}

约束：
- 不要重复已经完成的机制：不要只说“工具无法取消”“没有提交态三元组”“没有本地提交态回查”“没有远端 committed=null 回查”“没有 Workbench”“没有 remote id 诊断”“没有 context 指标”。
- 只基于上面的系统描述判断，不要虚构已经存在的代码细节。
- 优先指出让你执行任务不顺畅的地方。
- 每条 concrete_fix 必须是工程上可做的，不要写“优化体验”这种空话。
"""


def _safe_stats(llm: Any) -> Dict[str, Any]:
    stats_getter = getattr(llm, "last_call_stats", None)
    if not callable(stats_getter):
        return {}
    stats = stats_getter() or {}
    return {k: v for k, v in stats.items() if "key" not in k.lower()}


def _artifact_path(out_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return out_dir / f"llm-runtime-interview-{stamp}.json"


def _write_artifact(out_dir: Path, payload: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = _artifact_path(out_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _call_llm(llm: Any, prompt: str, max_tokens: int) -> str:
    if hasattr(llm, "_call"):
        return llm._call(
            system="只输出一行严格 JSON。不要解释，不要 Markdown，不要 <think>。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.0,
        )
    return llm.reflect(prompt)


def _feedback_payload(
    *,
    ok: bool,
    failure_type: Any,
    mode: str,
    provider: str,
    timeout: float,
    max_tokens: int,
    started: float,
    llm: Any,
    feedback: Any = None,
    raw: str = "",
    error: str = "",
    attempt: str = "primary",
) -> Dict[str, Any]:
    parsed = feedback if isinstance(feedback, dict) else None
    critique = _critique_feedback(parsed, mode) if ok and parsed else None
    actionability = _feedback_actionability(parsed, critique) if ok and parsed else {
        "actionable": False,
        "decision": "no_valid_feedback",
        "actionable_blockers": [failure_type or "feedback_call_failed"],
        "next_feedback_prompt": "Ask a configured low-latency feedback model for strict JSON feedback.",
    }
    payload: Dict[str, Any] = {
        "ok": ok,
        "failure_type": failure_type,
        "mode": mode,
        "provider": provider,
        "timeout_seconds": timeout,
        "max_tokens": max_tokens,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "feedback": parsed if ok else None,
        "critique": critique,
        "raw": raw,
        "call_stats": _safe_stats(llm),
        "attempt": attempt,
        **actionability,
    }
    if error:
        payload["error"] = error
    return payload


def _attempt_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "attempts"}


def _should_retry_feedback_timeout(
    attempt_payload: Dict[str, Any],
    *,
    force_retry: bool = False,
) -> bool:
    if force_retry:
        return True
    stats = attempt_payload.get("call_stats") or {}
    return bool(stats.get("response_started"))


def _should_retry_reasoning_truncation(attempt_payload: Dict[str, Any]) -> bool:
    stats = attempt_payload.get("call_stats") or {}
    return (
        attempt_payload.get("failure_type") == "empty_feedback_content"
        and stats.get("finish_reason") == "length"
        and int(stats.get("content_length") or 0) == 0
        and int(stats.get("reasoning_content_length") or 0) > 0
    )


def _repair_max_tokens(
    feedback_cfg: Dict[str, Any],
    spec: Dict[str, Any],
    fallback_tokens: int,
    cli_value: Optional[int] = None,
) -> int:
    if cli_value is not None:
        return int(cli_value)
    if spec.get("repair_max_tokens") is not None:
        return int(spec["repair_max_tokens"])
    configured = feedback_cfg.get("repair_max_tokens")
    if configured is not None:
        return int(configured)
    base_tokens = int(spec.get("max_tokens", fallback_tokens))
    return max(base_tokens * 4, 1024)


def _repair_timeout_seconds(
    feedback_cfg: Dict[str, Any],
    spec: Dict[str, Any],
    fallback_timeout: float,
    cli_value: Optional[float] = None,
) -> float:
    if cli_value is not None:
        return float(cli_value)
    if spec.get("repair_timeout") is not None:
        return float(spec["repair_timeout"])
    configured = feedback_cfg.get("repair_timeout")
    if configured is not None:
        return float(configured)
    return max(float(spec.get("timeout", fallback_timeout)) * 2.0, 16.0)


def _should_replace_final_payload(current: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    if current.get("ok") and current.get("actionable") is not False:
        return bool(candidate.get("ok") and candidate.get("actionable") is not False)
    if candidate.get("ok") and candidate.get("actionable") is not False:
        return True
    if current.get("ok") and candidate.get("ok"):
        return False
    if candidate.get("ok"):
        return True
    if candidate.get("skipped") and not current.get("skipped"):
        return False
    if current.get("skipped") and not candidate.get("skipped"):
        return True
    return True


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _fallback_specs(feedback_cfg: Dict[str, Any], cli_providers: Optional[str]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for item in _split_csv(cli_providers):
        provider, _, model = item.partition(":")
        spec = {"provider": provider}
        if model:
            spec["model"] = model
        specs.append(spec)

    configured = feedback_cfg.get("fallbacks", [])
    if isinstance(configured, list):
        for item in configured:
            if isinstance(item, str):
                if item.strip():
                    specs.append({"provider": item.strip()})
            elif isinstance(item, dict) and item.get("provider"):
                specs.append(dict(item))
    return specs


def _apply_llm_overrides(
    base_cfg: Config,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Config:
    cfg = base_cfg.clone()
    llm_cfg = cfg.data.setdefault("llm", {})
    original_provider = base_cfg.llm_provider()
    provider_changed = bool(provider and provider != original_provider)
    if timeout is not None:
        llm_cfg["timeout"] = float(timeout)
    if provider:
        llm_cfg["provider"] = provider
    if provider_changed:
        preset = provider_preset(provider)
        api_keys = llm_cfg.get("api_keys") or {}
        if not api_keys.get(provider):
            llm_cfg["api_key"] = ""
        llm_cfg["model"] = model or preset.get("model", "")
        llm_cfg["base_url"] = base_url or preset.get("base_url", "")
    elif model:
        llm_cfg["model"] = model
    if base_url:
        llm_cfg["base_url"] = base_url
    return cfg


def _provider_has_scoped_key(config: Config, provider: str) -> bool:
    llm_cfg = config.llm_config()
    api_keys = llm_cfg.get("api_keys") or {}
    if api_keys.get(provider):
        return True
    env_var = provider_preset(provider).get("env_var", "")
    return bool(env_var and os.getenv(env_var, "").strip())


def _skipped_feedback_payload(
    *,
    mode: str,
    provider: str,
    timeout: float,
    max_tokens: int,
    attempt: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "failure_type": "feedback_provider_unconfigured",
        "mode": mode,
        "provider": provider,
        "timeout_seconds": timeout,
        "max_tokens": max_tokens,
        "elapsed_ms": 0.0,
        "feedback": None,
        "critique": None,
        "raw": "",
        "call_stats": {},
        "attempt": attempt,
        "error": reason,
        "skipped": True,
    }


def _attempt_feedback(
    *,
    base_cfg: Config,
    mode: str,
    prompt: str,
    provider: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
    timeout: float,
    max_tokens: int,
    attempt: str,
) -> Dict[str, Any]:
    cfg = _apply_llm_overrides(
        base_cfg,
        provider=provider,
        model=model,
        base_url=base_url,
        timeout=timeout,
    )
    active_provider = cfg.llm_provider()
    if provider and provider != base_cfg.llm_provider() and not _provider_has_scoped_key(cfg, active_provider):
        return _skipped_feedback_payload(
            mode=mode,
            provider=active_provider,
            timeout=timeout,
            max_tokens=max_tokens,
            attempt=attempt,
            reason=(
                f"Feedback fallback provider '{active_provider}' has no provider-scoped key. "
                "Set llm.api_keys.<provider> or the provider-specific env var."
            ),
        )
    started = time.perf_counter()
    llm: Any = None
    try:
        llm = LLMFactory.create(active_provider, cfg)
        raw = _call_llm(llm, prompt, max_tokens=max_tokens)
        parsed = _normalize_feedback(raw)
        failure_type = parsed.get("failure_type") if parsed.get("_parse_error") else None
        return _feedback_payload(
            ok=not bool(parsed.get("_parse_error")),
            failure_type=failure_type or ("invalid_feedback_shape" if parsed.get("_parse_error") else None),
            mode=mode,
            provider=active_provider,
            timeout=timeout,
            max_tokens=max_tokens,
            started=started,
            llm=llm,
            feedback=parsed,
            raw=raw,
            attempt=attempt,
        )
    except LLMTimeoutError as e:
        return _feedback_payload(
            ok=False,
            failure_type="llm_interview_timeout",
            mode=mode,
            provider=active_provider,
            timeout=timeout,
            max_tokens=max_tokens,
            started=started,
            llm=llm,
            error=str(e),
            attempt=attempt,
        )
    except (LLMAPIError, RuntimeError, ValueError) as e:
        stats = _safe_stats(llm) if llm is not None else {}
        payload: Dict[str, Any] = {
            "ok": False,
            "failure_type": "llm_interview_api_error",
            "mode": mode,
            "provider": active_provider,
            "timeout_seconds": timeout,
            "max_tokens": max_tokens,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "feedback": None,
            "critique": None,
            "raw": "",
            "call_stats": stats,
            "attempt": attempt,
            "error": str(e),
        }
        return payload


def _normalize_feedback(raw: str) -> Dict[str, Any]:
    if not raw or not raw.strip():
        return {
            "_parse_error": True,
            "failure_type": "empty_feedback_content",
            "error": "Expected a JSON object, got empty model content",
            "parsed_value": None,
        }
    parsed = parse_llm_json(raw, fallback_done=False)
    if isinstance(parsed, dict):
        return parsed
    return {
        "_parse_error": True,
        "error": f"Expected a JSON object, got {type(parsed).__name__}",
        "parsed_value": parsed,
    }


def _critique_feedback(feedback: Dict[str, Any], mode: str) -> Dict[str, Any]:
    text = json.dumps(feedback, ensure_ascii=False)
    stale_claims = []
    completed_topics = {
        "tool_cancel_timeout": ["工具无法取消", "不能取消", "无法取消", "工具卡死"],
        "commit_state_triple": ["没有提交态", "没有 idempotency_key", "没有 committed", "没有 observed_at"],
        "local_commit_reconcile": ["没有本地提交态回查", "没有任何自动回查", "没有自动回查/对账机制"],
        "workbench_exists": ["没有 Workbench", "没有工作台"],
        "tool_preflight_alternatives": [
            "没有工具 preflight",
            "没有 preflight",
            "没有替代工具建议",
            "没有 alternatives",
            "工具规划/验证质量低下",
        ],
        "plan_validation_event": [
            "没有计划验证事件",
            "没有 plan_validation",
            "没有多步计划验证闭环",
            "无法自动验证多步计划是否成功执行",
        ],
        "active_context_compression": [
            "主动上下文压缩缺失",
            "没有自动压缩机制",
            "没有主动上下文压缩",
            "只能被动截断",
        ],
        "commit_history_endpoint": [
            "缺少提交态历史查询入口",
            "没有提交态历史",
            "无法按步回溯 agent 的提交状态",
            "没有 commit-history",
            "没有 submissions",
        ],
        "goal_checklist": [
            "没有跨步目标",
            "没有验收清单",
            "没有 goal_checklist",
            "跨步目标分解与验收标准生成",
        ],
        "skill_sync_manifest": [
            "no skill sync",
            "skill sync missing",
            "cross-Agent skill sync",
            "跨 Agent skill 同步",
            "跨Agent skill同步",
            "跨Agent skill无法动态发现",
            "没有 skill 同步",
            "没有跨 Agent skill",
            "无法动态发现",
            "无中央注册",
            "没有 query_skills",
            "技能定义分散",
            "启动时拉取最新skill",
        ],
    }
    completed_topics["context_sync_event"] = [
        "missing context_sync",
        "no context_sync",
        "no incremental context sync",
        "missing incremental context sync",
        "no context snapshot",
        "missing context snapshot",
        "no shared session context",
        "context sync missing",
        "cross-Agent session context sync",
        "上下文同步",
        "会话上下文同步",
        "增量上下文同步",
        "没有 context_sync",
        "没有上下文快照",
    ]
    for topic, needles in completed_topics.items():
        if any(needle in text for needle in needles):
            stale_claims.append(topic)
    return {
        "mode": mode,
        "stale_claims": stale_claims,
        "requires_human_review": bool(stale_claims),
        "note": (
            "Feedback may be pointing at an already-completed mechanism; inspect current code before implementing literally."
            if stale_claims
            else "No obvious stale completed-mechanism claim detected."
        ),
    }


def _feedback_actionability(
    feedback: Optional[Dict[str, Any]],
    critique: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not feedback:
        return {
            "actionable": False,
            "decision": "no_feedback",
            "actionable_blockers": ["missing_feedback"],
            "next_feedback_prompt": "Ask the LLM for one concrete current bottleneck as strict JSON.",
        }

    stale_claims = []
    if isinstance(critique, dict):
        stale_claims = list(critique.get("stale_claims") or [])
    if stale_claims:
        return {
            "actionable": False,
            "decision": "reject_stale_feedback",
            "actionable_blockers": stale_claims,
            "next_feedback_prompt": (
                "The previous feedback repeats completed mechanisms. Ask again for a bottleneck that assumes "
                "skill sync registry, skill graph UI, query_skills, context_sync snapshots, and "
                "GET /sessions/{id}/context-sync already exist. Prefer MakerMCP onboarding, remote invocation "
                "semantics, token efficiency, front/back runtime gaps, or TapTapMaker-specific UX."
            ),
        }

    likely_files = feedback.get("files_likely_touched") if isinstance(feedback, dict) else None
    fictional_paths = []
    if isinstance(likely_files, list):
        for item in likely_files:
            if not isinstance(item, str) or not item.strip():
                continue
            normalized = item.replace("\\", "/").strip()
            if normalized.startswith(("src/", "internal/")) and not (ROOT / normalized).exists():
                fictional_paths.append(normalized)
    if fictional_paths:
        return {
            "actionable": False,
            "decision": "needs_repo_mapping",
            "actionable_blockers": ["fictional_paths"],
            "fictional_paths": fictional_paths,
            "next_feedback_prompt": (
                "The feedback names paths that do not exist in this repository. Ask the LLM to restate the fix "
                "using real TTMEvolve boundaries such as agent/, core/, server/, frontend/, ecosystem/, llm/, "
                "memory/, learning/, or scripts/."
            ),
        }

    return {
        "actionable": True,
        "decision": "accept_for_human_mapping",
        "actionable_blockers": [],
        "next_feedback_prompt": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the active runtime LLM what is awkward for it as an Agent.")
    parser.add_argument("--mode", choices=["light", "full"], default="light")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--fallback-provider", default=None, help="Comma-separated fallback providers for feedback only.")
    parser.add_argument("--repair-max-tokens", type=int, default=None, help="Max tokens for retrying reasoning-only truncated feedback.")
    parser.add_argument("--repair-timeout", type=float, default=None, help="Timeout seconds for retrying reasoning-only truncated feedback.")
    parser.add_argument("--retry-same-provider", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--out-dir", default="docs/llm-feedback")
    args = parser.parse_args()

    cfg = Config(ROOT / "config.json").clone()
    mode = args.mode
    default_timeout = 12 if mode == "light" else 30
    feedback_cfg = cfg.get("llm.feedback", {}) or {}
    provider_override = args.provider or feedback_cfg.get("provider")
    model_override = args.model or feedback_cfg.get("model")
    base_url_override = args.base_url or feedback_cfg.get("base_url")
    timeout = float(args.timeout if args.timeout is not None else feedback_cfg.get("timeout", cfg.get("llm.interview_timeout", default_timeout)))
    max_tokens = int(args.max_tokens if args.max_tokens is not None else (220 if mode == "light" else 1800))
    prompt = LIGHT_PROMPT if mode == "light" else FULL_PROMPT
    prompt += (
        "\nCompleted after the base prompt: cross-Agent skill sync manifest, "
        "version conflict detection, same-version fingerprint drift detection, "
        "shared `storage/skill_sync/registry.json`, safe export plans, "
        "dynamic `skill_graph` with providers/input schema/preconditions/callability, "
        "Agent-callable `query_skills` tool over that graph, "
        "CLI `scripts/sync_skills.py --registry --export-plan`, AppServer endpoint `/skills/sync-status`, "
        "and ReAct `skill_sync` events after session start / plan validation. "
        "When the registry signature changes, generated skills are re-discovered before the next action. "
        "AgentWorkbench now displays Skill Graph sync state, skill count, pending export actions, and conflicts.\n"
        "ReAct now emits compact `context_sync` snapshots at session start and after meaningful step changes, "
        "including revision/signature/diff_keys, last tool/action, plan verdict, goal checklist, commit summary, "
        "skill sync summary, and artifact refs. AgentWorkbench displays Context Sync revision, last tool, "
        "plan/goal state, artifact count, and diff keys.\n"
        "AppServer now exposes read-only `GET /sessions/{id}/context-sync?steps=N` for external agents/processes "
        "to pull persisted context_sync snapshots without subscribing to SSE.\n"
        "Do not report missing cross-Agent skill sync, missing skill graph UI, or missing incremental context sync "
        "unless you are asking for deeper remote invocation, multi-process notification, or distributed context sharing."
    )

    primary = _attempt_feedback(
        base_cfg=cfg,
        mode=mode,
        prompt=prompt,
        provider=provider_override,
        model=model_override,
        base_url=base_url_override,
        timeout=timeout,
        max_tokens=max_tokens,
        attempt="primary",
    )
    attempts = [_attempt_snapshot(primary)]
    payload = primary

    if not primary["ok"] and primary.get("failure_type") == "llm_interview_timeout":
        should_retry_same = _should_retry_feedback_timeout(primary, force_retry=args.retry_same_provider)
        if should_retry_same:
            retry_timeout = min(timeout, 12.0)
            retry_tokens = min(max_tokens, 140)
            payload = _attempt_feedback(
                base_cfg=cfg,
                mode="ultra_light",
                prompt=ULTRA_LIGHT_PROMPT,
                provider=provider_override,
                model=model_override,
                base_url=base_url_override,
                timeout=retry_timeout,
                max_tokens=retry_tokens,
                attempt="fallback_same_provider_after_timeout",
            )
            attempts.append(_attempt_snapshot(payload))

    if (not payload["ok"]) or payload.get("actionable") is False:
        fallback_timeout = float(feedback_cfg.get("fallback_timeout", min(timeout, 10.0)))
        fallback_tokens = int(feedback_cfg.get("fallback_max_tokens", min(max_tokens, 140)))
        for index, spec in enumerate(_fallback_specs(feedback_cfg, args.fallback_provider), start=1):
            candidate = _attempt_feedback(
                base_cfg=cfg,
                mode="fallback",
                prompt=ULTRA_LIGHT_PROMPT,
                provider=spec.get("provider"),
                model=spec.get("model"),
                base_url=spec.get("base_url"),
                timeout=float(spec.get("timeout", fallback_timeout)),
                max_tokens=int(spec.get("max_tokens", fallback_tokens)),
                attempt=f"fallback_provider_{index}",
            )
            attempts.append(_attempt_snapshot(candidate))
            if _should_replace_final_payload(payload, candidate):
                payload = candidate
            if candidate["ok"] and candidate.get("actionable") is not False:
                break
            if _should_retry_reasoning_truncation(candidate):
                retry_tokens = _repair_max_tokens(feedback_cfg, spec, fallback_tokens, args.repair_max_tokens)
                retry_timeout = _repair_timeout_seconds(
                    feedback_cfg,
                    spec,
                    fallback_timeout,
                    args.repair_timeout,
                )
                candidate = _attempt_feedback(
                    base_cfg=cfg,
                    mode="fallback_repair",
                    prompt=ULTRA_LIGHT_PROMPT,
                    provider=spec.get("provider"),
                    model=spec.get("model"),
                    base_url=spec.get("base_url"),
                    timeout=retry_timeout,
                    max_tokens=retry_tokens,
                    attempt=f"fallback_provider_{index}_reasoning_retry",
                )
                attempts.append(_attempt_snapshot(candidate))
                if _should_replace_final_payload(payload, candidate):
                    payload = candidate
                if candidate["ok"] and candidate.get("actionable") is not False:
                    break
            if candidate.get("failure_type") in {"invalid_feedback_shape", "empty_feedback_content"}:
                continue

    status_code = 0 if payload.get("ok") else 4
    if payload.get("failure_type") == "llm_interview_timeout":
        status_code = 2
    elif payload.get("failure_type") == "llm_interview_api_error":
        status_code = 3

    if not payload.get("ok"):
        payload.setdefault(
            "concrete_fix",
            "Configure llm.feedback.fallbacks with at least one low-latency provider/model that has a valid provider-scoped API key.",
        )
        if payload.get("failure_type") == "llm_interview_timeout" and not _fallback_specs(feedback_cfg, args.fallback_provider):
            payload["skipped_fallback"] = True
            payload["skip_reason"] = "no_feedback_fallback_provider_configured"

    payload["attempts"] = attempts

    if args.save:
        path = _write_artifact(ROOT / args.out_dir, payload)
        payload["artifact"] = str(path)
        path.write_text(
            json.dumps({**payload, "event": feedback_event(payload)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return status_code


if __name__ == "__main__":
    raise SystemExit(main())
