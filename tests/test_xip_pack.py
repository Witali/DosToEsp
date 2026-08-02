#!/usr/bin/env python3
"""Host tests for the standalone Xtensa XIP module builder."""

from __future__ import annotations

import pathlib
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import d2e_pack_xip


def main() -> None:
    imports = d2e_pack_xip.parse_imports(
        PROJECT_ROOT / "include" / "d2e" / "xip_imports.h"
    )
    assert len(imports) == 47
    assert sorted(imports.values()) == list(range(47))
    assert imports["d2e_native_interrupt"] == 5
    assert imports["d2e_x86_write8"] == 44
    assert imports["d2e_x86_port_in16"] == 45
    assert imports["d2e_x86_port_out16"] == 46
    assert d2e_pack_xip.align_up(0x10001, 0x10000) == 0x20000
    with tempfile.TemporaryDirectory() as directory:
        temporary = pathlib.Path(directory)
        try:
            d2e_pack_xip.build_xip_module(
                temporary,
                [],
                temporary / "missing-toolchain",
                temporary / "TEST.D2E",
                "TEST",
                "Test",
            )
        except ValueError as error:
            assert "Xtensa tool is missing" in str(error)
        else:
            raise AssertionError("missing Xtensa toolchain was accepted")
    print("XIP module packer tests passed")


if __name__ == "__main__":
    main()
