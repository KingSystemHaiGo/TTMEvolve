from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from scripts.llm_runtime_interview import (
    _apply_llm_overrides,
    _attempt_feedback,
    _feedback_actionability,
    _fallback_specs,
    _normalize_feedback,
    _repair_max_tokens,
    _repair_timeout_seconds,
    _should_replace_final_payload,
    _should_retry_reasoning_truncation,
    _should_retry_feedback_timeout,
)
from scripts.summarize_llm_feedback import summarize


def test_normalize_feedback_rejects_non_object_json():
    payload = _normalize_feedback('[{"not":"an object"}]')

    assert payload["_parse_error"] is True
    assert "list" in payload["error"]


def test_normalize_feedback_rejects_empty_content():
    payload = _normalize_feedback("")

    assert payload["_parse_error"] is True
    assert payload["failure_type"] == "empty_feedback_content"


def test_feedback_timeout_retry_requires_response_started_or_force():
    before_headers = {"call_stats": {"response_started": False}}
    after_headers = {"call_stats": {"response_started": True}}

    assert _should_retry_feedback_timeout(before_headers) is False
    assert _should_retry_feedback_timeout(after_headers) is True
    assert _should_retry_feedback_timeout(before_headers, force_retry=True) is True


def test_feedback_retries_reasoning_truncation():
    payload = {
        "failure_type": "empty_feedback_content",
        "call_stats": {
            "finish_reason": "length",
            "content_length": 0,
            "reasoning_content_length": 306,
        },
    }

    assert _should_retry_reasoning_truncation(payload) is True
    assert _should_retry_reasoning_truncation({"failure_type": "empty_feedback_content", "call_stats": {}}) is False


def test_feedback_repair_max_tokens_precedence():
    assert _repair_max_tokens({}, {}, 140) == 1024
    assert _repair_max_tokens({"repair_max_tokens": 640}, {}, 140) == 640
    assert _repair_max_tokens({"repair_max_tokens": 640}, {"repair_max_tokens": 768}, 140) == 768
    assert _repair_max_tokens({"repair_max_tokens": 640}, {"repair_max_tokens": 768}, 140, 2048) == 2048


def test_feedback_repair_timeout_precedence():
    assert _repair_timeout_seconds({}, {}, 8) == 16.0
    assert _repair_timeout_seconds({"repair_timeout": 18}, {}, 8) == 18.0
    assert _repair_timeout_seconds({"repair_timeout": 18}, {"repair_timeout": 12}, 8) == 12.0
    assert _repair_timeout_seconds({"repair_timeout": 18}, {"repair_timeout": 12}, 8, 22) == 22.0


def test_feedback_skipped_fallback_does_not_mask_real_failure():
    real_failure = {"ok": False, "failure_type": "llm_interview_timeout"}
    skipped = {"ok": False, "failure_type": "feedback_provider_unconfigured", "skipped": True}
    real_after_skip = {"ok": False, "failure_type": "invalid_feedback_shape"}

    assert _should_replace_final_payload(real_failure, skipped) is False
    assert _should_replace_final_payload(skipped, real_after_skip) is True
    assert _should_replace_final_payload(real_failure, {"ok": True}) is True


def test_feedback_actionability_rejects_stale_claims():
    decision = _feedback_actionability(
        {"top_pain_point": "cross-Agent skill sync missing"},
        {"stale_claims": ["skill_sync_manifest"], "requires_human_review": True},
    )

    assert decision["actionable"] is False
    assert decision["decision"] == "reject_stale_feedback"
    assert "skill_sync_manifest" in decision["actionable_blockers"]
    assert "context_sync" in decision["next_feedback_prompt"]


def test_feedback_actionability_requires_repo_mapping_for_fictional_paths():
    decision = _feedback_actionability(
        {
            "top_pain_point": "tool routing",
            "files_likely_touched": ["internal/agent/skill_sync.go"],
        },
        {"stale_claims": [], "requires_human_review": False},
    )

    assert decision["actionable"] is False
    assert decision["decision"] == "needs_repo_mapping"
    assert decision["fictional_paths"] == ["internal/agent/skill_sync.go"]


def test_feedback_actionability_accepts_real_mapped_feedback():
    decision = _feedback_actionability(
        {
            "top_pain_point": "MakerMCP onboarding is too implicit",
            "files_likely_touched": ["agent/react_loop.py", "server/app_server.py"],
        },
        {"stale_claims": [], "requires_human_review": False},
    )

    assert decision["actionable"] is True
    assert decision["decision"] == "accept_for_human_mapping"


def test_feedback_replacement_prefers_actionable_over_stale_ok():
    actionable = {"ok": True, "actionable": True}
    stale = {"ok": True, "actionable": False, "decision": "reject_stale_feedback"}
    failure = {"ok": False, "failure_type": "llm_interview_timeout"}

    assert _should_replace_final_payload(failure, stale) is True
    assert _should_replace_final_payload(stale, actionable) is True
    assert _should_replace_final_payload(actionable, stale) is False


def test_feedback_fallback_specs_merge_cli_and_config():
    specs = _fallback_specs(
        {
            "fallbacks": [
                "deepseek",
                {
                    "provider": "qwen",
                    "model": "qwen-turbo",
                    "timeout": 8,
                },
                {},
            ]
        },
        "openai:gpt-4.1-mini, moonshot",
    )

    assert specs == [
        {"provider": "openai", "model": "gpt-4.1-mini"},
        {"provider": "moonshot"},
        {"provider": "deepseek"},
        {"provider": "qwen", "model": "qwen-turbo", "timeout": 8},
    ]


def test_feedback_llm_overrides_do_not_mutate_base_config():
    base = Config.__new__(Config)
    base.path = Path("config.json")
    base.data = {
        "llm": {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "base_url": "https://api.minimax.chat/v1",
            "timeout": 25,
        }
    }
    base._profiles = {}
    base._active_profile = "default"

    overridden = _apply_llm_overrides(
        base,
        provider="deepseek",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        timeout=8,
    )

    assert base.llm_provider() == "minimax"
    assert base.get("llm.model") == "MiniMax-M3"
    assert overridden.llm_provider() == "deepseek"
    assert overridden.get("llm.model") == "deepseek-v4-flash"
    assert overridden.get("llm.timeout") == 8.0


def test_feedback_provider_switch_uses_target_preset_and_scoped_key():
    base = Config.__new__(Config)
    base.path = Path("config.json")
    base.data = {
        "llm": {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "base_url": "https://api.minimax.chat/v1",
            "api_key": "minimax-global-key",
            "api_keys": {},
            "timeout": 25,
        }
    }
    base._profiles = {}
    base._active_profile = "default"

    overridden = _apply_llm_overrides(base, provider="deepseek", timeout=8)

    assert overridden.llm_provider() == "deepseek"
    assert overridden.get("llm.model") == "deepseek-v4-pro"
    assert overridden.get("llm.base_url") == "https://api.deepseek.com"
    assert overridden.get("llm.api_key") == ""
    assert base.get("llm.api_key") == "minimax-global-key"


def test_feedback_fallback_skips_provider_without_scoped_key(monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    else:
        import os

        os.environ.pop("DEEPSEEK_API_KEY", None)
    base = Config.__new__(Config)
    base.path = Path("config.json")
    base.data = {
        "llm": {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "base_url": "https://api.minimax.chat/v1",
            "api_key": "minimax-global-key",
            "api_keys": {},
            "timeout": 25,
        }
    }
    base._profiles = {}
    base._active_profile = "default"

    payload = _attempt_feedback(
        base_cfg=base,
        mode="fallback",
        prompt="{}",
        provider="deepseek",
        model=None,
        base_url=None,
        timeout=1,
        max_tokens=8,
        attempt="fallback_provider_1",
    )

    assert payload["failure_type"] == "feedback_provider_unconfigured"
    assert payload["skipped"] is True
    assert payload["provider"] == "deepseek"


def test_feedback_summary_counts_invalid_shape():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "llm-runtime-interview-1.json").write_text(
            json.dumps({"ok": False}, ensure_ascii=False),
            encoding="utf-8",
        )
        (root / "llm-runtime-interview-2.json").write_text(
            json.dumps({"ok": False, "failure_type": "llm_interview_timeout"}, ensure_ascii=False),
            encoding="utf-8",
        )

        payload = summarize(root)

        assert payload["total_runs"] == 2
        assert payload["counts"]["invalid_feedback_shape"] == 1
        assert payload["counts"]["llm_interview_timeout"] == 1


if __name__ == "__main__":
    test_normalize_feedback_rejects_non_object_json()
    test_normalize_feedback_rejects_empty_content()
    test_feedback_timeout_retry_requires_response_started_or_force()
    test_feedback_retries_reasoning_truncation()
    test_feedback_repair_max_tokens_precedence()
    test_feedback_repair_timeout_precedence()
    test_feedback_skipped_fallback_does_not_mask_real_failure()
    test_feedback_actionability_rejects_stale_claims()
    test_feedback_actionability_requires_repo_mapping_for_fictional_paths()
    test_feedback_actionability_accepts_real_mapped_feedback()
    test_feedback_replacement_prefers_actionable_over_stale_ok()
    test_feedback_fallback_specs_merge_cli_and_config()
    test_feedback_llm_overrides_do_not_mutate_base_config()
    test_feedback_provider_switch_uses_target_preset_and_scoped_key()
    test_feedback_fallback_skips_provider_without_scoped_key()
    test_feedback_summary_counts_invalid_shape()
    print("[PASS] llm runtime interview tests")
