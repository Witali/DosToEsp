#!/usr/bin/env python3
"""Pack a final relocatable Xtensa ELF into a D2EXIP1 Flash module."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import pathlib
import re
import subprocess
import struct
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER_SIZE = 256
FLASH_PAGE_SIZE = 0x10000
IROM_LINK_ADDRESS = 0
DROM_LINK_ADDRESS = 0x10000000
R_XTENSA_32 = 1
SHT_SYMTAB = 2
SHT_RELA = 4
XTENSA_COMPILER_CALL_FLAGS = ("-mno-longcalls", "-Wa,--longcalls")
XTENSA_LINKER_RELAXATION_FLAGS = ("--relax", "--size-opt")


@dataclasses.dataclass(frozen=True)
class Section:
    index: int
    name: str
    kind: int
    address: int
    offset: int
    size: int
    link: int
    entry_size: int


@dataclasses.dataclass(frozen=True)
class Symbol:
    name: str
    value: int
    size: int
    section_index: int


class Elf32:
    def __init__(self, data: bytes) -> None:
        if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
            raise ValueError("input is not a little-endian ELF32 file")
        section_offset = struct.unpack_from("<I", data, 32)[0]
        section_entry_size, section_count, names_index = struct.unpack_from(
            "<HHH", data, 46
        )
        if section_entry_size != 40 or section_count == 0:
            raise ValueError("unsupported ELF section table")
        raw_sections = []
        for index in range(section_count):
            offset = section_offset + index * section_entry_size
            if offset + 40 > len(data):
                raise ValueError("truncated ELF section table")
            raw_sections.append(struct.unpack_from("<IIIIIIIIII", data, offset))
        if names_index >= section_count:
            raise ValueError("invalid ELF section-name table")
        names_header = raw_sections[names_index]
        names = self._slice(data, names_header[4], names_header[5])
        self.data = data
        self.sections = []
        for index, header in enumerate(raw_sections):
            self.sections.append(
                Section(
                    index,
                    self._string(names, header[0]),
                    header[1],
                    header[3],
                    header[4],
                    header[5],
                    header[6],
                    header[9],
                )
            )
        self.by_name = {section.name: section for section in self.sections}
        self.symbols: list[Symbol] = []
        self.symbol_by_name: dict[str, Symbol] = {}
        symbol_tables = [s for s in self.sections if s.kind == SHT_SYMTAB]
        if len(symbol_tables) != 1:
            raise ValueError("ELF must contain one symbol table")
        symbol_table = symbol_tables[0]
        if symbol_table.link >= len(self.sections) or symbol_table.entry_size != 16:
            raise ValueError("unsupported ELF symbol table")
        string_section = self.sections[symbol_table.link]
        strings = self.section_data(string_section)
        symbols = self.section_data(symbol_table)
        for offset in range(0, len(symbols), 16):
            name_offset, value, size, _info, _other, section_index = (
                struct.unpack_from("<IIIBBH", symbols, offset)
            )
            symbol = Symbol(
                self._string(strings, name_offset), value, size, section_index
            )
            self.symbols.append(symbol)
            if symbol.name:
                self.symbol_by_name[symbol.name] = symbol

    @staticmethod
    def _slice(data: bytes, offset: int, size: int) -> bytes:
        if offset > len(data) or size > len(data) - offset:
            raise ValueError("ELF section is outside the file")
        return data[offset : offset + size]

    @staticmethod
    def _string(strings: bytes, offset: int) -> str:
        if offset >= len(strings):
            raise ValueError("invalid ELF string offset")
        end = strings.find(b"\0", offset)
        if end < 0:
            raise ValueError("unterminated ELF string")
        return strings[offset:end].decode("ascii")

    def section_data(self, section: Section) -> bytes:
        return self._slice(self.data, section.offset, section.size)


def align_up(value: int, alignment: int) -> int:
    return value + (-value % alignment)


def parse_imports(header: pathlib.Path) -> dict[str, int]:
    pattern = re.compile(
        r"X\(\s*(\d+),\s*[A-Z0-9_]+,\s*([a-zA-Z0-9_]+)\s*\)"
    )
    text = header.read_text(encoding="utf-8").replace("\\\n", "")
    imports = {
        match.group(2): int(match.group(1))
        for match in pattern.finditer(text)
    }
    if not imports:
        raise ValueError(f"no XIP imports found in {header}")
    return imports


def read_c_string(data: bytes, address: int, base: int) -> str:
    offset = address - base
    if offset < 0 or offset >= len(data):
        raise ValueError("program name points outside DROM")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated program name")
    return data[offset:end].decode("ascii")


def collect_relocations(
    elf: Elf32, irom: Section, drom: Section, imports: dict[str, int]
) -> list[tuple[int, int, int, int, int]]:
    records: list[tuple[int, int, int, int, int]] = []
    for section in elf.sections:
        if section.kind != SHT_RELA or section.name not in (
            ".rela.irom",
            ".rela.drom",
        ):
            continue
        if section.link >= len(elf.sections) or section.entry_size != 12:
            raise ValueError(f"unsupported relocation section {section.name}")
        patch_section = irom if section.name == ".rela.irom" else drom
        for offset in range(0, section.size, 12):
            patch_address, info, addend = struct.unpack_from(
                "<IIi", elf.section_data(section), offset
            )
            relocation_kind = info & 0xFF
            if relocation_kind != R_XTENSA_32:
                continue
            symbol_index = info >> 8
            if symbol_index >= len(elf.symbols):
                raise ValueError("invalid relocation symbol index")
            symbol = elf.symbols[symbol_index]
            patch_offset = patch_address - patch_section.address
            if patch_offset < 0 or patch_offset + 4 > patch_section.size:
                raise ValueError("relocation patch points outside mapped segment")
            linked_value = struct.unpack_from(
                "<I", elf.section_data(patch_section), patch_offset
            )[0]
            if symbol.section_index == irom.index:
                target_kind = 0
                target = linked_value - irom.address
                target_addend = 0
            elif symbol.section_index == drom.index:
                target_kind = 1
                target = linked_value - drom.address
                target_addend = 0
            elif symbol.section_index == 0:
                if symbol.name not in imports:
                    raise ValueError(f"symbol is not in shell import ABI: {symbol.name}")
                target_kind = 2
                target = imports[symbol.name]
                target_addend = addend
            else:
                raise ValueError(
                    f"R_XTENSA_32 target is not IROM, DROM, or import: {symbol.name}"
                )
            if target < 0 or target > 0xFFFFFFFF:
                raise ValueError("relocation target is outside uint32 range")
            records.append(
                (patch_section.index, patch_offset, target_kind, target,
                 target_addend)
            )
    return records


def pack_module(
    elf_data: bytes, command: str, title: str, imports_header: pathlib.Path
) -> bytes:
    command = command.upper()
    if not re.fullmatch(r"[A-Z0-9_]{1,8}", command):
        raise ValueError("command must contain one to eight DOS-style characters")
    elf = Elf32(elf_data)
    try:
        irom = elf.by_name[".irom"]
        drom = elf.by_name[".drom"]
        program_symbol = elf.symbol_by_name["d2e_generated_program"]
    except KeyError as error:
        raise ValueError(f"required ELF item is missing: {error.args[0]}") from error
    if irom.address != IROM_LINK_ADDRESS or drom.address != DROM_LINK_ADDRESS:
        raise ValueError("ELF uses unexpected synthetic IROM/DROM addresses")
    irom_data = elf.section_data(irom)
    drom_data = elf.section_data(drom)
    program_offset = program_symbol.value - drom.address
    if program_offset < 0 or program_offset + 56 > len(drom_data):
        raise ValueError("d2e_generated_program is outside DROM")
    program = drom_data[program_offset : program_offset + 56]
    name_pointer, image_format = struct.unpack_from("<II", program, 0)
    load_segment, entry_cs, entry_ip, initial_ss, initial_sp = struct.unpack_from(
        "<HHHHH", program, 8
    )
    image_pointer, image_size, guest_relocation_pointer, guest_relocation_count = (
        struct.unpack_from("<IIII", program, 20)
    )
    block_pointer, block_count, region_pointer, fragment_pointer, fragment_count = (
        struct.unpack_from("<IIIII", program, 36)
    )
    if image_pointer != 0 or block_pointer != 0 or block_count != 0:
        raise ValueError("XIP modules require a region and sparse data image")
    if not (irom.address <= region_pointer < irom.address + len(irom_data)):
        raise ValueError("translated region entry is outside IROM")
    name = read_c_string(drom_data, name_pointer, drom.address)
    fragments: list[tuple[int, int, int]] = []
    fragment_native_offset = fragment_pointer - drom.address
    if fragment_count and (
        fragment_native_offset < 0
        or fragment_native_offset + fragment_count * 12 > len(drom_data)
    ):
        raise ValueError("native fragment table is outside DROM")
    for index in range(fragment_count):
        image_offset, data_pointer, size = struct.unpack_from(
            "<III", drom_data, fragment_native_offset + index * 12
        )
        data_offset = data_pointer - drom.address
        if data_offset < 0 or data_offset + size > len(drom_data):
            raise ValueError("fragment data points outside DROM")
        fragments.append((image_offset, data_offset, size))
    guest_relocations = b""
    if guest_relocation_count:
        guest_offset = guest_relocation_pointer - drom.address
        guest_size = guest_relocation_count * 4
        if guest_offset < 0 or guest_offset + guest_size > len(drom_data):
            raise ValueError("guest MZ relocation table is outside DROM")
        guest_relocations = drom_data[guest_offset : guest_offset + guest_size]

    raw_relocations = collect_relocations(
        elf, irom, drom, parse_imports(imports_header)
    )
    relocation_offset = HEADER_SIZE
    fragment_offset = relocation_offset + len(raw_relocations) * 16
    mz_relocation_offset = fragment_offset + len(fragments) * 12
    irom_offset = align_up(
        mz_relocation_offset + len(guest_relocations), FLASH_PAGE_SIZE
    )
    drom_offset = align_up(irom_offset + len(irom_data), FLASH_PAGE_SIZE)
    module_size = drom_offset + len(drom_data)
    module = bytearray(module_size)
    module[irom_offset : irom_offset + len(irom_data)] = irom_data
    module[drom_offset : drom_offset + len(drom_data)] = drom_data

    relocations = []
    for section_index, patch, kind, target, addend in raw_relocations:
        segment_offset = irom_offset if section_index == irom.index else drom_offset
        relocations.append((segment_offset + patch, kind, target, addend))
    relocations.sort()
    for index, record in enumerate(relocations):
        struct.pack_into("<IIIi", module, relocation_offset + index * 16, *record)
    for index, (image_offset, data_offset, size) in enumerate(fragments):
        struct.pack_into(
            "<III",
            module,
            fragment_offset + index * 12,
            image_offset,
            drom_offset + data_offset,
            size,
        )
    module[
        mz_relocation_offset : mz_relocation_offset + len(guest_relocations)
    ] = guest_relocations

    module[:8] = b"D2EXIP1\0"
    struct.pack_into(
        "<IIIIIIIIIIIIIIIIIII",
        module,
        8,
        1,
        HEADER_SIZE,
        1,
        1,
        0,
        module_size,
        irom_offset,
        len(irom_data),
        drom_offset,
        len(drom_data),
        relocation_offset,
        len(relocations),
        region_pointer - irom.address,
        image_size,
        fragment_offset,
        len(fragments),
        mz_relocation_offset,
        guest_relocation_count,
        image_format,
    )
    struct.pack_into(
        "<HHHHH", module, 84, load_segment, entry_cs, entry_ip, initial_ss,
        initial_sp
    )
    for offset, size, value in (
        (100, 9, command),
        (109, 32, name),
        (141, 64, title),
    ):
        encoded = value.encode("ascii")
        if len(encoded) >= size:
            raise ValueError(f"text is too long for module field: {value}")
        module[offset : offset + len(encoded)] = encoded
    module[205:237] = hashlib.sha256(module).digest()
    return bytes(module)


def build_xip_module(
    sources: pathlib.Path,
    source_names: list[str],
    toolchain_bin: pathlib.Path,
    output: pathlib.Path,
    command: str,
    title: str,
) -> int:
    executable_suffix = ".exe" if sys.platform == "win32" else ""
    compiler = toolchain_bin / f"xtensa-esp32-elf-gcc{executable_suffix}"
    linker = toolchain_bin / f"xtensa-esp32-elf-ld{executable_suffix}"
    for tool in (compiler, linker):
        if not tool.is_file():
            raise ValueError(f"Xtensa tool is missing: {tool}")
    with tempfile.TemporaryDirectory(prefix="d2e-xip-") as temporary:
        build = pathlib.Path(temporary)
        objects = []
        for index, name in enumerate(source_names):
            if pathlib.Path(name).name != name or not name.endswith((".c", ".S")):
                raise ValueError(f"invalid generated source name: {name}")
            source = sources / name
            object_path = build / f"module-{index:03d}.o"
            command_line = [
                str(compiler),
                "-c",
                str(source),
                "-o",
                str(object_path),
                "-std=gnu17",
                "-O2",
                "-mtext-section-literals",
                *XTENSA_COMPILER_CALL_FLAGS,
                "-fno-builtin-memcpy",
                "-fno-builtin-memset",
                "-fno-builtin-bzero",
                "-ffunction-sections",
                "-fdata-sections",
                f"-I{PROJECT_ROOT / 'include'}",
                f"-I{sources}",
            ]
            subprocess.run(command_line, check=True)
            objects.append(object_path)
        elf_path = build / "module.elf"
        subprocess.run(
            [
                str(linker),
                *XTENSA_LINKER_RELAXATION_FLAGS,
                "--emit-relocs",
                "--unresolved-symbols=ignore-all",
                "-T",
                str(PROJECT_ROOT / "tools" / "d2e_xip_module.ld"),
                "-o",
                str(elf_path),
                *(str(path) for path in objects),
            ],
            check=True,
        )
        module = pack_module(
            elf_path.read_bytes(), command, title,
            PROJECT_ROOT / "include" / "d2e" / "xip_imports.h"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(module)
    return len(module)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=pathlib.Path, help="final Xtensa ELF")
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--command", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--imports-header",
        type=pathlib.Path,
        default=PROJECT_ROOT / "include" / "d2e" / "xip_imports.h",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        module = pack_module(
            args.input.read_bytes(), args.command, args.title,
            args.imports_header
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(module)
    except (OSError, UnicodeError, ValueError, struct.error) as error:
        print(f"XIP module pack failed: {error}", file=sys.stderr)
        return 1
    print(f"XIP module complete: {args.output} ({len(module)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
