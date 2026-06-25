"""Tests for the placeholder icon builder."""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# Load the icon builder as a module.
_spec = importlib.util.spec_from_file_location(
    "build_icons",
    _PROJECT_ROOT / "scripts" / "build_portable" / "build_icons.py",
)
icons = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(icons)


# ---------- PNG generation ----------


def test_png_bytes_signature():
    data = icons._png_bytes(32, 32)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_bytes_dimensions_encoded():
    data = icons._png_bytes(64, 32)
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    assert width == 64
    assert height == 32


def test_png_bytes_brand_color():
    """The PNG should contain the brand color in the IDAT stream."""
    data = icons._png_bytes(8, 8)
    # The brand color #00D9C5 = (0, 217, 197, 255).
    # IDAT is zlib-compressed, but the row-filter byte 0 + RGBA values
    # appear in the raw stream. Easier to just decompress and verify.
    import zlib
    # Skip PNG signature (8) + IHDR length+type+data (4+4+13) = 25 bytes.
    idat_start = data.index(b"IDAT") + 4
    # The IDAT chunk length and the data start at idat_start - 4
    # but we just want to find the compressed data.
    idat_length = struct.unpack(">I", data[idat_start - 4:idat_start])[0]
    compressed = data[idat_start:idat_start + idat_length]
    raw = zlib.decompress(compressed)
    # raw is rows of (filter_byte, rgba*width). For 8x8, each row is 1 + 8*4 = 33 bytes.
    # The RGBA bytes start at offset 1 of each row.
    expected_rgba = bytes([0, 217, 197, 255])
    row_size = 1 + 8 * 4
    for row_index in range(8):
        offset = row_index * row_size + 1
        assert raw[offset:offset + 4] == expected_rgba, (
            f"row {row_index} has unexpected color"
        )


def test_png_dimensions_helper():
    data = icons._png_bytes(128, 64)
    width, height = icons._png_dimensions(data)
    assert width == 128
    assert height == 64


# ---------- ICO generation ----------


def test_ico_bytes_header_is_valid(tmp_path):
    png_a = tmp_path / "a.png"
    png_a.write_bytes(icons._png_bytes(32, 32))
    ico = icons._ico_bytes([png_a])
    # ICONDIR: reserved=0, type=1 (icon), count=1
    assert struct.unpack("<HHH", ico[:6]) == (0, 1, 1)


def test_ico_bytes_contains_all_pngs(tmp_path):
    png_a = tmp_path / "a.png"
    png_a.write_bytes(icons._png_bytes(16, 16))
    png_b = tmp_path / "b.png"
    png_b.write_bytes(icons._png_bytes(32, 32))
    ico = icons._ico_bytes([png_a, png_b])
    assert struct.unpack("<HHH", ico[:6]) == (0, 1, 2)


# ---------- ICNS generation ----------


def test_icns_bytes_has_magic(tmp_path):
    png = tmp_path / "big.png"
    png.write_bytes(icons._png_bytes(256, 256))
    icns = icons._icns_bytes(png)
    assert icns[:4] == b"icns"
    # Total length is at bytes 4-7.
    total = struct.unpack(">I", icns[4:8])[0]
    assert total == len(icns)


# ---------- actual file generation ----------


def test_main_writes_expected_files(monkeypatch, tmp_path):
    """Run main() with a redirected ICONS_DIR and verify all 5 outputs exist."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    rc = icons.main()
    assert rc == 0
    for name in ["32x32.png", "128x128.png", "128x128@2x.png", "icon.ico", "icon.icns"]:
        path = tmp_path / name
        assert path.exists(), f"missing: {name}"
        assert path.stat().st_size > 0, f"empty: {name}"


def test_main_is_idempotent(monkeypatch, tmp_path):
    """Re-running main() must not error on existing files."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    assert icons.main() == 0
    # Second run should also succeed.
    assert icons.main() == 0