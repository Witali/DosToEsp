#!/usr/bin/env python3
"""Emit the initial Xtensa assembly backend for translated 8086 programs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class BackendError(RuntimeError):
    """The decoded program is outside the current Xtensa backend subset."""


REG16_OFFSETS = {
    "ax": 0,
    "cx": 2,
    "dx": 4,
    "bx": 6,
    "sp": 8,
    "bp": 10,
    "si": 12,
    "di": 14,
}


class _Emitter:
    def __init__(self) -> None:
        self.literals: list[tuple[str, int]] = []

    def literal(self, value: int, purpose: str) -> str:
        label = f".Lprogram_region_{purpose}_{len(self.literals)}"
        self.literals.append((label, value & 0xFFFFFFFF))
        return label


def _error(instruction: Any, detail: str) -> BackendError:
    return BackendError(
        f"{instruction.address:04x}: Xtensa assembly backend {detail} "
        f"({instruction.mnemonic} {instruction.op_str})"
    )


def _emit_mov(emitter: _Emitter, instruction: Any) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand MOV")
    destination, source = instruction.operands
    if destination[0] != "reg" or destination[1] not in REG16_OFFSETS:
        raise _error(instruction, "currently supports only 16-bit register MOV destinations")

    destination_offset = REG16_OFFSETS[str(destination[1])]
    if source[0] == "imm":
        literal = emitter.literal(int(source[1]) & 0xFFFF, "immediate")
        return [
            f"    l32r a4, {literal}",
            f"    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
        ]
    if source[0] == "reg" and source[1] in REG16_OFFSETS:
        source_offset = REG16_OFFSETS[str(source[1])]
        return [
            f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}",
            f"    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
        ]
    raise _error(instruction, "currently supports only immediate/register MOV sources")


def omitted_image_offsets(
    image: bytes,
    blocks: Mapping[int, Sequence[Any]],
    image_base: int = 0x100,
) -> frozenset[int]:
    """Return initialized-image offsets replaced by native code/control flow."""
    omitted: set[int] = set()
    for block in blocks.values():
        for instruction in block:
            instruction_offset = instruction.address - image_base
            instruction_end = instruction_offset + instruction.size
            if instruction_offset < 0 or instruction_end > len(image):
                raise BackendError(
                    f"{instruction.address:04x}: decoded instruction lies outside the image"
                )
            omitted.update(range(instruction_offset, instruction_end))

            if instruction.mnemonic == "jmp" and instruction.indirect_targets:
                pattern_offset = instruction_offset - 9
                table_offset = instruction.next_address - image_base
                if pattern_offset < 0 or pattern_offset + 3 > len(image):
                    raise BackendError(
                        f"{instruction.address:04x}: recognized jump table has no bounded pattern"
                    )
                table_size = (image[pattern_offset + 2] + 1) * 2
                table_end = table_offset + table_size
                if table_offset < 0 or table_end > len(image):
                    raise BackendError(
                        f"{instruction.address:04x}: recognized jump table lies outside the image"
                    )
                omitted.update(range(table_offset, table_end))
    return frozenset(omitted)


def extract_data_fragments(
    image: bytes,
    blocks: Mapping[int, Sequence[Any]],
    image_base: int = 0x100,
) -> list[tuple[int, bytes]]:
    """Extract contiguous initialized ranges not replaced by native lowering."""
    omitted = omitted_image_offsets(image, blocks, image_base)
    fragments: list[tuple[int, bytes]] = []
    start: int | None = None
    for offset in range(len(image) + 1):
        keep = offset < len(image) and offset not in omitted
        if keep and start is None:
            start = offset
        elif not keep and start is not None:
            fragments.append((start, image[start:offset]))
            start = None
    return fragments


def emit_program(
    image: bytes,
    blocks: Mapping[int, Sequence[Any]],
    name: str,
    load_segment: int,
    entry: int,
) -> str:
    """Emit a complete Xtensa `.S` unit for the first straight-line subset."""
    if list(sorted(blocks)) != [entry]:
        raise BackendError(
            "Xtensa assembly backend stage 1 requires exactly one block at the entry point"
        )
    block = list(blocks[entry])
    if not block or block[-1].mnemonic != "hlt":
        raise BackendError(
            "Xtensa assembly backend stage 1 requires the entry block to end in HLT"
        )

    emitter = _Emitter()
    data_fragments = extract_data_fragments(image, blocks)
    load_literal = emitter.literal(load_segment, "load_segment")
    entry_literal = emitter.literal(entry, "entry")
    next_ip_literal = emitter.literal(block[-1].next_address, "next_ip")
    body: list[str] = []
    for index, instruction in enumerate(block):
        body.append(
            f"    /* {instruction.address:04x}: {instruction.mnemonic} {instruction.op_str} */"
        )
        if instruction.mnemonic == "mov":
            body.extend(_emit_mov(emitter, instruction))
        elif instruction.mnemonic == "nop" and not instruction.operands:
            body.append("    nop")
        elif instruction.mnemonic == "hlt" and index == len(block) - 1:
            pass
        else:
            raise _error(instruction, "does not support this instruction yet")

    lines = [
        "/* Generated by tools/d2e_translate.py --backend xtensa-asm. Do not edit. */",
        '#include "d2e/native_asm_offsets.h"',
        "",
        '    .section .literal.program_region,"a",@progbits',
        "    .align 4",
    ]
    for label, value in emitter.literals:
        lines.extend([f"{label}:", f"    .long 0x{value:08x}"])
    lines.extend(
        [
            "",
            '    .section .text.program_region,"ax",@progbits',
            "    .align 4",
            "    .global program_region",
            "    .type program_region, @function",
            "program_region:",
            "    entry a1, 32",
            "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + (D2E_ASM_X86_CS_INDEX * 2)",
            f"    l32r a5, {load_literal}",
            "    bne a4, a5, .Lprogram_region_unknown",
            "    l16ui a4, a2, D2E_ASM_CPU_IP_OFFSET",
            f"    l32r a5, {entry_literal}",
            "    bne a4, a5, .Lprogram_region_unknown",
            "    beqz a3, .Lprogram_region_budget",
        ]
    )
    lines.extend(body)
    lines.extend(
        [
            f"    l32r a4, {next_ip_literal}",
            "    s16i a4, a2, D2E_ASM_CPU_IP_OFFSET",
            "    l32i a4, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET",
            "    l32i a5, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET + 4",
            f"    movi a6, {len(block)}",
            "    add a6, a4, a6",
            "    bltu a6, a4, .Lprogram_region_retired_carry",
            ".Lprogram_region_store_retired:",
            "    s32i a6, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET",
            "    s32i a5, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET + 4",
            "    movi a4, D2E_ASM_STOP_EXITED",
            "    s32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
            "    movi a2, 1",
            "    retw",
            ".Lprogram_region_retired_carry:",
            "    addi a5, a5, 1",
            "    j .Lprogram_region_store_retired",
            ".Lprogram_region_unknown:",
            "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + (D2E_ASM_X86_CS_INDEX * 2)",
            "    s16i a4, a2, D2E_ASM_CPU_FAULT_CS_OFFSET",
            "    l16ui a4, a2, D2E_ASM_CPU_IP_OFFSET",
            "    s16i a4, a2, D2E_ASM_CPU_FAULT_IP_OFFSET",
            "    movi a4, D2E_ASM_STOP_UNTRANSLATED_TARGET",
            "    s32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
            "    movi a2, 0",
            "    retw",
            ".Lprogram_region_budget:",
            "    movi a2, 0",
            "    retw",
            "    .size program_region, . - program_region",
            "",
        ]
    )
    for fragment_index, (_, fragment_data) in enumerate(data_fragments):
        lines.extend(
            [
                '    .section .rodata.d2e_generated_data,"a",@progbits',
                "    .align 4",
                f".Lprogram_data_{fragment_index}:",
            ]
        )
        for offset in range(0, len(fragment_data), 12):
            chunk = fragment_data[offset : offset + 12]
            lines.append("    .byte " + ", ".join(f"0x{value:02x}" for value in chunk))
    if data_fragments:
        lines.extend(
            [
                '    .section .rodata.d2e_generated_fragments,"a",@progbits',
                "    .align 4",
                ".Lprogram_fragments:",
            ]
        )
        for fragment_index, (fragment_offset, fragment_data) in enumerate(
            data_fragments
        ):
            lines.extend(
                [
                    f"    .long {fragment_offset}",
                    f"    .long .Lprogram_data_{fragment_index}",
                    f"    .long {len(fragment_data)}",
                ]
            )
    encoded_name = name.encode("ascii")
    lines.extend(
        [
            '    .section .rodata.d2e_generated_name,"a",@progbits',
            "    .align 4",
            ".Lprogram_name:",
            "    .byte " + ", ".join(f"0x{value:02x}" for value in encoded_name + b"\0"),
            "",
            '    .section .rodata.d2e_generated_program,"a",@progbits',
            "    .align 4",
            "    .global d2e_generated_program",
            "    .type d2e_generated_program, @object",
            "d2e_generated_program:",
            "    .long .Lprogram_name",
            "    .long 0 /* D2E_NATIVE_IMAGE_COM */",
            f"    .short 0x{load_segment & 0xFFFF:04x}",
            "    .short 0 /* entry_cs */",
            f"    .short 0x{entry & 0xFFFF:04x}",
            "    .short 0 /* initial_ss */",
            "    .short 0xfffe /* initial_sp */",
            "    .short 0 /* pointer alignment */",
            "    .long 0 /* full image omitted */",
            f"    .long {len(image)}",
            "    .long 0 /* relocations */",
            "    .long 0 /* relocation_count */",
            "    .long 0 /* blocks */",
            "    .long 0 /* block_count */",
            "    .long program_region",
            (
                "    .long .Lprogram_fragments"
                if data_fragments
                else "    .long 0 /* image_fragments */"
            ),
            f"    .long {len(data_fragments)} /* image_fragment_count */",
            "    .size d2e_generated_program, . - d2e_generated_program",
            "",
        ]
    )
    return "\n".join(lines)
