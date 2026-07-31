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

    mz = bytearray(33)
    mz[:2] = b"MZ"
    struct.pack_into("<H", mz, 0x02, len(mz))
    struct.pack_into("<H", mz, 0x04, 1)
    struct.pack_into("<H", mz, 0x08, 2)
    mz[32] = 0xF4
    mz_image = d2e_analyze.identify(bytes(mz), "auto", None, None)
    mz_report = d2e_analyze.analyze(mz_image, "tiny.exe")
    assert mz_report["file"]["format"] == "mz"
    assert mz_report["file"]["module_size"] == 1
    assert mz_report["instruction_frequency"] == {"hlt": 1}
    print("static inventory tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
