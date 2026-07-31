# DosToEsp

DosToEsp is an experimental 8086-to-ESP32 ahead-of-time translator aimed at small
real-mode DOS games such as *Alley Cat*. It targets the two-USB
ESP32-2432S028 (CYD2USB) used by the sibling HLV-codec project: classic
ESP32-D0WD-V3, 320x240 ST7789 display, microSD, GPIO26 DAC and BOOT on GPIO0.

The project is deliberately split into a portable C99 core and a thin
ESP-IDF platform layer. The same decoder, translator and DOS machine therefore
run in fast host tests, Espressif QEMU and on the physical board.

## Current milestone

The first milestone is a deterministic `.COM` machine rather than a promise
that an arbitrary DOS program already runs:

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
test command builds a tiny synthetic COM through the complete translation
pipeline and verifies its final registers and DOS exit code:

```powershell
.\scripts\setup-analysis-tools.ps1
.\scripts\test-host.ps1
.\scripts\audit-xtensa.ps1
```

The last command asks the ESP32 Xtensa compiler used by the sibling HLV-codec
project for assembly output and checks for native LX6 instructions such as
`entry`, `l32i`, `s16i` and `call8`.

There is no x86 opcode interpreter in the firmware. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the execution model and
acceptance gates.
