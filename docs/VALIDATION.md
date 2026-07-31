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
