# Alley Cat target fingerprint

This project targets the user-supplied English DOS release extracted locally
from `Alley-Cat_DOS_EN.zip`. The binary itself remains under the Git-ignored
`games/` directory and is not redistributed by DosToEsp.

## Binary identity

- Filename: `CAT.EXE`
- Size: 55067 bytes
- SHA-256: `4979c8867826e08881d1d4bec95c95d6bc1ac70fd21050ccdb4f733a50d7bfdd`
- Format: DOS MZ executable
- Header: 512 bytes
- Load-module size: 54555 bytes
- Relocations: 9
- Initial CS:IP: `0723:0000` (module offset `07230h`)
- Initial SS:SP: `0000:0100`
- Minimum extra allocation: 0 paragraphs
- Maximum extra allocation: 65535 paragraphs

Analysis outputs are generated locally as `out/analysis/alley-cat.json` and
`out/analysis/alley-cat.md` by:

```powershell
.\scripts\analyze-game.ps1 `
    -InputPath games\Alley-Cat_DOS_EN\alley-cat\CAT.EXE `
    -Name alley-cat
```

## Initial reachable inventory

- 4224 decoded instructions
- 1576 basic blocks
- 2355 CFG edges
- no decode/overlap issues
- one unresolved indirect jump at module offset `0747Bh`:
  `jmp word ptr cs:[bx + 0250h]`
- 32 statically visible loads of the CGA segment constant `B800h`
- 704 instructions with memory-write operands requiring runtime code-range
  and CGA classification

Most frequent instruction families include `mov` (1516), `cmp` (422), direct
`call` (372), `ret` (211), conditional branches (over 600), arithmetic,
boolean operations, shifts, stack operations and string operations. The tail
also contains `mul`, `xchg`, `lods`, `stos`, `rcl/rcr`, `lahf/sahf`, `cli/sti`,
`std/cld` and one `aaa`.

## Observable PC boundary

Statically reachable software interrupts:

- `INT 10h`: 13 video BIOS call sites
- `INT 11h`: 2 equipment-list call sites
- `INT 1Ah`: 38 time-of-day call sites

Static port operands include:

- `40h`: PIT channel 0 reads
- `42h`: PIT channel 2 / speaker divisor
- `43h`: PIT control
- `61h`: PC speaker/PPI gate
- dynamic `DX` ports, to be resolved by the reference trace

The game therefore appears to use BIOS only for video/equipment/time while
driving keyboard, timer, speaker and CGA-related hardware directly. A dynamic
trace remains authoritative because static code reachability includes routines
that a normal play path may not execute.

## Implementation order derived from this target

1. MZ relocation and initial CS:IP/SS:SP loading.
2. 8086 ModR/M memory addressing and segment-register operations.
3. Stack, direct calls and returns.
4. Boolean, shift/rotate and string instruction groups.
5. Observed BIOS calls and port devices.
6. Resolve the single jump table using static table recovery plus trace data.

## Current translator coverage

`scripts/report-coverage.ps1 -Name alley-cat` compares every inventoried site
against the actual translator semantics. The initial baseline was:

- supported: 1633 of 4224 sites (38.66%);
- unsupported: 2591 sites;
- memory operands: 1524 sites;
- call/return and other control transfers: 586 sites;
- missing instruction semantics: 407 sites;
- segment or special registers: 73 sites;
- indirect control target: 1 site.

The common ModR/M layer has since raised coverage to 3065 of 4224 sites
(72.56%) and reduced unsupported memory operands from 1524 to 90. It covers
8/16-bit reads, writes and read-modify-write operations, all 8086
`BX/BP/SI/DI` effective-address combinations, DS/SS defaults and explicit
segment overrides. The remaining blockers are 586 control transfers, 407
missing instruction semantics, 90 sites where a still-unsupported operation
uses memory, 75 segment or special-register sites and one indirect target.
Direct `call`/`ret`, `push`/`pop` and segment-register moves have since raised
coverage again to 3773 of 4224 sites (89.32%). The remaining 451 sites comprise
357 missing instruction semantics, 90 memory-using forms of those operations,
three control transfers (`loopne`, `loope`, `retf`) and one indirect jump.
Boolean and shift semantics are now the largest dependency.

Native `AND`, `OR`, `TEST`, `NOT`, flag-control and LAHF/SAHF semantics have
raised coverage to 4008 of 4224 sites (94.89%). The 216 remaining sites are
dominated by 107 shifts, 63 port I/O operations and 30 string operations; the
rest are four multiply, four exchange, four control-flow and a few legacy
instruction sites.

With SHL/SHR and the observed carry rotates implemented, coverage is now 4118
of 4224 sites (97.49%). The final 106 static sites are 63 port operations, 30
string operations, four multiply, four exchange, four control-flow and one
AAA instruction.

All 30 observed MOVS/STOS/LODS and REP sites are now native, raising coverage
to 4148 of 4224 sites (98.20%). Port I/O accounts for 63 of the remaining 76
sites, so the next large step is the explicit PC-device boundary rather than
more general x86 decoding.

All 63 byte `IN`/`OUT` sites now translate through a strict generic device
callback boundary, bringing instruction coverage to 4211 of 4224 sites
(99.69%). This covers opcode translation only: ports 40h/42h/43h/61h and the
dynamic DX values still require PIT/PPI/keyboard device semantics driven by
the reference trace.

The remaining observed `MUL`, `XCHG`, `AAA`, `LOOPE`, `LOOPNE` and `RETF`
forms are now emitted as native C and covered by a small end-to-end COM
fixture. Coverage is therefore 4223 of 4224 sites (99.98%). The sole remaining
translation blocker is `jmp word ptr cs:[bx + 0x250]` at module offset
`0747Bh`; its finite jump-table target set must be recovered statically and
confirmed by the reference trace.

The runtime MZ loader and common native emitter now pack the complete
54555-byte module, construct its PSP, establish `CS:IP`, `SS:SP`, `DS` and
`ES`, apply all nine relocations and address native regions through segmented
MZ target keys. The same path is regression-tested with a fully covered tiny
MZ input; no Alley Cat-specific code is used.

The unified frontend currently writes `out/generated/alley-cat/game_image.c`,
the inventory and coverage reports, and a `blocked` manifest naming that one
indirect target. It will change the manifest to `complete` and add
`game_native.c` only when the same general backend can translate every
required site; no Alley Cat routine is maintained as handwritten ESP32 code.
