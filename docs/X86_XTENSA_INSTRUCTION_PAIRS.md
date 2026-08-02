# 8086 to ESP32 Xtensa instruction-pair policy

This document defines the preferred instruction pairs for the direct assembly
backend. It targets the original 8086 programming model and the ESP32 Xtensa
LX6 configuration selected by `xtensa-esp32-elf-gcc`, not a generic Xtensa
processor.

The primary Xtensa source is Cadence's official [Xtensa Instruction Set ISA
Summary](https://www.cadence.com/content/dam/cadence-www/global/en_US/documents/tools/silicon-solutions/compute-ip/isa-summary.pdf).
The installed Espressif GCC configuration and an assembler/objdump probe are
the final availability check because Xtensa instruction packages are
configurable.

## Target facts verified with the installed toolchain

The ESP32 compiler reports support for code density, zero-overhead loops,
`SEXT`, `ABS`, `MIN`/`MAX`, `MUL16S`/`MUL16U`, `MULL`, `MULSH`/`MULUH`,
`QUOS`/`QUOU`, `REMS`/`REMU`, `NSA`/`NSAU`, Boolean registers and MAC16.

An assembler probe additionally verified all instructions selected below.
`SALT` and `SALTU`, although present in the generic current ISA summary, were
rejected by the ESP32 assembler and must not be emitted. Use compare-and-branch
instructions instead.

The assembler automatically relaxed canonical `mov`, `movi`, `add`, `addi`
and `retw` source instructions to `mov.n`, `movi.n`, `add.n`, `addi.n` and
`retw.n` when their operands allowed it. The translator should therefore emit
canonical mnemonics and let the assembler choose density encodings. Explicit
`.n` spelling is useful only if a future audit proves that relaxation was
disabled.

## Selection rules

1. Preserve 8086 semantics before minimizing the instruction count.
2. A direct pair is preferred when produced flags are dead or can be consumed
   directly by the next operation.
3. Keep an 8- or 16-bit x86 value canonical with `EXTUI` when later 32-bit
   operations can observe upper bits. A width-specific store can provide the
   truncation when no subsequent register operation observes the value.
4. Fuse a flag producer with its consumer before materializing FLAGS.
5. Use a short inline sequence for `CF` and `ZF`; use shared x86 helpers when
   `PF`, `AF`, `SF` or `OF` would make the inline sequence larger or slower.
6. Guest memory accesses remain behind the common memory contract unless a
   separately proven fast path preserves 20-bit wrapping, segment-offset
   wrapping, unaligned accesses, CGA mapping and faults.
7. Rank valid candidates by measured target cycles first, linked bytes second.
   QEMU cycle-counter results are only a repeated paired approximation; the
   physical ESP32 is authoritative.

## Preferred arithmetic and data pairs

| 8086 operation | Preferred Xtensa lowering | Conditions and notes |
|---|---|---|
| `MOV r,r` | `MOV` | The assembler normally selects `MOV.N`. |
| `MOV r,imm` | `MOVI`, otherwise interned `L32R` | `MOVI` covers signed 12-bit values; its density form covers `-32..95`. |
| `MOV r8/r16,[host]` | `L8UI` / `L16UI` | Only for proven host addresses. Guest addresses normally use the common read helper. |
| `MOV [host],r8/r16` | `S8I` / `S16I` | Same guest-memory restriction. |
| `ADD r,r` | `ADD`, then `EXTUI` if needed | Exact value pair when flags are dead. The assembler may select `ADD.N`. |
| `ADD r,imm8` | `ADDI`, then `EXTUI` if needed | Use when the signed immediate is `-128..127` and `CF` is dead. |
| `SUB r,r` | `SUB`, then `EXTUI` if needed | Exact value pair when flags are dead. |
| `SUB r,imm` | `ADDI r,r,-imm` | Xtensa has no `SUBI`; use this for a representable negated immediate when `CF` is dead. |
| `INC` / `DEC` | `ADDI +1` / `ADDI -1` | Preserve x86 `CF`; the assembler can select `ADDI.N`. |
| `AND` / `OR` / `XOR` | `AND` / `OR` / `XOR` | Direct value pair; materialize only live x86 flags. |
| `TEST` | `AND` into a temporary | Do not store the result. Fuse a following `JZ`/`JNZ` into `BEQZ`/`BNEZ`. |
| `NOT` | `MOVI -1; XOR` | Truncate only when upper bits remain observable. |
| `NEG` | `NEG` | Direct result pair; x86 flags still require inline logic or a helper. |
| `CBW` | `SEXT dst,src,7` | The low 16 bits are the exact sign-extended AL result. |
| `CWD` | `SEXT tmp,AX,15; SRLI DX,tmp,16` | Produces `0000h` or `FFFFh`. |
| `LEA` | `ADD`, `ADDI`, `ADDMI`, or `ADDX2/4/8` | Select from the proven address expression; do not perform a guest load. |
| `XCHG r,r` | three `MOV` operations with a temporary | There is no integer swap instruction. Memory forms stay in a helper. |

## Preferred multiply and divide pairs

| 8086 operation | Preferred Xtensa lowering | Conditions and notes |
|---|---|---|
| `MUL r/m16` | `MUL16U` | The 32-bit product maps directly to `DX:AX`; set `CF=OF` from the upper half only if live. |
| `MUL r/m8` | mask both bytes, then `MUL16U` | Store the 16-bit result in AX; `CF=OF` iff AH is nonzero. |
| `IMUL r/m16` | `MUL16S` | The 32-bit signed product maps to `DX:AX`; overflow flags compare the upper half with sign extension of AX. |
| `IMUL r/m8` | `SEXT` both operands, then `MUL16S` | Store the low 16 bits in AX and derive live overflow flags. |
| `DIV r/m8,16` | guarded `QUOU` plus `REMU` | Check divisor zero and x86 quotient overflow before committing AX/DX. |
| `IDIV r/m8,16` | guarded `QUOS` plus `REMS` | Also guard signed overflow and the 8086 quotient range. Keep the helper until differential tests cover all edges. |

Xtensa divide instructions cannot replace x86 division without guards: an
Xtensa exception is not an 8086 divide error, and the permitted quotient width
is different.

## Preferred shift and rotate pairs

| 8086 operation | Preferred Xtensa lowering | Conditions and notes |
|---|---|---|
| `SHL imm` | `SLLI` | Canonicalize to 8/16 bits and materialize only live flags. |
| `SHR imm` | `SRLI` | Same. |
| `SAR imm` | `SEXT`, then `SRAI` | Sign-extend from bit 7 or 15 before shifting. |
| variable `SHL` | `SSL count; SLL` | Only after handling original-8086 counts greater than 31 explicitly. |
| variable `SHR` / `SAR` | `SSR count; SRL` / `SRA` | The Xtensa SAR register masks its count; the original 8086 does not have later-x86 five-bit count masking. |
| `ROR` | `SSAI`/`SSR` plus `SRC` | Replicate the 8/16-bit operand before a 32-bit combined shift. |
| `ROL` | complementary `SRC` sequence | Prefer a helper when flags are live or the count is not constant. |

Do not translate an arbitrary x86 `LOOP` instruction to Xtensa `LOOP`.
The semantic direct pair is `ADDI CX,-1; BNEZ`. Xtensa zero-overhead `LOOP`
becomes appropriate only after trace formation proves one native loop body,
entry semantics, trip count and supervisor-budget checks.

## Preferred adjacent-instruction fusion

Xtensa's three-register operations can eliminate an x86 copy whose destination
is immediately consumed. These fusions require both instructions to be in one
basic block, the ALU flags to be dead or fused with their consumer, and partial
register aliases to be resolved explicitly.

| Adjacent 8086 operations | Preferred Xtensa lowering |
|---|---|
| `MOV d,s; ADD d,t` | `ADD d,s,t` |
| `MOV d,s; SUB d,t` | `SUB d,s,t` |
| `MOV d,s; AND/OR/XOR d,t` | `AND/OR/XOR d,s,t` |
| `MOV d,s; ADD/SUB d,imm8` | `ADDI d,s,+/-imm8` |
| `MOV d,s; INC/DEC d` | `ADDI d,s,+1/-1` |
| `MOV d,s; AND d,(2^n-1)` | `EXTUI d,s,0,n` |
| `MOV d,s; SHL/SHR d,n` | `SLLI/SRLI d,s,n` |
| `SHL d,1/2/3; ADD d,t` | `ADDX2/4/8 d,d,t` |

There is no general Xtensa integer instruction for `d = s + t + immediate`.
`ADDX2/4/8` supplies only an implicit scale factor, not a third additive input.
Inside a helper-free dead-flags run, operations may retain noncanonical upper
bits: the low 16 bits remain exact modulo 2^16 through the supported arithmetic
and logical operations, and the final `S16I` performs the required truncation.

## Preferred compare and branch fusion

This is the highest-value pairing because Xtensa compare-and-branch
instructions need no condition-code register.

| 8086 producer and consumer | Preferred Xtensa branch |
|---|---|
| `CMP a,b; JE/JNE` | `BEQ` / `BNE` |
| `CMP a,b; JB/JAE` | `BLTU` / `BGEU` |
| `CMP a,b; JL/JGE` | sign-extend 8/16-bit operands, then `BLT` / `BGE` |
| `CMP a,b; JBE` | `BLTU` followed by `BEQ` |
| `CMP a,b; JA` | inverse of the `JBE` pair |
| `TEST a,b; JZ/JNZ` | `AND tmp,a,b; BEQZ/BNEZ tmp` |
| `INC/DEC/ADD/SUB ...; JZ/JNZ` | branch on the canonical result directly |

When FLAGS are already materialized, use `AND` plus `BEQZ`/`BNEZ` for single
flag tests. For a pending arithmetic result, branch directly on operands or
the result and avoid a FLAGS load/store entirely.

## Operations that deliberately remain shared helpers

- `ADC` and `SBB` when carry is live: Xtensa has no integer carry flag input.
- `AAA`, `AAS`, `DAA`, `DAS`, `AAM`, `AAD`: decimal-adjust semantics have no
  useful one-instruction pair.
- `PUSH`, `POP`, `CALL`, `RET`, far control transfers and `IRET`: the guest
  segmented stack, wraparound, faults and translated-target dispatch are not
  the Xtensa call ABI.
- `INT`, `IN` and `OUT`: direct assembly calls the program-independent DOS
  shell helpers; it must not use Xtensa exception or special-register I/O.
- `MOVS`, `STOS`, `LODS`, `CMPS` and `SCAS`: use common string/pattern helpers
  until a conventional-RAM trace proves that an inline load/store loop is safe.
- `LAHF`, `SAHF`, `PUSHF` and `POPF`: these consume or expose architectural
  FLAGS and force pending flags to materialize.

## Implementation order

1. Expand adjacent copy/ALU fusion from cached 16-bit runs to proven 8-bit and
   trace-level operations.
2. Add `CMP`/`TEST` plus `Jcc` fusion before expanding flag materialization.
3. Add direct `CBW`, `CWD` and `NEG` sequences.
4. Replace word and byte multiply helpers with `MUL16U`/`MUL16S` sequences.
5. Select `ADDX2/4/8`, `ADDMI` and reusable address expressions for `LEA` and
   guest effective-address calculation.
6. Add guarded `QUO`/`REM` division only with exhaustive differential tests.
7. Use zero-overhead loops for proven native traces and safe string fast paths,
   never for an isolated x86 `LOOP` instruction.
