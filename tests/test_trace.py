#!/usr/bin/env python3
"""Regression tests for the reference trace contract."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import d2e_analyze
import d2e_trace


def main() -> int:
    data = d2e_analyze.read_hex(ROOT / "tests" / "fixtures" / "native_smoke.hex")
    inventory = d2e_analyze.analyze(
        d2e_analyze.identify(data, "com", None, None), "native_smoke.hex"
    )
    digest = inventory["file"]["sha256"]
    events = [
        {"event": "meta", "schema": d2e_trace.TRACE_SCHEMA, "sha256": digest},
        {"event": "exec", "cs": 0x1000, "ip": 0x100},
        {"event": "exec", "cs": 0x1000, "ip": 0x106},
        {"event": "exec", "cs": 0x1000, "ip": 0x106},
        {"event": "exec", "cs": 0x1000, "ip": 0x222},
        {"event": "interrupt", "number": 0x21, "cs": 0x1000, "ip": 0x116},
        {"event": "port_out", "port": 0x3D9, "width": 8, "value": 0x30},
        {"event": "mem_write", "address": 0xB8000, "width": 16, "value": 0x1234},
    ]
    for line_number, event in enumerate(events, 1):
        d2e_trace.validate_event(event, line_number)
    report = d2e_trace.summarize(events, inventory)
    assert report["summary"] == {
        "event_count": 7,
        "executed_instruction_count": 4,
        "unique_code_location_count": 3,
        "location_not_in_static_inventory_count": 1,
    }
    assert report["locations_not_in_static_inventory"] == [
        {"cs": 0x1000, "ip": 0x222, "count": 1}
    ]
    assert report["interrupts"] == [{"number": 0x21, "count": 1}]
    assert report["ports"][0]["port"] == 0x3D9
    assert report["cga"] == {
        "write_event_count": 1,
        "written_byte_count": 2,
        "unique_address_count": 2,
        "first_address": 0xB8000,
        "last_address": 0xB8001,
    }
    bad_events = [dict(events[0]), *events[1:]]
    bad_events[0]["sha256"] = "0" * 64
    try:
        d2e_trace.summarize(bad_events, inventory)
    except ValueError:
        pass
    else:
        raise AssertionError("binary fingerprint mismatch was accepted")
    print("reference trace tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
