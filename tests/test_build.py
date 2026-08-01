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
import d2e_translate


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
    print("unified source build tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
