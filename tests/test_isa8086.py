#!/usr/bin/env python3
"""Table-driven audit of the documented Intel 8086 instruction set."""

from __future__ import annotations

import dataclasses
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "local_tools" / "python_packages"))

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

import d2e_translate


@dataclasses.dataclass(frozen=True)
class Case:
    label: str
    encoding: str
    mnemonic: str
    control: bool = False
    external: bool = False


CASES = (
    Case("mov-reg", "b8 34 12", "mov"),
    Case("mov-memory", "89 00", "mov"),
    Case("push", "50", "push"),
    Case("pop", "58", "pop"),
    Case("xchg", "93", "xchg"),
    Case("xlat", "d7", "xlatb"),
    Case("in-byte", "e4 60", "in"),
    Case("in-word", "e5 60", "in"),
    Case("in-byte-dx", "ec", "in"),
    Case("in-word-dx", "ed", "in"),
    Case("out-byte", "e6 60", "out"),
    Case("out-word", "e7 60", "out"),
    Case("out-byte-dx", "ee", "out"),
    Case("out-word-dx", "ef", "out"),
    Case("lea", "8d 00", "lea"),
    Case("lds", "c5 18", "lds"),
    Case("les", "c4 00", "les"),
    Case("lahf", "9f", "lahf"),
    Case("sahf", "9e", "sahf"),
    Case("pushf", "9c", "pushf"),
    Case("popf", "9d", "popf"),
    Case("add", "01 d8", "add"),
    Case("adc", "11 d8", "adc"),
    Case("inc", "40", "inc"),
    Case("aaa", "37", "aaa"),
    Case("daa", "27", "daa"),
    Case("sub", "29 d8", "sub"),
    Case("sbb", "19 d8", "sbb"),
    Case("dec", "48", "dec"),
    Case("neg", "f7 d8", "neg"),
    Case("cmp", "39 d8", "cmp"),
    Case("aas", "3f", "aas"),
    Case("das", "2f", "das"),
    Case("mul-byte", "f6 e3", "mul"),
    Case("mul-word", "f7 e3", "mul"),
    Case("imul-byte", "f6 eb", "imul"),
    Case("imul-word", "f7 eb", "imul"),
    Case("aam", "d4 0a", "aam"),
    Case("div-byte", "f6 f3", "div"),
    Case("div-word", "f7 f3", "div"),
    Case("idiv-byte", "f6 fb", "idiv"),
    Case("idiv-word", "f7 fb", "idiv"),
    Case("aad", "d5 0a", "aad"),
    Case("cbw", "98", "cbw"),
    Case("cwd", "99", "cwd"),
    Case("not", "f7 d3", "not"),
    Case("shl", "d1 e0", "shl"),
    Case("shr", "d1 e8", "shr"),
    Case("sar", "d1 f8", "sar"),
    Case("rol", "d1 c0", "rol"),
    Case("ror", "d1 c8", "ror"),
    Case("rcl", "d1 d0", "rcl"),
    Case("rcr", "d1 d8", "rcr"),
    Case("and", "21 d8", "and"),
    Case("test", "85 d8", "test"),
    Case("or", "09 d8", "or"),
    Case("xor", "31 d8", "xor"),
    Case("movsb", "a4", "movsb"),
    Case("movsw", "a5", "movsw"),
    Case("cmpsb", "a6", "cmpsb"),
    Case("cmpsw", "a7", "cmpsw"),
    Case("scasb", "ae", "scasb"),
    Case("scasw", "af", "scasw"),
    Case("lodsb", "ac", "lodsb"),
    Case("lodsw", "ad", "lodsw"),
    Case("stosb", "aa", "stosb"),
    Case("stosw", "ab", "stosw"),
    Case("rep-movsb", "f3 a4", "rep movsb"),
    Case("repe-cmpsb", "f3 a6", "repe cmpsb"),
    Case("repne-cmpsb", "f2 a6", "repne cmpsb"),
    Case("call-near", "e8 00 00", "call", control=True),
    Case("call-indirect", "ff d0", "call", control=True),
    Case("call-far", "9a 34 12 78 56", "lcall", control=True),
    Case("call-far-indirect", "ff 18", "lcall", control=True),
    Case("jmp-short", "eb 00", "jmp", control=True),
    Case("jmp-indirect", "ff e0", "jmp", control=True),
    Case("jmp-far", "ea 34 12 78 56", "ljmp", control=True),
    Case("jmp-far-indirect", "ff 28", "ljmp", control=True),
    Case("ret", "c3", "ret", control=True),
    Case("ret-immediate", "c2 04 00", "ret", control=True),
    Case("retf", "cb", "retf", control=True),
    Case("retf-immediate", "ca 04 00", "retf", control=True),
    Case("jo", "70 00", "jo", control=True),
    Case("jno", "71 00", "jno", control=True),
    Case("jb", "72 00", "jb", control=True),
    Case("jae", "73 00", "jae", control=True),
    Case("je", "74 00", "je", control=True),
    Case("jne", "75 00", "jne", control=True),
    Case("jbe", "76 00", "jbe", control=True),
    Case("ja", "77 00", "ja", control=True),
    Case("js", "78 00", "js", control=True),
    Case("jns", "79 00", "jns", control=True),
    Case("jp", "7a 00", "jp", control=True),
    Case("jnp", "7b 00", "jnp", control=True),
    Case("jl", "7c 00", "jl", control=True),
    Case("jge", "7d 00", "jge", control=True),
    Case("jle", "7e 00", "jle", control=True),
    Case("jg", "7f 00", "jg", control=True),
    Case("loopne", "e0 00", "loopne", control=True),
    Case("loope", "e1 00", "loope", control=True),
    Case("loop", "e2 00", "loop", control=True),
    Case("jcxz", "e3 00", "jcxz", control=True),
    Case("int", "cd 21", "int", control=True),
    Case("int3", "cc", "int3", control=True),
    Case("into", "ce", "into", control=True),
    Case("iret", "cf", "iret", control=True),
    Case("clc", "f8", "clc"),
    Case("cmc", "f5", "cmc"),
    Case("stc", "f9", "stc"),
    Case("cld", "fc", "cld"),
    Case("std", "fd", "std"),
    Case("cli", "fa", "cli"),
    Case("sti", "fb", "sti"),
    Case("hlt", "f4", "hlt", control=True),
    Case("wait", "9b", "wait", external=True),
    Case("nop", "90", "nop"),
    Case("lock-add", "f0 01 18", "add"),
    Case("esc", "d8 00", "fadd", external=True),
)


# These are verified coverage gaps, not accepted semantics. Each implementation
# change removes its labels and adds behavioral assertions before committing.
KNOWN_GAPS: set[str] = set()
KNOWN_XTENSA_DIRECT = {
    "call-near",
    "cmp",
    "hlt",
    "ja",
    "jae",
    "jb",
    "jbe",
    "je",
    "jmp-short",
    "jne",
    "mov-memory",
    "mov-reg",
    "mul-word",
    "nop",
    "pop",
    "popf",
    "push",
    "pushf",
    "ret",
    "ret-immediate",
}


def decode(case: Case) -> d2e_translate.Instruction:
    machine_code = bytes.fromhex(case.encoding)
    disassembler = Cs(CS_ARCH_X86, CS_MODE_16)
    disassembler.detail = True
    return d2e_translate.decode_one(disassembler, machine_code, 0x100, 0x100)


def translates(case: Case, instruction: d2e_translate.Instruction) -> bool:
    if case.external:
        return False
    try:
        if case.control:
            d2e_translate.emit_region({0x100: [instruction]}, 0x1000)
        else:
            d2e_translate.translate_data_instruction(instruction, cached=True)
    except d2e_translate.TranslationError:
        return False
    return True


def translates_to_xtensa(
    case: Case, instruction: d2e_translate.Instruction
) -> bool:
    if case.external:
        return False
    try:
        d2e_translate.d2e_xtensa.emit_program(
            bytes(instruction.next_address - 0x100),
            {0x100: [instruction]},
            "isa_probe",
            0x1000,
            0x100,
        )
    except d2e_translate.d2e_xtensa.BackendError:
        return False
    return True


def translates_to_mixed_xtensa(
    case: Case, instruction: d2e_translate.Instruction
) -> bool:
    if case.external:
        return False
    try:
        files = d2e_translate.emit_xtensa_source_files(
            bytes(instruction.next_address - 0x100),
            (),
            {0x100: [instruction]},
            "isa_probe",
            "com",
            0x1000,
            0x100,
            0,
            0x100,
            0,
            0xfffe,
        )
    except (
        d2e_translate.TranslationError,
        d2e_translate.d2e_xtensa.BackendError,
    ):
        return False
    return "game_native.S" in files


def main() -> int:
    gaps: set[str] = set()
    xtensa_gaps: set[str] = set()
    mixed_xtensa_gaps: set[str] = set()
    labels: set[str] = set()
    for case in CASES:
        assert case.label not in labels, case.label
        labels.add(case.label)
        instruction = decode(case)
        assert instruction.mnemonic == case.mnemonic, (
            case.label,
            instruction.mnemonic,
            instruction.op_str,
        )
        if not case.external and not translates(case, instruction):
            gaps.add(case.label)
        if not case.external and not translates_to_xtensa(case, instruction):
            xtensa_gaps.add(case.label)
        if not case.external and not translates_to_mixed_xtensa(
            case, instruction
        ):
            mixed_xtensa_gaps.add(case.label)

    assert gaps == KNOWN_GAPS, (
        f"8086 translation gap set changed; new={sorted(gaps - KNOWN_GAPS)}, "
        f"implemented={sorted(KNOWN_GAPS - gaps)}"
    )
    nonexternal = {case.label for case in CASES if not case.external}
    direct_xtensa = nonexternal - xtensa_gaps
    assert direct_xtensa == KNOWN_XTENSA_DIRECT, (
        "Xtensa direct-lowering set changed; "
        f"new={sorted(direct_xtensa - KNOWN_XTENSA_DIRECT)}, "
        f"lost={sorted(KNOWN_XTENSA_DIRECT - direct_xtensa)}"
    )
    assert not mixed_xtensa_gaps, sorted(mixed_xtensa_gaps)
    print(
        f"8086 ISA audit passed: {len(CASES)} canonical forms, "
        f"{len(gaps)} C gaps, {len(xtensa_gaps)} direct Xtensa fallbacks, "
        f"{len(mixed_xtensa_gaps)} mixed-backend gaps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
