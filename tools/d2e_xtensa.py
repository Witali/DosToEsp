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
        if source[0] == "reg" and source[1] in SEGMENT_INDICES:
            segment_index = SEGMENT_INDICES[str(source[1])]
            return [
                (
                    "    l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
                    f"({segment_index} * 2)"
                ),
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

    if destination[0] == "reg" and destination[1] in SEGMENT_INDICES:
        if destination[1] == "cs":
            raise _error(instruction, "cannot write CS with MOV")
        destination_index = SEGMENT_INDICES[str(destination[1])]
        if source[0] == "reg" and source[1] in REG16_OFFSETS:
            source_offset = REG16_OFFSETS[str(source[1])]
            return [
                f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}",
                (
                    "    s16i a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
                    f"({destination_index} * 2)"
                ),
            ]
        if source[0] == "mem":
            memory = _memory_operand(instruction, source, 16)
            return [
                *_emit_memory_arguments(emitter, instruction, memory),
                "    call8 d2e_native_helper_read16",
                (
                    "    s16i a10, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
                    f"({destination_index} * 2)"
                ),
            ]
        raise _error(
            instruction,
            "currently supports only register/memory MOV sources for segments",
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
        elif (
            source[0] == "reg"
            and width == 16
            and source[1] in SEGMENT_INDICES
        ):
            segment_index = SEGMENT_INDICES[str(source[1])]
            lines.append(
                "    l16ui a13, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
                f"({segment_index} * 2)"
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


def _binary_operand_width(instruction: Any, operand: tuple[Any, Any]) -> int:
    if operand[0] == "reg" and operand[1] in REG8_OFFSETS:
        return 8
    if operand[0] == "reg" and operand[1] in REG16_OFFSETS:
        return 16
    if operand[0] == "mem" and int(getattr(operand[1], "width", 0)) in (8, 16):
        return int(getattr(operand[1], "width"))
    raise _error(instruction, "requires an 8/16-bit binary operand")


def _emit_nonmemory_value(
    emitter: _Emitter,
    instruction: Any,
    operand: tuple[Any, Any],
    width: int,
    target_register: str,
) -> list[str]:
    register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
    load = "l8ui" if width == 8 else "l16ui"
    if operand[0] == "reg" and operand[1] in register_offsets:
        offset = register_offsets[str(operand[1])]
        return [
            f"    {load} {target_register}, a2, D2E_ASM_CPU_REGS_OFFSET + {offset}"
        ]
    if operand[0] == "imm":
        mask = 0xFF if width == 8 else 0xFFFF
        literal = emitter.literal(int(operand[1]) & mask, "immediate")
        return [f"    l32r {target_register}, {literal}"]
    raise _error(instruction, "uses mismatched or unsupported binary operands")


def _emit_binary_values(
    emitter: _Emitter,
    instruction: Any,
    left: tuple[Any, Any],
    right: tuple[Any, Any],
    width: int,
) -> list[str]:
    if left[0] == "mem" and right[0] == "mem":
        raise _error(instruction, "cannot use two memory operands")
    if right[0] == "mem":
        memory = _memory_operand(instruction, right, width)
        return [
            *_emit_memory_arguments(emitter, instruction, memory),
            f"    call8 d2e_native_helper_read{width}",
            "    mov a5, a10",
            *_emit_nonmemory_value(emitter, instruction, left, width, "a4"),
        ]
    lines: list[str] = []
    if left[0] == "mem":
        memory = _memory_operand(instruction, left, width)
        lines.extend(
            [
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_read{width}",
                "    mov a4, a10",
            ]
        )
    else:
        lines.extend(
            _emit_nonmemory_value(emitter, instruction, left, width, "a4")
        )
    lines.extend(_emit_nonmemory_value(emitter, instruction, right, width, "a5"))
    return lines


def _emit_cmp16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand CMP")
    left, right = instruction.operands
    width = _binary_operand_width(instruction, left)
    if live_flags == 0:
        return ["    /* CMP result and all flags are dead. */"]

    lines = _emit_binary_values(emitter, instruction, left, right, width)
    if live_flags & ~(d2e_flags.CF | d2e_flags.ZF):
        lines.extend(
            [
                "    mov a10, a2",
                "    mov a11, a4",
                "    mov a12, a5",
                f"    call8 d2e_x86_sub{width} /* CMP result discarded */",
            ]
        )
    else:
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


def _emit_near_call(emitter: _Emitter, instruction: Any) -> list[str]:
    _direct_target(instruction)
    completed = emitter.local("call_push_completed")
    return_literal = emitter.literal(instruction.next_address, "call_return")
    load_literal = emitter.literal(emitter.load_segment, "load_segment")
    return [
        "    mov a10, a2",
        f"    l32r a11, {return_literal}",
        f"    l32r a12, {load_literal}",
        "    call8 d2e_native_helper_push_near_return",
        "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
        f"    beqz a4, {completed}",
        "    j .Lprogram_region_finish",
        f"{completed}:",
    ]


def _emit_near_return(emitter: _Emitter, instruction: Any) -> list[str]:
    if not instruction.operands:
        cleanup = 0
    elif len(instruction.operands) == 1 and instruction.operands[0][0] == "imm":
        cleanup = int(instruction.operands[0][1]) & 0xFFFF
    else:
        raise _error(instruction, "requires no operand or an immediate cleanup")

    lines = [
        "    mov a10, a2",
        "    call8 d2e_x86_pop16",
        "    s16i a10, a2, D2E_ASM_CPU_IP_OFFSET",
    ]
    if cleanup:
        lines.append(
            f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS['sp']}"
        )
        if cleanup <= 127:
            lines.append(f"    addi a4, a4, {cleanup}")
        else:
            cleanup_literal = emitter.literal(cleanup, "return_cleanup")
            lines.extend(
                [f"    l32r a5, {cleanup_literal}", "    add a4, a4, a5"]
            )
        lines.extend(
            [
                "    extui a4, a4, 0, 16",
                (
                    "    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + "
                    f"{REG16_OFFSETS['sp']}"
                ),
            ]
        )
    return lines


def _emit_stack_push(emitter: _Emitter, instruction: Any) -> list[str]:
    if len(instruction.operands) != 1:
        raise _error(instruction, "requires one PUSH operand")
    source = instruction.operands[0]
    lines = ["    mov a10, a2"]
    if source[0] == "reg" and source[1] in REG16_OFFSETS:
        source_offset = REG16_OFFSETS[str(source[1])]
        lines.append(
            f"    l16ui a11, a2, D2E_ASM_CPU_REGS_OFFSET + {source_offset}"
        )
        if source[1] == "sp":
            lines.extend(
                [
                    "    addi a11, a11, -2 /* 8086 PUSH SP value */",
                    "    extui a11, a11, 0, 16",
                ]
            )
    elif source[0] == "reg" and source[1] in SEGMENT_INDICES:
        segment_index = SEGMENT_INDICES[str(source[1])]
        lines.append(
            "    l16ui a11, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            f"({segment_index} * 2)"
        )
    elif source[0] == "mem":
        memory = _memory_operand(instruction, source, 16)
        lines = [
            *_emit_memory_arguments(emitter, instruction, memory),
            "    call8 d2e_native_helper_read16",
            "    mov a11, a10",
            "    mov a10, a2",
        ]
    else:
        raise _error(
            instruction,
            "currently supports only register, segment, and memory PUSH operands",
        )
    completed = emitter.local("stack_push_completed")
    lines.extend(
        [
            "    call8 d2e_x86_push16",
            "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
            f"    beqz a4, {completed}",
            "    j .Lprogram_region_finish",
            f"{completed}:",
        ]
    )
    return lines


def _emit_stack_pop(emitter: _Emitter, instruction: Any) -> list[str]:
    if len(instruction.operands) != 1:
        raise _error(instruction, "requires one POP operand")
    destination = instruction.operands[0]
    lines = ["    mov a10, a2", "    call8 d2e_x86_pop16"]
    if destination[0] == "reg" and destination[1] in REG16_OFFSETS:
        destination_offset = REG16_OFFSETS[str(destination[1])]
        lines.append(
            f"    s16i a10, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    elif (
        destination[0] == "reg"
        and destination[1] in SEGMENT_INDICES
        and destination[1] != "cs"
    ):
        segment_index = SEGMENT_INDICES[str(destination[1])]
        lines.append(
            "    s16i a10, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            f"({segment_index} * 2)"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, 16)
        completed = emitter.local("stack_pop_write_completed")
        lines.extend(
            [
                "    mov a13, a10",
                *_emit_memory_arguments(emitter, instruction, memory),
                "    call8 d2e_native_helper_write16",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    else:
        raise _error(
            instruction,
            "currently supports only register, segment, and memory POP operands",
        )
    return lines


def _emit_push_flags(emitter: _Emitter, instruction: Any) -> list[str]:
    if instruction.operands:
        raise _error(instruction, "requires operand-free PUSHF")
    completed = emitter.local("push_flags_completed")
    return [
        "    mov a10, a2",
        "    l16ui a11, a2, D2E_ASM_CPU_FLAGS_OFFSET",
        "    movi a4, D2E_ASM_X86_FLAG_FIXED",
        "    or a11, a11, a4",
        "    call8 d2e_x86_push16",
        "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
        f"    beqz a4, {completed}",
        "    j .Lprogram_region_finish",
        f"{completed}:",
    ]


def _emit_pop_flags(emitter: _Emitter, instruction: Any) -> list[str]:
    if instruction.operands:
        raise _error(instruction, "requires operand-free POPF")
    mask_literal = emitter.literal(0x0FD5, "pop_flags_mask")
    return [
        "    mov a10, a2",
        "    call8 d2e_x86_pop16",
        f"    l32r a4, {mask_literal}",
        "    and a10, a10, a4",
        "    movi a4, D2E_ASM_X86_FLAG_FIXED",
        "    or a10, a10, a4",
        "    s16i a10, a2, D2E_ASM_CPU_FLAGS_OFFSET",
    ]


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


def _emit_dispatch_tree(
    emitter: _Emitter,
    leaders: Sequence[int],
    leader_literals: Mapping[int, str],
) -> list[str]:
    """Emit bounded address comparisons without a retained guest jump table."""
    if not leaders:
        return ["    j .Lprogram_region_unknown"]
    if len(leaders) <= 16:
        lines: list[str] = []
        for leader in leaders:
            lines.extend(
                [
                    f"    l32r a5, {leader_literals[leader]}",
                    f"    beq a4, a5, {_block_label(leader)}",
                ]
            )
        lines.append("    j .Lprogram_region_unknown")
        return lines

    middle = len(leaders) // 2
    leader = leaders[middle]
    left = leaders[:middle]
    right = leaders[middle + 1 :]
    lines = [
        f"    l32r a5, {leader_literals[leader]}",
        f"    beq a4, a5, {_block_label(leader)}",
    ]
    if left and right:
        dispatch_left = emitter.local("dispatch_left")
        lines.append(f"    bltu a4, a5, {dispatch_left}")
        lines.extend(_emit_dispatch_tree(emitter, right, leader_literals))
        lines.append(f"{dispatch_left}:")
        lines.extend(_emit_dispatch_tree(emitter, left, leader_literals))
    elif left:
        dispatch_left = emitter.local("dispatch_left")
        lines.extend(
            [
                f"    bltu a4, a5, {dispatch_left}",
                "    j .Lprogram_region_unknown",
                f"{dispatch_left}:",
            ]
        )
        lines.extend(_emit_dispatch_tree(emitter, left, leader_literals))
    elif right:
        dispatch_right = emitter.local("dispatch_right")
        lines.extend(
            [
                f"    bgeu a4, a5, {dispatch_right}",
                "    j .Lprogram_region_unknown",
                f"{dispatch_right}:",
            ]
        )
        lines.extend(_emit_dispatch_tree(emitter, right, leader_literals))
    else:
        lines.append("    j .Lprogram_region_unknown")
    return lines


def _emit_hash_dispatch(
    emitter: _Emitter,
    leaders: Sequence[int],
    leader_literals: Mapping[int, str],
) -> tuple[list[str], list[str], int, int]:
    """Emit checked hash buckets and return code, labels, shift, and max load."""
    if not leaders:
        return ["    j .Lprogram_region_unknown"], [], 0, 0
    if len(leaders) <= 16:
        return (
            _emit_dispatch_tree(emitter, leaders, leader_literals),
            [],
            0,
            len(leaders),
        )

    minimum_buckets = (len(leaders) + 9) // 10
    bucket_count = 1
    while bucket_count < minimum_buckets and bucket_count < 128:
        bucket_count *= 2
    bucket_count = min(bucket_count, 128)

    best_shift = 1
    best_buckets: list[list[int]] = []
    best_score: tuple[int, int] | None = None
    for shift in range(1, 17):
        buckets = [[] for _ in range(bucket_count)]
        for leader in leaders:
            bucket = (leader ^ (leader >> shift)) & (bucket_count - 1)
            buckets[bucket].append(leader)
        loads = [len(bucket) for bucket in buckets]
        score = (max(loads), sum(load * load for load in loads))
        if best_score is None or score < best_score:
            best_shift = shift
            best_buckets = buckets
            best_score = score

    bucket_labels = [emitter.local("dispatch_bucket") for _ in best_buckets]
    bucket_bits = (bucket_count - 1).bit_length()
    lines = [
        f"    srli a5, a4, {best_shift}",
        "    xor a5, a5, a4",
        f"    extui a5, a5, 0, {bucket_bits}",
        "    slli a5, a5, 2",
        "    l32r a8, .Lprogram_region_dispatch_bucket_table_pointer",
        "    add a5, a5, a8",
        "    l32i a5, a5, 0",
        "    jx a5",
    ]
    for label, bucket in zip(bucket_labels, best_buckets, strict=True):
        lines.append(f"{label}:")
        for leader in bucket:
            lines.extend(
                [
                    f"    l32r a5, {leader_literals[leader]}",
                    f"    beq a4, a5, {_block_label(leader)}",
                ]
            )
        lines.append("    j .Lprogram_region_unknown")
    maximum_load = best_score[0] if best_score is not None else 0
    return lines, bucket_labels, best_shift, maximum_load


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


def native_block_leaders(
    blocks: Mapping[int, Sequence[Any]],
    image_format: str,
    load_segment: int,
) -> frozenset[int]:
    """Return blocks fully supported by the direct assembly lowerings."""
    liveness = d2e_flags.analyze(blocks)
    supported: set[int] = set()
    for leader, sequence in blocks.items():
        emitter = _Emitter(image_format, load_segment)
        try:
            for index, instruction in enumerate(sequence):
                mnemonic = instruction.mnemonic
                live = liveness.live_defined[instruction.address]
                if mnemonic in d2e_flags.CONDITION_READS:
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires a branch to end its block")
                    _emit_condition(emitter, instruction, emitter.local("taken"))
                    _direct_target(instruction)
                elif mnemonic == "jmp":
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires JMP to end its block")
                    if instruction.indirect_targets:
                        _emit_indirect_jump(emitter, instruction, blocks)
                    else:
                        _direct_target(instruction)
                elif mnemonic == "call":
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires CALL to end its block")
                    _emit_near_call(emitter, instruction)
                elif mnemonic == "ret":
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires RET to end its block")
                    _emit_near_return(emitter, instruction)
                elif mnemonic == "push":
                    _emit_stack_push(emitter, instruction)
                elif mnemonic == "pop":
                    _emit_stack_pop(emitter, instruction)
                elif mnemonic == "pushf":
                    _emit_push_flags(emitter, instruction)
                elif mnemonic == "popf":
                    _emit_pop_flags(emitter, instruction)
                elif mnemonic == "hlt":
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires HLT to end its block")
                elif mnemonic == "mov":
                    _emit_mov(emitter, instruction)
                elif mnemonic == "add":
                    _emit_add16(emitter, instruction, live)
                elif mnemonic == "cmp":
                    _emit_cmp16(emitter, instruction, live)
                elif mnemonic == "sub":
                    _emit_sub16(emitter, instruction, live)
                elif mnemonic == "shl":
                    _emit_shl16(instruction, live)
                elif mnemonic == "mul":
                    _emit_mul16(emitter, instruction, live)
                elif mnemonic == "nop" and not instruction.operands:
                    pass
                else:
                    raise _error(instruction, "does not have a direct lowering")
        except BackendError:
            continue
        supported.add(leader)
    return frozenset(supported)


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
    fallback_blocks: frozenset[int] = frozenset(),
    fallback_symbol: str | None = None,
) -> str:
    """Emit a complete Xtensa `.S` unit for the supported DOS subset."""
    if image_format not in ("com", "mz"):
        raise BackendError(f"Xtensa assembly backend does not support {image_format}")
    if entry not in blocks:
        raise BackendError("Xtensa assembly backend has no block at the entry point")
    if any(not sequence for sequence in blocks.values()):
        raise BackendError("Xtensa assembly backend cannot emit an empty block")
    if not fallback_blocks.issubset(blocks):
        raise BackendError("Xtensa fallback block set contains an unknown leader")
    if fallback_blocks and not fallback_symbol:
        raise BackendError("Xtensa fallback blocks require a helper symbol")

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
    native_blocks = {
        leader: sequence
        for leader, sequence in blocks.items()
        if leader not in fallback_blocks
    }
    load_literal = emitter.literal(load_segment, "load_segment")
    leader_literals = {
        leader: emitter.literal(leader, "leader")
        for leader in sorted(native_blocks)
    }
    body: list[str] = []
    for leader in sorted(native_blocks):
        block = list(blocks[leader])
        execute = emitter.local("execute_block")
        body.extend(
            [
                f"{_block_label(leader)}:",
                f"    bltu a6, a3, {execute}",
                f"    l32r a4, {leader_literals[leader]}",
                "    j .Lprogram_region_budget_finish",
                f"{execute}:",
            ]
        )
        body.append("    addi a6, a6, 1")
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
                body.extend(
                    _emit_edge(emitter, instruction.next_address, native_blocks)
                )
                body.append(f"{taken}:")
                body.extend(
                    _emit_edge(
                        emitter, _direct_target(instruction), native_blocks
                    )
                )
                terminated = True
            elif mnemonic == "jmp":
                if index != len(block) - 1:
                    raise _error(instruction, "requires JMP to end its block")
                body.extend(_emit_retired(emitter, len(block)))
                if instruction.indirect_targets:
                    body.extend(
                        _emit_indirect_jump(
                            emitter, instruction, native_blocks
                        )
                    )
                else:
                    body.extend(
                        _emit_edge(
                            emitter,
                            _direct_target(instruction),
                            native_blocks,
                        )
                    )
                terminated = True
            elif mnemonic == "call":
                if index != len(block) - 1:
                    raise _error(instruction, "requires CALL to end its block")
                body.extend(_emit_near_call(emitter, instruction))
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(
                    _emit_edge(
                        emitter,
                        _direct_target(instruction),
                        native_blocks,
                    )
                )
                terminated = True
            elif mnemonic == "ret":
                if index != len(block) - 1:
                    raise _error(instruction, "requires RET to end its block")
                body.extend(_emit_near_return(emitter, instruction))
                body.extend(_emit_retired(emitter, len(block)))
                body.append("    j .Lprogram_region_dispatch")
                terminated = True
            elif mnemonic == "push":
                body.extend(_emit_stack_push(emitter, instruction))
            elif mnemonic == "pop":
                body.extend(_emit_stack_pop(emitter, instruction))
            elif mnemonic == "pushf":
                body.extend(_emit_push_flags(emitter, instruction))
            elif mnemonic == "popf":
                body.extend(_emit_pop_flags(emitter, instruction))
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
            body.extend(
                _emit_edge(
                    emitter, block[-1].next_address, native_blocks
                )
            )

    (
        hash_dispatch,
        dispatch_bucket_labels,
        dispatch_hash_shift,
        dispatch_hash_maximum_load,
    ) = _emit_hash_dispatch(
        emitter, tuple(sorted(native_blocks)), leader_literals
    )

    lines = [
        "/* Generated by tools/d2e_translate.py --backend xtensa-asm. Do not edit. */",
        '#include "d2e/native_asm_offsets.h"',
        "    .extern d2e_native_helper_mul16",
        "    .extern d2e_native_helper_push_near_return",
        "    .extern d2e_x86_pop16",
        "    .extern d2e_x86_push16",
        "    .extern d2e_x86_sub8",
        "    .extern d2e_x86_sub16",
        "    .extern d2e_native_helper_read8",
        "    .extern d2e_native_helper_read16",
        "    .extern d2e_native_helper_write8",
        "    .extern d2e_native_helper_write16",
        "",
        '    .section .literal.program_region,"a",@progbits',
        "    .align 4",
    ]
    if fallback_symbol is not None:
        lines.insert(7, f"    .extern {fallback_symbol}")
    for label, value in emitter.literals:
        lines.extend([f"{label}:", f"    .long 0x{value:08x}"])
    if dispatch_bucket_labels:
        lines.extend(
            [
                ".Lprogram_region_dispatch_bucket_table_pointer:",
                "    .long .Lprogram_region_dispatch_bucket_table",
                "",
                '    .section .rodata.d2e_generated_dispatch,"a",@progbits',
                "    .align 4",
                ".Lprogram_region_dispatch_bucket_table:",
            ]
        )
        for bucket_label in dispatch_bucket_labels:
            lines.append(f"    .long {bucket_label}")
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
    if dispatch_bucket_labels:
        dispatch.append(
            "    /* Hash dispatch: "
            f"{len(dispatch_bucket_labels)} buckets, shift {dispatch_hash_shift}, "
            f"maximum load {dispatch_hash_maximum_load}. */"
        )
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
    lines.extend(hash_dispatch)
    lines.extend(body)
    unknown: list[str] = [".Lprogram_region_unknown:"]
    if fallback_symbol is not None:
        unknown.extend(
            [
                "    bltu a6, a3, .Lprogram_region_fallback_execute",
                "    j .Lprogram_region_finish",
                ".Lprogram_region_fallback_execute:",
                "    mov a10, a2",
                "    mov a11, a7",
                f"    call8 {fallback_symbol}",
                "    mov a4, a10 /* packed retired delta and success bit */",
                "    extui a10, a4, 0, 1",
                "    srli a7, a4, 1",
                "    add a6, a6, a10",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                "    bnez a4, .Lprogram_region_finish",
                "    bnez a10, .Lprogram_region_dispatch",
            ]
        )
    lines.extend(unknown)
    lines.append("    j .Lprogram_region_untranslated")
    lines.append(".Lprogram_region_budget_finish:")
    if image_format == "mz":
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
    lines.extend(
        [
            "    s16i a4, a2, D2E_ASM_CPU_IP_OFFSET",
            "    j .Lprogram_region_finish",
        ]
    )
    lines.extend(
        [
            ".Lprogram_region_untranslated:",
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
