# Volkov Commander 4.00 target

Volkov Commander 4.00 is supported as an external `D2EXIP1` module for the
ESP32 D2E Shell. The user-supplied distribution remains in the Git-ignored
`games/` directory and is not redistributed by DosToEsp.

## Binary identity

- Filename: `VC.COM`
- Size: 65,142 bytes
- SHA-256: `f0a1fa6e78aa79268c8374d3603d45444484c598f6307fe9c0eb8c2c3aab8904`
- Format: DOS COM
- Load segment and entry: `1000h:0100h`
- CPU profile: Intel 8086

The current frontend translates every reachable instruction. VC also uses two
runtime callback entries that are not roots of the static COM entry graph:
`0397h` and `0425h`. The dedicated build script records both targets.

## Build

Place the original VC distribution at
`games\volkov-commander-4.00\`, then run:

```powershell
.\scripts\build-volkov-commander.ps1
```

The script works from a normal checkout or a Git worktree. It produces the
ignored artifact `out\modules\VC.D2E`. The module command is `VC`; its title is
`Volkov Commander 4.00`.

VC uses the `xtensa-c` XIP backend. Its statically discovered x86 graph is
compiled to Xtensa C regions, while a small assembly dispatcher keeps the
module entry and sparse data image compatible with direct Flash execution.
This backend is larger and slower than the direct assembly optimizer, but it
preserves the verified C translation semantics for VC's relocated control
flow.

## SD-card layout and shell use

Copy `VC.D2E` and the contents of the original VC distribution directory to
the root of a FAT-formatted SD card. In D2E Shell:

```text
C:
INSTALL VC.D2E
VC
```

`INSTALL` stores the executable module in the internal `A:` XIP volume. The
original `VC.COM`, help, menu, configuration and extension files remain on
`C:` so the DOS filesystem services can expose them to the running commander.
Installing the first package also creates `A:\AUTOEXEC.BAT`; a fresh device
therefore starts `VC` automatically on later boots. `Ctrl+]` returns to D2E
Shell.

## Runtime requirements

The shell exposes 224 KiB of conventional memory to VC. The first 124 KiB is a
resident byte-addressable region. The remaining 100 KiB is sparse and allocates
4 KiB, 32-bit-capable ESP32 pages only when written, leaving enough DRAM for
the mounted FAT filesystem.

The PC/AT boundary includes the DOS services used during the verified startup:
memory allocation and resize, DTA management, file open/read/seek/close,
directory enumeration, current drive and directory, country case mapping,
date/time, extended error reporting, Ctrl-Break, interrupt vectors, IOCTL,
idle and Windows time-slice multiplex calls. The SD root is mapped as DOS
drive `C:`. Text video, keyboard, timer, minimal mouse detection and the VC
video-shadow probe are also handled.

## Validation

The host probe reaches the complete two-panel interface and lists both panels
from the original distribution directory. The end-to-end ESP32 test builds the
firmware and module, creates a FAT32 SD image, installs `VC.D2E`, executes the
generated `AUTOEXEC.BAT`, runs VC for a bounded interactive frame count and
returns through the harness without a guest fault:

```powershell
.\firmware\esp32_cyd\qemu-xip-volkov-commander-windows.ps1 -FrameLimit 10
```

The validated module size is 1,135,336 bytes. The QEMU run retired 3,159,802
guest instructions and ended with `state=1, reason=8`, the expected active
supervisor state with a per-slice budget boundary.
