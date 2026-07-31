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

The user-facing product boundary is one deterministic build command accepting
a DOS COM/MZ executable and producing ESP32 C sources plus a fingerprinted
manifest. Game functions are never rewritten manually. When coverage is
incomplete, the command emits analysis reports and a `blocked` manifest instead
of presenting an image-only or partially translated build as runnable code.

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
