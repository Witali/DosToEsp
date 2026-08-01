#!/usr/bin/env python3
"""Regression tests for the deterministic static inventory."""

from __future__ import annotations

import hashlib
import json
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import d2e_analyze


def main() -> int:
    fixture = ROOT / "tests" / "fixtures" / "native_smoke.hex"
    data = d2e_analyze.read_hex(fixture)
    image = d2e_analyze.identify(data, "com", None, None)
    report = d2e_analyze.analyze(image, fixture.name)

    assert report["file"]["format"] == "com"
    assert report["file"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert report["summary"] == {
        "instruction_count": 11,
        "block_count": 5,
        "edge_count": 6,
        "unresolved_flow_count": 0,
        "issue_count": 0,
    }
    assert report["instruction_frequency"]["jne"] == 2
    assert report["interrupts"] == [
        {"address": 0x114, "number": 0x21},
        {"address": 0x119, "number": 0x21},
    ]
    assert report["ports"] == []
    assert report["unresolved_flow"] == []
    first = json.dumps(report, sort_keys=True)
    second = json.dumps(d2e_analyze.analyze(image, fixture.name), sort_keys=True)
    assert first == second

    io_image = d2e_analyze.identify(
        bytes.fromhex("b800b8e460e661f4"), "com", None, None
    )
    io_report = d2e_analyze.analyze(io_image, "io.com")
    assert io_report["ports"] == [
        {"address": 0x103, "operation": "in", "port": 0x60},
        {"address": 0x105, "operation": "out", "port": 0x61},
    ]
    assert io_report["cga_candidates"] == [
        {"address": 0x100, "kind": "segment_constant", "value": 0xB800}
    ]

    indirect = d2e_analyze.analyze(
        d2e_analyze.identify(bytes.fromhex("ffe0"), "com", None, None),
        "indirect.com",
    )
    assert indirect["unresolved_flow"] == [
        {"address": 0x100, "kind": "jump", "operand": "ax"}
    ]

    high_target_data = bytearray(0x8F01)
    high_target_data[:3] = bytes.fromhex("e9 fd 8e")
    high_target_data[-1] = 0xF4
    high_target = d2e_analyze.analyze(
        d2e_analyze.identify(bytes(high_target_data), "com", None, None),
        "high-target.com",
    )
    assert high_target["summary"] == {
        "instruction_count": 2,
        "block_count": 2,
        "edge_count": 1,
        "unresolved_flow_count": 0,
        "issue_count": 0,
    }
    assert high_target["blocks"][0]["successors"] == [
        {"kind": "jump", "source": 0x100, "target": 0x9000}
    ]

    jump_table_data = d2e_analyze.read_hex(
        ROOT / "tests" / "fixtures" / "native_indirect.hex"
    )
    jump_table = d2e_analyze.analyze(
        d2e_analyze.identify(jump_table_data, "com", None, None),
        "native_indirect.com",
    )
    assert jump_table["unresolved_flow"] == []
    assert jump_table["recovered_indirect_flow"] == [
        {
            "address": 0x10C,
            "operand": "word ptr cs:[bx + 0x111]",
            "targets": [0x117, 0x11B, 0x11F],
        }
    ]
    assert any(
        edge == {"source": 0x10C, "target": 0x11B, "kind": "jump_table"}
        for block in jump_table["blocks"]
        for edge in block["successors"]
    )

    irq_image = bytearray(bytes.fromhex(
        "b800008ec0bb2001fa26891e2400268c0e2600f4"
    ))
    irq_image.extend(b"\x00" * (0x20 - len(irq_image)))
    irq_image.extend(bytes.fromhex("e460cf"))
    irq_report = d2e_analyze.analyze(
        d2e_analyze.identify(bytes(irq_image), "com", None, None),
        "irq.com",
    )
    assert irq_report["recovered_interrupt_vectors"] == [
        {"address": 0x109, "vector": 9, "targets": [0x120]}
    ]
    assert irq_report["ports"] == [
        {"address": 0x120, "operation": "in", "port": 0x60}
    ]
    decoded_irq = __import__("d2e_translate").discover(
        bytes(irq_image), 0x100, 0x100
    )
    assert 0x120 in decoded_irq
    assert 0x120 in __import__("d2e_translate").make_blocks(decoded_irq, 0x100)

    mz = bytearray(33)
    mz[:2] = b"MZ"
    struct.pack_into("<H", mz, 0x02, len(mz))
    struct.pack_into("<H", mz, 0x04, 1)
    struct.pack_into("<H", mz, 0x06, 1)
    struct.pack_into("<H", mz, 0x08, 2)
    struct.pack_into("<H", mz, 0x18, 0x1C)
    struct.pack_into("<HH", mz, 0x1C, 0, 0)
    mz[32] = 0xF4
    mz_image = d2e_analyze.identify(bytes(mz), "auto", None, None)
    mz_report = d2e_analyze.analyze(mz_image, "tiny.exe")
    assert mz_report["file"]["format"] == "mz"
    assert mz_report["file"]["module_size"] == 1
    assert mz_report["relocations"] == [{"offset": 0, "segment": 0}]
    assert mz_report["instruction_frequency"] == {"hlt": 1}
    packed = __import__("d2e_pack_mz").emit(mz_image, "tiny", 0x1000)
    assert ".format = D2E_NATIVE_IMAGE_MZ" in packed
    assert "{UINT16_C(0x0000), UINT16_C(0x0000)}" in packed
    print("static inventory tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
