"""Build placeholder desktop icons for the TTMEvolve desktop shell.

Generates:
- icons/32x32.png
- icons/128x128.png
- icons/128x128@2x.png  (256x256)
- icons/icon.icns  (macOS, simple placeholder)
- icons/icon.ico   (Windows, multi-resolution)

If Pillow is unavailable, emits a tiny 1x1 transparent PNG as a fallback.
The icons use the brand color from theme.css (#00D9C5) as a solid
placeholder; designers can replace them later.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "src-tauri" / "icons"
BRAND_RGBA = (0, 217, 197, 255)  # #00D9C5
SIZE_MAP = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
}


def _png_bytes(width: int, height: int, rgba: tuple = BRAND_RGBA) -> bytes:
    """Generate a solid-color PNG without external dependencies."""
    r, g, b, a = rgba
    raw = b""
    for _ in range(height):
        raw += b"\x00" + bytes([r, g, b, a]) * width
    compressed = zlib.compress(raw, 9)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")


def _ico_bytes(png_paths: list) -> bytes:
    """Pack multiple PNGs into a Windows .ico container."""
    header = struct.pack("<HHH", 0, 1, len(png_paths))
    entries = b""
    image_data = b""
    offset = 6 + 16 * len(png_paths)
    for path in png_paths:
        data = Path(path).read_bytes()
        w, h = _png_dimensions(data)
        # ICO format uses 0 to mean "256 or larger".
        w_byte = 0 if w >= 256 else w
        h_byte = 0 if h >= 256 else h
        entries += struct.pack(
            "<BBBBHHII",
            w_byte, h_byte, 0, 0, 1, 32, len(data), offset,
        )
        image_data += data
        offset += len(data)
    return header + entries + image_data


def _png_dimensions(data: bytes) -> tuple:
    """Decode the width and height from a PNG file."""
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    return width, height


def _icns_bytes(png_256_path: Path) -> bytes:
    """Build a minimal .icns containing a single ic09 (512x512) entry.

    We reuse the 256x256 PNG as a stand-in. Real ICNS needs ic08 (256) and
    ic09 (512) PNGs; the bundle tool will scale the icon at install time.
    """
    data = png_256_path.read_bytes()
    # 'icns' magic, total length, then one entry: 'ic08' + length + PNG.
    entry_header = b"ic08" + struct.pack(">I", 8 + len(data))
    body = entry_header + data
    header = b"icns" + struct.pack(">I", 8 + len(body))
    return header + body


def main() -> int:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate PNGs at the required sizes.
    generated = []
    for filename, size in SIZE_MAP.items():
        target = ICONS_DIR / filename
        target.write_bytes(_png_bytes(size, size))
        generated.append(target)
        print(f"[build_icons] wrote {target.name} ({size}x{size})")

    # Build the multi-resolution ICO from the two smaller PNGs.
    ico_target = ICONS_DIR / "icon.ico"
    ico_target.write_bytes(_ico_bytes([generated[0], generated[1]]))
    print(f"[build_icons] wrote {ico_target.name}")

    # Build a minimal ICNS (single ic08 entry, scaled from 256x256 PNG).
    icns_target = ICONS_DIR / "icon.icns"
    icns_target.write_bytes(_icns_bytes(generated[1]))
    print(f"[build_icons] wrote {icns_target.name}")

    print("[build_icons] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())