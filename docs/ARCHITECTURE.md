# Architecture

## Why a block translator

Directly converting a whole DOS executable into fixed Xtensa addresses is not
safe for the software we want to run. Real-mode code can use computed jumps,
overlapping segments and writes into executable memory. DosToEsp therefore
uses a dynamic binary translator (DBT): it decodes one straight-line 8086
basic block on first execution and caches a compact array of micro-operations.
The C compiler turns the executor and its hot paths into Xtensa LX6 machine
code as part of the ESP-IDF build.

This first representation is intentionally portable. Once traces identify a
real bottleneck, individual micro-operations or complete hot blocks can gain
Xtensa-specific templates without changing guest-visible behaviour.

## Components

- `core`: 8086 registers, 20-bit memory wrapping, flags, instruction decoder,
  micro-operation cache and executor. This code is freestanding C99 and owns
  no files, display or input devices.
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
- Every guest write bumps page generations. A cached block records the pages
  containing its source bytes and is discarded when a generation changes.

## Initial 8086 coverage

Implementation proceeds by semantic groups, each gated by host tests:

1. data movement, stack and exchange;
2. integer arithmetic and all status flags;
3. boolean, shift and rotate operations;
4. conditional branches, calls, returns and loops;
5. ModR/M addressing and segment overrides;
6. strings with REP/REPE/REPNE;
7. multiply, divide, BCD helpers and interrupt control.

80186+ instructions are rejected unless enabled by a later target profile.

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

- Every implemented instruction has boundary tests for results and flags.
- Random differential cases are compared with an independent 16-bit x86
  engine or disassembler where that engine exposes the required behaviour.
- A synthetic COM integration fixture must produce an identical state digest
  on the host and ESP32.
- QEMU must boot the actual ESP-IDF image and report the expected digest.
- Physical-board validation records chip, free heap, translated-block counts,
  invalidations, frames and frame-time percentiles over serial.

## Out of scope for the first playable build

- protected mode, 32-bit x86 and x87;
- an exact PC chipset emulator;
- unobserved DOS APIs and hardware devices;
- distributing proprietary game files.

