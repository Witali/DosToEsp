# ESP32 native smoke firmware

This ESP-IDF 5.5.5 project targets the same classic ESP32-D0WD-V3 CYD2USB
board as HLV-codec. Its current entry point is deliberately small: the host
translator converts `tests/fixtures/native_smoke.hex` into C block functions,
ESP-IDF compiles them to Xtensa LX6 code, and the firmware verifies the final
8086-visible state using only 128 KiB conventional RAM plus a separate 16 KiB
CGA window.

Build the image:

```powershell
.\build.ps1
```

Run it under the sibling project's pinned Espressif QEMU:

```powershell
.\qemu-smoke.ps1
```

Success is reported as `D2E_NATIVE_OK,...` followed by `D2E_QEMU_DONE,0`.
The `-no-reboot` QEMU option turns the deliberate final ESP restart into a
clean emulator exit.

Generate, compile and probe the user-supplied Alley Cat executable in QEMU:

```powershell
.\qemu-alley-cat.ps1
```

This mode reports `D2E_ALLEY_START` followed by `D2E_ALLEY_STOP` at the first
missing BIOS, port or other environment boundary. It exercises the generated
MZ native code and is not expected to reach gameplay until those devices are
implemented.

Run the game with the sibling HLV-codec project's native Windows QEMU models
for the CYD ST7789 display and SDSPI card:

```powershell
.\qemu-alley-cat-board-windows.ps1 -ScriptedInput
```

The default run opens an SDL window, renders through the same SPI2 DMA driver
used on the board, mounts the HLV-codec FAT image through SPI3 and stores UART
telemetry in `out/qemu/alley-cat-board-windows.log`. Visible runs use a large
default frame limit and permit emulated hardware reboot, so the SDL Reset
action restarts the ESP32 and game without closing QEMU. Headless runs default
to a bounded 240-frame smoke and use `-no-reboot` to turn the deliberate final
firmware restart into process exit. Pass `-FrameLimit N` or `-SdImage path.img`
as needed. QEMU snapshot mode keeps both source images unchanged.

Flash and verify the physical CYD2USB board (COM8 by default):

```powershell
.\flash.ps1
.\board-smoke.ps1
```

The board verifier resets the ESP32 through the modified CH340 auto-boot
circuit and accepts either 460800 baud (a clean configuration) or 115200 baud
(an existing local `sdkconfig`). Success ends with `D2E_BOARD_DONE,0`.
