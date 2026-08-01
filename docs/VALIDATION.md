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

## 2026-08-01: interactive Alley Cat QEMU loop

The board execution loop is now also available in QEMU without the bounded
64-slice diagnostic limit. It uses `esp_timer` for BIOS time, polls UART0
through the common ANSI-to-PC-key mapper, and records whether each sampled CGA
frame changed. A bounded eight-frame invocation of the continuous path reached
2,722,831 translated instructions without a strict boundary. The first frame
had mode 4 hash `9337185a`; the final sample is emitted even when unchanged so
the regression distinguishes a stable frame from missing telemetry.

## 2026-08-01: host-visible QEMU CGA frame

The bounded interactive firmware can now emit a complete, delimited 16 KiB
CGA VRAM snapshot. The host converter validates that every byte is present,
renders modes 4/5/6 with the same palette and 320x240 geometry as the board,
and writes a dependency-free 24-bit BMP. The one-command eight-frame capture
completed without a strict boundary and produced:

```text
D2E_FRAME,seq=1,mode=4,dirty=1,fnv1a=9337185a
D2E_FRAME,seq=8,mode=4,dirty=0,fnv1a=9337185a
D2E_VRAM_BEGIN,mode=4,mode_control=0a,color_control=00,size=16384
D2E_VRAM_END
D2E_ALLEY_STOP,reason=8,csip=1723:2b62,instructions=2722831,...
rendered CGA mode 4: out\qemu\alley-cat-frame.bmp (16384 VRAM bytes)
```

The BMP is 230,454 bytes and has SHA-256
`BD78FEE5BFB5CF1F9170BC5CFB2E87D5328993B5DF0BAF2E0C9A995229A79720`.
It was decoded and visually inspected as a non-empty red/green CGA frame.

## 2026-08-01: hardware interrupt AOT roots

The static frontend now recognises the 8086 compiler pattern that writes a
near offset followed by `CS` into the real-mode interrupt vector table. For
Alley Cat it recovers IRQ1 vector 9 targets `CS:14B3` and `CS:14FB`, adding
both handlers as native AOT roots. The expanded inventory has 8,480
instructions, 3,232 blocks, 4,891 edges, no unresolved flow and 100% current
translation coverage.

A generated COM regression installs vector 9, executes its handler through a
real `IRET` frame and verifies the external `JMP F000:E05B` remains a strict
untranslated-target boundary. The string regression also executes
`REPNE SCASB` through a successful match. The real `CAT.EXE` source build is
again `complete` and emits `game_native.c`.

## 2026-08-01: native keyboard IRQ1 delivery

The PC/AT boundary now keeps an XT make/break scan-code queue, exposes keyboard
data/status ports `60h`/`64h`, accepts PIC EOI on port `20h`, and pushes a real
`FLAGS`, `CS`, `IP` interrupt frame before routing vector 9 to translated code.
Host tests verify the `39h/B9h` Space pair and the exact six-byte stack frame.

The 150-frame scripted QEMU run then proved that both events execute the IRQ1
handler recovered from `CAT.EXE`:

```text
D2E_KEY,frame=120,ascii=20,scan=39
D2E_IRQ,frame=120,vector=09,target=1723:14b3,pending=2
D2E_IRQ,frame=121,vector=09,target=1723:14b3,pending=1
D2E_ALLEY_STOP,reason=8,...,instructions=42724413,...
```

The make and break interrupts returned through native `IRET` without hitting a
strict boundary. A longer Space/Right/Space/Left run also completed, but its
final framebuffer remained at hash `99881404`; therefore the correct
title-screen start action and first playable scene are not yet claimed.

## 2026-08-01: Windows QEMU ST7789 and SDSPI board run

The Alley Cat firmware now has a bounded board-device QEMU configuration that
keeps the production SPI2 ST7789 renderer enabled while preserving the QEMU
restart/exit and frame-limit controls. It also initializes the CYD SPI3 pins,
mounts a FAT card with ESP-IDF's SDSPI/VFS stack and reads the HLV QEMU marker.
The native Windows QEMU from HLV-codec attaches both patched devices; snapshot
mode prevents the source flash and SD images from being modified.

A headless eight-frame smoke run and a visible 240-frame SDL run both passed.
The visible run reported:

```text
D2E_SD_READY,sectors=262144,marker=HLV ESP32 SPI3 SD test
D2E_FRAME,seq=1,mode=4,dirty=1,fnv1a=9337185a
D2E_FRAME,seq=91,mode=4,dirty=1,fnv1a=ec9bb1da
D2E_FRAME,seq=97,mode=4,dirty=1,fnv1a=99881404
D2E_KEY,frame=120,ascii=20,scan=39
D2E_IRQ,frame=120,vector=09,target=1723:14b3,pending=2
D2E_QEMU_DONE,0
```

This validates the same ESP-IDF display and SD drivers used by the CYD board,
not a host-side framebuffer substitute. The changing hashes prove that the
guest renderer submitted multiple distinct CGA frames to the emulated panel;
they do not yet establish entry into the first playable scene.

## 2026-08-01: translated Alley Cat reaches the playable scene

The earlier red/green eight-frame capture was reclassified as an intermediate
CGA buffer, not an Alley Cat screen. Two general compatibility defects were
then fixed without adding game code to the translator:

- BIOS `INT 10h/AH=0Eh` and character-write services now rasterise CP437 glyphs
  in CGA graphics modes 4/5/6, with the correct 40-column modes 4/5 and
  640-pixel mode 6 boundary;
- MZ relocations are applied to the byte view used for disassembly, so a
  segment immediate such as `0010h` becomes `1010h` in native C when the load
  segment is `1000h`. The packed original image and relocation table remain
  unchanged for the runtime loader.

A synthetic one-relocation MZ regression proves the second rule independently
of Alley Cat. The real generated IRQ1 code now loads data segment `1010h`, and
the setup harness waits for the three guest wait blocks before sending N, K
and Space. The 900-frame Windows QEMU run entered the active game loop and
produced a visually inspected scene containing the fence, windows, bins and
cat:

```text
D2E_KEY,frame=782,ascii=6e,scan=31,wait=0d127
D2E_KEY,frame=783,ascii=6b,scan=25,wait=0d159
D2E_KEY,frame=785,ascii=20,scan=39,wait=0d1da
D2E_FRAME,seq=900,mode=4,dirty=1,fnv1a=8a6ce86f
D2E_ALLEY_STOP,reason=8,csip=1723:237f,instructions=198561264,...
D2E_QEMU_DONE,0
```

The rendered 230,454-byte BMP has SHA-256
`DD427CC81CF75DFD779F7C77AAE28986F5C2C451DE2FBCC2834D017015251618`.
The full host suite also passed, including the source frontend, all 18 C test
executables and the generated 54,555-byte Alley Cat MZ image with nine runtime
relocations.
