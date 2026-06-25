"""
tests/test_agents_md_parser.py — AGENTS.md 解析器测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.agents_md_parser import chunk_markdown, extract_tool_specs, parse_agents_md_files


def test_chunk_markdown_headings():
    text = """# Project Rules

Always use TypeScript.

## Tool Usage

Prefer builtins.

### Subsection

Detailed info here.
"""
    chunks = chunk_markdown(text, "AGENTS.md", max_chunk_chars=500, overlap_chars=50)
    headings = [c.heading for c in chunks]
    assert "Project Rules" in headings
    assert "Tool Usage" in headings
    assert "Subsection" in headings


def test_chunk_long_section_split():
    text = "# Big\n\n" + "\n\n".join([f"paragraph {i}" for i in range(20)])
    chunks = chunk_markdown(text, "AGENTS.md", max_chunk_chars=100, overlap_chars=20)
    assert len(chunks) >= 2
    # 每块都带 heading
    assert all(c.heading == "Big" for c in chunks)


def test_extract_tool_specs_json():
    text = """## Tool: run_linter

```json
{
  "description": "Run ESLint",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string"}
    },
    "required": ["path"]
  },
  "risk_level": "medium",
  "handler": {
    "type": "shell",
    "command": "npx eslint {path}"
  }
}
```
"""
    chunks = chunk_markdown(text, "AGENTS.md")
    specs = extract_tool_specs(chunks)
    assert len(specs) == 1
    spec = specs[0]
    assert spec["name"] == "run_linter"
    assert spec["description"] == "Run ESLint"
    assert spec["risk_level"] == "medium"
    assert spec["handler"]["type"] == "shell"


def test_parse_agents_md_files_skips_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "AGENTS.md").write_text("# Rules\n\nUse git.\n", encoding="utf-8")
        chunks, specs = parse_agents_md_files([root / "AGENTS.md", root / "MISSING.md"])
        assert len(chunks) >= 1
        assert specs == []


if __name__ == "__main__":
    test_chunk_markdown_headings()
    print("OK test_chunk_markdown_headings")
    test_chunk_long_section_split()
    print("OK test_chunk_long_section_split")
    test_extract_tool_specs_json()
    print("OK test_extract_tool_specs_json")
    test_parse_agents_md_files_skips_missing()
    print("OK test_parse_agents_md_files_skips_missing")
    print("\nAll agents_md parser tests passed.")
