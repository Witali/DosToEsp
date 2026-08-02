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
