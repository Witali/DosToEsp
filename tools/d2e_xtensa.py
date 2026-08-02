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
        self._literal_labels: dict[int, str] = {}
        self.local_count = 0
        self.image_format = image_format
        self.load_segment = load_segment

    def literal(self, value: int, purpose: str) -> str:
        value &= 0xFFFFFFFF
        existing = self._literal_labels.get(value)
        if existing is not None:
            return existing
        label = f".Lprogram_region_{purpose}_{len(self.literals)}"
        self.literals.append((label, value))
        self._literal_labels[value] = label
        return label

    def local(self, purpose: str) -> str:
        label = f".Lprogram_region_{purpose}_{self.local_count}"
        self.local_count += 1
        return label


def _emit_load_constant(
    emitter: _Emitter,
    target_register: str,
    value: int,
    purpose: str,
) -> list[str]:
    """Load an exact 32-bit value without allocating an avoidable literal."""
    value &= 0xFFFFFFFF
    if value <= 2047:
        return [f"    movi {target_register}, {value}"]
    if value >= 0xFFFFF800:
        return [f"    movi {target_register}, {value - 0x100000000}"]
    literal = emitter.literal(value, purpose)
    return [f"    l32r {target_register}, {literal}"]


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
    lines = [
        "    mov a10, a2",
        (
            "    l16ui a11, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            f"({SEGMENT_INDICES[segment]} * 2)"
        ),
    ]
    lines.extend(
        _emit_load_constant(
            emitter,
            "a12",
            int(getattr(memory, "displacement", 0)) & 0xFFFF,
            "memory_offset",
        )
    )
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
            return [
                *_emit_load_constant(
                    emitter, "a4", int(source[1]) & 0xFFFF, "immediate"
                ),
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
            return [
                *_emit_load_constant(
                    emitter, "a4", int(source[1]) & 0xFF, "immediate"
                ),
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
            lines.extend(
                _emit_load_constant(
                    emitter, "a13", int(source[1]) & mask, "immediate"
                )
            )
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
        lines.extend(
            _emit_load_constant(emitter, "a12", live_flags, "live_flags")
        )
    lines.append("    call8 d2e_native_helper_mul16")
    return lines


def _emit_add16(emitter: _Emitter, instruction: Any, live_flags: int) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand ADD")
    destination, source = instruction.operands
    width = _binary_operand_width(instruction, destination)
    direct_flags = (live_flags & ~(d2e_flags.CF | d2e_flags.ZF)) == 0
    immediate_add: int | None = None
    if (
        direct_flags
        and (live_flags & d2e_flags.CF) == 0
        and destination[0] == "reg"
        and source[0] == "imm"
    ):
        value = int(source[1]) & 0xFFFF
        signed = value if value < 0x8000 else value - 0x10000
        if -128 <= signed <= 127:
            immediate_add = signed
    if immediate_add is not None:
        lines = _emit_nonmemory_value(
            emitter, instruction, destination, width, "a4"
        )
    else:
        lines = _emit_binary_values(
            emitter, instruction, destination, source, width
        )

    if direct_flags:
        if immediate_add is not None:
            lines.append(f"    addi a4, a4, {immediate_add}")
        else:
            lines.append("    add a4, a4, a5")
        lines.append(f"    extui a4, a4, 0, {width}")
        if live_flags:
            lines.extend(_emit_add_flags(emitter, "a4", "a5", live_flags))
        result_register = "a4"
    else:
        lines.extend(
            [
                "    mov a10, a2",
                "    mov a11, a4",
                "    mov a12, a5",
                f"    call8 d2e_x86_add{width}",
            ]
        )
        result_register = "a10"

    if destination[0] == "reg":
        register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
        if destination[1] not in register_offsets:
            raise _error(instruction, "uses a mismatched ADD destination")
        destination_offset = register_offsets[str(destination[1])]
        store = "s8i" if width == 8 else "s16i"
        lines.append(
            f"    {store} {result_register}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, width)
        completed = emitter.local("add_write_completed")
        lines.extend(
            [
                f"    mov a13, {result_register}",
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    else:
        raise _error(instruction, "requires a register or memory ADD destination")
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


def _emit_add_flags(
    emitter: _Emitter,
    result_register: str,
    right_register: str,
    live_flags: int,
) -> list[str]:
    lines = [
        "    l16ui a8, a2, D2E_ASM_CPU_FLAGS_OFFSET",
        f"    movi a9, {-1 - live_flags}",
        "    and a8, a8, a9",
    ]
    if live_flags & d2e_flags.CF:
        carry_done = emitter.local("add_carry_done")
        lines.extend(
            [
                f"    bgeu {result_register}, {right_register}, {carry_done}",
                f"    movi a9, {d2e_flags.CF}",
                "    or a8, a8, a9",
                f"{carry_done}:",
            ]
        )
    if live_flags & d2e_flags.ZF:
        zero_done = emitter.local("add_zero_done")
        lines.extend(
            [
                f"    bnez {result_register}, {zero_done}",
                f"    movi a9, {d2e_flags.ZF}",
                "    or a8, a8, a9",
                f"{zero_done}:",
            ]
        )
    lines.append("    s16i a8, a2, D2E_ASM_CPU_FLAGS_OFFSET")
    return lines


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
        value = int(operand[1]) & mask
        return _emit_load_constant(emitter, target_register, value, "immediate")
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
    width = _binary_operand_width(instruction, destination)
    direct_flags = (live_flags & ~(d2e_flags.CF | d2e_flags.ZF)) == 0
    immediate_add: int | None = None
    if (
        direct_flags
        and (live_flags & d2e_flags.CF) == 0
        and source[0] == "imm"
    ):
        mask = 0xFF if width == 8 else 0xFFFF
        sign_bit = 1 << (width - 1)
        value = (-int(source[1])) & mask
        signed = value if value < sign_bit else value - (mask + 1)
        if -128 <= signed <= 127:
            immediate_add = signed

    if immediate_add is not None:
        if destination[0] == "reg":
            lines = _emit_nonmemory_value(
                emitter, instruction, destination, width, "a4"
            )
        elif destination[0] == "mem":
            memory = _memory_operand(instruction, destination, width)
            lines = [
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_read{width}",
                "    mov a4, a10",
            ]
        else:
            raise _error(
                instruction, "requires a register or memory SUB destination"
            )
    else:
        lines = _emit_binary_values(
            emitter, instruction, destination, source, width
        )

    if direct_flags:
        if immediate_add is not None:
            lines.append(f"    addi a4, a4, {immediate_add}")
            lines.append(f"    extui a4, a4, 0, {width}")
            if live_flags & d2e_flags.ZF:
                lines.extend(_emit_zero_flag(emitter, "a4"))
        else:
            if live_flags:
                lines.extend(
                    _emit_compare_flags(emitter, "a4", "a5", live_flags)
                )
            lines.extend(
                ["    sub a4, a4, a5", f"    extui a4, a4, 0, {width}"]
            )
        result_register = "a4"
    else:
        lines.extend(
            [
                "    mov a10, a2",
                "    mov a11, a4",
                "    mov a12, a5",
                f"    call8 d2e_x86_sub{width}",
            ]
        )
        result_register = "a10"

    if destination[0] == "reg":
        register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
        if destination[1] not in register_offsets:
            raise _error(instruction, "uses a mismatched SUB destination")
        destination_offset = register_offsets[str(destination[1])]
        store = "s8i" if width == 8 else "s16i"
        lines.append(
            f"    {store} {result_register}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, width)
        completed = emitter.local("subtract_write_completed")
        lines.extend(
            [
                f"    mov a13, {result_register}",
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    else:
        raise _error(instruction, "requires a register or memory SUB destination")
    return lines


def _emit_inc_dec(
    emitter: _Emitter,
    instruction: Any,
    live_flags: int,
) -> list[str]:
    if len(instruction.operands) != 1:
        raise _error(instruction, "requires one INC/DEC operand")
    destination = instruction.operands[0]
    width = _binary_operand_width(instruction, destination)
    if destination[0] == "reg":
        lines = _emit_nonmemory_value(
            emitter, instruction, destination, width, "a4"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, width)
        lines = [
            *_emit_memory_arguments(emitter, instruction, memory),
            f"    call8 d2e_native_helper_read{width}",
            "    mov a4, a10",
        ]
    else:
        raise _error(instruction, "requires a register or memory INC/DEC operand")

    if live_flags in (0, d2e_flags.ZF):
        delta = 1 if instruction.mnemonic == "inc" else -1
        lines.extend(
            [f"    addi a4, a4, {delta}", f"    extui a4, a4, 0, {width}"]
        )
        if live_flags == d2e_flags.ZF:
            lines.extend(_emit_zero_flag(emitter, "a4"))
        result_register = "a4"
    else:
        lines.extend(
            [
                "    mov a10, a2",
                "    mov a11, a4",
                f"    call8 d2e_x86_{instruction.mnemonic}{width}",
            ]
        )
        result_register = "a10"

    if destination[0] == "reg":
        register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
        destination_offset = register_offsets[str(destination[1])]
        store = "s8i" if width == 8 else "s16i"
        lines.append(
            f"    {store} {result_register}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    else:
        memory = _memory_operand(instruction, destination, width)
        completed = emitter.local("increment_write_completed")
        lines.extend(
            [
                f"    mov a13, {result_register}",
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    return lines


def _emit_logic_flags(
    emitter: _Emitter,
    result_register: str,
    live_flags: int,
) -> list[str]:
    zero_done = emitter.local("logic_zero_done")
    lines = [
        "    l16ui a8, a2, D2E_ASM_CPU_FLAGS_OFFSET",
    ]
    clear_mask = -1 - live_flags
    if clear_mask >= -2048:
        lines.append(f"    movi a9, {clear_mask}")
    else:
        mask_literal = emitter.literal(clear_mask, "logic_flags_mask")
        lines.append(f"    l32r a9, {mask_literal}")
    lines.append("    and a8, a8, a9")
    if live_flags & d2e_flags.ZF:
        lines.extend(
            [
                f"    bnez {result_register}, {zero_done}",
                f"    movi a9, {d2e_flags.ZF}",
                "    or a8, a8, a9",
                f"{zero_done}:",
            ]
        )
    lines.append("    s16i a8, a2, D2E_ASM_CPU_FLAGS_OFFSET")
    return lines


def _emit_logical(
    emitter: _Emitter,
    instruction: Any,
    live_flags: int,
) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a two-operand logical instruction")
    destination, source = instruction.operands
    width = _binary_operand_width(instruction, destination)
    if live_flags == 0 and instruction.mnemonic == "test":
        return ["    /* TEST result and all flags are dead. */"]

    lines = _emit_binary_values(
        emitter, instruction, destination, source, width
    )
    operation = {
        "and": "and",
        "or": "or",
        "xor": "xor",
        "test": "and",
    }[instruction.mnemonic]
    lines.extend(
        [
            f"    {operation} a4, a4, a5",
            f"    extui a4, a4, 0, {width}",
        ]
    )
    direct_mask = d2e_flags.CF | d2e_flags.ZF | d2e_flags.OF
    if (live_flags & ~direct_mask) == 0:
        if live_flags:
            lines.extend(_emit_logic_flags(emitter, "a4", live_flags))
        result_register = "a4"
    else:
        lines.extend(
            [
                "    mov a10, a2",
                "    mov a11, a4",
                f"    call8 d2e_x86_logic{width}",
            ]
        )
        result_register = "a10"

    if instruction.mnemonic == "test":
        return lines
    if destination[0] == "reg":
        register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
        if destination[1] not in register_offsets:
            raise _error(instruction, "uses a mismatched logical destination")
        destination_offset = register_offsets[str(destination[1])]
        store = "s8i" if width == 8 else "s16i"
        lines.append(
            f"    {store} {result_register}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, width)
        completed = emitter.local("logical_write_completed")
        lines.extend(
            [
                f"    mov a13, {result_register}",
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    else:
        raise _error(instruction, "requires a register or memory logical destination")
    return lines


def _emit_not(emitter: _Emitter, instruction: Any) -> list[str]:
    if len(instruction.operands) != 1:
        raise _error(instruction, "requires one NOT operand")
    destination = instruction.operands[0]
    width = _binary_operand_width(instruction, destination)
    if destination[0] == "reg":
        lines = _emit_nonmemory_value(
            emitter, instruction, destination, width, "a4"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, width)
        lines = [
            *_emit_memory_arguments(emitter, instruction, memory),
            f"    call8 d2e_native_helper_read{width}",
            "    mov a4, a10",
        ]
    else:
        raise _error(instruction, "requires a register or memory NOT operand")
    lines.extend(
        [
            "    movi a5, -1",
            "    xor a4, a4, a5",
            f"    extui a4, a4, 0, {width}",
        ]
    )
    if destination[0] == "reg":
        register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
        destination_offset = register_offsets[str(destination[1])]
        store = "s8i" if width == 8 else "s16i"
        lines.append(
            f"    {store} a4, a2, D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    else:
        memory = _memory_operand(instruction, destination, width)
        completed = emitter.local("not_write_completed")
        lines.extend(
            [
                "    mov a13, a4",
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    return lines


def _emit_flag_control(instruction: Any) -> list[str]:
    if instruction.operands:
        raise _error(instruction, "requires no flag-control operands")
    mnemonic = instruction.mnemonic
    affected = {
        "clc": d2e_flags.CF,
        "cmc": d2e_flags.CF,
        "stc": d2e_flags.CF,
        "cld": d2e_flags.DF,
        "std": d2e_flags.DF,
        "cli": d2e_flags.IF,
        "sti": d2e_flags.IF,
    }
    if mnemonic not in affected:
        raise _error(instruction, "uses an unsupported flag-control instruction")
    flag = affected[mnemonic]
    lines = ["    l16ui a4, a2, D2E_ASM_CPU_FLAGS_OFFSET"]
    if mnemonic == "cmc":
        lines.append(f"    xori a4, a4, {flag}")
    elif mnemonic.startswith("cl"):
        lines.extend([f"    movi a5, {-1 - flag}", "    and a4, a4, a5"])
    else:
        lines.extend([f"    movi a5, {flag}", "    or a4, a4, a5"])
    lines.append("    s16i a4, a2, D2E_ASM_CPU_FLAGS_OFFSET")
    return lines


def _emit_shift_rotate(
    emitter: _Emitter,
    instruction: Any,
    live_flags: int,
) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires a destination and shift count")
    destination, count = instruction.operands
    width = _binary_operand_width(instruction, destination)
    if destination[0] == "reg":
        lines = _emit_nonmemory_value(
            emitter, instruction, destination, width, "a4"
        )
    elif destination[0] == "mem":
        memory = _memory_operand(instruction, destination, width)
        lines = [
            *_emit_memory_arguments(emitter, instruction, memory),
            f"    call8 d2e_native_helper_read{width}",
            "    mov a4, a10",
        ]
    else:
        raise _error(instruction, "requires a register or memory shift destination")

    direct_dead = (
        live_flags == 0
        and count == ("imm", 1)
        and instruction.mnemonic in ("shl", "shr", "sar")
    )
    if direct_dead:
        if instruction.mnemonic == "shl":
            lines.append("    slli a4, a4, 1")
        elif instruction.mnemonic == "shr":
            lines.append("    srli a4, a4, 1")
        else:
            lines.extend(
                [
                    f"    slli a4, a4, {32 - width}",
                    f"    srai a4, a4, {33 - width}",
                ]
            )
        lines.append(f"    extui a4, a4, 0, {width}")
        result_register = "a4"
    else:
        if live_flags == 0:
            raise _error(
                instruction,
                "does not lower dead variable-count shifts through a slower helper",
            )
        lines.extend(["    mov a10, a2", "    mov a11, a4"])
        if count[0] == "imm":
            value = int(count[1]) & 0xFF
            lines.append(f"    movi a12, {value}")
        elif count == ("reg", "cl"):
            lines.append(
                f"    l8ui a12, a2, D2E_ASM_CPU_REGS_OFFSET + {REG8_OFFSETS['cl']}"
            )
        else:
            raise _error(instruction, "requires an immediate or CL shift count")
        lines.append(f"    call8 d2e_x86_{instruction.mnemonic}{width}")
        result_register = "a10"

    if destination[0] == "reg":
        register_offsets = REG8_OFFSETS if width == 8 else REG16_OFFSETS
        destination_offset = register_offsets[str(destination[1])]
        store = "s8i" if width == 8 else "s16i"
        lines.append(
            f"    {store} {result_register}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {destination_offset}"
        )
    else:
        memory = _memory_operand(instruction, destination, width)
        completed = emitter.local("shift_write_completed")
        lines.extend(
            [
                f"    mov a13, {result_register}",
                *_emit_memory_arguments(emitter, instruction, memory),
                f"    call8 d2e_native_helper_write{width}",
                "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
                f"    beqz a4, {completed}",
                "    j .Lprogram_region_finish",
                f"{completed}:",
            ]
        )
    return lines


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


def _emit_interrupt(emitter: _Emitter, instruction: Any) -> list[str]:
    if instruction.mnemonic == "int3":
        if instruction.operands:
            raise _error(instruction, "requires operand-free INT3")
        interrupt_number = 3
    elif instruction.mnemonic == "int":
        interrupt_number = _direct_target(instruction)
        if interrupt_number > 0xFF:
            raise _error(instruction, "requires an 8-bit interrupt number")
    else:
        raise _error(instruction, "requires INT or INT3")

    completed = emitter.local("interrupt_completed")
    return [
        *_emit_store_ip(emitter, instruction.next_address),
        "    mov a10, a2",
        f"    movi a11, {interrupt_number}",
        "    call8 d2e_native_interrupt",
        "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
        f"    beqz a4, {completed}",
        "    j .Lprogram_region_finish",
        f"{completed}:",
    ]


def _emit_port_operand(
    emitter: _Emitter,
    instruction: Any,
    operand: tuple[Any, Any],
    target_register: str,
) -> list[str]:
    if operand[0] == "imm":
        return _emit_load_constant(
            emitter, target_register, int(operand[1]) & 0xFFFF, "port"
        )
    if operand == ("reg", "dx"):
        return [
            f"    l16ui {target_register}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS['dx']}"
        ]
    raise _error(instruction, "requires an immediate port or DX")


def _emit_port_io(emitter: _Emitter, instruction: Any) -> list[str]:
    if len(instruction.operands) != 2:
        raise _error(instruction, "requires two IN/OUT operands")
    first, second = instruction.operands
    completed = emitter.local("port_completed")

    if instruction.mnemonic == "in":
        if first == ("reg", "al"):
            width = 8
        elif first == ("reg", "ax"):
            width = 16
        else:
            raise _error(instruction, "requires AL or AX as the IN destination")
        store = "s8i" if width == 8 else "s16i"
        return [
            "    mov a10, a2",
            *_emit_port_operand(emitter, instruction, second, "a11"),
            f"    call8 d2e_x86_port_in{width}",
            f"    {store} a10, a2, D2E_ASM_CPU_REGS_OFFSET + 0",
            "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
            f"    beqz a4, {completed}",
            "    j .Lprogram_region_finish",
            f"{completed}:",
        ]

    if instruction.mnemonic == "out":
        if second == ("reg", "al"):
            width = 8
        elif second == ("reg", "ax"):
            width = 16
        else:
            raise _error(instruction, "requires AL or AX as the OUT source")
        load = "l8ui" if width == 8 else "l16ui"
        return [
            "    mov a10, a2",
            *_emit_port_operand(emitter, instruction, first, "a11"),
            f"    {load} a12, a2, D2E_ASM_CPU_REGS_OFFSET + 0",
            f"    call8 d2e_x86_port_out{width}",
            "    l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET",
            f"    beqz a4, {completed}",
            "    j .Lprogram_region_finish",
            f"{completed}:",
        ]

    raise _error(instruction, "requires IN or OUT")


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


def _emit_loop_control(
    emitter: _Emitter,
    instruction: Any,
    blocks: Mapping[int, Sequence[Any]],
) -> list[str]:
    target = _direct_target(instruction)
    mnemonic = instruction.mnemonic
    if mnemonic not in ("loop", "loope", "loopne", "jcxz"):
        raise _error(instruction, "uses an unsupported loop-control instruction")
    lines = [
        f"    l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS['cx']}",
    ]
    if mnemonic != "jcxz":
        lines.extend(
            [
                "    addi a4, a4, -1",
                "    extui a4, a4, 0, 16",
                f"    s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS['cx']}",
            ]
        )
    if mnemonic in ("loop", "jcxz"):
        taken = emitter.local("loop_taken")
        branch = "bnez" if mnemonic == "loop" else "beqz"
        lines.append(f"    {branch} a4, {taken}")
        lines.extend(_emit_edge(emitter, instruction.next_address, blocks))
        lines.append(f"{taken}:")
        lines.extend(_emit_edge(emitter, target, blocks))
        return lines

    not_taken = emitter.local("loop_not_taken")
    lines.extend(
        [
            f"    beqz a4, {not_taken}",
            "    l16ui a5, a2, D2E_ASM_CPU_FLAGS_OFFSET",
            f"    movi a8, {d2e_flags.ZF}",
            "    and a5, a5, a8",
        ]
    )
    flag_branch = "beqz" if mnemonic == "loope" else "bnez"
    lines.append(f"    {flag_branch} a5, {not_taken}")
    lines.extend(_emit_edge(emitter, target, blocks))
    lines.append(f"{not_taken}:")
    lines.extend(_emit_edge(emitter, instruction.next_address, blocks))
    return lines


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


def _can_fuse_compare_branch(
    producer: Any,
    branch: Any,
    flag_liveness: d2e_flags.FlagLiveness,
) -> bool:
    """Return whether a CMP/TEST result can feed one terminal branch directly."""
    if producer.mnemonic not in ("cmp", "test"):
        return False
    zero_conditions = {"je", "jz", "jne", "jnz"}
    compare_conditions = {
        "jb",
        "jc",
        "jnae",
        "jae",
        "jnb",
        "jnc",
        *zero_conditions,
        "jbe",
        "jna",
        "ja",
        "jnbe",
    }
    supported = zero_conditions if producer.mnemonic == "test" else compare_conditions
    if branch.mnemonic not in supported:
        return False
    if len(producer.operands) != 2 or any(
        operand[0] == "mem" for operand in producer.operands
    ):
        return False
    defined = d2e_flags.effects(producer).defines
    return (flag_liveness.live_after[branch.address] & defined) == 0


def _emit_compare_branch(
    emitter: _Emitter,
    producer: Any,
    branch: Any,
    taken: str,
) -> list[str]:
    """Branch directly on CMP/TEST operands without materializing x86 FLAGS."""
    left, right = producer.operands
    width = _binary_operand_width(producer, left)
    lines = _emit_binary_values(emitter, producer, left, right, width)
    if producer.mnemonic == "test":
        lines.append("    and a4, a4, a5")
        operation = "beqz" if branch.mnemonic in ("je", "jz") else "bnez"
        lines.append(f"    {operation} a4, {taken}")
        return lines

    if branch.mnemonic in ("je", "jz"):
        lines.append(f"    beq a4, a5, {taken}")
    elif branch.mnemonic in ("jne", "jnz"):
        lines.append(f"    bne a4, a5, {taken}")
    elif branch.mnemonic in ("jb", "jc", "jnae"):
        lines.append(f"    bltu a4, a5, {taken}")
    elif branch.mnemonic in ("jae", "jnb", "jnc"):
        lines.append(f"    bgeu a4, a5, {taken}")
    elif branch.mnemonic in ("jbe", "jna"):
        lines.append(f"    bgeu a5, a4, {taken}")
    elif branch.mnemonic in ("ja", "jnbe"):
        lines.append(f"    bltu a5, a4, {taken}")
    else:
        raise _error(branch, "does not support direct compare fusion")
    return lines


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


_CACHED_XTENSA_REGISTERS = ("a4", "a5", "a8", "a9")


def _cached_register_operation(
    instruction: Any,
    live_flags: int,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Return register reads/writes for a cacheable helper-free operation."""
    operands = instruction.operands
    mnemonic = instruction.mnemonic
    if mnemonic == "mov":
        if (
            len(operands) != 2
            or operands[0][0] != "reg"
            or operands[0][1] not in REG16_OFFSETS
        ):
            return None
        destination = str(operands[0][1])
        source = operands[1]
        if source[0] == "reg" and source[1] in REG16_OFFSETS:
            return (str(source[1]),), (destination,)
        if source[0] == "imm" and (int(source[1]) & 0xFFFF) <= 2047:
            return (), (destination,)
        return None

    if mnemonic in ("add", "sub", "and", "or", "xor"):
        if (
            live_flags != 0
            or len(operands) != 2
            or operands[0][0] != "reg"
            or operands[0][1] not in REG16_OFFSETS
        ):
            return None
        destination = str(operands[0][1])
        source = operands[1]
        if source[0] == "reg" and source[1] in REG16_OFFSETS:
            return (destination, str(source[1])), (destination,)
        if source[0] != "imm":
            return None
        value = int(source[1]) & 0xFFFF
        signed = value if value < 0x8000 else value - 0x10000
        addi_value = signed if mnemonic == "add" else -signed
        if value <= 2047 or (
            mnemonic in ("add", "sub") and -128 <= addi_value <= 127
        ):
            return (destination,), (destination,)
        return None

    if mnemonic in ("inc", "dec", "not"):
        if (
            len(operands) != 1
            or operands[0][0] != "reg"
            or operands[0][1] not in REG16_OFFSETS
            or (mnemonic in ("inc", "dec") and live_flags != 0)
        ):
            return None
        destination = str(operands[0][1])
        return (destination,), (destination,)
    return None


def _cached_baseline_instruction_count(instruction: Any) -> int:
    """Estimate existing direct-lowering instructions for a cacheable op."""
    if instruction.mnemonic == "mov":
        return 2
    if (
        instruction.mnemonic in ("add", "sub")
        and instruction.operands[1][0] == "imm"
    ):
        value = int(instruction.operands[1][1]) & 0xFFFF
        signed = value if value < 0x8000 else value - 0x10000
        addi_value = signed if instruction.mnemonic == "add" else -signed
        if -128 <= addi_value <= 127:
            return 4
    if instruction.mnemonic in ("add", "sub", "and", "or", "xor", "not"):
        return 5
    if instruction.mnemonic in ("inc", "dec"):
        return 4
    raise AssertionError(f"unexpected cached operation: {instruction.mnemonic}")


def _cached_baseline_memory_access_count(instruction: Any) -> int:
    """Count CPU-register loads/stores in the existing direct lowering."""
    if instruction.mnemonic == "mov":
        return 1 if instruction.operands[1][0] == "imm" else 2
    if instruction.mnemonic in ("add", "sub", "and", "or", "xor"):
        return 2 if instruction.operands[1][0] == "imm" else 3
    if instruction.mnemonic in ("inc", "dec", "not"):
        return 2
    raise AssertionError(f"unexpected cached operation: {instruction.mnemonic}")


def _emit_cached_register_operation(
    instruction: Any,
    registers: Mapping[str, str],
) -> list[str]:
    # Supported cached operations preserve the exact low 16 bits even when an
    # arithmetic result is not canonicalized after every instruction. The run
    # ends with S16I stores, so emitting EXTUI here would only add work.
    mnemonic = instruction.mnemonic
    operands = instruction.operands
    destination = str(operands[0][1])
    target = registers[destination]
    if mnemonic == "mov":
        source = operands[1]
        if source[0] == "reg":
            source_register = registers[str(source[1])]
            if source_register == target:
                return []
            return [f"    mov {target}, {source_register}"]
        return [f"    movi {target}, {int(source[1]) & 0xFFFF}"]

    if mnemonic in ("inc", "dec"):
        delta = 1 if mnemonic == "inc" else -1
        return [f"    addi {target}, {target}, {delta}"]
    if mnemonic == "not":
        return [
            "    movi a10, -1",
            f"    xor {target}, {target}, a10",
            f"    extui {target}, {target}, 0, 16",
        ]

    source = operands[1]
    operation = mnemonic
    lines: list[str] = []
    if source[0] == "reg":
        source_register = registers[str(source[1])]
    else:
        value = int(source[1]) & 0xFFFF
        signed = value if value < 0x8000 else value - 0x10000
        addi_value = signed if mnemonic == "add" else -signed
        if mnemonic in ("add", "sub") and -128 <= addi_value <= 127:
            return [f"    addi {target}, {target}, {addi_value}"]
        lines.append(f"    movi a10, {value}")
        source_register = "a10"
    lines.append(f"    {operation} {target}, {target}, {source_register}")
    return lines


def _emit_cached_register_pair(
    first: Any,
    second: Any,
    registers: Mapping[str, str],
) -> list[str] | None:
    """Fuse a cached 16-bit MOV and its dependent operation when possible."""
    if first.mnemonic != "mov" or len(first.operands) != 2:
        return None
    destination, move_source = first.operands
    if (
        destination[0] != "reg"
        or destination[1] not in REG16_OFFSETS
        or move_source[0] != "reg"
        or move_source[1] not in REG16_OFFSETS
    ):
        return None

    destination_name = str(destination[1])
    source_name = str(move_source[1])
    target = registers[destination_name]
    source_register = registers[source_name]
    if not second.operands or second.operands[0] != destination:
        return None

    if second.mnemonic in ("inc", "dec") and len(second.operands) == 1:
        delta = 1 if second.mnemonic == "inc" else -1
        return [f"    addi {target}, {source_register}, {delta}"]

    if (
        second.mnemonic not in ("add", "sub", "and", "or", "xor")
        or len(second.operands) != 2
    ):
        return None
    right = second.operands[1]
    if right[0] == "reg" and right[1] in REG16_OFFSETS:
        right_name = str(right[1])
        if right_name == destination_name:
            right_name = source_name
        return [
            f"    {second.mnemonic} {target}, {source_register}, "
            f"{registers[right_name]}"
        ]
    if right[0] != "imm":
        return None

    value = int(right[1]) & 0xFFFF
    signed = value if value < 0x8000 else value - 0x10000
    if second.mnemonic in ("add", "sub"):
        addi_value = signed if second.mnemonic == "add" else -signed
        if -128 <= addi_value <= 127:
            return [f"    addi {target}, {source_register}, {addi_value}"]
        return None
    if second.mnemonic == "and":
        if value == 0:
            return [f"    movi {target}, 0"]
        if value & (value + 1) == 0:
            return [
                f"    extui {target}, {source_register}, 0, {value.bit_length()}"
            ]
    return None


def _build_cached_register_run(
    instructions: Sequence[Any],
    live_flags: Mapping[int, int],
) -> tuple[list[str], tuple[int, int]] | None:
    """Build a run and return lines plus instruction/memory-access savings."""
    touched: list[str] = []
    live_in: list[str] = []
    dirty: list[str] = []
    written: set[str] = set()
    baseline_count = 0
    baseline_memory_accesses = 0
    for instruction in instructions:
        shape = _cached_register_operation(
            instruction, live_flags[instruction.address]
        )
        if shape is None:
            return None
        reads, writes = shape
        baseline_count += _cached_baseline_instruction_count(instruction)
        baseline_memory_accesses += _cached_baseline_memory_access_count(
            instruction
        )
        for register in (*reads, *writes):
            if register not in touched:
                touched.append(register)
        for register in reads:
            if register not in written and register not in live_in:
                live_in.append(register)
        for register in writes:
            written.add(register)
            if register not in dirty:
                dirty.append(register)
    if len(touched) > len(_CACHED_XTENSA_REGISTERS):
        return None

    registers = dict(zip(touched, _CACHED_XTENSA_REGISTERS, strict=False))
    lines: list[str] = []
    for register in live_in:
        lines.append(
            f"    l16ui {registers[register]}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS[register]}"
        )
    index = 0
    while index < len(instructions):
        instruction = instructions[index]
        lines.append(
            f"    /* {instruction.address:04x}: {instruction.mnemonic} "
            f"{instruction.op_str} */"
        )
        if index + 1 < len(instructions):
            following = instructions[index + 1]
            fused = _emit_cached_register_pair(
                instruction, following, registers
            )
            if fused is not None:
                lines.append(
                    f"    /* {following.address:04x}: {following.mnemonic} "
                    f"{following.op_str}; fused with preceding MOV. */"
                )
                lines.extend(fused)
                index += 2
                continue
        lines.extend(_emit_cached_register_operation(instruction, registers))
        index += 1
    for register in dirty:
        lines.append(
            f"    s16i {registers[register]}, a2, "
            f"D2E_ASM_CPU_REGS_OFFSET + {REG16_OFFSETS[register]}"
        )

    candidate_count = sum(
        line.startswith("    ") and not line.startswith("    /*")
        for line in lines
    )
    saving = (
        baseline_count - candidate_count,
        baseline_memory_accesses - len(live_in) - len(dirty),
    )
    if saving <= (0, 0):
        return None
    bindings = ", ".join(
        f"{register.upper()}={registers[register]}" for register in touched
    )
    lines.insert(
        0,
        (
            f"    /* Register cache: {bindings}; estimated saving "
            f"{saving[0]} instructions, {saving[1]} CPU accesses. */"
        ),
    )
    return lines, saving


def _plan_cached_register_runs(
    instructions: Sequence[Any],
    live_flags: Mapping[int, int],
) -> tuple[dict[int, tuple[int, list[str]]], tuple[int, int]]:
    """Choose non-overlapping cached runs with maximum estimated saving."""
    candidates: dict[int, list[tuple[int, list[str], tuple[int, int]]]] = {}
    for start in range(len(instructions)):
        touched: set[str] = set()
        for end in range(start + 1, len(instructions) + 1):
            instruction = instructions[end - 1]
            shape = _cached_register_operation(
                instruction, live_flags[instruction.address]
            )
            if shape is None:
                break
            touched.update((*shape[0], *shape[1]))
            if len(touched) > len(_CACHED_XTENSA_REGISTERS):
                break
            candidate = _build_cached_register_run(
                instructions[start:end], live_flags
            )
            if candidate is not None:
                lines, score = candidate
                candidates.setdefault(start, []).append((end, lines, score))

    best_score = [(0, 0)] * (len(instructions) + 1)
    best_runs: list[list[tuple[int, int, list[str], tuple[int, int]]]] = [
        [] for _ in range(len(instructions) + 1)
    ]
    for start in range(len(instructions) - 1, -1, -1):
        best_score[start] = best_score[start + 1]
        best_runs[start] = best_runs[start + 1]
        for end, lines, score in candidates.get(start, []):
            total = (
                score[0] + best_score[end][0],
                score[1] + best_score[end][1],
            )
            if total > best_score[start]:
                best_score[start] = total
                best_runs[start] = [
                    (start, end, lines, score),
                    *best_runs[end],
                ]

    selected = {
        start: (end, lines)
        for start, end, lines, _ in best_runs[0]
    }
    return selected, best_score[0]


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
                elif mnemonic in ("loop", "loope", "loopne", "jcxz"):
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires loop control to end its block")
                    _emit_loop_control(emitter, instruction, blocks)
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
                elif mnemonic in ("int", "int3"):
                    if index != len(sequence) - 1:
                        raise _error(instruction, "requires INT to end its block")
                    _emit_interrupt(emitter, instruction)
                elif mnemonic in ("in", "out"):
                    _emit_port_io(emitter, instruction)
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
                elif mnemonic in ("inc", "dec"):
                    _emit_inc_dec(emitter, instruction, live)
                elif mnemonic in ("and", "or", "xor", "test"):
                    _emit_logical(emitter, instruction, live)
                elif mnemonic == "not":
                    _emit_not(emitter, instruction)
                elif mnemonic in ("clc", "cmc", "stc", "cld", "std", "cli", "sti"):
                    _emit_flag_control(instruction)
                elif mnemonic in ("shl", "shr", "sar", "rol", "ror", "rcl", "rcr"):
                    _emit_shift_rotate(emitter, instruction, live)
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
    cached_run_count = 0
    cached_instruction_saving = 0
    cached_memory_saving = 0
    for leader in sorted(native_blocks):
        block = list(blocks[leader])
        cached_runs, block_cached_score = _plan_cached_register_runs(
            block, flag_liveness.live_defined
        )
        cached_run_count += len(cached_runs)
        cached_instruction_saving += block_cached_score[0]
        cached_memory_saving += block_cached_score[1]
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
        cached_until = 0
        fused_compare_index: int | None = None
        if len(block) >= 2 and _can_fuse_compare_branch(
            block[-2], block[-1], flag_liveness
        ):
            fused_compare_index = len(block) - 2
        for index, instruction in enumerate(block):
            if index < cached_until:
                continue
            cached = cached_runs.get(index)
            if cached is not None:
                cached_until, cached_lines = cached
                body.extend(cached_lines)
                continue
            mnemonic = instruction.mnemonic
            body.append(
                f"    /* {instruction.address:04x}: {mnemonic} {instruction.op_str} */"
            )
            if index == fused_compare_index:
                branch = block[index + 1]
                body.append(
                    f"    /* {branch.address:04x}: {branch.mnemonic} "
                    f"{branch.op_str}; fused with preceding {mnemonic.upper()}. */"
                )
                taken = emitter.local("fused_branch_taken")
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(
                    _emit_compare_branch(
                        emitter, instruction, branch, taken
                    )
                )
                body.extend(
                    _emit_edge(emitter, branch.next_address, native_blocks)
                )
                body.append(f"{taken}:")
                body.extend(
                    _emit_edge(
                        emitter, _direct_target(branch), native_blocks
                    )
                )
                terminated = True
                break
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
            elif mnemonic in ("loop", "loope", "loopne", "jcxz"):
                if index != len(block) - 1:
                    raise _error(instruction, "requires loop control to end its block")
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(
                    _emit_loop_control(emitter, instruction, native_blocks)
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
            elif mnemonic in ("int", "int3"):
                if index != len(block) - 1:
                    raise _error(instruction, "requires INT to end its block")
                body.extend(_emit_retired(emitter, len(block)))
                body.extend(_emit_interrupt(emitter, instruction))
                body.extend(
                    _emit_edge(emitter, instruction.next_address, native_blocks)
                )
                terminated = True
            elif mnemonic in ("in", "out"):
                body.extend(_emit_port_io(emitter, instruction))
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
            elif mnemonic in ("inc", "dec"):
                body.extend(
                    _emit_inc_dec(
                        emitter,
                        instruction,
                        flag_liveness.live_defined[instruction.address],
                    )
                )
            elif mnemonic in ("and", "or", "xor", "test"):
                body.extend(
                    _emit_logical(
                        emitter,
                        instruction,
                        flag_liveness.live_defined[instruction.address],
                    )
                )
            elif mnemonic == "not":
                body.extend(_emit_not(emitter, instruction))
            elif mnemonic in ("clc", "cmc", "stc", "cld", "std", "cli", "sti"):
                body.extend(_emit_flag_control(instruction))
            elif mnemonic in ("shl", "shr", "sar", "rol", "ror", "rcl", "rcr"):
                body.extend(
                    _emit_shift_rotate(
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
        (
            f"/* Register-cache selection: {cached_run_count} runs, "
            f"estimated {cached_instruction_saving} Xtensa instructions and "
            f"{cached_memory_saving} CPU accesses saved. */"
        ),
        '#include "d2e/native_asm_offsets.h"',
        "    .extern d2e_native_helper_mul16",
        "    .extern d2e_native_helper_push_near_return",
        "    .extern d2e_native_interrupt",
        "    .extern d2e_x86_port_in8",
        "    .extern d2e_x86_port_in16",
        "    .extern d2e_x86_port_out8",
        "    .extern d2e_x86_port_out16",
        "    .extern d2e_x86_pop16",
        "    .extern d2e_x86_push16",
        "    .extern d2e_x86_add8",
        "    .extern d2e_x86_add16",
        "    .extern d2e_x86_sub8",
        "    .extern d2e_x86_sub16",
        "    .extern d2e_x86_inc8",
        "    .extern d2e_x86_inc16",
        "    .extern d2e_x86_dec8",
        "    .extern d2e_x86_dec16",
        "    .extern d2e_x86_logic8",
        "    .extern d2e_x86_logic16",
        "    .extern d2e_x86_shl8",
        "    .extern d2e_x86_shl16",
        "    .extern d2e_x86_shr8",
        "    .extern d2e_x86_shr16",
        "    .extern d2e_x86_sar8",
        "    .extern d2e_x86_sar16",
        "    .extern d2e_x86_rol8",
        "    .extern d2e_x86_rol16",
        "    .extern d2e_x86_ror8",
        "    .extern d2e_x86_ror16",
        "    .extern d2e_x86_rcl8",
        "    .extern d2e_x86_rcl16",
        "    .extern d2e_x86_rcr8",
        "    .extern d2e_x86_rcr16",
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
                "    mov a12, a4 /* already computed module target */",
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
