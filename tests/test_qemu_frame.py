#!/usr/bin/env python3
"""Tests for the QEMU CGA snapshot converter."""

from __future__ import annotations

import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import d2e_qemu_frame


def make_dump(mode: int, mode_control: int, color_control: int,
              first_byte: int) -> str:
    vram = bytearray(0x4000)
    vram[0] = first_byte
    lines = [
        f"D2E_VRAM_BEGIN,mode={mode},mode_control={mode_control:02x},"
        f"color_control={color_control:02x},size={len(vram)}"
    ]
    for offset in range(0, len(vram), 64):
        lines.append(f"D2E_VRAM,{offset:04x},{vram[offset:offset + 64].hex()}")
    lines.append("D2E_VRAM_END")
    return "\n".join(lines)


mode4 = d2e_qemu_frame.parse_dump(make_dump(4, 0x0A, 0, 0x1B))
pixels = d2e_qemu_frame.render_320x240(mode4)
assert len(pixels) == 320 * 240 * 3
assert pixels[:3] == bytes((0, 0, 0))
row = 20 * 320 * 3
assert pixels[row : row + 3] == bytes((0, 0, 0))
assert pixels[row + 3 : row + 6] == bytes((0, 196, 0))
assert pixels[row + 6 : row + 9] == bytes((196, 0, 0))

mode6 = d2e_qemu_frame.parse_dump(make_dump(6, 0x1A, 0x0E, 0x90))
pixels = d2e_qemu_frame.render_320x240(mode6)
assert pixels[row : row + 3] == bytes((243, 243, 78))
assert pixels[row + 3 : row + 6] == bytes((243, 243, 78))
assert pixels[row + 6 : row + 9] == bytes((0, 0, 0))

with tempfile.TemporaryDirectory() as temporary:
    output = pathlib.Path(temporary) / "frame.bmp"
    d2e_qemu_frame.write_bmp(output, pixels)
    encoded = output.read_bytes()
    assert encoded[:2] == b"BM"
    assert int.from_bytes(encoded[2:6], "little") == len(encoded)
    assert int.from_bytes(encoded[10:14], "little") == 54
    assert len(encoded) == 54 + 320 * 240 * 3
print("QEMU CGA frame converter tests passed")
