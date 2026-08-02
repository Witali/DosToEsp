# Xtensa Assembly Translator Plan

## Objective

Replace the generated-C execution regions with build-time generated Xtensa LX6
assembly while preserving the existing decoder, control-flow discovery, package
ABI and supervisor lifecycle. Lower common x86 instructions directly to compact
Xtensa sequences and call shared C helpers for operations whose inline lowering
would be large or fragile.

The C backend remains available as the semantic reference and fallback until the
assembly backend passes the same host, ESP-IDF and QEMU validation gates.

## Baseline

The 2026-08-02 Alley Cat build provides the initial comparison point:

- application binary: `0xc9e70` bytes (826,992 bytes);
- original relocated MZ image retained in flash: 54,591 bytes;
- 3,232 discovered basic blocks containing 8,480 decoded instructions;
- 13 generated C regions: 445,780 bytes of Xtensa flash code;
- build mode: generated regions compiled with `-O2`.

All size and performance comparisons must use the same ESP-IDF configuration,
partition table, Alley Cat input binary and QEMU frame workload.

## Target architecture

```text
MZ/COM input
  -> existing x86 decoder and CFG discovery
  -> backend-neutral basic blocks
  -> flag liveness and lowering decisions
  -> C backend (reference) or Xtensa assembly backend
  -> ESP-IDF assembler and linker
  -> existing d2e_native_program/package ABI
```

The first assembly backend generates `.S` source rather than raw instruction
bytes. This delegates instruction encoding, literal pools, symbol relocation,
call-range handling, alignment and debug symbols to the Espressif toolchain.

## Execution ABI

Each generated region initially keeps the existing callable shape:

```c
uint32_t d2e_generated_region_NNN(d2e_x86_cpu *cpu,
                                  uint32_t block_budget);
```

The conservative first ABI accesses architectural registers through the
`d2e_x86_cpu` structure at block boundaries. Later stages may cache guest
registers in Xtensa registers within a region, but every helper call, supervisor
exit and unresolved control-flow edge must observe a synchronized CPU state.

Shared helpers use the normal ESP-IDF Xtensa windowed C ABI. The generated
assembly must not reserve ABI-owned `a0`/`a1`, and it must treat caller-saved
registers as clobbered across helper calls.

## Instruction lowering policy

Inline lowering is intended for compact, common operations:

- register moves and constant loads;
- `ADD`, `SUB`, `CMP`, `AND`, `OR`, `XOR`, `TEST`;
- simple increments, decrements and shifts;
- direct conditional and unconditional branches;
- aligned guest-memory loads and stores after address validation is established.

Shared helpers are initially used for:

- `MUL`, `IMUL`, `DIV`, `IDIV` and BCD adjustments;
- string and `REP` operations;
- port I/O and interrupts;
- stack operations that cross a checked-memory boundary;
- segment override and wrapping corner cases;
- unaligned or boundary-crossing guest-memory access;
- unresolved indirect control flow.

An operation moves from a helper to inline assembly only when tests demonstrate
that the inline form is smaller or materially faster without weakening x86
semantics.

## Flag liveness and lazy materialization

Each decoded instruction receives two masks: flags read and flags defined. A
backward data-flow pass computes flag liveness over the complete CFG:

```text
live_out(block) = union(live_in(successor))
live_in(insn)    = flags_read(insn) union
                   (live_out(insn) - flags_defined(insn))
```

The lowering receives the live-defined mask for every instruction:

- no live result flags: emit no flag calculation;
- only `ZF` live: calculate only zero;
- `ADC`/`SBB` consumer: preserve or materialize `CF`;
- `PUSHF`, `LAHF`, interrupt entry or an unknown edge: materialize every
  architecturally observable pending flag.

Partial flag writers require special handling. For example, `INC` defines
`OF`, `SF`, `ZF`, `AF` and `PF` but preserves the incoming `CF`.

The initial implementation may materialize live flags at block exits. A later
optimization can carry a pending descriptor `(operation, width, lhs, rhs,
result)` across a proven single-predecessor edge. Merge points either combine
identical descriptors or materialize before the edge.

## Migration stages

### Stage 1: backend boundary and assembly smoke slice

- Add an explicit `c`/`xtensa-asm` backend selection to the translator.
- Preserve byte-for-byte generated C output for the default backend.
- Generate one `.S` unit for a bounded COM fixture containing register moves,
  immediate loads and a normal region return.
- Add golden generation tests and assemble the unit with the pinned Xtensa
  toolchain.

Exit gate: the assembly unit links into ESP-IDF and produces the same final CPU
state as the C backend for its supported instructions.

### Stage 2: helper ABI

- Define assembly-safe helper entry points with explicit argument and clobber
  contracts.
- Add helpers for unsupported arithmetic, memory, stack and interrupt operations.
- Add mixed inline/helper fixtures.

Exit gate: helper calls preserve all required guest state and satisfy stack
alignment and windowed-ABI requirements.

### Stage 3: flag analysis

- Add per-mnemonic read/define flag masks.
- Implement CFG-wide backward liveness.
- Emit only live flags for arithmetic and logic operations.
- Add fixtures for partial writers, joins, loops, `ADC`/`SBB`, `PUSHF`/`POPF`,
  `LAHF`/`SAHF` and interrupt boundaries.

Exit gate: flag-intensive host fixtures match the C backend, and dead flag
calculations are absent from generated assembly golden files.

### Stage 4: registers and guest memory

- Lower the remaining common register forms.
- Introduce checked direct RAM access and explicit slow helpers for unaligned or
  wrapping accesses.
- Cache guest registers inside safe straight-line regions.

Exit gate: native memory, string, stack/call and rare-instruction fixtures pass.

### Stage 5: control flow and MZ regions

- Emit direct edges within a region.
- Replace large generated-C `switch` dispatchers with compact address tables or
  a shared lookup helper for indirect and cross-region edges.
- Generate split `.S` regions for Alley Cat and retain source-to-guest-address
  symbols for debugging.

Exit gate: every discovered Alley Cat block is reachable through the assembly
dispatcher and no C-generated execution region is linked in assembly mode.

### Stage 6: validation and optimization

- Run the complete host test suite against both backends.
- Run bounded and board-device QEMU workloads.
- Compare final CPU state, rendered-frame hashes, audio telemetry, retired guest
  instructions, application size and execution time.
- Tune inline/helper thresholds and use Xtensa density forms where the assembler
  and target support them.

Initial success target: reduce the 445,780-byte translated region contribution
by at least 30 percent without a semantic regression. Stretch target: keep the
translated region contribution below 220 KiB.

## Safety and rollout

- The new backend is opt-in until all exit gates pass.
- Unsupported instructions fail translation with their guest address; they do
  not silently execute with weakened semantics.
- The generated assembly is build-time code in the signed application image;
  the firmware does not make RAM executable or generate code at runtime.
- Each migration stage is a focused commit with its own tests and size report.
