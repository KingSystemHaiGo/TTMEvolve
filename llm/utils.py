"""
llm/utils.py — LLM 通用工具

供 ClaudeLLM、LocalLLM 等实现复用的 JSON 解析与提示词处理函数。
"""

from __future__ import annotations
import json
import re
from typing import Any, Dict


_DSMl_INVOKE_RE = re.compile(
    r'<\｜\｜DSML\｜\｜invoke\s+name="([^"]+)">(.*?)<\/\｜\｜DSML\｜\｜invoke>',
    re.DOTALL,
)
_DSMl_PARAM_RE = re.compile(
    r'<\｜\｜DSML\｜\｜parameter\s+name="([^"]+)"\s+string="true">(.*?)<\/\｜\｜DSML\｜\｜parameter>',
    re.DOTALL,
)


def _parse_dsml_tool_calls(text: str) -> Dict[str, Any]:
    """解析 DeepSeek DSML tool_calls 格式为 {tool, params}。"""
    match = _DSMl_INVOKE_RE.search(text)
    if not match:
        return {"done": True, "output": text}
    tool = match.group(1)
    params = {}
    for pm in _DSMl_PARAM_RE.finditer(match.group(2)):
        params[pm.group(1)] = pm.group(2).strip()
    return {"tool": tool, "params": params}


def parse_llm_json(raw: str, fallback_done: bool = True) -> Dict[str, Any]:
    """
    从 LLM 输出中提取 JSON 对象/数组。
    支持代码块、脏文本、第一个 {...} 或 [...] 的自动提取。
    失败时返回 {"done": True, "output": text} 作为最终回答兜底。
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    text = text.strip()

    # DeepSeek 等模型可能输出 XML 形式的 tool_calls
    if "<\｜\｜DSML\｜\｜tool_calls>" in text or "<\｜\｜DSML\｜\｜invoke" in text:
        return _parse_dsml_tool_calls(text)

    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 尝试从文本中提取第一个 JSON 对象或数组
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if not in_string:
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except Exception:
                            break
    # 最终回退：把整段文本作为回答
    if fallback_done:
        return {"done": True, "output": text}
    return {"_parse_error": True, "raw": text}
