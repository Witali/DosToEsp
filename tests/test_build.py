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
        assert manifest["generated_sources"] == ["game_native.c"]
        native = (output / "game_native.c").read_text(encoding="utf-8")
        assert "program_region" in native
        assert "D2E_NATIVE_IMAGE_COM" in native

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
        assert manifest["generated_sources"] == ["game_native.c"]
        assert manifest["blockers"] == []
        native = (output / "game_native.c").read_text(encoding="utf-8")
        assert "D2E_NATIVE_IMAGE_MZ" in native
        assert "switch (module_target)" in native
        assert ".entry_cs = UINT16_C(0x0000)" in native
        assert ".entry_ip = UINT16_C(0x0000)" in native
        assert "cpu->segments[D2E_X86_CS] - UINT16_C(0x1000)" in native

        partitions = d2e_translate.partition_blocks(
            {address: [] for address in range(257)}
        )
        assert len(partitions) == 2
        assert len(partitions[0]) == d2e_translate.MZ_REGION_BLOCK_LIMIT
        assert list(partitions[1]) == [256]
    print("unified source build tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
