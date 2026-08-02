#!/usr/bin/env python3
"""Regression tests for translator coverage reporting."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import d2e_analyze
import d2e_coverage


def main() -> int:
    data = d2e_analyze.read_hex(ROOT / "tests" / "fixtures" / "native_smoke.hex")
    inventory = d2e_analyze.analyze(
        d2e_analyze.identify(data, "com", None, None), "native_smoke.hex"
    )
    report = d2e_coverage.coverage(inventory)
    assert report["summary"]["instruction_count"] == 11
    assert report["summary"]["supported_instruction_count"] == 11
    assert report["summary"]["supported_percent"] == 100.0

    memory_instruction = {
        "address": 0x100,
        "size": 2,
        "mnemonic": "mov",
        "op_str": "ax, word ptr [bx]",
        "operands": [
            {"type": "reg", "reg": "ax", "size": 2},
            {
                "type": "mem",
                "segment": None,
                "base": "bx",
                "index": None,
                "scale": 1,
                "displacement": 0,
                "write": False,
                "size": 2,
            },
        ],
    }
    assert d2e_coverage.classify(memory_instruction) == (True, "supported")
    memory_instruction["mnemonic"] = "div"
    memory_instruction["op_str"] = "word ptr [bx]"
    memory_instruction["operands"] = [memory_instruction["operands"][1]]
    assert d2e_coverage.classify(memory_instruction) == (True, "supported")
    call_instruction = {
        "address": 0x102,
        "size": 3,
        "mnemonic": "call",
        "op_str": "0x200",
        "operands": [{"type": "imm", "value": 0x200, "size": 2}],
    }
    assert d2e_coverage.classify(call_instruction) == (True, "supported")
    call_instruction["op_str"] = "ax"
    call_instruction["operands"] = [{"type": "reg", "reg": "ax", "size": 2}]
    assert d2e_coverage.classify(call_instruction) == (
        False,
        "indirect_control_target",
    )
    print("translator coverage tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
