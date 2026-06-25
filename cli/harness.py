"""
core/harness.py — Harness 统一入口

对外只暴露 AgentSession 和 run_session。
CLI、App Server、未来 GUI 都通过 Harness 启动任务。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.agent import TapMakerAgent
from core.config import Config
from llm.llm_factory import LLMFactory


@dataclass
class AgentSession:
    session_id: str
    task: str
    profile: Optional[str]
    provider: Optional[str]
    events: List[Dict[str, Any]]
    result: Optional[Dict[str, Any]] = None


class Harness:
    """统一的 Agent 执行 Harness。"""

    def __init__(self, config_path: Optional[str] = None):
        self.config = Config(config_path)

    def run_session(
        self,
        task: str,
        profile: Optional[str] = None,
        provider: Optional[str] = None,
        human_confirm_callback=None,
    ) -> AgentSession:
        cfg = self.config
        if profile:
            cfg._active_profile = profile
        active_provider = provider or cfg.llm_provider()
        llm = LLMFactory.create(active_provider, cfg)
        agent = TapMakerAgent(
            llm=llm,
            config=cfg,
            human_confirm_callback=human_confirm_callback,
        )
        session_id = agent._new_session_id()
        events = agent.get_events(session_id)
        result = agent.run(task, session_id=session_id)
        agent.close()
        return AgentSession(
            session_id=session_id,
            task=task,
            profile=profile,
            provider=active_provider,
            events=events,
            result=result,
        )
