# DosToEsp

DosToEsp is an experimental 8086-to-ESP32 dynamic translator aimed at small
real-mode DOS games such as *Alley Cat*. It targets the two-USB
ESP32-2432S028 (CYD2USB) used by the sibling HLV-codec project: classic
ESP32-D0WD-V3, 320x240 ST7789 display, microSD, GPIO26 DAC and BOOT on GPIO0.

The project is deliberately split into a portable C99 core and a thin
ESP-IDF platform layer. The same decoder, translator and DOS machine therefore
run in fast host tests, Espressif QEMU and on the physical board.

## Current milestone

The first milestone is a deterministic `.COM` machine rather than a promise
that an arbitrary DOS program already runs:

1. load a COM image into a 1 MiB real-mode address space;
2. decode 8086 basic blocks into cached micro-operations;
3. execute the blocks with precise 16-bit flags and invalidate translated code
   when guest memory is modified;
4. provide the BIOS/DOS services and CGA modes observed in the target game;
5. render CGA into the board's 320x240 RGB565 display and map available input;
6. validate the same workload on the host, ESP32 QEMU and CYD2USB hardware.

The game binary is intentionally not part of the repository. Place a legally
obtained image under `games/` when it becomes available; that directory is
ignored by Git.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the execution model and
acceptance gates.

