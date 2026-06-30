"""Tests for the multimodal LLM interface and provider integration (Q1.2-Q1.3)."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from llm.content import ImageBlock, TextBlock
from llm.interface import LLMInterface
from llm.mock_llm import MockLLM
from llm.unconfigured_llm import UnconfiguredLLM


@pytest.fixture
def png_path(tmp_path: Path) -> Path:
    path = tmp_path / "pixel.png"
    path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAAAQABh6FO1AAAAABJRU5ErkJggg=="
        )
    )
    return path


def test_llm_interface_default_supports_multimodal_is_false():
    """The base interface does not promise multimodal; providers opt in."""

    class _Stub(LLMInterface):
        def think(self, task, context, trajectory, tools_description):
            return ""

        def choose_action(self, task, thought, tools_description):
            return {}

        def reflect(self, prompt):
            return ""

        def generate_code(self, prompt):
            return ""

    assert _Stub.supports_multimodal is False


def test_default_think_multimodal_falls_back_to_text(png_path: Path):
    """Without an override, the interface flattens images to text placeholders."""

    captured = {}

    class _Capturing(LLMInterface):
        def think(self, task, context, trajectory, tools_description):
            captured["context"] = context
            return "stub"

        def choose_action(self, task, thought, tools_description):
            return {}

        def reflect(self, prompt):
            return ""

        def generate_code(self, prompt):
            return ""

    image = ImageBlock(source=str(png_path), caption="preview")
    text = TextBlock("ctx")
    out = _Capturing().think_multimodal(
        task="t",
        content=[text, image],
        trajectory=[],
        tools_description="",
    )
    assert out == "stub"
    assert "ctx" in captured["context"]
    assert "preview" in captured["context"]


def test_mock_llm_supports_multimodal_and_records_calls(png_path: Path):
    mock = MockLLM()
    assert mock.supports_multimodal is True
    image = ImageBlock(source=str(png_path), caption="frame")
    text = TextBlock("see image")
    out = mock.think_multimodal(
        task="play next",
        content=[text],
        trajectory=[],
        tools_description="schema",
        attachments=[image],
    )
    assert "Mock multimodal think" in out
    assert len(mock.multimodal_calls) == 1
    call = mock.multimodal_calls[0]
    assert call["task"] == "play next"
    assert call["text_block_count"] == 1
    assert call["attachments"] == [str(png_path)]
    assert call["tools_description_chars"] == len("schema")


def test_mock_llm_choose_action_multimodal_returns_action(png_path: Path):
    mock = MockLLM(scripted_actions=[{"tool": "noop", "params": {}}])
    image = ImageBlock(source=str(png_path))
    action = mock.choose_action_multimodal(
        task="t",
        thought="thought",
        tools_description="",
        attachments=[image],
    )
    assert action == {"tool": "noop", "params": {}}


def test_unconfigured_llm_think_multimodal_raises():
    llm = UnconfiguredLLM("no api key")
    assert llm.supports_multimodal is False
    with pytest.raises(RuntimeError):
        llm.think_multimodal("t", [TextBlock("ctx")], [], "", attachments=[])


def test_mock_llm_text_path_still_works(png_path: Path):
    """Adding multimodal must not break the existing text-only call sites."""
    mock = MockLLM()
    out = mock.think("play", "ctx", [], "schema")
    assert out == "Mock thinking for: play"


def test_router_passthrough_to_multimodal_provider(png_path: Path):
    """When the primary provider supports multimodal, the router calls
    ``think_multimodal`` on it. When it does not, the router flattens
    images and falls back to plain ``think``."""
    from llm.router import LLMRouter

    image = ImageBlock(source=str(png_path), caption="snap")
    mock = MockLLM()
    router = LLMRouter(primary=mock, fallbacks=[])
    out = router.think_multimodal(
        task="t",
        content=[TextBlock("ctx")],
        trajectory=[],
        tools_description="",
        attachments=[image],
    )
    assert "Mock multimodal think" in out
    assert len(mock.multimodal_calls) == 1


def test_router_falls_back_to_text_when_provider_lacks_multimodal(png_path: Path):
    from llm.router import LLMRouter

    class _TextOnly(LLMInterface):
        supports_multimodal = False

        def __init__(self):
            self.calls: List[Dict[str, Any]] = []

        def think(self, task, context, trajectory, tools_description):
            self.calls.append({"context": context})
            return "ok"

        def choose_action(self, task, thought, tools_description):
            return {}

        def reflect(self, prompt):
            return ""

        def generate_code(self, prompt):
            return ""

    image = ImageBlock(source=str(png_path), caption="snap")
    provider = _TextOnly()
    router = LLMRouter(primary=provider, fallbacks=[])
    out = router.think_multimodal(
        task="t",
        content=[TextBlock("ctx")],
        trajectory=[],
        tools_description="",
        attachments=[image],
    )
    assert out == "ok"
    assert len(provider.calls) == 1
    assert "snap" in provider.calls[0]["context"]


def test_anthropic_think_multimodal_builds_serialized_messages(monkeypatch, png_path: Path):
    """Verify the Claude implementation serializes the content blocks
    into Anthropic Messages format without going to the network."""
    from llm import claude_llm

    class _FakeClaude(claude_llm.ClaudeLLM):
        def __init__(self):
            self.captured = None

        def _call(self, system, messages, max_tokens=1024, content_blocks=None):
            self.captured = {
                "system": system,
                "messages": messages,
                "content_blocks": content_blocks,
            }
            return "stub"

        # The real __init__ requires API key, so we patch it out.
        def _bypass(self): pass

    fake = _FakeClaude.__new__(_FakeClaude)
    fake.captured = None
    fake.api_key = "x"
    fake.model = "claude-test"
    fake._last_call_stats = {}

    image = ImageBlock(source=str(png_path))
    out = fake.think_multimodal(
        task="play",
        content=[TextBlock("hello")],
        trajectory=[],
        tools_description="schema",
        attachments=[image],
    )
    assert out == "stub"
    assert fake.captured["content_blocks"] is not None
    blocks = fake.captured["content_blocks"]
    # Framing text + image should be present
    assert any(isinstance(b, TextBlock) for b in blocks)
    assert any(isinstance(b, ImageBlock) for b in blocks)
    # Anthropic translation should yield a base64 image block.
    anth = [b.to_anthropic() for b in blocks]
    assert any(b["type"] == "image" and b["source"]["type"] == "base64" for b in anth)
