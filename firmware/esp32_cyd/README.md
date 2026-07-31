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

Flash and verify the physical CYD2USB board (COM8 by default):

```powershell
.\flash.ps1
.\board-smoke.ps1
```

The board verifier resets the ESP32 through the modified CH340 auto-boot
circuit and accepts either 460800 baud (a clean configuration) or 115200 baud
(an existing local `sdkconfig`). Success ends with `D2E_BOARD_DONE,0`.
