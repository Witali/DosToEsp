#!/usr/bin/env python3
"""Translate statically reachable 8086 DOS blocks into native C regions."""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys
from collections import deque

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = PROJECT_ROOT / "local_tools" / "python_packages"
sys.path.insert(0, str(LOCAL_PACKAGES))

try:
    from capstone import CS_ARCH_X86, CS_MODE_16, Cs
    from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_OP_REG
except ImportError as error:
    raise SystemExit(
        "Capstone is missing. Run scripts/setup-analysis-tools.ps1 first."
    ) from error


class TranslationError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class MemoryOperand:
    width: int
    segment: str | None
    base: str | None
    index: str | None
    displacement: int


OperandValue = int | str | MemoryOperand


@dataclasses.dataclass(frozen=True)
class Instruction:
    address: int
    size: int
    mnemonic: str
    op_str: str
    operands: tuple[tuple[str, OperandValue], ...]
    indirect_targets: tuple[int, ...] = ()

    @property
    def next_address(self) -> int:
        return self.address + self.size


REG16 = {
    "ax": "D2E_X86_AX",
    "cx": "D2E_X86_CX",
    "dx": "D2E_X86_DX",
    "bx": "D2E_X86_BX",
    "sp": "D2E_X86_SP",
    "bp": "D2E_X86_BP",
    "si": "D2E_X86_SI",
    "di": "D2E_X86_DI",
}

REG8 = {
    "al": 0,
    "cl": 1,
    "dl": 2,
    "bl": 3,
    "ah": 4,
    "ch": 5,
    "dh": 6,
    "bh": 7,
}

SEGMENTS = {
    "es": "D2E_X86_ES",
    "cs": "D2E_X86_CS",
    "ss": "D2E_X86_SS",
    "ds": "D2E_X86_DS",
}

CONDITIONS = {
    "jo": "(cpu->flags & D2E_X86_FLAG_OF) != 0U",
    "jno": "(cpu->flags & D2E_X86_FLAG_OF) == 0U",
    "jb": "(cpu->flags & D2E_X86_FLAG_CF) != 0U",
    "jc": "(cpu->flags & D2E_X86_FLAG_CF) != 0U",
    "jnae": "(cpu->flags & D2E_X86_FLAG_CF) != 0U",
    "jae": "(cpu->flags & D2E_X86_FLAG_CF) == 0U",
    "jnb": "(cpu->flags & D2E_X86_FLAG_CF) == 0U",
    "jnc": "(cpu->flags & D2E_X86_FLAG_CF) == 0U",
    "je": "(cpu->flags & D2E_X86_FLAG_ZF) != 0U",
    "jz": "(cpu->flags & D2E_X86_FLAG_ZF) != 0U",
    "jne": "(cpu->flags & D2E_X86_FLAG_ZF) == 0U",
    "jnz": "(cpu->flags & D2E_X86_FLAG_ZF) == 0U",
    "jbe": "(cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_ZF)) != 0U",
    "jna": "(cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_ZF)) != 0U",
    "ja": "(cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_ZF)) == 0U",
    "jnbe": "(cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_ZF)) == 0U",
    "js": "(cpu->flags & D2E_X86_FLAG_SF) != 0U",
    "jns": "(cpu->flags & D2E_X86_FLAG_SF) == 0U",
    "jp": "(cpu->flags & D2E_X86_FLAG_PF) != 0U",
    "jpe": "(cpu->flags & D2E_X86_FLAG_PF) != 0U",
    "jnp": "(cpu->flags & D2E_X86_FLAG_PF) == 0U",
    "jpo": "(cpu->flags & D2E_X86_FLAG_PF) == 0U",
    "jl": "((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U",
    "jnge": "((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U",
    "jge": "(((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U) == 0U",
    "jnl": "(((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U) == 0U",
    "jle": "((cpu->flags & D2E_X86_FLAG_ZF) != 0U) || (((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U)",
    "jng": "((cpu->flags & D2E_X86_FLAG_ZF) != 0U) || (((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U)",
    "jg": "((cpu->flags & D2E_X86_FLAG_ZF) == 0U) && ((((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U) == 0U)",
    "jnle": "((cpu->flags & D2E_X86_FLAG_ZF) == 0U) && ((((cpu->flags >> 7U) ^ (cpu->flags >> 11U)) & 1U) == 0U)",
}

INTEL_8086_PREFIXES = frozenset((0x26, 0x2E, 0x36, 0x3E, 0xF0, 0xF2, 0xF3))
OUTSIDE_DOCUMENTED_8086_OPCODES = frozenset(
    (*range(0x60, 0x70), 0x82, 0xC0, 0xC1, 0xC8, 0xC9, 0xD6, 0xF1)
)


def require_8086_encoding(encoded: bytes, address: int) -> None:
    """Reject instruction encodings outside the documented Intel 8086 ISA."""
    opcode_index = 0
    while (
        opcode_index < len(encoded)
        and encoded[opcode_index] in INTEL_8086_PREFIXES
    ):
        opcode_index += 1
    if opcode_index >= len(encoded):
        raise TranslationError(f"{address:05x}: instruction contains only prefixes")

    opcode = encoded[opcode_index]
    if opcode == 0x0F or opcode in OUTSIDE_DOCUMENTED_8086_OPCODES:
        raise TranslationError(
            f"{address:05x}: opcode 0x{opcode:02x} is outside the Intel 8086 profile"
        )


def normalize_8086_mnemonic(encoded: bytes, mnemonic: str) -> str:
    """Correct operand-size-dependent names using the fixed 16-bit profile."""
    opcode_index = 0
    while (
        opcode_index < len(encoded)
        and encoded[opcode_index] in INTEL_8086_PREFIXES
    ):
        opcode_index += 1
    if opcode_index < len(encoded):
        opcode = encoded[opcode_index]
        if opcode == 0x98:
            return "cbw"
        if opcode == 0x99:
            return "cwd"
    return mnemonic.lower()


def read_hex(path: pathlib.Path) -> bytes:
    chunks: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        chunks.append(line.split("#", 1)[0])
    compact = re.sub(r"\s+", "", "".join(chunks))
    try:
        return bytes.fromhex(compact)
    except ValueError as error:
        raise TranslationError(f"invalid hexadecimal fixture {path}: {error}") from error


def relocate_mz_module(
    image: bytes,
    relocations: tuple[tuple[int, int], ...],
    load_segment: int,
) -> bytes:
    """Return the load module bytes as DOS presents them to the program."""
    relocated = bytearray(image)
    for offset, segment in relocations:
        index = segment * 16 + offset
        if index < 0 or index + 2 > len(relocated):
            raise TranslationError(
                f"MZ relocation {segment:04x}:{offset:04x} leaves the load module"
            )
        value = relocated[index] | (relocated[index + 1] << 8)
        value = (value + load_segment) & 0xFFFF
        relocated[index] = value & 0xFF
        relocated[index + 1] = value >> 8
    return bytes(relocated)


def operand_tuple(instruction, operand) -> tuple[str, OperandValue]:
    if operand.type == X86_OP_REG:
        return ("reg", instruction.reg_name(operand.reg))
    if operand.type == X86_OP_IMM:
        return ("imm", int(operand.imm) & 0xFFFF)
    if operand.type == X86_OP_MEM:
        memory = operand.mem
        if int(memory.scale) not in (0, 1):
            return ("unsupported", 0)
        return (
            "mem",
            MemoryOperand(
                width=int(operand.size) * 8,
                segment=(
                    instruction.reg_name(memory.segment)
                    if memory.segment
                    else None
                ),
                base=instruction.reg_name(memory.base) if memory.base else None,
                index=instruction.reg_name(memory.index) if memory.index else None,
                displacement=int(memory.disp),
            ),
        )
    return ("unsupported", 0)


def decode_one(disassembler: Cs, image: bytes, base: int, address: int) -> Instruction:
    index = address - base
    if index < 0 or index >= len(image):
        raise TranslationError(f"control flow leaves COM image at {address:04x}")
    decoded = next(disassembler.disasm(image[index:], address, count=1), None)
    if decoded is None:
        raise TranslationError(f"cannot decode instruction at {address:04x}")
    require_8086_encoding(bytes(decoded.bytes), address)
    return Instruction(
        address=address,
        size=decoded.size,
        mnemonic=normalize_8086_mnemonic(
            bytes(decoded.bytes), decoded.mnemonic
        ),
        op_str=decoded.op_str,
        operands=tuple(operand_tuple(decoded, operand) for operand in decoded.operands),
    )


def direct_target(instruction: Instruction) -> int:
    if len(instruction.operands) != 1 or instruction.operands[0][0] != "imm":
        raise TranslationError(
            f"{instruction.address:04x}: indirect {instruction.mnemonic} is not yet supported"
        )
    return int(instruction.operands[0][1])


def recover_cs_bx_jump_table(
    image: bytes, base: int, instruction: Instruction
) -> tuple[int, ...]:
    """Recover the bounded 8086 switch idiom used by the target compiler."""
    if (
        instruction.mnemonic != "jmp"
        or len(instruction.operands) != 1
        or instruction.operands[0][0] != "mem"
        or not isinstance(instruction.operands[0][1], MemoryOperand)
    ):
        return ()
    memory = instruction.operands[0][1]
    if (
        memory.width != 16
        or memory.segment != "cs"
        or memory.base != "bx"
        or memory.index is not None
    ):
        return ()

    instruction_offset = instruction.address - base
    pattern_offset = instruction_offset - 9
    if pattern_offset < 0 or instruction.next_address - base > len(image):
        return ()
    pattern = image[pattern_offset:instruction_offset]
    if (
        len(pattern) != 9
        or pattern[0:2] != bytes((0x83, 0xFB))
        or pattern[3:] != bytes((0x76, 0x02, 0x2B, 0xDB, 0xD1, 0xE3))
    ):
        return ()

    entry_count = pattern[2] + 1
    table_offset = instruction.next_address - base
    table_end = table_offset + entry_count * 2
    segment_base = instruction.next_address - (memory.displacement & 0xFFFF)
    if table_end > len(image):
        return ()

    targets: list[int] = []
    image_end = base + len(image)
    for offset in range(table_offset, table_end, 2):
        target_ip = image[offset] | (image[offset + 1] << 8)
        target = segment_base + target_ip
        if target < base or target >= image_end:
            return ()
        targets.append(target)
    return tuple(dict.fromkeys(targets))


def recover_interrupt_vector_targets(
    image: bytes,
    base: int,
    cs_base: int,
    instruction: Instruction,
    decoded: dict[int, Instruction],
) -> tuple[int, tuple[int, ...]] | None:
    """Recover handlers installed with MOV ES:[vector],BX / MOV ES:[vector+2],CS."""
    if (
        instruction.mnemonic != "mov"
        or len(instruction.operands) != 2
        or instruction.operands[0][0] != "mem"
        or not isinstance(instruction.operands[0][1], MemoryOperand)
        or instruction.operands[1] != ("reg", "bx")
    ):
        return None
    memory = instruction.operands[0][1]
    vector_offset = memory.displacement & 0xFFFF
    if (
        memory.width != 16
        or memory.segment != "es"
        or memory.base is not None
        or memory.index is not None
        or vector_offset > 0x03FC
        or vector_offset % 4 != 0
    ):
        return None

    following = instruction.next_address - base
    segment_offset = vector_offset + 2
    expected = bytes(
        (0x26, 0x8C, 0x0E, segment_offset & 0xFF, segment_offset >> 8)
    )
    if image[following : following + len(expected)] != expected:
        return None

    candidates: list[int] = []
    for previous in decoded.values():
        if not instruction.address - 32 <= previous.address < instruction.address:
            continue
        if (
            previous.mnemonic == "mov"
            and len(previous.operands) == 2
            and previous.operands[0] == ("reg", "bx")
            and previous.operands[1][0] == "imm"
        ):
            target = cs_base + int(previous.operands[1][1])
            if base <= target < base + len(image):
                candidates.append(target)
    targets = tuple(dict.fromkeys(candidates))
    if not targets:
        return None
    return vector_offset // 4, targets


def successors(instruction: Instruction) -> tuple[int, ...]:
    mnemonic = instruction.mnemonic
    if mnemonic == "ljmp":
        return ()
    if mnemonic == "jmp":
        if instruction.indirect_targets:
            return instruction.indirect_targets
        return (direct_target(instruction),)
    if mnemonic in CONDITIONS or mnemonic in ("loop", "loope", "loopne", "jcxz"):
        return (direct_target(instruction), instruction.next_address)
    if mnemonic in ("ret", "retf", "iret", "hlt"):
        return ()
    if mnemonic == "call":
        return (direct_target(instruction), instruction.next_address)
    return (instruction.next_address,)


def is_terminator(instruction: Instruction) -> bool:
    return (
        instruction.mnemonic in CONDITIONS
        or instruction.mnemonic
        in (
            "jmp", "loop", "loope", "loopne", "jcxz", "call", "ret",
            "retf", "iret", "ljmp", "int", "hlt"
        )
    )


def discover(
    image: bytes, base: int, entry: int, cs_base: int | None = None
) -> dict[int, Instruction]:
    disassembler = Cs(CS_ARCH_X86, CS_MODE_16)
    disassembler.detail = True
    queue = deque([entry])
    decoded: dict[int, Instruction] = {}
    occupied: dict[int, int] = {}
    image_end = base + len(image)
    if cs_base is None:
        cs_base = base - 0x100

    while queue:
        address = queue.popleft()
        if address in decoded:
            continue
        if address < base or address >= image_end:
            raise TranslationError(f"control flow leaves COM image at {address:04x}")
        if address in occupied:
            owner = occupied[address]
            raise TranslationError(
                f"control flow enters the middle of {owner:04x} at {address:04x}"
            )
        instruction = decode_one(disassembler, image, base, address)
        indirect_targets = recover_cs_bx_jump_table(image, base, instruction)
        if indirect_targets:
            instruction = dataclasses.replace(
                instruction, indirect_targets=indirect_targets
            )
        for byte_address in range(address, instruction.next_address):
            previous = occupied.get(byte_address)
            if previous is not None and previous != address:
                raise TranslationError(
                    f"overlapping instructions at {previous:04x} and {address:04x}"
                )
            occupied[byte_address] = address
        decoded[address] = instruction
        vector_candidates = [instruction]
        vector_candidates.extend(
            decoded[candidate]
            for candidate in range(address + 1, address + 33)
            if candidate in decoded
        )
        for vector_instruction in vector_candidates:
            interrupt_vector = recover_interrupt_vector_targets(
                image, base, cs_base, vector_instruction, decoded
            )
            if interrupt_vector is not None:
                _, targets = interrupt_vector
                queue.extend(targets)
        for target in successors(instruction):
            wrapped_target = target & 0xFFFF
            if wrapped_target != image_end:
                queue.append(wrapped_target)
    return decoded


def make_blocks(
    decoded: dict[int, Instruction], entry: int
) -> dict[int, list[Instruction]]:
    leaders = {entry}
    incoming: set[int] = set()
    for instruction in decoded.values():
        if is_terminator(instruction):
            for target in successors(instruction):
                if target in decoded:
                    leaders.add(target)
                    incoming.add(target)
        else:
            if instruction.next_address in decoded:
                incoming.add(instruction.next_address)
    leaders.update(set(decoded) - incoming)

    blocks: dict[int, list[Instruction]] = {}
    for leader in sorted(leaders):
        current = leader
        block: list[Instruction] = []
        while current in decoded:
            instruction = decoded[current]
            block.append(instruction)
            if is_terminator(instruction):
                break
            current = instruction.next_address
            if current in leaders:
                break
        blocks[leader] = block
    return blocks


def cached_base_register(name: str) -> str:
    if name in REG16:
        return name
    if name in REG8:
        return ("ax", "cx", "dx", "bx")[REG8[name] & 3]
    raise TranslationError(f"unsupported register {name}")


def reg_read(name: str, cached: bool = False) -> tuple[str, int]:
    if name in SEGMENTS:
        return (f"cpu->segments[{SEGMENTS[name]}]", 16)
    if cached:
        base = cached_base_register(name)
        if name in REG16:
            return (f"r_{base}", 16)
        shift = 8 if REG8[name] >= 4 else 0
        return (f"(uint8_t)((r_{base} >> {shift}U) & UINT16_C(0x00ff))", 8)
    if name in REG16:
        return (f"cpu->regs[{REG16[name]}]", 16)
    if name in REG8:
        return (f"d2e_x86_get_reg8(cpu, {REG8[name]}U)", 8)
    raise TranslationError(f"unsupported register {name}")


def reg_write(name: str, expression: str, cached: bool = False) -> str:
    if name in SEGMENTS:
        return f"cpu->segments[{SEGMENTS[name]}] = (uint16_t)({expression});"
    if cached:
        base = cached_base_register(name)
        if name in REG16:
            return f"r_{base} = (uint16_t)({expression});"
        if REG8[name] >= 4:
            return (
                f"r_{base} = (uint16_t)((r_{base} & UINT16_C(0x00ff)) | "
                f"((uint16_t)(uint8_t)({expression}) << 8U));"
            )
        return (
            f"r_{base} = (uint16_t)((r_{base} & UINT16_C(0xff00)) | "
            f"(uint8_t)({expression}));"
        )
    if name in REG16:
        return f"cpu->regs[{REG16[name]}] = (uint16_t)({expression});"
    if name in REG8:
        return f"d2e_x86_set_reg8(cpu, {REG8[name]}U, (uint8_t)({expression}));"
    raise TranslationError(f"unsupported register {name}")


def memory_offset_expression(memory: MemoryOperand, cached: bool) -> str:
    terms: list[str] = []
    for name in (memory.base, memory.index):
        if name is None:
            continue
        value, width = reg_read(name, cached)
        if width != 16:
            raise TranslationError(f"invalid 8086 address register {name}")
        terms.append(value)
    if memory.displacement or not terms:
        terms.append(f"UINT16_C(0x{memory.displacement & 0xffff:04x})")
    return f"(uint16_t)({' + '.join(terms)})"


def memory_segment_expression(memory: MemoryOperand) -> str:
    name = memory.segment
    if name is None:
        name = "ss" if "bp" in (memory.base, memory.index) else "ds"
    if name not in SEGMENTS:
        raise TranslationError(f"unsupported memory segment {name}")
    return f"cpu->segments[{SEGMENTS[name]}]"


def memory_read_expression(memory: MemoryOperand, cached: bool) -> str:
    segment = memory_segment_expression(memory)
    offset = memory_offset_expression(memory, cached)
    if memory.width == 8:
        return f"d2e_x86_read8(cpu, d2e_x86_linear({segment}, {offset}))"
    if memory.width == 16:
        return f"d2e_x86_read16_seg(cpu, {segment}, {offset})"
    raise TranslationError(f"unsupported memory width {memory.width}")


def memory_write_statements(
    memory: MemoryOperand, expression: str, cached: bool
) -> list[str]:
    segment = memory_segment_expression(memory)
    offset = memory_offset_expression(memory, cached)
    if memory.width == 8:
        statement = (
            f"d2e_x86_write8(cpu, d2e_x86_linear({segment}, {offset}), "
            f"(uint8_t)({expression}));"
        )
    elif memory.width == 16:
        statement = (
            f"d2e_x86_write16_seg(cpu, {segment}, {offset}, "
            f"(uint16_t)({expression}));"
        )
    else:
        raise TranslationError(f"unsupported memory width {memory.width}")
    return [
        statement,
        "if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
    ]


def operand_width(operand: tuple[str, OperandValue], cached: bool) -> int:
    kind, value = operand
    if kind == "reg":
        return reg_read(str(value), cached)[1]
    if kind == "mem" and isinstance(value, MemoryOperand):
        return value.width
    raise TranslationError("operand has no data width")


def value_expression(
    operand: tuple[str, OperandValue], width: int, cached: bool = False
) -> str:
    kind, value = operand
    if kind == "reg":
        expression, actual_width = reg_read(str(value), cached)
        if actual_width != width:
            raise TranslationError(f"operand width mismatch for {value}")
        return expression
    if kind == "imm":
        masked = int(value) & (0xFF if width == 8 else 0xFFFF)
        return f"UINT{width}_C(0x{masked:0{width // 4}x})"
    if kind == "mem" and isinstance(value, MemoryOperand):
        if value.width != width:
            raise TranslationError("memory operand width mismatch")
        return memory_read_expression(value, cached)
    raise TranslationError("unsupported value operand")


def write_operand(
    operand: tuple[str, OperandValue], expression: str, cached: bool
) -> list[str]:
    kind, value = operand
    if kind == "reg":
        return [reg_write(str(value), expression, cached)]
    if kind == "mem" and isinstance(value, MemoryOperand):
        return memory_write_statements(value, expression, cached)
    raise TranslationError("destination is not writable")


def stack_pointer_expression(cached: bool) -> str:
    return "r_sp" if cached else "cpu->regs[D2E_X86_SP]"


def stack_push_statements(
    operand: tuple[str, OperandValue], cached: bool
) -> list[str]:
    stack_pointer = stack_pointer_expression(cached)
    value = value_expression(operand, 16, cached)
    return [
        f"{stack_pointer} = (uint16_t)({stack_pointer} - UINT16_C(2));",
        (
            "d2e_x86_write16_seg(cpu, cpu->segments[D2E_X86_SS], "
            f"{stack_pointer}, {value});"
        ),
        "if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
    ]


def stack_pop_statements(
    operand: tuple[str, OperandValue], cached: bool
) -> list[str]:
    stack_pointer = stack_pointer_expression(cached)
    lines = [
        (
            "stack_value = d2e_x86_read16_seg(cpu, "
            f"cpu->segments[D2E_X86_SS], {stack_pointer});"
        ),
        f"{stack_pointer} = (uint16_t)({stack_pointer} + UINT16_C(2));",
    ]
    lines.extend(write_operand(operand, "stack_value", cached))
    return lines


def string_index_update(register: str, width: int) -> str:
    forward = f"UINT16_C(0x{width:04x})"
    backward = f"UINT16_C(0x{(-width) & 0xffff:04x})"
    return (
        f"r_{register} = (uint16_t)(r_{register} + "
        f"((cpu->flags & D2E_X86_FLAG_DF) != 0U ? {backward} : {forward}));"
    )


def string_statements(
    mnemonic: str,
    operands: tuple[tuple[str, OperandValue], ...],
    cached: bool,
) -> list[str]:
    repeat_mode = ""
    operation = mnemonic
    for prefix in ("repne ", "repe ", "rep "):
        if mnemonic.startswith(prefix):
            repeat_mode = prefix.strip()
            operation = mnemonic.removeprefix(prefix)
            break
    repeated = bool(repeat_mode)
    if operation not in (
        "movsb", "movsw", "stosb", "stosw", "lodsb", "lodsw",
        "scasb", "scasw",
    ):
        raise TranslationError(f"unsupported string instruction {mnemonic}")
    width = 1 if operation.endswith("b") else 2
    if len(operands) != 2:
        raise TranslationError(f"unexpected operands for {mnemonic}")
    lines: list[str] = []
    if repeated:
        lines.append("while (r_cx != 0U) {")
    indent = "    " if repeated else ""
    destination, source = operands
    if operation.startswith("scas"):
        accumulator = value_expression(destination, width * 8, cached)
        memory_value = value_expression(source, width * 8, cached)
        lines.append(
            f"{indent}(void)d2e_x86_sub{width * 8}(cpu, "
            f"{accumulator}, {memory_value});"
        )
        lines.append(
            f"{indent}if (cpu->stop_reason != D2E_X86_RUNNING) "
            "{ goto finish; }"
        )
    else:
        statements = write_operand(
            destination, value_expression(source, width * 8, cached), cached
        )
        lines.extend(f"{indent}{statement}" for statement in statements)
    if operation.startswith(("movs", "lods")):
        lines.append(indent + string_index_update("si", width))
    if operation.startswith(("movs", "stos", "scas")):
        lines.append(indent + string_index_update("di", width))
    if repeated:
        lines.append("    r_cx = (uint16_t)(r_cx - UINT16_C(1));")
        if repeat_mode == "repne":
            lines.append(
                "    if ((cpu->flags & D2E_X86_FLAG_ZF) != 0U) { break; }"
            )
        elif repeat_mode == "repe":
            lines.append(
                "    if ((cpu->flags & D2E_X86_FLAG_ZF) == 0U) { break; }"
            )
        lines.append("}")
    return lines


def port_expression(operand: tuple[str, OperandValue], cached: bool) -> str:
    if operand[0] == "imm":
        return f"UINT16_C(0x{int(operand[1]) & 0xffff:04x})"
    value, width = reg_read(str(operand[1]), cached)
    if operand[0] != "reg" or width != 16:
        raise TranslationError("port must be an immediate or 16-bit register")
    return value


def translate_data_instruction(
    instruction: Instruction, cached: bool = False
) -> list[str]:
    mnemonic = instruction.mnemonic
    operands = instruction.operands
    location = f"{instruction.address:04x}: {mnemonic} {instruction.op_str}".rstrip()
    if mnemonic == "nop":
        return []
    if mnemonic == "push" and len(operands) == 1:
        return stack_push_statements(operands[0], cached)
    if mnemonic == "pop" and len(operands) == 1:
        return stack_pop_statements(operands[0], cached)
    if mnemonic == "pushf" and not operands:
        stack_pointer = stack_pointer_expression(cached)
        return [
            f"{stack_pointer} = (uint16_t)({stack_pointer} - UINT16_C(2));",
            "d2e_x86_write16_seg(cpu, cpu->segments[D2E_X86_SS], "
            f"{stack_pointer}, (uint16_t)(cpu->flags | D2E_X86_FLAG_FIXED));",
            "if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
        ]
    if mnemonic == "popf" and not operands:
        stack_pointer = stack_pointer_expression(cached)
        return [
            "stack_value = d2e_x86_read16_seg(cpu, "
            f"cpu->segments[D2E_X86_SS], {stack_pointer});",
            f"{stack_pointer} = (uint16_t)({stack_pointer} + UINT16_C(2));",
            "if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
            "cpu->flags = (uint16_t)((stack_value & UINT16_C(0x0fd5)) | "
            "D2E_X86_FLAG_FIXED);",
        ]
    operation = mnemonic.removeprefix("rep ").removeprefix(
        "repne "
    ).removeprefix("repe ")
    if operation in (
        "movsb", "movsw", "stosb", "stosw", "lodsb", "lodsw",
        "scasb", "scasw",
    ):
        return string_statements(mnemonic, operands, cached)
    if mnemonic == "in" and len(operands) == 2:
        if operand_width(operands[0], cached) != 8:
            raise TranslationError("only 8-bit IN is implemented")
        lines = write_operand(
            operands[0],
            f"d2e_x86_port_in8(cpu, {port_expression(operands[1], cached)})",
            cached,
        )
        lines.append("if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }")
        return lines
    if mnemonic == "out" and len(operands) == 2:
        if operand_width(operands[1], cached) != 8:
            raise TranslationError("only 8-bit OUT is implemented")
        value = value_expression(operands[1], 8, cached)
        return [
            f"d2e_x86_port_out8(cpu, {port_expression(operands[0], cached)}, {value});",
            "if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
        ]
    if mnemonic == "mov" and len(operands) == 2:
        width = operand_width(operands[0], cached)
        return write_operand(
            operands[0], value_expression(operands[1], width, cached), cached
        )
    if mnemonic in ("add", "adc", "sub", "xor", "and", "or", "cmp", "test") and len(operands) == 2:
        width = operand_width(operands[0], cached)
        left = value_expression(operands[0], width, cached)
        right = value_expression(operands[1], width, cached)
        if mnemonic in ("xor", "and", "or", "test"):
            operator = {"xor": "^", "and": "&", "or": "|", "test": "&"}[mnemonic]
            expression = (
                f"d2e_x86_logic{width}(cpu, "
                f"(uint{width}_t)({left} {operator} {right}))"
            )
        else:
            operation = "sub" if mnemonic == "cmp" else mnemonic
            expression = f"d2e_x86_{operation}{width}(cpu, {left}, {right})"
        if mnemonic in ("cmp", "test"):
            return [f"(void){expression};"]
        return write_operand(operands[0], expression, cached)
    if mnemonic in ("inc", "dec") and len(operands) == 1:
        width = operand_width(operands[0], cached)
        value = value_expression(operands[0], width, cached)
        return write_operand(
            operands[0],
            f"d2e_x86_{mnemonic}{width}(cpu, {value})",
            cached,
        )
    if mnemonic == "not" and len(operands) == 1:
        width = operand_width(operands[0], cached)
        value = value_expression(operands[0], width, cached)
        return write_operand(
            operands[0], f"(uint{width}_t)(~(uint{width}_t)({value}))", cached
        )
    if mnemonic in ("shl", "shr", "rcl", "rcr") and len(operands) == 2:
        width = operand_width(operands[0], cached)
        value = value_expression(operands[0], width, cached)
        count = value_expression(operands[1], 8, cached)
        return write_operand(
            operands[0],
            f"d2e_x86_{mnemonic}{width}(cpu, {value}, (uint8_t)({count}))",
            cached,
        )
    if mnemonic == "xchg" and len(operands) == 2:
        width = operand_width(operands[0], cached)
        if operand_width(operands[1], cached) != width:
            raise TranslationError("XCHG operand width mismatch")
        left = value_expression(operands[0], width, cached)
        right = value_expression(operands[1], width, cached)
        lines = [f"exchange_value = (uint16_t)({left});"]
        lines.extend(write_operand(operands[0], right, cached))
        lines.extend(
            write_operand(
                operands[1], f"(uint{width}_t)exchange_value", cached
            )
        )
        return lines
    if mnemonic == "mul" and len(operands) == 1:
        width = operand_width(operands[0], cached)
        value = value_expression(operands[0], width, cached)
        if width == 8:
            return [
                "r_ax = d2e_x86_mul8(cpu, (uint8_t)r_ax, "
                f"(uint8_t)({value}));"
            ]
        if width == 16:
            return [
                f"multiply_value = d2e_x86_mul16(cpu, r_ax, {value});",
                "r_ax = (uint16_t)multiply_value;",
                "r_dx = (uint16_t)(multiply_value >> 16U);",
            ]
        raise TranslationError(f"unsupported MUL width {width}")
    if mnemonic == "aaa" and not operands:
        return ["r_ax = d2e_x86_aaa(cpu, r_ax);"]
    if mnemonic == "cbw" and not operands:
        return ["r_ax = (uint16_t)(int16_t)(int8_t)(uint8_t)r_ax;"]
    if mnemonic == "cwd" and not operands:
        return [
            "r_dx = (r_ax & UINT16_C(0x8000)) != 0U "
            "? UINT16_C(0xffff) : UINT16_C(0x0000);"
        ]
    if mnemonic in ("clc", "cld", "cli") and not operands:
        flag = {
            "clc": "D2E_X86_FLAG_CF",
            "cld": "D2E_X86_FLAG_DF",
            "cli": "D2E_X86_FLAG_IF",
        }[mnemonic]
        return [f"cpu->flags = (uint16_t)(cpu->flags & (uint16_t)~{flag});"]
    if mnemonic in ("stc", "std", "sti") and not operands:
        flag = {
            "stc": "D2E_X86_FLAG_CF",
            "std": "D2E_X86_FLAG_DF",
            "sti": "D2E_X86_FLAG_IF",
        }[mnemonic]
        return [f"cpu->flags = (uint16_t)(cpu->flags | {flag});"]
    if mnemonic == "lahf" and not operands:
        return [
            reg_write(
                "ah",
                "(uint8_t)(cpu->flags & UINT16_C(0x00d7))",
                cached,
            )
        ]
    if mnemonic == "sahf" and not operands:
        return [
            (
                "cpu->flags = (uint16_t)((cpu->flags & UINT16_C(0xff28)) | "
                "(r_ax >> 8U & UINT16_C(0x00d7)) | D2E_X86_FLAG_FIXED);"
            )
        ]
    raise TranslationError(f"unsupported instruction {location}")


def cached_registers(blocks: dict[int, list[Instruction]]) -> list[str]:
    used: set[str] = set()
    for block in blocks.values():
        for instruction in block:
            for kind, value in instruction.operands:
                if kind == "reg":
                    name = str(value)
                    if name not in SEGMENTS:
                        used.add(cached_base_register(name))
                elif kind == "mem" and isinstance(value, MemoryOperand):
                    for name in (value.base, value.index):
                        if name is not None:
                            used.add(cached_base_register(name))
            if instruction.mnemonic in ("loop", "loope", "loopne", "jcxz"):
                used.add("cx")
            if instruction.mnemonic in (
                "call", "ret", "retf", "iret", "push", "pop", "pushf",
                "popf"
            ):
                used.add("sp")
            if instruction.mnemonic in ("lahf", "sahf"):
                used.add("ax")
            if instruction.mnemonic == "cbw":
                used.add("ax")
            if instruction.mnemonic == "cwd":
                used.update(("ax", "dx"))
            if instruction.mnemonic.startswith(("rep ", "repne ", "repe ")):
                used.add("cx")
            if instruction.mnemonic in ("mul", "aaa"):
                used.add("ax")
            if instruction.mnemonic == "mul" and operand_width(
                instruction.operands[0], True
            ) == 16:
                used.add("dx")
    return [name for name in REG16 if name in used]


def emit_cached_load(registers: list[str], indent: str = "    ") -> list[str]:
    return [
        f"{indent}r_{name} = cpu->regs[{REG16[name]}];" for name in registers
    ]


def emit_cached_store(registers: list[str], indent: str = "    ") -> list[str]:
    return [
        f"{indent}cpu->regs[{REG16[name]}] = r_{name};" for name in registers
    ]


def emit_native_target(
    lines: list[str],
    target: int,
    blocks: dict[int, list[Instruction]],
    indent: str,
    image_format: str,
    load_segment: int,
) -> None:
    if target in blocks:
        lines.append(f"{indent}goto block_{target:04x};")
    else:
        lines.append(
            f"{indent}cpu->ip = {guest_ip_expression(target, image_format, load_segment)};"
        )
        lines.append(f"{indent}goto dispatch;")


def guest_ip_expression(target: int, image_format: str, load_segment: int) -> str:
    if image_format == "com":
        return f"UINT16_C(0x{target:04x})"
    return (
        f"(uint16_t)(UINT32_C(0x{target:05x}) - "
        f"((uint32_t)(uint16_t)(cpu->segments[D2E_X86_CS] - "
        f"UINT16_C(0x{load_segment:04x})) << 4U))"
    )


def emit_region(
    blocks: dict[int, list[Instruction]],
    load_segment: int,
    image_format: str = "com",
    function_name: str = "program_region",
    handoff_on_unknown: bool = False,
) -> list[str]:
    registers = cached_registers(blocks)
    lines = [
        f"static uint32_t {function_name}(d2e_x86_cpu *cpu, uint32_t block_budget) {{",
        "    uint32_t executed = 0;",
        "    uint64_t retired = 0;",
    ]
    if image_format == "mz":
        lines.append("    uint32_t module_target;")
    if any(
        instruction.mnemonic in ("pop", "popf")
        for block in blocks.values()
        for instruction in block
    ):
        lines.append("    uint16_t stack_value;")
    if any(
        instruction.mnemonic == "xchg"
        for block in blocks.values()
        for instruction in block
    ):
        lines.append("    uint16_t exchange_value;")
    if any(
        instruction.mnemonic == "mul"
        and operand_width(instruction.operands[0], True) == 16
        for block in blocks.values()
        for instruction in block
    ):
        lines.append("    uint32_t multiply_value;")
    for name in registers:
        lines.append(f"    uint16_t r_{name};")
    lines.extend(emit_cached_load(registers))
    lines.extend(["", "    goto dispatch;", "dispatch:"])
    if image_format == "com":
        lines.extend(
            [
                f"    if (cpu->segments[D2E_X86_CS] != UINT16_C(0x{load_segment:04x})) {{",
                "        cpu->fault_cs = cpu->segments[D2E_X86_CS];",
                "        cpu->fault_ip = cpu->ip;",
                "        cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
                "        goto finish;",
                "    }",
                "    switch (cpu->ip) {",
            ]
        )
    else:
        lines.extend(
            [
                f"    if (cpu->segments[D2E_X86_CS] < UINT16_C(0x{load_segment:04x})) {{",
                "        cpu->fault_cs = cpu->segments[D2E_X86_CS];",
                "        cpu->fault_ip = cpu->ip;",
                "        cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
                "        goto finish;",
                "    }",
                "    module_target =",
                f"        ((uint32_t)(uint16_t)(cpu->segments[D2E_X86_CS] - UINT16_C(0x{load_segment:04x})) << 4U) + cpu->ip;",
                "    switch (module_target) {",
            ]
        )
    for leader in sorted(blocks):
        constant = "UINT16_C" if image_format == "com" else "UINT32_C"
        width = 4 if image_format == "com" else 5
        lines.append(
            f"    case {constant}(0x{leader:0{width}x}): goto block_{leader:04x};"
        )
    lines.append("    default:")
    if handoff_on_unknown:
        lines.append("        goto finish;")
    else:
        lines.extend(
            [
                "        cpu->fault_cs = cpu->segments[D2E_X86_CS];",
                "        cpu->fault_ip = cpu->ip;",
                "        cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
                "        goto finish;",
            ]
        )
    lines.extend(["    }", ""])

    for leader in sorted(blocks):
        block = blocks[leader]
        lines.extend(
            [
                f"block_{leader:04x}:",
                "    if (executed >= block_budget) {",
                f"        cpu->ip = {guest_ip_expression(leader, image_format, load_segment)};",
                "        goto finish;",
                "    }",
                "    ++executed;",
            ]
        )
        terminated = False
        for instruction in block:
            mnemonic = instruction.mnemonic
            if mnemonic in CONDITIONS:
                target = direct_target(instruction)
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append(f"    if ({CONDITIONS[mnemonic]}) {{")
                emit_native_target(
                    lines, target, blocks, "        ", image_format, load_segment
                )
                lines.append("    }")
                emit_native_target(
                    lines,
                    instruction.next_address,
                    blocks,
                    "    ",
                    image_format,
                    load_segment,
                )
                terminated = True
            elif mnemonic == "jmp":
                lines.append(f"    retired += UINT64_C({len(block)});")
                if instruction.indirect_targets:
                    operand = instruction.operands[0]
                    target = value_expression(operand, 16, cached=True)
                    lines.append(f"    cpu->ip = (uint16_t)({target});")
                    lines.append("    if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }")
                    lines.append("    goto dispatch;")
                else:
                    emit_native_target(
                        lines,
                        direct_target(instruction),
                        blocks,
                        "    ",
                        image_format,
                        load_segment,
                    )
                terminated = True
            elif mnemonic == "loop":
                target = direct_target(instruction)
                lines.append("    r_cx = (uint16_t)(r_cx - 1U);")
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append("    if (r_cx != 0U) {")
                emit_native_target(
                    lines, target, blocks, "        ", image_format, load_segment
                )
                lines.append("    }")
                emit_native_target(
                    lines,
                    instruction.next_address,
                    blocks,
                    "    ",
                    image_format,
                    load_segment,
                )
                terminated = True
            elif mnemonic in ("loope", "loopne"):
                target = direct_target(instruction)
                flag_condition = (
                    "(cpu->flags & D2E_X86_FLAG_ZF) != 0U"
                    if mnemonic == "loope"
                    else "(cpu->flags & D2E_X86_FLAG_ZF) == 0U"
                )
                lines.append("    r_cx = (uint16_t)(r_cx - 1U);")
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append(f"    if (r_cx != 0U && {flag_condition}) {{")
                emit_native_target(
                    lines, target, blocks, "        ", image_format, load_segment
                )
                lines.append("    }")
                emit_native_target(
                    lines,
                    instruction.next_address,
                    blocks,
                    "    ",
                    image_format,
                    load_segment,
                )
                terminated = True
            elif mnemonic == "jcxz":
                target = direct_target(instruction)
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append("    if (r_cx == 0U) {")
                emit_native_target(
                    lines, target, blocks, "        ", image_format, load_segment
                )
                lines.append("    }")
                emit_native_target(
                    lines,
                    instruction.next_address,
                    blocks,
                    "    ",
                    image_format,
                    load_segment,
                )
                terminated = True
            elif mnemonic == "int":
                interrupt_number = direct_target(instruction) & 0xFF
                lines.append(
                    f"    cpu->ip = {guest_ip_expression(instruction.next_address, image_format, load_segment)};"
                )
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.extend(emit_cached_store(registers))
                lines.extend(
                    [
                        "    cpu->instructions_retired += retired;",
                        "    retired = 0;",
                        f"    d2e_native_interrupt(cpu, UINT8_C(0x{interrupt_number:02x}));",
                        "    if (cpu->stop_reason != D2E_X86_RUNNING) {",
                        "        return executed;",
                        "    }",
                    ]
                )
                lines.extend(emit_cached_load(registers))
                lines.append("    goto dispatch;")
                terminated = True
            elif mnemonic == "hlt":
                lines.append(
                    f"    cpu->ip = {guest_ip_expression(instruction.next_address, image_format, load_segment)};"
                )
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append("    cpu->stop_reason = D2E_X86_EXITED;")
                lines.append("    goto finish;")
                terminated = True
            elif mnemonic == "call":
                lines.extend(
                    [
                        "    r_sp = (uint16_t)(r_sp - UINT16_C(2));",
                        (
                            "    d2e_x86_write16_seg(cpu, cpu->segments[D2E_X86_SS], "
                            f"r_sp, {guest_ip_expression(instruction.next_address, image_format, load_segment)});"
                        ),
                        "    if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
                    ]
                )
                lines.append(f"    retired += UINT64_C({len(block)});")
                emit_native_target(
                    lines,
                    direct_target(instruction),
                    blocks,
                    "    ",
                    image_format,
                    load_segment,
                )
                terminated = True
            elif mnemonic == "ret":
                stack_adjustment = 2
                if instruction.operands:
                    if len(instruction.operands) != 1 or instruction.operands[0][0] != "imm":
                        raise TranslationError(
                            f"unsupported ret operands {instruction.address:04x}: {instruction.op_str}"
                        )
                    stack_adjustment += int(instruction.operands[0][1])
                lines.extend(
                    [
                        "    cpu->ip = d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS], r_sp);",
                        f"    r_sp = (uint16_t)(r_sp + UINT16_C(0x{stack_adjustment & 0xffff:04x}));",
                        f"    retired += UINT64_C({len(block)});",
                        "    goto dispatch;",
                    ]
                )
                terminated = True
            elif mnemonic == "retf":
                stack_adjustment = 4
                if instruction.operands:
                    if len(instruction.operands) != 1 or instruction.operands[0][0] != "imm":
                        raise TranslationError(
                            f"unsupported retf operands {instruction.address:04x}: {instruction.op_str}"
                        )
                    stack_adjustment += int(instruction.operands[0][1])
                lines.extend(
                    [
                        "    cpu->ip = d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS], r_sp);",
                        "    cpu->segments[D2E_X86_CS] = d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS], (uint16_t)(r_sp + UINT16_C(2)));",
                        f"    r_sp = (uint16_t)(r_sp + UINT16_C(0x{stack_adjustment & 0xffff:04x}));",
                        f"    retired += UINT64_C({len(block)});",
                        "    goto dispatch;",
                    ]
                )
                terminated = True
            elif mnemonic == "iret":
                lines.extend(
                    [
                        "    cpu->ip = d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS], r_sp);",
                        "    cpu->segments[D2E_X86_CS] = d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS], (uint16_t)(r_sp + UINT16_C(2)));",
                        "    cpu->flags = (uint16_t)((d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS], (uint16_t)(r_sp + UINT16_C(4))) & UINT16_C(0x0fd5)) | D2E_X86_FLAG_FIXED);",
                        "    r_sp = (uint16_t)(r_sp + UINT16_C(6));",
                        f"    retired += UINT64_C({len(block)});",
                        "    if (cpu->stop_reason != D2E_X86_RUNNING) { goto finish; }",
                        "    goto dispatch;",
                    ]
                )
                terminated = True
            elif mnemonic == "ljmp":
                if (
                    len(instruction.operands) != 2
                    or any(operand[0] != "imm" for operand in instruction.operands)
                ):
                    raise TranslationError(
                        f"unsupported far jump {instruction.address:04x}: {instruction.op_str}"
                    )
                segment = int(instruction.operands[0][1]) & 0xFFFF
                offset = int(instruction.operands[1][1]) & 0xFFFF
                lines.extend(
                    [
                        f"    cpu->segments[D2E_X86_CS] = UINT16_C(0x{segment:04x});",
                        f"    cpu->ip = UINT16_C(0x{offset:04x});",
                        "    cpu->fault_cs = cpu->segments[D2E_X86_CS];",
                        "    cpu->fault_ip = cpu->ip;",
                        "    cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
                        f"    retired += UINT64_C({len(block)});",
                        "    goto finish;",
                    ]
                )
                terminated = True
            else:
                for statement in translate_data_instruction(instruction, cached=True):
                    lines.append(f"    {statement}")
            if terminated:
                break
        if not terminated:
            next_address = block[-1].next_address
            lines.append(f"    retired += UINT64_C({len(block)});")
            emit_native_target(
                lines, next_address, blocks, "    ", image_format, load_segment
            )
        lines.append("")

    lines.append("finish:")
    lines.extend(emit_cached_store(registers))
    lines.extend(
        [
            "    cpu->instructions_retired += retired;",
            "    return executed;",
            "}",
        ]
    )
    return lines


MZ_REGION_BLOCK_LIMIT = 256


def partition_blocks(
    blocks: dict[int, list[Instruction]], limit: int = MZ_REGION_BLOCK_LIMIT
) -> list[dict[int, list[Instruction]]]:
    if limit <= 0:
        raise ValueError("native region block limit must be positive")
    leaders = sorted(blocks)
    return [
        {leader: blocks[leader] for leader in leaders[offset : offset + limit]}
        for offset in range(0, len(leaders), limit)
    ]


def emit_mz_regions(
    blocks: dict[int, list[Instruction]], load_segment: int
) -> list[str]:
    partitions = partition_blocks(blocks)
    if len(partitions) == 1:
        return emit_region(blocks, load_segment, "mz")

    lines: list[str] = []
    for index, partition in enumerate(partitions):
        if lines:
            lines.append("")
        lines.extend(
            emit_region(
                partition,
                load_segment,
                "mz",
                f"program_region_{index}",
                handoff_on_unknown=True,
            )
        )

    lines.extend(
        [
            "",
            "static uint32_t program_region(d2e_x86_cpu *cpu, uint32_t block_budget) {",
            "    uint32_t executed = 0;",
            "    uint32_t step;",
            "    uint32_t module_target;",
            "    while (executed < block_budget &&",
            "           cpu->stop_reason == D2E_X86_RUNNING) {",
            f"        if (cpu->segments[D2E_X86_CS] < UINT16_C(0x{load_segment:04x})) {{",
            "            goto unknown_target;",
            "        }",
            "        module_target =",
            f"            ((uint32_t)(uint16_t)(cpu->segments[D2E_X86_CS] - UINT16_C(0x{load_segment:04x})) << 4U) + cpu->ip;",
        ]
    )
    for index, partition in enumerate(partitions):
        keyword = "if" if index == 0 else "else if"
        maximum = max(partition)
        lines.extend(
            [
                f"        {keyword} (module_target <= UINT32_C(0x{maximum:05x})) {{",
                f"            step = program_region_{index}(cpu, block_budget - executed);",
                "        }",
            ]
        )
    lines.extend(
        [
            "        else {",
            "            goto unknown_target;",
            "        }",
            "        if (step == 0U && cpu->stop_reason == D2E_X86_RUNNING) {",
            "            goto unknown_target;",
            "        }",
            "        executed += step;",
            "    }",
            "    return executed;",
            "unknown_target:",
            "    cpu->fault_cs = cpu->segments[D2E_X86_CS];",
            "    cpu->fault_ip = cpu->ip;",
            "    cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
            "    return executed;",
            "}",
        ]
    )
    return lines


def c_identifier(name: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not result or result[0].isdigit():
        result = "program_" + result
    return result


def emit_program(
    image: bytes,
    blocks: dict[int, list[Instruction]],
    name: str,
    load_segment: int,
    entry: int,
) -> str:
    lines = [
        "/* Generated by tools/d2e_translate.py. Do not edit. */",
        '#include "d2e/native_runtime.h"',
        '#include "d2e/x86_alu.h"',
        "",
    ]
    lines.extend(emit_region(blocks, load_segment))
    lines.append("")

    lines.append("static const uint8_t program_image[] = {")
    for offset in range(0, len(image), 12):
        chunk = image[offset : offset + 12]
        lines.append("    " + ", ".join(f"UINT8_C(0x{value:02x})" for value in chunk) + ",")
    lines.extend(
        [
            "};",
            "",
            "const d2e_native_program d2e_generated_program = {",
            f'    .name = "{c_identifier(name)}",',
            "    .format = D2E_NATIVE_IMAGE_COM,",
            f"    .load_segment = UINT16_C(0x{load_segment:04x}),",
            "    .entry_cs = 0,",
            f"    .entry_ip = UINT16_C(0x{entry:04x}),",
            "    .initial_ss = 0,",
            "    .initial_sp = UINT16_C(0xfffe),",
            "    .image = program_image,",
            "    .image_size = sizeof(program_image),",
            "    .relocations = NULL,",
            "    .relocation_count = 0,",
            "    .blocks = NULL,",
            "    .block_count = 0,",
            "    .region = program_region",
            "};",
            "",
        ]
    )
    return "\n".join(lines)


def emit_mz_program(
    image: bytes,
    relocations: tuple[tuple[int, int], ...],
    blocks: dict[int, list[Instruction]],
    name: str,
    load_segment: int,
    entry_cs: int,
    entry_ip: int,
    initial_ss: int,
    initial_sp: int,
) -> str:
    lines = [
        "/* Generated by tools/d2e_translate.py. Do not edit. */",
        '#include "d2e/native_runtime.h"',
        '#include "d2e/x86_alu.h"',
        "",
    ]
    lines.extend(emit_mz_regions(blocks, load_segment))
    lines.extend(["", "static const uint8_t program_image[] = {"])
    for offset in range(0, len(image), 12):
        chunk = image[offset : offset + 12]
        lines.append(
            "    " + ", ".join(f"UINT8_C(0x{value:02x})" for value in chunk) + ","
        )
    lines.extend(["};", ""])

    if relocations:
        lines.append("static const d2e_mz_relocation program_relocations[] = {")
        for offset, segment in relocations:
            lines.append(
                f"    {{UINT16_C(0x{offset:04x}), UINT16_C(0x{segment:04x})}},"
            )
        lines.extend(["};", ""])
        relocation_pointer = "program_relocations"
        relocation_count = (
            "sizeof(program_relocations) / sizeof(program_relocations[0])"
        )
    else:
        relocation_pointer = "NULL"
        relocation_count = "0"

    lines.extend(
        [
            "const d2e_native_program d2e_generated_program = {",
            f'    .name = "{c_identifier(name)}",',
            "    .format = D2E_NATIVE_IMAGE_MZ,",
            f"    .load_segment = UINT16_C(0x{load_segment:04x}),",
            f"    .entry_cs = UINT16_C(0x{entry_cs:04x}),",
            f"    .entry_ip = UINT16_C(0x{entry_ip:04x}),",
            f"    .initial_ss = UINT16_C(0x{initial_ss:04x}),",
            f"    .initial_sp = UINT16_C(0x{initial_sp:04x}),",
            "    .image = program_image,",
            "    .image_size = sizeof(program_image),",
            f"    .relocations = {relocation_pointer},",
            f"    .relocation_count = {relocation_count},",
            "    .blocks = NULL,",
            "    .block_count = 0,",
            "    .region = program_region",
            "};",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate statically reachable 8086 DOS blocks to native C"
    )
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--hex-input", action="store_true")
    parser.add_argument("--name")
    parser.add_argument("--load-segment", type=lambda value: int(value, 0), default=0x1000)
    parser.add_argument("--entry", type=lambda value: int(value, 0), default=0x100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image = read_hex(args.input) if args.hex_input else args.input.read_bytes()
    name = args.name or args.input.stem
    try:
        decoded = discover(image, 0x100, args.entry)
        blocks = make_blocks(decoded, args.entry)
        output = emit_program(image, blocks, name, args.load_segment, args.entry)
    except TranslationError as error:
        print(f"translation failed: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8", newline="\n")
    print(
        f"translated {len(decoded)} instructions into {len(blocks)} native blocks: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
