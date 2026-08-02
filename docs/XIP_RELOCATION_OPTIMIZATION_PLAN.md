# XIP relocation optimization plan

This document defines the staged plan for reducing or eliminating the native
Xtensa relocation table in installable D2E XIP modules. It covers relocations
created for native IROM, DROM, and resident-shell import references. Original
DOS MZ relocation records are a separate format and are not changed by this
work.

## Baseline

The current `D2EXIP1` format stores every native relocation as four 32-bit
fields: module-relative patch offset, target kind, target value, and signed
addend. Each record therefore occupies 16 bytes.

The Volkov Commander 4.00 module is the initial optimization target:

| Item | Value |
| --- | ---: |
| Original `VC.COM` size | 65,142 bytes |
| Translated instruction sites | 12,449 |
| Complete `VC.D2E` size | 1,135,336 bytes |
| IROM size | 411,187 bytes |
| DROM size | 152,296 bytes |
| Native relocation count | 28,805 |
| Native relocation bytes | 460,880 bytes |
| Alignment padding | 110,069 bytes |

The relocation population is highly compressible:

| Target kind | Records | Unique targets |
| --- | ---: | ---: |
| IROM | 28,635 | 4,005 |
| DROM | 97 | 97 |
| Resident-shell import | 73 | 41 |

Records are already sorted by patch offset. Of all patch deltas, 28,702 are at
most four bytes and 28,774 are at most 16 bytes. Internal IROM and DROM records
always have a zero addend. The current fixed-width encoding repeats all of this
information.

## Goals

- Reduce the Volkov Commander module below 800 KiB in the first format-only
  stage.
- Preserve arbitrary 64-KiB-aligned IROM and DROM mappings.
- Keep relocation work in the installation path; module execution must not
  spend time decoding relocation data.
- Decode records as a bounded stream with constant auxiliary memory.
- Continue accepting existing `D2EXIP1` modules during migration.
- Keep module generation deterministic.
- Eventually support a position-independent module with no native relocation
  table.

## Non-goals

- Changing DOS MZ relocation semantics or their four-byte guest records.
- Coupling an installable module to one firmware build or one physical Flash
  slot.
- Reserving fixed ESP32 virtual addresses as the primary solution.
- Replacing the resident-shell import ABI with firmware function addresses.

## Stage 1: measure and classify

Add a relocation report to the XIP packer or a companion inspection tool. The
report must contain:

- encoded and decoded byte counts;
- counts by IROM, DROM, and import target kind;
- unique-target counts and target reuse distribution;
- patch-delta distribution and consecutive patch runs;
- addend distribution;
- relocation bytes and alignment bytes as percentages of the complete module.

Record baselines for Volkov Commander and Alley Cat in automated tests. This
prevents later code-generation changes from silently restoring fixed-width
growth.

## Stage 2: introduce a compact relocation stream

Prototype a version-2 relocation encoding while keeping the existing logical
record model. The decoder reconstructs the same `patch, kind, target, addend`
values currently consumed by the installer.

The initial encoding should use:

- unsigned LEB128 patch deltas instead of complete patch offsets;
- a compact tag containing the target kind and optional-field flags;
- target dictionaries for repeated IROM targets when a dictionary is smaller
  than direct offsets;
- unsigned LEB128 direct offsets for low-reuse IROM and DROM targets;
- shell-ABI import indexes instead of complete target words;
- signed LEB128 addends only when an addend is nonzero;
- optional run records for consecutive four-byte patch locations.

The packer must select dictionary or direct-target encoding by measured output
size rather than by a hard-coded program-specific choice. Streams must remain
sorted by patch location.

Version 2 needs explicit encoded-stream size and encoding identifiers in the
header. The version-1 header and record parser remain available for installed
legacy modules. The installer must reject:

- non-monotonic, unaligned, duplicate, or out-of-range patch locations;
- invalid target kinds and import indexes;
- overflowing LEB128 values and arithmetic;
- truncated dictionaries, streams, and optional fields;
- decoded record counts that differ from the header.

The installer should decode and apply one record at a time. It must not expand
the compact stream into a RAM copy of the complete version-1 table.

Expected result: reduce the Volkov Commander relocation payload from 460,880
bytes to approximately 70-120 KiB. Depending on the resulting 64-KiB boundary,
the complete module should be approximately 680-750 KiB.

## Stage 3: enable safe Xtensa call relaxation

The current module compiler uses `-mlongcalls`, and the final linker retains
the resulting absolute literal references. Test final linking with:

```text
--relax --size-opt --emit-relocs
```

The linker should convert reachable internal long-call sequences back to
PC-relative `call8` instructions. Keep unresolved resident-shell calls in a
long-call form until import veneers are available.

Before enabling this by default:

- verify that all relocation kinds remaining after relaxation are supported;
- verify post-relaxation literal values, because literal pools may be merged;
- compare generated code and relocation counts with and without relaxation;
- run native control-flow tests and both XIP QEMU targets;
- confirm that `--emit-relocs` describes the final patch words.

If global `-mlongcalls` still blocks useful relaxation, compile internal calls
normally and mark only external import declarations as long calls. Do not emit
an out-of-range direct call to an unresolved import.

## Stage 4: replace absolute dispatch pointers

Compiler relaxation cannot remove absolute addresses intentionally stored in
dispatch and target tables. Change generated tables to contain offsets relative
to the IROM base instead of native pointers. The dispatch path adds the active
module base before an indirect transfer.

Apply the same model to DROM references where practical:

- store IROM and DROM offsets in generated descriptors;
- derive complete mapped addresses from the active module context;
- keep direct PC-relative calls for statically known internal targets;
- use compact indexes for repeated translated targets.

Measure the execution cost of the extra base addition. Prefer one base addition
at an indirect-dispatch boundary over repeated additions inside translated
instruction bodies.

## Stage 5: route imports through a runtime table

Pass a resident-shell import table through the native runtime context. Generated
code then resolves imports by stable ABI index instead of embedding firmware
addresses at every call site.

If direct generated calls are required for performance, create one local veneer
per used import. Only veneers access the runtime import table; all translated
call sites use PC-relative calls to the local veneer. This bounds import glue by
the number of unique imports rather than the number of call sites.

The shell import ABI version remains in the module header and is validated
before execution.

## Stage 6: zero-relocation modules

A module can declare zero native relocations when all of the following hold:

- internal direct calls are PC-relative and in range;
- indirect code targets are offsets from the mapped IROM base;
- data targets are offsets from the mapped DROM base or active module context;
- resident services are reached through the runtime import table or local
  veneers;
- no absolute native address remains in an IROM or DROM patch word.

The packer must independently scan final ELF relocations and reject a module
that claims zero relocations while retaining an absolute mapped reference.
Zero-relocation output is an optimization, not a requirement for accepting a
translated program.

## Validation

Each stage requires:

1. Unit tests for deterministic encoding and decoding.
2. Malformed-stream and integer-overflow tests.
3. Round-trip comparison against version-1 logical relocation records.
4. Installation of the same module at two valid Flash extents, when the test
   harness can reserve both mappings.
5. Complete host tests.
6. Alley Cat XIP QEMU execution.
7. Volkov Commander XIP QEMU execution through the expected frame and return.
8. Size reports for the relocation payload, IROM, DROM, padding, and complete
   module.

The first compact-format milestone is accepted when Volkov Commander remains
functionally identical, its complete module is below 800 KiB, and version-1
modules still install. The relative-reference milestone targets fewer than five
percent of the baseline native relocation records. The final milestone has zero
native records without fixed-address or firmware-build coupling.

## Delivery sequence

Keep implementation changes independently reviewable:

1. Relocation analysis report and regression fixtures.
2. Version-2 codec and strict decoder tests.
3. Streaming ESP32 installer support with version-1 compatibility.
4. Version-2 packer output enabled by default.
5. Linker relaxation experiment and guarded rollout.
6. Relative dispatch/data tables.
7. Runtime import table and veneers.
8. Zero-relocation validation and output mode.

Do not combine a container-format migration with call-generation or dispatch
changes in one commit. Keeping the stages separate makes size and correctness
regressions attributable.
