"""
quick_test.py — 快速验证 ReAct + Executor 链路
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent.agent import TapMakerAgent
from core.config import Config
from llm.mock_llm import MockLLM

llm = MockLLM(scripted_actions=[
    {"tool": "list_directory", "params": {"path": "."}},
    {"done": True, "output": "已列出目录"},
])

agent = TapMakerAgent(
    llm=llm,
    config=Config("config.json"),
    human_confirm_callback=None,
)
result = agent.run("列出项目文件")
print("Output:", result.get("output"))
print("Iterations:", result.get("iteration_count"))
print("Repair:", result.get("repair_status"))
agent.close()
