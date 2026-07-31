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

        mz = bytearray(33)
        mz[:2] = b"MZ"
        struct.pack_into("<H", mz, 0x02, len(mz))
        struct.pack_into("<H", mz, 0x04, 1)
        struct.pack_into("<H", mz, 0x08, 2)
        mz[32] = 0xF4
        output = pathlib.Path(temporary) / "mz"
        manifest = d2e_build.build_sources(
            bytes(mz), "tiny.exe", "auto", "tiny", 0x1000, output
        )
        assert manifest["status"] == "blocked"
        assert manifest["generated_sources"] == ["game_image.c"]
        assert manifest["blockers"] == [
            {
                "kind": "segmented_mz_codegen",
                "message": (
                    "native target keys must preserve CS:IP while using "
                    "linear MZ module offsets"
                ),
            }
        ]
    print("unified source build tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
