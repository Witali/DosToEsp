# D2E XIP module format

Translated DOS programs are stored in a versioned `D2EXIP1` container. The
resident DOS shell owns the x86 CPU, devices, supervisor, and common CISC
helpers. A module contains only program-specific Xtensa code and the data that
must be copied into conventional DOS memory.

An installed module is kept in a contiguous, 64-KiB-aligned extent on drive
`A:`. Its IROM range is mapped into the ESP32 instruction address space and is
executed directly from main SPI Flash. Its DROM range is mapped read-only into
the data address space. Files on the SD-backed `C:` drive are installation
sources; they cannot be executed in place by this loader.

## Header

All integers are unsigned little-endian unless stated otherwise. The header is
256 bytes. Text fields are ASCII, NUL-terminated, and padded with zeroes.

| Offset | Size | Field |
| ---: | ---: | --- |
| 0 | 8 | `D2EXIP1\0` magic |
| 8 | 4 | format version |
| 12 | 4 | header size |
| 16 | 4 | package ABI version |
| 20 | 4 | resident shell/import ABI version |
| 24 | 4 | flags; zero in version 1 |
| 28 | 4 | complete module size |
| 32 | 4 | IROM file offset |
| 36 | 4 | IROM byte size |
| 40 | 4 | DROM file offset |
| 44 | 4 | DROM byte size |
| 48 | 4 | native relocation table offset |
| 52 | 4 | native relocation count |
| 56 | 4 | translated region entry offset within IROM |
| 60 | 4 | logical DOS image size |
| 64 | 4 | sparse image-fragment table offset |
| 68 | 4 | sparse image-fragment count |
| 72 | 4 | MZ relocation table offset |
| 76 | 4 | MZ relocation count |
| 80 | 4 | native image format (`0` COM, `1` MZ) |
| 84 | 2 | load segment |
| 86 | 2 | initial CS relative to load segment |
| 88 | 2 | initial IP |
| 90 | 2 | initial SS relative to load segment |
| 92 | 2 | initial SP |
| 94 | 6 | reserved; zero |
| 100 | 9 | shell command, at most eight characters |
| 109 | 32 | internal program name |
| 141 | 64 | display title |
| 205 | 32 | SHA-256 module digest with this field treated as zero |
| 237 | 19 | reserved; zero |

IROM and DROM offsets are multiples of 64 KiB. Table and segment ranges must be
inside the declared module size. The parser rejects malformed ranges before a
module can become a shell package.

## Native relocations

Each 16-byte record contains a module-relative patch offset, target kind,
target value, and signed addend. Version 1 supports 32-bit aligned absolute
patches. IROM and DROM targets are offsets relative to their mapped segment.
Import targets are stable indexes in the shell ABI, not firmware function
addresses. This keeps common x86 helpers outside every translated program.

## Sparse DOS image

Each 12-byte fragment record contains the logical DOS-image offset, absolute
module data offset, and size. Fragments are ordered and non-overlapping. The
shell clears the logical image and copies only these data fragments, so the
original executable code is not duplicated in conventional memory or DROM.

MZ relocation records retain the original four-byte `offset, segment` layout.
The resident native loader applies them after reconstructing the sparse image.

## Translator output

The unified translator performs source generation, Xtensa compilation, final
relaxation, retained-relocation extraction, and container packing in one run:

```powershell
python tools/d2e_build.py CAT.EXE --name alley-cat --backend xtensa-asm `
  --output out/generated/alley-cat --xip-module out/modules/ALLEY.D2E `
  --xtensa-toolchain-bin C:\path\to\xtensa-esp-elf\bin `
  --command ALLEY --title "Alley Cat"
```

The packer reads post-relaxation words for internal absolute references. This
is required because Xtensa relaxation can merge literal pools and change final
target offsets after input relocations were emitted.

The staged plan for compact relocation streams, relative native references,
and zero-relocation modules is documented in
[`XIP_RELOCATION_OPTIMIZATION_PLAN.md`](XIP_RELOCATION_OPTIMIZATION_PLAN.md).
