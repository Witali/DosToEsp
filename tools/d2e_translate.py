#!/usr/bin/env python3
"""Translate statically reachable 8086 COM blocks into native C functions."""

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
    from capstone.x86_const import X86_OP_IMM, X86_OP_REG
except ImportError as error:
    raise SystemExit(
        "Capstone is missing. Run scripts/setup-analysis-tools.ps1 first."
    ) from error


class TranslationError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Instruction:
    address: int
    size: int
    mnemonic: str
    op_str: str
    operands: tuple[tuple[str, int | str], ...]

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


def read_hex(path: pathlib.Path) -> bytes:
    chunks: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        chunks.append(line.split("#", 1)[0])
    compact = re.sub(r"\s+", "", "".join(chunks))
    try:
        return bytes.fromhex(compact)
    except ValueError as error:
        raise TranslationError(f"invalid hexadecimal fixture {path}: {error}") from error


def operand_tuple(instruction, operand) -> tuple[str, int | str]:
    if operand.type == X86_OP_REG:
        return ("reg", instruction.reg_name(operand.reg))
    if operand.type == X86_OP_IMM:
        return ("imm", int(operand.imm) & 0xFFFF)
    return ("unsupported", 0)


def decode_one(disassembler: Cs, image: bytes, base: int, address: int) -> Instruction:
    index = address - base
    if index < 0 or index >= len(image):
        raise TranslationError(f"control flow leaves COM image at {address:04x}")
    decoded = next(disassembler.disasm(image[index:], address, count=1), None)
    if decoded is None:
        raise TranslationError(f"cannot decode instruction at {address:04x}")
    return Instruction(
        address=address,
        size=decoded.size,
        mnemonic=decoded.mnemonic.lower(),
        op_str=decoded.op_str,
        operands=tuple(operand_tuple(decoded, operand) for operand in decoded.operands),
    )


def direct_target(instruction: Instruction) -> int:
    if len(instruction.operands) != 1 or instruction.operands[0][0] != "imm":
        raise TranslationError(
            f"{instruction.address:04x}: indirect {instruction.mnemonic} is not yet supported"
        )
    return int(instruction.operands[0][1])


def successors(instruction: Instruction) -> tuple[int, ...]:
    mnemonic = instruction.mnemonic
    if mnemonic == "jmp":
        return (direct_target(instruction),)
    if mnemonic in CONDITIONS or mnemonic in ("loop", "jcxz"):
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
        in ("jmp", "loop", "jcxz", "call", "ret", "retf", "iret", "int", "hlt")
    )


def discover(image: bytes, base: int, entry: int) -> dict[int, Instruction]:
    disassembler = Cs(CS_ARCH_X86, CS_MODE_16)
    disassembler.detail = True
    queue = deque([entry])
    decoded: dict[int, Instruction] = {}
    occupied: dict[int, int] = {}
    image_end = base + len(image)

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
        for byte_address in range(address, instruction.next_address):
            previous = occupied.get(byte_address)
            if previous is not None and previous != address:
                raise TranslationError(
                    f"overlapping instructions at {previous:04x} and {address:04x}"
                )
            occupied[byte_address] = address
        decoded[address] = instruction
        for target in successors(instruction):
            wrapped_target = target & 0xFFFF
            if wrapped_target != image_end:
                queue.append(wrapped_target)
    return decoded


def make_blocks(
    decoded: dict[int, Instruction], entry: int
) -> dict[int, list[Instruction]]:
    leaders = {entry}
    for instruction in decoded.values():
        if is_terminator(instruction):
            for target in successors(instruction):
                if target in decoded:
                    leaders.add(target)

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


def value_expression(
    operand: tuple[str, int | str], width: int, cached: bool = False
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
    raise TranslationError("memory operands are not implemented in this milestone")


def translate_data_instruction(
    instruction: Instruction, cached: bool = False
) -> list[str]:
    mnemonic = instruction.mnemonic
    operands = instruction.operands
    location = f"{instruction.address:04x}: {mnemonic} {instruction.op_str}".rstrip()
    if mnemonic == "nop":
        return []
    if mnemonic == "mov" and len(operands) == 2 and operands[0][0] == "reg":
        destination = str(operands[0][1])
        _, width = reg_read(destination, cached)
        return [
            reg_write(
                destination, value_expression(operands[1], width, cached), cached
            )
        ]
    if mnemonic in ("add", "sub", "xor", "cmp") and len(operands) == 2:
        if operands[0][0] != "reg":
            raise TranslationError(f"{location}: destination must be a register")
        destination = str(operands[0][1])
        left, width = reg_read(destination, cached)
        right = value_expression(operands[1], width, cached)
        if mnemonic == "xor":
            expression = f"d2e_x86_logic{width}(cpu, (uint{width}_t)({left} ^ {right}))"
        else:
            operation = "sub" if mnemonic == "cmp" else mnemonic
            expression = f"d2e_x86_{operation}{width}(cpu, {left}, {right})"
        if mnemonic == "cmp":
            return [f"(void){expression};"]
        return [reg_write(destination, expression, cached)]
    if mnemonic in ("inc", "dec") and len(operands) == 1:
        if operands[0][0] != "reg":
            raise TranslationError(f"{location}: destination must be a register")
        destination = str(operands[0][1])
        value, width = reg_read(destination, cached)
        return [
            reg_write(
                destination,
                f"d2e_x86_{mnemonic}{width}(cpu, {value})",
                cached,
            )
        ]
    raise TranslationError(f"unsupported instruction {location}")


def cached_registers(blocks: dict[int, list[Instruction]]) -> list[str]:
    used: set[str] = set()
    for block in blocks.values():
        for instruction in block:
            for kind, value in instruction.operands:
                if kind == "reg":
                    used.add(cached_base_register(str(value)))
            if instruction.mnemonic in ("loop", "jcxz"):
                used.add("cx")
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
    lines: list[str], target: int, blocks: dict[int, list[Instruction]], indent: str
) -> None:
    if target in blocks:
        lines.append(f"{indent}goto block_{target:04x};")
    else:
        lines.append(f"{indent}cpu->ip = UINT16_C(0x{target:04x});")
        lines.append(f"{indent}goto dispatch;")


def emit_region(
    blocks: dict[int, list[Instruction]], load_segment: int
) -> list[str]:
    registers = cached_registers(blocks)
    lines = [
        "static uint32_t program_region(d2e_x86_cpu *cpu, uint32_t block_budget) {",
        "    uint32_t executed = 0;",
        "    uint64_t retired = 0;",
    ]
    for name in registers:
        lines.append(f"    uint16_t r_{name};")
    lines.extend(emit_cached_load(registers))
    lines.extend(
        [
            "",
            "dispatch:",
            f"    if (cpu->segments[D2E_X86_CS] != UINT16_C(0x{load_segment:04x})) {{",
            "        cpu->fault_cs = cpu->segments[D2E_X86_CS];",
            "        cpu->fault_ip = cpu->ip;",
            "        cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
            "        goto finish;",
            "    }",
            "    switch (cpu->ip) {",
        ]
    )
    for leader in sorted(blocks):
        lines.append(f"    case UINT16_C(0x{leader:04x}): goto block_{leader:04x};")
    lines.extend(
        [
            "    default:",
            "        cpu->fault_cs = cpu->segments[D2E_X86_CS];",
            "        cpu->fault_ip = cpu->ip;",
            "        cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;",
            "        goto finish;",
            "    }",
            "",
        ]
    )

    for leader in sorted(blocks):
        block = blocks[leader]
        lines.extend(
            [
                f"block_{leader:04x}:",
                "    if (executed >= block_budget) {",
                f"        cpu->ip = UINT16_C(0x{leader:04x});",
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
                emit_native_target(lines, target, blocks, "        ")
                lines.append("    }")
                emit_native_target(lines, instruction.next_address, blocks, "    ")
                terminated = True
            elif mnemonic == "jmp":
                lines.append(f"    retired += UINT64_C({len(block)});")
                emit_native_target(lines, direct_target(instruction), blocks, "    ")
                terminated = True
            elif mnemonic == "loop":
                target = direct_target(instruction)
                lines.append("    r_cx = (uint16_t)(r_cx - 1U);")
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append("    if (r_cx != 0U) {")
                emit_native_target(lines, target, blocks, "        ")
                lines.append("    }")
                emit_native_target(lines, instruction.next_address, blocks, "    ")
                terminated = True
            elif mnemonic == "jcxz":
                target = direct_target(instruction)
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append("    if (r_cx == 0U) {")
                emit_native_target(lines, target, blocks, "        ")
                lines.append("    }")
                emit_native_target(lines, instruction.next_address, blocks, "    ")
                terminated = True
            elif mnemonic == "int":
                interrupt_number = direct_target(instruction) & 0xFF
                lines.append(f"    cpu->ip = UINT16_C(0x{instruction.next_address:04x});")
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
                lines.append(f"    cpu->ip = UINT16_C(0x{instruction.next_address:04x});")
                lines.append(f"    retired += UINT64_C({len(block)});")
                lines.append("    cpu->stop_reason = D2E_X86_EXITED;")
                lines.append("    goto finish;")
                terminated = True
            elif mnemonic in ("call", "ret", "retf", "iret"):
                raise TranslationError(
                    f"unsupported control transfer {instruction.address:04x}: {mnemonic} {instruction.op_str}"
                )
            else:
                for statement in translate_data_instruction(instruction, cached=True):
                    lines.append(f"    {statement}")
            if terminated:
                break
        if not terminated:
            next_address = block[-1].next_address
            lines.append(f"    retired += UINT64_C({len(block)});")
            emit_native_target(lines, next_address, blocks, "    ")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate statically reachable 8086 COM blocks to native C"
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
