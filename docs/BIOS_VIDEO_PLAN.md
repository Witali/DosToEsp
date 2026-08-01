# BIOS and video implementation plan

## Scope

The target CPU remains the documented Intel 8086 instruction set. The machine
contract is the smallest PC/AT-compatible real-mode BIOS, DOS and video layer
required by the fingerprinted Alley Cat and Volkov Commander 4.00 binaries.
Unobserved functions remain strict diagnostic boundaries.

Observed interrupt-number scope:

- Alley Cat: BIOS `INT 10h`, `11h` and `1Ah`.
- Volkov Commander: BIOS `INT 10h`, `15h`, `16h` and `1Ah`.
- Volkov Commander also requires non-BIOS `INT 21h`, `28h`, `2Fh` and `33h`.

Static analysis identifies interrupt numbers. A reference trace must confirm
the dynamic `AH`/`AL` subfunctions before the strict boundary can be considered
complete.

## 1. Common interrupt boundary

- [x] Add a configurable native interrupt callback to the 8086 state.
- [x] Preserve that callback across program loading and CPU reset.
- [x] Keep DOS termination (`INT 20h`, `INT 21h/AH=4Ch`) in the common runtime.
- [x] Report an unsupported interrupt as `(interrupt << 8) | AH`.
- [x] Add an explicit wait-for-input stop state instead of busy emulation.

Acceptance: unsupported services stop deterministically with `CS:IP`, interrupt
and function; supported services return without an x86 interpreter.

## 2. PC/AT BIOS foundation

- [x] Implement `INT 11h` equipment word and `INT 12h` conventional memory.
- [x] Implement deterministic `INT 1Ah` tick get/set and baseline RTC queries.
- [x] Implement `INT 16h` read/check/shift-state services with a key queue.
- [x] Implement the observed baseline `INT 15h` services (`86h`, `88h`, `90h`,
  `91h`, `C0h`) as strict deterministic PC/AT responses.
- [x] Maintain BIOS Data Area video fields used by DOS software.
- [x] Drive ticks at 18.2065 Hz and implement midnight rollover from the
  ESP32 clock.
- [x] Map BOOT and UART/ANSI input to BIOS scan/ASCII codes; modifier state
  remains for a future multi-button or USB keyboard source.
- [ ] Confirm every observed subfunction with a reference trace.

Acceptance: Alley Cat and Volkov Commander pass every observed non-video BIOS
call or stop on a precisely identified missing subfunction.

## 3. BIOS video services

- [x] Implement mode set/query, active page and cursor services.
- [x] Implement text read/write, teletype and rectangular scroll operations.
- [x] Implement CGA background/palette and BIOS pixel read/write operations.
- [x] Implement baseline EGA identification, font-info and palette calls.
- [ ] Complete only the additional `INT 10h` subfunctions proven by traces.

Acceptance: BIOS-visible registers, flags, BDA state and video memory match an
independent reference for all calls used by both programs.

## 4. CGA output

- [x] Map direct `B8000h` accesses ahead of conventional RAM.
- [x] Model the observed CGA CRTC, mode, palette and status ports.
- [x] Model deterministic PIT channels and PC/AT system port `61h` used by
  Alley Cat timing and speaker setup.
- [x] Render CGA modes 4/5 (320x200, two bits per pixel) to RGB565.
- [x] Render CGA mode 6 (640x200 monochrome) with horizontal downsampling for
  the 320-pixel panel.
- [x] Submit 320x200 rows centered vertically on the 320x240 ST7789.
- [ ] Add dirty-row tracking so unchanged CGA rows are not retransmitted.

Acceptance: direct VRAM and BIOS pixel writes produce identical frame hashes;
the physical panel shows the Alley Cat title and first playable scene.

## 5. EGA and text output

- [ ] Add EGA planar `A0000h` memory, sequencer/graphics-controller registers
  and 16-colour palette state for observed accesses.
- [ ] Render observed EGA graphics modes to 320x240 RGB565.
- [x] Add an attributed text renderer for 40/80-column modes using CP437,
  including box-drawing characters used by Volkov Commander.
- [x] Support 25/43-row text scaling, attributes, blink, cursor and page
  offsets in the display renderer.
- [x] Reuse the verified HLV-codec ST7789 DMA submission path.

Acceptance: deterministic text/EGA frame hashes and a readable Volkov Commander
panel on the physical CYD display.

## 6. Interactive Alley Cat in QEMU

- [x] Keep a bounded, deterministic multi-slice probe for automated builds.
- [x] Add a separate continuous QEMU execution mode that does not stop at the
  diagnostic slice limit.
- [x] Route QEMU UART/ANSI input through the same BIOS scan/ASCII mapper used
  by the physical board.
- [x] Advance BIOS time from a real-time frame scheduler instead of one synthetic
  tick per diagnostic slice.
- [x] Export CGA VRAM and render it in a host-side BMP viewer because ESP32
  QEMU does not model the external SPI ST7789 panel.
- [x] Record hashes for consecutive frames and distinguish unchanged, dirty
  and animated frames in regression output.
- [ ] Continue execution with scripted keys until the title screen, start of
  gameplay and first input response are proven.
- [x] Deliver scripted and UART keys as XT make/break scan codes through ports
  `60h`/`64h`, PIC EOI port `20h` and the game's native IRQ1 handler.
- [ ] Record dynamic `CS:IP`, interrupt subfunctions and port accesses at every
  new strict boundary, then implement only the observed missing behaviour.

Acceptance: one command opens a host framebuffer, accepts keyboard input and
runs Alley Cat continuously; an automated companion command verifies stable
multi-frame hashes without requiring the physical display.

## 7. DOS and auxiliary services for Volkov Commander

- [ ] Trace and implement required `INT 21h` memory, drive, directory, file and
  process functions against a sandboxed filesystem provider.
- [ ] Implement the observed `INT 28h` idle contract.
- [ ] Implement only observed `INT 2Fh` multiplex queries.
- [ ] Implement the observed `INT 33h` mouse reset, state and position calls.

Acceptance: VC reaches its two-panel UI, lists a sandboxed directory and reacts
to keyboard input without silently fabricating unimplemented DOS behaviour.

## 8. Validation sequence

1. Run the full host suite after every semantic milestone.
2. Compile all generated fixtures with the Xtensa toolchain.
3. Run both the bounded Alley Cat probe and the continuous interactive QEMU
   mode; continue each to the next strict boundary.
4. Generate Volkov Commander only after all static instruction sites and
   dynamic control targets are proven.
5. Record consecutive framebuffer hashes, dirty-frame state, interrupt
   telemetry and heap usage in QEMU.
6. Flash the CYD2USB board and validate display, input and timing physically.
