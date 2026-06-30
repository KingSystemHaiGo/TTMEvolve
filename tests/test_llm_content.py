"""Tests for the multimodal ContentBlock layer (Q1.1-Q1.4)."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from llm.content import (
    ImageBlock,
    TextBlock,
    blocks_from_strings,
    to_anthropic_messages,
    to_openai_messages,
    to_text_fallback,
)


@pytest.fixture
def png_path(tmp_path: Path) -> Path:
    """A tiny but valid 1x1 PNG so ImageBlock.load_bytes has something to read."""
    path = tmp_path / "pixel.png"
    # 1x1 transparent PNG (67 bytes), hand-encoded to avoid a Pillow dep.
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAA"
        "AAQABh6FO1AAAAABJRU5ErkJggg=="
    )
    path.write_bytes(base64.b64decode(b64))
    return path


def test_text_block_round_trips_through_providers():
    block = TextBlock("hello")
    assert block.to_anthropic() == {"type": "text", "text": "hello"}
    assert block.to_openai() == {"type": "text", "text": "hello"}
    assert block.to_text_fallback() == "hello"


def test_image_block_loads_bytes_from_path(png_path: Path):
    block = ImageBlock(source=str(png_path), caption="pixel")
    assert block.media_type == "image/png"
    payload = block.load_bytes()
    assert payload.startswith(b"\x89PNG")
    assert len(payload) > 0


def test_image_block_anthropic_serializes_base64(png_path: Path):
    block = ImageBlock(source=str(png_path), caption="pixel")
    out = block.to_anthropic()
    assert out["type"] == "image"
    assert out["source"]["type"] == "base64"
    assert out["source"]["media_type"] == "image/png"
    decoded = base64.b64decode(out["source"]["data"])
    assert decoded.startswith(b"\x89PNG")


def test_image_block_openai_serializes_data_url(png_path: Path):
    block = ImageBlock(source=str(png_path), caption="pixel", detail="high")
    out = block.to_openai()
    assert out["type"] == "image_url"
    url = out["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert out["image_url"]["detail"] == "high"


def test_image_block_text_fallback_includes_caption_and_path(png_path: Path):
    block = ImageBlock(source=str(png_path), caption="level 3 boss")
    text = block.to_text_fallback()
    assert "level 3 boss" in text
    assert str(png_path) in text


def test_image_block_data_url_does_not_need_disk_read():
    data_url = "data:image/png;base64," + base64.b64encode(b"fake-png").decode()
    block = ImageBlock(source=data_url)
    assert block.load_bytes() == b"fake-png"
    text = block.to_text_fallback()
    assert "(inline data URL)" in text
    # Path component should NOT be appended for inline data URLs.
    assert data_url not in text


def test_to_anthropic_messages_mixes_text_and_image(png_path: Path):
    blocks = [TextBlock("context"), ImageBlock(source=str(png_path))]
    out = to_anthropic_messages(blocks)
    assert out[0] == {"type": "text", "text": "context"}
    assert out[1]["type"] == "image"
    assert out[1]["source"]["type"] == "base64"


def test_to_openai_messages_handles_string_inputs(png_path: Path):
    blocks = ["raw string", TextBlock("block"), ImageBlock(source=str(png_path))]
    out = to_openai_messages(blocks)
    assert out[0] == {"type": "text", "text": "raw string"}
    assert out[1] == {"type": "text", "text": "block"}
    assert out[2]["type"] == "image_url"


def test_to_text_fallback_includes_captions(png_path: Path):
    blocks = [
        TextBlock("see image"),
        ImageBlock(source=str(png_path), caption="preview"),
    ]
    out = to_text_fallback(blocks)
    assert "see image" in out
    assert "preview" in out


def test_blocks_from_strings_drops_empty():
    out = blocks_from_strings(["a", "", None, "b"])
    assert [b.text for b in out] == ["a", "b"]


def test_image_block_rejects_empty_source():
    with pytest.raises(ValueError):
        ImageBlock(source="")


def test_image_block_invalid_detail_falls_back_to_auto(png_path: Path):
    block = ImageBlock(source=str(png_path), detail="bogus")
    assert block.detail == "auto"


def test_image_block_remote_url_raises_on_load():
    block = ImageBlock(source="https://example.com/img.png")
    with pytest.raises(ValueError):
        block.load_bytes()


def test_image_block_missing_file_raises(png_path: Path):
    block = ImageBlock(source=str(png_path.with_name("missing.png")))
    with pytest.raises(FileNotFoundError):
        block.load_bytes()


def test_image_block_exceeds_size_limit_uses_disk_check(png_path: Path):
    block = ImageBlock(source=str(png_path))
    # 67-byte fixture is well under the 4 MB soft limit.
    assert block.exceeds_size_limit(limit=10) is True
    assert block.exceeds_size_limit(limit=10_000) is False
