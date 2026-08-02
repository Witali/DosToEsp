# D2E Shell

`D2E Shell` is the resident ESP32 supervisor for programs translated ahead of
time. It is deliberately smaller than MS-DOS: the shell owns the display,
keyboard, storage and program lifecycle, while the existing PC/AT runtime
provides the DOS and BIOS services used by a running package.

## Package model

Every launchable entry has an eight-character DOS-style command, a title and
a `d2e_native_program`. Programs may be compiled into a development firmware or
installed as versioned `D2EXIP1` modules. Installed Xtensa IROM and DROM are
mapped read-only from the custom `A:` Flash volume; only sparse guest data, the
PSP, and conventional memory are copied into RAM for a session. Shared x86
helpers remain in the resident shell and are referenced through its versioned
import ABI.

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

- `DIR` lists packages in the installed catalog.
- `A:` selects the custom XIP volume in the unused portion of internal ESP32
  flash.
- `C:` selects the FAT-formatted SD card when one is inserted.
- `INSTALL <file>` validates and installs a `D2EXIP1` file from `C:` to `A:`.
- `RUN <name>` starts one package.
- `HELP` prints the available commands.

Typing a package name directly is equivalent to `RUN <name>`. During a
program, `Ctrl+]` requests an immediate return to the shell. On the physical
CYD board, pressing BOOT at the shell starts the first catalog entry.

At boot, the shell reads `A:\AUTOEXEC.BAT` and executes its commands in order.
Blank lines and `REM` comments are accepted. The custom XIP catalog stores the
file as an atomic append-only record with a maximum of 48 bytes. Installing the
first package creates the file automatically with that package's command, so
installing Alley Cat writes `ALLEY` and subsequent boots start it without user
input. An existing XIP volume with one or more packages but no startup file is
migrated in the same way when it is mounted.

Volkov Commander is installed as command `VC`. Its executable module runs from
`A:`, while the original help, menu, configuration and extension files stay on
the FAT-backed `C:` drive. This split is required because XIP code must be in
internal Flash but VC's DOS file access must remain writable and enumerable.

Development firmware can still contain a built-in `ALLEY` entry. The production
layout installs that translation from the FAT-backed `C:` drive into an
aligned, append-only extent on `A:`. A catalog record is committed only after
the complete module passes structural validation, so an interrupted copy is
ignored on the next boot.

At launch, the platform maps only the selected module. The Xtensa linker has
already resolved instruction-relative relocations; the Flash installer patches
the retained aligned absolute references to the actual IROM/DROM windows and
resolves import indexes through the resident shell ABI. Mapping handles and the
small RAM-native fragment table are released when the session returns to the
prompt. Programs on `C:` must be installed first because SD storage is not part
of the ESP32 instruction mmap address space.
