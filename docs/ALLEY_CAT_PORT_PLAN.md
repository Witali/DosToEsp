# Alley Cat native port plan

This is the working roadmap for translating a specific DOS Alley Cat binary
into native Xtensa LX6 code for the classic ESP32 CYD2USB board. DosToEsp does
not execute an x86 instruction interpreter on the board. It emulates only the
observable PC environment required by the game: DOS/BIOS services, CGA,
keyboard, timer and speaker.

## Rules and completion criteria

- The exact game binary is identified by filename, format, size and SHA-256.
- Translation coverage is driven by static analysis and a reference trace of
  that binary, not by implementing an arbitrary PC emulator.
- The deliverable is a general automatic COM/MZ-to-ESP32 source generator.
  Target-specific hand translations are not accepted; Alley Cat is the primary
  integration test for the general backend.
- Every unsupported instruction, interrupt, port or indirect target stops with
  an address and guest-state diagnostic.
- Each semantic group has host tests before it is used in firmware.
- Generated game blocks are compiled by the ESP32 toolchain. The firmware must
  not contain x86 fetch/decode/execute or bytecode dispatch loops.
- Every logically complete improvement is committed separately.

## Phases

### 1. Freeze the target binary

- [x] Put the user-supplied game and its required data files under
  `games/` (ignored by Git).
- [x] Detect COM, MZ EXE or boot-image format.
- [x] Record size and SHA-256 in the target manifest.
- [x] Refuse to merge trace output when the binary fingerprint changes.

Acceptance gate: one unambiguous target image and reproducible fingerprint.

### 2. Static inventory

- [x] Build the initial reachable 16-bit CFG from the entry point.
- [x] Report instruction and prefix frequencies.
- [x] Inventory direct and unresolved indirect calls/jumps.
- [x] Inventory interrupts, `IN`/`OUT`, segment use and CGA references.
- [x] Flag overlapping and memory-write/code-range check candidates.
- [x] Emit deterministic JSON and Markdown reports.

Acceptance gate: the report either covers every reachable direct block or
names the exact address and reason analysis stopped.

### 3. Reference execution trace

- [ ] Instrument the local Pico-286 reference or another independent runner.
- [ ] Capture executed `CS:IP`, interrupts, ports, CGA writes, keyboard reads,
  timer accesses and speaker programming.
- [ ] Script input from launch through the title screen and first playable
  scene.
- [ ] Merge observed indirect targets into the static inventory.

Acceptance gate: a deterministic trace digest and an ordered list of missing
native translation/runtime capabilities. Pico-286 CPU code remains reference
only and is not copied into DosToEsp.

### 4. Translation coverage

- [x] Add ModR/M memory addressing and segment overrides.
- [x] Add stack, direct near calls and near returns.
- [x] Recover the bounded CS-relative jump table and add direct far return,
  both with generated regression programs.
- [x] Recover handlers installed into the real-mode interrupt vector table as
  additional AOT control-flow roots; Alley Cat installs IRQ1 vector 9 with
  handler variants at `CS:14B3` and `CS:14FB`.
- [x] Add boolean, shifts, rotates and multiply forms observed in the target
  (no divide site is present in the current inventory).
- [x] Add string operations and REP variants as observed.
- [x] Add the IRQ1-only `REPNE SCASB` and `IRET` forms, and translate an
  external far jump to a strict untranslated-target boundary.
- [ ] Complete exact 8086 flags for every implemented operation.
- [x] Reject 80186/80286/386 instructions and prefixes: the fixed CPU profile
  is documented Intel 8086, with no profile extension for this port.

Acceptance gate: the target's traced code translates without unsupported
instruction diagnostics and passes differential semantic tests.

### 5. Native register caching

- [x] Form native regions from compatible guest basic blocks.
- [x] Keep used AX/BX/CX/DX/SI/DI/BP/SP values in compiler-allocated Xtensa
  registers across internal edges.
- [x] Spill at runtime calls, budget yields and diagnostic boundaries.
- [ ] Replace the current used-register set with block-level liveness and
  selective spill information for large real-game regions.
- [x] Audit that internal guest blocks do not become Xtensa ABI function
  boundaries.

Acceptance gate: host state remains identical while Xtensa assembly shows
fewer guest-state loads/stores and no x86 interpreter dispatch.

### 6. Program and DOS machine loading

- [x] Pack the fingerprinted MZ load module and implement PSP, relocation and
  initial register loading with all nine target relocations verified.
- [x] Apply those relocations to the translation view as well as the runtime
  image, so relocated segment immediates are native constants at the selected
  load segment.
- [x] Generate segmented native target keys and connect the MZ image to its
  translated regions.
- [ ] Add only the DOS/BIOS calls observed in the inventory.
- [ ] Model the required conventional-memory allocation and files from bundled
  game assets.

Acceptance gate: headless execution reaches video initialization with the
expected register/memory digest.

### 7. Hardware environment

- [x] Connect the existing CGA modes 4/5 renderer to the CYD ST7789 using the
  verified HLV-codec pinout and SPI DMA setup.
- [ ] Add dirty-line/region updates and centre 320x200 inside 320x240.
- [x] Map BOOT/UART/QEMU input to XT make/break scan codes, ports `60h`/`64h`
  and IRQ1 as observed by
  the game.
- [ ] Provide deterministic BIOS/PIT time and real-time ESP32 scheduling.
- [x] Confirm that the DOS target uses PIT channel 2 and port 61h for title
  music and in-game PC Speaker music/effects.
- [x] Convert observed PC speaker/PIT programming to a portable PCM
  synthesizer and the board's GPIO26 continuous-DAC output; verify the same
  signal through QEMU DirectSound/WAV.

Acceptance gate: title screen, input, first playable scene and sound on the
physical board without timing-dependent speed changes.

### 8. End-to-end validation and optimisation

- [x] Headless test with scripted input and CGA frame hashes.
- [x] Compile, link and boot the real generated Alley Cat firmware in ESP32
  QEMU, reaching the first strict environment boundary after native entry.
- [x] QEMU boot of the real generated firmware through its setup prompts and
  into a visually verified first playable scene, with state/frame digests.
- [ ] Physical CYD run with UART telemetry for frame times, heap, block counts
  and unknown targets.
- [ ] Profile and optimise superblocks, flags, segment addressing, CGA dirty
  updates and IRAM placement.

Acceptance gate: repeatable first-level gameplay on hardware and clean host,
QEMU and physical-board regression tests.

## Current status

Completed foundations:

- native AOT block generation for a synthetic COM fixture;
- core 16-bit register/flag state and sparse real-mode memory;
- CGA 320x200 2bpp peripheral semantics and row renderer;
- deterministic COM/MZ fingerprint, reachable CFG and static hardware/API
  inventory reports with fixture regression tests;
- fingerprint-checked JSONL reference trace contract and deterministic summary
  for code locations, interrupts, ports and CGA writes;
- unified executable-to-source frontend with deterministic reports, generated
  image/native files and a strict machine-readable completion/blocker manifest;
- common segmented MZ native-region generation with preserved `CS:IP`, packed
  relocation metadata, translation-time relocated immediates and no
  target-specific code;
- common 8086 ModR/M addressing for 8/16-bit operands, including DS/SS default
  selection and explicit ES/CS/SS/DS overrides, compiled by the Xtensa audit;
- cached-SP guest stack operations plus direct near calls/returns as native
  region edges, including nested-call host and Xtensa regression fixtures;
- native boolean/test/not operations, status-control instructions and
  LAHF/SAHF transfer semantics with generated flag regression tests;
- exact count-zero/one flag handling and native helpers for observed SHL, SHR,
  RCL and RCR forms, including register, CL-count and memory operands;
- native MOVS/STOS/LODS loops for byte/word and observed REP forms, with
  DS:SI/ES:DI wrapping, CX completion and DF-controlled direction;
- generic 8-bit IN/OUT callbacks preserved across program loading, with strict
  unknown-port stops and native immediate/DX port operands;
- native MUL, XCHG, AAA, LOOPE/LOOPNE and RETF semantics, exercised together
  by a compact generated COM program on both the host and Xtensa compiler;
- strict recovery of the compiler's bounded `CS:[BX+table]` switch idiom,
  expanding the Alley Cat CFG to 8368 instructions with no unresolved edges;
- native ADC plus PUSHF/POPF semantics discovered behind that table, each
  covered by another compact generated COM program;
- complete automatic `CAT.EXE` to `game_native.c` generation with 8368/8368
  instruction sites covered and the full output assembled to an Xtensa object;
- automatic partitioning of the large MZ control-flow graph into 13 bounded
  native regions, with `CS:IP` handoff and no x86 instruction dispatch loop;
- successful ESP32 QEMU boot of the real 624,944-byte Alley Cat firmware,
  executing five native-translated guest instructions before the first strict
  environment boundary, BIOS `INT 11h`;
- successful native Windows QEMU run through HLV-codec's ST7789 and SDSPI
  board models: the FAT card marker is read through SPI3 and changing CGA mode
  4 frames are submitted to the 320x240 SPI2 display;
- host tests, native Xtensa assembly audit, ESP32 QEMU smoke test and physical
  CYD2USB smoke test.

Immediate work queue:

1. generalise native pattern recognition from explicit REP MOVS/STOS to
   compiler-generated copy/fill loops and guarded unrolled forms;
2. make the QEMU BIOS tick source deterministic before treating a particular
   animation-frame hash as a golden result;
3. capture an independent reference trace and compare the input/video path;
4. flash the same generated firmware to the physical CYD and verify the first
   playable scene on the ST7789 panel plus PC-speaker output on GPIO26;
5. generalise the next DOS/BIOS or hardware boundary exposed by another DOS
   program, keeping Alley Cat as an integration test rather than a special
   translation path.
