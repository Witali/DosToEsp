# DosToEsp

DosToEsp is an experimental 8086-to-ESP32 ahead-of-time translator aimed at small
real-mode DOS games such as *Alley Cat*. It targets the two-USB
ESP32-2432S028 (CYD2USB) used by the sibling HLV-codec project: classic
ESP32-D0WD-V3, 320x240 ST7789 display, microSD, GPIO26 DAC and BOOT on GPIO0.
The fixed guest profile is the Intel 8086 instruction set inside a narrow
PC/AT-compatible real-mode BIOS/device environment; PC/AT compatibility does
not enable 80286 instructions or protected mode.

The project is deliberately split into a host-only translator, a portable C99
runtime and a thin ESP-IDF platform layer. The generated blocks and runtime run
in fast host tests, Espressif QEMU and on the physical board; disassembly never
happens on the ESP32.

## Current milestone

The current milestone is an automatic DOS `.COM`/MZ `.EXE` to ESP32 source
pipeline. It is deliberately strict: it produces runnable native sources only
when every reachable instruction is supported, rather than claiming that an
arbitrary DOS program already runs:

1. load and analyse a COM image on the development PC;
2. decode reachable 8086 basic blocks and emit portable C plus optional Xtensa
   LX6 assembly templates;
3. let the ESP-IDF toolchain compile each emitted block to native ESP32
   instructions with precise 16-bit flags;
4. provide the BIOS/DOS services and CGA modes observed in the target game;
5. render CGA into the board's 320x240 RGB565 display and map available input;
6. validate the same workload on the host, ESP32 QEMU and CYD2USB hardware.

The game binary is intentionally not part of the repository. Place a legally
obtained image under `games/` when it becomes available; that directory is
ignored by Git.

## Developer smoke test

The setup script installs the pinned Capstone disassembler under the ignored
`local_tools/` directory and verifies its official PyPI SHA-256. The normal
test command builds a suite of tiny synthetic COM programs through the complete
translation pipeline. The fixtures separately exercise arithmetic, memory,
calls and stack, flags, shifts, strings, ports and rare control-flow forms,
then verify their final guest state:

```powershell
.\scripts\setup-analysis-tools.ps1
.\scripts\test-host.ps1
.\scripts\audit-xtensa.ps1
```

The last command asks the ESP32 Xtensa compiler used by the sibling HLV-codec
project for assembly output and checks for native LX6 instructions such as
`entry`, `l32i`, `s16i` and `call8`.

Create the first deterministic inventory after placing a legally obtained game
under the ignored `games/` directory:

```powershell
.\scripts\analyze-game.ps1 -InputPath games\ALLEY.COM
```

The product entry point is the automatic DOS executable to ESP32 source
pipeline. It never silently emits a partial native program: incomplete opcode
coverage produces a `blocked` manifest with exact reasons. Fully covered MZ
inputs produce one `game_native.c` containing the relocated load module and
native regions addressed through preserved real-mode `CS:IP` state.

```powershell
.\scripts\translate-game.ps1 `
    -InputPath games\Alley-Cat_DOS_EN\alley-cat\CAT.EXE `
    -Name alley-cat
```

Generated sources and reports are written under ignored `out/generated/`.
For the fingerprinted Alley Cat target, the current frontend resolves the
bounded jump table, covers all 8368 reachable instruction sites and emits a
`complete` manifest plus `game_native.c`. The remaining work is the emulated
DOS boundary for larger applications, complete input/timing, and any additional
video operations exposed by execution traces, not an x86 CPU interpreter.

The first ESP-IDF image can also be exercised in QEMU or flashed to the CYD:

```powershell
.\firmware\esp32_cyd\qemu-smoke.ps1
.\firmware\esp32_cyd\qemu-alley-cat.ps1
.\firmware\esp32_cyd\qemu-alley-cat-interactive.ps1
.\firmware\esp32_cyd\build-alley-cat.ps1
.\firmware\esp32_cyd\flash-alley-cat.ps1 -Port COM8
.\firmware\esp32_cyd\flash.ps1
.\firmware\esp32_cyd\board-smoke.ps1
```

The Alley Cat board image runs continuously in translated-code slices. The
BOOT button sends Space. A serial terminal on UART0 can send letters, digits,
Enter, Backspace and ANSI arrow-key sequences; the backtick key sends Escape.
The interactive QEMU command uses the same UART/ANSI mapping and runs until
QEMU is closed; pass `-FrameLimit 8` for a bounded regression run.

There is no x86 opcode interpreter in the firmware. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the execution model and
acceptance gates.
