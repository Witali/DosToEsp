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
- [ ] Apply whole-program flag liveness to CISC lowering. Emit plain arithmetic
  when no produced flag is live and materialize only required flags otherwise.
- [ ] Use a bounded 32-bit retired-instruction delta and materialize the 64-bit
  counter only at synchronization points.
- [ ] Share cold budget-exhaustion and guest-PC materialization paths instead
  of repeating them in every block.
- [ ] Remove stop-reason checks only after translator-backed proof that the
  preceding operation cannot fault.
- [ ] Partition CISC blocks by CFG locality and estimated linked byte size,
  rather than fixed address-ordered groups of 256 blocks.
- [ ] Expand high-impact direct Xtensa lowerings after dispatch is scalable:
  near `call`/`ret`, stack operations, memory and byte forms of `cmp`/`sub`,
  then common logical and increment/decrement instructions.

## Evaluation log

| Change | App bytes | CISC bytes | QEMU result | Decision |
|---|---:|---:|---|---|
| Baseline | 694,000 | 427,537 | Pass | Keep |
| Direct region range routing | 694,016 (+16) | 427,537 (+0) | Pass | Keep: size-neutral, removes failed region calls |
| Mixed single-step specialization | 631,872 (-62,144) | 365,577 (-61,960) | Pass | Keep: removes unreachable multi-block machinery |

Blanket `-Os`, binary-search dispatch, and outlining of hot instruction
semantics are not default solutions because they can trade execution speed for
size. They may be reconsidered only with measured QEMU evidence.
