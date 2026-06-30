"""Multimodal content blocks for LLM calls.

The LLM interface used to be pure-text in / pure-text out. This module
introduces ``ContentBlock`` (text or image) so the LLM can see images
returned by tools (e.g. ``preview.screenshot``) without breaking the
existing text-only call sites.

Design rules:

- Backward compatible: every helper accepts ``List[ContentBlock]`` but a
  text-only LLM implementation only ever receives ``[TextBlock(...)]``.
- Lazy image load: image bytes are read on serialization, not on
  construction, so building a long trajectory does not touch the disk.
- Per-provider translation: Anthropic, OpenAI, and a text fallback are
  the only three shapes we need today. MiniMax and any other
  OpenAI-compatible provider should reuse the OpenAI translator.
- Fail open: if an image cannot be loaded, the text fallback is emitted
  with a note. Multimodal is supposed to enhance, not block.
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union


CONTENT_BLOCK_VERSION = "content-block.v1"


# A reasonable upper bound on a single image before we warn. 4 MB is
# roughly a 1500x1500 PNG; the limit is advisory, not enforced.
SOFT_IMAGE_BYTES_LIMIT = 4 * 1024 * 1024


@dataclass
class TextBlock:
    """Plain text content. The only block type the old API could send."""

    text: str

    def to_anthropic(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}

    def to_openai(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}

    def to_text_fallback(self) -> str:
        return self.text

    def is_text(self) -> bool:
        return True


@dataclass
class ImageBlock:
    """One image. ``source`` can be a local path, a ``data:`` URL, or a
    plain ``http(s)://`` URL. Local paths and ``data:`` URLs are loaded
    eagerly during serialization; remote URLs must be pre-fetched by the
    caller (this keeps the LLM client free of network dependencies
    besides its own API)."""

    source: str
    media_type: Optional[str] = None
    caption: str = ""
    # OpenAI-only knob: low | high | auto. Ignored by Anthropic.
    detail: str = "auto"

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("ImageBlock.source must be a non-empty path or data URL")
        if self.media_type is None and not self.source.startswith("data:"):
            guessed, _ = mimetypes.guess_type(self.source.split("?")[0])
            self.media_type = guessed or "image/png"
        if self.detail not in {"low", "high", "auto"}:
            self.detail = "auto"

    def is_remote_url(self) -> bool:
        return self.source.startswith(("http://", "https://"))

    def is_data_url(self) -> bool:
        return self.source.startswith("data:")

    def load_bytes(self) -> bytes:
        """Load the image bytes. Raises on failure; callers should catch
        and fall back to text representation."""
        if self.is_data_url():
            try:
                _, payload = self.source.split(",", 1)
                return base64.b64decode(payload)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"could not decode data URL: {exc}") from exc
        if self.is_remote_url():
            raise ValueError(
                "remote URL images must be pre-fetched by the caller; "
                "this keeps the LLM client free of extra network calls"
            )
        path = Path(self.source)
        if not path.is_file():
            raise FileNotFoundError(f"image not found: {self.source}")
        return path.read_bytes()

    def to_anthropic(self) -> Dict[str, Any]:
        """Anthropic Messages format. ``source.type=base64`` is the
        well-supported path; ``source.type=url`` exists but we do not
        load remote URLs in this helper on purpose."""
        data = base64.b64encode(self.load_bytes()).decode("ascii")
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": self.media_type or "image/png",
                "data": data,
            },
        }

    def to_openai(self) -> Dict[str, Any]:
        """OpenAI Chat Completions image_url format. data: URL keeps the
        request self-contained so we do not need to host the image."""
        data = base64.b64encode(self.load_bytes()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{self.media_type or 'image/png'};base64,{data}",
                "detail": self.detail,
            },
        }

    def to_text_fallback(self) -> str:
        """Plain-text placeholder so a text-only LLM still gets the
        metadata. Includes caption + path so the LLM can correlate the
        image with whatever filesystem evidence it has."""
        parts = ["[image"]
        if self.caption:
            parts.append(f": {self.caption}")
        if self.is_data_url():
            parts.append(" (inline data URL)")
        elif not self.is_remote_url():
            parts.append(f" at {self.source}")
        parts.append("]")
        return "".join(parts)

    def is_text(self) -> bool:
        return False

    def exceeds_size_limit(self, limit: int = SOFT_IMAGE_BYTES_LIMIT) -> bool:
        try:
            return len(self.load_bytes()) > limit
        except Exception:
            return False


ContentBlock = Union[TextBlock, ImageBlock]


def _flatten(blocks: Sequence[Any]) -> List[ContentBlock]:
    """Drop non-block values; keep ordering. Str inputs are wrapped as
    TextBlock for ergonomic call sites like ``[TextBlock(x), "extra"]``."""
    out: List[ContentBlock] = []
    for item in blocks:
        if isinstance(item, (TextBlock, ImageBlock)):
            out.append(item)
        elif isinstance(item, str):
            out.append(TextBlock(item))
        # silently drop None / unknown types
    return out


def to_anthropic_messages(
    blocks: Sequence[ContentBlock],
) -> List[Dict[str, Any]]:
    """Serialize content blocks to Anthropic Messages API content arrays."""
    return [b.to_anthropic() for b in _flatten(blocks)]


def to_openai_messages(
    blocks: Sequence[ContentBlock],
) -> List[Dict[str, Any]]:
    """Serialize content blocks to OpenAI Chat Completions content arrays.
    MiniMax's ChatCompletion v2 is OpenAI-compatible, so it can reuse this
    helper or wrap it with a different image block implementation."""
    return [b.to_openai() for b in _flatten(blocks)]


def to_text_fallback(blocks: Sequence[ContentBlock]) -> str:
    """Render every block as a single text string. Used by LLM
    implementations that have not yet opted into multimodal support."""
    return "\n".join(b.to_text_fallback() for b in _flatten(blocks))


def blocks_from_strings(lines: Sequence[str]) -> List[TextBlock]:
    """Convenience for tests and for the legacy text-only call sites
    that want to build a uniform ``List[ContentBlock]`` from plain text."""
    out: List[TextBlock] = []
    for line in lines:
        if line is None:
            continue
        text = str(line).strip()
        if text:
            out.append(TextBlock(text))
    return out


__all__ = [
    "CONTENT_BLOCK_VERSION",
    "SOFT_IMAGE_BYTES_LIMIT",
    "TextBlock",
    "ImageBlock",
    "ContentBlock",
    "to_anthropic_messages",
    "to_openai_messages",
    "to_text_fallback",
    "blocks_from_strings",
]
