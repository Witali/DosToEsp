#!/usr/bin/env python3
"""Create a deterministic static inventory for a 16-bit DOS image."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import struct
import sys
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = PROJECT_ROOT / "local_tools" / "python_packages"
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(LOCAL_PACKAGES))

try:
    from capstone import CS_AC_WRITE, CS_ARCH_X86, CS_MODE_16, Cs
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG
except ImportError as error:
    raise SystemExit(
        "Capstone is missing. Run scripts/setup-analysis-tools.ps1 first."
    ) from error

import d2e_translate


@dataclass(frozen=True)
class Image:
    file_bytes: bytes
    module_bytes: bytes
    format: str
    base: int
    entry: int
    metadata: dict[str, int]
    relocations: tuple[tuple[int, int], ...]


def read_hex(path: pathlib.Path) -> bytes:
    chunks = [line.split("#", 1)[0] for line in path.read_text().splitlines()]
    return bytes.fromhex(re.sub(r"\s+", "", "".join(chunks)))


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def identify(data: bytes, requested: str, base: int | None, entry: int | None) -> Image:
    image_format = requested
    if image_format == "auto":
        image_format = "mz" if data[:2] in (b"MZ", b"ZM") else "com"

    if image_format == "mz":
        if len(data) < 0x1C or data[:2] not in (b"MZ", b"ZM"):
            raise ValueError("input is not a valid MZ executable")
        header_bytes = u16(data, 0x08) * 16
        pages = u16(data, 0x04)
        last_page_bytes = u16(data, 0x02)
        declared_size = pages * 512
        if last_page_bytes:
            declared_size -= 512 - last_page_bytes
        if header_bytes < 0x1C or header_bytes > len(data):
            raise ValueError(f"invalid MZ header size: {header_bytes}")
        declared_size = min(declared_size or len(data), len(data))
        module = data[header_bytes:declared_size]
        initial_cs = u16(data, 0x16)
        initial_ip = u16(data, 0x14)
        relocation_count = u16(data, 0x06)
        relocation_table_offset = u16(data, 0x18)
        relocation_end = relocation_table_offset + relocation_count * 4
        if relocation_end > header_bytes or relocation_end > len(data):
            raise ValueError("MZ relocation table leaves the executable header")
        relocations = tuple(
            (
                u16(data, relocation_table_offset + index * 4),
                u16(data, relocation_table_offset + index * 4 + 2),
            )
            for index in range(relocation_count)
        )
        module_base = 0 if base is None else base
        image_entry = module_base + initial_cs * 16 + initial_ip
        if entry is not None:
            image_entry = entry
        metadata = {
            "header_bytes": header_bytes,
            "relocation_count": relocation_count,
            "relocation_table_offset": relocation_table_offset,
            "initial_cs": initial_cs,
            "initial_ip": initial_ip,
            "initial_ss": u16(data, 0x0E),
            "initial_sp": u16(data, 0x10),
            "minimum_extra_paragraphs": u16(data, 0x0A),
            "maximum_extra_paragraphs": u16(data, 0x0C),
        }
        return Image(
            data, module, "mz", module_base, image_entry, metadata, relocations
        )

    if image_format not in ("com", "raw"):
        raise ValueError(f"unsupported image format: {image_format}")
    module_base = (0x100 if image_format == "com" else 0) if base is None else base
    image_entry = module_base if entry is None else entry
    return Image(data, data, image_format, module_base, image_entry, {}, ())


def operand_record(instruction: Any, operand: Any) -> dict[str, Any]:
    record: dict[str, Any] = {"size": int(operand.size)}
    if operand.type == X86_OP_REG:
        record.update(type="reg", reg=instruction.reg_name(operand.reg))
    elif operand.type == X86_OP_IMM:
        record.update(type="imm", value=int(operand.imm) & 0xFFFFF)
    elif operand.type == X86_OP_MEM:
        memory = operand.mem
        record.update(
            type="mem",
            segment=instruction.reg_name(memory.segment) if memory.segment else None,
            base=instruction.reg_name(memory.base) if memory.base else None,
            index=instruction.reg_name(memory.index) if memory.index else None,
            scale=int(memory.scale),
            displacement=int(memory.disp),
            write=bool(operand.access & CS_AC_WRITE),
        )
    else:
        record.update(type="other")
    return record


def direct_target(record: dict[str, Any]) -> int | None:
    operands = record["operands"]
    if len(operands) == 1 and operands[0]["type"] == "imm":
        return int(operands[0]["value"]) & 0xFFFF
    return None


def flow_kind(mnemonic: str) -> str:
    if mnemonic == "jmp":
        return "jump"
    if mnemonic.startswith("j") or mnemonic.startswith("loop"):
        return "conditional"
    if mnemonic in ("call", "lcall"):
        return "call"
    if mnemonic in ("ret", "retf", "iret"):
        return "return"
    if mnemonic == "int":
        return "interrupt"
    if mnemonic == "hlt":
        return "halt"
    return "linear"


def analyze(image: Image, source_name: str) -> dict[str, Any]:
    disassembler = Cs(CS_ARCH_X86, CS_MODE_16)
    disassembler.detail = True
    image_end = image.base + len(image.module_bytes)
    queue: deque[int] = deque([image.entry])
    decoded: dict[int, dict[str, Any]] = {}
    translated_decoded: dict[int, d2e_translate.Instruction] = {}
    occupied: dict[int, int] = {}
    edges: set[tuple[int, int, str]] = set()
    unresolved: set[tuple[int, str, str]] = set()
    issues: set[tuple[int, str]] = set()
    cs_base = (
        image.base + image.metadata["initial_cs"] * 16
        if image.format == "mz"
        else image.base - (0x100 if image.format == "com" else 0)
    )

    def enqueue(source: int, target: int, kind: str) -> None:
        edges.add((source, target, kind))
        if image.base <= target < image_end:
            queue.append(target)
        else:
            issues.add((source, f"{kind} target 0x{target:05x} leaves image"))

    while queue:
        address = queue.popleft()
        while address not in decoded:
            if not image.base <= address < image_end:
                issues.add((address, "decode address leaves image"))
                break
            if address in occupied:
                issues.add(
                    (address, f"control flow enters instruction at 0x{occupied[address]:05x}")
                )
                break
            offset = address - image.base
            instruction = next(
                disassembler.disasm(image.module_bytes[offset:], address, count=1), None
            )
            if instruction is None:
                issues.add((address, "Capstone could not decode instruction"))
                break
            try:
                d2e_translate.require_8086_encoding(
                    bytes(instruction.bytes), address
                )
            except d2e_translate.TranslationError as error:
                issues.add((address, str(error)))
                break
            mnemonic = d2e_translate.normalize_8086_mnemonic(
                bytes(instruction.bytes), instruction.mnemonic
            )
            record = {
                "address": address,
                "size": int(instruction.size),
                "bytes": bytes(instruction.bytes).hex(),
                "mnemonic": mnemonic,
                "op_str": instruction.op_str,
                "prefixes": [f"0x{value:02x}" for value in instruction.prefix if value],
                "operands": [
                    operand_record(instruction, operand)
                    for operand in instruction.operands
                ],
            }
            translated_instruction = d2e_translate.Instruction(
                address=address,
                size=int(instruction.size),
                mnemonic=mnemonic,
                op_str=instruction.op_str,
                operands=tuple(
                    d2e_translate.operand_tuple(instruction, operand)
                    for operand in instruction.operands
                ),
            )
            indirect_targets = d2e_translate.recover_cs_bx_jump_table(
                image.module_bytes, image.base, translated_instruction
            )
            if indirect_targets:
                record["indirect_targets"] = list(indirect_targets)
            for byte_address in range(address, address + instruction.size):
                previous = occupied.get(byte_address)
                if previous is not None and previous != address:
                    issues.add(
                        (address, f"overlaps instruction at 0x{previous:05x}")
                    )
                occupied[byte_address] = address
            decoded[address] = record
            translated_decoded[address] = translated_instruction

            vector_candidates = [translated_instruction]
            vector_candidates.extend(
                translated_decoded[candidate]
                for candidate in range(address + 1, address + 33)
                if candidate in translated_decoded
            )
            for vector_instruction in vector_candidates:
                interrupt_vector = d2e_translate.recover_interrupt_vector_targets(
                    image.module_bytes,
                    image.base,
                    cs_base,
                    vector_instruction,
                    translated_decoded,
                )
                if interrupt_vector is None:
                    continue
                vector, interrupt_targets = interrupt_vector
                vector_record = decoded[vector_instruction.address]
                vector_record["interrupt_vector"] = vector
                vector_record["interrupt_targets"] = list(interrupt_targets)
                for interrupt_target in interrupt_targets:
                    enqueue(
                        vector_instruction.address,
                        interrupt_target,
                        f"interrupt_vector_{vector:02x}",
                    )

            next_address = address + instruction.size
            kind = flow_kind(record["mnemonic"])
            target = direct_target(record)
            if kind == "jump":
                if target is None:
                    if indirect_targets:
                        for indirect_target in indirect_targets:
                            enqueue(address, indirect_target, "jump_table")
                    else:
                        unresolved.add((address, kind, record["op_str"]))
                else:
                    enqueue(address, target, kind)
                break
            if kind == "conditional":
                if target is None:
                    unresolved.add((address, kind, record["op_str"]))
                else:
                    enqueue(address, target, "taken")
                enqueue(address, next_address, "fallthrough")
                break
            if kind == "call":
                if target is None:
                    unresolved.add((address, kind, record["op_str"]))
                else:
                    enqueue(address, target, kind)
                enqueue(address, next_address, "return_site")
                break
            if kind in ("return", "halt"):
                break
            if kind == "interrupt":
                if next_address != image_end:
                    enqueue(address, next_address, "interrupt_return")
                break
            if next_address == image_end:
                break
            if next_address in decoded:
                edges.add((address, next_address, "fallthrough"))
                break
            address = next_address

    preliminary_edges = [
        {"source": source, "target": target, "kind": kind}
        for source, target, kind in sorted(edges)
    ]
    leaders = {image.entry}
    leaders.update(
        edge["target"] for edge in preliminary_edges if edge["target"] in decoded
    )
    block_addresses: list[tuple[int, list[int]]] = []
    for leader in sorted(leaders):
        addresses: list[int] = []
        current = leader
        while current in decoded:
            record = decoded[current]
            addresses.append(current)
            next_address = current + record["size"]
            if flow_kind(record["mnemonic"]) != "linear":
                break
            if next_address in leaders and next_address != leader:
                break
            current = next_address
        if addresses:
            block_addresses.append((leader, addresses))
            last = addresses[-1]
            last_record = decoded[last]
            next_address = last + last_record["size"]
            if flow_kind(last_record["mnemonic"]) == "linear" and next_address in leaders:
                edges.add((last, next_address, "fallthrough"))

    edge_records = [
        {"source": source, "target": target, "kind": kind}
        for source, target, kind in sorted(edges)
    ]
    blocks = [
        {
            "address": leader,
            "instructions": addresses,
            "successors": [
                edge for edge in edge_records if edge["source"] == addresses[-1]
            ],
        }
        for leader, addresses in block_addresses
    ]

    ordered_instructions = [decoded[address] for address in sorted(decoded)]
    frequency = Counter(record["mnemonic"] for record in ordered_instructions)
    interrupts: list[dict[str, int | None]] = []
    ports: list[dict[str, int | str]] = []
    segment_overrides: list[dict[str, int | str]] = []
    cga_candidates: list[dict[str, int | str]] = []
    memory_writes: list[int] = []
    for record in ordered_instructions:
        operands = record["operands"]
        if record["mnemonic"] == "int":
            number = operands[0]["value"] if operands and operands[0]["type"] == "imm" else None
            interrupts.append({"address": record["address"], "number": number})
        if record["mnemonic"] in ("in", "out"):
            port_operand = operands[-1] if record["mnemonic"] == "in" else operands[0]
            port: int | str = (
                port_operand["value"] if port_operand["type"] == "imm" else "dx"
            )
            ports.append(
                {"address": record["address"], "operation": record["mnemonic"], "port": port}
            )
        for operand in operands:
            if operand["type"] == "mem":
                if operand["segment"]:
                    segment_overrides.append(
                        {"address": record["address"], "segment": operand["segment"]}
                    )
                if operand["write"]:
                    memory_writes.append(record["address"])
            if operand["type"] == "imm" and 0xB800 <= operand["value"] <= 0xBBFF:
                cga_candidates.append(
                    {
                        "address": record["address"],
                        "kind": "segment_constant",
                        "value": operand["value"],
                    }
                )

    return {
        "schema": "d2e-static-inventory-v1",
        "file": {
            "name": source_name,
            "format": image.format,
            "size": len(image.file_bytes),
            "module_size": len(image.module_bytes),
            "sha256": hashlib.sha256(image.file_bytes).hexdigest(),
            "base": image.base,
            "entry": image.entry,
            "metadata": image.metadata,
        },
        "summary": {
            "instruction_count": len(ordered_instructions),
            "block_count": len(blocks),
            "edge_count": len(edge_records),
            "unresolved_flow_count": len(unresolved),
            "issue_count": len(issues),
        },
        "instruction_frequency": dict(sorted(frequency.items())),
        "interrupts": interrupts,
        "ports": ports,
        "segment_overrides": segment_overrides,
        "cga_candidates": cga_candidates,
        "memory_write_instructions": sorted(set(memory_writes)),
        "relocations": [
            {"offset": offset, "segment": segment}
            for offset, segment in image.relocations
        ],
        "unresolved_flow": [
            {"address": address, "kind": kind, "operand": operand}
            for address, kind, operand in sorted(unresolved)
        ],
        "recovered_indirect_flow": [
            {
                "address": record["address"],
                "operand": record["op_str"],
                "targets": record["indirect_targets"],
            }
            for record in ordered_instructions
            if record.get("indirect_targets")
        ],
        "recovered_interrupt_vectors": [
            {
                "address": record["address"],
                "vector": record["interrupt_vector"],
                "targets": record["interrupt_targets"],
            }
            for record in ordered_instructions
            if record.get("interrupt_targets")
        ],
        "issues": [
            {"address": address, "message": message}
            for address, message in sorted(issues)
        ],
        "blocks": blocks,
        "instructions": ordered_instructions,
    }


def hex_address(value: int) -> str:
    return f"0x{value:05x}"


def render_markdown(report: dict[str, Any]) -> str:
    file = report["file"]
    summary = report["summary"]
    lines = [
        f"# Static inventory: {file['name']}",
        "",
        "## Fingerprint",
        "",
        f"- Format: `{file['format']}`",
        f"- File size: `{file['size']}` bytes",
        f"- Module size: `{file['module_size']}` bytes",
        f"- SHA-256: `{file['sha256']}`",
        f"- Load base: `{hex_address(file['base'])}`",
        f"- Entry: `{hex_address(file['entry'])}`",
        "",
        "## Reachable inventory",
        "",
        f"- Instructions: `{summary['instruction_count']}`",
        f"- Basic blocks: `{summary['block_count']}`",
        f"- CFG edges: `{summary['edge_count']}`",
        f"- Unresolved control transfers: `{summary['unresolved_flow_count']}`",
        f"- Analysis issues: `{summary['issue_count']}`",
        "",
        "### Instruction frequency",
        "",
        "| Mnemonic | Count |",
        "|---|---:|",
    ]
    for mnemonic, count in report["instruction_frequency"].items():
        lines.append(f"| `{mnemonic}` | {count} |")
    lines.extend(["", "### Interrupts", ""])
    if report["interrupts"]:
        for item in report["interrupts"]:
            number = "dynamic" if item["number"] is None else f"0x{item['number']:02x}"
            lines.append(f"- `{hex_address(item['address'])}`: `INT {number}`")
    else:
        lines.append("None in the statically reachable set.")
    lines.extend(["", "### Port I/O", ""])
    if report["ports"]:
        for item in report["ports"]:
            port = item["port"] if isinstance(item["port"], str) else f"0x{item['port']:04x}"
            lines.append(
                f"- `{hex_address(item['address'])}`: `{item['operation'].upper()} {port}`"
            )
    else:
        lines.append("None in the statically reachable set.")
    lines.extend(["", "### CGA and segment candidates", ""])
    if report["cga_candidates"]:
        for item in report["cga_candidates"]:
            lines.append(
                f"- `{hex_address(item['address'])}`: {item['kind']} "
                f"`0x{item['value']:04x}`"
            )
    else:
        lines.append("No immediate CGA segment constants were found.")
    if report["segment_overrides"]:
        lines.append("")
        for item in report["segment_overrides"]:
            lines.append(
                f"- `{hex_address(item['address'])}`: explicit "
                f"`{item['segment'].upper()}` memory segment"
            )
    lines.extend(["", "### Memory writes", ""])
    if report["memory_write_instructions"]:
        lines.append(
            "Potential write sites requiring runtime code-range checks: "
            + ", ".join(
                f"`{hex_address(address)}`"
                for address in report["memory_write_instructions"]
            )
            + "."
        )
    else:
        lines.append("None in the statically reachable set.")
    lines.extend(["", "### Unresolved control flow and issues", ""])
    if not report["unresolved_flow"] and not report["issues"]:
        lines.append("None.")
    for item in report["unresolved_flow"]:
        lines.append(
            f"- `{hex_address(item['address'])}`: unresolved {item['kind']} `{item['operand']}`"
        )
    for item in report["issues"]:
        lines.append(f"- `{hex_address(item['address'])}`: {item['message']}")
    lines.extend(["", "### Recovered indirect control flow", ""])
    if report["recovered_indirect_flow"]:
        for item in report["recovered_indirect_flow"]:
            targets = ", ".join(
                f"`{hex_address(target)}`" for target in item["targets"]
            )
            lines.append(
                f"- `{hex_address(item['address'])}`: `{item['operand']}` -> {targets}"
            )
    else:
        lines.append("None.")
    lines.extend(["", "### Recovered hardware interrupt vectors", ""])
    if report["recovered_interrupt_vectors"]:
        for item in report["recovered_interrupt_vectors"]:
            targets = ", ".join(
                f"`{hex_address(target)}`" for target in item["targets"]
            )
            lines.append(
                f"- `{hex_address(item['address'])}`: IRQ/INT vector "
                f"`0x{item['vector']:02x}` -> {targets}"
            )
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("--format", choices=("auto", "com", "mz", "raw"), default="auto")
    parser.add_argument("--base", type=lambda value: int(value, 0))
    parser.add_argument("--entry", type=lambda value: int(value, 0))
    parser.add_argument("--hex-input", action="store_true")
    parser.add_argument("--json", type=pathlib.Path, required=True)
    parser.add_argument("--markdown", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = read_hex(args.input) if args.hex_input else args.input.read_bytes()
        image = identify(data, args.format, args.base, args.entry)
        report = analyze(image, args.input.name)
    except (OSError, ValueError) as error:
        print(f"analysis failed: {error}", file=sys.stderr)
        return 1
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(
        f"analyzed {report['summary']['instruction_count']} instructions in "
        f"{report['summary']['block_count']} blocks: {args.json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
