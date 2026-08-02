#!/usr/bin/env python3
"""Backward x86 flag-liveness analysis for native translation backends."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

CF = 1 << 0
PF = 1 << 2
AF = 1 << 4
ZF = 1 << 6
SF = 1 << 7
IF = 1 << 9
DF = 1 << 10
OF = 1 << 11

ARITHMETIC = CF | PF | AF | ZF | SF | OF
ARITHMETIC_WITHOUT_CF = ARITHMETIC & ~CF
STATUS = CF | PF | AF | ZF | SF | OF
ALL = STATUS | IF | DF

CONDITION_READS = {
    "jo": OF,
    "jno": OF,
    "jb": CF,
    "jc": CF,
    "jnae": CF,
    "jae": CF,
    "jnb": CF,
    "jnc": CF,
    "je": ZF,
    "jz": ZF,
    "jne": ZF,
    "jnz": ZF,
    "jbe": CF | ZF,
    "jna": CF | ZF,
    "ja": CF | ZF,
    "jnbe": CF | ZF,
    "js": SF,
    "jns": SF,
    "jp": PF,
    "jpe": PF,
    "jnp": PF,
    "jpo": PF,
    "jl": SF | OF,
    "jnge": SF | OF,
    "jge": SF | OF,
    "jnl": SF | OF,
    "jle": ZF | SF | OF,
    "jng": ZF | SF | OF,
    "jg": ZF | SF | OF,
    "jnle": ZF | SF | OF,
}


@dataclasses.dataclass(frozen=True)
class FlagEffects:
    reads: int = 0
    defines: int = 0


@dataclasses.dataclass(frozen=True)
class FlagLiveness:
    live_after: dict[int, int]
    live_defined: dict[int, int]
    block_live_in: dict[int, int]
    block_live_out: dict[int, int]


def effects(instruction: Any) -> FlagEffects:
    mnemonic = instruction.mnemonic
    if mnemonic in CONDITION_READS:
        return FlagEffects(reads=CONDITION_READS[mnemonic])
    if mnemonic in ("adc", "sbb"):
        return FlagEffects(reads=CF, defines=ARITHMETIC)
    if mnemonic in ("add", "sub", "cmp", "neg"):
        return FlagEffects(defines=ARITHMETIC)
    if mnemonic in ("and", "or", "xor", "test"):
        return FlagEffects(defines=ARITHMETIC)
    if mnemonic in ("inc", "dec"):
        return FlagEffects(defines=ARITHMETIC_WITHOUT_CF)
    if mnemonic in ("shl", "shr", "sar"):
        return FlagEffects(defines=CF | PF | ZF | SF | OF)
    if mnemonic in ("rol", "ror"):
        return FlagEffects(defines=CF | OF)
    if mnemonic in ("rcl", "rcr"):
        return FlagEffects(reads=CF, defines=CF | OF)
    if mnemonic == "mul":
        return FlagEffects(defines=CF | OF)
    if mnemonic == "aaa":
        return FlagEffects(reads=AF, defines=AF | CF)
    if mnemonic in ("clc", "cmc", "stc"):
        return FlagEffects(defines=CF)
    if mnemonic in ("cld", "std"):
        return FlagEffects(defines=DF)
    if mnemonic in ("cli", "sti"):
        return FlagEffects(defines=IF)
    if mnemonic == "pushf":
        return FlagEffects(reads=ALL)
    if mnemonic == "popf":
        return FlagEffects(defines=ALL)
    if mnemonic == "lahf":
        return FlagEffects(reads=STATUS)
    if mnemonic == "sahf":
        return FlagEffects(defines=STATUS)
    if mnemonic in ("loope", "loopne"):
        return FlagEffects(reads=ZF)
    if mnemonic in ("int", "iret"):
        return FlagEffects(reads=ALL)

    operation = mnemonic.removeprefix("rep ").removeprefix(
        "repne "
    ).removeprefix("repe ")
    if operation in ("movsb", "movsw", "stosb", "stosw", "lodsb", "lodsw"):
        return FlagEffects(reads=DF)
    if operation in ("scasb", "scasw"):
        repeat_reads = ZF if mnemonic.startswith(("repne ", "repe ")) else 0
        return FlagEffects(reads=DF | repeat_reads, defines=ARITHMETIC)

    if mnemonic in {
        "mov",
        "nop",
        "push",
        "pop",
        "in",
        "out",
        "xchg",
        "not",
        "cbw",
        "cwd",
        "jmp",
        "loop",
        "jcxz",
        "call",
        "ret",
        "retf",
        "ljmp",
        "hlt",
    }:
        return FlagEffects()

    # Until a mnemonic has an explicit contract, preserve every incoming flag.
    return FlagEffects(reads=ALL)


def _direct_target(instruction: Any) -> int | None:
    if len(instruction.operands) == 1 and instruction.operands[0][0] == "imm":
        return int(instruction.operands[0][1]) & 0xFFFF
    return None


def _successors(instruction: Any) -> tuple[int, ...]:
    mnemonic = instruction.mnemonic
    direct = _direct_target(instruction)
    if mnemonic == "jmp":
        if instruction.indirect_targets:
            return tuple(instruction.indirect_targets)
        return (direct,) if direct is not None else ()
    if mnemonic in CONDITION_READS or mnemonic in (
        "loop",
        "loope",
        "loopne",
        "jcxz",
    ):
        return (
            (direct, instruction.next_address)
            if direct is not None
            else (instruction.next_address,)
        )
    if mnemonic == "call":
        return (
            (direct, instruction.next_address)
            if direct is not None
            else (instruction.next_address,)
        )
    if mnemonic in ("ret", "retf", "iret", "ljmp", "hlt"):
        return ()
    return (instruction.next_address,)


def analyze(blocks: Mapping[int, Sequence[Any]]) -> FlagLiveness:
    """Compute live flags at every instruction and basic-block boundary."""
    leaders = set(blocks)
    block_use: dict[int, int] = {}
    block_defines: dict[int, int] = {}
    local_successors: dict[int, tuple[int, ...]] = {}
    external_live: dict[int, int] = {}

    for leader, sequence in blocks.items():
        defined = 0
        used = 0
        for instruction in sequence:
            contract = effects(instruction)
            used |= contract.reads & ~defined
            defined |= contract.defines
        block_use[leader] = used
        block_defines[leader] = defined

        if not sequence:
            local_successors[leader] = ()
            external_live[leader] = ALL
            continue
        final = sequence[-1]
        targets = _successors(final)
        local_successors[leader] = tuple(
            target for target in targets if target in leaders
        )
        has_external_edge = any(target not in leaders for target in targets)
        if final.mnemonic in ("ret", "retf", "iret", "ljmp"):
            has_external_edge = True
        # HLT has no subsequent guest consumer, so it does not force flags live.
        external_live[leader] = ALL if has_external_edge else 0

    live_in = {leader: 0 for leader in blocks}
    live_out = {leader: 0 for leader in blocks}
    changed = True
    while changed:
        changed = False
        for leader in reversed(sorted(blocks)):
            outgoing = external_live[leader]
            for successor in local_successors[leader]:
                outgoing |= live_in[successor]
            incoming = block_use[leader] | (
                outgoing & ~block_defines[leader]
            )
            if outgoing != live_out[leader] or incoming != live_in[leader]:
                live_out[leader] = outgoing
                live_in[leader] = incoming
                changed = True

    instruction_live_after: dict[int, int] = {}
    instruction_live_defined: dict[int, int] = {}
    for leader, sequence in blocks.items():
        live = live_out[leader]
        for instruction in reversed(sequence):
            contract = effects(instruction)
            instruction_live_after[instruction.address] = live
            instruction_live_defined[instruction.address] = contract.defines & live
            live = contract.reads | (live & ~contract.defines)

    return FlagLiveness(
        live_after=instruction_live_after,
        live_defined=instruction_live_defined,
        block_live_in=live_in,
        block_live_out=live_out,
    )
