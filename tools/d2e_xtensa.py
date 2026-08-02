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

REG8_OFFSETS = {
    "al": 0,
    "ah": 1,
    "cl": 2,
    "ch": 3,
    "dl": 4,
    "dh": 5,
    "bl": 6,
    "bh": 7,
}

SEGMENT_INDICES = {
    "es": "D2E_ASM_X86_ES_INDEX",
    "cs": "D2E_ASM_X86_CS_INDEX",
    "ss": "D2E_ASM_X86_SS_INDEX",
    "ds": "D2E_ASM_X86_DS_INDEX",
}


class _Emitter:
    def __init__(self, image_format: str, load_segment: int) -> None:
        self.literals: list[tuple[str, int]] = []
        self.local_count = 0
        self.image_format = image_format
        self.load_segment = load_segment

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


def _memory_operand(
    instruction: Any,
    operand: tuple[Any, Any],
    width: int,
) -> Any:
    if operand[0] != "mem":
        raise _error(instruction, "requires a memory operand")
    memory = operand[1]
    if getattr(memory, "width", 0) != width:
        raise _error(instruction, f"requires a {width}-bit memory operand")
    for register in (
        getattr(memory, "base", None),
        getattr(memory, "index", None),
    ):
        if register is not None and register not in REG16_OFFSETS:
            raise _error(instruction, "uses an unsupported address register")
    return memory


def _emit_memory_arguments(
    emitter: _Emitter,
    instruction: Any,
    memory: Any,
) -> list[str]:
    base = getattr(memory, "base", None)
    index = getattr(memory, "index", None)
    default_segment = "ss" if "bp" in (base, index) else "ds"
    segment = getattr(memory, "segment", None) or default_segment
    if segment not in SEGMENT_INDICES:
        raise _error(instruction, "uses an unsupported memory segment")
    offset_literal = emitter.literal(
        int(getattr(memory, "displacement", 0)) & 0xFFFF,
        "memory_offset",
    )
    lines = [
        "    mov a10, a2",
        (
            "    l16ui a11, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            f"({SEGMENT_INDICES[segment]} * 2)"
        ),
        f"    l32r a12, {offset_literal}",
    ]
    for register in (base, index):
        if register is not None:
            lines.extend(
                [
                    (
                        "    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + "
                        f"{REG16_OFFSETS[register]}"
                    ),
                    "    add a12, a12, a4",
                ]
            )
    if base is not None or index is not None:
        lines.append("    extui a12, a12, 0, 16")
    return lines


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
            memory = _memory_operand(instruction, source, 16)
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
            "currently supports only immediate/register/memory MOV sources",
        )

    if destination[0] == "reg" and destination[1] in REG8_OFFSETS:
        destination_offset = REG8_OFFSETS[str(destination[1])]
        if source[0] == "imm":
            literal = emitter.literal(int(source[1]) & 0xFF, "immediate")
            return [
                f"    l32r a4, {literal}",
                f"    s8i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
            ]
        if source[0] == "reg" and source[1] in REG8_OFFSETS:
            source_offset = REG8_OFFSETS[str(source[1])]
            return [
                f"    l8ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}",
                f"    s8i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
            ]
        if source[0] == "mem":
            memory = _memory_operand(instruction, source, 8)
            return [
                *_emit_memory_arguments(emitter, instruction, memory),
                "    call8 d2e_native_helper_read8",
                (
                    "    s8i a10, a2, D2E_ASM_CPU_REGS_OFFSET + "
                    f"{destination_offset}"
                ),
            ]
        raise _error(
            instruction,
            "currently supports only immediate/register/memory byte MOV sources",
        )

    if destination[0] == "mem":
        width = int(getattr(destination[1], "width", 0))
        if width not in (8, 16):
            raise _error(instruction, "currently supports only 8/16-bit MOV stores")
        memory = _memory_operand(instruction, destination, width)
        lines = _emit_memory_arguments(emitter, instruction, memory)
        if source[0] == "imm":
            mask = 0xFF if width == 8 else 0xFFFF
            literal = emitter.literal(int(source[1]) & mask, "immediate")
            lines.append(f"    l32r a13, {literal}")
        elif (
            source[0] == "reg"
            and width == 16
            and source[1] in REG16_OFFSETS
        ):
            source_offset = REG16_OFFSETS[str(source[1])]
            lines.append(
                f"    l16ui a13, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}"
            )
        elif source[0] == "reg" and width == 8 and source[1] in REG8_OFFSETS:
            source_offset = REG8_OFFSETS[str(source[1])]
            lines.append(
                f"    l8ui a13, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}"
            )
        else:
            raise _error(
                instruction,
                "currently supports only immediate/register MOV stores",
            )
        completed = emitter.local("memory_write_completed")
        lines.extend(
            [
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
        return lines

    raise _error(
        instruction,
        "currently supports only 8/16-bit register/memory MOV destinations",
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


def _emit_compare_flags(
    emitter: _Emitter,
    left_register: str,
    right_register: str,
    live_flags: int,
) -> list[str]:
    lines = [
        "    l16ui a8, a2, D2E_ASM_CPU_FLAGS_OFFSET",
        f"    movi a9, {-1 - live_flags}",
        "    and a8, a8, a9",
    ]
    if live_flags & d2e_flags.CF:
        carry_done = emitter.local("compare_carry_done")
        lines.extend(
            [
                f"    bgeu {left_register}, {right_register}, {carry_done}",
                f"    movi a9, {d2e_flags.CF}",
                "    or a8, a8, a9",
                f"{carry_done}:",
            ]
        )
    if live_flags & d2e_flags.ZF:
        zero_done = emitter.local("compare_zero_done")
        lines.extend(
            [
                f"    sub a9, {left_register}, {right_register}",
                f"    bnez a9, {zero_done}",
                f"    movi a9, {d2e_flags.ZF}",
                "    or a8, a8, a9",
                f"{zero_done}:",
            ]
        )
    lines.append("    s16i a8, a2, D2E_ASM_CPU_FLAGS_OFFSET")
    return lines


def _emit_cmp16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand CMP")
    left, right = instruction.operands
    if left[0] != "reg" or left[1] not in REG16_OFFSETS:
        raise _error(instruction, "currently supports only 16-bit register CMP left operands")
    if live_flags & ~(d2e_flags.CF | d2e_flags.ZF):
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
    lines.extend(_emit_compare_flags(emitter, "a4", "a5", live_flags))
    return lines


def _emit_sub16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand SUB")
    destination, source = instruction.operands
    if destination[0] != "reg" or destination[1] not in REG16_OFFSETS:
        raise _error(instruction, "currently supports only 16-bit register SUB destinations")
    if live_flags != 0:
        raise _error(instruction, "does not yet materialize live SUB flags")

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
        raise _error(instruction, "currently supports only immediate/register SUB sources")
    lines.extend(
        [
            "    sub a4, a4, a5",
            "    extui a4, a4, 0, 16",
            f"    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
        ]
    )
    return lines


def _emit_shl16(instruction: Any, live_flags: int) -> list[str]:
    if (
        len(instruction.operands) != 2
        or instruction.operands[0][0] != "reg"
        or instruction.operands[0][1] not in REG16_OFFSETS
        or instruction.operands[1] != ("imm", 1)
    ):
        raise _error(instruction, "currently supports only 16-bit register SHL by one")
    if live_flags != 0:
        raise _error(instruction, "does not yet materialize live SHL flags")
    destination_offset = REG16_OFFSETS[str(instruction.operands[0][1])]
    return [
        f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
        "    slli a4, a4, 1",
        "    extui a4, a4, 0, 16",
        f"    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}",
    ]


def _direct_target(instruction: Any) -> int:
    if len(instruction.operands) != 1 or instruction.operands[0][0] != "imm":
        raise _error(instruction, "requires a direct control-flow target")
    return int(instruction.operands[0][1]) & 0xFFFF


def _block_label(address: int) -> str:
    return f".Lprogram_region_block_{address:04x}"


def _emit_store_ip(emitter: _Emitter, target: int) -> list[str]:
    target_literal = emitter.literal(target, "edge_target")
    lines = [f"    l32r a4, {target_literal}"]
    if emitter.image_format == "mz":
        load_literal = emitter.literal(emitter.load_segment, "load_segment")
        lines.extend(
            [
                (
                    "    l16ui a5, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
                    "(D2E_ASM_X86_CS_INDEX * 2)"
                ),
                f"    l32r a8, {load_literal}",
                "    sub a5, a5, a8",
                "    extui a5, a5, 0, 16",
                "    slli a5, a5, 4",
                "    sub a4, a4, a5",
            ]
        )
    lines.append("    s16i a4, a2, D2E_ASM_CPU_IP_OFFSET")
    return lines


def _emit_edge(
    emitter: _Emitter,
    target: int,
    blocks: Mapping[int, Sequence[Any]],
) -> list[str]:
    if target in blocks:
        return [f"    j {_block_label(target)}"]
    return [*_emit_store_ip(emitter, target), "    j .Lprogram_region_dispatch"]


def _emit_retired(emitter: _Emitter, count: int) -> list[str]:
    if count <= 127:
        return [f"    addi a7, a7, {count}"]
    count_literal = emitter.literal(count, "retired")
    return [f"    l32r a4, {count_literal}", "    add a7, a7, a4"]


def _emit_condition(emitter: _Emitter, instruction: Any, taken: str) -> list[str]:
    supported = {
        "jb",
        "jc",
        "jnae",
        "jae",
        "jnb",
        "jnc",
        "je",
        "jz",
        "jne",
        "jnz",
        "jbe",
        "jna",
        "ja",
        "jnbe",
    }
    if instruction.mnemonic not in supported:
        raise _error(instruction, "does not support this condition yet")
    branch_when_clear = {
        "jae",
        "jnb",
        "jnc",
        "jne",
        "jnz",
        "ja",
        "jnbe",
    }
    branch = "beqz" if instruction.mnemonic in branch_when_clear else "bnez"
    mask = d2e_flags.CONDITION_READS[instruction.mnemonic]
    return [
        "    l16ui a4, a2, D2E_ASM_CPU_FLAGS_OFFSET",
        f"    movi a5, {mask}",
        "    and a4, a4, a5",
        f"    {branch} a4, {taken}",
    ]


def _emit_indirect_jump(
    emitter: _Emitter,
    instruction: Any,
    blocks: Mapping[int, Sequence[Any]],
) -> list[str]:
    entries = tuple(getattr(instruction, "indirect_table_entries", ()))
    if not entries:
        raise _error(instruction, "has no recovered jump-table entries")
    if (
        len(instruction.operands) != 1
        or instruction.operands[0][0] != "mem"
        or getattr(instruction.operands[0][1], "segment", None) != "cs"
        or getattr(instruction.operands[0][1], "base", None) != "bx"
        or getattr(instruction.operands[0][1], "index", None) is not None
    ):
        raise _error(instruction, "uses an unsupported indirect jump form")

    matches = [emitter.local("jump_table_entry") for _ in entries]
    lines = [
        f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS['bx']}",
    ]
    for index, match in enumerate(matches):
        lines.extend([f"    movi a5, {index * 2}", f"    beq a4, a5, {match}"])
    lines.append("    j .Lprogram_region_unknown")
    for match, target in zip(matches, entries, strict=True):
        lines.append(f"{match}:")
        lines.extend(_emit_edge(emitter, target, blocks))
    return lines


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
    *,
    image_format: str = "com",
    entry_cs: int = 0,
    entry_ip: int | None = None,
    initial_ss: int = 0,
    initial_sp: int = 0xFFFE,
    relocations: Sequence[tuple[int, int]] = (),
) -> str:
    """Emit a complete Xtensa `.S` unit for the supported DOS subset."""
    if image_format not in ("com", "mz"):
        raise BackendError(f"Xtensa assembly backend does not support {image_format}")
    if entry not in blocks:
        raise BackendError("Xtensa assembly backend has no block at the entry point")
    if any(not sequence for sequence in blocks.values()):
        raise BackendError("Xtensa assembly backend cannot emit an empty block")

    if entry_ip is None:
        entry_ip = entry
    image_base = 0x100 if image_format == "com" else 0
    emitter = _Emitter(image_format, load_segment)
    data_fragments = extract_data_fragments(image, blocks, image_base)
    retained_offsets = {
        fragment_offset + index
        for fragment_offset, fragment_data in data_fragments
        for index in range(len(fragment_data))
    }
    retained_relocations: list[tuple[int, int]] = []
    for offset, segment in relocations:
        target = segment * 16 + offset
        retained_bytes = (
            target in retained_offsets,
            target + 1 in retained_offsets,
        )
        if all(retained_bytes):
            retained_relocations.append((offset, segment))
        elif any(retained_bytes):
            raise BackendError(
                "Xtensa assembly backend cannot partially retain an MZ relocation"
            )
    relocations = tuple(retained_relocations)
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
                *_emit_store_ip(emitter, leader),
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
                if instruction.indirect_targets:
                    body.extend(_emit_indirect_jump(emitter, instruction, blocks))
                else:
                    body.extend(
                        _emit_edge(emitter, _direct_target(instruction), blocks)
                    )
                terminated = True
            elif mnemonic == "hlt":
                if index != len(block) - 1:
                    raise _error(instruction, "requires HLT to end its block")
                body.extend(
                    _emit_store_ip(emitter, instruction.next_address)
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
            elif mnemonic == "sub":
                body.extend(
                    _emit_sub16(
                        emitter,
                        instruction,
                        flag_liveness.live_defined[instruction.address],
                    )
                )
            elif mnemonic == "shl":
                body.extend(
                    _emit_shl16(
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
        "    .extern d2e_native_helper_read8",
        "    .extern d2e_native_helper_read16",
        "    .extern d2e_native_helper_write8",
        "    .extern d2e_native_helper_write16",
        "",
        '    .section .literal.program_region,"a",@progbits',
        "    .align 4",
    ]
    for label, value in emitter.literals:
        lines.extend([f"{label}:", f"    .long 0x{value:08x}"])
    dispatch = [
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
    ]
    if image_format == "com":
        dispatch.extend(
            [
            "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + (D2E_ASM_X86_CS_INDEX * 2)",
            f"    l32r a5, {load_literal}",
            "    bne a4, a5, .Lprogram_region_unknown",
            "    l16ui a4, a2, D2E_ASM_CPU_IP_OFFSET",
            ]
        )
    else:
        dispatch.extend(
            [
                (
                    "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
                    "(D2E_ASM_X86_CS_INDEX * 2)"
                ),
                f"    l32r a5, {load_literal}",
                "    sub a4, a4, a5",
                "    extui a4, a4, 0, 16",
                "    slli a4, a4, 4",
                "    l16ui a5, a2, D2E_ASM_CPU_IP_OFFSET",
                "    add a4, a4, a5 /* module target */",
            ]
        )
    lines.extend(dispatch)
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
    if relocations:
        lines.extend(
            [
                '    .section .rodata.d2e_generated_relocations,"a",@progbits',
                "    .align 2",
                ".Lprogram_relocations:",
            ]
        )
        for offset, segment in relocations:
            lines.extend(
                [
                    f"    .short 0x{offset & 0xFFFF:04x}",
                    f"    .short 0x{segment & 0xFFFF:04x}",
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
            (
                "    .long 0 /* D2E_NATIVE_IMAGE_COM */"
                if image_format == "com"
                else "    .long 1 /* D2E_NATIVE_IMAGE_MZ */"
            ),
            f"    .short 0x{load_segment & 0xFFFF:04x}",
            f"    .short 0x{entry_cs & 0xFFFF:04x} /* entry_cs */",
            f"    .short 0x{entry_ip & 0xFFFF:04x} /* entry_ip */",
            f"    .short 0x{initial_ss & 0xFFFF:04x} /* initial_ss */",
            f"    .short 0x{initial_sp & 0xFFFF:04x} /* initial_sp */",
            "    .short 0 /* pointer alignment */",
            "    .long 0 /* full image omitted */",
            f"    .long {len(image)}",
            (
                "    .long .Lprogram_relocations"
                if relocations
                else "    .long 0 /* relocations */"
            ),
            f"    .long {len(relocations)} /* relocation_count */",
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
