"""
memory/agents_md_parser.py — AGENTS.md 解析器

把项目规范 markdown 文件切成语义块，并提取其中声明的动态工具规范。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .vector_index import TextChunk


TOOL_HEADING_RE = re.compile(r"^#+\s*Tool:\s*(.+)$", re.MULTILINE)
CODE_BLOCK_RE = re.compile(r"```(?:json|yaml|yml)?\s*\n(.*?)\n```", re.DOTALL)


def chunk_markdown(
    text: str,
    source: str,
    max_chunk_chars: int = 800,
    overlap_chars: int = 100,
) -> List[TextChunk]:
    """按 markdown 标题层级分块。

    每个 chunk 保留最近的父标题、在源文件中的 offset 和原始文本。
    当单节内容超过 max_chunk_chars 时，按段落进一步切分并保留 overlap。
    """
    lines = text.splitlines()
    chunks: List[TextChunk] = []
    current_heading = ""
    current_offset = 0
    buffer: List[str] = []

    def flush(heading: str, offset: int, body_lines: List[str]) -> None:
        body = "\n".join(body_lines).strip()
        if not body:
            return
        # 如果 body 太长，按段落切分
        if len(body) <= max_chunk_chars:
            chunks.append(TextChunk(
                id=f"{source}::{heading}:{offset}",
                text=body,
                source=source,
                heading=heading,
                offset=offset,
                meta={"type": "convention"},
            ))
            return

        paragraphs = re.split(r"\n\s*\n", body)
        part: List[str] = []
        part_offset = offset
        for para in paragraphs:
            if not para.strip():
                continue
            if part and sum(len(p) + 1 for p in part) + len(para) > max_chunk_chars:
                text_block = "\n\n".join(part).strip()
                chunks.append(TextChunk(
                    id=f"{source}::{heading}:{part_offset}",
                    text=text_block,
                    source=source,
                    heading=heading,
                    offset=part_offset,
                    meta={"type": "convention"},
                ))
                # 保留 overlap
                overlap_text = text_block[-overlap_chars:] if len(text_block) > overlap_chars else text_block
                part = [overlap_text, para]
                part_offset += len(text_block) - len(overlap_text)
            else:
                part.append(para)
        if part:
            text_block = "\n\n".join(part).strip()
            chunks.append(TextChunk(
                id=f"{source}::{heading}:{part_offset}",
                text=text_block,
                source=source,
                heading=heading,
                offset=part_offset,
                meta={"type": "convention"},
            ))

    for i, line in enumerate(lines):
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            flush(current_heading, current_offset, buffer)
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            current_heading = title
            current_offset = sum(len(lines[j]) + 1 for j in range(i))
            buffer = [line]
            continue
        buffer.append(line)

    flush(current_heading, current_offset, buffer)

    # 去重：如果多个 chunk 文本相同，只保留第一个
    seen_text: set[str] = set()
    unique: List[TextChunk] = []
    for c in chunks:
        if c.text in seen_text:
            continue
        seen_text.add(c.text)
        unique.append(c)
    return unique


def extract_tool_specs(chunks: List[TextChunk]) -> List[Dict[str, Any]]:
    """从 chunk 文本中提取 Tool 规范。"""
    specs: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    for chunk in chunks:
        text = chunk.text
        for match in TOOL_HEADING_RE.finditer(text):
            name = match.group(1).strip()
            if name in seen_names:
                continue
            # 找该标题后的第一个代码块
            after = text[match.end():]
            cb_match = CODE_BLOCK_RE.search(after)
            if not cb_match:
                continue
            block = cb_match.group(1).strip()
            try:
                spec = json.loads(block)
            except json.JSONDecodeError:
                continue
            if not isinstance(spec, dict):
                continue
            spec["name"] = name
            spec.setdefault("description", spec.get("description", ""))
            spec.setdefault("parameters", {"type": "object", "properties": {}})
            spec.setdefault("risk_level", "medium")
            spec.setdefault("source", chunk.source)
            specs.append(spec)
            seen_names.add(name)

    return specs


def parse_agents_md_files(
    paths: List[Path],
    max_chunk_chars: int = 800,
    overlap_chars: int = 100,
) -> Tuple[List[TextChunk], List[Dict[str, Any]]]:
    """解析一组 AGENTS.md 文件，返回 (chunks, tool_specs)。"""
    all_chunks: List[TextChunk] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        chunks = chunk_markdown(text, str(path), max_chunk_chars, overlap_chars)
        all_chunks.extend(chunks)

    tool_specs = extract_tool_specs(all_chunks)
    return all_chunks, tool_specs
