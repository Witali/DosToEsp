#ifndef D2E_NATIVE_ASM_OFFSETS_H
#define D2E_NATIVE_ASM_OFFSETS_H

/*
 * Stable 32-bit ABI offsets used by generated Xtensa assembly. Keep the
 * matching compile-time checks in native_runtime.c in sync with this file.
 */
#define D2E_ASM_CPU_REGS_OFFSET 0
#define D2E_ASM_CPU_SEGMENTS_OFFSET 16
#define D2E_ASM_CPU_IP_OFFSET 24
#define D2E_ASM_CPU_STOP_REASON_OFFSET 64
#define D2E_ASM_CPU_FAULT_CS_OFFSET 68
#define D2E_ASM_CPU_FAULT_IP_OFFSET 70
#define D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET 80

#define D2E_ASM_X86_CS_INDEX 1
#define D2E_ASM_STOP_EXITED 1
#define D2E_ASM_STOP_UNTRANSLATED_TARGET 2

#endif
