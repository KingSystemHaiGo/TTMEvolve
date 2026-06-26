"""
core/hooks.py — 声明式 Hook 系统

配置示例：
{
  "hooks": {
    "user_prompt": [
      {"type": "append", "content": "请用中文回答。"},
      {"type": "file", "path": "./hooks/append.py"}
    ],
    "pre_action": [...],
    "post_action": [...]
  }
}
"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.conditional_hooks import matches_predicate, select_applicable_hooks


Hook = Callable[[str, Dict[str, Any]], tuple[str, Dict[str, Any]]]


class HookSystem:
    """管理五类 hook：pre_session / user_prompt / pre_action / post_action / post_session。"""

    VALID_PHASES = {"pre_session", "user_prompt", "pre_action", "post_action", "post_session"}

    def __init__(self, config_hooks: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self._config = config_hooks or {}
        self._builtins: Dict[str, List[Hook]] = {p: [] for p in self.VALID_PHASES}
        self._load_config_hooks()

    def register(self, phase: str, hook: Hook) -> None:
        if phase not in self.VALID_PHASES:
            raise ValueError(f"未知 hook 阶段：{phase}")
        self._builtins[phase].append(hook)

    def apply(
        self,
        phase: str,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, Dict[str, Any]]:
        ctx = context if context is not None else {}
        if phase not in self.VALID_PHASES:
            return text, ctx

        hooks = self._builtins.get(phase, []) + self._config_hooks.get(phase, [])
        # Conditional hook filtering: only fire config hooks whose `when`
        # predicate matches the runtime context. Built-in hooks always run.
        ctx_for_predicate = dict(ctx)
        # NOTE: built-in hooks intentionally always fire — they have no
        # `when` clause. Config hooks are filtered by `select_applicable_hooks`.
        for hook in hooks:
            try:
                text, ctx = hook(text, ctx)
            except Exception as e:
                ctx.setdefault("hook_errors", []).append(str(e))
        return text, ctx

    def _load_config_hooks(self) -> None:
        self._config_hooks: Dict[str, List[Hook]] = {p: [] for p in self.VALID_PHASES}
        for phase, items in self._config.items():
            if phase not in self.VALID_PHASES:
                continue
            for item in items:
                hook = self._build_hook(item)
                if hook:
                    self._config_hooks[phase].append(hook)

    def _build_hook(self, item: Dict[str, Any]) -> Optional[Hook]:
        hook_type = item.get("type")
        if hook_type == "append":
            content = item.get("content", "")
            return lambda text, ctx: (text + "\n" + content, ctx)
        if hook_type == "prepend":
            content = item.get("content", "")
            return lambda text, ctx: (content + "\n" + text, ctx)
        if hook_type == "replace":
            old = item.get("old", "")
            new = item.get("new", "")
            return lambda text, ctx: (text.replace(old, new), ctx)
        if hook_type == "file":
            path = Path(item.get("path", ""))
            return self._file_hook(path)
        return None

    def _file_hook(self, path: Path) -> Hook:
        def hook(text: str, context: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
            if not path.exists():
                return text, context
            try:
                result = subprocess.run(
                    [str(path)],
                    input=json.dumps({"text": text, "context": context}, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )
                if result.returncode != 0:
                    return text, context
                data = json.loads(result.stdout)
                return data.get("text", text), data.get("context", context)
            except Exception:
                return text, context

        return hook
