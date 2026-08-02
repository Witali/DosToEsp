#!/usr/bin/env python3
"""Regression tests for the unified DOS executable source frontend."""

from __future__ import annotations

import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import d2e_analyze
import d2e_build
import d2e_flags
import d2e_translate
import d2e_xtensa


def main() -> int:
    fixture = d2e_analyze.read_hex(ROOT / "tests" / "fixtures" / "native_smoke.hex")
    with tempfile.TemporaryDirectory() as temporary:
        output = pathlib.Path(temporary) / "com"
        manifest = d2e_build.build_sources(
            fixture, "native_smoke.com", "com", "native_smoke", 0x1000, output
        )
        assert manifest["status"] == "complete"
        assert manifest["generated_sources"] == [
            "game_image.c",
            "game_native.c",
            "game_region_000.c",
        ]
        assert manifest["generated_headers"] == ["game_native.h"]
        assert manifest["generated_data"] == ["game_image.inc"]
        image_source = (output / "game_image.c").read_text(encoding="utf-8")
        assert '#include "game_image.inc"' in image_source
        assert "UINT8_C(0x" not in image_source
        assert (output / "game_image.inc").read_text(encoding="utf-8").startswith(
            "    UINT8_C(0x"
        )
        native = (output / "game_native.c").read_text(encoding="utf-8")
        assert "program_region" in native
        assert "D2E_NATIVE_IMAGE_COM" in native
        assert "block_0100:" not in native
        assert "block_0100:" in (output / "game_region_000.c").read_text(
            encoding="utf-8"
        )

        mz_module = d2e_analyze.read_hex(
            ROOT / "tests" / "fixtures" / "native_call.hex"
        )
        mz = bytearray(32 + len(mz_module))
        mz[:2] = b"MZ"
        struct.pack_into("<H", mz, 0x02, len(mz))
        struct.pack_into("<H", mz, 0x04, 1)
        struct.pack_into("<H", mz, 0x08, 2)
        mz[32:] = mz_module
        output = pathlib.Path(temporary) / "mz"
        manifest = d2e_build.build_sources(
            bytes(mz), "tiny.exe", "auto", "tiny", 0x1000, output
        )
        assert manifest["status"] == "complete"
        assert manifest["generated_sources"] == [
            "game_image.c",
            "game_native.c",
            "game_region_000.c",
        ]
        assert manifest["blockers"] == []
        assert manifest["generated_data"] == ["game_image.inc"]
        native = (output / "game_native.c").read_text(encoding="utf-8")
        assert "D2E_NATIVE_IMAGE_MZ" in native
        region = (output / "game_region_000.c").read_text(encoding="utf-8")
        assert "switch (module_target)" in region
        assert ".entry_cs = UINT16_C(0x0000)" in native
        assert ".entry_ip = UINT16_C(0x0000)" in native
        assert "cpu->segments[D2E_X86_CS] - UINT16_C(0x1000)" in region

        pattern_fixture = d2e_analyze.read_hex(
            ROOT / "tests" / "fixtures" / "native_string.hex"
        )
        output = pathlib.Path(temporary) / "patterns"
        manifest = d2e_build.build_sources(
            pattern_fixture,
            "patterns.com",
            "com",
            "patterns",
            0x1000,
            output,
        )
        assert manifest["status"] == "complete"
        region = (output / "game_region_000.c").read_text(encoding="utf-8")
        assert "d2e_pattern_copy8(" in region
        assert "d2e_pattern_fill16(" in region
        assert "d2e/native_patterns.h" in region

        relocated_module = bytes.fromhex("b8 10 00 8e d8 b8 00 4c cd 21")
        relocated_mz = bytearray(32 + len(relocated_module))
        relocated_mz[:2] = b"MZ"
        struct.pack_into("<H", relocated_mz, 0x02, len(relocated_mz))
        struct.pack_into("<H", relocated_mz, 0x04, 1)
        struct.pack_into("<H", relocated_mz, 0x06, 1)
        struct.pack_into("<H", relocated_mz, 0x08, 2)
        struct.pack_into("<H", relocated_mz, 0x18, 0x1C)
        struct.pack_into("<HH", relocated_mz, 0x1C, 1, 0)
        relocated_mz[32:] = relocated_module
        output = pathlib.Path(temporary) / "relocated-mz"
        manifest = d2e_build.build_sources(
            bytes(relocated_mz),
            "relocated.exe",
            "auto",
            "relocated",
            0x1000,
            output,
        )
        assert manifest["status"] == "complete"
        region = (output / "game_region_000.c").read_text(encoding="utf-8")
        image_source = (output / "game_image.c").read_text(encoding="utf-8")
        image_data = (output / "game_image.inc").read_text(encoding="utf-8")
        relocation_data = (output / "game_relocations.inc").read_text(
            encoding="utf-8"
        )
        assert "r_ax = (uint16_t)(UINT16_C(0x1010));" in region
        assert '#include "game_image.inc"' in image_source
        assert '#include "game_relocations.inc"' in image_source
        assert "UINT8_C(0x10), UINT8_C(0x00)" in image_data
        assert "{UINT16_C(0x0001), UINT16_C(0x0000)}" in relocation_data
        assert manifest["generated_data"] == [
            "game_image.inc",
            "game_relocations.inc",
        ]

        partitions = d2e_translate.partition_blocks(
            {address: [] for address in range(257)}
        )
        assert len(partitions) == 2
        assert len(partitions[0]) == d2e_translate.MZ_REGION_BLOCK_LIMIT
        assert list(partitions[1]) == [256]

        d2e_translate.require_8086_encoding(bytes.fromhex("f3 a4"), 0x0100)
        for outside_8086 in (
            "60",
            "68 34 12",
            "82 c0 01",
            "c1 e0 02",
            "c8 00 00 00",
            "d6",
            "0f 01 16 00 02",
            "66 90",
        ):
            try:
                d2e_translate.require_8086_encoding(
                    bytes.fromhex(outside_8086), 0x1234
                )
            except d2e_translate.TranslationError as error:
                assert "outside the Intel 8086 profile" in str(error)
            else:
                raise AssertionError(
                    f"accepted non-profile encoding: {outside_8086}"
                )

        asm_fixture = d2e_analyze.read_hex(
            ROOT / "tests" / "fixtures" / "native_asm_smoke.hex"
        )
        decoded = d2e_translate.discover(asm_fixture, 0x100, 0x100)
        blocks = d2e_translate.make_blocks(decoded, 0x100)
        assembly = d2e_xtensa.emit_program(
            asm_fixture, blocks, "native_asm_smoke", 0x1000, 0x100
        )
        assert ".global program_region" in assembly
        assert ".global d2e_generated_program" in assembly
        assert "call8 d2e_native_helper_read16" in assembly
        assert "call8 d2e_native_helper_write16" in assembly
        assert "(D2E_ASM_X86_DS_INDEX * 2)" in assembly
        assert "s16i a10, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in assembly
        assert "l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in assembly
        assert "s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + 6" in assembly
        assert "call8 d2e_native_helper_mul16" in assembly
        assert "l16ui a11, a2, D2E_ASM_CPU_REGS_OFFSET + 2" in assembly
        assert "movi a12, 0 /* no MUL flags are live */" in assembly
        assert "add a4, a4, a5" in assembly
        assert "does not yet materialize live ADD flags" not in assembly
        assert ".Lprogram_region_block_0100:" in assembly
        assert ".Lprogram_region_block_010b:" in assembly
        assert ".Lprogram_region_block_0119:" in assembly
        assert "movi a9, -65" in assembly
        assert "beqz a4, .Lprogram_region_branch_taken_" in assembly
        add_start = assembly.index("/* 0103: add ax, 1 */")
        cmp_start = assembly.index("/* 0106: cmp ax, 0x1235 */")
        assert "D2E_ASM_CPU_FLAGS_OFFSET" not in assembly[add_start:cmp_start]
        assert ".Lprogram_image" not in assembly
        assert ".Lprogram_fragments" in assembly
        assert ".long 29" in assembly
        assert ".byte 0x34, 0x12" in assembly
        assert ".byte 0xa1, 0x1d, 0x01" not in assembly
        assert ".long 0 /* full image omitted */" in assembly

        output = pathlib.Path(temporary) / "asm-com"
        manifest = d2e_build.build_sources(
            asm_fixture,
            "native_asm_smoke.com",
            "com",
            "native_asm_smoke",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        assert manifest["backend"] == "xtensa-asm"
        assert manifest["generated_sources"] == ["game_native.S"]
        assert manifest["generated_data"] == []
        assert (output / "game_native.S").read_text(encoding="utf-8") == assembly

        mixed_fixture = bytes.fromhex("50 eb 00 f4")
        output = pathlib.Path(temporary) / "asm-mixed"
        manifest = d2e_build.build_sources(
            mixed_fixture,
            "mixed.com",
            "com",
            "mixed",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        assert manifest["generated_sources"] == [
            "game_native.S",
            "game_cisc.c",
            "game_cisc_region_000.c",
        ]
        mixed_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        mixed_cisc = (output / "game_cisc.c").read_text(encoding="utf-8")
        mixed_region = (output / "game_cisc_region_000.c").read_text(
            encoding="utf-8"
        )
        assert ".extern d2e_generated_cisc_step" in mixed_assembly
        assert "call8 d2e_generated_cisc_step" in mixed_assembly
        assert "/* 0103: hlt  */" in mixed_assembly
        assert ".byte 0x50" not in mixed_assembly
        assert ".byte 0xeb" not in mixed_assembly
        assert ".byte 0xf4" not in mixed_assembly
        assert "d2e_generated_cisc_region_000" in mixed_cisc
        assert "uint32_t d2e_generated_cisc_region_000" in mixed_region
        assert (
            "static uint32_t d2e_generated_cisc_region_000"
            not in mixed_region
        )
        assert "r_sp = (uint16_t)(r_sp - UINT16_C(2));" in mixed_region
        assert "d2e_x86_write16_seg(" in mixed_region
        assert "r_sp, r_ax);" in mixed_region
        assert "block_0103:" not in mixed_region
        assert "UINT32_C(1)" not in mixed_cisc
        assert "uint32_t step;" not in mixed_cisc
        assert "const uint32_t module_target = cpu->ip;" in mixed_cisc
        assert "uint32_t block_budget" not in mixed_region
        assert "executed >= block_budget" not in mixed_region
        assert mixed_region.count("goto dispatch;") == 1

        fallback_image = bytes([0x50] * 257)
        fallback_decoded = d2e_translate.discover(
            fallback_image, 0x100, 0x100
        )
        fallback_blocks = {
            instruction.address: [instruction]
            for instruction in fallback_decoded.values()
        }
        fallback_files = d2e_translate.emit_xtensa_source_files(
            fallback_image,
            (),
            fallback_blocks,
            "fallback_router",
            "com",
            0x1000,
            0x100,
            0,
            0x100,
            0,
            0xfffe,
        )
        fallback_bridge = fallback_files["game_cisc.c"]
        assert "module_target <= UINT32_C(0x001ff)" in fallback_bridge
        assert "module_target <= UINT32_C(0x00200)" in fallback_bridge
        assert fallback_bridge.count("d2e_generated_cisc_region_000(") == 2
        assert fallback_bridge.count("d2e_generated_cisc_region_001(") == 2

        asm_mz_module = bytes.fromhex("b8 10 00 f4")
        asm_mz = bytearray(32 + len(asm_mz_module))
        asm_mz[:2] = b"MZ"
        struct.pack_into("<H", asm_mz, 0x02, len(asm_mz))
        struct.pack_into("<H", asm_mz, 0x04, 1)
        struct.pack_into("<H", asm_mz, 0x06, 1)
        struct.pack_into("<H", asm_mz, 0x08, 2)
        struct.pack_into("<H", asm_mz, 0x18, 0x1C)
        struct.pack_into("<HH", asm_mz, 0x1C, 1, 0)
        asm_mz[32:] = asm_mz_module
        output = pathlib.Path(temporary) / "asm-mz"
        manifest = d2e_build.build_sources(
            bytes(asm_mz),
            "tiny.exe",
            "auto",
            "tiny_mz",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        mz_assembly = (output / "game_native.S").read_text(encoding="utf-8")
        assert ".long 1 /* D2E_NATIVE_IMAGE_MZ */" in mz_assembly
        assert "add a4, a4, a5 /* module target */" in mz_assembly
        assert ".Lprogram_relocations" not in mz_assembly
        assert ".long 0 /* relocation_count */" in mz_assembly
        assert "0x00001010" in mz_assembly

        indexed_fixture = bytes.fromhex(
            "bb 07 01 be 02 00 8b 00 f4 34 12"
        )
        indexed_decoded = d2e_translate.discover(indexed_fixture, 0x100, 0x100)
        indexed_blocks = d2e_translate.make_blocks(indexed_decoded, 0x100)
        indexed_assembly = d2e_xtensa.emit_program(
            indexed_fixture,
            indexed_blocks,
            "indexed_memory",
            0x1000,
            0x100,
        )
        assert "D2E_ASM_CPU_REGS_OFFSET + 6" in indexed_assembly
        assert "D2E_ASM_CPU_REGS_OFFSET + 12" in indexed_assembly
        assert indexed_assembly.count("add a12, a12, a4") == 2
        assert "extui a12, a12, 0, 16" in indexed_assembly
        assert "(D2E_ASM_X86_DS_INDEX * 2)" in indexed_assembly
        assert ".long 9" in indexed_assembly
        assert ".byte 0x34, 0x12" in indexed_assembly

        byte_fixture = bytes.fromhex(
            "8a 1e 09 01 88 1e 09 01 f4 7f"
        )
        byte_decoded = d2e_translate.discover(byte_fixture, 0x100, 0x100)
        byte_blocks = d2e_translate.make_blocks(byte_decoded, 0x100)
        byte_assembly = d2e_xtensa.emit_program(
            byte_fixture,
            byte_blocks,
            "byte_memory",
            0x1000,
            0x100,
        )
        assert "call8 d2e_native_helper_read8" in byte_assembly
        assert "call8 d2e_native_helper_write8" in byte_assembly
        assert "s8i a10, a2, D2E_ASM_CPU_REGS_OFFSET + 6" in byte_assembly
        assert "l8ui a13, a2, D2E_ASM_CPU_REGS_OFFSET + 6" in byte_assembly
        assert ".byte 0x7f" in byte_assembly

        high_byte_fixture = bytes.fromhex("b4 12 f4")
        high_byte_decoded = d2e_translate.discover(
            high_byte_fixture, 0x100, 0x100
        )
        high_byte_blocks = d2e_translate.make_blocks(
            high_byte_decoded, 0x100
        )
        high_byte_assembly = d2e_xtensa.emit_program(
            high_byte_fixture,
            high_byte_blocks,
            "high_byte_register",
            0x1000,
            0x100,
        )
        assert "s8i a4, a2, D2E_ASM_CPU_REGS_OFFSET + 1" in high_byte_assembly

        segment_fixture = bytes.fromhex(
            "b8 34 12 8e d8 8c db f4"
        )
        segment_decoded = d2e_translate.discover(segment_fixture, 0x100, 0x100)
        segment_blocks = d2e_translate.make_blocks(segment_decoded, 0x100)
        segment_assembly = d2e_xtensa.emit_program(
            segment_fixture,
            segment_blocks,
            "segment_registers",
            0x1000,
            0x100,
        )
        assert (
            "s16i a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            "(D2E_ASM_X86_DS_INDEX * 2)"
        ) in segment_assembly
        assert (
            "l16ui a4, a2, D2E_ASM_CPU_SEGMENTS_OFFSET + "
            "(D2E_ASM_X86_DS_INDEX * 2)"
        ) in segment_assembly
        assert "s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + 6" in segment_assembly

        stack_fixture = bytes.fromhex("bd 07 01 8b 46 00 f4 34 12")
        stack_decoded = d2e_translate.discover(stack_fixture, 0x100, 0x100)
        stack_blocks = d2e_translate.make_blocks(stack_decoded, 0x100)
        stack_assembly = d2e_xtensa.emit_program(
            stack_fixture,
            stack_blocks,
            "stack_memory",
            0x1000,
            0x100,
        )
        assert "(D2E_ASM_X86_SS_INDEX * 2)" in stack_assembly

        c_default = d2e_translate.emit_program(
            asm_fixture, blocks, "native_asm_smoke", 0x1000, 0x100
        )
        assert c_default.startswith("/* Generated by tools/d2e_translate.py.")

        indirect_fixture = d2e_analyze.read_hex(
            ROOT / "tests" / "fixtures" / "native_indirect.hex"
        )
        indirect_decoded = d2e_translate.discover(indirect_fixture, 0x100, 0x100)
        indirect_blocks = d2e_translate.make_blocks(indirect_decoded, 0x100)
        indirect_jump = next(
            instruction
            for instruction in indirect_decoded.values()
            if instruction.indirect_table_entries
        )
        assert indirect_jump.indirect_table_entries == (0x117, 0x11B, 0x11F)
        indirect_assembly = d2e_xtensa.emit_program(
            indirect_fixture,
            indirect_blocks,
            "native_indirect",
            0x1000,
            0x100,
        )
        assert "/* 010c: jmp word ptr cs:[bx + 0x111] */" in indirect_assembly
        assert "movi a5, 0" in indirect_assembly
        assert "movi a5, 2" in indirect_assembly
        assert "movi a5, 4" in indirect_assembly
        assert ".Lprogram_region_jump_table_entry_" in indirect_assembly
        assert ".byte 0x17, 0x01, 0x1b, 0x01, 0x1f, 0x01" not in indirect_assembly
        retained_offsets = {
            offset + index
            for offset, data in d2e_xtensa.extract_data_fragments(
                indirect_fixture, indirect_blocks
            )
            for index in range(len(data))
        }
        for instruction in indirect_decoded.values():
            instruction_offset = instruction.address - 0x100
            assert all(
                offset not in retained_offsets
                for offset in range(
                    instruction_offset, instruction_offset + instruction.size
                )
            )
            if instruction.indirect_targets:
                table_offset = instruction.next_address - 0x100
                pattern_offset = instruction_offset - 9
                table_size = (indirect_fixture[pattern_offset + 2] + 1) * 2
                assert all(
                    offset not in retained_offsets
                    for offset in range(table_offset, table_offset + table_size)
                )

        dead_flags = bytes.fromhex("83 c0 01 f4")
        dead_decoded = d2e_translate.discover(dead_flags, 0x100, 0x100)
        dead_blocks = d2e_translate.make_blocks(dead_decoded, 0x100)
        dead_liveness = d2e_flags.analyze(dead_blocks)
        assert dead_liveness.live_defined[0x100] == 0

        carry_chain = bytes.fromhex("83 c0 01 83 d3 00 f4")
        carry_decoded = d2e_translate.discover(carry_chain, 0x100, 0x100)
        carry_blocks = d2e_translate.make_blocks(carry_decoded, 0x100)
        carry_liveness = d2e_flags.analyze(carry_blocks)
        assert carry_liveness.live_defined[0x100] == d2e_flags.CF
        assert carry_liveness.live_defined[0x103] == 0

        zero_branch = bytes.fromhex("83 f8 01 74 03 bb 01 00 f4")
        zero_decoded = d2e_translate.discover(zero_branch, 0x100, 0x100)
        zero_blocks = d2e_translate.make_blocks(zero_decoded, 0x100)
        zero_liveness = d2e_flags.analyze(zero_blocks)
        assert zero_liveness.live_defined[0x100] == d2e_flags.ZF

        observed_flags = bytes.fromhex("83 c0 01 9c f4")
        observed_decoded = d2e_translate.discover(observed_flags, 0x100, 0x100)
        observed_blocks = d2e_translate.make_blocks(observed_decoded, 0x100)
        observed_liveness = d2e_flags.analyze(observed_blocks)
        assert (
            observed_liveness.live_defined[0x100]
            == d2e_flags.ARITHMETIC
        )
    print("unified source build tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
