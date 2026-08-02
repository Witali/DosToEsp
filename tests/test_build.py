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
        assert "addi a4, a4, 1" in assembly
        assert "does not yet materialize live ADD flags" not in assembly
        assert ".Lprogram_region_block_0100:" in assembly
        assert ".Lprogram_region_block_010b:" in assembly
        assert ".Lprogram_region_block_0119:" in assembly
        assert "fused with preceding CMP" in assembly
        assert "bne a4, a5, .Lprogram_region_fused_branch_taken_" in assembly
        assert assembly.count(".Lprogram_region_budget_finish:") == 1
        assert assembly.count("j .Lprogram_region_budget_finish") == len(blocks)
        assert assembly.count(".Lprogram_region_untranslated:") == 1

        literal_emitter = d2e_xtensa._Emitter("com", 0x1000)
        shared_literal = literal_emitter.literal(0x1234, "first")
        assert literal_emitter.literal(0x100001234, "second") == shared_literal
        assert literal_emitter.literals == [(shared_literal, 0x1234)]
        assert d2e_xtensa._emit_load_constant(
            literal_emitter, "a4", 2047, "small"
        ) == ["    movi a4, 2047"]
        assert d2e_xtensa._emit_load_constant(
            literal_emitter, "a5", -2048, "negative"
        ) == ["    movi a5, -2048"]
        large_load = d2e_xtensa._emit_load_constant(
            literal_emitter, "a8", 0x3456, "large"
        )
        assert large_load == [
            "    l32r a8, .Lprogram_region_large_1"
        ]
        assert d2e_xtensa._emit_load_constant(
            literal_emitter, "a9", 0x3456, "duplicate"
        ) == ["    l32r a9, .Lprogram_region_large_1"]
        assert literal_emitter.literals == [
            (shared_literal, 0x1234),
            (".Lprogram_region_large_1", 0x3456),
        ]

        repeated_immediate_fixture = bytes.fromhex(
            "b8 34 12 bb 34 12 b9 07 00 ba 07 00 f4"
        )
        repeated_decoded = d2e_translate.discover(
            repeated_immediate_fixture, 0x100, 0x100
        )
        repeated_blocks = d2e_translate.make_blocks(repeated_decoded, 0x100)
        repeated_assembly = d2e_xtensa.emit_program(
            repeated_immediate_fixture,
            repeated_blocks,
            "repeated_immediate",
            0x1000,
            0x100,
        )
        assert repeated_assembly.count("    .long 0x00001234") == 1
        assert repeated_assembly.count("    movi a4, 7") == 2
        assert "    .long 0x00000007" not in repeated_assembly

        cached_fixture = bytes.fromhex(
            "01 d8 01 c8 89 c2 f4"
        )  # add ax,bx; add ax,cx; mov dx,ax; hlt
        cached_decoded = d2e_translate.discover(cached_fixture, 0x100, 0x100)
        cached_blocks = d2e_translate.make_blocks(cached_decoded, 0x100)
        cached_assembly = d2e_xtensa.emit_program(
            cached_fixture,
            cached_blocks,
            "cached_registers",
            0x1000,
            0x100,
        )
        assert (
            "/* Register-cache selection: 1 runs, estimated 4 Xtensa "
            "instructions and 3 CPU accesses saved. */"
        ) in cached_assembly
        assert (
            "/* Register cache: AX=a4, BX=a5, CX=a8, DX=a9; estimated "
            "saving 4 instructions, 3 CPU accesses. */"
        ) in cached_assembly
        assert "l16ui a4, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in cached_assembly
        assert "l16ui a5, a2, D2E_ASM_CPU_REGS_OFFSET + 6" in cached_assembly
        assert "l16ui a8, a2, D2E_ASM_CPU_REGS_OFFSET + 2" in cached_assembly
        assert "add a4, a4, a5" in cached_assembly
        assert "add a4, a4, a8" in cached_assembly
        assert "mov a9, a4" in cached_assembly
        assert "s16i a4, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in cached_assembly
        assert "s16i a9, a2, D2E_ASM_CPU_REGS_OFFSET + 4" in cached_assembly
        assert "extui a4, a4, 0, 16" not in cached_assembly

        fused_fixture = bytes.fromhex(
            "89 c2 01 da f4"
        )  # mov dx,ax; add dx,bx; hlt
        fused_decoded = d2e_translate.discover(fused_fixture, 0x100, 0x100)
        fused_blocks = d2e_translate.make_blocks(fused_decoded, 0x100)
        fused_assembly = d2e_xtensa.emit_program(
            fused_fixture,
            fused_blocks,
            "fused_registers",
            0x1000,
            0x100,
        )
        assert "/* 0102: add dx, bx; fused with preceding MOV. */" in (
            fused_assembly
        )
        assert "add a5, a4, a8" in fused_assembly
        assert "mov a5, a4" not in fused_assembly
        assert "extui a5, a5, 0, 16" not in fused_assembly

        fused_immediate_fixture = bytes.fromhex(
            "89 c2 83 c2 05 f4"
        )  # mov dx,ax; add dx,5; hlt
        fused_immediate_decoded = d2e_translate.discover(
            fused_immediate_fixture, 0x100, 0x100
        )
        fused_immediate_blocks = d2e_translate.make_blocks(
            fused_immediate_decoded, 0x100
        )
        fused_immediate_assembly = d2e_xtensa.emit_program(
            fused_immediate_fixture,
            fused_immediate_blocks,
            "fused_immediate_registers",
            0x1000,
            0x100,
        )
        assert "addi a5, a4, 5" in fused_immediate_assembly
        assert "mov a5, a4" not in fused_immediate_assembly

        fused_alias_fixture = bytes.fromhex(
            "89 c2 01 d2 f4"
        )  # mov dx,ax; add dx,dx; hlt
        fused_alias_decoded = d2e_translate.discover(
            fused_alias_fixture, 0x100, 0x100
        )
        fused_alias_blocks = d2e_translate.make_blocks(
            fused_alias_decoded, 0x100
        )
        fused_alias_assembly = d2e_xtensa.emit_program(
            fused_alias_fixture,
            fused_alias_blocks,
            "fused_alias_registers",
            0x1000,
            0x100,
        )
        assert "add a5, a4, a4" in fused_alias_assembly
        assert "add a5, a4, a5" not in fused_alias_assembly

        fused_operations_fixture = bytes.fromhex(
            "89 c2 29 da "
            "89 c2 21 da "
            "89 c2 09 da "
            "89 c2 31 da "
            "89 c2 4a "
            "89 c2 83 e2 1f "
            "f4"
        )
        fused_operations_decoded = d2e_translate.discover(
            fused_operations_fixture, 0x100, 0x100
        )
        fused_operations_blocks = d2e_translate.make_blocks(
            fused_operations_decoded, 0x100
        )
        fused_operations_assembly = d2e_xtensa.emit_program(
            fused_operations_fixture,
            fused_operations_blocks,
            "fused_operations",
            0x1000,
            0x100,
        )
        assert "sub a5, a4, a8" in fused_operations_assembly
        assert "and a5, a4, a8" in fused_operations_assembly
        assert "or a5, a4, a8" in fused_operations_assembly
        assert "xor a5, a4, a8" in fused_operations_assembly
        assert "addi a5, a4, -1" in fused_operations_assembly
        assert "extui a5, a4, 0, 5" in fused_operations_assembly

        fused_shift_fixture = bytes.fromhex(
            "89 c2 d1 e2 "  # mov dx,ax; shl dx,1
            "89 c2 d1 ea "  # mov dx,ax; shr dx,1
            "f4"
        )
        fused_shift_decoded = d2e_translate.discover(
            fused_shift_fixture, 0x100, 0x100
        )
        fused_shift_blocks = d2e_translate.make_blocks(
            fused_shift_decoded, 0x100
        )
        fused_shift_assembly = d2e_xtensa.emit_program(
            fused_shift_fixture,
            fused_shift_blocks,
            "fused_shifts",
            0x1000,
            0x100,
        )
        assert "slli a5, a4, 1" in fused_shift_assembly
        assert "extui a5, a4, 1, 15" in fused_shift_assembly
        assert "mov a5, a4" not in fused_shift_assembly

        fused_scaled_add_fixture = bytes.fromhex("d1 e0 01 d8 f4")
        fused_scaled_add_decoded = d2e_translate.discover(
            fused_scaled_add_fixture, 0x100, 0x100
        )
        fused_scaled_add_blocks = d2e_translate.make_blocks(
            fused_scaled_add_decoded, 0x100
        )
        fused_scaled_add_assembly = d2e_xtensa.emit_program(
            fused_scaled_add_fixture,
            fused_scaled_add_blocks,
            "fused_scaled_add",
            0x1000,
            0x100,
        )
        assert "/* 0102: add ax, bx; fused with preceding SHL. */" in (
            fused_scaled_add_assembly
        )
        assert "addx2 a4, a4, a5" in fused_scaled_add_assembly
        assert "slli a4, a4, 1" not in fused_scaled_add_assembly

        fused_scaled_alias_fixture = bytes.fromhex("d1 e0 01 c0 f4")
        fused_scaled_alias_decoded = d2e_translate.discover(
            fused_scaled_alias_fixture, 0x100, 0x100
        )
        fused_scaled_alias_blocks = d2e_translate.make_blocks(
            fused_scaled_alias_decoded, 0x100
        )
        fused_scaled_alias_assembly = d2e_xtensa.emit_program(
            fused_scaled_alias_fixture,
            fused_scaled_alias_blocks,
            "fused_scaled_alias",
            0x1000,
            0x100,
        )
        assert "slli a4, a4, 2" in fused_scaled_alias_assembly
        assert "addx2 a4, a4, a4" not in fused_scaled_alias_assembly

        uncached_fixture = bytes.fromhex("89 d8 f4")  # mov ax,bx; hlt
        uncached_decoded = d2e_translate.discover(
            uncached_fixture, 0x100, 0x100
        )
        uncached_blocks = d2e_translate.make_blocks(uncached_decoded, 0x100)
        uncached_assembly = d2e_xtensa.emit_program(
            uncached_fixture,
            uncached_blocks,
            "uncached_registers",
            0x1000,
            0x100,
        )
        assert (
            "/* Register-cache selection: 0 runs, estimated 0 Xtensa "
            "instructions and 0 CPU accesses saved. */"
        ) in uncached_assembly
        assert "/* Register cache:" not in uncached_assembly

        live_add_fixture = bytes.fromhex(
            "01 d8 74 01 f4 f4"
        )  # add ax,bx; jz taken
        live_add_decoded = d2e_translate.discover(
            live_add_fixture, 0x100, 0x100
        )
        live_add_blocks = d2e_translate.make_blocks(live_add_decoded, 0x100)
        live_add_assembly = d2e_xtensa.emit_program(
            live_add_fixture,
            live_add_blocks,
            "live_add_registers",
            0x1000,
            0x100,
        )
        assert "/* Register cache:" not in live_add_assembly
        assert "s16i a8, a2, D2E_ASM_CPU_FLAGS_OFFSET" in live_add_assembly

        fused_compare_fixture = bytes.fromhex("39 d8 72 01 f4 f4")
        fused_compare_decoded = d2e_translate.discover(
            fused_compare_fixture, 0x100, 0x100
        )
        fused_compare_blocks = d2e_translate.make_blocks(
            fused_compare_decoded, 0x100
        )
        fused_compare_assembly = d2e_xtensa.emit_program(
            fused_compare_fixture,
            fused_compare_blocks,
            "fused_compare_branch",
            0x1000,
            0x100,
        )
        assert "/* 0102: jb 0x105; fused with preceding CMP. */" in (
            fused_compare_assembly
        )
        assert "bltu a4, a5, .Lprogram_region_fused_branch_taken_" in (
            fused_compare_assembly
        )
        assert "D2E_ASM_CPU_FLAGS_OFFSET" not in fused_compare_assembly

        fused_test_fixture = bytes.fromhex("85 d8 74 01 f4 f4")
        fused_test_decoded = d2e_translate.discover(
            fused_test_fixture, 0x100, 0x100
        )
        fused_test_blocks = d2e_translate.make_blocks(
            fused_test_decoded, 0x100
        )
        fused_test_assembly = d2e_xtensa.emit_program(
            fused_test_fixture,
            fused_test_blocks,
            "fused_test_branch",
            0x1000,
            0x100,
        )
        assert "/* 0102: je 0x105; fused with preceding TEST. */" in (
            fused_test_assembly
        )
        assert "and a4, a4, a5" in fused_test_assembly
        assert "beqz a4, .Lprogram_region_fused_branch_taken_" in (
            fused_test_assembly
        )
        assert "D2E_ASM_CPU_FLAGS_OFFSET" not in fused_test_assembly

        for opcode, expected in ((0x76, "bgeu a5, a4"), (0x77, "bltu a5, a4")):
            fixture = bytes((0x39, 0xD8, opcode, 0x01, 0xF4, 0xF4))
            decoded = d2e_translate.discover(fixture, 0x100, 0x100)
            blocks = d2e_translate.make_blocks(decoded, 0x100)
            order_assembly = d2e_xtensa.emit_program(
                fixture,
                blocks,
                "fused_order_branch",
                0x1000,
                0x100,
            )
            assert expected in order_assembly
            assert "D2E_ASM_CPU_FLAGS_OFFSET" not in order_assembly

        live_compare_flags_fixture = bytes.fromhex(
            "39 d8 74 02 9c f4 9c f4"
        )
        live_compare_flags_decoded = d2e_translate.discover(
            live_compare_flags_fixture, 0x100, 0x100
        )
        live_compare_flags_blocks = d2e_translate.make_blocks(
            live_compare_flags_decoded, 0x100
        )
        live_compare_flags_assembly = d2e_xtensa.emit_program(
            live_compare_flags_fixture,
            live_compare_flags_blocks,
            "live_compare_flags",
            0x1000,
            0x100,
        )
        assert "fused with preceding CMP" not in live_compare_flags_assembly
        assert "D2E_ASM_CPU_FLAGS_OFFSET" in live_compare_flags_assembly

        live_immediate_add_fixture = bytes.fromhex(
            "83 c0 01 74 01 f4 f4"
        )  # add ax,1; jz taken
        live_immediate_add_decoded = d2e_translate.discover(
            live_immediate_add_fixture, 0x100, 0x100
        )
        live_immediate_add_blocks = d2e_translate.make_blocks(
            live_immediate_add_decoded, 0x100
        )
        live_immediate_add_assembly = d2e_xtensa.emit_program(
            live_immediate_add_fixture,
            live_immediate_add_blocks,
            "live_immediate_add",
            0x1000,
            0x100,
        )
        assert "addi a4, a4, 1" in live_immediate_add_assembly
        assert "movi a5, 1" not in live_immediate_add_assembly
        assert "l32r a5, .Lprogram_region_immediate" not in (
            live_immediate_add_assembly
        )

        full_flags_add_fixture = bytes.fromhex(
            "00 d8 9c f4"
        )  # add al,bl; pushf; hlt
        output = pathlib.Path(temporary) / "asm-direct-full-flags-add"
        manifest = d2e_build.build_sources(
            full_flags_add_fixture,
            "direct-full-flags-add.com",
            "com",
            "direct_full_flags_add",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        assert manifest["generated_sources"] == ["game_native.S"]
        full_flags_add_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: add al, bl */" in full_flags_add_assembly
        assert "call8 d2e_x86_add8" in full_flags_add_assembly
        assert "s8i a10, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in (
            full_flags_add_assembly
        )

        memory_add_fixture = bytes.fromhex(
            "83 06 08 01 01 f4 00 00 34 12"
        )  # add word ptr [0108h],1; hlt; data
        output = pathlib.Path(temporary) / "asm-direct-memory-add"
        manifest = d2e_build.build_sources(
            memory_add_fixture,
            "direct-memory-add.com",
            "com",
            "direct_memory_add",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        assert manifest["generated_sources"] == ["game_native.S"]
        memory_add_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "call8 d2e_native_helper_read16" in memory_add_assembly
        assert "call8 d2e_native_helper_write16" in memory_add_assembly
        assert "add a4, a4, a5" in memory_add_assembly
        assert "0x34, 0x12" in memory_add_assembly

        carry_zero_add_fixture = bytes.fromhex(
            "01 d8 76 01 f4 f4"
        )  # add ax,bx; jbe taken
        output = pathlib.Path(temporary) / "asm-direct-carry-zero-add"
        manifest = d2e_build.build_sources(
            carry_zero_add_fixture,
            "direct-carry-zero-add.com",
            "com",
            "direct_carry_zero_add",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        carry_zero_add_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert ".Lprogram_region_add_carry_done_" in carry_zero_add_assembly
        assert ".Lprogram_region_add_zero_done_" in carry_zero_add_assembly
        assert "call8 d2e_x86_add16" not in carry_zero_add_assembly

        pressure_fixture = bytes.fromhex(
            "01 d8 01 c8 01 d0 01 f0 f4"
        )  # four ADDs touch five x86 registers
        pressure_decoded = d2e_translate.discover(
            pressure_fixture, 0x100, 0x100
        )
        pressure_blocks = d2e_translate.make_blocks(pressure_decoded, 0x100)
        pressure_block = list(pressure_blocks[0x100])
        pressure_liveness = d2e_flags.analyze(pressure_blocks)
        pressure_runs, pressure_score = d2e_xtensa._plan_cached_register_runs(
            pressure_block, pressure_liveness.live_defined
        )
        assert pressure_score == (8, 4)
        assert set(pressure_runs) == {0, 1}
        assert pressure_runs[0][0] == 1
        assert pressure_runs[1][0] == 4

        dispatch_probe_emitter = d2e_xtensa._Emitter("com", 0x1000)
        dispatch_probe_leaders = tuple(range(0x100, 0x111))
        dispatch_probe_literals = {
            leader: dispatch_probe_emitter.literal(leader, "leader")
            for leader in dispatch_probe_leaders
        }
        dispatch_probe = "\n".join(
            d2e_xtensa._emit_dispatch_tree(
                dispatch_probe_emitter,
                dispatch_probe_leaders,
                dispatch_probe_literals,
            )
        )
        assert ".Lprogram_region_dispatch_left_" in dispatch_probe
        assert "bltu a4, a5, .Lprogram_region_dispatch_left_" in dispatch_probe

        hash_probe_leaders = tuple(range(0x100, 0x201))
        hash_probe_literals = {
            leader: dispatch_probe_emitter.literal(leader, "leader")
            for leader in hash_probe_leaders
        }
        hash_probe, hash_labels, hash_shift, hash_maximum_load = (
            d2e_xtensa._emit_hash_dispatch(
                dispatch_probe_emitter,
                hash_probe_leaders,
                hash_probe_literals,
            )
        )
        hash_probe_text = "\n".join(hash_probe)
        assert len(hash_labels) == 32
        assert 1 <= hash_shift <= 16
        assert hash_maximum_load <= 16
        assert "    jx a5" in hash_probe_text
        for leader in hash_probe_leaders:
            assert hash_probe_text.count(
                f"beq a4, a5, .Lprogram_region_block_{leader:04x}"
            ) == 1

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

        mixed_fixture = bytes.fromhex("27 eb 00 f4")
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
        assert "mov a12, a4 /* already computed module target */" in mixed_assembly
        assert "/* 0103: hlt  */" in mixed_assembly
        assert ".byte 0x27" not in mixed_assembly
        assert ".byte 0xeb" not in mixed_assembly
        assert ".byte 0xf4" not in mixed_assembly
        assert "d2e_generated_cisc_region_000" in mixed_cisc
        assert "uint32_t d2e_generated_cisc_region_000" in mixed_region
        assert (
            "static uint32_t d2e_generated_cisc_region_000"
            not in mixed_region
        )
        assert "r_ax = d2e_x86_daa(cpu, r_ax);" in mixed_region
        assert "block_0103:" not in mixed_region
        assert "UINT32_C(1)" not in mixed_cisc
        assert "uint32_t step;" not in mixed_cisc
        assert (
            "d2e_generated_cisc_step(d2e_x86_cpu *cpu, uint32_t retired, "
            "uint32_t module_target)"
        ) in mixed_cisc
        assert "const uint32_t module_target = cpu->ip;" not in mixed_cisc
        assert "d2e_generated_cisc_region_000(cpu, module_target)" in mixed_cisc
        assert (
            "d2e_generated_cisc_region_000(d2e_x86_cpu *cpu, "
            "uint32_t module_target)"
        ) in mixed_region
        assert "switch (module_target)" in mixed_region
        assert "uint32_t block_budget" not in mixed_region
        assert "executed >= block_budget" not in mixed_region
        assert mixed_region.count("goto dispatch;") == 1
        assert "uint32_t retired = 0;" in mixed_region
        assert "return (retired << 1U) | executed;" in mixed_region
        assert "cpu->instructions_retired += retired;" not in mixed_region
        assert "srli a7, a4, 1" in mixed_assembly
        assert "extui a10, a4, 0, 1" in mixed_assembly

        fallback_image = bytes([0x27] * 257)
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

        direct_call_fixture = bytes.fromhex("e8 01 00 f4 c3")
        output = pathlib.Path(temporary) / "asm-direct-call"
        manifest = d2e_build.build_sources(
            direct_call_fixture,
            "direct-call.com",
            "com",
            "direct_call",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_call_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: call 0x104 */" in direct_call_assembly
        assert "call8 d2e_native_helper_push_near_return" in direct_call_assembly
        assert "0x00000103" in direct_call_assembly
        assert "/* 0104: ret  */" in direct_call_assembly
        assert "call8 d2e_x86_pop16" in direct_call_assembly

        for fixture, expected_comment, expected_number in (
            (bytes.fromhex("cd 10 f4"), "/* 0100: int 0x10 */", 16),
            (bytes.fromhex("cc f4"), "/* 0100: int3  */", 3),
        ):
            output = pathlib.Path(temporary) / f"asm-direct-int-{expected_number}"
            manifest = d2e_build.build_sources(
                fixture,
                f"direct-int-{expected_number}.com",
                "com",
                f"direct_int_{expected_number}",
                0x1000,
                output,
                "xtensa-asm",
            )
            assert manifest["status"] == "complete"
            assert manifest["generated_sources"] == ["game_native.S"]
            direct_int_assembly = (output / "game_native.S").read_text(
                encoding="utf-8"
            )
            assert expected_comment in direct_int_assembly
            assert f"movi a11, {expected_number}" in direct_int_assembly
            assert "call8 d2e_native_interrupt" in direct_int_assembly
            assert "l32i a4, a2, D2E_ASM_CPU_STOP_REASON_OFFSET" in (
                direct_int_assembly
            )

        direct_port_fixture = bytes.fromhex(
            "e4 60 e5 61 ec ed e6 62 e7 63 ee ef f4"
        )
        output = pathlib.Path(temporary) / "asm-direct-port"
        manifest = d2e_build.build_sources(
            direct_port_fixture,
            "direct-port.com",
            "com",
            "direct_port",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        assert manifest["generated_sources"] == ["game_native.S"]
        direct_port_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "call8 d2e_x86_port_in8" in direct_port_assembly
        assert "call8 d2e_x86_port_in16" in direct_port_assembly
        assert "call8 d2e_x86_port_out8" in direct_port_assembly
        assert "call8 d2e_x86_port_out16" in direct_port_assembly
        assert "movi a11, 96" in direct_port_assembly
        assert "movi a11, 99" in direct_port_assembly
        assert direct_port_assembly.count(
            f"l16ui a11, a2, D2E_ASM_CPU_REGS_OFFSET + "
            f"{d2e_xtensa.REG16_OFFSETS['dx']}"
        ) == 4
        assert "s8i a10, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in (
            direct_port_assembly
        )
        assert "s16i a10, a2, D2E_ASM_CPU_REGS_OFFSET + 0" in (
            direct_port_assembly
        )

        direct_return_fixture = bytes.fromhex("c2 80 00")
        output = pathlib.Path(temporary) / "asm-direct-return"
        manifest = d2e_build.build_sources(
            direct_return_fixture,
            "direct-return.com",
            "com",
            "direct_return",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_return_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: ret 0x80 */" in direct_return_assembly
        assert "call8 d2e_x86_pop16" in direct_return_assembly
        assert "0x00000080" in direct_return_assembly
        assert "extui a4, a4, 0, 16" in direct_return_assembly

        direct_stack_fixture = bytes.fromhex("54 5b 1e 07 f4")
        output = pathlib.Path(temporary) / "asm-direct-stack"
        manifest = d2e_build.build_sources(
            direct_stack_fixture,
            "direct-stack.com",
            "com",
            "direct_stack",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_stack_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: push sp */" in direct_stack_assembly
        assert "addi a11, a11, -2 /* 8086 PUSH SP value */" in direct_stack_assembly
        assert direct_stack_assembly.count("call8 d2e_x86_push16") == 2
        assert direct_stack_assembly.count("call8 d2e_x86_pop16") == 2
        assert "D2E_ASM_X86_DS_INDEX" in direct_stack_assembly
        assert "D2E_ASM_X86_ES_INDEX" in direct_stack_assembly

        direct_flags_stack_fixture = bytes.fromhex("9c 9d f4")
        output = pathlib.Path(temporary) / "asm-direct-flags-stack"
        manifest = d2e_build.build_sources(
            direct_flags_stack_fixture,
            "direct-flags-stack.com",
            "com",
            "direct_flags_stack",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_flags_stack_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: pushf  */" in direct_flags_stack_assembly
        assert "/* 0101: popf  */" in direct_flags_stack_assembly
        assert "D2E_ASM_X86_FLAG_FIXED" in direct_flags_stack_assembly
        assert "0x00000fd5" in direct_flags_stack_assembly
        assert direct_flags_stack_assembly.count("call8 d2e_x86_push16") == 1
        assert direct_flags_stack_assembly.count("call8 d2e_x86_pop16") == 1

        direct_memory_stack_fixture = bytes.fromhex(
            "ff 36 09 01 8f 06 0b 01 f4 ef be 00 00"
        )
        output = pathlib.Path(temporary) / "asm-direct-memory-stack"
        manifest = d2e_build.build_sources(
            direct_memory_stack_fixture,
            "direct-memory-stack.com",
            "com",
            "direct_memory_stack",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_memory_stack_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: push word ptr [0x109] */" in direct_memory_stack_assembly
        assert "/* 0104: pop word ptr [0x10b] */" in direct_memory_stack_assembly
        assert "call8 d2e_native_helper_read16" in direct_memory_stack_assembly
        assert "call8 d2e_x86_push16" in direct_memory_stack_assembly
        assert "call8 d2e_x86_pop16" in direct_memory_stack_assembly
        assert "call8 d2e_native_helper_write16" in direct_memory_stack_assembly
        assert ".byte 0xef, 0xbe, 0x00, 0x00" in direct_memory_stack_assembly

        direct_byte_compare_fixture = bytes.fromhex(
            "80 3e 09 01 01 72 01 f4 f4 00"
        )
        output = pathlib.Path(temporary) / "asm-direct-byte-compare"
        manifest = d2e_build.build_sources(
            direct_byte_compare_fixture,
            "direct-byte-compare.com",
            "com",
            "direct_byte_compare",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_byte_compare_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: cmp byte ptr [0x109], 1 */" in direct_byte_compare_assembly
        assert "call8 d2e_native_helper_read8" in direct_byte_compare_assembly
        assert "movi a5, 1" in direct_byte_compare_assembly
        assert "call8 d2e_x86_sub8 /* CMP result discarded */" not in (
            direct_byte_compare_assembly
        )
        assert "D2E_ASM_CPU_FLAGS_OFFSET" in direct_byte_compare_assembly
        assert ".byte 0x00" in direct_byte_compare_assembly

        direct_byte_subtract_fixture = bytes.fromhex(
            "80 2e 06 01 01 f4 02"
        )
        output = pathlib.Path(temporary) / "asm-direct-byte-subtract"
        manifest = d2e_build.build_sources(
            direct_byte_subtract_fixture,
            "direct-byte-subtract.com",
            "com",
            "direct_byte_subtract",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_byte_subtract_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: sub byte ptr [0x106], 1 */" in (
            direct_byte_subtract_assembly
        )
        assert "call8 d2e_native_helper_read8" in direct_byte_subtract_assembly
        assert "call8 d2e_native_helper_write8" in direct_byte_subtract_assembly
        assert "addi a4, a4, -1" in direct_byte_subtract_assembly
        assert "movi a5, 1" not in direct_byte_subtract_assembly
        assert "call8 d2e_x86_sub8" not in direct_byte_subtract_assembly
        assert "extui a4, a4, 0, 8" in direct_byte_subtract_assembly
        assert ".byte 0x02" in direct_byte_subtract_assembly

        live_zero_subtract_fixture = bytes.fromhex("83 e8 01 74 01 f4 f4")
        output = pathlib.Path(temporary) / "asm-live-zero-subtract"
        manifest = d2e_build.build_sources(
            live_zero_subtract_fixture,
            "live-zero-subtract.com",
            "com",
            "live_zero_subtract",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        live_zero_subtract_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "addi a4, a4, -1" in live_zero_subtract_assembly
        assert "movi a5, 1" not in live_zero_subtract_assembly
        assert "D2E_ASM_CPU_FLAGS_OFFSET" in live_zero_subtract_assembly
        assert "call8 d2e_x86_sub16" not in live_zero_subtract_assembly

        live_carry_subtract_fixture = bytes.fromhex("83 e8 01 72 01 f4 f4")
        output = pathlib.Path(temporary) / "asm-live-carry-subtract"
        manifest = d2e_build.build_sources(
            live_carry_subtract_fixture,
            "live-carry-subtract.com",
            "com",
            "live_carry_subtract",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        live_carry_subtract_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "addi a4, a4, -1" not in live_carry_subtract_assembly
        assert "movi a5, 1" in live_carry_subtract_assembly
        assert "sub a4, a4, a5" in live_carry_subtract_assembly
        assert "call8 d2e_x86_sub16" not in live_carry_subtract_assembly

        direct_increment_fixture = bytes.fromhex("fe 06 05 01 f4 ff")
        output = pathlib.Path(temporary) / "asm-direct-increment"
        manifest = d2e_build.build_sources(
            direct_increment_fixture,
            "direct-increment.com",
            "com",
            "direct_increment",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_increment_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: inc byte ptr [0x105] */" in direct_increment_assembly
        assert "call8 d2e_native_helper_read8" in direct_increment_assembly
        assert "call8 d2e_native_helper_write8" in direct_increment_assembly
        assert "call8 d2e_x86_inc8" not in direct_increment_assembly
        assert "addi a4, a4, 1" in direct_increment_assembly
        assert ".byte 0xff" in direct_increment_assembly

        direct_logical_fixture = bytes.fromhex(
            "80 26 06 01 0f f4 ff"
        )
        output = pathlib.Path(temporary) / "asm-direct-logical"
        manifest = d2e_build.build_sources(
            direct_logical_fixture,
            "direct-logical.com",
            "com",
            "direct_logical",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_logical_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: and byte ptr [0x106], 0xf */" in direct_logical_assembly
        assert "call8 d2e_native_helper_read8" in direct_logical_assembly
        assert "call8 d2e_native_helper_write8" in direct_logical_assembly
        assert "call8 d2e_x86_logic8" not in direct_logical_assembly
        assert "movi a5, 15" in direct_logical_assembly
        assert ".byte 0xff" in direct_logical_assembly

        direct_test_fixture = bytes.fromhex(
            "f6 06 09 01 01 74 01 f4 f4 00"
        )
        output = pathlib.Path(temporary) / "asm-direct-test"
        manifest = d2e_build.build_sources(
            direct_test_fixture,
            "direct-test.com",
            "com",
            "direct_test",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_test_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: test byte ptr [0x109], 1 */" in direct_test_assembly
        assert "call8 d2e_native_helper_read8" in direct_test_assembly
        assert "call8 d2e_x86_logic8" not in direct_test_assembly
        assert "and a4, a4, a5" in direct_test_assembly
        assert "movi a9, -65" in direct_test_assembly

        direct_unary_fixture = bytes.fromhex(
            "f6 16 0f 01 f8 f5 f9 fc fd fa fb f4 00 00 00 ff"
        )
        output = pathlib.Path(temporary) / "asm-direct-unary"
        manifest = d2e_build.build_sources(
            direct_unary_fixture,
            "direct-unary.com",
            "com",
            "direct_unary",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_unary_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: not byte ptr [0x10f] */" in direct_unary_assembly
        assert "call8 d2e_native_helper_read8" in direct_unary_assembly
        assert "call8 d2e_native_helper_write8" in direct_unary_assembly
        assert "xor a4, a4, a5" in direct_unary_assembly
        assert "/* 0104: clc  */" in direct_unary_assembly
        assert "/* 0105: cmc  */" in direct_unary_assembly
        assert "/* 0106: stc  */" in direct_unary_assembly
        assert "/* 0107: cld  */" in direct_unary_assembly
        assert "/* 0108: std  */" in direct_unary_assembly
        assert "/* 0109: cli  */" in direct_unary_assembly
        assert "/* 010a: sti  */" in direct_unary_assembly
        assert "xori a4, a4, 1" in direct_unary_assembly

        direct_shift_fixture = bytes.fromhex(
            "d0 2e 0a 01 74 01 f4 f4 00 00 81"
        )
        output = pathlib.Path(temporary) / "asm-direct-shift"
        manifest = d2e_build.build_sources(
            direct_shift_fixture,
            "direct-shift.com",
            "com",
            "direct_shift",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_shift_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: shr byte ptr [0x10a], 1 */" in direct_shift_assembly
        assert "call8 d2e_x86_shr8" in direct_shift_assembly
        assert "call8 d2e_native_helper_write8" in direct_shift_assembly

        dead_shift_fixture = bytes.fromhex("d1 f8 b8 01 00 f4")
        output = pathlib.Path(temporary) / "asm-direct-dead-shift"
        manifest = d2e_build.build_sources(
            dead_shift_fixture,
            "direct-dead-shift.com",
            "com",
            "direct_dead_shift",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        dead_shift_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0100: sar ax, 1 */" in dead_shift_assembly
        assert "call8 d2e_x86_sar16" not in dead_shift_assembly
        assert "srai a4, a4, 17" in dead_shift_assembly

        direct_loop_fixture = bytes.fromhex("b9 02 00 e1 01 f4 f4")
        output = pathlib.Path(temporary) / "asm-direct-loop"
        manifest = d2e_build.build_sources(
            direct_loop_fixture,
            "direct-loop.com",
            "com",
            "direct_loop",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        direct_loop_assembly = (output / "game_native.S").read_text(
            encoding="utf-8"
        )
        assert "/* 0103: loope 0x106 */" in direct_loop_assembly
        assert "addi a4, a4, -1" in direct_loop_assembly
        assert "movi a8, 64" in direct_loop_assembly
        assert ".Lprogram_region_loop_not_taken_" in direct_loop_assembly

        dead_cisc_fixture = bytes.fromhex(
            "27 83 c0 01 d1 e0 f7 e3 f4"
        )
        output = pathlib.Path(temporary) / "asm-dead-cisc-flags"
        manifest = d2e_build.build_sources(
            dead_cisc_fixture,
            "dead-cisc-flags.com",
            "com",
            "dead_cisc_flags",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        dead_cisc_region = (output / "game_cisc_region_000.c").read_text(
            encoding="utf-8"
        )
        assert "d2e_x86_add16(" not in dead_cisc_region
        assert "d2e_x86_shl16(" not in dead_cisc_region
        assert "d2e_x86_mul16(" not in dead_cisc_region
        assert "(uint16_t)(r_ax) + (uint16_t)(UINT16_C(0x0001))" in dead_cisc_region
        assert "(uint16_t)(r_ax) << 1U" in dead_cisc_region
        assert "(uint32_t)(uint16_t)r_ax" in dead_cisc_region

        live_carry_fixture = bytes.fromhex("50 83 c0 01 83 d3 00 f4")
        output = pathlib.Path(temporary) / "asm-live-cisc-carry"
        manifest = d2e_build.build_sources(
            live_carry_fixture,
            "live-cisc-carry.com",
            "com",
            "live_cisc_carry",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        live_cisc_region = (output / "game_cisc_region_000.c").read_text(
            encoding="utf-8"
        )
        assert "d2e_x86_add16(" in live_cisc_region
        assert "d2e_x86_adc16(" not in live_cisc_region
        assert "D2E_X86_FLAG_CF" in live_cisc_region

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

        mixed_mz_module = bytes.fromhex("27 eb 00 f4")
        mixed_mz = bytearray(32 + len(mixed_mz_module))
        mixed_mz[:2] = b"MZ"
        struct.pack_into("<H", mixed_mz, 0x02, len(mixed_mz))
        struct.pack_into("<H", mixed_mz, 0x04, 1)
        struct.pack_into("<H", mixed_mz, 0x08, 2)
        mixed_mz[32:] = mixed_mz_module
        output = pathlib.Path(temporary) / "asm-mixed-mz"
        manifest = d2e_build.build_sources(
            bytes(mixed_mz),
            "mixed.exe",
            "auto",
            "mixed_mz",
            0x1000,
            output,
            "xtensa-asm",
        )
        assert manifest["status"] == "complete"
        mixed_mz_region = (output / "game_cisc_region_000.c").read_text(
            encoding="utf-8"
        )
        assert "uint32_t next_module_target = UINT32_MAX;" in mixed_mz_region
        assert "next_module_target = UINT32_C(0x00003);" in mixed_mz_region
        assert "if (next_module_target != UINT32_MAX)" in mixed_mz_region
        assert mixed_mz_region.count("cpu->ip = (uint16_t)(next_module_target -") == 1

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

        flags_program_fixture = bytes.fromhex("9c 9d f4")
        flags_program_decoded = d2e_translate.discover(
            flags_program_fixture, 0x100, 0x100
        )
        flags_program = d2e_translate.emit_program(
            flags_program_fixture,
            d2e_translate.make_blocks(flags_program_decoded, 0x100),
            "flags_program",
            0x1000,
            0x100,
        )
        control_program_fixture = bytes.fromhex("e8 01 00 f4 c3")
        control_program_decoded = d2e_translate.discover(
            control_program_fixture, 0x100, 0x100
        )
        control_program = d2e_translate.emit_program(
            control_program_fixture,
            d2e_translate.make_blocks(control_program_decoded, 0x100),
            "control_program",
            0x1000,
            0x100,
        )
        for generated_program in (flags_program, control_program):
            assert '#include "d2e/x86_control.h"' in generated_program
            assert "uint16_t d2e_x86_call_near(" not in generated_program
        assert "d2e_x86_push_flags(cpu, r_sp)" in flags_program
        assert "d2e_x86_pop_flags(cpu, r_sp)" in flags_program
        assert "d2e_x86_push_near_return(cpu, r_sp" in control_program
        assert "d2e_x86_return_near(cpu, r_sp" in control_program
        assert "cpu->flags = (uint16_t)((stack_value" not in flags_program

        register_call_fixture = bytes.fromhex("b80601ffd0f4")
        register_call_decoded = d2e_translate.discover(
            register_call_fixture, 0x100, 0x100
        )
        register_call_blocks = d2e_translate.make_blocks(
            register_call_decoded, 0x100
        )
        register_call_region = "\n".join(
            d2e_translate.emit_region(register_call_blocks, 0x1000)
        )
        assert (
            "    control_offset = (uint16_t)(r_ax);\n"
            "    r_sp = d2e_x86_push_near_return(cpu, r_sp,"
        ) in register_call_region

        register_jump_fixture = bytes.fromhex("ffe0")
        register_jump_decoded = d2e_translate.discover(
            register_jump_fixture, 0x100, 0x100
        )
        register_jump_blocks = d2e_translate.make_blocks(
            register_jump_decoded, 0x100
        )
        register_jump_region = "\n".join(
            d2e_translate.emit_region(register_jump_blocks, 0x1000)
        )
        assert (
            "    cpu->ip = (uint16_t)(r_ax);\n"
            "    goto dispatch;"
        ) in register_jump_region

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
