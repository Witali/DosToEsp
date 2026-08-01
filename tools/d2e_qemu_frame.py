#!/usr/bin/env python3
"""Convert a DosToEsp QEMU CGA VRAM dump to a 320x240 BMP image."""

from __future__ import annotations

import argparse
import pathlib
import re
import struct
from dataclasses import dataclass


CGA_RGB888 = (
    0x000000, 0x0000C4, 0x00C400, 0x00C4C4,
    0xC40000, 0xC400C4, 0xC47E00, 0xC4C4C4,
    0x4E4E4E, 0x4E4EDC, 0x4EDC4E, 0x4EF3F3,
    0xDC4E4E, 0xF34EF3, 0xF3F34E, 0xFFFFFF,
)
CGA_GRAPHICS_PALETTE = (
    ((0, 2, 4, 6), (0, 10, 12, 14)),
    ((0, 3, 5, 7), (0, 11, 13, 15)),
    ((0, 3, 4, 7), (0, 11, 12, 15)),
)


@dataclass(frozen=True)
class CgaDump:
    mode: int
    mode_control: int
    color_control: int
    vram: bytes


def parse_dump(text: str) -> CgaDump:
    header = re.search(
        r"D2E_VRAM_BEGIN,mode=(\d+),mode_control=([0-9a-fA-F]{2}),"
        r"color_control=([0-9a-fA-F]{2}),size=(\d+)",
        text,
    )
    if header is None or "D2E_VRAM_END" not in text:
        raise ValueError("complete D2E VRAM dump was not found")
    size = int(header.group(4))
    vram = bytearray(size)
    covered = bytearray(size)
    for match in re.finditer(r"D2E_VRAM,([0-9a-fA-F]{4,8}),([0-9a-fA-F]+)", text):
        offset = int(match.group(1), 16)
        chunk = bytes.fromhex(match.group(2))
        if offset + len(chunk) > size:
            raise ValueError("VRAM chunk exceeds declared size")
        vram[offset : offset + len(chunk)] = chunk
        covered[offset : offset + len(chunk)] = b"\x01" * len(chunk)
    if not all(covered):
        raise ValueError("VRAM dump has missing chunks")
    return CgaDump(
        mode=int(header.group(1)),
        mode_control=int(header.group(2), 16),
        color_control=int(header.group(3), 16),
        vram=bytes(vram),
    )


def _rgb(color: int) -> bytes:
    value = CGA_RGB888[color]
    return bytes((value >> 16, (value >> 8) & 0xFF, value & 0xFF))


def render_320x240(dump: CgaDump) -> bytes:
    if dump.mode not in (4, 5, 6):
        raise ValueError(f"unsupported CGA graphics mode: {dump.mode}")
    output = bytearray(320 * 240 * 3)
    for y in range(200):
        source = (y >> 1) * 80 + (0x2000 if y & 1 else 0)
        destination = (y + 20) * 320 * 3
        if dump.mode == 6 or dump.mode_control & 0x10:
            foreground = dump.color_control & 0x0F or 15
            for x in range(320):
                input_x = x * 2
                pair = (dump.vram[source + (input_x >> 3)] >>
                        (6 - (input_x & 6))) & 3
                output[destination + x * 3 : destination + x * 3 + 3] = (
                    _rgb(foreground if pair else 0)
                )
            continue
        intensity = (dump.color_control >> 4) & 1
        group = (dump.color_control >> 5) & 1
        if dump.mode == 5 or dump.mode_control & 0x04:
            group = 2
        palette = CGA_GRAPHICS_PALETTE[group][intensity]
        background = dump.color_control & 0x0F
        for byte_index in range(80):
            packed = dump.vram[source + byte_index]
            for pixel in range(4):
                selector = (packed >> (6 - pixel * 2)) & 3
                color = background if selector == 0 else palette[selector]
                x = byte_index * 4 + pixel
                output[destination + x * 3 : destination + x * 3 + 3] = _rgb(color)
    return bytes(output)


def write_bmp(path: pathlib.Path, pixels: bytes) -> None:
    width = 320
    height = 240
    row_size = width * 3
    if len(pixels) != row_size * height:
        raise ValueError("RGB888 frame must be exactly 320x240")
    bitmap = bytearray(len(pixels))
    for output_y, input_y in enumerate(range(height - 1, -1, -1)):
        input_row = pixels[input_y * row_size : (input_y + 1) * row_size]
        output_offset = output_y * row_size
        for x in range(width):
            red, green, blue = input_row[x * 3 : x * 3 + 3]
            bitmap[output_offset + x * 3 : output_offset + x * 3 + 3] = (
                blue, green, red
            )
    pixel_offset = 14 + 40
    header = struct.pack(
        "<2sIHHI IiiHHIIiiII",
        b"BM", pixel_offset + len(bitmap), 0, 0, pixel_offset,
        40, width, height, 1, 24, 0, len(bitmap), 2835, 2835, 0, 0,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bitmap)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    dump = parse_dump(args.log.read_text(encoding="utf-8", errors="replace"))
    pixels = render_320x240(dump)
    write_bmp(args.output, pixels)
    print(
        f"rendered CGA mode {dump.mode}: {args.output} "
        f"({len(dump.vram)} VRAM bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
