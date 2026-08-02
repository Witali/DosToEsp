# Translation Optimization TODO

This backlog records the next improvements identified by the 2026-08-02
translator audit. Work items are ordered by expected benefit and dependency.
Every change must preserve 8086 behavior, keep reusable x86 semantics in the
DOS shell, and be evaluated with the same input, build configuration and
bounded workload.

## Audit checkpoint

- Alley Cat contains 3,232 discovered blocks and 8,480 decoded instructions.
- The current split is 2,850 direct Xtensa blocks and 382 CISC fallback blocks.
- The external XIP module is 424,636 bytes: 302,088 bytes of IROM and 31,420
  bytes of DROM, plus metadata and section-alignment gaps.
- Generated assembly contains 9,256 literal slots but only 4,132 distinct
  values. Literal interning has a measured upper bound of 20,496 bytes before
  accounting for instruction-range and relocation constraints.
- Static generated code contains about 4,292 CPU-register references, 3,102
  segment references and 2,482 guest-memory helper calls.
- Checked hash dispatch already bounds direct-address lookup. The bounded QEMU
  comparison, 41.8 seconds versus 41.7 seconds for hybrid dispatch, showed no
  measurable speed difference; further dispatch tuning is not a priority
  without target-cycle profiles.

## 0. Measurement infrastructure

- [x] Add an optional ESP32 profiling build that reads the Xtensa cycle counter
  around each bounded translated supervisor step and reports calls, total,
  minimum and maximum cycles plus cycles per 1,000 retired guest instructions.
  QEMU values are useful only for repeated paired comparisons: the virtual
  counter varied materially between identical builds, so physical-board
  measurements remain the acceptance authority.
- [ ] Extend cycle attribution to native blocks, CISC regions and shared
  helpers after the region-level counter identifies a regression.
- [ ] Report mixed-backend crossings, memory-helper traffic, interrupt and port
  calls, string operations and budget exits.
- [x] Keep profiling instrumentation out of release builds unless
  `D2E_TRANSLATION_PROFILE` is explicitly enabled.
- [ ] Define a repeatable physical-board workload in addition to the bounded
  QEMU correctness run.

## 1. Literal and immediate compaction

- [x] Define the preferred 8086-to-ESP32 instruction pairs and selection rules
  in `X86_XTENSA_INSTRUCTION_PAIRS.md`, verified against the official Cadence
  ISA summary and the installed ESP32 assembler.
- [x] Intern numeric assembly literals by their exact normalized 32-bit value.
  The current API emits no relocatable literals, so value identity is
  sufficient; relocatable values must use a typed key when introduced.
- [x] Reuse common constants such as the load segment instead of emitting one
  source literal per instruction.
- [x] Select `movi` for exact signed 12-bit values used by immediate operands
  and guest-memory displacement calculations.
- [x] Select `addi` for signed 8-bit `ADD` immediates when carry is dead.
  Explicit `mov.n` and `movi.n` selection was also evaluated, but linked IROM
  was unchanged because the Xtensa assembler already applies density
  relaxation; keep the source-neutral forms.
- [ ] Select `addi` for representable `SUB immediate` forms when carry is dead.
- [x] Measure generated literals, IROM, DROM and total module bytes separately.
- [x] Evaluate the original 15-20 KiB estimate. Generated `.long` entries fell
  from 9,256 to 3,891, but linker relaxation had already merged many duplicate
  literals. Linked IROM fell by 2,164 bytes, from 302,088 to 299,924 bytes.
  DROM and the 424,636-byte module file did not change because DROM remains on
  the same 64 KiB boundary.

## 2. Remove high-volume CISC fallback

- [x] Lower the remaining byte, memory-source and live-flags forms of `ADD`.
  Direct `CF`/`ZF` subsets stay inline, full live flags use the common x86
  helpers, and small immediates use `addi` when carry is dead. This moved 137
  Alley Cat blocks out of fallback and reduced IROM by 5,698 bytes.
- [x] Lower `INT imm8` and `INT3` as direct calls to the program-independent
  interrupt helper. This moved 113 Alley Cat blocks out of fallback, primarily
  BIOS `INT 1Ah` and `INT 10h` calls, while preserving the architectural next
  IP before entering the shell service.
- [x] Lower all 8/16-bit immediate/DX forms of `IN` and `OUT` as direct calls
  to shared port helpers. This reduced IROM by 4,652 bytes and fallback by 43
  blocks. Three direct QEMU profiles had a 58,238 cycles-per-1,000 median,
  below the 58,565 median of the surrounding identical-workload controls;
  retain it, with physical-board confirmation still required.
- [ ] Lower variable-count shifts directly or through shared ALU helpers. The
  audit found 33 fallback blocks.
- [ ] Route `MOVS`, `STOS`, `LODS` and `SCAS`, including `REP` forms, to common
  string helpers without generating game-private implementations.
- [ ] Cover the remaining rare forms: byte `MUL`, `ADC`, `XCHG`, `LAHF`,
  `SAHF`, `IRET`, far `RET` and far `JMP`.
- [ ] Recount fallback blocks after every focused lowering and retain a change
  only when total size and target performance do not regress unexpectedly.

## 3. Flag materialization

- [ ] Extend CISC lowering from all-or-none dead-flag elimination to an exact
  required-flag mask.
- [ ] Represent a pending flag result as operation, width, operands and result
  across safe block edges.
- [ ] Materialize architectural flags only at a real consumer such as `Jcc`,
  `PUSHF`, `LAHF`, an interrupt, a helper boundary or an unresolved edge.
- [ ] Preserve instruction-specific unaffected and undefined flags; in
  particular, keep `CF` unchanged for `INC` and `DEC`.
- [ ] Add differential tests for every live-flag subset used by direct and CISC
  lowering.

## 4. Trace-level intermediate representation

- [x] Add a block-local dynamic-programming planner that chooses non-overlapping
  register-cached runs by estimated Xtensa instruction count and CPU-register
  memory traffic. Equal instruction counts prefer fewer CPU accesses.
- [x] Cache up to four 16-bit x86 registers in `a4`, `a5`, `a8` and `a9` for
  helper-free `MOV`, dead-flag `ADD`/`SUB`/logical operations, `INC`, `DEC` and
  `NOT`. Use `a10` only as a temporary inside a run that cannot call a helper.
- [x] Load only values read before their first write and spill only dirty x86
  registers at the selected run boundary.
- [ ] Introduce a backend-neutral micro-operation IR for one basic block before
  extending it across control-flow edges.
- [ ] Add constant propagation, redundant load/store removal, dead guest-register
  store elimination and address-expression reuse.
- [ ] Form short traces from fall-through and single-predecessor edges, guided
  by physical-board profiles when available.
- [ ] Extend register caching across basic-block edges and include segment bases
  after the trace IR can reconcile cached state at joins.
- [ ] Spill dirty architectural state before helpers, supervisor exits and
  unresolved edges once cached runs are allowed to cross block boundaries.
- [ ] Hoist the retired-instruction budget check to trace boundaries while
  preserving exact accounting and bounded supervisor response time.

## 5. Guest-memory fast paths

- [ ] Profile memory-helper call counts and cycles before selecting operations
  to inline.
- [ ] Add a guarded conventional-RAM fast path with a shared slow path.
- [ ] Preserve 20-bit physical wrapping, 16-bit segment-offset wrapping between
  the two bytes of a word, unaligned accesses, CGA mapping and unmapped-memory
  behavior.
- [ ] Keep word accesses byte-accurate when the first byte is at offset
  `FFFFh`; do not replace them with an unconditional aligned Xtensa word load.
- [ ] Add boundary tests for RAM limits, CGA limits, segment wrapping and odd
  addresses.

## 6. CISC region and boundary cleanup

- [ ] Re-evaluate dense block IDs after the high-volume direct lowerings reduce
  the fallback set.
- [ ] Let connected fallback blocks execute inside one CISC region until an
  assembly handoff, runtime boundary or shared budget exit.
- [ ] Synchronize only live or dirty CPU fields at mixed-backend boundaries.
- [ ] Partition remaining CISC blocks by CFG locality and measured linked size
  instead of fixed address ranges.

## 7. XIP module format v2

- [ ] Design a layout that does not require a mostly empty 64 KiB prefix before
  IROM and minimizes padding before DROM.
- [ ] Keep code executable directly from mapped flash and retain stable import
  relocations into the DOS shell.
- [ ] Measure file-size savings separately from translated-code savings.
- [ ] Evaluate optional compression only for data fragments; decompression must
  remain a common shell service and must not affect direct code execution.
- [ ] Retain backward loading support or reject old/new module versions with a
  clear English diagnostic.

## 8. Program discovery and compatibility

- [ ] Add abstract interpretation for constant segment/register values and
  indirect control targets.
- [ ] Recognize relocation-backed pointer tables and convert proven targets to
  native labels or dense IDs without retaining the original address table when
  it is not observable as data.
- [ ] Add interprocedural call/return summaries and code/data conflict checks.
- [ ] Detect writes to translated code pages and choose an explicit policy:
  invalidate and interpret, preserve code bytes in compatibility mode, or
  reject the program during translation.
- [ ] Add a hybrid interpreter path for runtime-generated code, overlays and
  self-decompressing programs.
- [ ] Never silently return zero-filled bytes for original code that the guest
  can read, checksum or modify.

## Correctness gates

- [ ] Use Intel's instruction reference as the primary semantic source and the
  AMD Architecture Programmer's Manual as an independent cross-check.
- [ ] Keep the configured CPU model explicit in tests. Do not import later x86
  shift-count, flag or stack behavior into the 8086 backend.
- [ ] Run exhaustive or boundary-focused host tests for each newly lowered
  instruction form.
- [ ] Run translated-versus-reference differential tests for registers, flags,
  memory, I/O events and stop reasons.
- [ ] Require the bounded Alley Cat QEMU run to render the expected frames,
  preserve normal speaker timing and return cleanly to the shell.
- [ ] Record before/after IROM, DROM, total module bytes, fallback-block count,
  helper calls and target cycles in the evaluation log.

## Evaluation log

| Change | IROM bytes | DROM bytes | Module bytes | Fallback blocks | Target cycles | Decision |
|---|---:|---:|---:|---:|---:|---|
| Audit checkpoint | 302,088 | 31,420 | 424,636 | 382 | Not measured | Baseline |
| Intern literals and select `movi` | 299,924 | 31,420 | 424,636 | 382 | Not measured | Keep: IROM -2,164; 60-frame QEMU run passed at 259 Hz |
| Automatic block-local register cache | 299,512 | 31,420 | 424,636 | 382 | Not measured | Keep: 126 runs, IROM -412, 133 instructions and 101 CPU accesses removed; QEMU passed at 259 Hz |
| Optional supervisor-step cycle profile | 299,512 | 31,420 | 424,636 | 382 | 70,358 cycles/1K instructions | Keep: opt-in instrumentation; 60-frame QEMU control retired 12,882,251 guest instructions at 259 Hz |
| Direct byte/memory/live-flags `ADD` | 293,814 | 31,420 | 424,636 | 245 | 68,688 cycles/1K instructions | Keep: IROM -5,698, fallback -137 and measured cycles -2.4%; 60-frame QEMU run passed at 259 Hz |
| Direct `INT imm8` and `INT3` | 281,974 | 31,420 | 424,636 | 132 | 46,381-60,946 cycles/1K instructions | Keep: IROM -11,840 and fallback -113; repeated identical-build QEMU values exposed virtual-counter variability, physical profile pending |
| Direct all-form `IN`/`OUT` | 277,322 | 31,420 | 424,636 | 89 | 58,238 cycles/1K instructions | Keep: IROM -4,652 and fallback -43; median of three direct QEMU runs is below the surrounding 58,565-cycle control median; physical profile pending |
