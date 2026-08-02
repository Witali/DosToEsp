#!/usr/bin/env python3
"""Emit the initial Xtensa assembly backend for translated 8086 programs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import d2e_flags


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

SEGMENT_INDICES = {
    "es": "D2E_ASM_X86_ES_INDEX",
    "cs": "D2E_ASM_X86_CS_INDEX",
    "ss": "D2E_ASM_X86_SS_INDEX",
    "ds": "D2E_ASM_X86_DS_INDEX",
}


class _Emitter:
    def __init__(self) -> None:
        self.literals: list[tuple[str, int]] = []
        self.local_count = 0

    def literal(self, value: int, purpose: str) -> str:
        label = f".Lprogram_region_{purpose}_{len(self.literals)}"
        self.literals.append((label, value & 0xFFFFFFFF))
        return label

    def local(self, purpose: str) -> str:
        label = f".Lprogram_region_{purpose}_{self.local_count}"
        self.local_count += 1
        return label


def _error(instruction: Any, detail: str) -> BackendError:
    return BackendError(
        f"{instruction.address:04x}: Xtensa assembly backend {detail} "
        f"({instruction.mnemonic} {instruction.op_str})"
    )


def _absolute_memory(instruction: Any, operand: tuple[Any, Any]) -> Any:
    if operand[0] != "mem":
        raise _error(instruction, "requires a memory operand")
    memory = operand[1]
    if (
        getattr(memory, "width", 0) != 16
        or getattr(memory, "base", None) is not None
        or getattr(memory, "index", None) is not None
    ):
        raise _error(
            instruction,
            "currently supports only absolute 16-bit memory operands",
        )
    return memory


def _emit_memory_arguments(
    emitter: _Emitter,
    instruction: Any,
    memory: Any,
) -> list[str]:
    segment = getattr(memory, "segment", None) or "ds"
    if segment not in SEGMENT_INDICES:
        raise _error(instruction, "uses an unsupported memory segment")
    offset_literal = emitter.literal(
        int(getattr(memory, "displacement", 0)) & 0xFFFF,
        "memory_offset",
    )
    return [
        "    mov a10, a2",
        (
            "    l16ui a11, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            f"({SEGMENT_INDICES[segment]} * 2)"
        ),
        f"    l32r a12, {offset_literal}",
    ]


def _emit_mov(emitter: _Emitter, instruction: Any) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand MOV")
    destination, source = instruction.operands
    if destination[0] == "reg" and destination[1] in REG16_OFFSETS:
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
        if source[0] == "mem":
            memory = _absolute_memory(instruction, source)
            return [
                *_emit_memory_arguments(emitter, instruction, memory),
                "    call8 d2e_native_helper_read16",
                (
                    "    s16i a10, a2, D2E_ASM_CPU_REGS_OFFSET + "
                    f"{destination_offset}"
                ),
            ]
        raise _error(
            instruction,
            "currently supports only immediate/register/absolute-memory MOV sources",
        )

    if destination[0] == "mem":
        memory = _absolute_memory(instruction, destination)
        lines = _emit_memory_arguments(emitter, instruction, memory)
        if source[0] == "imm":
            literal = emitter.literal(int(source[1]) & 0xFFFF, "immediate")
            lines.append(f"    l32r a13, {literal}")
        elif source[0] == "reg" and source[1] in REG16_OFFSETS:
            source_offset = REG16_OFFSETS[str(source[1])]
            lines.append(
                f"    l16ui a13, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}"
            )
        else:
            raise _error(
                instruction,
                "currently supports only immediate/register MOV stores",
            )
        completed = emitter.local("memory_write_completed")
        lines.extend(
            [
                "    call8 d2e_native_helper_write16",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
        return lines

    raise _error(
        instruction,
        "currently supports only 16-bit register/memory MOV destinations",
    )


def _emit_mul16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if (
        len(instruction.operands) != 1
        or instruction.operands[0][0] != "reg"
        or instruction.operands[0][1] not in REG16_OFFSETS
    ):
        raise _error(instruction, "currently supports only 16-bit register MUL operands")
    operand_offset = REG16_OFFSETS[str(instruction.operands[0][1])]
    lines = [
        "    mov a10, a2",
        f"    l16ui a11, a2, D2E_ASM_CPU_REGS_OFFSET + {operand_offset}",
    ]
    if live_flags == 0:
        lines.append("    movi a12, 0 /* no MUL flags are live */")
    else:
        live_literal = emitter.literal(live_flags, "live_flags")
        lines.append(f"    l32r a12, {live_literal}")
    lines.append("    call8 d2e_native_helper_mul16")
    return lines


def _emit_add16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand ADD")
    destination, source = instruction.operands
    if destination[0] != "reg" or destination[1] not in REG16_OFFSETS:
        raise _error(instruction, "currently supports only 16-bit register ADD destinations")
    if live_flags not in (0, d2e_flags.ZF):
        raise _error(instruction, "does not yet materialize live ADD flags")

    destination_offset = REG16_OFFSETS[str(destination[1])]
    lines = [
        f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
    ]
    if source[0] == "imm":
        source_literal = emitter.literal(int(source[1]) & 0xFFFF, "immediate")
        lines.append(f"    l32r a5, {source_literal}")
    elif source[0] == "reg" and source[1] in REG16_OFFSETS:
        source_offset = REG16_OFFSETS[str(source[1])]
        lines.append(
            f"    l16ui a5, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}"
        )
    else:
        raise _error(instruction, "currently supports only immediate/register ADD sources")
    lines.extend(
        [
            "    add a4, a4, a5",
            "    extui a4, a4, 0, 16",
            f"    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
        ]
    )
    if live_flags == d2e_flags.ZF:
        lines.extend(_emit_zero_flag(emitter, "a4"))
    return lines


def _emit_zero_flag(emitter: _Emitter, result_register: str) -> list[str]:
    done = emitter.local("zero_flag_done")
    return [
        "    l16ui a5, a2, D2E_ASM_CPU_FLAGS_OFFSET",
        f"    movi a8, {-1 - d2e_flags.ZF}",
        "    and a5, a5, a8",
        f"    bnez {result_register}, {done}",
        f"    movi a8, {d2e_flags.ZF}",
        "    or a5, a5, a8",
        f"{done}:",
        "    s16i a5, a2, D2E_ASM_CPU_FLAGS_OFFSET",
    ]


def _emit_cmp16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand CMP")
    left, right = instruction.operands
    if left[0] != "reg" or left[1] not in REG16_OFFSETS:
        raise _error(instruction, "currently supports only 16-bit register CMP left operands")
    if live_flags not in (0, d2e_flags.ZF):
        raise _error(instruction, "does not yet materialize these live CMP flags")
    if live_flags == 0:
        return ["    /* CMP result and all flags are dead. */"]

    left_offset = REG16_OFFSETS[str(left[1])]
    lines = [f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {left_offset}"]
    if right[0] == "imm":
        right_literal = emitter.literal(int(right[1]) & 0xFFFF, "immediate")
        lines.append(f"    l32r a5, {right_literal}")
    elif right[0] == "reg" and right[1] in REG16_OFFSETS:
        right_offset = REG16_OFFSETS[str(right[1])]
        lines.append(f"    l16ui a5, a2, D2E_ASM_CPU_REGS_OFFSET + {right_offset}")
    else:
        raise _error(instruction, "currently supports only immediate/register CMP right operands")
    lines.extend(["    sub a4, a4, a5", "    extui a4, a4, 0, 16"])
    lines.extend(_emit_zero_flag(emitter, "a4"))
    return lines


def _direct_target(instruction: Any) -> int:
    if len(instruction.operands) != 1 or instruction.operands[0][0] != "imm":
        raise _error(instruction, "requires a direct control-flow target")
    return int(instruction.operands[0][1]) & 0xFFFF


def _block_label(address: int) -> str:
    return f".Lprogram_region_block_{address:04x}"


def _emit_edge(
    emitter: _Emitter,
    target: int,
    blocks: Mapping[int, Sequence[Any]],
) -> list[str]:
    if target in blocks:
        return [f"    j {_block_label(target)}"]
    target_literal = emitter.literal(target, "edge_target")
    return [
        f"    l32r a4, {target_literal}",
        "    s16i a4, a2, D2E_ASM_CPU_IP_OFFSET",
        "    j .Lprogram_region_dispatch",
    ]


def _emit_retired(emitter: _Emitter, count: int) -> list[str]:
    if count <= 127:
        return [f"    addi a7, a7, {count}"]
    count_literal = emitter.literal(count, "retired")
    return [f"    l32r a4, {count_literal}", "    add a7, a7, a4"]


def _emit_condition(emitter: _Emitter, instruction: Any, taken: str) -> list[str]:
    if instruction.mnemonic not in ("je", "jz", "jne", "jnz"):
        raise _error(instruction, "does not support this condition yet")
    branch = "bnez" if instruction.mnemonic in ("je", "jz") else "beqz"
    return [
        "    l16ui a4, a2, D2E_ASM_CPU_FLAGS_OFFSET",
        f"    movi a5, {d2e_flags.ZF}",
        "    and a4, a4, a5",
        f"    {branch} a4, {taken}",
    ]


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
    """Emit a complete Xtensa `.S` unit for the supported COM subset."""
    if entry not in blocks:
        raise BackendError("Xtensa assembly backend has no block at the entry point")
    if any(not sequence for sequence in blocks.values()):
        raise BackendError("Xtensa assembly backend cannot emit an empty block")

    emitter = _Emitter()
    data_fragments = extract_data_fragments(image, blocks)
    flag_liveness = d2e_flags.analyze(blocks)
    load_literal = emitter.literal(load_segment, "load_segment")
    leader_literals = {
        leader: emitter.literal(leader, "leader") for leader in sorted(blocks)
    }
    body: list[str] = []
    for leader in sorted(blocks):
        block = list(blocks[leader])
        execute = emitter.local("execute_block")
        body.extend(
            [
                f"{_block_label(leader)}:",
                f"    bltu a6, a3, {execute}",
                f"    l32r a4, {leader_literals[leader]}",
                "    s16i a4, a2, D2E_ASM_CPU_IP_OFFSET",
                "    j .Lprogram_region_finish",
                f"{execute}:",
                "    addi a6, a6, 1",
            ]
        )
        terminated = False
        for index, instruction in enumerate(block):
            mnemonic = instruction.mnemonic
            body.append(
                f"    /* {instruction.address:04x}: {mnemonic} {instruction.op_str} */"
            )
            if mnemonic in d2e_flags.CONDITION_READS:
                if index != len(block) - 1:
                    raise _error(instruction, "requires a conditional branch to end its block")
                taken = emitter.local("branch_taken")
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(_emit_condition(emitter, instruction, taken))
                body.extend(_emit_edge(emitter, instruction.next_address, blocks))
                body.append(f"{taken}:")
                body.extend(_emit_edge(emitter, _direct_target(instruction), blocks))
                terminated = True
            elif mnemonic == "jmp":
                if index != len(block) - 1:
                    raise _error(instruction, "requires JMP to end its block")
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(_emit_edge(emitter, _direct_target(instruction), blocks))
                terminated = True
            elif mnemonic == "hlt":
                if index != len(block) - 1:
                    raise _error(instruction, "requires HLT to end its block")
                next_ip_literal = emitter.literal(instruction.next_address, "next_ip")
                body.extend(
                    [
                        f"    l32r a4, {next_ip_literal}",
                        "    s16i a4, a2, D2E_ASM_CPU_IP_OFFSET",
                    ]
                )
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(
                    [
                        "    movi a4, D2E_ASM_STOP_EXITED",
                        "    s32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                        "    j .Lprogram_region_finish",
                    ]
                )
                terminated = True
            elif mnemonic == "mov":
                body.extend(_emit_mov(emitter, instruction))
            elif mnemonic == "add":
                body.extend(
                    _emit_add16(
                        emitter,
                        instruction,
                        flag_liveness.live_defined[instruction.address],
                    )
                )
            elif mnemonic == "cmp":
                body.extend(
                    _emit_cmp16(
                        emitter,
                        instruction,
                        flag_liveness.live_defined[instruction.address],
                    )
                )
            elif mnemonic == "mul":
                body.extend(
                    _emit_mul16(
                        emitter,
                        instruction,
                        flag_liveness.live_defined[instruction.address],
                    )
                )
            elif mnemonic == "nop" and not instruction.operands:
                body.append("    nop")
            else:
                raise _error(instruction, "does not support this instruction yet")
        if not terminated:
            body.extend(_emit_retired(emitter, len(block)))
            body.extend(_emit_edge(emitter, block[-1].next_address, blocks))

    lines = [
        "/* Generated by tools/d2e_translate.py --backend xtensa-asm. Do not edit. */",
        '#include "d2e/native_asm_offsets.h"',
        "    .extern d2e_native_helper_mul16",
        "    .extern d2e_native_helper_read16",
        "    .extern d2e_native_helper_write16",
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
            "    movi a6, 0 /* executed blocks */",
            "    movi a7, 0 /* retired guest instructions */",
            ".Lprogram_region_dispatch:",
            "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + (D2E_ASM_X86_CS_INDEX * 2)",
            f"    l32r a5, {load_literal}",
            "    bne a4, a5, .Lprogram_region_unknown",
            "    l16ui a4, a2, D2E_ASM_CPU_IP_OFFSET",
        ]
    )
    for leader in sorted(blocks):
        lines.extend(
            [
                f"    l32r a5, {leader_literals[leader]}",
                f"    beq a4, a5, {_block_label(leader)}",
            ]
        )
    lines.append("    j .Lprogram_region_unknown")
    lines.extend(body)
    lines.extend(
        [
            ".Lprogram_region_unknown:",
            "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + (D2E_ASM_X86_CS_INDEX * 2)",
            "    s16i a4, a2, D2E_ASM_CPU_FAULT_CS_OFFSET",
            "    l16ui a4, a2, D2E_ASM_CPU_IP_OFFSET",
            "    s16i a4, a2, D2E_ASM_CPU_FAULT_IP_OFFSET",
            "    movi a4, D2E_ASM_STOP_UNTRANSLATED_TARGET",
            "    s32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
            ".Lprogram_region_finish:",
            "    beqz a7, .Lprogram_region_return",
            "    l32i a4, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET",
            "    l32i a5, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET + 4",
            "    add a8, a4, a7",
            "    bltu a8, a4, .Lprogram_region_retired_carry",
            ".Lprogram_region_store_retired:",
            "    s32i a8, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET",
            "    s32i a5, a2, D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET + 4",
            ".Lprogram_region_return:",
            "    mov a2, a6",
            "    retw",
            ".Lprogram_region_retired_carry:",
            "    addi a5, a5, 1",
            "    j .Lprogram_region_store_retired",
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
