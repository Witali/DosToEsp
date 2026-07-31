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
- Every unsupported instruction, interrupt, port or indirect target stops with
  an address and guest-state diagnostic.
- Each semantic group has host tests before it is used in firmware.
- Generated game blocks are compiled by the ESP32 toolchain. The firmware must
  not contain x86 fetch/decode/execute or bytecode dispatch loops.
- Every logically complete improvement is committed separately.

## Phases

### 1. Freeze the target binary

- [ ] Put the legally obtained game and its required data files under
  `games/` (ignored by Git).
- [ ] Detect COM, MZ EXE or boot-image format.
- [ ] Record size and SHA-256 in a local analysis manifest.
- [ ] Refuse to reuse analysis output when the binary fingerprint changes.

Acceptance gate: one unambiguous target image and reproducible fingerprint.

### 2. Static inventory

- [ ] Build reachable 16-bit CFG from the entry point.
- [ ] Report instruction and prefix frequencies.
- [ ] Inventory direct and unresolved indirect calls/jumps.
- [ ] Inventory interrupts, `IN`/`OUT`, segment use and CGA references.
- [ ] Flag overlapping or self-modifying code candidates.
- [ ] Emit deterministic JSON and Markdown reports.

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

- [ ] Add ModR/M memory addressing and segment overrides.
- [ ] Add stack, direct/indirect calls and returns.
- [ ] Add boolean, shifts, rotates, multiply and divide as observed.
- [ ] Add string operations and REP variants as observed.
- [ ] Complete exact 8086 flags for every implemented operation.
- [ ] Reject unobserved 80186/386 instructions unless the target requires a
  documented profile extension.

Acceptance gate: the target's traced code translates without unsupported
instruction diagnostics and passes differential semantic tests.

### 5. Native register caching

- [ ] Form native superblocks from compatible guest basic blocks.
- [ ] Keep live AX/BX/CX/DX/SI/DI/BP/SP values in compiler-allocated Xtensa
  registers across internal edges.
- [ ] Spill only at runtime calls, indirect exits and diagnostic boundaries.
- [ ] Add liveness information and an assembly audit for hot paths.

Acceptance gate: host state remains identical while Xtensa assembly shows
fewer guest-state loads/stores and no x86 interpreter dispatch.

### 6. Program and DOS machine loading

- [ ] Complete PSP and COM startup semantics, or implement MZ header,
  relocation and initial register loading if the fingerprinted target is EXE.
- [ ] Add only the DOS/BIOS calls observed in the inventory.
- [ ] Model the required conventional-memory allocation and files from bundled
  game assets.

Acceptance gate: headless execution reaches video initialization with the
expected register/memory digest.

### 7. Hardware environment

- [ ] Connect the existing CGA modes 4/5 renderer to the CYD ST7789 using the
  verified HLV-codec pinout and SPI DMA setup.
- [ ] Add dirty-line/region updates and centre 320x200 inside 320x240.
- [ ] Map the selected physical input to the keyboard interface observed by
  the game.
- [ ] Provide deterministic BIOS/PIT time and real-time ESP32 scheduling.
- [ ] Convert observed PC speaker/PIT programming to the board audio output.

Acceptance gate: title screen, input, first playable scene and sound on the
physical board without timing-dependent speed changes.

### 8. End-to-end validation and optimisation

- [ ] Headless test with scripted input and CGA frame hashes.
- [ ] QEMU boot of the real generated firmware with matching state/frame
  digests.
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
- host tests, native Xtensa assembly audit, ESP32 QEMU smoke test and physical
  CYD2USB smoke test.

Immediate work queue:

1. add the deterministic static inventory tool and test it on the fixture;
2. fingerprint the real Alley Cat binary when it is placed under `games/`;
3. use that inventory to order instruction and runtime implementation.
