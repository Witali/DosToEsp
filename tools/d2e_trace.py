#!/usr/bin/env python3
"""Validate and summarize a DosToEsp reference-runner JSONL trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections import Counter
from typing import Any, Iterable

TRACE_SCHEMA = "d2e-reference-trace-v1"
EVENTS = {"meta", "exec", "interrupt", "port_in", "port_out", "mem_write"}


def require_uint(event: dict[str, Any], name: str, maximum: int) -> int:
    value = event.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise ValueError(f"{event.get('event', 'event')}.{name} must be 0..{maximum}")
    return value


def validate_event(event: Any, line_number: int) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError(f"line {line_number}: event must be a JSON object")
    event_type = event.get("event")
    if event_type not in EVENTS:
        raise ValueError(f"line {line_number}: unsupported event type {event_type!r}")
    if event_type == "meta":
        if event.get("schema") != TRACE_SCHEMA:
            raise ValueError(f"line {line_number}: unsupported trace schema")
        digest = event.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"line {line_number}: meta.sha256 must be hexadecimal SHA-256")
        try:
            bytes.fromhex(digest)
        except ValueError as error:
            raise ValueError(f"line {line_number}: invalid meta.sha256") from error
    elif event_type == "exec":
        require_uint(event, "cs", 0xFFFF)
        require_uint(event, "ip", 0xFFFF)
    elif event_type == "interrupt":
        require_uint(event, "number", 0xFF)
        require_uint(event, "cs", 0xFFFF)
        require_uint(event, "ip", 0xFFFF)
    elif event_type in ("port_in", "port_out"):
        require_uint(event, "port", 0xFFFF)
        if event.get("width") not in (8, 16):
            raise ValueError(f"line {line_number}: port width must be 8 or 16")
        require_uint(event, "value", 0xFFFF)
    elif event_type == "mem_write":
        require_uint(event, "address", 0xFFFFF)
        if event.get("width") not in (8, 16, 32):
            raise ValueError(f"line {line_number}: memory width must be 8, 16 or 32")
        require_uint(event, "value", 0xFFFFFFFF)
    return event


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {line_number}: invalid JSON: {error.msg}") from error
        events.append(validate_event(event, line_number))
    if not events or events[0]["event"] != "meta":
        raise ValueError("the first trace event must be meta")
    if any(event["event"] == "meta" for event in events[1:]):
        raise ValueError("the trace must contain exactly one meta event")
    return events


def trace_digest(events: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for event in events:
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
        digest.update(encoded.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def summarize(
    events: list[dict[str, Any]], static_report: dict[str, Any]
) -> dict[str, Any]:
    expected_hash = static_report.get("file", {}).get("sha256")
    actual_hash = events[0]["sha256"].lower()
    if expected_hash != actual_hash:
        raise ValueError(
            f"trace binary SHA-256 {actual_hash} does not match inventory {expected_hash}"
        )

    exec_counts: Counter[tuple[int, int]] = Counter()
    interrupts: Counter[int] = Counter()
    ports: Counter[tuple[str, int, int]] = Counter()
    port_values: dict[tuple[str, int, int], set[int]] = {}
    cga_writes = 0
    cga_bytes = 0
    cga_addresses: set[int] = set()
    for event in events[1:]:
        event_type = event["event"]
        if event_type == "exec":
            exec_counts[(event["cs"], event["ip"])] += 1
        elif event_type == "interrupt":
            interrupts[event["number"]] += 1
        elif event_type in ("port_in", "port_out"):
            key = (event_type.removeprefix("port_"), event["port"], event["width"])
            ports[key] += 1
            port_values.setdefault(key, set()).add(event["value"])
        elif event_type == "mem_write":
            width_bytes = event["width"] // 8
            for address in range(event["address"], event["address"] + width_bytes):
                if 0xB8000 <= address <= 0xBBFFF:
                    cga_addresses.add(address)
                    cga_bytes += 1
            if any(
                0xB8000 <= address <= 0xBBFFF
                for address in range(event["address"], event["address"] + width_bytes)
            ):
                cga_writes += 1

    static_ips = {item["address"] for item in static_report.get("instructions", [])}
    locations = [
        {"cs": cs, "ip": ip, "count": count}
        for (cs, ip), count in sorted(exec_counts.items())
    ]
    return {
        "schema": "d2e-reference-trace-summary-v1",
        "binary_sha256": actual_hash,
        "trace_sha256": trace_digest(events),
        "summary": {
            "event_count": len(events) - 1,
            "executed_instruction_count": sum(exec_counts.values()),
            "unique_code_location_count": len(exec_counts),
            "location_not_in_static_inventory_count": sum(
                1 for _, ip in exec_counts if ip not in static_ips
            ),
        },
        "code_locations": locations,
        "locations_not_in_static_inventory": [
            item for item in locations if item["ip"] not in static_ips
        ],
        "interrupts": [
            {"number": number, "count": count}
            for number, count in sorted(interrupts.items())
        ],
        "ports": [
            {
                "direction": key[0],
                "port": key[1],
                "width": key[2],
                "count": count,
                "values": sorted(port_values[key]),
            }
            for key, count in sorted(ports.items())
        ],
        "cga": {
            "write_event_count": cga_writes,
            "written_byte_count": cga_bytes,
            "unique_address_count": len(cga_addresses),
            "first_address": min(cga_addresses) if cga_addresses else None,
            "last_address": max(cga_addresses) if cga_addresses else None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=pathlib.Path)
    parser.add_argument("--inventory", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        events = read_jsonl(args.trace)
        static_report = json.loads(args.inventory.read_text(encoding="utf-8"))
        report = summarize(events, static_report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"trace analysis failed: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"summarized {report['summary']['event_count']} trace events: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
