# Validation record

## 2026-07-31: native translation smoke milestone

The host translator converted an 11-instruction 8086 COM fixture into five C
basic-block functions. ESP-IDF 5.5.5 then compiled those functions into the
classic ESP32's Xtensa LX6 instruction set. The runtime dynamically retired 15
guest instructions because one block contains a three-iteration `loop`.

The same image logic passed in both environments:

```text
QEMU:  D2E_NATIVE_OK,exit=42,ax=4c2a,cx=0000,instructions=15
       D2E_QEMU_DONE,0

BOARD: D2E_NATIVE_OK,exit=42,ax=4c2a,cx=0000,instructions=15
       D2E_BOARD_DONE,0
```

Physical target: ESP32-D0WD-V3 revision 3.1 on the HLV-codec CYD2USB board,
connected through its CH340 interface on COM8. Flash writes and SHA verification
completed successfully. The application image was 145264 bytes, leaving 86% of
the one-megabyte application partition free.

This milestone verifies native translated control flow, arithmetic, flags,
DOS process exit, sparse conventional memory, and the ESP32 build boundary. It
does not yet claim that a complete game is supported.

## 2026-07-31: register-cached native regions

The generator now emits one native C region for the reachable fixture CFG.
AX and CX remain compiler-allocated values across direct internal edges and
the three loop iterations; guest blocks are labels rather than Xtensa ABI
function boundaries. State is committed at an interrupt, diagnostic boundary
or scheduler budget yield.

Host testing forced a yield after two dynamic blocks and observed
`IP=0106, AX=0006, CX=0002, instructions=5`; resuming reached the original
15-instruction exit state. The strengthened Xtensa assembly audit found the
single `program_region` symbol and no guest `block_*` function symbols.

The regenerated firmware passed both QEMU and physical COM8 smoke tests with
the same state as above. Its application image was 145440 bytes, leaving 86%
of the application partition free.

## 2026-07-31: Alley Cat MZ load image

The ignored user-supplied `CAT.EXE` is packed into generated C during local
host testing. The loader copied its 54555-byte load module, created the PSP,
set initial `CS:IP=1723:0000`, `SS:SP=1000:0100`, `DS=ES=0FF0`, and verified
all nine relocated words after adding module segment `1000h`. The generic
loader also rejects a relocation whose target is outside the MZ load module.

The extended program ABI retained compatibility with the translated COM
fixture: host tests, Xtensa assembly audit and ESP32 QEMU smoke all passed.

## 2026-07-31: complete Alley Cat static source generation

A strict recognizer recovered the eight-entry `CS:[BX+0250h]` jump table after
proving the preceding BX range check and scale. This expanded the reachable
CFG from 4224 to 8368 instructions and exposed `ADC`, `PUSHF` and `POPF`
semantics that were not visible before. Dedicated COM fixtures for the jump
table and carry/flags stack pass on the host and compile with the Xtensa
toolchain.

The automatic frontend now reports `complete`, emits a 3,045,220-byte
`game_native.c`, and covers 8368/8368 instruction sites. Espressif GCC 14.2.0
produced a complete 3,609,428-byte Xtensa assembly file, which assembled into
a 1,655,940-byte object. The load-relevant `.literal`, `.text` and `.rodata`
sections total 531,407 bytes before the runtime and final link. This validates
static source generation and target compilation; BIOS, ports, timing, input
and display integration remain before the generated game can execute through
gameplay.

## 2026-07-31: first Alley Cat ESP32 QEMU execution

The MZ generator now partitions large control-flow graphs into bounded native
regions and emits a compact `CS:IP` router between them. Alley Cat currently
produces 13 native regions; this avoids Xtensa literal-range overflows without
introducing an x86 instruction interpreter. The Alley Cat firmware build also
uses a single compiler job so its large generated translation fits reliably
within the available host memory.

ESP-IDF linked the real generated game into a 624,944-byte application image,
leaving 40% of the one-megabyte application partition free. ESP32 QEMU booted
that image and produced:

```text
D2E_ALLEY_START,csip=1723:0000,sssp=1000:0100,heap=157436
D2E_ALLEY_STOP,reason=6,csip=1723:5c62,ax=0000,bx=0000,cx=0000,dx=0000,instructions=5,address=00000000,heap=157436
D2E_QEMU_DONE,0
```

Stop reason 6 is the strict unhandled-interrupt boundary. The preceding target
instruction is `INT 11h` at load-module offset `CE90h`, requesting the BIOS
equipment list; the reported `CS:IP` is the following instruction. This proves
that the automatic `CAT.EXE` translation can be compiled, linked, booted and
entered as native Xtensa firmware. It does not yet claim title-screen or
gameplay execution.

## 2026-07-31: Alley Cat PC/AT BIOS and port execution

The firmware now attaches the generated executable to the common PC/AT BIOS
dispatcher and device-port layer. An intermediate QEMU probe passed the BIOS
equipment call and stopped after 99 instructions at PIT control port `43h`.
After adding deterministic PIT channels, system port `61h`, and the observed
CGA CRTC, palette and status ports, the same image produced:

```text
D2E_ALLEY_START,csip=1723:0000,sssp=1000:0100,heap=157260
D2E_ALLEY_STOP,reason=8,csip=1723:2b62,ax=0000,bx=2b02,cx=0000,dx=3a98,instructions=340875,address=00000000,heap=157260
D2E_QEMU_DONE,0
```

Stop reason 8 is the configured translated-instruction budget, not an
unsupported interrupt, port or instruction. The probe therefore executes
340,875 native-translated 8086 instructions through the current initialization
path without crossing a strict hardware boundary. Rendering and input remain
the next acceptance gates; this result alone does not claim playable output.

## 2026-07-31: CYD display build

The firmware now uses the verified HLV-codec ST7789 SPI2 DMA path. CGA modes
4/5/6 and attributed 40/80-column CP437 text are rendered as 320x200 RGB565
rows centered vertically on the 320x240 panel. Text rendering covers 25- and
43-row layouts, active-page offsets, cursor, blink and box-drawing glyphs.

The physical Alley Cat configuration compiled and linked successfully. After
adding continuous translated-code slices, an 18.2065 Hz BIOS clock, deferred
`INT 16h` completion, BOOT-as-Space and UART/ANSI keyboard input, its
application image is 693,888 bytes (`0xA9680`), leaving 34% of its one-megabyte
partition free. A 64-slice QEMU probe then executed 21,778,510 translated
instructions without an unsupported boundary and reported:

```text
D2E_ALLEY_SLICES,64
D2E_ALLEY_VIDEO,mode=4,nonzero=15002,fnv1a=9337185a
D2E_ALLEY_STOP,reason=8,csip=1723:2b4b,ax=0000,bx=c41a,cx=0000,dx=3a98,instructions=21778510,address=00000000,heap=157260
```

This proves that initialization reaches a non-empty CGA mode 4 frame with a
deterministic VRAM hash. Physical serial-port enumeration found no connected
COM device during this run, so the new Alley Cat image has not yet been flashed
for visual inspection on the panel.
