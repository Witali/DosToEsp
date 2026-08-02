# CISC helper optimization TODO

This backlog tracks size reductions for the mixed Xtensa assembly backend.
Every item must preserve 8086 behavior, must not reduce execution speed, and
must be evaluated against the same Alley Cat input, ESP-IDF configuration and
bounded QEMU workload.

## Baseline

- Application image: 694,000 bytes (`0xA96F0`).
- Eleven generated CISC regions: 427,537 bytes of linked flash code.
- CISC fallback: 2,684 basic blocks.
- Direct Xtensa path: 548 basic blocks and 58,961 bytes of linked flash code.
- Retained Alley Cat data and descriptors: 30,903 bytes.
- Bounded QEMU result: CGA mode 4, 14,118,099 retired guest instructions,
  clean shell return, and `D2E_QEMU_DONE,0`.

## Work items

- [x] Route a translated target directly to its CISC region; remove sequential
  probing of up to eleven region functions. Dense local block routing remains
  a separate item below.
- [ ] Replace sparse module-address switches with compact dense block IDs.
- [ ] Let a CISC region execute connected blocks until it reaches an assembly
  handoff, a runtime boundary, or the shared block budget.
- [x] Specialize mixed-backend CISC entry points for one basic block and
  remove their unused block-budget and post-block redispatch scaffolding.
- [ ] Reduce redundant full CPU register synchronization at mixed-backend
  boundaries.
- [x] Apply whole-program flag liveness to CISC lowering and emit plain
  arithmetic when no produced status flag is live.
- [ ] Materialize only the required status-flag subset when some, but not all,
  produced flags remain live.
- [x] Use a bounded 32-bit retired-instruction delta and materialize the 64-bit
  counter only at synchronization points.
- [x] Share static MZ guest-PC materialization at each CISC region boundary
  instead of repeating the CS-relative formula on every control-flow edge.
- [x] Share cold budget-exhaustion paths instead of repeating them in every
  direct assembly block.
- [x] Remove stop-reason checks only after translator-backed proof that the
  preceding operation cannot fault.
- [ ] Partition CISC blocks by CFG locality and estimated linked byte size,
  rather than fixed address-ordered groups of 256 blocks.
- [x] Bound direct-address redispatch with a generated comparison tree and
  short linear leaves, without retaining the guest address table.
- [x] Evaluate translator-selected checked hash buckets for direct-address
  redispatch. The table contains native bucket labels only; full guest targets
  are validated in generated code and the original transition table remains
  discarded.
- [ ] Expand high-impact direct Xtensa lowerings after dispatch is scalable:
  - [x] direct near `call` with a specialized return-stack helper;
  - [x] near `ret` through the existing wrap-safe stack pop helper;
  - [x] stack operations:
    - [x] register and segment `push`/`pop`, including 8086 `push sp`;
    - [x] `pushf`/`popf` with the 8086 writable-flags mask;
    - [x] memory forms (neutral on the current Alley Cat block set);
  - [x] memory and byte forms of `cmp`, using ALU helpers only for flags beyond
    the direct `CF`/`ZF` subset;
  - [ ] memory and byte forms of `sub`;
  - [ ] common logical and increment/decrement instructions.

## Evaluation log

| Change | App bytes | CISC bytes | QEMU result | Decision |
|---|---:|---:|---|---|
| Baseline | 694,000 | 427,537 | Pass | Keep |
| Direct region range routing | 694,016 (+16) | 427,537 (+0) | Pass | Keep: size-neutral, removes failed region calls |
| Mixed single-step specialization | 631,872 (-62,144) | 365,577 (-61,960) | Pass | Keep: removes unreachable multi-block machinery |
| Elide dead CISC status flags | 622,832 (-9,040) | 356,695 (-8,882) | Pass | Keep: plain wrapping arithmetic replaces unused flag helpers |
| Shared ZF-only result helper | 622,880 (+48) | 356,695 (+0) | Not run | Revert: call sites do not shrink and the helper adds flash code |
| Pack CISC retired delta into the assembly handoff | 608,208 (-14,624) | 342,383 (-14,312) | Pass | Keep: one shared 64-bit synchronization path |
| Share static MZ PC materialization per region | 574,368 (-33,840) | 308,545 (-33,838) | Pass | Keep: replaces more than 4,000 repeated CS-relative expressions |
| Share direct assembly budget-exhaustion path | 562,704 (-11,664) | 308,545 (+0) | Pass | Keep: removes duplicated cold MZ formulas and edge-target literals |
| Prove register control-target reads cannot stop | 562,704 (+0) | 308,545 (+0) | Alley output unchanged; host pass | Keep: removes checks in programs with register-indirect control flow; Alley Cat has none |
| Direct near `call` with specialized stack helper | 540,832 (-21,872) | 226,493 (-82,052) | Pass | Keep: same helper-call count, less caller code, exact `SP`-then-write order |
| Full balanced comparison tree before stack-helper specialization | 567,648 (+5,312 from matching linear build) | 226,493 (+0) | Pass | Supersede: fast lookup but excessive code growth |
| Hybrid tree with 16-address leaves | 541,808 (+976 from linear) | 226,493 (+0) | Pass | Keep: bounds lookup to about 23 comparisons and restores normal melody tempo |
| Checked hash dispatch (128 buckets, shift 9, maximum load 17) | 541,792 (-16 from hybrid) | 226,493 (+0) | Pass; 41.8 s versus hybrid 41.7 s | Keep: fewer expected dispatch comparisons, normal melody tempo, no measurable QEMU regression |
| Fresh no-direct-`RET` control after CMake reconfigure | 691,024 | 226,493 | Build control | Compare only with the following row |
| Direct near `RET` and `RET imm16` | 682,400 (-8,624 from fresh control) | 204,691 (-21,802) | Pass; 60 frames, 259 Hz, clean shell return | Keep: 320 more native blocks, no new C wrapper, and a net size reduction |
| Direct register/segment `PUSH` and `POP` | 681,424 (-976) | 197,093 (-7,598) | Pass; 60 frames, 259 Hz, clean shell return | Keep: 73 more native blocks, explicit 8086 `PUSH SP`, and no new helper |
| Direct `PUSHF` and `POPF` | 681,328 (-96) | 196,906 (-187) | Pass; 60 frames, 259 Hz, clean shell return | Keep: one more native block and the existing `0x0fd5` writable-flags contract |
| Direct memory `PUSH` and `POP` | 681,328 (+0) | 196,906 (+0) | Host pass; Alley Cat QEMU unchanged | Keep: general translator coverage with no Alley Cat image cost |
| Direct byte/memory `CMP` and full-flags helper fallback | 673,072 (-8,256) | 139,398 (-57,508) | Pass; 60 frames, 259 Hz, clean shell return | Keep: 557 more native blocks and helpers only when partial direct flags are insufficient |

Blanket `-Os` and outlining hot instruction semantics remain excluded because
they can trade execution speed for size. The full comparison tree was measured
and replaced first by the bounded hybrid, then by the slightly smaller checked
hash dispatch. The coarse whole-run QEMU timing does not establish a measurable
speedup; a target-cycle benchmark remains necessary to quantify it on ESP32.
The full CMake reconfigure changed the common linked firmware size while the
226,493-byte generated CISC control stayed unchanged. Consequently, the direct
`RET` decision uses its immediately preceding fresh control rather than the
older absolute application-image rows.
