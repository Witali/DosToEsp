#!/usr/bin/env python3
"""Compare a static inventory with the current native translator coverage."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import d2e_translate


SUPPORTED_CONTROL = set(d2e_translate.CONDITIONS) | {
    "call", "ret", "retf", "jmp", "loop", "loope", "loopne", "jcxz", "int", "hlt"
}
UNSUPPORTED_CONTROL = {"lcall", "iret"}


def translator_instruction(record: dict[str, Any]) -> d2e_translate.Instruction:
    operands: list[tuple[str, d2e_translate.OperandValue]] = []
    for operand in record["operands"]:
        if operand["type"] == "reg":
            operands.append(("reg", operand["reg"]))
        elif operand["type"] == "imm":
            operands.append(("imm", operand["value"]))
        elif operand["type"] == "mem":
            operands.append(
                (
                    "mem",
                    d2e_translate.MemoryOperand(
                        width=int(operand["size"]) * 8,
                        segment=operand["segment"],
                        base=operand["base"],
                        index=operand["index"],
                        displacement=int(operand["displacement"]),
                    ),
                )
            )
        else:
            operands.append(("unsupported", 0))
    return d2e_translate.Instruction(
        address=record["address"],
        size=record["size"],
        mnemonic=record["mnemonic"],
        op_str=record["op_str"],
        operands=tuple(operands),
    )


def classify(record: dict[str, Any]) -> tuple[bool, str]:
    mnemonic = record["mnemonic"]
    operands = record["operands"]
    if mnemonic in UNSUPPORTED_CONTROL:
        return False, "control_transfer"
    if mnemonic in SUPPORTED_CONTROL:
        if mnemonic in ("ret", "retf"):
            if not operands or (
                len(operands) == 1 and operands[0]["type"] == "imm"
            ):
                return True, "supported"
            return False, "control_transfer"
        if mnemonic == "hlt":
            return True, "supported"
        if mnemonic == "jmp" and record.get("indirect_targets"):
            return True, "supported"
        if len(operands) != 1 or operands[0]["type"] != "imm":
            return False, "indirect_control_target"
        return True, "supported"
    if any(operand["type"] == "other" for operand in operands):
        return False, "unsupported_operand"
    for operand in operands:
        if operand["type"] == "reg":
            name = operand["reg"]
            if (
                name not in d2e_translate.REG16
                and name not in d2e_translate.REG8
                and name not in d2e_translate.SEGMENTS
            ):
                return False, "segment_or_special_register"
    try:
        d2e_translate.translate_data_instruction(
            translator_instruction(record), cached=True
        )
    except d2e_translate.TranslationError:
        reason = (
            "memory_operand"
            if any(operand["type"] == "mem" for operand in operands)
            else "instruction_semantics"
        )
        return False, reason
    return True, "supported"


def coverage(inventory: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    supported_count = 0
    reason_counts: Counter[str] = Counter()
    for instruction in inventory["instructions"]:
        mnemonic = instruction["mnemonic"]
        supported, reason = classify(instruction)
        entry = entries.setdefault(
            mnemonic,
            {
                "mnemonic": mnemonic,
                "total": 0,
                "supported": 0,
                "unsupported": 0,
                "reasons": Counter(),
                "examples": [],
            },
        )
        entry["total"] += 1
        if supported:
            supported_count += 1
            entry["supported"] += 1
        else:
            entry["unsupported"] += 1
            entry["reasons"][reason] += 1
            reason_counts[reason] += 1
            if len(entry["examples"]) < 5:
                entry["examples"].append(
                    {
                        "address": instruction["address"],
                        "text": (
                            f"{instruction['mnemonic']} {instruction['op_str']}"
                        ).rstrip(),
                        "reason": reason,
                    }
                )

    mnemonic_entries = []
    for entry in entries.values():
        entry["reasons"] = dict(sorted(entry["reasons"].items()))
        mnemonic_entries.append(entry)
    mnemonic_entries.sort(key=lambda item: (-item["unsupported"], item["mnemonic"]))
    total = len(inventory["instructions"])
    return {
        "schema": "d2e-translator-coverage-v1",
        "binary_sha256": inventory["file"]["sha256"],
        "summary": {
            "instruction_count": total,
            "supported_instruction_count": supported_count,
            "unsupported_instruction_count": total - supported_count,
            "supported_percent": round(supported_count * 100.0 / total, 2) if total else 100.0,
            "fully_supported_mnemonic_count": sum(
                1 for entry in mnemonic_entries if entry["unsupported"] == 0
            ),
            "mnemonic_count": len(mnemonic_entries),
        },
        "unsupported_reasons": dict(sorted(reason_counts.items())),
        "mnemonics": mnemonic_entries,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Native translator coverage",
        "",
        f"- Binary SHA-256: `{report['binary_sha256']}`",
        f"- Instruction sites: `{summary['instruction_count']}`",
        f"- Currently translatable: `{summary['supported_instruction_count']}` "
        f"(`{summary['supported_percent']:.2f}%`)",
        f"- Unsupported: `{summary['unsupported_instruction_count']}`",
        "",
        "## Unsupported sites by mnemonic",
        "",
        "| Mnemonic | Unsupported | Total | Primary reason |",
        "|---|---:|---:|---|",
    ]
    for entry in report["mnemonics"]:
        if not entry["unsupported"]:
            continue
        reason = max(entry["reasons"], key=entry["reasons"].get)
        lines.append(
            f"| `{entry['mnemonic']}` | {entry['unsupported']} | "
            f"{entry['total']} | `{reason}` |"
        )
    lines.extend(["", "## First examples", ""])
    for entry in report["mnemonics"]:
        if not entry["examples"]:
            continue
        lines.append(f"### `{entry['mnemonic']}`")
        lines.append("")
        for example in entry["examples"]:
            lines.append(
                f"- `0x{example['address']:05x}`: `{example['text']}` "
                f"({example['reason']})"
            )
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=pathlib.Path)
    parser.add_argument("--json", type=pathlib.Path, required=True)
    parser.add_argument("--markdown", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        report = coverage(inventory)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"coverage failed: {error}", file=sys.stderr)
        return 1
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(
        f"translator covers {report['summary']['supported_instruction_count']} of "
        f"{report['summary']['instruction_count']} instruction sites "
        f"({report['summary']['supported_percent']:.2f}%): {args.json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
