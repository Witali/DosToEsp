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
    assert len(imports) == 57
    assert sorted(imports.values()) == list(range(57))
    assert imports["d2e_native_interrupt"] == 5
    assert imports["d2e_x86_write8"] == 44
    assert imports["d2e_native_service_control_target"] == 45
    assert imports["d2e_native_helper_mul16"] == 46
    assert imports["d2e_x86_adc16"] == 47
    assert imports["d2e_x86_div16"] == 48
    assert imports["d2e_x86_div8"] == 49
    assert imports["d2e_x86_mul16"] == 50
    assert imports["d2e_x86_push_far_return"] == 51
    assert imports["d2e_x86_ror16"] == 52
    assert imports["d2e_x86_ror8"] == 53
    assert imports["d2e_x86_sbb16"] == 54
    assert imports["d2e_x86_port_in16"] == 55
    assert imports["d2e_x86_port_out16"] == 56
    assert d2e_pack_xip.align_up(0x10001, 0x10000) == 0x20000
    assert d2e_pack_xip.XTENSA_COMPILER_CALL_FLAGS == (
        "-mno-longcalls",
        "-Wa,--longcalls",
    )
    assert d2e_pack_xip.XTENSA_LINKER_RELAXATION_FLAGS == (
        "--relax",
        "--size-opt",
    )
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
