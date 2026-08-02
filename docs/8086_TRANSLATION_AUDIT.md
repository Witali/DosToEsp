# 8086 Translation Audit

## Scope

The audit covers the documented Intel 8086/8088 integer instruction set,
including byte and word operand forms, segment addressing, string prefixes,
near/far and direct/indirect control transfers, flags, and processor-control
instructions. Later x86 extensions are outside this profile.

The canonical instruction behavior and affected flags are checked against:

- Intel, *Intel 64 and IA-32 Architectures Software Developer's Manual*,
  Volume 2, Instruction Set Reference:
  <https://www.intel.com/content/www/us/en/content-details/671110/>
- AMD, *AMD64 Architecture Programmer's Manual*, Volume 3,
  General-Purpose and System Instructions, publication 24594:
  <https://docs.amd.com/v/u/en-US/24594_3.37>
- AMD, *Am186ES/ESLV and Am188ES/ESLV Microcontrollers Data Sheet*,
  publication 20002, for the backward-compatible 8086/8088 register,
  addressing, segment-selection, and I/O model:
  <https://www.amd.com/content/dam/amd/en/documents/archived-tech-docs/datasheets/20002.pdf>

## Test policy

`tests/test_isa8086.py` decodes canonical machine-code samples rather than
testing a hand-written mnemonic allowlist. Every documented family must either
translate successfully or appear in the explicit gap set. Removing a gap
therefore requires an executable regression test, and newly introduced silent
coverage loss fails the test.

Instructions that require absent external hardware, such as 8087 `ESC`, remain
explicit capability failures and must never be reported as translated 8086 CPU
semantics.

## Current result

The catalog contains 118 canonical encodings. Of these, 116 exercise 8086 CPU
semantics and translate without a mixed-backend gap. The two external cases,
`WAIT` and 8087 `ESC`, remain explicit hardware capability failures.

The `xtensa-asm` backend selects translation per basic block. Twelve canonical
forms currently have a direct handwritten Xtensa lowering. The remaining 104
forms are emitted as generated CISC helper regions and compiled to Xtensa by
ESP-IDF. This is a lowering choice, not a semantic coverage gap.

Both paths omit every statically decoded executable byte from the retained DOS
image. Only initialized data fragments and relocation words that belong to
those fragments are emitted. Recovered source jump-table entries are likewise
omitted because their targets are represented by the generated dispatcher.

`scripts/audit-xtensa.ps1` compiles the generated assembly, generated CISC
helper, and runtime ABI assertions with `xtensa-esp32-elf-gcc`. The host suite
also executes instruction-family fixtures for arithmetic flags, decimal
adjust, multiply/divide traps, strings and repetition, ports, stack operations,
near/far control flow, interrupts, and recovered indirect targets.

The ESP32 QEMU assembly smoke fixture deliberately crosses from a direct
Xtensa block into a generated stack-operation helper and back through the
shared dispatcher. It verifies the call ABI, block budget, retired-instruction
accounting, CPU-state synchronization, and final data result at runtime.
