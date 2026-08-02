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

Generate Alley Cat and exercise it through the resident D2E Shell in QEMU:

```powershell
.\qemu-alley-cat.ps1
```

This bounded mode automatically selects the internal-flash `ALLEY` package.
It reports `D2E_SHELL_READY`, `D2E_SHELL_RUN`, `D2E_SHELL_RETURN` and finally
`D2E_QEMU_DONE,0`. The supervisor clears conventional memory before launch
and again when it returns to the shell.

Run the game with the sibling `QEMU-ESP32` fork, which owns the native Windows
CYD ST7789, SDSPI, audio, reset and SDL keyboard models:

```powershell
.\qemu-alley-cat-board-windows.ps1 -ScriptedInput
```

The command builds `C:\Work\QEMU-ESP32` when its cached runtime is stale. The
default visible run opens an SDL window at the `D2E DOS 0.1` prompt.
Enter `DIR`, `HELP`, `RUN ALLEY`, or simply `ALLEY`; `Ctrl+]` returns from a
running program to the prompt. `A:` selects the custom XIP volume in the remaining
internal flash and `C:` selects the SD-card FAT volume. `INSTALL <file>` copies a
translated module from `C:` into an aligned Flash extent on `A:`. The firmware renders
through the same SPI2 DMA driver used on the board, mounts the HLV-codec FAT fixture through SPI3 and stores UART
telemetry in `out/qemu/alley-cat-board-windows.log`. PIT channel 2 and port
`61h` PC-speaker output is synthesized at 16 kHz and sent through the ESP32
continuous DAC on GPIO26; patched QEMU routes it to DirectSound. Visible runs use a large
default frame limit and permit emulated hardware reboot, so the SDL Reset
action restarts the ESP32 and game without closing QEMU. Headless runs default
to a bounded 240-frame automatic launch and use `-no-reboot` to turn the deliberate final
firmware restart into process exit. Pass `-FrameLimit N`, `-SdImage path.img`
or `-Volume 0..100` as needed. `-AudioCapture path.wav` records the DAC stream
with QEMU's WAV backend instead of playing it. QEMU snapshot mode keeps both
source images unchanged.

The first installed module also creates `A:\AUTOEXEC.BAT`. The shell executes
this file on every boot; installing the Alley Cat module writes `ALLEY`, so the
game starts automatically without being compiled into the resident firmware.

Verify the production layout, where Alley Cat is absent from the application
partition and is installed from SD before executing directly from `A:` Flash:

```powershell
.\qemu-xip-alley-cat-windows.ps1 -FrameLimit 60
```

Flash and verify the physical CYD2USB board (COM8 by default):

```powershell
.\flash.ps1
.\board-smoke.ps1
```

The board verifier resets the ESP32 through the modified CH340 auto-boot
circuit and accepts either 460800 baud (a clean configuration) or 115200 baud
(an existing local `sdkconfig`). Success ends with `D2E_BOARD_DONE,0`.
