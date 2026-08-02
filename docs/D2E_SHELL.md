# D2E Shell

`D2E Shell` is the resident ESP32 supervisor for programs translated ahead of
time. It is deliberately smaller than MS-DOS: the shell owns the display,
keyboard, storage and program lifecycle, while the existing PC/AT runtime
provides the DOS and BIOS services used by a running package.

## Package model

Every launchable entry has an eight-character DOS-style command, a title and
a `d2e_native_program`. Package ABI version 1 supports programs compiled into
the ESP32 application image. Their Xtensa instructions execute directly from
internal flash; only the guest data image, PSP and conventional memory are
copied into RAM for a session.

External native modules are reserved in the API but intentionally rejected by
the version-1 validator. Loading translated Xtensa code from an SD card needs
a relocatable module format and symbol allow-list; it must not silently fall
back to an x86 interpreter. Adding that loader will not change shell commands
or the supervisor lifecycle.

## Session lifecycle

1. The shell resolves a command in its package catalog.
2. Platform devices are reset to a clean PC/AT state.
3. The supervisor clears conventional memory and calls `d2e_native_load`.
4. The shell repeatedly calls `d2e_supervisor_step` while servicing video,
   input, timers and audio.
5. `INT 20h` or `INT 21h/AH=4Ch` produces `D2E_SUPERVISOR_EXITED` and retains
   the DOS exit code. Any other terminal stop reason produces
   `D2E_SUPERVISOR_FAULTED`.
6. After reporting the result, the platform stops audio and resets devices;
   `d2e_supervisor_return_to_shell` clears the guest CPU and memory.

The explicit final step prevents a terminated program from leaking interrupt
hooks, memory contents or register state into the next program.

## Initial commands

- `DIR` lists packages in the compiled catalog.
- `A:` selects the writable LittleFS volume in the unused portion of internal
  ESP32 flash.
- `C:` selects the FAT-formatted SD card when one is inserted.
- `RUN <name>` starts one package.
- `HELP` prints the available commands.

Typing a package name directly is equivalent to `RUN <name>`. During a
program, `Ctrl+]` requests an immediate return to the shell. On the physical
CYD board, pressing BOOT at the shell starts the first catalog entry.

The first ESP32 catalog contains `ALLEY`, backed by the generated Alley Cat
translation in the application partition of internal flash. The drive volumes
are mounted in ESP-IDF VFS as `/A` and `/C`; resident packages are kept separate
from files on either volume. External native module loading remains a subsequent
milestone.
