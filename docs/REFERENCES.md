# Implementation references

DosToEsp reimplements behaviour rather than copying an emulator CPU core.
These local sources were consulted for the first hardware-facing milestone.

## Pico-286 CGA behaviour

Reference tree:
`C:/Work/r36sx_disasm/homebrew/pico_286`

- `pico-286/src/emulator/video/cga.c`: RGB palette values, graphics palette
  groups and the meaning of CGA ports `3D8h` and `3D9h`.
- `r36sx_port/r36sx_linux-main.cpp`: 320x200 packed-pixel expansion and the
  8 KiB even/odd CGA scanline banks.

Only the small CGA peripheral contract was reimplemented. None of Pico-286's
x86 instruction dispatch or CPU interpreter is used by DosToEsp.

## ESP32-2432S028 CYD2USB

Reference tree: `C:/Work/HLV-codec`

- `firmware/esp32_2432s028_hlv_player_idf_c/main/board_config.h`: ST7789,
  microSD, DAC and BOOT GPIO assignments.
- `firmware/esp32_2432s028_hlv_player_idf_c/main/cyd_display.c`: known-good
  ESP-IDF ST7789 SPI/DMA configuration.
- `firmware/esp32_2432s028_hlv_player_idf_c/qemu/README.md`: original
  QEMU/ST7789 workflow and pinned QEMU lineage used during bring-up.

The maintained emulator tree now lives at `C:/Work/QEMU-ESP32`. It is based
on Espressif commit `40edccac415693c5130f91c01d84176ae6008566`; the imported
HLV board changes and the DosToEsp SDL-keyboard bridge are regular commits on
its `main` branch. HLV-codec is no longer modified to build DosToEsp QEMU.

## Disassembly and target compiler

- Capstone 5.0.9 Windows wheel from the official PyPI project, pinned by
  SHA-256 in `scripts/setup-analysis-tools.ps1`. It is a host-only
  disassembler and is not linked into the firmware.
- Espressif Xtensa GCC `esp-14.2.0_20260121` from the sibling HLV-codec's
  pinned ESP-IDF 5.5.5 installation is used by the native-code audit.
