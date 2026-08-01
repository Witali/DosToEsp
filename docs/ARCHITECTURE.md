# Architecture

## Native translation contract

Directly converting a whole DOS executable into fixed Xtensa addresses is not
safe for the software we want to run. Real-mode code can use computed jumps,
overlapping segments and writes into executable memory. DosToEsp handles this
with an ahead-of-time (AOT) basic-block translator on the development PC:

1. the translator disassembles all statically reachable 8086 blocks;
2. it groups compatible blocks into native regions whose internal edges are C
   labels and direct branches, with a target switch only at external entries;
3. live guest registers become region-local C values so the Xtensa compiler
   keeps them in hardware registers across internal block edges;
4. ESP-IDF compiles those regions into Xtensa LX6 instructions;
5. profiling or an emulator trace can add targets missed by static analysis,
   then the game is translated and rebuilt again.

The firmware must not contain an x86 fetch/decode/execute loop, bytecode
executor or micro-operation interpreter. Unsupported code addresses stop with
a diagnostic so that the next offline translation pass can include them.
Performance-critical operations may use explicit Xtensa assembly templates;
ordinary emitted C is still native translation because the Xtensa compiler
lowers each source block before the firmware is built.

## Native pattern lowering

The translator may replace a proven sequence of 8086 operations with a call to
a shared ESP32-native helper. This is an ahead-of-time optimisation, not a CPU
emulation fallback: the helper is compiled by ESP-IDF into Xtensa LX6 code and
contains no opcode fetch or decode loop.

The first pattern family recognises repeated `MOVSB/MOVSW` and `STOSB/STOSW`
and emits `d2e_pattern_copy8/16` or `d2e_pattern_fill8/16`. These helpers retain
the exact visible 8086 contract: `DF` direction, 16-bit `SI`/`DI` wrapping,
`CX` completion, segment selection, sequential overlapping-copy behaviour and
early memory-fault state. The rule is generic and is applied to every COM/MZ
input; it has no executable fingerprint or game-specific address checks.

Later recognisers may cover equivalent compiler loops and unrolled sequences,
but only after control-flow and data-flow checks prove that replacing the
whole region preserves all registers, flags, memory-access order and possible
fault boundaries. If a proof fails, the ordinary translated basic blocks stay
in place.

The user-facing product boundary is one deterministic build command accepting
a DOS COM/MZ executable and producing ESP32 C sources plus a fingerprinted
manifest. Game functions are never rewritten manually. When coverage is
incomplete, the command emits analysis reports and a `blocked` manifest instead
of presenting an image-only or partially translated build as runnable code.

## Generated source layout

The unified COM/MZ frontend emits multiple independent translation units:

- `game_native.c` contains only the program descriptor and region dispatcher;
- `game_image.c` contains the original executable module and MZ relocations;
- `game_region_NNN.c` contains one bounded group of translated basic blocks;
- `game_native.h` is a private generated interface shared by those files.

The manifest lists every generated source so a platform build can compile the
set without assuming a particular region count. BIOS, DOS and video services
are not generated into these files. They remain shared runtime components such
as `pc_at.c`, `cga.c` and `text_video.c`; translated `INT` instructions contain
only calls across that common platform boundary.

## Components

- `translator`: host-only 8086 decoder, control-flow discovery and source
  emitter. It is not linked into the ESP32 firmware.
- `runtime`: the guest register file, 20-bit address helpers, flags, native
  region entry/fallback dispatcher and platform call boundary. It has no x86
  opcode decoder.
- `machine`: COM/MZ loading plus a narrow DOS/BIOS environment. Interrupts are
  routed to explicit services; unsupported calls stop with a diagnostic rather
  than silently returning invented results.
- `platform/host`: deterministic tests, instruction differential checks and a
  desktop diagnostic runner.
- `platform/esp32`: ESP-IDF integration for the CYD2USB display, SD card,
  GPIO26 DAC, BOOT button and serial telemetry.

## Guest state and memory

- 8086 general and segment registers are stored as `uint16_t`.
- Physical addresses use `(segment << 4) + offset`, masked to 20 bits.
- The guest sees one 1 MiB byte-addressed array. The ESP32 implementation may
  back unused regions sparsely, but reads and writes must keep the same API.
- COM programs start with a synthetic PSP and DOS-compatible registers:
  `CS=DS=ES=SS=psp_segment`, `IP=0x100`, and a stack below the segment limit.
- Writes to addresses that contained translated code are diagnosed. If the
  target really uses self-modifying code, the AOT pass must identify the finite
  variants and emit a guarded native version for each one.

## Fixed target profile

The guest instruction-set boundary is the documented Intel 8086 ISA. The
offline analyzer and translator reject 80186/80286 instructions, 32-bit
operand/address prefixes and later x86 extensions even when the disassembler
can decode them. There is no protected mode, descriptor-table state or 286 CPU
fallback.

The machine boundary is an IBM PC/AT-compatible real-mode environment with the
specific ISA devices observed by Alley Cat: conventional memory, PC BIOS/DOS
services, CGA, 8253/8254 PIT, 8255-compatible speaker control, keyboard and PC
speaker. "PC/AT-compatible" describes the firmware/device contract only; it
does not expand the translated CPU beyond the 8086 instruction set. Unobserved
AT devices and APIs remain strict diagnostic boundaries.

## Intel 8086 coverage

Translation proceeds by semantic groups, each gated by generated-code tests:

1. data movement, stack and exchange;
2. integer arithmetic and all status flags;
3. boolean, shift and rotate operations;
4. conditional branches, calls, returns and loops;
5. ModR/M addressing and segment overrides;
6. strings with REP/REPE/REPNE;
7. multiply, divide, BCD helpers and interrupt control.

Post-8086 instructions are permanently outside this initial target profile.

## DOS, video, input and sound

The intended target is the original PC booter/DOS-era Alley Cat family, but
the exact executable must be fingerprinted before assuming its interface.
The compatibility layer will be driven by a trace from that binary. Likely
first targets are DOS `INT 21h` process/file calls, BIOS keyboard `INT 16h`,
timer ticks, PC speaker and CGA modes 4/5 or direct B800 memory access.

CGA's 320x200 image maps cleanly to the physical 320x240 panel with 20 black
rows above and below it. Rendering expands 2-bit CGA pixels into RGB565 strips,
so no full RGB framebuffer is required. Guest B800 memory remains only 16 KiB.

## Validation gates

- Every implemented translation has boundary tests for results and flags.
- Random differential cases are compared with an independent 16-bit x86
  engine or disassembler where that engine exposes the required behaviour.
- A synthetic COM integration fixture must produce an identical state digest
  on the host and ESP32.
- QEMU must boot the actual ESP-IDF image, execute only translated native
  blocks and report the expected digest.
- Physical-board validation records chip, free heap, translated-block counts,
  invalidations, frames and frame-time percentiles over serial.

## Out of scope for the first playable build

- protected mode, 32-bit x86 and x87;
- 80186/80286 and later instruction-set extensions;
- an exact PC chipset emulator;
- unobserved DOS APIs and hardware devices;
- distributing proprietary game files.

## Reference implementation boundary

`C:/Work/r36sx_disasm/homebrew/pico_286` is a useful behavioural reference for
CGA, BIOS, DOS, keyboard, timer and speaker details. Its instruction dispatch
and CPU interpreter are explicitly outside the implementation path: copying
them would defeat the native-translation goal.
